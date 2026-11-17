"""Play a full Lay the Grass match with a live model."""

import argparse
from collections import Counter
from collections.abc import Callable
from contextlib import ExitStack, nullcontext
from dataclasses import asdict, replace
from heapq import nlargest
import json
from pathlib import Path
from threading import Lock

from chatarena.agent import Player
from chatarena.arena import Arena
from chatarena.message import Message

from ...models import ActionLanguageModel, DEFAULT_EFFORT, DEFAULT_MODELS, InvalidModelChoice, Review, open_model
from ...models import CodexLanguageModel as CodexLanguageModel
from ...relationships import Ratings

from .choice_five import CHANNEL_NAMES
from .demo import DEMO_DISCUSSION_ROUNDS, make_grass_game, placement_rank
from .environment import LayTheGrass
from .simulation import ConcordiaBackend, ask_action, parallel_actions


class LiveGrassBackend(ConcordiaBackend):
    def __init__(self, name: str, model: ActionLanguageModel, game: LayTheGrass, *,
                 allow_review: bool = True, reserve_review: Callable[[], bool] | None = None,
                 relationships: Ratings | None = None):
        self.game = game
        self.allow_review = allow_review
        self.reserve_review = reserve_review
        super().__init__(name, model, relationships=relationships)

    def reset(self) -> None:
        super().reset()
        self.invalid_action = None
        self.last_decision_note = ""

    def query(self, agent_name, role_desc, history_messages, global_prompt=None, request_msg=None):
        request = history_messages[-1]
        placement_choices = {}
        if self.game.phase in {"manhole", "tree"}:
            available = sorted(self.game.park - self.game.manholes.keys() - self.game.trees)
            if self.game.phase == "tree":
                cells = "\n".join(json.dumps(cell, separators=(",", ":")) for cell in available)
                hint = f"다음 후보 중 한 줄을 골라 그대로 출력하세요.\n{cells}"
            else:
                cells = json.dumps(available, separators=(",", ":"))
                hint = f"사용 가능한 빈 칸 좌표 {cells}"
            request = replace(request, content=f"{request.content}\n{hint}")
        if self.game.phase == "place":
            candidates = nlargest(12, self.game.legal_placements(agent_name),
                                  key=lambda move: placement_rank(self.game, agent_name, move))
            placement_choices = {
                str(index): json.dumps(asdict(placement))
                for index, (placement, _) in enumerate(candidates, start=1)
            }
            options = "\n".join(f"후보 {index} {action}" for index, action in placement_choices.items())
            hint = (
                "아래의 검증된 후보를 고르려면 후보 번호 하나만 출력하세요. "
                "직접 배치하려면 앞의 JSON 형식을 사용하세요.\n" + options
            )
            if not candidates:
                hint = "현재 가능한 배치가 없습니다. 실패를 출력하세요."
            request = replace(request, content=f"{request.content}\n{hint}")
        if self.invalid_action is not None:
            request = replace(request, content=(
                f"{request.content}\n직전 제출은 규칙 또는 출력 형식에 맞지 않았습니다. "
                f"다른 유효한 행동을 제출하세요. 직전 제출 {self.invalid_action}"
            ))
        terminal_choice = request.msg_type == "choice_request" or self.game.phase in {"stance", "partner", "obstacle"}
        record_note = terminal_choice or (request.msg_type == "grass_request" and self.game.phase != "plan")
        capture = record_note and isinstance(self._model, ActionLanguageModel)
        with self._model.capture_strategy(allow_review=terminal_choice and self.allow_review) if capture else nullcontext() as strategy:
            action = super().query(agent_name, role_desc, [*history_messages[:-1], request],
                                   global_prompt, request_msg)
        action = placement_choices.get(action, action)
        simultaneous = bool(self.game.simultaneous_players())
        valid = self.game.check_action(action, agent_name, simultaneous=simultaneous)
        self.last_decision_note = strategy.text if valid and strategy is not None else ""
        if valid and strategy is not None and strategy.review_requested and (
            self.reserve_review is None or self.reserve_review()
        ):
            review = Review(action, strategy.text)
            draft = Message(agent_name, review.instructions(), turn=request.turn,
                            msg_type="review_draft", visible_to=[agent_name])
            try:
                with self._model.capture_strategy() as final_strategy:
                    revised = super().query(agent_name, role_desc, [*history_messages[:-1], draft, request],
                                            global_prompt, request_msg)
            except InvalidModelChoice:
                revised = None
            if revised is not None and self.game.check_action(revised, agent_name, simultaneous=simultaneous):
                action = revised
                final_note = final_strategy.text
            else:
                final_note = ""
            self.last_decision_note = " · ".join(
                part for part in (review.summary(), f"최종 답안 {action}", final_note) if part
            )
        self.invalid_action = None if valid else action
        return action


def transcript(path: Path, rows: list[dict]) -> None:
    title = f"# 잔디 깔기 협상 기록 · {rows[0]['model']}"
    lines = [title, "", "비공개 발언, 초대, 응답의 화살표는 당시 수신자를 표시한다."]
    section = None
    for row in rows:
        phase = row.get("phase")
        if phase not in ("before_choice", "talk"):
            continue
        key = (phase, row["round"])
        for event in row["events"]:
            channel = event["msg_type"]
            if channel not in CHANNEL_NAMES and channel != "room_move":
                continue
            if section != key:
                label = "선택 5 전" if phase == "before_choice" else "미리보기 후"
                lines.extend(("", f"## {label} · {row['round']}라운드", ""))
                section = key
            content = " ".join(event["content"].splitlines())
            if channel == "room_move":
                lines.append(f"- [이동] {content}")
            else:
                speaker = event["agent_name"]
                if isinstance(event["visible_to"], list):
                    recipients = ", ".join(name for name in event["visible_to"] if name != speaker)
                    if recipients:
                        speaker = f"{speaker} → {recipients}"
                lines.append(f"- [{CHANNEL_NAMES[channel]}] **{speaker}** · {content}")
    result = rows[-1]
    if result.get("type") == "result":
        lines.extend(("", "## 최종 승점", ""))
        for name, score in sorted(result["scores"].items(), key=lambda pair: -pair[1]):
            lines.append(f"- {name} {score:+d}점")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(arena: Arena, model: ActionLanguageModel, model_name: str, output: Path, *,
        allow_review: bool | None = None) -> None:
    game = arena.environment
    output.mkdir(parents=True, exist_ok=True)
    log = output / "events.jsonl"
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
    counts: Counter[str] = Counter()
    header = {
        "type": "match", "model": model_name, "initial_scores": game.scores, "priority": game.priority,
        "discussion_rounds": DEMO_DISCUSSION_ROUNDS,
        "events": [asdict(event) for event in game.match_events()],
    }
    if rows:
        saved_provider = rows[0].get("provider", "codex")
        if saved_provider != model.provider:
            raise ValueError(f"이 경기는 --provider {saved_provider}로 이어가세요. 새 경기는 다른 --output을 지정하세요.")
        saved_effort = rows[0].get("effort", DEFAULT_EFFORT)
        if saved_effort != model.effort:
            raise ValueError(f"이 경기는 --effort {saved_effort}로 이어가세요. 새 경기는 다른 --output을 지정하세요.")
        saved_review = rows[0].get("allow_review", False)
        if allow_review is not None and allow_review != saved_review:
            raise ValueError("잔디 깔기를 이어갈 때는 처음과 동일한 검토 설정을 사용하세요.")
        allow_review = saved_review
        if any(rows[0][key] != value for key, value in header.items() if key != "events"):
            raise ValueError("The existing match log has different settings")
        game.preview_planning = rows[0].get("preview_planning", False)
        game.discussion_notes = rows[0].get("discussion_notes", False)
    if allow_review is None:
        allow_review = True
    for player in arena.players:
        player.backend.allow_review = allow_review
    header["effort"] = model.effort
    header["provider"] = model.provider
    header["preview_planning"] = game.preview_planning
    header["discussion_notes"] = game.discussion_notes
    header["allow_review"] = allow_review
    with game.discussion.restore_history():
        for row in rows[1:]:
            if row["type"] == "step":
                name = row["player"]
                observations = game.get_observation(name)
                if observations[-1].msg_type in {"grass_request", "discussion_request"}:
                    observations = observations[:-1]
                arena.name_to_player[name].backend.observe(observations)
                note = next((json.loads(event["content"])["note"] for event in row["events"]
                             if event["msg_type"] == "decision_note"), "")
                game.step(name, row["action"], note=note)
                counts[row["phase"]] += 1
                model.calls += row["calls"]
                model.usage.update(row["usage"])
            elif row["type"] == "result":
                transcript(output / "negotiation.md", rows)
                print(f"경기 완료 · {log}", flush=True)
                return

    with (
        log.open("a", encoding="utf-8", buffering=1) as file,
        (output / "prompts.jsonl").open("a", encoding="utf-8", buffering=1) as prompt_log,
    ):
        def record(row: dict) -> None:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
            rows.append(row)

        prompt_lock = Lock()

        def record_prompt(name, step, model_input):
            row = {"step": step, "phase": phase, "player": name, "input": model_input}
            with prompt_lock:
                prompt_log.write(json.dumps(row, ensure_ascii=False) + "\n")

        def record_step(name, action, turn, start):
            counts[phase] += 1
            record({
                "type": "step", "phase": phase, "player": name,
                "round": (counts[phase] - 1) // game.num_players + 1,
                "action": action, "events": [asdict(event) for event in game.match_events(start)],
                "calls": turn.calls, "usage": dict(turn.usage),
            })

        if not rows:
            record(header)
        try:
            while not game.is_terminal():
                phase = game.phase or ("before_choice" if game._discussing() else "choice_five")
                players = game.simultaneous_players()
                step = sum(counts.values()) + 1
                if players:
                    step_by_name = dict(zip(players, range(step, step + len(players)), strict=True))

                    def ask(name):
                        with model.track_turn(lambda prompt: record_prompt(name, step_by_name[name], prompt)) as turn:
                            return ask_action(arena, name, simultaneous=True), turn

                    submissions = parallel_actions(players, ask)
                    for name, ((action, note), turn) in submissions.items():
                        start = len(game.match_events())
                        game.step(name, action, note=note)
                        record_step(name, action, turn, start)
                else:
                    name = game.get_next_player()
                    start = len(game.match_events())
                    with model.track_turn(lambda prompt: record_prompt(name, step, prompt)) as turn:
                        action, note = ask_action(arena, name)
                    game.step(name, action, note=note)
                    record_step(name, action, turn, start)
                if counts[phase] % game.num_players == 0 or game.phase not in (None, phase):
                    transcript(output / "negotiation.md", rows)
                    print(f"{phase} {counts[phase]}턴 · 모델 호출 {model.calls}회", flush=True)
            record({"type": "result", "scores": game.scores, "placed": len(game.placed),
                    "board": game.render_board(), "calls": model.calls, "usage": dict(model.usage)})
        finally:
            transcript(output / "negotiation.md", rows)
    print(f"경기 완료 · {log}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="실제 모델로 잔디 깔기 한 판을 실행합니다.")
    parser.add_argument("--model")
    parser.add_argument("--provider", choices=DEFAULT_MODELS, default="codex", help="모델 호출 경로 (기본값: %(default)s)")
    parser.add_argument("--effort", default=DEFAULT_EFFORT, help="모델의 추론 노력 수준 (기본값: %(default)s)")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--allow-review", action=argparse.BooleanOptionalAction, default=None,
                        help="선택 5~8에서 제출 전 추가 검토 허용 (새 경기 기본값 켜짐)")
    args = parser.parse_args()
    model_name = args.model if args.model is not None else DEFAULT_MODELS[args.provider]
    with ExitStack() as stack:
        try:
            model = stack.enter_context(open_model(args.provider, model_name, effort=args.effort))
        except ValueError as error:
            parser.error(str(error))
        game = make_grass_game()
        players = [Player(name=name, role_desc="잔디 깔기 참가자", backend=LiveGrassBackend(name, model, game))
                   for name in game.player_names]
        run(Arena(players, game), model, model_name, args.output, allow_review=args.allow_review)


if __name__ == "__main__":
    main()
