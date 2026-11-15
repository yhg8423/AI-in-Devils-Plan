"""Day 2 prison match as a virtual six-slot deduction game."""

from functools import partial
import json

from ..either_or.discussion import MAX_SPEECH_LENGTH, speech_text
from ..match import Decision, Match
from ..models import STRATEGY_NOTE_LIMIT


def parse_speech(response, neighbors):
    speech = json.loads(response)
    if not isinstance(speech, list):
        raise ValueError("Expected a list of messages")
    messages = []
    for message in speech:
        if not isinstance(message, dict):
            raise ValueError("Expected a message object")
        channel = message.get("channel")
        if channel == "public" and message.keys() == {"channel", "text"}:
            recipient = None
        elif channel == "whisper" and message.keys() == {"channel", "to", "text"} and message["to"] in neighbors:
            recipient = message["to"]
        else:
            raise ValueError("Whispers may only go to an adjacent seat")
        messages.append((channel, speech_text(message["text"]), recipient))
    return messages


def valid_speech(response, *, neighbors):
    try:
        parse_speech(response, neighbors)
    except (ValueError, RecursionError):
        return False
    return True


def reflect(match, name, action, outcome, balance, positions):
    note = match.request_action(
        name, "roulette_reflection",
        f"행동 후 비공개 복기입니다. 방금 한 행동: {action}. 결과: {outcome}\n"
        f"내 남은 크레딧 {balance}. {positions}\n"
        "행동 전 예상과 실제 결과를 비교하세요. 새로 확인한 정보와 아직 추정인 내용을 구분하고, "
        "다음 대화나 행동에서 무엇을 바꿀지 적으세요. 회전은 참가자와 칸의 대응을 바꾸고, "
        "조작은 지정한 두 칸의 내용만 교환합니다. "
        f"전략 메모만 한국어 {STRATEGY_NOTE_LIMIT}자 이내로 출력하세요.",
        "", valid=lambda text: len(text.strip()) <= STRATEGY_NOTE_LIMIT,
    ).strip()
    if note:
        match.event("decision_note", {"phase": "roulette_reflection", "note": note}, private=[name], actor=name)
        return f"\n최근 내 비공개 복기 메모 · 이후 상황에 맞춰 수정하세요.\n{note}"
    return ""


def talk(match, seats, neighbors, credits, positions, acting, reflections):
    if not match.backends or match.live_turns <= 0:
        return

    def exchange(participants, instruction):
        decisions = {
            name: Decision(
                f"{instruction}\n다음 크레딧 행동은 {acting}의 차례입니다. "
                f"내 크레딧 {credits[name]}. {positions}\n"
                f"내 양옆 자리 {', '.join(neighbors[name])}.\n"
                "자기 차례가 아니거나 크레딧이 0이어도 무료로 말할 수 있습니다. "
                "내 말을 들은 상대가 어떤 행동을 할지, 그 행동이 내 생존에 어떤 영향을 줄지 판단하세요. "
                "상대를 돕거나 정보를 공유할 때는 내가 얻는 이득을 고려하세요. "
                "이미 전달한 내용을 반복할 이득도 따져보세요.\n"
                '발언을 JSON 배열로 출력하세요. 전체 발언은 [{"channel":"public","text":"..."}], '
                '귓속말은 [{"channel":"whisper","to":"양옆 중 한 참가자 ID","text":"..."}]입니다. '
                f"발언 하나는 {MAX_SPEECH_LENGTH}자까지입니다. 말할 내용이 없으면 []를 출력하세요."
                + reflections.get(name, ""),
                "[]", valid=partial(valid_speech, neighbors=neighbors[name]),
            )
            for name in participants if name in match.backends
        }
        listeners = set()
        for name, response in match.decide_together("roulette_talk", decisions, record_actions=False).items():
            for channel, text, recipient in parse_speech(response, neighbors[name]):
                if recipient is None:
                    match.event(channel, text, actor=name)
                    listeners.update(seats)
                else:
                    match.event(channel, text, actor=name, private=(name, recipient))
                    listeners.add(recipient)
        return listeners

    listeners = exchange(seats, "다음 크레딧 행동 전 전원에게 주어진 대화 기회입니다.")
    if listeners and match.live_turns > 0:
        exchange((name for name in seats if name in listeners), "방금 들은 발언에 답할 수 있는 기회입니다.")


def play(match: Match) -> dict:
    seats = list(match.players)
    match.rng.shuffle(seats)
    count = len(seats)
    neighbors = {name: (seats[index - 1], seats[(index + 1) % count]) for index, name in enumerate(seats)}
    marks = [False] * count
    for index in match.rng.sample(range(count), 2):
        marks[index] = True
    credits = dict.fromkeys(seats, 16)
    reflections = {}
    offset = manipulation_credits = round_number = 0

    def positions():
        return "현재 공개 칸 배정 " + " · ".join(
            f"{slot}번 {player}" for slot, player in enumerate(seats[offset:] + seats[:offset], 1)
        )

    match.event("rules", (
        "러시안 룰렛 · 6인 추리 게임\n\n"
        "1. 시작과 차례\n"
        "개인전입니다. 각 참가자의 목표는 자신의 최종 생존 가능성을 높이는 것입니다. "
        "참가자마다 단말기와 16크레딧을 받고, 추첨으로 자리를 정합니다. 6칸 원형 보드에 탈락 표식 두 개를 숨깁니다. "
        "첫 자리에 앉은 사람이 1라운드의 선입니다. 매 라운드 시계 방향으로 행동하고, 다음 라운드의 선은 "
        "시계 방향으로 한 자리씩 바뀝니다. 첫 행동 전과 크레딧 행동 사이에는 차례나 잔액에 관계없이 모두 무료로 말할 수 있습니다. "
        "전체 발언은 모두에게, 귓속말은 자기 양옆에 앉은 사람 중 한 명에게만 전달됩니다. "
        "발언이 있으면 받은 사람에게 다음 크레딧 행동 전에 한 번 답할 기회가 주어집니다. "
        "기준 칸을 옮겨도 양옆 자리는 그대로입니다.\n\n"
        "2. 조사와 회전\n"
        "자기 차례에는 잔액 안에서 행동 하나를 고릅니다. 공개 조사에는 1크레딧, 비공개 조사에는 2크레딧을 씁니다. "
        "두 조사 모두 고른 칸과 그 다음 칸에 표식이 있는지 확인합니다. 6번 다음은 1번입니다. "
        "공개 조사 결과는 모두에게, 비공개 조사 결과는 조사한 사람에게만 보입니다. "
        "1칸 회전에는 3크레딧, 2칸 회전에는 4크레딧을 씁니다. 1번 칸에 대응하는 자리는 시계 방향으로 옮겨지고 "
        "모두에게 공개됩니다.\n\n"
        "3. 조작\n"
        "조작을 선택하면 한 차례에 1~3크레딧을 비공개로 제출합니다. 조작에 제출한 크레딧이 합계 6개 이상이 되면 "
        "마지막으로 제출한 참가자에게 조작권이 생깁니다. 그 참가자는 이웃한 두 칸을 골라 내용을 맞바꿉니다. "
        "교환 뒤에는 초과분까지 소모하고, 다음 조작에 필요한 크레딧을 0부터 다시 셉니다. "
        "다른 참가자에게는 비공개 행동을 했다는 사실만 보이며, 제출한 크레딧 수와 교환 위치는 당사자만 봅니다.\n\n"
        "4. 종료와 생존\n"
        "잔액은 게임 도중 본인만 확인할 수 있습니다. 잔액이 0이 된 참가자는 이후 차례를 자동으로 넘깁니다. "
        "세 번째 참가자의 잔액이 0이 되는 행동을 마치면 게임을 끝냅니다. 1번 칸부터 시계 방향으로 판정하며, "
        "표식이 있는 두 칸에 대응하는 참가자는 탈락합니다. 살아남은 네 명은 피스를 한 개씩 받습니다."
    ))
    match.event("seats", {"clockwise": seats, "slot_1": seats[offset]})
    while sum(balance == 0 for balance in credits.values()) < 3:
        start = round_number % count
        round_number += 1
        match.event("round", {"round": round_number, "leader": seats[start]})
        for name in seats[start:] + seats[:start]:
            balance = credits[name]
            if not balance:
                match.event("pass", {"player": name})
                continue
            costs = {f"공개 조사 {slot}": 1 for slot in range(1, count + 1)}
            if balance >= 2:
                costs.update({f"비공개 조사 {slot}": 2 for slot in range(1, count + 1)})
            if balance >= 3:
                costs["회전 1"] = 3
            if balance >= 4:
                costs["회전 2"] = 4
            costs.update({f"조작 {amount}": amount for amount in range(1, min(balance, 3) + 1)})
            talk(match, seats, neighbors, credits, positions(), name, reflections)
            options = tuple(costs)
            action = match.decide(
                name, "credit",
                f"내 크레딧 {balance}. {positions()}\n내 생존에 가장 유리한 크레딧 행동을 하나 고르세요."
                + reflections.get(name, ""),
                match.policy.choice(options), options=options,
            )
            kind, number = action.rsplit(" ", 1)
            amount = int(number)
            credits[name] -= costs[action]
            if kind in {"비공개 조사", "조작"}:
                match.event("private_action", "비공개 행동을 했습니다.", actor=name)
            if kind in {"공개 조사", "비공개 조사"}:
                pair = (amount - 1, amount % count)
                inspected = {i + 1: marks[i] for i in pair}
                match.event("inspection", {"player": name, "slots": inspected},
                            private=[name] if kind == "비공개 조사" else ())
                outcome = " · ".join(f"{slot}번 {'표식' if marked else '빈칸'}" for slot, marked in inspected.items())
            elif kind == "회전":
                offset = (offset + amount) % count
                match.event("shift", {"player": name, "amount": amount, "slot_1": seats[offset]})
                outcome = f"회전 후 내 칸은 {(seats.index(name) - offset) % count + 1}번입니다."
            else:
                manipulation_credits += amount
                outcome = "이번 제출로 두 칸 교환은 발생하지 않았습니다."
                if manipulation_credits >= 6:
                    options = tuple(str(i) for i in range(1, count + 1))
                    swap = int(match.decide(
                        name, "swap",
                        f"조작권을 얻었습니다. {positions()}\n내 생존에 유리한 교환을 위해 인접 두 칸의 시작 번호를 고르세요."
                        + reflections.get(name, ""),
                        match.policy.choice(options), options=options,
                    ))
                    left, right = swap - 1, swap % count
                    marks[left], marks[right] = marks[right], marks[left]
                    manipulation_credits = 0
                    match.event("swap", {"player": name, "slots": [left + 1, right + 1]}, private=[name])
                    outcome = f"{left + 1}번과 {right + 1}번 칸의 내용을 교환했습니다."
            if sum(balance == 0 for balance in credits.values()) == 3:
                break
            if name in match.backends and match.live_turns > 0:
                reflection = reflect(match, name, action, outcome, credits[name], positions())
                if reflection:
                    reflections[name] = reflection
        if round_number % 3 == 0 and sum(balance == 0 for balance in credits.values()) < 3:
            match.review_relationships(f"러시안 룰렛 {round_number}라운드 종료")

    eliminated = [seats[(offset + i) % count] for i, marked in enumerate(marks) if marked]
    survivors = [name for name in seats if name not in eliminated]
    return {"rounds": round_number, "seats": seats, "credits": credits, "eliminated": eliminated,
            "survivors": survivors, "pieces_awarded": dict.fromkeys(survivors, 1),
            "pieces": {name: match.pieces[name] + (name in survivors) for name in seats}}
