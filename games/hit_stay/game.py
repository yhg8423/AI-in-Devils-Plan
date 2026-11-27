"""Changing-limit card betting with an effective-stack cap and private hands.

Rules: https://namu.moe/w/데블스%20플랜:%20데드%20어게인/6일차
The cap excludes folded players, as supported by the broadcast's first all-in.
Common short-stack antes and tied-first-bust card overtime are simulator policy.
"""

import json

from ..either_or.discussion import Discussion
from ..match import Decision, Match, encode


DECK_COUNTS = {7: 1, 6: 2, 5: 3, 4: 4, 3: 5, 2: 6, 1: 7, -1: 7}
DECK = tuple(value for value, count in DECK_COUNTS.items() for _ in range(count))
OPENING_TURNS = 10
TIE_POLICY = "Only simultaneous first-bust players play chip-free card rounds; only tied lowest replay."
CAP_POLICY = "Minimum round contribution plus remaining chips among players who have not folded."
RULES = """HIT, STAY · 4~5인 준결승 메인 매치

각자 기본 30칩을 받고 기존 피스를 전부 1:1로 바꿉니다. 양도·카드 교환은 없습니다.
시작 전 대화는 각자 10턴입니다. 모두 비공개로 공공/개인 이익을 고릅니다.
과반수가 공공을 고르면 상금의 징표 1개가 추가됩니다. 개인 선택자는 결과와 무관하게 10칩을 받습니다.
첫 선을 추첨하고 다음 라운드부터 시계 방향의 다음 생존자가 선을 맡습니다.

카드는 7 1장, 6 2장, 5 3장, 4 4장, 3 5장, 2 6장, 1 7장, -1 7장, 총35장입니다.
매 라운드 기본 베팅 1칩을 내고, 10라운드가 끝날 때마다 기본 베팅이 1칩 증가합니다.
기본 베팅 다음 5~12 주사위로 한계를 정하고, 전체 덱을 새로 섞어 3장씩 비공개로 받습니다.
각자 공개할 카드 한 장을 먼저 확정한 뒤 모두 함께 공개합니다. 나머지 두 장은 본인만 봅니다.

선부터 1차 베팅: call/raise/fold. raise의 total은 기본 베팅을 포함해 이번 라운드에 낼 누적 총액입니다.
포기하지 않은 사람 중 (이미 낸 칩+남은 칩)이 가장 적은 사람까지만 베팅할 수 있습니다.
포기자는 상한에서 제외하며, 이미 낸 칩을 돌려받지 못합니다. 사이드 팟은 만들지 않습니다.
상대가 아직 올리지 않았어도 포기할 수 있고, 추가 지불 없는 call은 체크입니다.
모든 비포기자가 같은 액수를 내고 응답을 마치면 선부터 HIT/STAY를 반복합니다.
HIT은 공개 카드 한 장을 추가하고 STAY는 더 받지 않습니다. 한계를 넘어도 -1로 회복할 수 있습니다.
모두 STAY하거나 덱이 소진되면 2차 베팅을 합니다. 올인 상한에 닿으면 추가 베팅을 생략합니다.
한 명만 포기하지 않고 남으면 패를 공개하지 않고 즉시 팟을 받습니다.

쇼다운에서는 비포기자의 전체 패만 공개합니다. 한계를 넘지 않은 최대 합이 승리합니다.
같은 합이면 카드가 많은 사람이 승리하고, 카드 수도 같거나 전원 초과면 무승부입니다.
팟을 동점자끼리 균등 분배하고 남는 칩은 선부터 시계 방향으로 한 개씩 배분합니다.
정산 후 처음 칩이 0이 된 한 사람은 영구 탈락하고, 이후 소진자는 감옥 매치로 갑니다.
칩 보유자 한 명이 남을 때까지 계속하며 그 사람이 결승에 직행합니다.

시뮬레이터 정책: 최소 스택이 기본 베팅보다 적으면 모두가 같은 최소 스택만 냅니다.
동시에 처음 0칩이 된 사람이 여럿이면 해당자끼리만 칩 없는 카드 연장을 합니다.
새 덱·새 한계·같은 공개/HIT/STAY 규칙으로 겨루고, 최하위 동점자만 반복해 유일 최하위를 탈락시킵니다.
연장은 칩·피스·추가 상금을 만들지 않습니다. 별도 제비뽑기로 최하위를 정하지 않습니다.
고정 최대 라운드나 강제 승자는 없습니다. 모델 예산이 끝나면 같은 규칙의 스크립트 선택으로 계속합니다.
"""


def ante_for(round_number):
    if type(round_number) is not int or round_number < 1:
        raise ValueError("라운드는 양의 정수여야 합니다.")
    return 1 + (round_number - 1) // 10


def hand_rank(cards, limit):
    value = sum(cards)
    return (1, value, len(cards)) if value <= limit else (0, 0, 0)


def settle_round(hands, limit, pot, order):
    """Settle only the remaining players; all busted hands tie regardless of sum."""
    if not hands or type(pot) is not int or pot < 0 or set(hands) - set(order):
        raise ValueError("유효한 비포기자 패와 0 이상의 팟이 필요합니다.")
    ranks = {name: hand_rank(cards, limit) for name, cards in hands.items()}
    best = max(ranks.values())
    winners = [name for name in order if ranks.get(name) == best]
    share, remainder = divmod(pot, len(winners))
    payouts = {name: share + (index < remainder) for index, name in enumerate(winners)}
    reason = "all_bust" if best[0] == 0 else "tie" if len(winners) > 1 else "best_hand"
    return {"winners": winners, "payouts": payouts, "reason": reason,
            "sums": {name: sum(cards) for name, cards in hands.items()},
            "counts": {name: len(cards) for name, cards in hands.items()}}


def effective_cap(chips, contributions, players):
    return min(chips[name] + contributions[name] for name in players)


def parse_bet(text, current, cap):
    action = json.loads(text)
    if action in ({"type": "call"}, {"type": "fold"}):
        return action
    if (not isinstance(action, dict) or set(action) != {"type", "total"}
            or action["type"] != "raise" or type(action["total"]) is not int
            or not current < action["total"] <= cap):
        raise ValueError("call/fold 또는 현재 베팅보다 크고 상한 이내인 정수 total raise가 필요합니다.")
    return action


def opening_discussion(match, players):
    discussion = Discussion(players, OPENING_TURNS)
    context = {"stage": "opening", "round": 0, "tiebreak": 0, "rounds": OPENING_TURNS}
    match.event("hit_discussion", context)
    topic = (
        "HIT, STAY 시작 전 협상입니다. 공공/개인 이익 선택과 생존 전략을 논의하세요. "
        "피스와 칩의 양도, 카드 교환은 불가능하며 약속은 이후 선택을 구속하지 않습니다. "
        '발언 {"type":"speak","channel":"public","text":"발언"}, '
        '같은 장소 귓속말은 channel:"whisper", to에 ID 또는 ID 배열을 씁니다. '
        '이동 {"type":"move","room":1}, 복도는 room:0. 방 발언은 channel:"room". '
        '초대는 channel:"room_invite"와 room/to/text, '
        '응답은 {"type":"respond_invite","invite_id":0,"decision":"accept"}. '
        '패스 {"type":"pass"}.'
    )
    for current in range(1, OPENING_TURNS + 1):
        match.event("hit_discussion_round", {**context, "turn": current})
        for seat, name in enumerate(players):
            turn = len(match.events)
            request = discussion.request(name, turn, topic, notes=False,
                                         action_index=(current - 1) * len(players) + seat)
            def valid(text):
                try:
                    discussion.parse(name, text, turn, notes=False)
                    return True
                except (ValueError, TypeError, RecursionError):
                    return False
            action = match.decide(name, "hit_discussion", request.content, '{"type":"pass"}',
                                  valid=valid, request_type=request.msg_type)
            parsed = discussion.parse(name, action, turn, notes=False)
            if parsed is not None:
                for event in discussion.record(name, parsed, turn):
                    match.event(event.msg_type, event.content, actor=event.agent_name,
                                private=() if event.visible_to == "all" else event.visible_to)
    discussion.clear()
    match.event("hit_discussion_end", {**context, "reason": "limit"})


class Round:
    def __init__(self, match, players, chips, first, number, *, tiebreak=0):
        self.match, self.players, self.chips = match, list(players), chips
        start = self.players.index(first)
        self.order = self.players[start:] + self.players[:start]
        self.context = {"round": number, "tiebreak": tiebreak, "first": first, "players": self.players.copy()}
        self.limit = match.rng.randrange(5, 13)
        self.context["limit"] = self.limit
        self.deck = list(DECK)
        match.rng.shuffle(self.deck)
        self.folded, self.stayed = set(), set()
        self.public_cards = {name: [] for name in self.players}
        self.hands = {}
        scheduled = ante_for(number) if not tiebreak else 0
        # A common capped ante preserves the no-side-pot rule for short stacks.
        ante = min(scheduled, min(chips[name] for name in players))
        self.contributions = dict.fromkeys(self.players, ante)
        for name in players:
            chips[name] -= ante
        self.pot = ante * len(players)
        self.event("hit_round", {"ante": ante, "scheduled_ante": scheduled, "pot": self.pot,
                                 "chips": chips.copy(), "contributions": self.contributions.copy(),
                                 "deck_remaining": len(self.deck)})
        for name in self.order:
            self.hands[name] = [self.deck.pop() for _ in range(3)]
            self.event("hit_hand", {"player": name, "cards": self.hands[name].copy()}, private=[name])
        decisions = {
            name: Decision("기본 카드 3장 중 전체에 공개할 한 장의 인덱스 0/1/2를 고르세요. "
                           "다른 참가자의 이번 공개 선택은 아직 보이지 않습니다. "
                           + self.prompt(name), str(sorted(range(3), key=self.hands[name].__getitem__)[1]),
                           options=("0", "1", "2")) for name in self.order
        }
        reveals = match.decide_together("hit_reveal", decisions, max_reviews=0)
        for name in self.order:
            self.public_cards[name].append(self.hands[name][int(reveals[name])])
        self.event("hit_reveal", {"cards": {name: cards[0] for name, cards in self.public_cards.items()},
                                  "hidden_counts": dict.fromkeys(self.players, 2), "deck_remaining": len(self.deck)})

    @property
    def remaining(self):
        return [name for name in self.order if name not in self.folded]

    def event(self, kind, data, **kwargs):
        self.match.event(kind, {**self.context, **data}, **kwargs)

    def snapshot(self):
        return {"pot": self.pot, "chips": self.chips.copy(), "contributions": self.contributions.copy(),
                "public_cards": {name: cards.copy() for name, cards in self.public_cards.items()},
                "hand_counts": {name: len(cards) for name, cards in self.hands.items()},
                "folded": [name for name in self.order if name in self.folded],
                "stayed": [name for name in self.order if name in self.stayed], "deck_remaining": len(self.deck)}

    def prompt(self, name):
        return "공개 상태 " + encode({**self.context, **self.snapshot()}) + "\n내 비공개 포함 전체 패 " + encode(self.hands[name])

    def betting(self, phase):
        pending = set(self.remaining)
        while pending and len(self.remaining) > 1:
            for name in self.order:
                if name not in pending or name in self.folded:
                    continue
                players = self.remaining
                current = max(self.contributions[player] for player in players)
                cap = effective_cap(self.chips, self.contributions, players)
                if current == cap and all(self.contributions[player] == current for player in players):
                    return
                self.event("hit_turn", {**self.snapshot(), "phase": phase, "player": name,
                                        "current_total": current, "cap": cap})
                def valid(text):
                    try:
                        parse_bet(text, current, cap)
                        return True
                    except (ValueError, TypeError, RecursionError):
                        return False
                text = self.match.decide(name, f"hit_{phase}", self.prompt(name)
                    + f"\n현재 누적액 {current}, 상한 {cap}. call은 차액만 지급, fold는 라운드 포기. "
                    + 'raise는 {"type":"raise","total":정수}로 ante 포함 라운드 누적 목표액을 제출하세요. '
                    + '그 외 {"type":"call"}, {"type":"fold"}.', '{"type":"call"}', valid=valid)
                action = parse_bet(text, current, cap)
                paid = 0
                if action["type"] == "fold":
                    self.folded.add(name)
                else:
                    total = action.get("total", current)
                    paid = total - self.contributions[name]
                    self.chips[name] -= paid
                    self.contributions[name] = total
                    self.pot += paid
                    if action["type"] == "raise":
                        pending = set(self.remaining)
                pending.discard(name)
                self.event("hit_bet", {**self.snapshot(), "phase": phase, "player": name,
                                       "type": action["type"], "paid": paid, "total": self.contributions[name],
                                       "cap": effective_cap(self.chips, self.contributions, self.remaining)})
                if len(self.remaining) == 1:
                    return

    def draw_cards(self):
        while self.deck and any(name not in self.stayed for name in self.remaining):
            for name in self.remaining:
                if name in self.stayed or not self.deck:
                    continue
                self.event("hit_turn", {**self.snapshot(), "phase": "hit_stay", "player": name,
                                        "current_total": max(self.contributions.values()),
                                        "cap": effective_cap(self.chips, self.contributions, self.remaining)})
                total = sum(self.hands[name])
                recoverable = self.limit < total <= self.limit + 2
                default = "HIT" if total <= self.limit - 3 or recoverable else "STAY"
                action = self.match.decide(name, "hit_draw", self.prompt(name)
                    + "\nHIT으로 공개 카드 한 장을 더 받거나 STAY로 추가 패를 끝내세요. 초과해도 HIT 가능합니다.",
                    default, options=("HIT", "STAY"))
                value = None
                if action == "STAY":
                    self.stayed.add(name)
                else:
                    value = self.deck.pop()
                    self.hands[name].append(value)
                    self.public_cards[name].append(value)
                self.event("hit_card", {**self.snapshot(), "player": name, "type": action,
                                        "value": value, "count": len(self.hands[name])})

    def play(self):
        if not self.context["tiebreak"]:
            self.betting("bet1")
        if len(self.remaining) > 1:
            self.draw_cards()
            if not self.context["tiebreak"]:
                self.betting("bet2")
        hands = {name: self.hands[name].copy() for name in self.remaining}
        if len(hands) == 1:
            winner, = hands
            settlement = {"winners": [winner], "payouts": {winner: self.pot}, "reason": "uncontested",
                          "sums": {}, "counts": {}}
            revealed = {}
        else:
            settlement = settle_round(hands, self.limit, self.pot, self.order)
            revealed = hands
        pot = self.pot
        for name, amount in settlement["payouts"].items():
            self.chips[name] += amount
        self.pot = 0
        self.event("hit_showdown", {**settlement, "hands": revealed, "pot": pot, "remaining_pot": 0,
                                    "chips": self.chips.copy()})
        return hands


def first_bust_loser(match, candidates, chips, seats, first, number):
    """Only tied lowest replay; fresh cards decide play, never an extra draw of lots."""
    active, overtime = list(candidates), 0
    while len(active) > 1:
        overtime += 1
        ordered = [name for name in seats if name in active]
        start = seats.index(first)
        leader = next(name for name in seats[start:] + seats[:start] if name in active)
        match.event("hit_tiebreak", {"round": number, "tiebreak": overtime, "stage": "start",
                                      "candidates": active.copy(), "lowest": [], "safe": [], "policy": TIE_POLICY})
        contest = Round(match, ordered, chips, leader, number, tiebreak=overtime)
        hands = contest.play()
        lowest_rank = min(hand_rank(cards, contest.limit) for cards in hands.values())
        lowest = [name for name in contest.order if hand_rank(hands[name], contest.limit) == lowest_rank]
        match.event("hit_tiebreak", {"round": number, "tiebreak": overtime, "stage": "result",
                                      "candidates": active.copy(), "lowest": lowest.copy(),
                                      "safe": [name for name in active if name not in lowest]})
        active = lowest
    return active[0]


def play(match: Match):
    players = list(match.players)
    if len(players) not in (4, 5) or len(set(players)) != len(players):
        raise ValueError("HIT, STAY에는 서로 다른 4~5명이 필요합니다.")
    if any(type(match.pieces[name]) is not int or match.pieces[name] < 0 for name in players):
        raise ValueError("시작 피스는 0 이상의 정수여야 합니다.")
    seats = match.rng.sample(players, len(players))
    pieces = match.pieces.copy()
    chips = {name: 30 + pieces[name] for name in players}
    match.pieces = dict.fromkeys(players, 0)
    match.event("rules", RULES)
    match.event("hit_setup", {"version": 1, "players": players, "seats": seats.copy(),
                              "deck_counts": DECK_COUNTS, "initial_chips": chips.copy(), "pieces_spent": pieces,
                              "opening_turns": OPENING_TURNS, "cap_policy": CAP_POLICY, "tie_policy": TIE_POLICY})
    opening_discussion(match, seats)
    match.review_relationships("HIT, STAY 시작 전 대화 종료")
    choices = match.decide_together("hit_interest", {
        name: Decision("공공 이익: 과반수 선택 시 상금의 징표 1개. 개인 이익: 결과와 무관하게 내 칩 +10. "
                       "모두 같은 정보로 비공개 확정한 뒤 공개합니다.", "personal", options=("public", "personal"))
        for name in seats
    }, max_reviews=0)
    bonuses = {name: 10 if choices[name] == "personal" else 0 for name in players}
    for name in players:
        chips[name] += bonuses[name]
    public_count = sum(choice == "public" for choice in choices.values())
    prize_token = public_count > len(players) // 2
    match.event("hit_interest", {"choices": choices, "threshold": len(players) // 2 + 1,
                                 "public_count": public_count, "bonuses": bonuses,
                                 "prize_token": prize_token, "chips": chips.copy()})
    match.review_relationships("HIT, STAY 이익 선택 공개")
    first, rounds, eliminated, out_groups, tiebreaks = seats[0], 0, [], [], []
    while sum(chips[name] > 0 for name in players) > 1:
        rounds += 1
        active = [name for name in seats if chips[name] > 0]
        table = Round(match, active, chips, first, rounds)
        table.play()
        zero = [name for name in table.order if chips[name] == 0]
        if zero:
            if not eliminated:
                loser = zero[0] if len(zero) == 1 else first_bust_loser(match, zero, chips, seats, first, rounds)
                eliminated = [loser]
                out_groups.append([loser])
                if len(zero) > 1:
                    tiebreaks.append({"round": rounds, "candidates": zero.copy(), "eliminated": loser})
                others = [name for name in zero if name != loser]
                if others:
                    out_groups.append(others)
            else:
                out_groups.append(zero)
            match.event("hit_bust", {"round": rounds, "tiebreak": 0, "zero": zero,
                                    "eliminated": eliminated.copy(),
                                    "prison": [name for group in out_groups for name in group if name not in eliminated],
                                    "chips": chips.copy()})
        match.review_relationships(f"HIT, STAY {rounds}라운드 정산")
        start = seats.index(first)
        first = next(name for name in seats[start + 1:] + seats[:start + 1] if chips[name] > 0)
    winner = next(name for name in players if chips[name] > 0)
    groups = [[winner], *reversed(out_groups)]
    ranking = [name for group in groups for name in group]
    result = {"ranking": ranking, "ranking_groups": groups, "living": [winner], "finalists": [winner],
              "prison": ranking[1:-1], "eliminated": eliminated, "pieces": dict.fromkeys(players, 0),
              "pieces_spent": pieces, "chips": chips.copy(), "prize_token": prize_token,
              "interest": choices, "rounds": rounds, "tiebreaks": tiebreaks}
    match.event("hit_final", result)
    return result
