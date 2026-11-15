"""Rules, turns, and observations for Either Or's fifth choice."""

from collections.abc import Mapping
import json

from chatarena.environments import Environment, TimeStep
from chatarena.message import Message, SYSTEM_NAME

from ..discussion import (
    CHANNEL_NAMES, MAX_NOTE_LENGTH, MAX_SPEECH_LENGTH, ROOMS, Discussion, _DiscussionDecision, format_speech, room_label,
)


PLAYER_COUNT = 16
SCORE = "점수"
INFORMATION = "정보"
OPTIONS = (SCORE, INFORMATION)
POINTS_AWARDED = 5
STANCE_RULES = (
    "공격은 타일을 그대로 씁니다. 배치 성공 시 기본 승점이 타일 번호의 두 배가 되고, 실패 시 승점 4점을 잃습니다.\n"
    "방어는 타일을 그대로 쓰거나 최대 두 칸까지 자를 수 있습니다. 두 칸을 자를 때는 변이 맞닿아야 합니다. "
    "번호가 적힌 칸은 자를 수 없고, 타일이 분리되거나 내부에 새 구멍이 생기면 안 됩니다. "
    "방어의 기본 배치 승점은 성공 시 타일 번호, 실패 시 0점입니다."
)
PARTNER_RULES = (
    "상생은 2인 팀으로 플레이합니다. 두 타일을 모두 배치하면 맞닿은 변 하나당 팀 추가 승점 1점을 얻어 합의해 나눕니다. "
    "시뮬레이션에서는 두 참가자가 서로 지목하면 팀이 됩니다. 각자 제출한 배분의 합이 팀 추가 승점과 일치하면 지급합니다.\n"
    "견제는 본인이 타일 배치에 성공하고, 본인을 포함해 성공한 참가자가 총 9명 이하일 때 승점 5점을 더 받습니다."
)
OBSTACLE_RULES = (
    "가로수는 하나를 설치합니다. 가로수 칸에 타일을 겹치려면 해당 타일 칸이 구멍이어야 합니다.\n"
    "맨홀은 +1과 -1을 하나씩 설치합니다. 잔디 타일이 맨홀을 덮으면 +1마다 승점 1점을 더하고 -1마다 1점을 뺍니다.\n"
    "맨홀, 가로수, 잔디 타일 순으로 설치하고 배치합니다. 장애물은 공원 안 빈 칸에 놓으므로 맨홀과 가로수는 겹칠 수 없습니다. "
    "시뮬레이션에서는 각 장애물 설치 단계에서도 타일 배치 순서를 따릅니다."
)
PREVIEW = "\n\n".join((
    "선택 6~8 미리보기",
    f"선택 6 · 공격 / 방어\n{STANCE_RULES}",
    f"선택 7 · 상생 / 견제\n{PARTNER_RULES}",
    f"선택 8 · 가로수 / 맨홀\n{OBSTACLE_RULES}",
))
CHOICE_REQUEST = (
    "선택 5 · 점수 / 정보\n"
    f"‘점수’를 고르면 승점 {POINTS_AWARDED}점을 받습니다. "
    "‘정보’를 고르면 타일을 고르기 전에 선택 6~8의 선택지와 세부 규칙을 비공개로 미리 확인합니다."
)
BEFORE_CHOICE_DISCUSSION = (
    f"지금은 선택 5 제출 전 협상입니다.\n{CHOICE_REQUEST}\n"
    "이 협상 다음에 각자 점수 또는 정보를 제출합니다."
)


class ChoiceFive(Environment):
    discussion_notes = False

    def __init__(
        self,
        initial_scores: Mapping[str, int],
        *,
        discussion_rounds: int = 0,
    ):
        if len(initial_scores) != PLAYER_COUNT:
            raise ValueError(f"Choice 5 requires {PLAYER_COUNT} players")
        if discussion_rounds < 0:
            raise ValueError("Discussion rounds cannot be negative")
        super().__init__(player_names=list(initial_scores))
        self._initial_scores = dict(initial_scores)
        self._discussion_turn_limit = discussion_rounds * self.num_players
        self._choice_turn = self._discussion_turn_limit + 2 if discussion_rounds else 1

    @property
    def max_steps(self) -> int:
        return self._discussion_turn_limit + self.num_players

    @property
    def scores(self) -> dict[str, int]:
        return self._scores.copy()

    def match_events(self, start: int = 0) -> tuple[Message, ...]:
        """Return the referee's event log, including private messages."""
        return tuple(self._messages[start:])

    def reset(self) -> TimeStep:
        self._scores = self._initial_scores.copy()
        self._discussion_turn = 0
        self.discussion = Discussion(self.player_names, self._discussion_turn_limit // self.num_players)
        self._submissions: dict[str, str] = {}
        self._messages = [self._scoreboard(turn=0)]
        if self._discussing():
            self._messages.append(
                Message(
                    SYSTEM_NAME, BEFORE_CHOICE_DISCUSSION, turn=1, msg_type="discussion"
                )
            )
        else:
            self._open_choice()
        return TimeStep(self.get_observation(), self.get_zero_rewards(), terminal=False)

    def _discussing(self) -> bool:
        return self._discussion_turn < self._discussion_turn_limit

    def _open_choice(self) -> None:
        self.discussion.clear()
        self._messages.append(
            Message(
                SYSTEM_NAME,
                CHOICE_REQUEST,
                turn=self._choice_turn,
                msg_type="choice_request",
            )
        )

    def _scoreboard(self, turn: int) -> Message:
        return Message(
            SYSTEM_NAME,
            json.dumps(self._scores, sort_keys=True, ensure_ascii=False),
            turn=turn,
            msg_type="scoreboard",
        )

    def get_next_player(self) -> str:
        if self.is_terminal():
            raise RuntimeError("Choice 5 has already been resolved")
        if self._discussing():
            return self.player_names[self._discussion_turn % self.num_players]
        return self.player_names[len(self._submissions)]

    def simultaneous_players(self) -> tuple[str, ...]:
        if self._discussing() or self.is_terminal():
            return ()
        return tuple(self.player_names[len(self._submissions):])

    def get_observation(self, player_name: str | None = None) -> list[Message]:
        messages = [
            message
            for message in self._messages
            if message.visible_to == "all"
            or (isinstance(message.visible_to, list) and player_name in message.visible_to)
        ]
        if player_name is not None and self._discussing() and player_name == self.get_next_player():
            messages.append(self.discussion.request(
                player_name, self._discussion_turn + 2, BEFORE_CHOICE_DISCUSSION,
                action_index=self._discussion_turn, notes=self.discussion_notes,
            ))
        return messages

    def _validate_action(self, action: str, player_name: str, *, simultaneous=False) -> _DiscussionDecision | None:
        if self.is_terminal() or (
            player_name not in self.simultaneous_players() if simultaneous else player_name != self.get_next_player()
        ):
            raise ValueError(f"Cannot submit a Choice 5 action for {player_name} now")
        if self._discussing():
            return self.discussion.parse(player_name, action, self._discussion_turn + 2, notes=self.discussion_notes)
        if action not in OPTIONS:
            raise ValueError(f"Invalid Choice 5 selection from {player_name}")
        return None

    def check_action(self, action: str, player_name: str, *, simultaneous=False) -> bool:
        try:
            self._validate_action(action, player_name, simultaneous=simultaneous)
        except (ValueError, RecursionError):
            return False
        return True

    def _record_decision_note(self, player_name: str, phase: str, note: str, turn: int) -> None:
        self._messages.append(Message(
            player_name, json.dumps({"phase": phase, "note": note}, ensure_ascii=False),
            turn=turn, visible_to=[player_name], msg_type="decision_note",
        ))

    def step(self, player_name: str, action: str, *, note: str = "") -> TimeStep:
        decision = self._validate_action(action, player_name)
        if self._discussing():
            if decision is not None:
                self._messages.extend(self.discussion.record(player_name, decision, self._discussion_turn + 2))
            self._discussion_turn += 1
            if not self._discussing():
                self._open_choice()
            return TimeStep(self.get_observation(), self.get_zero_rewards(), terminal=False)

        if note:
            self._record_decision_note(player_name, "choice_five", note, self._choice_turn)
        self._submissions[player_name] = action
        if not self.is_terminal():
            return TimeStep(self.get_observation(), self.get_zero_rewards(), terminal=False)

        rewards = {
            name: POINTS_AWARDED if choice == SCORE else 0
            for name, choice in self._submissions.items()
        }
        for name, reward in rewards.items():
            self._scores[name] += reward
        if any(rewards.values()):
            self._messages.append(self._scoreboard(turn=self._choice_turn + 1))
        self._messages.extend(
            Message(
                SYSTEM_NAME,
                PREVIEW,
                turn=self._choice_turn + 2,
                visible_to=[name],
                msg_type="preview",
            )
            for name, choice in self._submissions.items()
            if choice == INFORMATION
        )
        return TimeStep(self.get_observation(), rewards, terminal=True)

    def is_terminal(self) -> bool:
        return len(self._submissions) == self.num_players

    def print(self) -> None:
        for message in self.get_observation():
            print(message.content)
