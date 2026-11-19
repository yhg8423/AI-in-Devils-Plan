"""Seven all-pay auctions with hidden awards and an optimal final bingo board."""

from collections import Counter
import json

from ..either_or.discussion import Discussion
from ..match import Decision, Match, encode
from ..models import STRATEGY_NOTE_LIMIT


GUEST = "G01"
ROUNDS = 7
SHAPES = ("triangle", "circle", "star")
SHAPE_NAMES = {"triangle": "세모", "circle": "동그라미", "star": "별"}
BOARD = (("triangle", "circle", "triangle"), ("circle", "star", "circle"),
         ("star", "circle", "triangle"))
INITIAL_COINS = {1: 3, 2: 3, 3: 2, 5: 1, 10: 1}
OPENING_TURNS = 10
DISCUSSION_TURNS = 6
FREE_SUBMISSION_HEADING = "\n\n6. 자유 제출\n"
PREPARATION_STEPS = (
    "목표 설정: 빙고판과 자금 제약을 검토하고, 필요한 도형과 생존·우승 목표를 정하세요.",
    "위험·대안 검토: 낙찰 여부는 본인도 알 수 없고 낙찰 실패에도 코인이 소모됩니다. 이전 계획의 위험과 대안을 검토하세요.",
    "협상 계획 확정: 제안할 협력, 공개할 정보의 범위와 계획을 바꿀 조건을 정하세요.",
)


def coin_value(coins):
    return sum(int(value) * count for value, count in coins.items())


def parse_bid(action, coins, pieces):
    """Validate physical denominations and a simultaneous Piece-to-one-won exchange."""
    payload = json.loads(action)
    if not isinstance(payload, dict) or payload.keys() != {"coins", "pieces"}:
        raise ValueError("coins와 pieces를 지정하세요.")
    used, exchanged = payload["coins"], payload["pieces"]
    if (not isinstance(used, dict) or type(exchanged) is not int or not 0 <= exchanged <= pieces
            or any(value not in {str(value) for value in INITIAL_COINS}
                   or type(count) is not int
                   or not 0 <= count <= coins.get(int(value), 0) + (exchanged if value == "1" else 0)
                   for value, count in used.items())):
        raise ValueError("보유한 코인과 피스만 입찰할 수 있습니다.")
    used = {int(value): count for value, count in used.items()}
    if coin_value(used) < 1:
        raise ValueError("매 라운드 최소 1원을 입찰해야 합니다.")
    return used, exchanged


def settle_round(choices, bids):
    """Compute a hidden allocation separately from its safe public announcement."""
    if (set(choices) != set(bids) or any(shape not in SHAPES for shape in choices.values())
            or any(type(value) is not int or value < 0 for value in bids.values())):
        raise ValueError("도형 선택과 입찰 내역이 올바르지 않습니다.")
    counts = {shape: sum(choice == shape for choice in choices.values()) for shape in SHAPES}
    prices, winners, discarded = {}, {}, {}
    awards = dict.fromkeys(choices, 0)
    for shape in SHAPES:
        bidders = [name for name in choices if choices[name] == shape and bids[name] > 0]
        price = max((bids[name] for name in bidders), default=None)
        prices[shape] = price
        winners[shape] = [name for name in bidders if bids[name] == price]
        share = counts[shape] // len(winners[shape]) if winners[shape] else 0
        for name in winners[shape]:
            awards[name] = share
        discarded[shape] = counts[shape] - share * len(winners[shape])
    highest = max((price for price in prices.values() if price is not None), default=None)
    secret = [shape for shape in SHAPES if highest is not None and prices[shape] == highest]
    return {"counts": counts, "prices": prices, "secret": secret, "winners": winners,
            "awards": awards, "discarded": discarded}


def optimal_board(shapes):
    """Exhaust all 512 board masks; use every placeable shape and maximize lines."""
    if (any(shape not in SHAPES for shape in shapes)
            or any(type(count) is not int or count < 0 for count in shapes.values())):
        raise ValueError("획득 도형 수가 올바르지 않습니다.")
    cells = sum(BOARD, ())
    available = {shape: min(shapes.get(shape, 0), cells.count(shape)) for shape in SHAPES}
    lines = ((0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8),
             (0, 4, 8), (2, 4, 6))
    best, best_lines = 0, -1
    for mask in range(1 << 9):
        selected = Counter(cells[index] for index in range(9) if mask & (1 << index))
        if any(selected[shape] != available[shape] for shape in SHAPES):
            continue
        count = sum(all(mask & (1 << index) for index in line) for line in lines)
        if count > best_lines:
            best, best_lines = mask, count
    return {"board": [[BOARD[row][col] if best & (1 << (row * 3 + col)) else None
                       for col in range(3)] for row in range(3)],
            "lines": best_lines, "filled": sum(available.values())}


def play(match: Match) -> dict:
    if len(match.players) != 8 or match.players.count(GUEST) != 1:
        raise ValueError("경매 빙고에는 본선 참가자 7명과 게스트 G01 한 명이 필요합니다.")
    players = match.players
    log = match.resume_log
    recorded_rules = next((event["content"] for event in log.events if event["msg_type"] == "rules"), None) if (
        log is not None and log.resume) else None
    free_submission = recorded_rules is None or FREE_SUBMISSION_HEADING in recorded_rules
    opening_turns = OPENING_TURNS if free_submission else 12
    discussion_turns = DISCUSSION_TURNS if free_submission else 4
    base_order = match.rng.sample(list(players), len(players))
    coins = {name: INITIAL_COINS.copy() for name in players}
    pieces = match.pieces.copy()
    spent = dict.fromkeys(players, 0)
    awards = dict.fromkeys(players, 0)
    shapes = {name: dict.fromkeys(SHAPES, 0) for name in players}
    forced_last = set()
    history = []
    discussion = Discussion(players, discussion_turns)
    rules = (
        "경매 빙고 · 본선 7명과 게스트 G01 · 7라운드\n\n"
        "1. 준비\n"
        "모두 같은 3×3 빙고판과 네임 티켓 7장, 1원 코인 3개·2원 3개·3원 2개·5원 1개·10원 1개(총 30원)를 받습니다. "
        "빙고판은 위부터 [세모, 동그라미, 세모] / [동그라미, 별, 동그라미] / [별, 동그라미, 세모]입니다. "
        "코인은 작은 단위로 나누거나 다른 사람에게 넘길 수 없습니다.\n\n"
        "2. 도형 선택과 입찰\n"
        "매 라운드 도형 선택 뒤 비공개 입찰을 합니다. 세모·동그라미·별 중 하나를 고르고, 전원 선택 후 각자의 도형이 공개됩니다. "
        "선택한 도형에 보유 코인을 조합해 최소 1원을 입찰합니다. 입찰할 때 피스 1개를 1원 코인 하나로 교환할 수 있습니다. "
        "교환한 코인은 입찰에 쓰거나 남길 수 있고, 교환한 피스는 반환되지 않습니다. "
        "입찰에 사용한 코인은 낙찰 여부와 관계없이 소모됩니다. 어느 라운드든 최소 1원을 내지 못하면 자동 최하위입니다.\n\n"
        "3. 낙찰과 비공개 정보\n"
        "각 도형의 최고 입찰자는 그 도형을 선택한 인원수만큼 도형을 얻습니다. 최고액 동률이면 해당 도형을 균등 분배하고 나머지는 버립니다. "
        "누가 낙찰받았는지와 획득한 도형 수는 본인에게도 알려주지 않습니다. 공개 발표에는 도형별 낙찰가만 나옵니다. "
        "세 도형 중 최고 낙찰가에 해당하는 도형은 모두 시크릿으로 표시합니다. 도형끼리 최고가가 같으면 모두 숨깁니다. "
        "선택자가 없는 도형은 경매 없음으로 표시합니다.\n\n"
        "4. 최종 결과\n"
        "7라운드가 끝나면 획득 도형과 시크릿 낙찰가를 공개합니다. 개인 입찰액은 계속 비공개입니다. "
        "넘치는 도형은 버리고 빙고 줄 수를 최대화하도록 자동 배치합니다. "
        "가로·세로·대각선의 완성 줄 수, 채운 칸 수, 남은 코인의 금액 합계 순으로 순위를 비교합니다. "
        "게스트를 제외한 상위 2명은 생활동, 다음 4명은 감옥동, 최하위 1명은 탈락입니다. "
        "본선 1위는 연맹의 징표로 감옥동 한 명을 생활동으로 옮깁니다. 9칸을 모두 채우면 피스 4개를 받습니다. "
        "게스트는 생활동·감옥동·탈락 판정에서 제외되며, 전체 1위와 빙고판 완성에 각각 상금 1,000만 원이 걸려 있습니다.\n\n"
        "5. 시뮬레이터 진행 규칙\n"
        f"규칙 공개 후 첫 대화 전에 비공개 전략 요약을 3단계로 다듬습니다. 시작 전 대화는 참가자마다 {opening_turns}턴, "
        f"매 라운드 도형 선택 전과 선택 공개 후 입찰 전 대화는 각각 최대 {discussion_turns}턴입니다. 매 라운드 대화는 한 턴에서 전원 패스하면 마칩니다. "
        "전체 대화, 논의실 이동·초대·대화, 같은 장소의 1:1 또는 그룹 귓속말을 사용할 수 있습니다. 입찰 직전에는 비공개 전략 요약을 갱신합니다. "
        "각 대화 구간과 공개 발표가 끝나면 새 근거에 따라 친밀도·신뢰도를 비공개로 검토합니다. "
        "완전 동률과 여러 자동 최하위자 사이의 순서는 시작할 때 추첨한 기본 순서로 판정합니다. "
        "도형 선택과 입찰은 각각 모두 같은 시점의 정보를 보고 동시에 제출합니다. "
        "게스트도 자신의 두 미션을 위해 경쟁하며 다른 참가자에게 협력할 의무는 없습니다."
    )
    if free_submission:
        rules = rules.replace("도형 선택과 입찰은 각각 모두 같은 시점의 정보를 보고 동시에 제출합니다. ", "")
        rules += FREE_SUBMISSION_HEADING + (
            "도형 선택과 입찰은 각각 최대 6턴의 대화 중 원하는 자기 차례에 비공개로 확정 제출할 수 있습니다. "
            "한 번 제출하면 바꾸거나 다시 제출할 수 없습니다. 제출한 사람도 다른 참가자가 결정하는 동안 대화하거나 이동할 수 있습니다. "
            "공개되는 제출 현황에는 완료한 참가자만 표시되고 도형과 입찰액은 표시되지 않습니다. "
            "전원 제출하면 남은 대화 없이 즉시 해당 단계를 끝냅니다. 6턴이 끝나거나 전원 패스하면 미제출자만 마지막으로 제출합니다. "
            "도형은 전원 제출 후 함께 공개하고, 개인 입찰액은 계속 비공개입니다. 입찰 전 전략 요약은 입찰 대화를 시작하기 전에 정리하고, "
            "대화 중에는 매 차례 전략 메모를 갱신합니다. 입찰 확정과 동시에 사용 코인과 교환 피스를 정산합니다."
        )
    if recorded_rules is not None:
        rules = recorded_rules
    match.event("rules", rules)
    match.event("bingo_setup", {"board": BOARD, "guest": GUEST, "base_order": base_order,
                                "coins": INITIAL_COINS, "pieces": pieces.copy(), "rounds": ROUNDS})

    def short_note(text):
        return isinstance(text, str) and 0 < len(text.strip()) <= STRATEGY_NOTE_LIMIT

    def prepare(phase, round_number, focus, previous=None):
        notes = match.decide_together(phase, {
            name: Decision(
                f"경매 빙고 비공개 전략 정리. {focus}\n"
                f"내 남은 코인 {encode(coins[name])}, 금액 합계 {coin_value(coins[name])}원, 피스 {pieces[name]}개. "
                "본인도 실제 낙찰 여부와 획득 도형 수를 아직 모릅니다. 상대의 발언을 확정 사실과 구분하세요. "
                + ("나는 G01입니다. 전체 1위와 빙고판 완성이라는 두 미션을 목표로 경쟁하세요. "
                   if name == GUEST else "내 생존과 생활동 진출, 우승에 유리한 계획을 세우세요. ")
                + (f"\n이전 전략 요약: {previous[name]}" if previous else "")
                + f"\n수정된 전략 요약만 한국어 {STRATEGY_NOTE_LIMIT}자 이내로 출력하세요.",
                previous[name] if previous else "남은 라운드에 최소 입찰액을 남기고, 필요한 도형과 경쟁 인원에 따라 입찰한다.",
                valid=short_note,
            ) for name in players
        }, record_actions=False)
        for name, note in notes.items():
            match.event("decision_note", {"phase": phase, "round": round_number, "note": note},
                        actor=name, private=[name])
        return notes

    def discuss(stage, round_number, topic, *, decisions=None, on_submit=None):
        turns = opening_turns if stage == "opening" else discussion_turns
        discussion.rounds = turns
        context = {"stage": stage, "round": round_number, "rounds": turns}
        match.event("bingo_discussion", context)
        submitted = {}
        resolved = set(players) - set(decisions) if decisions is not None else set()
        phase = "shape" if stage == "before_shape" else "bid"

        def commit(name, choice):
            submitted[name] = choice
            resolved.add(name)
            match.event("action", {"phase": f"bingo_{phase}", "action": choice}, actor=name, private=[name])
            if on_submit is not None:
                on_submit(name, choice)
            progress(name)

        def progress(name):
            match.event("bingo_submission", {"round": round_number, "phase": phase, "player": name,
                                              "submitted": [name for name in players if name in resolved],
                                              "total": len(players)})

        if decisions is not None:
            for name in players:
                if name not in decisions:
                    progress(name)
        reason = "limit"
        for current in range(1, turns + 1):
            if decisions is not None and len(resolved) == len(players):
                reason = "all_submitted"
                break
            match.event("bingo_discussion_round", {**context, "turn": current})
            active = False
            for seat, name in enumerate(base_order):
                if name not in match.backends or match.live_turns <= 0:
                    continue
                turn = len(match.events)
                submission = decisions.get(name) if decisions is not None and name not in resolved else None
                status = ""
                if decisions is not None:
                    if name in submitted:
                        status = f"\n나는 이미 비공개로 {submitted[name]}을 확정했습니다. 수정·재제출은 불가능하며 대화와 이동만 할 수 있습니다."
                    elif name in resolved:
                        status = "\n나는 최소 입찰액을 낼 수 없어 자동 최하위로 판정되었습니다. 대화와 이동은 할 수 있습니다."
                    else:
                        example = encode({"type": "submit", "choice": submission.default, "note": "선택 근거와 전략 요약"})
                        status = (
                            "\n나는 아직 제출하지 않았습니다. 지금 확정하려면 아래 형식의 비공개 제출을 사용하세요. "
                            "제출하면 되돌리거나 수정할 수 없습니다. 더 논의하려면 대화·이동·패스를 선택하세요.\n"
                            + example + "\n" + submission.instructions()
                        )
                    status += f"\n이번 단계 제출 완료 {len(resolved)}/{len(players)}명."
                request = discussion.request(
                    name, turn, topic + status + "\n필요한 도형과 입찰 협력을 논의할 수 있지만 약속은 행동을 구속하지 않습니다. "
                    "비공개로 논의할 상대가 있다면 논의실이나 같은 장소의 귓속말을 사용하세요. "
                    '전체 발언 {"type":"speak","channel":"public","text":"발언","note":"전략 요약"}, '
                    '같은 장소의 귓속말은 channel을 "whisper"로 하고 to에 상대 ID 또는 ID 배열을 넣으세요. '
                    '이동은 {"type":"move","room":1,"note":"전략 요약"}, 복도는 room:0, '
                    '논의실 발언은 channel:"room", 초대는 channel:"room_invite"와 room·to·text를 사용하세요. '
                    '초대 응답은 {"type":"respond_invite","invite_id":0,"decision":"accept","note":"전략 요약"}처럼 '
                    '받은 초대 번호와 accept 또는 decline을 쓰세요. '
                    '패스는 {"type":"pass","note":"전략 요약"}. '
                    f"내 코인 {encode(coins[name])}, 피스 {pieces[name]}개. 실제 낙찰 결과는 아직 공개되지 않았습니다.",
                    action_index=(current - 1) * len(players) + seat, notes=True,
                    progress=f"대화 {current}/{turns}턴",
                )

                def valid(action):
                    try:
                        discussion.parse(name, action, turn, notes=True,
                                         validate_submission=submission.accepts if submission else None)
                    except (ValueError, TypeError, RecursionError):
                        return False
                    return True

                action = match.request_action(
                    name, "bingo_discussion", request.content,
                    encode({"type": "pass", "note": "들은 제안과 남은 자금을 비교해 다음 선택을 준비한다."}),
                    valid=valid, request_type=request.msg_type,
                )
                parsed = discussion.parse(name, action, turn, notes=True,
                                          validate_submission=submission.accepts if submission else None)
                active = active or parsed.room is not None or bool(parsed.messages)
                for event in discussion.record(name, parsed, turn):
                    match.event(event.msg_type, event.content, actor=event.agent_name,
                                private=() if event.visible_to == "all" else event.visible_to)
                if parsed.submission is not None:
                    commit(name, parsed.submission)
                    active = True
                    if len(resolved) == len(players):
                        reason = "all_submitted"
                        break
            if reason == "all_submitted":
                break
            if not active and stage != "opening":
                reason = "all_passed"
                break
        if decisions is not None and len(resolved) < len(players):
            pending = {name: decision for name, decision in decisions.items() if name not in resolved}
            for name, choice in match.decide_together(f"bingo_{phase}", pending, record_actions=False).items():
                commit(name, choice)
        match.event("bingo_discussion_end", {**context, "reason": reason})
        match.review_relationships(f"경매 빙고 {round_number}라운드 {stage} 대화 종료")
        return submitted

    plans = None
    for turn, focus in enumerate(PREPARATION_STEPS, 1):
        match.event("bingo_preparation", {"turn": turn, "turns": len(PREPARATION_STEPS)})
        plans = prepare("bingo_preparation", 0, focus, plans)
    match.event("bingo_preparation_end", {"turns": len(PREPARATION_STEPS)})
    discuss("opening", 0, "경기 시작 전 협상입니다. 규칙과 공동 빙고판만 공개되었습니다.")

    for round_number in range(1, ROUNDS + 1):
        match.event("bingo_round", {"round": round_number, "phase": "shape"})
        if not free_submission:
            discuss("before_shape", round_number, f"{round_number}라운드 도형 선택 전입니다. 아직 이번 도형은 제출하지 않았습니다.")
        shape_decisions = {
            name: Decision(
                f"{round_number}/{ROUNDS}라운드. 이번에 입찰할 도형 하나를 선택하세요. "
                "전원 선택 뒤 각자의 도형이 공개되고, 선택 인원을 확인한 뒤 별도로 비공개 입찰합니다. "
                "그 도형의 공급량은 선택한 인원수와 같습니다. 실제 누적 낙찰 결과는 아직 모릅니다.",
                match.policy.choice(SHAPES), options=SHAPES,
            ) for name in players
        }
        if free_submission:
            submitted = discuss("before_shape", round_number,
                                f"{round_number}라운드 전체 도형 공개 전입니다. 원하는 사람은 도형을 먼저 확정할 수 있습니다.",
                                decisions=shape_decisions)
            choices = {name: submitted[name] for name in players}
        else:
            choices = match.decide_together("bingo_shape", shape_decisions)
        counts = {shape: sum(choice == shape for choice in choices.values()) for shape in SHAPES}
        match.event("bingo_shapes", {"round": round_number, "choices": choices, "counts": counts})
        match.review_relationships(f"경매 빙고 {round_number}라운드 도형 선택 공개")
        match.event("bingo_round", {"round": round_number, "phase": "bid"})
        bid_topic = (f"{round_number}라운드 도형 선택 공개 후 입찰 단계입니다. 선택 내역 {encode(choices)}. "
                     "이제 도형은 바꿀 수 없고 입찰액을 논의하거나 먼저 확정할 수 있습니다.")
        if not free_submission:
            discuss("before_bid", round_number,
                    f"{round_number}라운드 도형 선택 공개 후 입찰 전입니다. 선택 내역 {encode(choices)}. "
                    "이제 도형은 바꿀 수 없고 입찰액을 논의할 수 있습니다.")
        match.event("bingo_strategy", {"round": round_number})
        plans = prepare("bingo_strategy", round_number,
                        f"{round_number}라운드 입찰 직전입니다. 확정된 도형 {encode(choices)}를 보고 입찰 계획과 위험을 갱신하세요.", plans)
        decisions = {}
        bids = dict.fromkeys(players, 0)
        for name in players:
            if coin_value(coins[name]) + pieces[name] < 1:
                forced_last.add(name)
                match.event("bingo_forfeit", {"round": round_number, "player": name})
                continue
            default_coin = next((value for value, count in coins[name].items() if count), None)
            default = {"coins": {str(default_coin or 1): 1},
                       "pieces": 0 if default_coin else 1}

            def valid_bid(action, name=name):
                try:
                    parse_bid(action, coins[name], pieces[name])
                except (ValueError, TypeError, RecursionError):
                    return False
                return True

            decisions[name] = Decision(
                f"{round_number}/{ROUNDS}라운드 {SHAPE_NAMES[choices[name]]} 비공개 입찰입니다. "
                f"전체 도형 선택 {encode(choices)}. 내 코인 {encode(coins[name])}, 피스 {pieces[name]}개. "
                "반드시 최소 1원을 내야 하며, 코인 단위를 쪼갤 수 없습니다. 입찰에 사용한 코인은 낙찰에 실패해도 소모됩니다. "
                "피스 1개를 1원 코인 하나로 교환할 수 있습니다. 교환한 코인은 이번 입찰에 쓰거나 남길 수 있습니다. "
                "피스는 교환한 수만큼 소모됩니다. 남은 라운드의 최소 입찰액도 고려하세요. "
                'JSON {"coins":{"1":1,"2":0,"3":0,"5":0,"10":0},"pieces":0}처럼 '
                "coins에는 각 액면 코인의 실제 입찰 사용 개수, pieces에는 1원 코인으로 교환할 피스 수를 출력하세요. "
                "이번에 교환하는 1원 코인도 coins에 포함해 입찰할 수 있습니다. 사용하지 않는 액면은 생략해도 됩니다. "
                f"입찰 직전 내 전략 요약: {plans[name]}",
                encode(default), valid=valid_bid,
            )
        def apply_bid(name, action):
            used, exchanged = parse_bid(action, coins[name], pieces[name])
            coins[name][1] += exchanged
            for value, count in used.items():
                coins[name][value] -= count
            pieces[name] -= exchanged
            spent[name] += exchanged
            bids[name] = coin_value(used)
            if free_submission:
                match.event("bingo_bank", {"round": round_number, "coins": coins[name].copy(),
                                           "pieces": pieces[name], "spent": spent[name]}, actor=name, private=[name])

        if free_submission:
            discuss("before_bid", round_number, bid_topic, decisions=decisions, on_submit=apply_bid)
        else:
            responses = match.decide_together("bingo_bid", decisions)
            for name, action in responses.items():
                apply_bid(name, action)
        for name in players:
            if not free_submission or name not in decisions:
                match.event("bingo_bank", {"round": round_number, "coins": coins[name].copy(),
                                           "pieces": pieces[name], "spent": spent[name]}, actor=name, private=[name])
        settled = settle_round(choices, bids)
        for name, count in settled["awards"].items():
            shapes[name][choices[name]] += count
        history.append({"round": round_number, "choices": choices,
                        **{key: settled[key] for key in ("counts", "prices", "secret")}})
        match.event("bingo_result", {"round": round_number, "counts": counts,
                                     "prices": {shape: None if shape in settled["secret"] else price
                                                for shape, price in settled["prices"].items()},
                                     "secret": settled["secret"]})
        match.review_relationships(f"경매 빙고 {round_number}라운드 낙찰가 발표")

    final = {name: {**optimal_board(shapes[name]), "shapes": shapes[name], "coins": coins[name],
                    "remaining_value": coin_value(coins[name]), "pieces": pieces[name],
                    "forced_last": name in forced_last} for name in players}
    all_ranking = sorted(base_order, key=lambda name: (True, 0, 0, 0) if name in forced_last else (
        False, -final[name]["lines"], -final[name]["filled"], -final[name]["remaining_value"]))
    ranking = [name for name in all_ranking if name != GUEST]
    match.event("bingo_reveal", {"ranking": ranking, "all_ranking": all_ranking,
                                 "players": final, "rounds": history, "guest": GUEST})
    match.review_relationships("경매 빙고 획득 도형·빙고판 공개")
    living, prison = ranking[:2], ranking[2:-1]
    saved = match.decide(
        ranking[0], "alliance", "연맹의 징표로 감옥동에서 생활동으로 옮길 본선 참가자 한 명을 선택하세요.",
        prison[0], options=prison, private=False,
    )
    living.append(saved)
    prison.remove(saved)
    match.review_relationships("경매 빙고 연맹의 징표 사용")
    for name in players:
        if final[name]["filled"] == 9:
            awards[name] = 4
            pieces[name] += 4
    guest_result = {"player": GUEST, "rank": all_ranking.index(GUEST) + 1,
                    "first": all_ranking[0] == GUEST, "full_board": final[GUEST]["filled"] == 9}
    guest_result["prize_won"] = 10_000_000 * (int(guest_result["first"]) + int(guest_result["full_board"]))
    return {
        "rounds": ROUNDS, "ranking": ranking, "all_ranking": all_ranking,
        "scores": {name: result["lines"] for name, result in final.items()},
        "filled": {name: result["filled"] for name, result in final.items()},
        "remaining_value": {name: result["remaining_value"] for name, result in final.items()},
        "shapes": shapes, "boards": {name: result["board"] for name, result in final.items()},
        "coins": coins, "guest": GUEST, "guest_result": guest_result, "forced_last": list(name for name in base_order if name in forced_last),
        "living": living, "prison": prison, "eliminated": ranking[-1:], "alliance_saved": saved,
        "pieces_awarded": awards, "pieces_spent": spent, "pieces": pieces,
    }
