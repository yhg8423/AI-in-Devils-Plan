"""Recover early Either/Or decisions from logs written before decision journaling."""

from collections.abc import Sequence
import json

from .resume import ResumeError


_ROOM_NUMBERS = {"복도": 0, **{f"{room}번 논의실": room for room in range(1, 5)}}


def _strategy(text="", *, review=False):
    return {"text": text, "allow_review": review, "review_requested": review}


def _payload(event, phase, kind, name=None):
    if event is None or event["msg_type"] != kind:
        return None
    if name is not None:
        if kind == "invalid_action":
            if event["visible_to"] != [name]:
                return None
        elif event["agent_name"] != name:
            return None
    data = json.loads(event["content"])
    return data if data.get("phase") == phase else None


class LegacyDecisions:
    def __init__(self, events: Sequence[dict]):
        self.events = events

    def _event(self, index):
        return self.events[index] if index < len(self.events) else None

    def _missing(self, phase, index):
        return ResumeError(f"기존 기록의 {index + 1}번째 이벤트({phase})에서 모델 응답을 복원할 수 없습니다.")

    def _action(self, name, phase, index, *, review=False):
        current = self._event(index)
        if invalid := _payload(current, phase, "invalid_action", name):
            return [invalid["action"], _strategy()], index + 1
        note = _payload(current, phase, "decision_note", name)
        if note:
            current = self._event(index + 1)
        if action := _payload(current, phase, "action", name):
            return [action["action"], _strategy(note["note"] if note else "")], index + 1 + bool(note)
        if note and review and note["note"].startswith("추가 검토 · 임시 답안 "):
            draft, _, text = note["note"].removeprefix("추가 검토 · 임시 답안 ").partition(" · ")
            if draft.isascii() and draft.isdecimal():
                return [draft, _strategy(text, review=True)], index + 1
        raise self._missing(phase, index)

    def _discussion(self, name, phase, index):
        action = {"type": "pass"}
        for i in range(index, len(self.events)):
            event = self.events[i]
            if invalid := _payload(event, phase, "invalid_action", name):
                return invalid["action"]
            if event["agent_name"] != name:
                break
            kind, content = event["msg_type"], event["content"]
            if kind == "discussion_note":
                submission = _payload(self._event(i + 1), "choice_2", "action", name)
                if submission is not None:
                    action = {"type": "submit", "choice": submission["action"]}
                return json.dumps({**action, "note": content}, ensure_ascii=False, separators=(",", ":"))
            if kind == "room_move":
                action = {"type": "move", "room": _ROOM_NUMBERS[content.split(" → ", 1)[1]]}
            elif kind == "room_invite":
                _, room, text = content.split(" · ", 2)
                recipient = next(player for player in event["visible_to"] if player != name)
                action = {"type": "speak", "channel": kind, "room": _ROOM_NUMBERS[room], "to": recipient, "text": text}
            elif kind == "room_invite_response":
                invite, _, response = content.split(" · ", 2)
                action = {"type": "respond_invite", "invite_id": int(invite.removeprefix("초대 #")),
                          "decision": {"수락": "accept", "거절": "decline"}[response]}
            elif kind == "room" and action["type"] == "respond_invite":
                action["text"] = content
            elif kind in ("public", "room", "whisper"):
                action.update(type="speak", channel=kind, text=content)
                if kind == "whisper":
                    action["to"] = next(player for player in event["visible_to"] if player != name)
            else:
                break
        raise self._missing(phase, index)

    def query(self, name, phase, event_index, *, batch=False):
        if event_index == len(self.events):
            return None
        if phase == "cubes" and not batch:
            return self._action(name, phase, event_index, review=True)[0]
        if phase == "choice_2_negotiation" and not batch:
            return [self._discussion(name, phase, event_index), _strategy()]
        raise self._missing(phase, event_index)

    def batch(self, phase, names, event_index):
        if event_index == len(self.events):
            return None
        if phase not in ("choice_1", "choice_2") or event_index > len(self.events):
            raise self._missing(phase, event_index)
        pending = set(names)
        resolved = {}
        index = event_index
        while pending:
            current = self._event(index)
            if current is None:
                raise self._missing(phase, index)
            kind = current["msg_type"]
            name = current["visible_to"][0] if kind == "invalid_action" else current["agent_name"]
            decision, index = self._action(name, phase, index)
            if name in pending:
                resolved[name] = [*decision, None]
                pending.remove(name)
            if kind == "invalid_action":
                if not _payload(self._event(index), phase, "action", name):
                    raise self._missing(phase, index)
                index += 1
        return resolved
