"""Shared decisions and operator event log for standalone matches."""

import argparse
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from contextlib import ExitStack, nullcontext
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from random import Random
import sys
from threading import Lock
from time import monotonic_ns

from chatarena.message import Message, MessagePool, MODERATOR_NAME, SYSTEM_NAME
from concordia.language_model.language_model import LanguageModel

from .either_or.discussion import CHANNEL_NAMES, format_speech
from .either_or.lay_the_grass.simulation import ConcordiaBackend, parallel_actions
from .models import ActionLanguageModel, DEFAULT_EFFORT, DEFAULT_MODELS, Review, StrategyNote, open_model
from .personas import persona_context
from .relationships import REASON_LIMIT, Ratings, RelationshipState, format_ratings, parse_ratings
from .resume import MatchLog, ResumeError
from .resume_legacy import LegacyDecisions


REVIEWABLE_BATCH_PHASES = {"representative", "memory_poker", "submit", "symmetry_arrange"}
EFFORTS = ("low", "medium", "high", "xhigh")
DEFAULT_GUEST_MODEL = ("codex", "gpt-6.1-sol", "low")
DAY_ONE_MAIN = "1일차 메인 매치 · 양자택일"
DAY_ONE_PRISON = "1일차 감옥 매치 · 무거운 13"
DAY_TWO_MAIN = "2일차 메인 매치 · 미스터리 거래소"
DAY_TWO_PRISON = "2일차 감옥 매치 · 러시안 룰렛"
DAY_THREE_MAIN = "3일차 메인 매치 · 보석 암시장"
DAY_THREE_PRISON = "3일차 감옥 매치 · 돼지 저금통"
DAY_FOUR_MAIN = "4일차 메인 매치 · 경매 빙고"
DAY_FOUR_PRISON = "4일차 감옥 매치 · 벽바둑 2"
DAY_FIVE_MAIN = "5일차 메인 매치 · 히든 워드"
DAY_FIVE_PRISON = "5일차 감옥 매치 · 수식의 탑"
FIRST_EXILE = "유배지 매치 1 · 피스 퍼즐"
SECOND_EXILE = "유배지 매치 2 · 달라진 그림 찾기"
THIRD_EXILE = "유배지 매치 3 · 비밀 코드"
FOURTH_EXILE = "유배지 매치 4 · 울타리 치기"
FIFTH_EXILE = "유배지 매치 5 · 대칭 퍼즐"


def canonical_game_title(title: str) -> str:
    """Recognize the former second-exile title without rewriting saved records."""
    return SECOND_EXILE if title == "유배지 매치 2 · 틀린 그림 찾기" else title


PRISON_STAGES = {
    DAY_ONE_MAIN: (DAY_ONE_PRISON, 7), DAY_TWO_MAIN: (DAY_TWO_PRISON, 6), DAY_THREE_MAIN: (DAY_THREE_PRISON, 4),
    DAY_FOUR_MAIN: (DAY_FOUR_PRISON, 3),
    DAY_FIVE_MAIN: (DAY_FIVE_PRISON, (3, 2)),
}
RELATIONSHIP_EVIDENCE = {
    "room_move", "teams", "rectangle_result", "team_vote", "choice_4_result", "grass_choices", "grass_placement",
    "grass_bonus", "choice_9_result", "poker_ranking", "placement", "market", "trade_fill", "inspection", "shift", "swap",
    "gem_auction", "gem_swap", "gem_bonus", "gem_reveal", "gem_card", "gem_peek", "gem_final",
    "pig_deposit", "pig_claim", "pig_doubt", "pig_replace", "pig_reset", "pig_challenge", "pig_reset_vote",
    "bingo_shapes", "bingo_result", "bingo_reveal", "bingo_submission",
    "word_similarity", "word_clue", "word_verdict", "word_final",
}


def encode(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


@dataclass(frozen=True)
class Decision:
    prompt: str
    default: str
    options: Sequence[str] = ()
    valid: Callable[[str], bool] | None = None
    invalid_default: str | None = None

    def accepts(self, action: str) -> bool:
        return self.valid(action) if self.valid is not None else action in self.options

    def instructions(self) -> str:
        if self.options:
            return self.prompt + "\n다음 중 하나를 그대로 출력하세요.\n" + "\n".join(self.options)
        return self.prompt


class Match:
    def __init__(
        self, players: Sequence[str], seed: int, *, pieces=None, model=None, live_players=(), live_turns=0,
        on_event: Callable[[Message], None] | None = None, allow_review: bool = True,
        relationships: RelationshipState | None = None,
        models: Mapping[str, LanguageModel] | None = None,
        resume_log: MatchLog | None = None, count_calls: Callable[[], int] | None = None,
    ):
        self.players = tuple(players)
        self.rng = Random(seed)
        self.policy = Random(seed)
        self.pieces = dict(zip(players, pieces, strict=True)) if pieces is not None else dict.fromkeys(players, 1)
        self.messages = MessagePool()
        self.live_turns = live_turns
        self._turn_lock = Lock()
        self.models = dict.fromkeys(live_players, model) if model is not None else {}
        if models is not None:
            self.models.update(models)
        self.allow_review = allow_review
        self.relationship_reviews_enabled = True
        self.on_event = on_event
        self.resume_log = resume_log
        self.count_calls = count_calls
        self.model_observations: Callable[[str, list[Message]], list[Message]] | None = None
        self.legacy = (LegacyDecisions(resume_log.events)
                       if resume_log and resume_log.resume and not resume_log.journal.remaining else None)
        previous = relationships or {}
        self.relationships: RelationshipState = {
            name: {other: rating.copy() for other, rating in previous.get(name, {}).items() if other in self.players}
            for name in self.players
        }
        self._relationship_reviewed: dict[str, int] = {}
        self.backends = {
            name: ConcordiaBackend(name, player_model, relationships=self.relationships[name])
            for name, player_model in self.models.items()
        }

    @property
    def events(self) -> list[Message]:
        return self.messages.get_all_messages()

    def event(self, kind: str, data: object, *, private: Sequence[str] = (), actor=SYSTEM_NAME) -> None:
        event = Message(
            agent_name=actor, content=data if isinstance(data, str) else encode(data),
            turn=len(self.events), msg_type=kind, visible_to=list(private) if private else "all",
        )
        self.messages.append_message(event)
        if self.on_event is not None:
            self.on_event(event)

    def observations(self, name: str) -> list[Message]:
        return self.messages.get_visible_messages(name, len(self.events))

    def decision(self, key, invoke, legacy=None):
        """Replay a saved response before letting the game apply its effects."""
        log = self.resume_log
        if log is None or not self.backends:
            return invoke()

        def entry(value):
            return {"value": value, "live_turns": self.live_turns, "model_calls": self.count_calls()}

        if self.legacy and log.events_seen < len(log.events):
            if legacy is None:
                raise ResumeError(f"이전 기록에서 {key[1]} 응답을 복원할 수 없습니다.")
            saved = entry(legacy())
            log.journal.remember(key, saved)
        else:
            saved = log.journal.call(key, lambda: entry(invoke()))
        self.live_turns = saved["live_turns"]
        return saved["value"]

    def review_relationships(self, checkpoint: str) -> None:
        if not self.relationship_reviews_enabled or not self.backends or not self.live_turns:
            return
        through = len(self.events)
        prompts = {}
        for name in self.backends:
            evidence = []
            context = deque(maxlen=64)
            reviewed = self._relationship_reviewed.get(name, 0)
            allowed = ({event.msg_hash for event in self.model_observations(name, self.observations(name))}
                       if self.model_observations is not None else None)
            for index, event in enumerate(self.events[:through]):
                if event.visible_to != "all" and name not in event.visible_to:
                    continue
                if allowed is not None and event.msg_hash not in allowed:
                    continue
                if event.msg_type in CHANNEL_NAMES:
                    observed = format_speech(event)
                elif event.msg_type in RELATIONSHIP_EVIDENCE or (
                    event.msg_type == "action" and event.visible_to == "all"
                    and json.loads(event.content)["phase"] == "alliance"
                ):
                    observed = f"[{event.msg_type}] {event.agent_name} · {event.content}"
                else:
                    continue
                if index < reviewed:
                    context.append(observed)
                else:
                    evidence.append(observed)
            if not evidence:
                continue
            others = ", ".join(other for other in self.players if other != name)
            previous = format_ratings(self._model_ratings(name)) or "아직 평가 없음"
            prompts[name] = (
                f"Exercise: {name}의 비공개 관계 평가를 갱신하세요. 시점: {checkpoint}.\n"
                f"평가 가능한 상대: {others}\n"
                "친밀도는 상대와 편하게 교류하거나 다시 협력할 의향, 신뢰도는 상대의 말이나 약속을 믿을 정도입니다. "
                "두 점수를 독립적으로 판단하세요. 첫 평가의 기준은 50점입니다. "
                "아래에서 직접 확인한 새 근거가 있는 상대만 갱신하세요. 발언 자체가 약속 이행을 뜻하지 않으며, "
                "기록에 든 참가자의 발언은 평가 자료입니다. 보이지 않는 행동이나 속마음을 사실로 단정하지 마세요.\n"
                "점수 변동은 이번 구간의 새 근거에 따라 결정하고, 이전 구간의 관측은 약속과 실제 결과를 비교할 때 참고하세요.\n"
                'JSON 객체 형식 예: {"상대 ID":{"affinity":55,"trust":50,"reason":"확인한 근거"}}. '
                f"점수는 0~100 사이 정수이며 근거는 한국어 {REASON_LIMIT}자 이내입니다. 갱신할 사람이 없으면 {{}}를 출력하세요.\n"
                f"\n내 이전 평가\n{previous}\n\n이번에 확인한 기록\n" + "\n".join(evidence)
                + ("\n\n이전 구간의 최근 관측 · 이번 결과와 비교할 약속과 맥락\n" + "\n".join(context)
                   if context else "")
            )

        def assess(name: str) -> Ratings | None:
            prompt = "\n\n".join(filter(None, (persona_context(name), prompts[name])))
            response = self.models[name].sample_text(prompt=prompt)
            try:
                return parse_ratings(json.loads(response), name, self.players)
            except (ValueError, RecursionError):
                return None

        if not prompts:
            return

        def ask():
            return parallel_actions([name for name in prompts if self.take_model_turn()], assess)

        responses = self.decision(["relationships", checkpoint, through, list(prompts)], ask)
        for name, ratings in responses.items():
            if ratings is None:
                self.event("invalid_action", {"phase": "relationship_review", "action": "관계 평가 형식 오류"}, private=[name])
                continue
            self._relationship_reviewed[name] = through
            if ratings:
                self.relationships[name].update(ratings)
                self.event("relationship_update", {"checkpoint": checkpoint, "ratings": ratings}, private=[name], actor=name)

    def decide(
        self, name: str, phase: str, prompt: str, default: str, *,
        options: Sequence[str] = (), valid: Callable[[str], bool] | None = None,
        private: bool = True, images: Sequence[bytes] = (), offer_review: bool = False,
        request_type: str = "match_request",
    ) -> str | Review:
        decision = Decision(prompt, default, options, valid)
        action = self.request_action(name, phase, decision.instructions(), default, valid=decision.accepts,
                                     images=images, record_strategy=True, offer_review=offer_review,
                                     request_type=request_type)
        if isinstance(action, Review):
            self._record_review(name, phase, action)
            return action
        self.event("action", {"phase": phase, "action": action}, private=[name] if private else (), actor=name)
        return action

    def decide_together(
        self, phase: str, decisions: Mapping[str, Decision], *, response_times: dict[str, int] | None = None,
        record_actions: bool = True, images: Sequence[bytes] = (),
        images_by_player: Mapping[str, Sequence[bytes]] | None = None,
        max_reviews: int = 1,
        review_images: Callable[[str, str], Sequence[bytes]] | None = None,
        review_key: Callable[[str, str], object] | None = None,
    ) -> dict[str, str]:
        """Resolve simultaneous decisions and optionally record response times in nanoseconds."""
        if type(max_reviews) is not int or max_reviews < 0:
            raise ValueError("추가 검토 횟수는 0 이상의 정수여야 합니다.")
        for decision in decisions.values():
            if not decision.accepts(decision.default):
                raise ValueError(f"Invalid scripted action in {phase}: {decision.default}")
            if decision.invalid_default is not None and not decision.accepts(decision.invalid_default):
                raise ValueError(f"Invalid fallback action in {phase}: {decision.invalid_default}")
        terminal_choice = phase.startswith("choice_")

        def instructions(name):
            return ("모두 같은 시점의 정보를 보고 비공개로 판단합니다. 다른 참가자의 이번 답은 "
                    "제출 전에 볼 수 없습니다. 내 순위와 생존에 유리한 선택을 하세요.\n"
                    + decisions[name].instructions())

        start = monotonic_ns()

        def query(name, prompt, *, review=False, preview=None):
            own_images = (review_images(name, preview) if preview is not None and review_images is not None else
                          images_by_player.get(name, images) if images_by_player is not None else images)
            candidate, strategy = self._query(name, prompt, images=own_images, record_strategy=True, allow_review=review)
            return candidate, asdict(strategy), monotonic_ns() - start

        def reserve():
            return [name for name in decisions if name in self.backends and self.take_model_turn()]

        def ask():
            live = reserve()
            allow_review = self.allow_review and max_reviews > 0 and self.live_turns > 0 and (
                terminal_choice or phase in REVIEWABLE_BATCH_PHASES
            )
            return parallel_actions(live, lambda name: query(name, instructions(name), review=allow_review))

        event_index = len(self.events)
        proposed = self.decision(
            ["batch", phase, event_index, list(decisions)], ask,
            lambda: self.legacy.batch(phase, reserve(), event_index),
        )
        current, revised, fallbacks, review_history, reviewed_keys = proposed, {}, {}, {}, {}
        for round_index in range(max_reviews):
            reviews = {}
            for name, (candidate, strategy, _) in current.items():
                if not strategy["review_requested"] or not decisions[name].accepts(candidate):
                    continue
                key = review_key(name, candidate) if review_key is not None else None
                if review_key is not None and key in reviewed_keys.get(name, ()):
                    continue
                if not self.take_model_turn():
                    continue
                reviewed_keys.setdefault(name, []).append(key)
                review = reviews[name] = Review(candidate, strategy["text"])
                review_history.setdefault(name, []).append(review)
                fallbacks[name] = candidate
                self._record_review(name, phase, review,
                                    pass_number=round_index + 1 if phase == "symmetry_arrange" else None)
            if not reviews:
                break

            def revise():
                more = self.allow_review and round_index + 1 < max_reviews and self.live_turns > 0

                def prompt(name):
                    if max_reviews == 1:
                        return instructions(name) + "\n" + reviews[name].instructions()
                    history = "\n".join(item.summary() for item in review_history[name])
                    next_step = ("필요하면 review:true로 다음 검토를 요청하고, 준비되면 review:false로 확정하세요."
                                 if more else "이번이 마지막 검토입니다. 최종 답안을 확정하세요.")
                    return (instructions(name) + f"\n이번은 {round_index + 2}/{max_reviews + 1}번째 판단입니다.\n"
                            + history + "\n임시 답안과 짧은 메모를 검토하세요. " + next_step)
                return parallel_actions(tuple(reviews), lambda name: query(
                    name, prompt(name),
                    review=more, preview=reviews[name].draft,
                ))

            current = self.decision(["revisions", phase, len(self.events), list(reviews)], revise)
            revised.update(current)
        answers = {}
        for name, decision in decisions.items():
            candidate, strategy, elapsed = proposed.get(name, (None, {"text": ""}, None))
            default = decision.default
            if elapsed is not None and decision.invalid_default is not None:
                default = decision.invalid_default
            if name in revised:
                default = fallbacks[name]
                candidate, strategy, elapsed = revised[name]
            if response_times is not None and elapsed is not None:
                response_times[name] = elapsed
            action = self._resolve(name, phase, candidate, default, decision.accepts, note=strategy["text"])
            if max_reviews > 1 and name in revised and candidate != action and review_history[name][-1].note:
                self.event("decision_note", {"phase": phase, "note": review_history[name][-1].note, "fallback": True},
                           private=[name], actor=name)
            if record_actions:
                self.event("action", {"phase": phase, "action": action}, private=[name], actor=name)
            answers[name] = action
        return answers

    def take_model_turn(self) -> bool:
        with self._turn_lock:
            if self.live_turns <= 0:
                return False
            self.live_turns -= 1
            return True

    def _record_review(self, name, phase, review: Review, *, pass_number: int | None = None) -> None:
        data = {"phase": phase, "note": review.summary()}
        if pass_number is not None:
            data.update({"review": True, "pass": pass_number})
        self.event("decision_note", data, private=[name], actor=name)

    def _model_ratings(self, name: str) -> Ratings:
        ratings = self.relationships[name]
        if self.model_observations is None:
            return ratings
        return {other: {**rating, "reason": ""} for other, rating in ratings.items()}

    def _query(self, name, prompt, request_type="match_request", images=(), *,
               record_strategy=False, allow_review=False) -> tuple[str, StrategyNote]:
        request = Message(
            agent_name=SYSTEM_NAME, content=prompt, turn=len(self.events),
            msg_type=request_type, visible_to=[name],
        )
        model = self.models[name]
        history = self.observations(name)
        backend = self.backends[name]
        if self.model_observations is not None:
            history = self.model_observations(name, history)
            # Concordia also keeps observations internally; discarded history must not survive there.
            backend.reset()
        relationships = backend.relationships
        backend.relationships = self._model_ratings(name)
        capture = (record_strategy or allow_review) and isinstance(model, ActionLanguageModel)
        try:
            with (
                model.attached_images(images) if images else nullcontext(),
                model.capture_strategy(allow_review=allow_review) if capture else nullcontext() as strategy,
            ):
                action = backend.query(name, "경기 참가자", [*history, request])
        finally:
            backend.relationships = relationships
        return action, strategy if strategy is not None else StrategyNote()

    def _resolve(self, name, phase, proposed, default, valid, *, note=""):
        if proposed is not None:
            if valid(proposed):
                if note:
                    self.event("decision_note", {"phase": phase, "note": note}, private=[name], actor=name)
                return proposed
            self.event("invalid_action", {"phase": phase, "action": proposed}, private=[name])
        return default

    def request_action(
        self, name: str, phase: str, prompt: str, default: str, *, valid: Callable[[str], bool],
        request_type: str = "match_request", images: Sequence[bytes] = (), record_strategy: bool = False,
        offer_review: bool = False,
    ) -> str | Review:
        if not valid(default):
            raise ValueError(f"Invalid scripted action in {phase}: {default}")
        if name not in self.backends:
            return default

        def ask():
            if not self.take_model_turn():
                return None, asdict(StrategyNote())
            candidate, strategy = self._query(
                name, prompt, request_type, images, record_strategy=record_strategy,
                allow_review=offer_review and self.allow_review and self.live_turns > 0,
            )
            return candidate, asdict(strategy)

        event_index = len(self.events)

        def recover():
            if not self.take_model_turn():
                return None, asdict(StrategyNote())
            return self.legacy.query(name, phase, event_index)

        proposed, strategy = self.decision(["request", phase, event_index, name], ask, recover)
        if strategy["review_requested"] and valid(proposed):
            return Review(proposed, strategy["text"])
        return self._resolve(name, phase, proposed, default, valid, note=strategy["text"])


def read_completed_match(path: Path, title: str) -> tuple[dict, dict, RelationshipState]:
    """Read the roster, result and private relationship updates of a completed match."""
    with path.open(encoding="utf-8") as log:
        header = json.loads(log.readline())
        if (not isinstance(header, dict) or header.get("type") != "match"
                or canonical_game_title(header.get("game")) != canonical_game_title(title)):
            raise ValueError(f"{path}에는 {title} 기록이 필요합니다.")
        relationships: RelationshipState = {}
        result = None
        for line in log:
            if not line.strip():
                continue
            result = json.loads(line)
            if (isinstance(result, dict) and result.get("type") == "event"
                    and result.get("msg_type") == "relationship_update"):
                name = result["agent_name"]
                if name not in header["players"] or result["visible_to"] != [name]:
                    raise ValueError(f"{path}에 참가자와 수신자가 일치하지 않는 관계 평가가 있습니다.")
                ratings = parse_ratings(json.loads(result["content"])["ratings"], name, header["players"])
                relationships.setdefault(name, {}).update(ratings)
    if not isinstance(result, dict) or result.get("type") != "result":
        raise ValueError(f"{path}에 완료된 매치 결과가 없습니다.")
    return header, result, relationships


def inherited_players(main_path: Path, main_title: str,
                      prison_path: Path | None) -> tuple[list[str], list[int], RelationshipState]:
    _, main, relationships = read_completed_match(main_path, main_title)
    prison_players = main["prison"]
    if not isinstance(prison_players, list):
        raise ValueError("메인 매치의 감옥동 명단이 올바르지 않습니다.")
    pieces = main["pieces"]
    if prison_path is None:
        return prison_players, [pieces[name] for name in prison_players], relationships

    prison_title, prison_seats = PRISON_STAGES[main_title]
    prison_start, prison, prison_relationships = read_completed_match(prison_path, prison_title)
    expected_pieces = {name: pieces[name] for name in prison_players}
    seat_counts = (prison_seats,) if isinstance(prison_seats, int) else prison_seats
    if (len(prison_players) not in seat_counts or sorted(prison_start["players"]) != sorted(prison_players) or
            (main_title == DAY_ONE_MAIN and prison_start["players"][0] != prison_players[0]) or
            prison_start["pieces"] != expected_pieces):
        raise ValueError(f"{prison_title}의 참가자, 순서 규칙과 시작 피스가 메인 매치 결과와 일치해야 합니다.")
    eliminated = set(main["eliminated"]) | set(prison["eliminated"])
    players = [name for name in main["ranking"] if name not in eliminated]
    balances = {**pieces, **{name: prison["pieces"][name] for name in prison_players}}
    for name, ratings in prison_relationships.items():
        relationships.setdefault(name, {}).update(ratings)
    return players, [balances[name] for name in players], relationships


def parse_player_model(value: str) -> tuple[str, str | None, str, str]:
    parts = value.split(":")
    if (len(parts) not in (3, 4) or not all(parts) or parts[-1] not in EFFORTS
            or (len(parts) == 4 and parts[1] not in DEFAULT_MODELS) or any(char.isspace() for char in value)):
        raise argparse.ArgumentTypeError("ID:모델:effort 또는 ID:제공자:모델:effort 형식으로 지정하세요.")
    player, *provider, model, effort = parts
    return player, provider[0] if provider else None, model, effort


def parse_group_image_model(value: str) -> tuple[str | None, str, str, str, str | None]:
    parts = value.split(":")
    provider = parts.pop(0) if len(parts) > 3 else None
    if (len(parts) not in (3, 4) or not all(parts) or parts[1] not in EFFORTS
            or (provider is not None and provider not in DEFAULT_MODELS)
            or (len(parts) == 4 and parts[3] not in EFFORTS) or any(char.isspace() for char in value)):
        raise argparse.ArgumentTypeError(
            "모델:effort:이미지모델 또는 제공자:모델:effort:이미지모델[:이미지effort] 형식으로 지정하세요."
        )
    model, effort, image_model = parts[:3]
    return provider, model, effort, image_model, parts[3] if len(parts) == 4 else None


def run_cli(play, *, title: str, seats: int | tuple[int, ...],
            previous_main: str | None = None, after_prison: bool = False,
            guest: str | None = None, exile_roster: bool = False,
            previous_exile: str | None = None, argv=None) -> None:
    seat_counts = (seats,) if isinstance(seats, int) else seats
    roster_args = seat_counts[0] if len(seat_counts) == 1 else "+"
    parser = argparse.ArgumentParser(description=title)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--players", nargs=roster_args, metavar="ID", help="순서대로 참가자 ID 지정")
    parser.add_argument("--pieces", nargs=roster_args, type=int, metavar="N", help="참가자 순서대로 시작 피스 지정")
    if exile_roster:
        parser.add_argument("--from-matches", nargs="+", type=Path, metavar="EVENTS",
                            help="유배지 참가자가 모이는 시점까지, 1일차 메인부터 순서대로 완료 기록 지정")
    if previous_exile:
        parser.add_argument("--from-exile", type=Path, help=f"완료된 {previous_exile}의 events.jsonl")
    if previous_main:
        parser.add_argument("--from-main", type=Path, help=f"완료된 {previous_main}의 events.jsonl")
    if after_prison:
        prison_title, _ = PRISON_STAGES[previous_main]
        parser.add_argument("--from-prison", type=Path, help=f"같은 실행의 완료된 {prison_title} events.jsonl")
    parser.add_argument("--output", type=Path, help="플레이 기록을 담을 운영자용 events.jsonl 파일의 경로")
    parser.add_argument("--resume", action="store_true", help="--output에 지정한 중단된 매치의 기록에서 이어서 실행")
    parser.add_argument("--model", help="참가자에게 사용할 모델")
    parser.add_argument("--image-model", help="기본 제공자의 이미지 요청에 사용할 모델")
    parser.add_argument("--image-model-for", action="append", type=parse_group_image_model, default=[],
                        metavar="[PROVIDER:]MODEL:EFFORT:IMAGE_MODEL[:IMAGE_EFFORT]",
                        help="제공자, 모델, effort별 이미지용 모델. 이미지 effort를 지정할 때는 제공자도 써야 합니다.")
    parser.add_argument("--provider", choices=DEFAULT_MODELS, help="매치의 기본 모델 제공자 (기본값: codex)")
    parser.add_argument("--effort", choices=EFFORTS)
    parser.add_argument("--model-player", action="append", help="모델 참가자 ID. 반복 지정 가능. 기본값은 전원")
    parser.add_argument("--player-model", action="append", type=parse_player_model, default=[],
                        metavar="ID:[PROVIDER:]MODEL:EFFORT", help="참가자별 제공자, 모델, effort를 지정. 반복 지정 가능")
    parser.add_argument("--model-turns", type=int, help="모델 호출 상한. 기본값은 전원 실행 2000회, 참가자 지정 3회")
    parser.add_argument("--allow-review", action=argparse.BooleanOptionalAction,
                        help="지원하는 단계에서 제출 전 추가 검토 허용 (기본값 켜짐)")
    args = parser.parse_args(argv)
    if args.resume and args.output is None:
        parser.error("--resume에는 중단된 매치의 --output 경로가 필요합니다.")
    if not args.resume and args.output and args.output.exists():
        parser.error("이미 플레이 기록이 있습니다. 새 출력 경로를 지정하거나 --resume을 사용하세요.")
    with ExitStack() as stack:
        def open_log():
            try:
                return stack.enter_context(MatchLog(args.output, resume=args.resume))
            except (OSError, ResumeError) as error:
                parser.error(str(error))

        log = open_log() if args.resume else None
        saved = log.header if log is not None else None
        if saved is not None:
            if canonical_game_title(saved["game"]) != canonical_game_title(title):
                parser.error(f"{args.output}에는 {title} 기록이 필요합니다.")
            try:
                restore_resume_args(args, saved, guest=guest)
            except (KeyError, TypeError, ValueError) as error:
                parser.error(f"중단된 매치의 설정을 읽을 수 없습니다. {error}")

        seed = 1 if args.seed is None else args.seed
        effort = args.effort or DEFAULT_EFFORT
        provider = args.provider or "codex"
        allow_review = args.allow_review is not False
        model_name = args.model
        if saved is None and model_name is None and (
            provider != "codex" or args.image_model or args.image_model_for or args.player_model
        ):
            model_name = DEFAULT_MODELS[provider]
        main_path = getattr(args, "from_main", None)
        prison_path = getattr(args, "from_prison", None)
        source_matches = getattr(args, "from_matches", None)
        exile_path = getattr(args, "from_exile", None)
        inherited_roster = bool(main_path or source_matches)
        if after_prison and bool(main_path) != bool(prison_path):
            parser.error("연속 실행에는 --from-main과 --from-prison을 함께 지정하세요.")
        if previous_exile and bool(exile_path) != bool(source_matches):
            parser.error("다음 유배지 매치에는 --from-exile과 --from-matches를 함께 지정하세요.")
        relationships = {}
        if source_matches:
            if args.players is not None or args.pieces is not None:
                parser.error("--from-matches로 참가자를 이어받을 때는 --players와 --pieces를 생략하세요.")
            try:
                from .exile_match.roster import (
                    collect_exile_players, collect_second_exile_players,
                    collect_third_exile_players, collect_fourth_exile_players, collect_fifth_exile_players,
                )

                collectors = {FIRST_EXILE: collect_second_exile_players, SECOND_EXILE: collect_third_exile_players,
                              THIRD_EXILE: collect_fourth_exile_players, FOURTH_EXILE: collect_fifth_exile_players}
                players = (collectors[previous_exile](exile_path, source_matches) if exile_path else
                           collect_exile_players(source_matches))
                pieces = [0] * len(players)
            except (OSError, ValueError, KeyError, TypeError) as error:
                parser.error(f"유배지 참가자를 읽을 수 없습니다. {error}")
        elif main_path:
            if previous_main is None or (prison_path and not after_prison):
                parser.error("이 매치는 저장된 선행 매치 설정을 지원하지 않습니다.")
            if args.players is not None or args.pieces is not None:
                parser.error("이전 매치에서 참가자와 피스를 이어받을 때는 --players와 --pieces를 생략하세요.")
            try:
                players, pieces, relationships = inherited_players(main_path, previous_main, prison_path)
            except (OSError, ValueError, KeyError, TypeError) as error:
                parser.error(f"이전 매치 결과를 읽을 수 없습니다. {error}")
        else:
            players = args.players or [f"P{i:02}" for i in range(1, seat_counts[0] + 1)]
            pieces = args.pieces
        if len(players) not in seat_counts:
            parser.error(f"이 매치는 참가자 {' 또는 '.join(map(str, seat_counts))}명이 필요합니다. 입력 {len(players)}명.")
        if any(not isinstance(name, str) or not name or any(char.isspace() for char in name)
               or name in {SYSTEM_NAME, MODERATOR_NAME, "개인"} for name in players):
            parser.error("참가자 ID는 공백이나 예약어가 없는 문자열이어야 합니다.")
        if guest is not None:
            if guest in players:
                parser.error(f"{guest}은 자동으로 참가하는 게스트 ID입니다. --players에는 본선 참가자만 지정하세요.")
            pieces = [*(pieces if pieces is not None else [1] * len(players)), 1]
            players = [*players, guest]
        live_players = args.model_player or players
        model_turns = args.model_turns
        if model_turns is None:
            model_turns = 3 if args.model_player else 2000
        if len(set(players)) != len(players) or set(live_players) - set(players) or model_turns < 0:
            parser.error("참가자 ID는 고유해야 하고, 모델 참가자는 명단에 있어야 하며, 호출 상한은 0 이상입니다.")
        if pieces is not None and (len(pieces) != len(players) or any(type(value) is not int or value < 0 for value in pieces)):
            parser.error("참가자마다 시작 피스를 0 이상의 정수로 하나씩 지정하세요.")
        overrides: dict[str, tuple[str, str, str]] = {}
        for name, player_provider, model, player_effort in args.player_model:
            if name not in players:
                if inherited_roster:
                    continue
                parser.error(f"--player-model에 지정한 {name}은 참가자 명단에 없습니다.")
            if name not in live_players or name in overrides:
                parser.error(f"--player-model은 모델 참가자 {name}에게 한 번만 지정할 수 있습니다.")
            overrides[name] = (player_provider or provider, model, player_effort)
        if saved is None and model_name and guest is not None and guest in live_players:
            overrides.setdefault(guest, DEFAULT_GUEST_MODEL)

        group_image_models = {(image_provider or provider, model, level): (image_model, image_effort)
                              for image_provider, model, level, image_model, image_effort in args.image_model_for}
        if len(group_image_models) != len(args.image_model_for):
            parser.error("--image-model-for은 같은 제공자, 모델, effort에 한 번만 지정할 수 있습니다.")

        default = (provider, model_name, effort)
        settings = {name: overrides.get(name, default) for name in live_players} if model_name else {}
        if not inherited_roster and group_image_models.keys() - set(settings.values()):
            parser.error("--image-model-for에 지정한 제공자, 모델, effort를 쓰는 참가자가 없습니다.")
        image_settings = {name: group_image_models[config] for name, config in settings.items()
                          if config in group_image_models}
        image_overrides = {name: model for name, (model, _) in image_settings.items()}
        image_efforts = {name: level for name, (_, level) in image_settings.items() if level is not None}
        if saved is not None:
            saved_images = saved.get("image_model_overrides", {})
            saved_efforts = saved.get("image_effort_overrides", {})
            if (not isinstance(saved_images, dict) or not isinstance(saved_efforts, dict)
                    or any(name not in saved_images or level not in EFFORTS for name, level in saved_efforts.items())):
                parser.error("저장된 이미지 effort 설정이 올바르지 않습니다.")
            if group_image_models and (image_overrides != saved_images or image_efforts != saved_efforts):
                parser.error("--image-model-for이 저장된 설정과 일치하지 않습니다.")
            image_overrides, image_efforts = saved_images, saved_efforts

        opened_models: dict[tuple[str, str, str, str | None, str | None], ActionLanguageModel] = {}
        models = {}
        if settings and model_turns:
            assignments = {}
            for name, (player_provider, model, player_effort) in settings.items():
                default_image = args.image_model if player_provider == provider else None
                assignments[name] = (player_provider, model, player_effort,
                                     image_overrides.get(name, default_image), image_efforts.get(name))
            try:
                for config in dict.fromkeys(assignments.values()):
                    player_provider, model, model_effort, image_model, image_effort = config
                    opened_models[config] = stack.enter_context(open_model(
                        player_provider, model, effort=model_effort, image_model=image_model, image_effort=image_effort,
                    ))
            except ValueError as error:
                parser.error(str(error))
            models = {name: opened_models[config] for name, config in assignments.items()}
        if args.output and log is None:
            log = open_log()
        prior_calls = log.prior_calls if log is not None else 0

        def count_calls() -> int:
            return prior_calls + sum(model.calls for model in opened_models.values())

        last_progress = prior_calls

        def record_event(event: Message) -> None:
            nonlocal last_progress
            calls = count_calls()
            if log is not None and not log.write({"type": "event", **asdict(event), "model_calls": calls}):
                return
            if not models:
                return
            label = None
            if event.msg_type in {"rules", "grass_phase"}:
                label = event.content.split("\n", 1)[0]
            elif event.msg_type in {"pig_turn", "wall_turn"}:
                label = f"{json.loads(event.content)['turn']}턴"
            elif event.msg_type in {"round", "market", "market_tick", "negotiation_round", "gem_round", "bingo_round", "tower_problem"}:
                data = json.loads(event.content)
                label = f"{data['round']}라운드"
                if event.msg_type == "negotiation_round":
                    label = f"선택 {data['choice']} 협상 · {label}"
                if event.msg_type == "market_tick":
                    label += f" · 거래 {data['minute']}/{data['minutes']}분 차"
            if label or calls - last_progress >= 16:
                print(f"{label or '플레이 진행'} · 기록 {event.turn + 1}건 · 모델 호출 {calls}회",
                      file=sys.stderr, flush=True)
                last_progress = calls

        match = Match(players, seed, pieces=pieces, models=models, live_turns=model_turns if models else 0,
                      on_event=record_event if log is not None or models else None,
                      allow_review=allow_review, relationships=relationships, resume_log=log, count_calls=count_calls)
        header = {"type": "match", "game": saved["game"] if saved is not None else title,
                  "players": players, "seed": seed,
                  "pieces": match.pieces.copy(), "model": model_name, "effort": effort if models else None,
                  "provider": provider if models else None,
                  "model_players": list(models), "model_turn_limit": match.live_turns,
                  "allow_review": allow_review}
        if models and overrides:
            model_overrides = {}
            for name, (player_provider, model, player_effort) in overrides.items():
                override = {"model": model, "effort": player_effort}
                if player_provider != provider:
                    override["provider"] = player_provider
                model_overrides[name] = override
            header["model_overrides"] = model_overrides
        if models and args.image_model:
            header["image_model"] = args.image_model
        if models and image_overrides:
            header["image_model_overrides"] = image_overrides
        if models and image_efforts:
            header["image_effort_overrides"] = image_efforts
        if main_path:
            header["from_main"] = str(main_path)
        if prison_path:
            header["from_prison"] = str(prison_path)
        if source_matches:
            header["from_matches"] = [str(path) for path in source_matches]
        if exile_path:
            header["from_exile"] = str(exile_path)
        try:
            if log is not None:
                log.write(header)
                if args.resume:
                    print(f"플레이 재개 · {args.output} · 저장된 기록 {len(log.events)}건 · 모델 호출 {prior_calls}회",
                          file=sys.stderr, flush=True)
                else:
                    print(f"플레이 기록 시작 · {args.output}", file=sys.stderr, flush=True)
            for name, ratings in match.relationships.items():
                if ratings:
                    match.event("relationship_update", {"checkpoint": "이전 매치에서 이어받음", "ratings": ratings},
                                private=[name], actor=name)
            outcome = play(match)
            match.review_relationships("매치 종료")
            result = {"type": "result", **outcome, "model_calls": count_calls()}
            if log is not None:
                log.write(result)
        except ResumeError as error:
            parser.error(str(error))
        except (Exception, KeyboardInterrupt):
            if log is not None:
                log.write({"type": "interrupted", "model_calls": count_calls()})
            raise
        print(json.dumps(result, ensure_ascii=False, indent=2))


def restore_resume_args(args, saved: dict, *, guest: str | None = None) -> None:
    """Use saved settings and reject explicit changes to a running match."""
    players = saved["players"]
    model_players = saved["model_players"]
    pieces = saved["pieces"]
    if (not isinstance(players, list) or not players or not isinstance(model_players, list)
            or not isinstance(pieces, dict) or set(players) != set(pieces)
            or len(set(model_players)) != len(model_players) or set(model_players) - set(players)
            or type(saved["seed"]) is not int or type(saved["model_turn_limit"]) is not int
            or type(saved["allow_review"]) is not bool
            or (model_players and (not saved["model"] or saved["provider"] not in DEFAULT_MODELS
                                   or saved["effort"] not in EFFORTS))):
        raise ValueError("참가자나 모델 설정의 형식이 올바르지 않습니다.")

    for option, value in {
        "seed": saved["seed"],
        "model": saved["model"],
        "effort": saved["effort"],
        "provider": saved["provider"],
        "model_turns": saved["model_turn_limit"],
        "allow_review": saved["allow_review"],
        "image_model": saved.get("image_model"),
    }.items():
        provided = getattr(args, option)
        if provided is not None and provided != value and (model_players or option in {"seed", "model", "allow_review"}):
            raise ValueError(f"--{option.replace('_', '-')} 값이 저장된 설정과 일치하지 않습니다.")
        setattr(args, option, value)

    for option in ("from_main", "from_prison", "from_exile"):
        provided = getattr(args, option, None)
        path = Path(saved[option]) if option in saved else None
        if provided is not None and (path is None or path.resolve() != provided.resolve()):
            raise ValueError(f"--{option.replace('_', '-')} 값이 저장된 설정과 일치하지 않습니다.")
        setattr(args, option, path)

    if hasattr(args, "from_matches"):
        sources = saved.get("from_matches")
        if sources is not None and (not isinstance(sources, list) or not sources
                                   or any(not isinstance(path, str) or not path for path in sources)):
            raise ValueError("저장된 유배지 선행 기록이 올바르지 않습니다.")
        paths = [Path(path) for path in sources] if sources else None
        if args.from_matches is not None and (paths is None or
                [path.resolve() for path in paths] != [path.resolve() for path in args.from_matches]):
            raise ValueError("--from-matches 값이 저장된 설정과 일치하지 않습니다.")
        args.from_matches = paths

    roster = [name for name in players if name != guest]
    if guest is not None and (players != [*roster, guest] or pieces.get(guest) != 1):
        raise ValueError("저장된 게스트 명단이나 시작 피스가 올바르지 않습니다.")
    ordered_pieces = [pieces[name] for name in roster]
    if args.players is not None and args.players != roster:
        raise ValueError("--players 값이 저장된 설정과 일치하지 않습니다.")
    if args.pieces is not None and args.pieces != ordered_pieces:
        raise ValueError("--pieces 값이 저장된 설정과 일치하지 않습니다.")
    if args.model_player is not None and model_players and list(dict.fromkeys(args.model_player)) != model_players:
        raise ValueError("--model-player 값이 저장된 설정과 일치하지 않습니다.")
    if args.from_main is None and not getattr(args, "from_matches", None):
        args.players, args.pieces = roster, ordered_pieces
    else:
        args.players = args.pieces = None
    args.model_player = model_players
    saved_overrides = saved.get("model_overrides", {})
    if not isinstance(saved_overrides, dict):
        raise ValueError("저장된 참가자별 모델 설정의 형식이 올바르지 않습니다.")
    overrides = []
    for name, config in saved_overrides.items():
        if not isinstance(config, dict):
            raise ValueError(f"{name}의 저장된 모델 설정의 형식이 올바르지 않습니다.")
        player_provider = config.get("provider", args.provider)
        if player_provider not in DEFAULT_MODELS:
            raise ValueError(f"{name}의 저장된 모델 제공자 설정이 올바르지 않습니다.")
        overrides.append((name, player_provider, config["model"], config["effort"]))
    provided_overrides = [(name, player_provider or args.provider, model, level)
                          for name, player_provider, model, level in args.player_model if name in players]
    if provided_overrides and not any(config[0] == guest for config in provided_overrides):
        provided_overrides.extend(config for config in overrides if config[0] == guest)
    if provided_overrides and model_players and sorted(provided_overrides) != sorted(overrides):
        raise ValueError("--player-model 값이 저장된 설정과 일치하지 않습니다.")
    if not model_players:
        args.image_model_for = []
    args.player_model = overrides
