"""Connect Concordia players to the Either Or ChatArena environment."""

import asyncio
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
import json
import logging

from chatarena.agent import Player
from chatarena.arena import Arena, TooManyInvalidActions
from chatarena.backends import IntelligenceBackend
from chatarena.message import Message, SYSTEM_NAME
from concordia.agents import entity_agent
from concordia.associative_memory.basic_associative_memory import AssociativeMemoryBank
from concordia.components import agent as agent_components
from concordia.language_model.language_model import LanguageModel
from concordia.language_model.no_language_model import NoLanguageModel
from concordia.typing.entity import choice_action_spec, free_action_spec
import numpy as np

from ...personas import persona_context
from ...relationships import Ratings, format_ratings
from ..discussion import CHANNEL_NAMES, MAX_SPEECH_LENGTH, format_speech
from .choice_five import OPTIONS, ChoiceFive


def parallel_actions(names: Sequence[str], ask: Callable):
    if len(names) < 2:
        return {name: ask(name) for name in names}
    with ThreadPoolExecutor(max_workers=min(len(names), 16)) as workers:
        return dict(zip(names, workers.map(ask, names), strict=True))


DISCUSSION_PROMPT = (
    "자기 차례에 할 행동을 JSON 객체 하나로 출력하세요. 아래는 대화와 이동에 쓸 수 있는 행동입니다. "
    "협력하면 나와 상대가 각각 무엇을 얻고 순위에 어떤 영향이 있는지, 상대가 약속을 지킬 유인이 있는지 따져보세요. "
    "계획이나 정보를 공개하면 경쟁자도 들을 수 있습니다. 한 명과 비공개로 조율하려면 귓속말을 쓸 수 있습니다. "
    "논의실에서는 여러 참가자와 비공개로 전략을 나눌 수 있습니다. 한 번 말하면 같은 방의 모두가 듣고, "
    "각자 차례에 답하며 함께 계획을 조정할 수 있습니다. "
    "함께 조율할 이득이 있으면 논의실 초대를 보내거나, 받은 초대에 응할 수 있습니다. "
    '이동만 하려면 {"type":"move","room":null}의 null을 목적지 번호로 바꾸세요. 1~4는 논의실이고 0은 복도입니다. '
    "같은 차례에 이동하고 말하려면 speak 객체에 room을 추가하세요. 방 인원은 모두에게 보입니다. "
    '전체 발언은 {"type":"speak","channel":"public","text":"..."}를 사용하세요. '
    '귓속말은 같은 논의실 또는 복도에 있는 한 명에게 {"type":"speak","channel":"whisper","to":"참가자 ID","text":"..."}로 보냅니다. '
    "다른 장소에 있는 사람에게 귓속말을 하려면 speak에 상대의 위치를 room으로 지정해 그곳으로 이동하세요. "
    '논의실 발언은 {"type":"speak","channel":"room","text":"..."}을 사용하세요. '
    "room을 함께 지정하면 이동 직후 새 방에 있는 사람에게 바로 전달됩니다. "
    '논의실 초대는 {"type":"speak","channel":"room_invite","to":"참가자 ID","room":null,"text":"안건"}을 사용하세요. '
    "null 자리에 1~4 중 방 번호를 넣으면 그 방으로 이동하며 상대에게 비공개 초대를 보냅니다. "
    '받은 초대에 응답하려면 {"type":"respond_invite","invite_id":null,"decision":"accept"}를 사용하세요. '
    'null 자리에 받은 초대의 ID 숫자를 넣고, 거절할 때는 decision을 "decline"으로 지정하세요. '
    "수락하면 초대받은 방으로 이동합니다. 수락과 동시에 방에서 말하려면 text도 넣으세요. "
    f'발언은 {MAX_SPEECH_LENGTH}자까지 가능합니다. 패스할 때는 type을 "pass"로 지정하세요.'
)
DiscussionAction = dict[str, str | int]


class ConcordiaBackend(IntelligenceBackend):
    stateful = True
    type_name = "concordia"

    def __init__(self, player_name: str, model: LanguageModel, *, relationships: Ratings | None = None):
        super().__init__(player_name=player_name)
        self._player_name = player_name
        self._model = model
        self.relationships = relationships if relationships is not None else {}
        self.reset()

    def reset(self) -> None:
        self.memory = AssociativeMemoryBank(
            sentence_embedder=lambda _: np.ones(1), allow_duplicates=True
        )
        self._game_rules = agent_components.constant.Constant(
            state="", pre_act_label="\n진행자 안내와 내 비공개 계획"
        )
        components = {
            "Instructions": agent_components.instructions.Instructions(
                agent_name=self._player_name, pre_act_label="\nInstructions"
            ),
            "Goal": agent_components.constant.Constant(
                state=(
                    "내 승점과 최종 순위를 높이고 생존 가능성을 키우세요. "
                    "행동을 고를 때 다른 참가자와의 승점 격차와 내 순위가 어떻게 바뀔지 고려하세요. "
                    "공개된 생존 기준이 있으면 그 기준을 따르세요. "
                    "생존 기준이 아직 공개되지 않았다면 현재 순위와 승점 격차로 뒤처질 위험을 판단하세요."
                ),
                pre_act_label="\nGoal",
            ),
        }
        if not isinstance(self._model, NoLanguageModel) and (persona := persona_context(self._player_name)):
            components["Persona"] = agent_components.constant.Constant(state=persona, pre_act_label="")
        components.update({
            "Observation": agent_components.observation.ObservationToMemory(),
            agent_components.observation.DEFAULT_OBSERVATION_COMPONENT_KEY:
                agent_components.observation.LastNObservations(
                    history_length=64, pre_act_label="\n최근 사건과 참가자 발언 (오래된 순서부터)"
                ),
            "GameRules": self._game_rules,
            agent_components.memory.DEFAULT_MEMORY_COMPONENT_KEY:
                agent_components.memory.AssociativeMemory(memory_bank=self.memory),
        })
        self.entity = entity_agent.EntityAgent(
            agent_name=self._player_name,
            act_component=agent_components.concat_act_component.ConcatActComponent(
                model=self._model, component_order=list(components),
                randomize_choices=False, prefix_entity_name=False,
            ),
            context_components=components,
        )
        self._observed_messages: set[str] = set()

    def observe(self, messages: Sequence[Message]) -> None:
        for message in messages:
            # Puzzle displays are recorded for spectators. Each prompt supplies the cards or images allowed in that phase.
            if message.msg_type in {"rules", "grass_rules", "grass_plan", "discussion_note", "cube_puzzle", "poker_cards",
                                    "relationship_update"}:
                continue
            message_id = message.msg_hash
            if message_id in self._observed_messages:
                continue
            # The referee retains this feedback. It can contain cards outside the selected slots.
            memory_feedback = (message.msg_type in {"decision_note", "invalid_action"}
                               and json.loads(message.content).get("phase") == "memorize")
            if not memory_feedback:
                observation = (
                    format_speech(message)
                    if message.msg_type in CHANNEL_NAMES
                    else message.content
                )
                self.entity.observe(observation)
            self._observed_messages.add(message_id)

    def query(
        self,
        agent_name: str,
        role_desc: str,
        history_messages: list[Message],
        global_prompt: str | None = None,
        request_msg: Message | None = None,
    ) -> str:
        rules = [
            message.content for message in history_messages
            if message.agent_name == SYSTEM_NAME and message.msg_type in {"rules", "grass_rules", "preview"}
        ]
        if self.relationships:
            rules.append("내 비공개 관계 평가 · 협상이나 상대 선택에 참고하세요. 점수와 근거는 비공개로 유지하고, "
                         "현재 이해관계와 새 증거도 함께 판단하세요.\n"
                         + format_ratings(self.relationships))
        for kind, label in (
            ("grass_plan", "미리보기 직후 작성한 내 비공개 전략"),
            ("discussion_note", "가장 최근에 작성한 내 비공개 협상 전략"),
        ):
            note = next((
                message.content for message in reversed(history_messages)
                if message.msg_type == kind and message.agent_name == self._player_name
            ), None)
            if note is not None:
                rules.append(f"{label} · 판세에 따라 조정 가능\n{note}")
        scores = next((
            json.loads(message.content) for message in reversed(history_messages)
            if message.agent_name == SYSTEM_NAME and message.msg_type == "scoreboard"
        ), {})
        if self._player_name in scores:
            score = scores[self._player_name]
            rank = 1 + sum(other_score > score for other_score in scores.values())
            tied = sum(other_score == score for other_score in scores.values()) > 1
            rank_label = f"공동 {rank}위" if tied else f"{rank}위"
            ordered = sorted(scores.items(), key=lambda entry: (-entry[1], entry[0]))
            rules.insert(0, (
                f"내 누적 승점 {score:+d}점 · 내 현재 순위 {rank_label} / {len(scores)}명\n"
                "공개 누적 승점 (높은 순) " + " · ".join(f"{name} {points:+d}" for name, points in ordered)
            ))
        self._game_rules.set_state({"state": "\n\n".join(rules)})
        request = history_messages[-1]
        if request.msg_type in {"grass_request", "match_request"}:
            self.observe(history_messages[:-1])
            return self.entity.act(free_action_spec(call_to_action=request.content))
        if request.msg_type == "discussion_request":
            self.observe(history_messages[:-1])
            return self.entity.act(free_action_spec(call_to_action=f"{DISCUSSION_PROMPT}\n{request.content}"))
        self.observe(history_messages)
        if request.msg_type != "choice_request":
            return self.entity.act(free_action_spec(call_to_action=DISCUSSION_PROMPT))
        return self.entity.act(
            choice_action_spec(
                call_to_action=(
                    "다섯 번째 선택에서 무엇을 고르겠습니까? 확정 승점 5점이 순위에 주는 이득과, "
                    "타일을 고르기 전에 선택 6~8의 자세한 규칙을 알아 타일·배치·협상 계획을 세울 이득을 비교하세요. "
                    "정보를 직접 갖는 가치와 다른 참가자가 정보를 공유할 가능성도 고려하세요."
                ),
                options=OPTIONS,
            )
        )

    async def async_query(self, *args, **kwargs) -> str:
        return await asyncio.to_thread(self.query, *args, **kwargs)


class ScriptedLanguageModel(NoLanguageModel):
    def __init__(
        self,
        choice: str | Callable[[str], str],
        speech: DiscussionAction | Callable[[str], DiscussionAction] | None = None,
    ):
        if isinstance(choice, str) and choice not in OPTIONS:
            raise ValueError(f"Invalid scripted choice {choice!r}")
        self._choice = choice
        self._speech = speech

    def sample_text(self, prompt: str, **kwargs) -> str:
        if f"Exercise: {DISCUSSION_PROMPT}" not in prompt:
            return ""
        speech = self._speech(prompt) if callable(self._speech) else self._speech
        return json.dumps(speech or {"type": "pass"}, ensure_ascii=False)

    def sample_choice(
        self, prompt: str, responses: Sequence[str], *, seed: int | None = None
    ) -> tuple[int, str, Mapping[str, object]]:
        # Concordia labels its options with letters and keeps their configured order.
        choice = self._choice(prompt) if callable(self._choice) else self._choice
        index = OPTIONS.index(choice)
        return index, responses[index], {}


def make_arena(
    initial_scores: Mapping[str, int],
    choices: Mapping[str, str | LanguageModel],
    *,
    discussion_rounds: int = 0,
) -> Arena:
    environment = ChoiceFive(initial_scores, discussion_rounds=discussion_rounds)
    if choices.keys() != initial_scores.keys():
        raise ValueError("Provide a model or a scripted choice for each player")
    players = []
    for name in environment.player_names:
        model = choices[name]
        if isinstance(model, str):
            model = ScriptedLanguageModel(model)
        players.append(
            Player(
                name=name,
                role_desc="양자택일 참가자",
                backend=ConcordiaBackend(name, model),
            )
        )
    return Arena(players, environment)


def ask_action(arena: Arena, name: str, *, simultaneous: bool = False) -> tuple[str, str]:
    environment = arena.environment
    player = arena.name_to_player[name]
    observation = environment.get_observation(name)
    for _ in range(arena.invalid_actions_retry):
        action = player(observation)
        if environment.check_action(action, name, simultaneous=simultaneous):
            return action, getattr(player.backend, "last_decision_note", "")
        logging.warning("%s made an invalid action %s", name, action)
    raise TooManyInvalidActions(f"{name} has made invalid actions for {arena.invalid_actions_retry} times")


def gather_arena_actions(arena: Arena, names: Sequence[str], *, simultaneous: bool) -> dict[str, tuple[str, str]]:
    return parallel_actions(names, lambda name: ask_action(arena, name, simultaneous=simultaneous))


def play_arena(
    arena: Arena, *, after_step: Callable[[], None] | None = None,
    gather_actions: Callable = gather_arena_actions,
) -> None:
    environment = arena.environment
    steps = 0
    while steps < environment.max_steps:
        simultaneous = environment.simultaneous_players()
        names = simultaneous or (environment.get_next_player(),)
        actions = gather_actions(arena, names, simultaneous=bool(simultaneous))
        for name, (action, note) in actions.items():
            timestep = environment.step(name, action, note=note)
            if after_step is not None:
                after_step()
        steps += len(actions)
        if timestep.terminal:
            break
    for player in arena.players:
        player.backend.observe(arena.environment.get_observation(player.name))


play_choice_five = play_arena
