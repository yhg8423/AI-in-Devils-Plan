"""Private bank memories and legacy summaries, separate from the operator log."""

import json

from chatarena.message import Message, SYSTEM_NAME


MEMORY_HEADING = "\n\n5. 기억 슬롯\n"
FREE_MEMORY_HEADING = "\n\n5. 비공개 기억 요약\n"
DYNAMIC_MEMORY_HEADING = "\n\n5. 변경 가능한 기억 슬롯\n"
MEMORY_SUMMARY_LIMIT = 300
MEMORY_CAPACITY = 3
MEMORY_INSTRUCTIONS = (
    "기억과 발언에 관한 안내\n"
    "별도 메모·기록장·장부·누적 카운터를 작성하거나 조회할 수 없으며, 관전용 전체 기록도 열람할 수 없습니다. "
    "대화나 전략 메모에 수량을 적거나 '기록했다'고 말해도 기억 슬롯 밖의 수량이 다음 턴에 보존되지 않습니다. "
    "실제로 기록장을 쓰거나 저장한 것처럼 '기록했습니다', '적어 두겠습니다'라고 말하지 마세요. "
    "선택한 세 저금통에서 정확히 회상한 값, 이번 턴에 직접 확인한 사실, 상대의 주장과 자신의 추정을 구분해 말하세요. "
    "동전을 추가하겠다는 계획은 실제로 추가·전달되기 전까지 실행된 행동으로 간주하지 마세요."
)
FREE_MEMORY_INSTRUCTIONS = (
    "비공개 기억 요약 안내\n"
    "다음 구간에도 보존되는 개인 기억은 자신이 직접 작성한 300자 이내 요약 하나뿐입니다. "
    "저금통 번호와 주제의 제한 없이 관측한 수량, 자신의 추정, 발언, 약속, 전략 중 필요한 내용을 골라 남길 수 있습니다. "
    "틀린 기억도 자동 보정하지 않으며 요약에서 빠진 내용은 다음 갱신 뒤 다시 제공되지 않습니다. "
    "대화나 전략 메모는 요약에 포함한 내용만 이후에 기억할 수 있습니다. "
    "별도 기록장이나 장부를 사용하거나 전체 관전 기록을 조회할 수 없습니다. "
    "실제 사실과 상대의 주장, 자신의 추정을 구분하고 계획한 동전 추가를 실행된 행동으로 간주하지 마세요."
)
DYNAMIC_MEMORY_INSTRUCTIONS = (
    "변경 가능한 기억 슬롯 안내\n"
    "다음 구간에도 보존되는 개인 기억은 저금통 세 개의 흑·백 개수에 대한 본인의 기억뿐입니다. "
    "기억 갱신 때 현재 저금통 중 아무 세 번호나 고를 수 있으며 이전 번호를 유지할 필요는 없습니다. "
    "선택에서 뺀 저금통의 과거 수량은 사라지고, 다시 골라도 실제 수량이나 과거 기억을 자동 복구하지 않습니다. "
    "기억은 틀릴 수 있고 null은 모른다는 뜻입니다. 새로 고른 번호도 이번에 확인한 사실과 추정으로 직접 답하세요. "
    "updated_turn은 저장된 추정이 갱신된 게임 턴입니다. 그때까지의 추가는 이미 반영했을 수 있으므로 "
    "그 뒤 새로 확인한 추가만 반영하고 같은 전달을 두 번 더하지 마세요. "
    "별도 자유 메모·기록장·장부를 쓰거나 전체 관전 기록을 조회할 수 없습니다. "
    "실제 사실과 상대의 주장, 자신의 추정을 구분하고 계획한 동전 추가를 실행된 행동으로 간주하지 마세요."
)
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


def parse_memory_summary(action):
    if not isinstance(action, str) or len(action) > MEMORY_SUMMARY_LIMIT:
        raise ValueError(f"기억 요약은 {MEMORY_SUMMARY_LIMIT}자 이내의 문자열로 답하세요.")
    return action


def parse_memory_update(action, bank_ids):
    banks = json.loads(action)
    if (not isinstance(banks, dict) or len(banks) != MEMORY_CAPACITY
            or not set(banks) <= {str(bank) for bank in bank_ids}):
        raise ValueError("현재 저금통 중 서로 다른 세 번호만 골라 기억을 답하세요.")
    for counts in banks.values():
        if (not isinstance(counts, dict) or counts.keys() != {"black", "white"}
                or any(value is not None and (type(value) is not int or value < 0) for value in counts.values())):
            raise ValueError("흑·백의 기억은 음이 아닌 정수 또는 모르면 null로 답하세요.")
    return banks


class PiggyMemory:
    def __init__(self, players, banks, *, mode="exact", auto_select=True):
        if mode not in {"exact", "summary", "dynamic"}:
            raise ValueError("지원하지 않는 기억 방식입니다.")
        self.players = tuple(players)
        self.banks = banks
        self.selections = {name: [] for name in players}
        self.epoch = 0
        self.mode = mode
        self.auto_select = auto_select
        if mode == "summary":
            self.summaries = dict.fromkeys(self.players, "")
        elif mode == "dynamic":
            self.beliefs = {name: {} for name in self.players}
        self.updated_turn = dict.fromkeys(self.players, 0)
        self.through = dict.fromkeys(self.players, 0)
        if mode == "dynamic":
            self.reset(0)

    def select(self, name, banks):
        self.selections[name] = parse_memory_selection(json.dumps(banks), self.banks)

    def update(self, name, value, turn, through):
        if self.mode == "dynamic":
            self.beliefs[name] = parse_memory_update(json.dumps(value), self.banks)
            self.selections[name] = [int(bank) for bank in self.beliefs[name]]
        else:
            self.summaries[name] = parse_memory_summary(value)
        self.updated_turn[name] = turn
        self.through[name] = through

    def replace(self, old_bank, new_bank):
        changed = []
        for name, selected in self.selections.items():
            if old_bank in selected:
                self.selections[name] = [new_bank if bank == old_bank else bank for bank in selected]
                if self.mode == "dynamic":
                    previous = self.beliefs[name]
                    self.beliefs[name] = {
                        str(bank): {"black": 1, "white": 1} if bank == new_bank else previous[str(bank)]
                        for bank in self.selections[name]
                    }
                changed.append(name)
        return changed

    def reset(self, epoch, turn=0):
        self.epoch = epoch
        if self.mode == "dynamic":
            selected = sorted(self.banks)[:MEMORY_CAPACITY] if self.auto_select else []
            self.selections = {name: selected.copy() for name in self.players}
            self.beliefs = {name: {str(bank): {"black": 1, "white": 1} for bank in selected}
                           for name in self.players}
            self.updated_turn = dict.fromkeys(self.players, turn)
        elif self.mode == "exact":
            self.selections = {name: [] for name in self.players}

    def recall(self, name):
        if self.mode == "dynamic":
            return {"reset": self.epoch, "mode": "dynamic", "updated_turn": self.updated_turn[name],
                    "banks": {bank: counts.copy() for bank, counts in self.beliefs[name].items()}}
        if self.mode == "summary":
            return {"reset": self.epoch, "mode": "summary", "updated_turn": self.updated_turn[name],
                    "text": self.summaries[name], "limit": MEMORY_SUMMARY_LIMIT}
        return {"reset": self.epoch, "banks": {
            str(bank): self.banks[bank].copy() for bank in self.selections[name] if bank in self.banks
        }}

    def __call__(self, name, history):
        """Expose retained memory and fresh observations without recovering expired history."""
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
            if (kind == "discussion_note" and event.agent_name == name and index < first_turn
                    and (self.mode == "exact" or self.through[name] == 0)):
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
        instructions = {"exact": MEMORY_INSTRUCTIONS, "summary": FREE_MEMORY_INSTRUCTIONS,
                        "dynamic": DYNAMIC_MEMORY_INSTRUCTIONS}[self.mode]
        projected.append(Message(SYSTEM_NAME, instructions, turn=turn,
                                 msg_type="rules", visible_to=[name]))
        if plan is not None:
            projected.append(plan)
        projected.append(Message(SYSTEM_NAME, encode(state), turn=turn, msg_type="pig_state"))
        fresh = (visible[boundary:] if self.mode == "exact" else
                 (event for event in visible if event.turn >= self.through[name]))
        projected.extend(event for event in fresh if event.msg_type in _CURRENT_EVENTS)
        projected.append(Message(name, encode(self.recall(name)), turn=turn,
                                 msg_type="pig_recall", visible_to=[name]))
        # Requests are normally appended after projection; accept that form for direct callers too.
        if visible and visible[-1].msg_type.endswith("_request"):
            projected.append(visible[-1])
        return projected
