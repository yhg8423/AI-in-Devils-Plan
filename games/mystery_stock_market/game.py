"""Day 2 main match. Orders execute against the exchange at each round's fixed quotes."""

import json
import re

from ..either_or.discussion import Discussion
from ..match import Match, encode
from ..models import Review


STOCKS = ("맛소금융", "무조건설", "방어제철", "알트엔터", "열림보안", "코요테크", "후자전자")
FINANCE, CONSTRUCTION, STEEL, ALT, SECURITY, TECH, ELECTRONICS = range(len(STOCKS))
ALT_PRICES = (
    10000, 10000, 9900, 9500, 8900, 8000, 8500, 8600, 6200, 4300, 6000, 5500,
    4600, 3200, 5000, 3700, 2400, 1300, 1000, 2400, 4800, 3300, 2800, 2400, 2400,
)
REVEAL_ROUNDS = (1, 5, 10, 15, 20)
ROUND_MINUTES = 5
# [round:text] marks characters that become public at that round.
STOCK_RULES = (
    "[20:4개 이상의] [5:주식이] [15:상승할] [5:경우] [10:다음 라운드 +20%], "
    "[20:4개 이상의] [5:주식이] [15:하락할 경우] 다음 [10:라운드 -10%]",
    "[20:방어제철의] 가격이 [10:올랐으면 +10%], [5:그렇지 않으면] [15:-10%]",
    "[20:방어제철의] [5:보유 총량이] [15:증가한 만큼] [10:1주당] -200원, [15:감소한 만큼] [10:1주당] +200원",
    "[5:알트엔터의] [10:주가 변동] [15:그래프는] [20:미스터리 거래소 로고][15:와 일치]한다",
    "[15:후자전자에] [20:시크릿이 걸려] 있으면 [5:+13%], 그렇지 [5:않으면] [10:-1000원]",
    "[5:코요테크의] [15:매수량이] [20:후자전자의] 매수량[15:보다] 많을 경우 [10:+1400원], [5:그렇지 않으면] [10:-700원]",
    "[10:후자전자의] [15:보유 총량이] [20:10주] [5:이상] [20:30주] [5:이하이면] +1500원, [5:그렇지 않으면] [15:-1000원]",
)
RULE_SEGMENT = re.compile(r"\[(\d+):([^]]+)\]")


def stock_hint(rule, round_number):
    next_reveal = next((reveal for reveal in REVEAL_ROUNDS if reveal > round_number), None)

    def reveal_or_mask(segment):
        reveal, text = segment.groups()
        reveal = int(reveal)
        if reveal <= round_number:
            return text
        box = "▧" if reveal == next_reveal else "□"
        return "".join(char if char.isspace() else box for char in text)

    return RULE_SEGMENT.sub(reveal_or_mask, rule)


def next_prices(prices, previous, held, bought, sold, secret, round_number):
    """Mark the next round using this round's flow and the preceding price changes."""
    rises = sum(now > then for now, then in zip(prices, previous, strict=True))
    falls = sum(now < then for now, then in zip(prices, previous, strict=True))
    steel = max(100, prices[STEEL] - 200 * (bought[STEEL] - sold[STEEL]))
    return [max(100, price) for price in (
        prices[FINANCE] * (120 if rises >= 4 else 90 if falls >= 4 else 100) // 100,
        prices[CONSTRUCTION] * (110 if steel > prices[STEEL] else 90) // 100,
        steel,
        ALT_PRICES[round_number],
        prices[SECURITY] * 113 // 100 if ELECTRONICS in secret else prices[SECURITY] - 1000,
        prices[TECH] + (1400 if bought[TECH] > bought[ELECTRONICS] else -700),
        prices[ELECTRONICS] + (1500 if 10 <= held[ELECTRONICS] <= 30 else -1000),
    )]


def trade_orders(action, cash, holdings, prices):
    """Validate and price the whole order list before mutating any balance."""
    return _fill_orders(json.loads(action), cash, holdings, prices)


def _fill_orders(orders, cash, holdings, prices):
    if not isinstance(orders, list):
        raise ValueError("Expected an array of [stock, quantity] orders")
    holdings = holdings.copy()
    for order in orders:
        if not isinstance(order, list) or len(order) != 2:
            raise ValueError("Expected [stock, quantity]")
        stock, quantity = order
        if type(stock) is not int or not 1 <= stock <= len(STOCKS) or type(quantity) is not int or quantity == 0:
            raise ValueError("Invalid stock or quantity")
        index = stock - 1
        cash -= prices[index] * quantity
        holdings[index] += quantity
        if cash < 0 or holdings[index] < 0:
            raise ValueError("Insufficient cash or holdings")
    return orders, cash, holdings


def _scripted_orders(match, cash, holdings, prices, secret):
    available = [i for i in range(len(STOCKS)) if i not in secret]
    stock = match.policy.choice(available) if available else None
    budget = cash // prices[stock] if stock is not None else 0
    orders = [[i + 1, -n] for i, n in enumerate(holdings) if n and i != stock and match.policy.random() < 0.35]
    if budget:
        orders.append([stock + 1, match.policy.randint(1, max(1, budget // 2))])
    return orders


def play(match: Match) -> dict:
    players = match.players
    living_count = len(players) - 8  # One elimination and seven candidates before the alliance choice.
    discussion = Discussion(players, ROUND_MINUTES)
    cash = dict.fromkeys(players, 100_000)
    pieces = match.pieces.copy()
    holdings = {name: [0] * len(STOCKS) for name in players}
    low = cash.copy()
    prices = previous = [10_000] * len(STOCKS)
    bought = sold = [0] * len(STOCKS)
    secret_end = [0] * len(STOCKS)
    used_secret = set()
    previewed = {name: set() for name in players}
    start_rank = {name: index for index, name in enumerate(match.rng.sample(players, len(players)))}

    def wealth(name):
        return cash[name] + sum(count * price for count, price in zip(holdings[name], prices, strict=True))

    def rank():
        return sorted(players, key=lambda name: (-wealth(name), -low[name], start_rank[name]))

    match.event("rules", (
        f"미스터리 거래소 · 참가자 {len(players)}명, 총 24라운드\n\n"
        "1. 시작 자산과 거래\n"
        "참가자마다 가상 현금 100,000원으로 시작합니다. 일곱 종목의 시작가는 각각 10,000원이고, "
        "최저가는 100원입니다. 한 라운드는 가상 시간 5분이며, 매분 각 참가자에게 행동 기회가 한 번 있습니다. "
        "그 시간에 논의실에 가거나 대화하고, 시크릿을 예약하거나 피스를 쓰고, 매수·매도할 수 있습니다. "
        "대화나 이동과 같은 차례에 주문도 낼 수 있습니다. 주문은 현재 가격으로 적은 순서대로 즉시 체결되며, "
        "자기 체결과 잔액, 보유량은 바로 확인합니다. 같은 라운드에서는 가격이 고정됩니다. "
        "같은 종목을 매수했다가 매도하는 자전거래도 가능합니다. 순보유량이 그대로여도 매수량과 매도량은 각각 집계합니다.\n\n"
        "2. 시세와 단서 공개\n"
        "라운드가 바뀌면 종목별 규칙에 따라 주가가 달라집니다. 새 라운드에는 현재 가격, "
        "직전 라운드의 매수·매도 수량, 전체 참가자의 종목별 보유 총량, 자산과 순위를 공개합니다. "
        "각 종목의 가격 규칙 문장은 일부 글자를 가린 채 시작합니다. □는 가려진 한 글자이고 ▧는 다음에 공개될 한 글자입니다. "
        "5·10·15라운드 시작 때 일부를 더 공개하고, 20라운드 시작 때 전부 공개합니다.\n\n"
        "3. 시크릿\n"
        "참가자는 게임 도중 한 번, 한 종목에 시크릿을 예약할 수 있습니다. 예약한 다음 라운드부터 두 라운드 동안 "
        "해당 종목의 시세, 매수·매도 수량, 전체 보유량을 가립니다. 같은 라운드에 여러 사람이 같은 종목에 쓰면 "
        "효과는 한 번 적용되고 각자의 사용권은 모두 소모됩니다. 시크릿이 적용된 라운드에는 참가자 정보 중 "
        "순위만 공개합니다. 시크릿 종목의 주문도 접수하며, 주문 뒤 자기 현금과 보유량을 확인할 수 있습니다.\n\n"
        "4. 피스 사용\n"
        "20라운드가 끝날 때까지 피스를 사용할 수 있습니다. 피스 한 개를 내고 한 종목에서 다음 공개 차례의 단서를 "
        "비공개로 받거나, 시뮬레이터 기준 가상 현금 10,000원으로 바꿀 수 있습니다. 20라운드에는 "
        "단서가 모두 공개되므로 현금 교환을 선택할 수 있습니다.\n\n"
        "5. 최종 순위와 보상\n"
        f"24라운드가 끝나면 현금과 보유 주식의 평가액을 합쳐 순위를 정합니다. 1~{living_count}위는 생활동, "
        f"{living_count + 1}~{len(players) - 1}위는 감옥동 예정이며 최하위 한 명은 탈락합니다. 공동 최하위가 나오면 게임 도중 기록한 "
        "최저 자산이 더 낮은 참가자가 탈락합니다. 1위는 연맹의 징표로 감옥동 예정자 한 명을 생활동으로 옮깁니다. "
        "최종 자산 기준 150만 원 이상은 피스 1개, 300만 원 이상은 2개, 600만 원 이상은 3개를 받습니다. "
        "최종 자산이 1,000만 원 이상인 참가자가 있으면 상금의 징표를 얻습니다."
    ))
    for round_number in range(1, 25):
        level = sum(round_number >= when for when in REVEAL_ROUNDS) - 1
        secret = {i for i, until in enumerate(secret_end) if round_number <= until}
        held = [sum(holdings[name][i] for name in players) for i in range(len(STOCKS))]
        hints = {stock: stock_hint(rule, round_number) for stock, rule in zip(STOCKS, STOCK_RULES, strict=True)}
        if round_number in REVEAL_ROUNDS:
            match.event("hints", hints)
        hint_text = "\n".join(f"{stock} · {hint}" for stock, hint in hints.items())
        match.event("market", {
            "round": round_number, "ranking": rank(),
            "stocks": {stock: None if i in secret else {"price": prices[i], "held": held[i],
                        "bought": bought[i], "sold": sold[i]} for i, stock in enumerate(STOCKS)},
            "assets": None if secret else {name: wealth(name) for name in players},
        })
        bought, sold = [0] * len(STOCKS), [0] * len(STOCKS)
        new_secrets = set()
        ranking = rank()

        def take_turn(name, minute, seat):
            turn = len(match.events)
            can_secret = name not in used_secret and round_number < 24
            piece_options = []
            if round_number <= 20 and pieces[name]:
                piece_options.append("현금")
                if level + 1 < len(REVEAL_ROUNDS):
                    piece_options.extend(f"단서 {stock}" for stock in STOCKS if (level, stock) not in previewed[name])

            def parse(action):
                payload = json.loads(action)
                if not isinstance(payload, dict):
                    raise ValueError("Expected an action object")
                orders = payload.pop("orders", [])
                kind = payload.get("type")
                social = None
                balance = cash[name]
                if kind in ("secret", "piece"):
                    options = (STOCKS if can_secret else ()) if kind == "secret" else piece_options
                    if payload.keys() != {"type", "choice"} or payload["choice"] not in options:
                        raise ValueError("Unavailable secret or piece choice")
                    if kind == "piece" and payload["choice"] == "현금":
                        balance += 10_000
                elif payload != {"type": "trade"}:
                    social = discussion.parse(name, encode(payload), turn, notes=False)
                return payload, social, _fill_orders(orders, balance, holdings[name], prices)

            def valid(action):
                try:
                    parse(action)
                except (ValueError, RecursionError):
                    return False
                return True

            default = {"type": "pass"}
            if minute == 1:
                if can_secret and round_number == 4 + seat:
                    default = {"type": "secret", "choice": STOCKS[ELECTRONICS]}
                else:
                    default = {"type": "trade", "orders": _scripted_orders(match, cash[name], holdings[name], prices, secret)}
            elif piece_options and round_number in (3, 10):
                default = {"type": "piece", "choice": "현금"}
            elif minute == 2 and round_number == 2 and seat % 3 == 0:
                choice = f"단서 {STOCKS[seat % len(STOCKS)]}"
                if choice in piece_options:
                    default = {"type": "piece", "choice": choice}

            quote = {i + 1: [symbol, None if i in secret else prices[i], holdings[name][i]]
                     for i, symbol in enumerate(STOCKS)}
            topic = (
                f"미스터리 거래소 {round_number}/24라운드 · 개장 순위 {ranking.index(name) + 1}/{len(players)}위. "
                f"내 현금 {cash[name]}원, 내 피스 {pieces[name]}개. 종목 [이름, 주문가, 내 수량] {quote}.\n"
                f"공개된 가격 규칙\n{hint_text}\n"
                '주문만 내려면 type을 "trade"로 하고 orders에 [[종목 번호, 수량], ...]을 적으세요. '
                '양수는 매수, 음수는 매도입니다. 같은 종목을 사서 되팔아 양쪽 거래량을 늘릴 수도 있습니다. '
                '대화나 이동 등 다른 행동에도 "orders"를 넣으면 같은 차례에 체결됩니다. '
                "자기 현금·보유량 안에서 주문하며, 다음 차례에도 주문을 추가할 수 있습니다. "
                "단서를 나누거나 매수량을 조율할 상대가 있다면 논의실이나 귓속말을 쓰세요. "
                "주문과 체결은 본인만 확인할 수 있고, 다른 참가자의 약속은 체결을 보장하지 않습니다.\n"
            )
            if can_secret:
                topic += '{"type":"secret","choice":"종목명"}으로 다음 라운드의 시크릿을 예약할 수 있습니다.\n'
            if piece_options:
                topic += f'{{"type":"piece","choice":"선택값"}}의 선택값에 {", ".join(piece_options)} 중 하나를 적으세요.\n'
            request = discussion.request(name, turn, topic, action_index=(minute - 1) * len(players) + seat,
                                         notes=False, progress=f"거래 시간 {minute}/{ROUND_MINUTES}분 차")
            action = match.decide(name, "market_turn", request.content, encode(default), valid=valid,
                                  offer_review=True, request_type=request.msg_type)
            if isinstance(action, Review):
                action = match.decide(name, "market_turn", request.content + "\n" + action.instructions(),
                                      action.draft, valid=valid, request_type=request.msg_type)
            payload, social, (orders, cash[name], holdings[name]) = parse(action)
            if payload["type"] == "secret":
                used_secret.add(name)
                new_secrets.add(STOCKS.index(payload["choice"]))
            elif payload["type"] == "piece":
                pieces[name] -= 1
                if payload["choice"] != "현금":
                    stock = payload["choice"].removeprefix("단서 ")
                    previewed[name].add((level, stock))
                    preview = stock_hint(STOCK_RULES[STOCKS.index(stock)], REVEAL_ROUNDS[level + 1])
                    match.event("preview", f"{stock} · {preview}", private=[name])
            if social is not None:
                for event in discussion.record(name, social, turn):
                    match.event(event.msg_type, event.content, actor=event.agent_name,
                                private=() if event.visible_to == "all" else event.visible_to)
            if orders:
                match.event("trade_fill", {"orders": orders, "cash": cash[name], "holdings": holdings[name]},
                            private=[name], actor=name)
            for stock_number, quantity in orders:
                if quantity > 0:
                    bought[stock_number - 1] += quantity
                else:
                    sold[stock_number - 1] -= quantity

        for minute in range(1, ROUND_MINUTES + 1):
            match.event("market_tick", {"round": round_number, "minute": minute, "minutes": ROUND_MINUTES})
            start = (round_number + minute - 2) % len(players)
            for seat in (*range(start, len(players)), *range(start)):
                take_turn(players[seat], minute, seat)

        held = [sum(holdings[name][i] for name in players) for i in range(len(STOCKS))]
        for i in new_secrets:
            secret_end[i] = round_number + 2
        next_secret = {i for i, until in enumerate(secret_end) if round_number + 1 <= until}
        previous, prices = prices, next_prices(prices, previous, held, bought, sold, next_secret, round_number)
        if round_number < 24:
            low = {name: min(low[name], wealth(name)) for name in players}
        if round_number % 4 == 0:
            match.review_relationships(f"거래소 {round_number}라운드 종료")

    ranking = rank()
    assets = {name: wealth(name) for name in ranking}
    awards = {name: sum(value >= threshold for threshold in (1_500_000, 3_000_000, 6_000_000))
              for name, value in assets.items()}
    living, prison = ranking[:living_count], ranking[living_count:-1]
    saved = match.decide(ranking[0], "alliance", f"최종 자산 {assets}. 생활동으로 옮길 참가자를 고르세요.",
                         prison[0], options=prison, private=False)
    living.append(saved)
    prison.remove(saved)
    return {"ranking": ranking, "assets": assets, "living": living, "prison": prison,
            "eliminated": ranking[-1:], "alliance_saved": saved, "pieces_awarded": awards,
            "pieces": {name: pieces[name] + awards[name] for name in players},
            "prize_token": max(assets.values()) >= 10_000_000, "rounds": 24}
