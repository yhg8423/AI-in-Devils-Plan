"""Memory poker hand ranking, duels, and the Either/Or elimination stage."""

from collections import Counter, deque
from itertools import combinations

from ..match import Decision


SUITS = "♠♥♦♣"
RANKS = "23456789TJQKA"
DECK = tuple((rank, suit) for rank in range(2, 15) for suit in SUITS)


def hand_rank(cards):
    ranks = [rank for rank, _ in cards]
    counts = Counter(ranks)
    groups = sorted(((count, rank) for rank, count in counts.items()), reverse=True)
    flush = len({suit for _, suit in cards}) == 1
    straight = 0
    if len(counts) == 5:
        if max(ranks) - min(ranks) == 4:
            straight = max(ranks)
        elif set(ranks) == {14, 2, 3, 4, 5}:
            straight = 5
    if straight and flush:
        return 8, straight
    patterns = {(4, 1): 7, (3, 2): 6, (3, 1, 1): 3, (2, 2, 1): 2, (2, 1, 1, 1): 1}
    if flush:
        return 5, *sorted(ranks, reverse=True)
    if straight:
        return 4, straight
    return patterns.get(tuple(count for count, _ in groups), 0), *(rank for _, rank in groups)


def poker_duel(match, challenger, opponent):
    def card_label(card):
        return RANKS[card[0] - 2] + card[1]

    labels = "ABCDEFGHIJKLMNOP"
    min_slots, max_slots = 8, 10
    options = tuple(" ".join(pair) for pair in combinations(labels, 2))
    while True:
        cards = match.rng.sample(DECK, 19)
        display, community = cards[:16], cards[16:]
        display_labels = list(map(card_label, display))
        memorization = " ".join(f"{label}={card}" for label, card in zip(labels, display_labels, strict=True))
        match.event("poker_cards", {"phase": "memorize", "display": display_labels, "players": [challenger, opponent]})
        decisions = {}
        for name in (challenger, opponent):
            slots = match.policy.randint(min_slots, max_slots)
            decisions[name] = Decision(
                f"20초 동안 공개된 카드 위치 {memorization}. "
                f"공유 카드를 보기 전에 기억할 위치를 {min_slots}~{max_slots}개 고르세요. "
                "고른 위치를 공백 없이 오름차순으로 출력하세요.",
                "".join(sorted(match.policy.sample(labels, slots))),
                valid=lambda a: min_slots <= len(a) <= max_slots and set(a) <= set(labels) and a == "".join(sorted(set(a))),
            )
        memories = match.decide_together("memorize", decisions)
        shared = ", ".join(map(card_label, community))
        match.event("poker_cards", {"phase": "memory_poker", "community": shared})
        decisions = {}
        for name, memory in memories.items():
            remembered = [labels.index(label) for label in memory]
            first, second = max(combinations(sorted(remembered), 2), key=lambda pair: hand_rank(
                [*community, display[pair[0]], display[pair[1]]]
            ))
            recalled = " ".join(f"{labels[i]}={card_label(display[i])}" for i in remembered)
            decisions[name] = Decision(f"내가 기억한 카드 위치 {recalled}. "
                                       f"공유 카드 3장은 {shared}. 최강 5장 조합을 만들 위치 2개를 오름차순으로 고르세요. "
                                       "기억하지 않은 위치도 추측해서 고를 수 있습니다.",
                                       f"{labels[first]} {labels[second]}", valid=options.__contains__)
        picks = match.decide_together("memory_poker", decisions)
        results = {name: hand_rank([*community, *(display[labels.index(label)] for label in choice.split())])
                   for name, choice in picks.items()}
        match.event("poker_result", {"display": display_labels, "community": shared,
                                     "picks": picks, "hands": results})
        if results[challenger] != results[opponent]:
            return max(results, key=results.__getitem__)


def memory_stage(match, ranking, pieces):
    match.event("rules", "미니게임 4 · 기억 포커와 선택 10\n"
                "잔디 깔기까지의 승점과 큐브 세기 우선권으로 시작 순위를 정합니다. 이 시점부터 승점 대신 "
                "포커 대결로 바뀐 순위에 따라 생존을 결정합니다. 승점 표는 포커가 시작되기 전의 순위를 나타냅니다.\n"
                "매 대결에서 52장 중 16장을 무작위로 뽑아 20초 동안 보여 준 뒤, 공유 카드 3장을 공개합니다. "
                "두 참가자는 암기한 위치 중 2개를 비공개로 고릅니다. 둘 다 고르면 공개하고, 각자 고른 2장과 "
                "공유 카드 3장 모두로 만든 5장 족보를 비교합니다. 시뮬레이션에서는 각 참가자가 외울 위치를 "
                "8~10개 직접 고릅니다. 최종 선택에서는 외우지 않은 위치도 추측해서 제출할 수 있습니다.\n"
                "높은 족보부터 스트레이트 플러시, 포카드, 풀하우스, 플러시, 스트레이트, 트리플, 투 페어, "
                "원 페어, 하이 카드 순입니다. 같은 족보는 해당 카드의 숫자, 나머지 카드 숫자 순으로 비교합니다. "
                "문양은 비교하지 않으며 A는 A-2-3-4-5의 가장 낮은 카드가 될 수 있습니다. 모두 같으면 새 카드로 재대결합니다.\n"
                "선택 10에서 지목 방식은 8표 이상, 계단 방식은 9표 이상이면 적용됩니다. 15위, 16위 순서로 연승전에 나섭니다. "
                "지목 방식은 자신보다 높은 순위 중 이번 연승전에서 아직 만나지 않은 상대를 고릅니다. 도전자가 이기면 "
                "한 단계 오르고 상대가 한 단계 내려갑니다. 시뮬레이션에서는 도전자의 상향 교환 뒤 상대의 하향 교환을 "
                "적용합니다. 상대가 바로 위면 한 번만 바꾸고, 두 칸 위면 두 교환을 거쳐 도전자가 두 칸 올라갑니다. "
                "지목받은 상대가 이기면 피스 1개를 받습니다. 계단 방식은 바로 윗순위와 겨루어 이기면 자리를 바꿉니다.\n"
                "도전자가 지거나 더 겨룰 상대가 없으면 해당 연승전이 끝납니다. 새로 15위 또는 16위가 된 사람이 "
                "다음 도전자가 됩니다. 이미 도전 대상이 됐던 사람은 다시 나오지 않으며, 새 도전자가 없으면 종료합니다.")
    votes = match.decide_together("choice_10", {
        name: Decision("기억 포커는 하위권 연승전입니다. 지목 방식 8표 이상이면 순위가 높은 상대를 지목하고, "
                       "계단 방식 9표 이상이면 바로 윗순위와만 대결합니다.",
                       match.policy.choice(("지목", "계단")), options=("지목", "계단")) for name in match.players
    })
    nominations = sum(vote == "지목" for vote in votes.values())
    nomination = nominations >= 8
    match.event("poker_mode", {"mode": "지목" if nomination else "계단", "nomination_votes": nominations})
    waiting = deque(ranking[-2:])
    already_eligible = set(waiting)
    while waiting:
        challenger = waiting.popleft()
        challenged = set()
        while (index := ranking.index(challenger)) > 0:
            candidates = tuple(name for name in ranking[:index] if name not in challenged)
            if not candidates:
                break
            opponent = ranking[index - 1]
            if nomination:
                opponent = match.decide(challenger, "nominate", f"현재 순위 {ranking}. 상대를 지목하세요.",
                                        candidates[-1], options=candidates, private=False)
            challenged.add(opponent)
            winner = poker_duel(match, challenger, opponent)
            if winner != challenger:
                if nomination:
                    pieces[opponent] += 1
                break
            target_index = ranking.index(opponent)
            ranking[index - 1], ranking[index] = ranking[index], ranking[index - 1]
            if target_index < index - 1:
                ranking[target_index], ranking[target_index + 1] = ranking[target_index + 1], ranking[target_index]
            match.event("poker_ranking", {"winner": winner, "opponent": opponent, "ranking": ranking})
        for name in ranking[-2:]:
            if name not in already_eligible:
                already_eligible.add(name)
                waiting.append(name)
