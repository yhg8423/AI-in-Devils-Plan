"""Shared room membership, private messages, and discussion actions."""

from collections.abc import Callable, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
import json

from chatarena.message import Message, SYSTEM_NAME


CHANNEL_NAMES = {
    "public": "전체", "whisper": "귓속말", "room": "논의실",
    "room_invite": "논의실 초대", "room_invite_response": "초대 응답",
}
MAX_SPEECH_LENGTH = 300
MAX_NOTE_LENGTH = 300
ROOMS = (1, 2, 3, 4)


@dataclass(frozen=True)
class _RoomInvite:
    sender: str
    recipient: str
    room: int
    text: str


@dataclass(frozen=True)
class _DiscussionDecision:
    room: int | None = None
    messages: tuple[Message, ...] = ()
    note: str | None = None
    invite: _RoomInvite | None = None
    reply_to: int | None = None
    submission: str | None = None


def room_label(room: int) -> str:
    return f"{room}번 논의실" if room else "복도"


def speech_text(text: object) -> str:
    if not isinstance(text, str) or not 0 < len(text.strip()) <= MAX_SPEECH_LENGTH:
        raise ValueError("Invalid speech length")
    return text.strip()


def format_speech(message: Message) -> str:
    speaker = message.agent_name
    if isinstance(message.visible_to, list):
        recipients = ", ".join(name for name in message.visible_to if name != speaker)
        if recipients:
            speaker = f"{speaker} → {recipients}"
    return f"[{CHANNEL_NAMES[message.msg_type]}] {speaker} · {message.content}"


class Discussion:
    def __init__(self, players: Sequence[str], rounds: int):
        self.players = tuple(players)
        self.rounds = rounds
        self._rooms_by_player: dict[str, int] = {}
        self._room_invites: dict[int, _RoomInvite] = {}
        self._restoring = False

    @contextmanager
    def restore_history(self):
        """Reapply saved turns, including whispers accepted before the location rule."""
        self._restoring = True
        try:
            yield
        finally:
            self._restoring = False

    def clear(self) -> None:
        self._rooms_by_player.clear()
        self._room_invites.clear()

    def location(self, player: str) -> int:
        return self._rooms_by_player.get(player, 0)

    def _room_members(self, room: int, *, joining: str | None = None) -> list[str]:
        return [name for name in self.players if name == joining or self.location(name) == room]

    def request(self, player_name: str, turn: int, topic: str, *, action_index: int, notes: bool,
                progress: str | None = None) -> Message:
        location = room_label(self.location(player_name))
        offset = self.players.index(player_name) % len(ROOMS)
        room_order = ROOMS[offset:] + ROOMS[:offset]
        roster = [f"{room_label(room)} {' · '.join(self._room_members(room)) or '비어 있음'}"
                  for room in (0, *room_order)]
        current = action_index // len(self.players) + 1
        instructions = [topic, progress or f"협상 {current}/{self.rounds}라운드", f"현재 위치 {location}", *roster]
        pending = [
            f"초대 #{number} · {invite.sender} · {room_label(invite.room)} · "
            f"안건 {json.dumps(invite.text, ensure_ascii=False)}"
            for number, invite in self._room_invites.items() if invite.recipient == player_name
        ]
        if pending:
            instructions.extend(("받은 논의실 초대 (응답 대기)", *pending))
        if notes:
            instructions.append(
                "협상 행동에는 같은 JSON 객체에 note 문자열을 추가하세요. "
                f"note는 자신만 보는 {MAX_NOTE_LENGTH}자 이내의 전략 메모입니다. "
                "이번 차례까지 실제로 들은 대화와 판세를 바탕으로 현재 계획과 바꿀 조건을 짧게 갱신하세요. "
                "앞으로 필요한 내용은 이전 메모에서 이어받고, 말이나 제안만으로 선택이 확정됐다고 가정하지 마세요. "
                "발언의 text에는 상대에게 공유할 내용만 넣으세요."
            )
        return Message(
            SYSTEM_NAME, "\n".join(instructions), turn=turn,
            visible_to=[player_name], msg_type="discussion_request",
        )

    def parse(
        self, player_name: str, action: str, turn: int, *, notes: bool,
        validate_submission: Callable[[str], bool] | None = None,
    ) -> _DiscussionDecision | None:
        payload = json.loads(action)
        if not isinstance(payload, dict):
            raise ValueError("Expected a discussion action object")
        note = None
        if notes:
            note = payload.pop("note", None)
            if not isinstance(note, str) or not 0 < len(note.strip()) <= MAX_NOTE_LENGTH:
                raise ValueError("Expected a short private strategy note")
            note = note.strip()
        if payload.get("type") == "submit":
            choice = payload.get("choice")
            if (validate_submission is None or payload.keys() != {"type", "choice"}
                    or not isinstance(choice, str) or not validate_submission(choice.strip())):
                raise ValueError("Invalid negotiation submission")
            return _DiscussionDecision(note=note, submission=choice.strip())
        if payload.get("type") == "respond_invite":
            return self._respond_to_invite(player_name, payload, turn, note)

        room = None
        if "room" in payload:
            room = payload.pop("room")
            if type(room) is not int or room not in (0, *ROOMS):
                raise ValueError("Choose a room from 1 to 4, or 0 to leave")
        if payload == {"type": "pass"} or (
            room is not None and payload in ({"type": "move"}, {"type": "move_room"})
        ):
            return _DiscussionDecision(room, note=note) if room is not None or note is not None else None
        if payload.get("type") != "speak":
            raise ValueError("Expected speak, move, pass, or respond_invite")

        channel = payload.get("channel")
        expected_fields = {"type", "channel", "text"}
        if channel in ("whisper", "room_invite"):
            expected_fields.add("to")
        if payload.keys() != expected_fields:
            raise ValueError("Unexpected speech fields")
        text = speech_text(payload["text"])

        location = self.location(player_name)
        destination = location if room is None else room
        invite = None
        if channel == "public":
            recipients = "all"
        elif channel == "whisper":
            targets = [payload["to"]] if isinstance(payload["to"], str) else payload["to"]
            if (not isinstance(targets, list) or not targets
                    or any(not isinstance(target, str) or target == player_name or target not in self.players
                           for target in targets)
                    or len(set(targets)) != len(targets)):
                raise ValueError("Choose one or more distinct other players for a whisper")
            if not self._restoring and any(self.location(target) != destination for target in targets):
                raise ValueError("All whisper recipients must be in the same room or hallway as the sender")
            recipients = [player_name, *targets]
        elif channel == "room_invite":
            recipient = payload["to"]
            if not isinstance(recipient, str) or recipient == player_name or recipient not in self.players:
                raise ValueError("Invalid recipient")
            recipients = [player_name, recipient]
            if room not in ROOMS:
                raise ValueError("An invitation needs a room from 1 to 4")
            invite = _RoomInvite(player_name, recipient, room, text)
            text = f"초대 #{turn} · {room_label(room)} · {text}"
            if room == location:
                room = None
        elif channel == "room" and destination in ROOMS:
            recipients = self._room_members(destination, joining=player_name)
        else:
            raise ValueError("Invalid speech channel")
        message = Message(player_name, text, turn=turn, visible_to=recipients, msg_type=channel)
        return _DiscussionDecision(room, (message,), note, invite=invite)

    def _respond_to_invite(
        self, player_name: str, payload: dict, turn: int, note: str | None,
    ) -> _DiscussionDecision:
        invite_id = payload.get("invite_id")
        decision = payload.get("decision")
        fields = {"type", "invite_id", "decision"}
        if decision == "accept" and "text" in payload:
            fields.add("text")
        if payload.keys() != fields or type(invite_id) is not int or decision not in ("accept", "decline"):
            raise ValueError("Choose accept or decline for a pending invitation ID")
        invite = self._room_invites.get(invite_id)
        if invite is None or invite.recipient != player_name:
            raise ValueError("No pending invitation with that ID for this player")

        accepted = decision == "accept"
        label = "수락" if accepted else "거절"
        response = Message(
            player_name,
            f"초대 #{invite_id} · {room_label(invite.room)} · {label}",
            turn=turn,
            visible_to=[player_name, invite.sender],
            msg_type="room_invite_response",
        )
        messages = (response,)
        if "text" in payload:
            messages += (Message(
                player_name, speech_text(payload["text"]), turn=turn,
                visible_to=self._room_members(invite.room, joining=player_name), msg_type="room",
            ),)
        room = invite.room if accepted and invite.room != self.location(player_name) else None
        return _DiscussionDecision(room, messages, note, reply_to=invite_id)

    def record(
        self, player_name: str, action: _DiscussionDecision, turn: int,
    ) -> list[Message]:
        messages = []
        room = action.room
        if room is not None:
            if room:
                self._rooms_by_player[player_name] = room
            else:
                self._rooms_by_player.pop(player_name, None)
            messages.append(
                Message(player_name, f"{player_name} → {room_label(room)}", turn=turn, msg_type="room_move")
            )
        if action.invite is not None:
            self._room_invites[turn] = action.invite
        if action.reply_to is not None:
            del self._room_invites[action.reply_to]
        messages.extend(action.messages)
        if action.note is not None:
            messages.append(
                Message(player_name, action.note, turn=turn, visible_to=[player_name], msg_type="discussion_note")
            )
        return messages
