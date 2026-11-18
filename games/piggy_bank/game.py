"""Hidden coin memory, suspicion, and reset challenges for four prisoners.

Rules: https://namu.wiki/w/데블스%20플랜:%20데드%20어게인/3일차#s-5.1
"""

import json

from ..either_or.discussion import Discussion
from ..match import Decision, Match, encode
from ..models import STRATEGY_NOTE_LIMIT


WIN_SCORE = 5
OPENING_TURNS = 4
COLORS = ("black", "white")
PASS = '{"type":"pass"}'


def parse_deposit(action, players, acting):
    move = json.loads(action)
    if not isinstance(move, dict) or move.keys() != {"black", "white", "to"}:
        raise ValueError("흑·백 동전 수와 전달 대상을 지정하세요.")
    if (any(type(move[color]) is not int or not 0 <= move[color] <= 5 for color in COLORS)
            or not 1 <= move["black"] + move["white"] <= 5
            or not isinstance(move["to"], str) or move["to"] == acting or move["to"] not in players):
        raise ValueError("자신 외의 참가자에게 합계 1~5개의 동전을 넣어 전달하세요.")
    return move


def parse_challenge(action, bank_ids):
    if action == "pass":
        return None
    guesses = json.loads(action)
    if not isinstance(guesses, dict) or set(guesses) != {str(bank) for bank in bank_ids}:
        raise ValueError("현재 저금통 다섯 개를 모두 답하세요.")
    for counts in guesses.values():
        if (not isinstance(counts, dict) or counts.keys() != set(COLORS)
                or any(type(counts[color]) is not int or counts[color] < 0 for color in COLORS)):
            raise ValueError("각 저금통의 흑·백 동전 수를 음이 아닌 정수로 답하세요.")
    return guesses


def _accepts(parse, action, *args):
    try:
        parse(action, *args)
    except (ValueError, TypeError, RecursionError):
        return False
    return True


def _count(action):
    if not action.isdecimal() or int(action) < 0:
        raise ValueError("동전 개수를 음이 아닌 정수로 답하세요.")
    return int(action)


def play(match: Match) -> dict:
    players = match.players
    if len(players) != 4 or "__operator__" in players:
        raise ValueError("돼지 저금통은 4명이 필요하며 __operator__는 참가자 ID로 쓸 수 없습니다.")
    order = match.rng.sample(list(players), 4)
    scores = dict.fromkeys(players, 0)
    acting = order[0]
    banks = {}
    lower = {}
    upper = {}
    next_bank = 6
    voters = []
    resets = turn = 0
    discussion = Discussion(order, OPENING_TURNS)

    def distribute():
        banks.clear()
        banks.update({bank: {"black": 1, "white": 1} for bank in range(1, 6)})
        lower.update({name: index for index, name in enumerate(order, 1)})
        upper.update({name: 5 if name == acting else None for name in order})

    def locations():
        return {"lower": lower.copy(), "upper": upper.copy()}

    def contents():
        match.event("pig_contents", {"banks": banks}, private=["__operator__"])

    def seating():
        return f"아래칸 {encode(lower)} · 위칸 {encode(upper)} · 공개 승점 {encode(scores)}"

    def talk(stage, turns):
        match.event("pig_discussion", {"stage": stage, "turn": turn, "turns": turns})
        for discussion_turn in range(1, turns + 1):
            for name in order:
                prompt = (
                    f"돼지 저금통 {'시작 전' if stage == 'opening' else '다음 행동 전'} 대화 "
                    f"{discussion_turn}/{turns}턴입니다. 다음 동전 추가자는 {acting}입니다. {seating()}\n"
                    "모두 같은 테이블에 앉아 있습니다. 공개 발언이나 특정 상대와의 귓속말을 선택할 수 있습니다. "
                    '전체 발언은 {"type":"speak","channel":"public","text":"..."}, '
                    '귓속말은 {"type":"speak","channel":"whisper","to":"상대 ID","text":"..."}입니다. '
                    '여럿에게는 to를 ["P02","P03"]처럼 지정하세요. 말하지 않으려면 {"type":"pass"}입니다. '
                    "동전이나 별도 저금통별 수량표로 카운팅하지 말고, 전달과 발언에 대한 기억을 바탕으로 판단하세요."
                )

                def parse(action):
                    payload = json.loads(action)
                    if (not isinstance(payload, dict) or "room" in payload
                            or payload.get("type") not in {"pass", "speak"}
                            or payload.get("channel", "public") not in {"public", "whisper"}):
                        raise ValueError("테이블에서 발언하거나 패스하세요.")
                    return discussion.parse(name, action, len(match.events), notes=False)

                action = match.decide(name, "pig_talk", prompt, PASS,
                                      valid=lambda action: _accepts(parse, action))
                parsed = parse(action)
                if parsed is not None:
                    for message in discussion.record(name, parsed, len(match.events)):
                        match.event(message.msg_type, message.content, actor=name,
                                    private=() if message.visible_to == "all" else message.visible_to)
        match.event("pig_discussion_end", {"stage": stage, "turn": turn})
        match.review_relationships("돼지 저금통 시작 전 대화 종료" if stage == "opening" else
                                   f"돼지 저금통 {turn}턴 대화 종료")

    match.event("rules", (
        "돼지 저금통 · 4인 기억 게임\n\n"
        "1. 시작과 전달\n"
        "추첨으로 자리와 첫 선을 정합니다. 1~4번 저금통을 각자 아래칸에 놓고, 선의 위칸에 5번을 놓습니다. "
        "저금통에는 처음에 흑동전과 백동전이 하나씩 들어 있습니다. 선은 아래칸 저금통에 두 색 동전을 "
        "합계 1~5개 넣고 추가한 흑·백 개수를 사실대로 공개한 뒤 다른 참가자에게 전달합니다. "
        "자신의 위칸 저금통은 아래칸으로 내리고, 받은 사람은 전달된 저금통을 위칸에 놓습니다.\n\n"
        "2. 개수 선언과 의심\n"
        "받은 사람은 위칸 저금통의 특정 색 동전 수를 선언합니다. 첫 선언은 흑, 다음은 백으로 계속 번갈아 바뀝니다. "
        "다른 참가자는 의심하거나 패스합니다. 의심하면 해당 저금통을 공개합니다. 선언이 틀렸으면 의심자는 "
        "1점을 받고 선언자는 1점을 잃습니다. 맞았으면 의심자만 1점을 잃습니다. 공개한 저금통은 제거하고 "
        "감점받은 참가자가 흑·백 하나씩 든 새 번호 저금통을 위칸에 받아 다음 동전 추가자가 됩니다. "
        "의심이 없으면 저금통을 받은 사람이 다음 추가자가 됩니다.\n\n"
        "3. 리셋과 전체 도전\n"
        "누구나 리셋을 요청할 수 있고, 서로 다른 세 명이 요청하면 리셋합니다. 리셋 전 요청하지 않은 한 명은 "
        "현재 다섯 저금통의 흑·백 개수를 모두 맞히는 도전을 하거나 패스할 수 있습니다. 모두 맞히면 3점, "
        "하나라도 틀리면 -2점입니다. 리셋하면 저금통은 흑·백 하나씩 든 1~5번으로 교체하고 요청을 지웁니다. "
        "누적 승점과 다음 추가자는 유지됩니다.\n\n"
        "4. 종료와 보상\n"
        "누군가 5점 이상을 얻는 즉시 최종 승점을 비교합니다. 최하위 한 명이 탈락하고 1위는 피스 3개를 받습니다. "
        "공동 1위는 피스 3개를 같은 정수 몫으로 나누고 나머지는 버립니다. 동전으로 카운팅하는 행위는 금지합니다.\n\n"
        "시뮬레이션 진행\n"
        "게임 전 비공개 전략 준비 두 단계와 참가자별 네 턴의 대화가 있습니다. 추가 행동 전에는 전원에게 한 턴씩 "
        "대화 기회를 줍니다. 20초 선언과 10초 의심은 각각 한 번의 응답으로 진행합니다. 의심은 동시에 제출하며 "
        "여러 명이 선택하면 추첨 자리 순서로 한 명을 정합니다. 리셋은 매 전달 뒤 추첨 순서로 요청 기회를 주고 "
        "세 번째 요청 즉시 처리합니다. 리셋 뒤에도 선언 색은 이어집니다. 최하위 동점은 추첨 순서가 뒤인 사람이 "
        "탈락합니다. "
        "참가자에게 자동 집계된 저금통별 수량표를 제공하지 않습니다."
    ))
    distribute()
    match.event("pig_setup", {"order": order, **locations(), "scores": scores.copy()})
    contents()
    match.event("pig_preparation", {"steps": 2})
    plans = dict.fromkeys(players, "전달과 공개 발언을 기억하고, 확신할 때만 의심하거나 전체 도전을 시도한다.")
    for step in (1, 2):
        plans = match.decide_together("pig_preparation", {
            name: Decision(
                f"돼지 저금통 비공개 전략 준비 {step}/2단계입니다. "
                + ("의심·리셋·전체 도전의 이득과 위험을 정리하세요. " if step == 1 else
                   "직전 계획의 취약점과 협력이 거절될 때의 대안을 검토해 수정하세요. ")
                + f"내 이전 전략 요약: {plans[name]}\n"
                "저금통별 동전 수량표나 누적 카운터를 작성하지 마세요. 공개한 기억과 불확실성을 구분하세요. "
                f"수정한 전략 요약만 한국어 {STRATEGY_NOTE_LIMIT}자 이내로 출력하세요.",
                plans[name], valid=lambda action: 0 < len(action.strip()) <= STRATEGY_NOTE_LIMIT,
            ) for name in order
        }, record_actions=False)
        for name, note in plans.items():
            match.event("decision_note", {"phase": "pig_preparation", "step": step, "steps": 2, "note": note},
                        actor=name, private=[name])
    for name, note in plans.items():
        match.event("discussion_note", note, actor=name, private=[name])
    match.event("pig_preparation_end", {"steps": 2})
    talk("opening", OPENING_TURNS)

    while max(scores.values()) < WIN_SCORE:
        turn += 1
        color = COLORS[(turn - 1) % 2]
        match.event("pig_turn", {"turn": turn, "player": acting, "color": color,
                                 **locations(), "scores": scores.copy()})
        talk("before_turn", 1)
        black = match.policy.randrange(6)
        white = match.policy.randint(0 if black else 1, 5 - black)
        default = encode({"black": black, "white": white,
                          "to": match.policy.choice([name for name in order if name != acting])})
        deposit = parse_deposit(match.decide(
            acting, "pig_deposit",
            f"{turn}턴. 아래칸 {lower[acting]}번에 동전을 추가하고 다른 참가자에게 전달하세요. {seating()}\n"
            'JSON 예: {"black":2,"white":1,"to":"상대 ID"}. 합계 1~5개이며 추가 개수는 그대로 공개됩니다. '
            f"받는 사람은 {'흑' if color == 'black' else '백'} 동전의 총개수를 선언합니다.",
            default, valid=lambda action: _accepts(parse_deposit, action, players, acting),
        ), players, acting)
        recipient = deposit["to"]
        bank = lower[acting]
        for coin in COLORS:
            banks[bank][coin] += deposit[coin]
        lower[acting], upper[acting] = upper[acting], None
        upper[recipient] = bank
        match.event("pig_deposit", {"turn": turn, "player": acting, "to": recipient, "bank": bank,
                                    "black": deposit["black"], "white": deposit["white"], **locations()})
        contents()
        count = _count(match.decide(
            recipient, "pig_count",
            f"{turn}턴. 전달받은 위칸 {bank}번 저금통의 {'흑' if color == 'black' else '백'} 동전 총개수를 선언하세요. "
            "지금까지 들은 전달·추가·개봉 기록을 기억해서 답하세요. 자동 수량표는 제공되지 않습니다. "
            "동전 수를 음이 아닌 정수 하나로 출력하세요.",
            str(match.policy.randint(1, min(20, turn + 5))), valid=lambda action: _accepts(_count, action), private=False,
        ))
        match.event("pig_claim", {"turn": turn, "player": recipient, "bank": bank, "color": color, "count": count})
        answers = match.decide_together("pig_doubt", {
            name: Decision(
                f"{recipient}가 {bank}번 저금통의 {'흑' if color == 'black' else '백'} 동전을 {count}개라고 선언했습니다. "
                "기억한 전달 기록을 바탕으로 의심(doubt)하거나 통과(pass)하세요. 성공 +1, 실패 -1입니다.",
                match.policy.choice(("doubt", "pass", "pass")), options=("doubt", "pass"),
            ) for name in order if name != recipient
        })
        challenger = next((name for name in order if answers.get(name) == "doubt"), None)
        acting = recipient
        if challenger is not None:
            correct = count != banks[bank][color]
            if correct:
                scores[challenger] += 1
                scores[recipient] -= 1
            else:
                scores[challenger] -= 1
            match.event("pig_doubt", {
                "turn": turn, "challenger": challenger, "player": recipient, "bank": bank, "color": color,
                "claimed": count, "actual": banks[bank].copy(), "correct": correct, "scores": scores.copy(),
            })
            acting = recipient if correct else challenger
            del banks[bank]
            upper[recipient] = None
            banks[next_bank] = {"black": 1, "white": 1}
            upper[acting] = next_bank
            match.event("pig_replace", {"turn": turn, "player": acting, "next_player": acting, "old_bank": bank,
                                        "bank": next_bank, "initial": banks[next_bank].copy(), **locations()})
            next_bank += 1
            contents()
        else:
            match.event("pig_pass", {"turn": turn, "player": recipient, "bank": bank, "color": color, "count": count})
        match.review_relationships(f"돼지 저금통 {turn}턴 선언·의심 결과")
        if max(scores.values()) >= WIN_SCORE:
            break

        for name in order:
            if name in voters:
                continue
            request = match.decide(
                name, "pig_reset_vote",
                f"{turn}턴 전달과 의심이 끝났습니다. 현재 리셋 요청자 {encode(voters)}. {seating()}\n"
                "리셋을 요청하려면 reset, 아니면 pass입니다. 요청은 취소할 수 없으며 세 명이면 리셋합니다. "
                "나머지 한 명은 그 전에 전체 동전 수 맞추기에 도전할 수 있습니다.",
                "reset" if match.policy.randrange(8) == 0 else "pass", options=("reset", "pass"), private=False,
            )
            if request != "reset":
                continue
            voters.append(name)
            match.event("pig_reset_vote", {"turn": turn, "player": name, "voters": voters.copy()})
            if len(voters) == 3:
                challenger = next(name for name in order if name not in voters)
                guess = parse_challenge(match.decide(
                    challenger, "pig_challenge",
                    f"세 명이 리셋을 요청했습니다. 당신만 현재 저금통 {encode(sorted(banks))}의 흑·백 개수를 모두 "
                    "맞히는 도전에 나설 수 있습니다. 성공 +3점, 실패 -2점입니다. 도전하지 않으면 pass를 출력하세요. "
                    '도전하려면 모든 번호를 포함한 JSON 객체를 출력하세요. 예: {"1":{"black":1,"white":2},...}. '
                    "지금까지 들은 공개 기록에 대한 기억만 사용하세요.",
                    "pass", valid=lambda action: _accepts(parse_challenge, action, banks),
                ), banks)
                if guess is not None:
                    actual = {str(bank): counts.copy() for bank, counts in banks.items()}
                    correct = guess == actual
                    scores[challenger] += 3 if correct else -2
                    match.event("pig_challenge", {"turn": turn, "player": challenger, "guesses": guess, "actual": actual,
                                                 "correct": correct, "scores": scores.copy()})
                    match.review_relationships(f"돼지 저금통 {turn}턴 전체 도전 결과")
                if max(scores.values()) >= WIN_SCORE:
                    break
                resets += 1
                distribute()
                next_bank = 6
                voters.clear()
                match.event("pig_reset", {"turn": turn, "reset": resets, "order": order, "scores": scores.copy(),
                                          "next_player": acting, **locations()})
                contents()
                match.review_relationships(f"돼지 저금통 {turn}턴 리셋 완료")
                break

    ranking = sorted(order, key=lambda name: -scores[name])
    winners = [name for name in ranking if scores[name] == scores[ranking[0]]]
    awards = {name: 3 // len(winners) if name in winners else 0 for name in players}
    return {"turns": turn, "resets": resets, "ranking": ranking, "scores": scores,
            "winners": winners, "survivors": ranking[:-1], "eliminated": ranking[-1:],
            "pieces_awarded": awards, "pieces": {name: match.pieces[name] + awards[name] for name in players}}
