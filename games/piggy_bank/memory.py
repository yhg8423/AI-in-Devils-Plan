"""A private three-bank memory, separate from the complete operator log."""

import json

from chatarena.message import Message, SYSTEM_NAME


MEMORY_HEADING = "\n\n5. 기억 슬롯\n"
MEMORY_CAPACITY = 3
_BOUNDARIES = {"pig_setup", "pig_turn", "pig_reset"}
_CURRENT_EVENTS = {
    *_BOUNDARIES, "pig_preparation", "pig_preparation_end", "pig_discussion", "pig_discussion_end",
    "pig_deposit", "pig_claim", "pig_doubt", "pig_replace", "pig_pass", "pig_reset_vote", "pig_challenge",
    "public", "whisper",
}


def parse_memory_selection(action, bank_ids):
    banks = json.loads(action)
    if (not isinstance(banks, list) or len(banks) != MEMORY_CAPACITY
            or any(type(bank) is not int or bank not in bank_ids for bank in banks)
            or len(set(banks)) != MEMORY_CAPACITY):
        raise ValueError("현재 저금통 중 서로 다른 세 번호를 JSON 배열로 선택하세요.")
    return sorted(banks)


class PiggyMemory:
    def __init__(self, players, banks):
        self.players = tuple(players)
        self.banks = banks
        self.selections = {name: [] for name in players}
        self.epoch = 0

    def select(self, name, banks):
        self.selections[name] = parse_memory_selection(json.dumps(banks), self.banks)

    def replace(self, old_bank, new_bank):
        changed = []
        for name, selected in self.selections.items():
            if old_bank in selected:
                self.selections[name] = [new_bank if bank == old_bank else bank for bank in selected]
                changed.append(name)
        return changed

    def reset(self, epoch):
        self.epoch = epoch
        self.selections = {name: [] for name in self.players}

    def recall(self, name):
        return {"reset": self.epoch, "banks": {
            str(bank): self.banks[bank].copy() for bank in self.selections[name] if bank in self.banks
        }}

    def __call__(self, name, history):
        """Keep this turn's observations and three exact memories, never the old transcript."""
        visible = [event for event in history if event.visible_to == "all" or name in event.visible_to]
        boundary = 0
        first_turn = len(visible)
        rules = plan = None
        state = {"reset": self.epoch, "banks": sorted(self.banks), "voters": []}
        for index, event in enumerate(visible):
            kind = event.msg_type
            if kind == "rules" and event.agent_name == SYSTEM_NAME:
                rules = event
            if kind == "pig_turn":
                first_turn = min(first_turn, index)
            if kind == "discussion_note" and event.agent_name == name and index < first_turn:
                plan = event
            if event.visible_to != "all" or not kind.startswith("pig_"):
                continue
            if kind in _BOUNDARIES:
                boundary = index
            if kind not in _CURRENT_EVENTS:
                continue
            data = json.loads(event.content)
            for key in ("lower", "upper", "scores", "turn", "color", "next_player"):
                if key in data:
                    state[key] = data[key]
            if kind in {"pig_setup", "pig_reset"}:
                state["voters"] = []
            if kind == "pig_turn":
                state["next_player"] = data["player"]
            elif kind in {"pig_claim", "pig_pass"}:
                state["next_player"] = data["player"]
            elif kind == "pig_reset_vote":
                state["voters"] = data["voters"]

        turn = visible[-1].turn if visible else 0
        encode = lambda value: json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        projected = [rules] if rules is not None else []
        if plan is not None:
            projected.append(plan)
        projected.append(Message(SYSTEM_NAME, encode(state), turn=turn, msg_type="pig_state"))
        projected.extend(event for event in visible[boundary:] if event.msg_type in _CURRENT_EVENTS)
        projected.append(Message(name, encode(self.recall(name)), turn=turn,
                                 msg_type="pig_recall", visible_to=[name]))
        # Requests are normally appended after projection; accept that form for direct callers too.
        if visible and visible[-1].msg_type.endswith("_request"):
            projected.append(visible[-1])
        return projected
