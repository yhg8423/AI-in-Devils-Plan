"""Day 1 prison match. Seats run clockwise, starting with the main-match leader."""

from ..match import Decision, Match


COLORS = ("빨강", "초록", "파랑")
WILD = "레인보우"
PASS = "패스"


def place(stack: list[int], weight: int) -> int:
    penalty = len(stack) if sum(stack) + weight >= 13 else 0
    if penalty:
        stack.clear()
    stack.append(weight)
    return penalty


def play(match: Match) -> dict:
    players = match.players
    stacks = {color: [] for color in COLORS}
    penalties = dict.fromkeys(players, 0)
    last_penalty = dict.fromkeys(players, -1)
    leader = players[0]
    match.event("rules", (
        "무거운 13 · 참가자 7명, 총 14라운드\n\n"
        "1. 준비\n"
        "빨강·초록·파랑 받침대 세 개를 사용합니다. 각 참가자는 0~6 바위 카드 한 장씩, "
        "빨강·초록·파랑 칩 두 개씩, 레인보우 칩 한 개를 받습니다. "
        "감옥동 참가자 중 메인 매치 순위가 가장 높은 사람이 첫 라운드의 선입니다. "
        "방송에서는 시작 전에 자리를 고르고 게임 도중에는 그 자리를 유지합니다.\n\n"
        "2. 비공개 제출\n"
        "매 라운드에 남은 바위 카드 한 장과 색 칩 한 개를 제출해 소모합니다. "
        "카드 숫자는 이번에 놓을 큐브의 무게이고, 색 칩은 놓을 받침대를 정합니다. "
        "방송의 제출 제한 시간은 3분입니다. 모두 제출하면 칩을 먼저 공개하고 카드 숫자를 공개합니다.\n\n"
        "3. 배치 순서와 패스\n"
        "레인보우 칩을 낸 사람이 먼저 놓습니다. 같은 우선순위에서는 카드 숫자가 큰 사람이 먼저 놓고, "
        "숫자까지 같으면 선 플레이어부터 시계 방향으로 순서를 정합니다. "
        "일반 칩은 같은 색 받침대에 놓고, 레인보우 칩은 배치할 때 받침대 세 곳 중 하나를 고릅니다. "
        "각 참가자는 라운드마다 배치 차례에 한 번 패스할 수 있습니다. "
        "패스한 사람은 나머지 배치가 끝난 뒤 나중에 패스한 사람부터 놓습니다.\n\n"
        "4. 벌점과 다음 라운드\n"
        "새 큐브를 놓아 합이 13 이상이 되면 그 받침대에 있던 기존 큐브를 모두 걷습니다. "
        "방금 놓은 큐브는 남고, 배치한 사람이 수거한 큐브 한 개당 벌점 1점을 받습니다. "
        "무게 0인 큐브도 수거할 때 한 개로 셉니다. 그 라운드의 마지막 벌점자가 다음 라운드의 선입니다. "
        "8라운드 시작 때 처음과 같은 카드와 칩을 받으며, 받침대와 누적 벌점은 이어집니다.\n\n"
        "5. 보상과 탈락\n"
        "14라운드가 끝나면 누적 벌점이 적은 순으로 순위를 정합니다. 벌점이 같으면 마지막 벌점을 더 최근에 받은 쪽이 "
        "낮은 순위에 놓입니다. 6위와 7위는 탈락합니다. 최소 벌점 참가자들은 피스 4개를 똑같이 나누고, "
        "나누고 남은 피스는 버립니다.\n\n"
        "시뮬레이션 진행\n"
        f"실행 명단 순서가 시계 방향 자리입니다. {' → '.join(players)}. "
        f"첫 선은 {leader}입니다. 시뮬레이터는 각 참가자의 제출을 받아 일괄 공개합니다."
    ))
    for round_number in range(1, 15):
        if round_number in (1, 8):
            cards = {name: list(range(7)) for name in players}
            chips = {name: [*COLORS, *COLORS, WILD] for name in players}
        start = players.index(leader)
        clockwise = players[start:] + players[:start]
        match.event("round", {"round": round_number, "leader": leader, "stacks": stacks,
                              "penalties": penalties})
        decisions = {}
        for name in clockwise:
            moves = [(weight, color) for weight in cards[name] for color in dict.fromkeys(chips[name])]
            loads = {color: sum(stacks[color]) for color in COLORS}
            loads[WILD] = min(loads.values())
            safe = [(weight, color) for weight, color in moves if loads[color] + weight < 13]
            weight, color = match.policy.choice(safe or moves)
            decisions[name] = Decision(f"{round_number}라운드. 내 숫자 카드와 색 칩을 제출하세요.",
                                       f"{weight} {color}", options=[f"{w} {c}" for w, c in moves])
        submissions = {}
        for name, action in match.decide_together("submit", decisions).items():
            value, color = action.split()
            weight = int(value)
            cards[name].remove(weight)
            chips[name].remove(color)
            submissions[name] = weight, color

        order = sorted(clockwise, key=lambda name: (submissions[name][1] != WILD, -submissions[name][0]))
        match.event("colors", {name: submissions[name][1] for name in order})
        match.event("weights", {name: submissions[name][0] for name in order})
        deferred = []
        while order or deferred:
            first_pass = bool(order)
            name = order.pop(0) if first_pass else deferred.pop()
            weight, chip = submissions[name]
            colors = COLORS if chip == WILD else (chip,)
            color = min(colors, key=lambda c: sum(stacks[c]))
            if first_pass or chip == WILD:
                options = (*colors, PASS) if first_pass else colors
                default = PASS if first_pass and sum(stacks[color]) + weight >= 13 else color
                action = match.decide(name, "place", f"무게 {weight}, 제출 칩 {chip}, 현재 받침대 {stacks}.",
                                      default, options=options, private=False)
                if action == PASS:
                    deferred.append(name)
                    continue
                color = action
            penalty = place(stacks[color], weight)
            if penalty:
                penalties[name] += penalty
                last_penalty[name] = len(match.events)
                leader = name
            match.event("placement", {"player": name, "color": color, "weight": weight,
                                      "stack": stacks[color], "penalty": penalty})
        if round_number == 7:
            match.review_relationships("무거운 13 전반 종료")

    ranking = sorted(players, key=lambda name: (penalties[name], last_penalty[name]))
    winners = [name for name in ranking if penalties[name] == penalties[ranking[0]]]
    awards = {name: 4 // len(winners) for name in winners}
    return {"ranking": ranking, "penalties": penalties, "eliminated": ranking[-2:],
            "pieces_awarded": awards, "pieces": {name: match.pieces[name] + awards.get(name, 0) for name in players}}
