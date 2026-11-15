"""Run rectangle counting, including team selection and settlement."""

from collections import Counter
from itertools import combinations
import json

from ..match import Decision
from .negotiation import negotiate


NANOSECONDS_PER_SECOND = 1_000_000_000
RECTANGLE_LIMIT_SECONDS = 300
CHOICE_TWO_SUBMISSION_TURN = 4


def count_rectangles(board, target):
    """Count every axis-aligned rectangle, including individual cells."""
    height, width = len(board), len(board[0])
    return sum(
        sum(board[row][col] for row in range(top, bottom) for col in range(left, right)) == target
        for top, bottom in combinations(range(height + 1), 2)
        for left, right in combinations(range(width + 1), 2)
    )


def rectangle_race(match, teams, phase="rectangles"):
    width = match.rng.randint(4, 6)
    board = [[match.rng.choice((0, 0, 0, 1, 2, 3, 4, 5)) for _ in range(width)] for _ in range(width)]
    target = match.rng.randint(3, 12)
    answer = count_rectangles(board, target)
    match.event("rectangle_puzzle", {"phase": phase, "board": board, "target": target})
    decisions = {}
    team_by_player = {}
    scripted_times = {}
    for team in teams:
        for name in team:
            scripted_times[name] = match.policy.randint(20, RECTANGLE_LIMIT_SECONDS) * NANOSECONDS_PER_SECOND
            estimate = max(0, answer + match.policy.choice((-2, -1, 1, 2))) if match.policy.random() < 0.22 else answer
            decisions[name] = Decision(
                f"판 {board}, 목표 합 {target}. 합이 목표인 축 정렬 네모의 개수를 세세요. "
                "0은 빈 칸입니다. 응답이 도착하면 버저를 누른 것으로 처리합니다. 답을 정수 하나로 제출하거나 패스하세요.",
                str(estimate), valid=lambda a: a == "패스" or (a.isascii() and a.isdecimal() and len(a) <= 4),
                invalid_default="패스",
            )
            team_by_player[name] = team
    response_times: dict[str, int] = {}
    answers = match.decide_together(phase, decisions, response_times=response_times)
    buzzes = []
    for name, action in answers.items():
        elapsed = response_times.get(name, scripted_times[name])
        if action != "패스" and elapsed <= RECTANGLE_LIMIT_SECONDS * NANOSECONDS_PER_SECOND:
            buzzes.append((elapsed, name, int(action)))
    tried = set()
    winner = None
    for elapsed, name, count in sorted(buzzes):
        team = team_by_player[name]
        if team in tried:
            continue
        tried.add(team)
        match.event("buzz", {"player": name, "time": round(elapsed / NANOSECONDS_PER_SECOND, 3),
                             "clock": "response" if name in response_times else "scripted",
                             "answer": count, "correct": count == answer})
        if count == answer:
            winner = team
            break
    match.event("rectangle_answer", {"answer": answer, "winner": winner})
    return winner


def rectangle_stage(match, priority, scores, pieces):
    players = match.players
    match.event("rules", "선택 2 · 팀 / 개인\n"
                "네모 세기는 혼자 참가하거나 3명이 팀으로 참가합니다. 세 사람이 같은 조합을 제출해야 팀이 확정되며 "
                "그 외에는 개인으로 참가합니다. 확정한 팀은 네모 세기가 끝날 때까지 바꿀 수 없습니다.\n"
                f"처음 {CHOICE_TWO_SUBMISSION_TURN - 1}턴은 협상만 할 수 있습니다. "
                f"{CHOICE_TWO_SUBMISSION_TURN}턴부터 자기 차례에 비공개로 제출할 수 있습니다. "
                "전원이 제출하면 팀을 공개하고 게임을 시작합니다. "
                "협상 제한에 도달하면 아직 제출하지 않은 참가자에게 마지막 선택을 받습니다.")
    match.event("rules", "미니게임 2 · 네모 세기\n"
                "공개 격자에서 칸의 숫자를 더해 목표 합이 되는 네모의 수를 셉니다. 빈 칸은 0으로 계산합니다. "
                "격자에 맞춘 직사각형을 세며, 조건을 만족하면 한 칸과 판 전체도 포함합니다.\n"
                "문제당 5분이며, 버저를 누르면 10초 안에 답해야 합니다. 시뮬레이션에서는 답만 제출하며 "
                "응답이 도착한 순서대로 버저를 처리합니다. "
                "오답을 낸 개인이나 팀은 같은 문제에 재도전할 수 없습니다. 먼저 정답을 맞히거나, "
                "시간 안에 정답이 없거나, 모든 개인과 팀이 오답이면 다음 문제로 넘어갑니다.\n"
                "두 문제를 맞힌 개인이나 팀은 승리하고 이후 문제에서 빠집니다. 개인과 3인 팀을 각각 한 팀으로 세어 "
                "전체 팀의 절반이 승리하면 끝납니다. 개인 승리는 +7점, 패배는 −3점입니다. "
                "3인 팀은 승리 시 7점을 나누고 패배 시 총 3점 또는 4점을 잃습니다.")
    seat = {name: i for i, name in enumerate(players)}
    draft = match.policy.sample(players, len(players))
    offers = {name: "개인" for name in players}
    triples = [tuple(sorted(draft[start:start + 3], key=seat.__getitem__)) for start in (0, 3, 6)]
    for triple in triples:
        for name in triple:
            offers[name] = " ".join(triple)
    decisions = {}
    for name in players:
        def valid(action, name=name):
            if action == "개인":
                return True
            members = action.split()
            return len(members) == len(set(members)) == 3 and name in members and set(members) <= set(players)

        decisions[name] = Decision(
            f"네모 세기를 혼자 하려면 개인, 3인 팀이면 내 이름을 포함한 세 참가자 ID를 공백으로 구분해 제출하세요. "
            f"세 사람이 같은 조합을 골라야 팀입니다. {players}", offers[name], valid=valid,
        )
    triple = triples[0]
    submitted = negotiate(match, 2, "네모 세기에 개인으로 참가할지, 누구와 3인 팀을 이룰지 논의하세요. "
                          "팀을 이루려면 세 사람 모두 같은 조합을 제출해야 합니다.", triple, (
                              f"{', '.join(triple)} 세 명이 팀을 이룰까요? 판을 세 구역으로 나눠 세면 좋겠어요.",
                              "세 명이 같은 조합을 제출하죠. 각자 맡을 구역도 맞춰 봐요.",
                              "저도 그 세 명 조합으로 제출할게요. 팀이 되면 제가 오른쪽 구역을 살펴볼게요.",
                          ), terminal_choices=decisions, submission_opens_on=CHOICE_TWO_SUBMISSION_TURN)
    remaining = {name: decision for name, decision in decisions.items() if name not in submitted}
    if remaining:
        submitted.update(match.decide_together("choice_2", remaining))
        match.event("choice_progress", {"choice": 2, "submitted": len(submitted), "total": len(players)})
    proposals = {}
    for name in players:
        action = submitted[name]
        proposals[name] = (name,) if action == "개인" else tuple(sorted(action.split(), key=seat.__getitem__))
    teams = tuple(dict.fromkeys(team if all(proposals[member] == team for member in team) else (name,)
                               for name, team in proposals.items()))
    match.event("teams", {"teams": teams})
    rectangle_start = len(match.events)
    points = dict.fromkeys(teams, 0)
    winners = set()
    while len(winners) < len(teams) // 2:
        winner = rectangle_race(match, [team for team in teams if team not in winners])
        if winner is not None:
            points[winner] += 1
            if points[winner] == 2:
                winners.add(winner)
            match.event("rectangle_standings", {" / ".join(team): score for team, score in points.items()})
    match.event("rectangle_result", {"winners": [team for team in teams if team in winners],
                                     "losers": [team for team in teams if team not in winners]})
    match.review_relationships("팀 구성 및 네모 세기 결과")
    team_entries = [team for team in teams if len(team) == 3]
    representatives = {}
    if team_entries:
        match.event("rules", "네모 세기 · 팀 대표 선출\n"
                    "각 3인 팀은 네모 세기에 기여도가 높았던 팀원 한 명을 대표로 정해 딜러에게 제출합니다.")
        buzzes = (json.loads(event.content) for event in match.events[rectangle_start:] if event.msg_type == "buzz")
        correct = Counter(buzz["player"] for buzz in buzzes if buzz["correct"])

        def contribution(name):
            return correct[name], -priority.index(name)

        nominations = {}
        for team in team_entries:
            result = "승리" if team in winners else "패배"
            record = " · ".join(f"{name} {correct[name]}문제" for name in team)
            decision = Decision(f"팀 {team}은 {result}했습니다. 팀원별 정답 수는 {record}입니다. "
                                "실제 경기 기여도를 고려해 팀 대표 한 명을 지목하세요.",
                                max(team, key=contribution), options=team)
            nominations.update(dict.fromkeys(team, decision))
        team_votes = match.decide_together("representative", nominations)
        for team in team_entries:
            votes = Counter(team_votes[name] for name in team)
            representatives[team] = max(team, key=lambda name: (votes[name], *contribution(name)))
        match.event("representatives", {rep: team for team, rep in representatives.items()})

    match.event("rules", "선택 3 · 네모 세기 정산과 추가 대결\n"
                "3인 팀은 세 명의 다수결로 정산합니다. 승리 팀은 독식(대표 +5, 팀원 각 +1)과 "
                "헌신(대표 +1, 팀원 각 +3) 중 고릅니다. 패배 팀은 희생(대표 −3, 팀원 0)과 "
                "질책(대표 0, 팀원 각 −2) 중 고릅니다.\n"
                "개인 참가자는 도전과 안전 중 고릅니다. 도전하면 추가 대결 승자에게 피스 3개, "
                "패자에게 승점 −3점을 적용합니다. 안전을 고르면 대결 없이 −1점입니다. "
                "시뮬레이션의 추가 대결은 네모 세기 한 문제를 먼저 맞히면 승리합니다. 정답자가 없으면 새 문제로 "
                "계속하고, 도전자가 한 명이면 그 참가자가 승리합니다.")
    settlements = {}
    for team in teams:
        won = team in winners
        if len(team) == 1:
            name = team[0]
            scores[name] += 7 if won else -3
        else:
            rep = representatives[team]
            options = ("독식", "헌신") if won else ("희생", "질책")
            consequences = ("독식은 대표 +5, 두 팀원 각 +1. 헌신은 대표 +1, 두 팀원 각 +3."
                            if won else "희생은 대표 −3, 두 팀원 0. 질책은 대표 0, 두 팀원 각 −2.")
            for name in team:
                settlements[name] = Decision(f"팀 {team}, 대표 {rep}. {consequences} 다수결입니다.",
                                             options[int(name != rep)] if won else options[int(name == rep)], options=options)
    votes = match.decide_together("choice_3_team", settlements)
    for team, rep in representatives.items():
        selection = Counter(votes[name] for name in team).most_common(1)[0][0]
        by_role = {"독식": (5, 1), "헌신": (1, 3), "희생": (-3, 0), "질책": (0, -2)}[selection]
        for name in team:
            scores[name] += by_role[int(name != rep)]
        match.event("team_vote", {"team": team, "decision": selection})
    match.event("scoreboard", scores)
    solo_choices = match.decide_together("choice_3_solo", {
        name: Decision("도전은 추가 네모 대결에서 이기면 피스 3개, 지면 승점 −3. 안전은 바로 승점 −1.",
                       "도전" if match.policy.random() < 0.5 else "안전", options=("도전", "안전"))
        for (name,) in (team for team in teams if len(team) == 1)
    })
    challengers = []
    for name, choice in solo_choices.items():
        if choice == "도전":
            challengers.append((name,))
        else:
            scores[name] -= 1
    if challengers:
        winner = challengers[0] if len(challengers) == 1 else None
        while winner is None:
            winner = rectangle_race(match, challengers, phase="rectangle_challenge")
        for (name,) in challengers:
            if winner == (name,):
                pieces[name] += 3
            else:
                scores[name] -= 3
        match.event("challenge_result", {"challengers": [name for name, in challengers], "winner": winner[0]})
    match.event("scoreboard", scores)
