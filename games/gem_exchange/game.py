"""Day 3 Gem Black Market, with hidden cards and directed Manito scoring."""

from collections import Counter
import json

from ..either_or.discussion import Discussion
from ..match import Decision, Match, encode


ROUNDS = 3
BUYERS = ("buyer1", "buyer2", "buyer3")
TABLE = (*BUYERS, "trash")
CARDS = tuple(
    {"kind": kind, "value": value}
    for kind, values in (
        ("diamond", (5, 6)), ("gold", (4, 5)), ("silver", (2, 3, 4)),
        ("copper", (1, 1, 2, 2)), ("bomb", (-6, -4)),
    )
    for value in values
)
PASS = '{"type":"pass"}'


def round_points(cards):
    demand = Counter(cards[slot]["kind"] for slot in BUYERS)
    return {
        name: card["value"] if card["kind"] == "bomb" else card["value"] * demand[card["kind"]]
        for name, card in cards.items() if name not in TABLE
    }


def auction(match, base_order, pieces):
    """Only the winner pays. A rebid replaces the bidder's total commitment."""
    bidders = list(base_order)
    highest = -1
    round_number = 0
    resolution = "bid"
    while len(bidders) > 1:
        round_number += 1
        match.event("gem_auction_round", {"round": round_number, "bidders": bidders, "minimum": highest + 1})
        decisions = {}
        for name in bidders:
            amounts = tuple(str(value) for value in range(highest + 1, pieces[name] + 1))
            options = amounts if highest < 0 else ("pass", *amounts)
            decisions[name] = Decision(
                f"1라운드 선을 정하는 비공개 피스 경매입니다. 기본 순서 {encode(base_order)}. "
                f"내 피스 {pieces[name]}개. 현재 최고 입찰 {max(0, highest)}개. "
                "입찰액은 총 지불할 피스 수입니다. 낙찰자만 지불하고 다른 참가자의 피스는 반환됩니다. "
                "재경매에서는 이전 최고액보다 높게 입찰하거나 pass로 기존 입찰을 유지하세요.",
                match.policy.choice(options), options=options,
            )
        responses = match.decide_together("gem_bid", decisions)
        raised = {name: int(value) for name, value in responses.items() if value != "pass"}
        if not raised:
            break
        highest = max(raised.values())
        bidders = [name for name in bidders if raised.get(name) == highest]
        if not any(pieces[name] > highest for name in bidders):
            break

    if len(bidders) > 1:
        votes = match.decide_together("gem_auction_agreement", {
            name: Decision(
                f"최고 {highest}피스 입찰이 동률이며 재경매가 끝났습니다. 동률 참가자 {encode(bidders)} 중 "
                "선을 맡을 사람을 합의하세요. 모두 같은 사람을 고르면 그 사람이 낙찰받습니다. "
                "합의가 성립하지 않으면 시뮬레이터는 기본 순서가 앞선 동률 참가자를 선택합니다.",
                bidders[0], options=bidders,
            ) for name in bidders
        })
        agreed = set(votes.values())
        leader = next(iter(agreed)) if len(agreed) == 1 else bidders[0]
        resolution = "agreement" if len(agreed) == 1 else "base_order"
    else:
        leader = bidders[0]
    pieces[leader] -= highest
    offset = base_order.index(leader)
    match.event("gem_auction", {
        "leader": leader, "bid": highest, "order": base_order[offset:] + base_order[:offset],
        "pieces": pieces.copy(), "resolution": resolution,
    })
    return leader, highest


def play(match: Match) -> dict:
    players = match.players
    if len(players) not in (9, 10) or set(players) & set(TABLE):
        raise ValueError("보석 암시장은 9명 또는 10명이 필요하며 buyer1~3과 trash는 참가자 ID로 쓸 수 없습니다.")
    base_order = match.rng.sample(list(players), len(players))
    manito_order = match.rng.sample(list(players), len(players))
    manitos = dict(zip(manito_order, manito_order[1:] + manito_order[:1], strict=True))
    scores = dict.fromkeys(players, 0)
    pieces = match.pieces.copy()
    awards = dict.fromkeys(players, 0)
    spent = dict.fromkeys(players, 0)
    peeked = set()
    discussion = Discussion(players, ROUNDS * 2 * len(players))
    deck = list(CARDS)
    if len(players) == 10:
        deck.append({"kind": "copper", "value": 1})

    match.event("rules", (
        f"보석 암시장 · 참가자 {len(players)}명 · 3라운드\n\n"
        "1. 카드와 선 경매\n"
        "다이아몬드 5·6, 금 4·5, 은 2·3·4, 동 1·1·2·2, 폭탄 -6·-4의 13장을 사용합니다. "
        "10인 연속 실행에서는 동 1 카드 한 장을 추가해 14장을 사용합니다. "
        "기본 순서를 추첨하고 비공개 피스 경매의 최고 입찰자가 1라운드 선이 됩니다. 낙찰자만 피스를 냅니다. "
        "동률자는 총 입찰액을 올려 재경매하며, 더 올리지 않으면 선을 합의합니다. 합의 불발 시 기본 순서를 따릅니다. "
        "선부터 기본 순서대로 각자 한 장, 구매자 세 칸과 휴지통에 한 장씩 뒷면으로 배분합니다. "
        "처음에는 자기 카드를 확인하고, 그 뒤에는 자기 차례에만 자기 카드를 확인할 수 있습니다.\n\n"
        "2. 교환과 정보\n"
        "매 라운드 정순으로 한 번, 역순으로 한 번씩 반드시 카드를 교환합니다. 선은 처음과 마지막에 행동합니다. "
        "다른 참가자, 구매자 한 칸 또는 휴지통과 맞바꿉니다. 폭탄을 가진 사람은 다른 참가자와만 교환합니다. "
        "다른 사람이 내 폭탄을 가져가면 나는 즉시 3점을 받고, 내가 직접 넘기면 보너스가 없습니다. "
        "게임 전체에서 한 번만 피스 하나를 내고 구매자 한 칸 또는 휴지통을 비공개로 확인할 수 있습니다. "
        "교환 제한 시간 3분은 전원에게 순서대로 대화 기회를 한 번씩 주는 것으로 진행합니다. "
        "대화 중에도 유료 확인을 선택할 수 있고, 교환자는 자기 차례에 유료 확인할 기회를 별도로 받습니다. "
        "전체 발언·같은 장소의 귓속말·논의실 대화를 할 수 있으며 약속은 교환을 구속하지 않습니다.\n\n"
        "3. 라운드 정산\n"
        "두 차례 교환 후 모든 카드를 공개합니다. 자기 보석과 같은 종류의 구매자 카드 수에 자기 카드 숫자를 곱해 "
        "승점을 얻습니다. 다이아몬드로 점수를 얻으면 피스 하나도 받습니다. 폭탄은 적힌 음수만큼 감점합니다. "
        "누적 승점을 공개하고 -6 폭탄 보유자, 없으면 -4 폭탄 보유자, 둘 다 없으면 기존 선이 다음 선입니다.\n\n"
        "4. 마니또와 최종 결과\n"
        "마니또 관계는 추첨한 한 방향의 고리입니다. 내가 점수에 영향을 주는 상대만 비공개로 확인합니다. "
        "내 점수에 영향을 주는 상대는 종료할 때 공개합니다. 3라운드 뒤 내 누적 승점과 나에게 영향을 주는 "
        "마니또의 누적 승점을 곱해 최종 승점을 정합니다. 동점은 시뮬레이터의 기본 순서로 판정합니다. "
        "상위 3명은 생활동, 최하위 한 명은 탈락, 나머지는 감옥동입니다. 1위는 연맹의 징표로 감옥동 한 명을 "
        "생활동으로 옮깁니다. 최종 승점이 1점 이상이면 피스 1개, 10점 이상이면 총 2개를 받습니다."
    ))
    match.event("gem_setup", {"base_order": base_order, "pieces": pieces.copy(), "rounds": ROUNDS, "card_count": len(deck)})
    for name in players:
        match.event("gem_manito", {"beneficiary": manitos[name]}, actor=name, private=[name])
    leader, bid = auction(match, base_order, pieces)
    spent[leader] += bid

    def peek(name, slot, round_number, cards):
        pieces[name] -= 1
        spent[name] += 1
        peeked.add(name)
        match.event("gem_piece", {"player": name, "pieces": pieces[name], "reason": "peek"})
        match.event("gem_peek", {"round": round_number, "slot": slot, "card": cards[slot]},
                    actor=name, private=[name])

    def talk(name, acting, round_number, pass_number, cards):
        turn = len(match.events)
        can_peek = name not in peeked and pieces[name] > 0

        def parse(action):
            payload = json.loads(action)
            if isinstance(payload, dict) and payload.get("type") == "peek":
                if payload.keys() != {"type", "slot"} or not can_peek or payload["slot"] not in TABLE:
                    raise ValueError("유료 확인을 사용할 수 없습니다.")
                return payload["slot"]
            return discussion.parse(name, action, turn, notes=False)

        def valid(action):
            try:
                parse(action)
            except (ValueError, TypeError, RecursionError):
                return False
            return True

        request = discussion.request(
            name, turn,
            f"{round_number}라운드 {pass_number}차 교환 전 대화입니다. 이번 교환자는 {acting}입니다. "
            f"공개 누적 승점 {encode(scores)}. 내 피스 {pieces[name]}. "
            '전체 발언은 {"type":"speak","channel":"public","text":"발언"}, '
            '귓속말은 {"type":"speak","channel":"whisper","to":"같은 장소의 상대 ID","text":"발언"}, '
            '논의실 이동은 {"type":"move","room":1}, '
            '논의실 발언은 {"type":"speak","channel":"room","text":"발언"}, '
            f"패스는 {PASS}입니다. "
            + ('유료 확인도 가능합니다. {"type":"peek","slot":"buyer1"}처럼 buyer1~3 또는 trash를 지정하세요.'
               if can_peek else "유료 확인은 사용할 수 없습니다."),
            action_index=((round_number - 1) * 2 + pass_number - 1) * len(players) ** 2,
            notes=False,
        )
        action = match.decide(name, "gem_talk", request.content, PASS, valid=valid, request_type=request.msg_type)
        decision = parse(action)
        if isinstance(decision, str):
            peek(name, decision, round_number, cards)
        elif decision is not None:
            for event in discussion.record(name, decision, turn):
                match.event(event.msg_type, event.content, actor=event.agent_name,
                            private=() if event.visible_to == "all" else event.visible_to)

    for round_number in range(1, ROUNDS + 1):
        offset = base_order.index(leader)
        order = base_order[offset:] + base_order[:offset]
        dealt = match.rng.sample(deck, len(deck))
        cards = dict(zip((*order, *TABLE), dealt, strict=True))
        match.event("gem_round", {"round": round_number, "leader": leader, "order": order})
        for name in order:
            match.event("gem_card", {"round": round_number, "slot": name, "card": cards[name]},
                        actor=name, private=[name])

        for pass_number, turn_order in enumerate((order, list(reversed(order))), 1):
            for name in turn_order:
                match.event("gem_turn", {"round": round_number, "pass": pass_number, "player": name})
                match.event("gem_card", {"round": round_number, "slot": name, "card": cards[name]},
                            actor=name, private=[name])
                for speaker in (*[player for player in order if player != name], name):
                    if speaker in match.backends and match.live_turns > 0:
                        talk(speaker, name, round_number, pass_number, cards)
                if name not in peeked and pieces[name] > 0:
                    slot = match.decide(
                        name, "gem_peek",
                        f"내 카드 {encode(cards[name])}. 내 피스 {pieces[name]}. 게임 전체에서 한 번만 피스 하나로 "
                        "구매자 한 칸 또는 휴지통을 확인할 수 있습니다. 확인할 위치나 pass를 고르세요.",
                        "pass", options=("pass", *TABLE),
                    )
                    if slot != "pass":
                        peek(name, slot, round_number, cards)
                targets = tuple(player for player in players if player != name)
                if cards[name]["kind"] != "bomb":
                    targets += TABLE
                target = match.decide(
                    name, "gem_swap",
                    f"{round_number}라운드 {pass_number}차 교환. 교환 순서 {encode(turn_order)}. "
                    f"내 현재 카드 {encode(cards[name])}. 공개 누적 승점 {encode(scores)}. "
                    f"나는 {manitos[name]}의 최종 승점에 영향을 줍니다. "
                    "확인한 정보와 지금까지의 교환 기록을 바탕으로 반드시 한 곳과 교환하세요. "
                    "폭탄은 다른 참가자에게만 넘길 수 있습니다. 이번 교환 뒤 카드도 확인할 수 있습니다.",
                    match.policy.choice(targets), options=targets,
                )
                passive_bomb = target in scores and cards[target]["kind"] == "bomb"
                cards[name], cards[target] = cards[target], cards[name]
                match.event("gem_swap", {"round": round_number, "pass": pass_number, "player": name, "target": target})
                if passive_bomb:
                    scores[target] += 3
                    match.event("gem_bonus", {"round": round_number, "player": target, "points": 3, "scores": scores.copy()})
                match.event("gem_card", {"round": round_number, "slot": name, "card": cards[name]},
                            actor=name, private=[name])

        points = round_points(cards)
        for name in players:
            scores[name] += points[name]
            if cards[name]["kind"] == "diamond" and points[name] > 0:
                pieces[name] += 1
                awards[name] += 1
                match.event("gem_piece", {"player": name, "pieces": pieces[name], "reason": "diamond"})
        bombs = [name for name in players if cards[name]["kind"] == "bomb"]
        if bombs:
            leader = min(bombs, key=lambda name: cards[name]["value"])
        match.event("gem_reveal", {
            "round": round_number, "cards": cards.copy(), "points": points, "scores": scores.copy(),
            "pieces": pieces.copy(), "next_leader": leader,
        })
        match.review_relationships(f"보석 암시장 {round_number}라운드 종료")

    final_scores = {beneficiary: scores[beneficiary] * scores[source] for source, beneficiary in manitos.items()}
    ranking = sorted(base_order, key=lambda name: -final_scores[name])
    match.event("gem_final", {"manitos": manitos, "scores": scores, "final_scores": final_scores})
    living, prison = ranking[:3], ranking[3:-1]
    saved = match.decide(
        ranking[0], "alliance", f"최종 승점 {encode(final_scores)}. 연맹의 징표로 생활동으로 옮길 참가자를 고르세요.",
        prison[0], options=prison, private=False,
    )
    living.append(saved)
    prison.remove(saved)
    for name in players:
        reward = int(final_scores[name] >= 1) + int(final_scores[name] >= 10)
        pieces[name] += reward
        awards[name] += reward
    return {
        "rounds": ROUNDS, "ranking": ranking, "scores": final_scores, "raw_scores": scores,
        "manitos": manitos, "living": living, "prison": prison, "eliminated": ranking[-1:],
        "alliance_saved": saved, "pieces_awarded": awards, "pieces_spent": spent, "pieces": pieces,
    }
