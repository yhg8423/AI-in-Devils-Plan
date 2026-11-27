"""Sealed bidding for three stones; one final exile returns with five Pieces.

Broadcast narration: https://subdl.com/id/s/info/MHU1SqES8i/the-devils-plan
Board reference: https://www.puzzlthink.com/ko/point-omok
Fresh-board draws and timeout defaults are simulator completion policies.
"""

from base64 import b64decode
from dataclasses import replace
import json

from ...match import Decision, Match, encode
from .puzzles import DIRECTIONS, SIZE, board, empty_board, five_lines, legal_triples, stone_list


SECONDS = 90
GRANT = 10
RULES = """포인트 오목 · 유배지 최후의 대결 · 2인전

15×15 판에서 정확히 다섯 돌을 이어 본선 복귀를 노리세요. 더 오래 유배지에서 생존한 참가자가
첫 선택자이며, 다음 라운드부터 번갈아 선택합니다. 독립 실행에서는 입력한 참가자 순서를 사용합니다.
선택자는 90초 안에 가로·세로·대각선으로 연속된 빈 교차점 세 개를 지정합니다.
그림의 x는 왼쪽부터 1~15, y는 위쪽부터 1~15입니다. 세 점은 A·B·C 순서로 표시됩니다.

매 라운드 각자 10포인트와 직전 이월분을 받습니다. 90초 안에 세 점에 포인트를 비공개로 배분하세요.
각 점에 정수 최소 1포인트를 써야 하고 합계는 보유 포인트 이하입니다. 전부 쓸 필요는 없습니다.
각 점에서 더 많이 낸 참가자의 돌이 놓입니다. 동률이면 이번 선택자가 아닌 참가자의 돌이 놓입니다.
이기든 지든 낸 포인트는 모두 소모하며, 남은 포인트의 절반을 소수점 버림하여 다음 라운드로 넘깁니다.
상대의 입찰액·잔액·이월분은 공개되지 않습니다. 돌의 주인만 함께 공개됩니다.

세 돌을 모두 놓은 뒤 가로·세로·대각선의 정확한 5목을 판정합니다. 6목 이상은 인정하지 않습니다.
양쪽에 동시에 5목이 생기면 5목 개수가 더 많은 참가자가 승리합니다.
승자는 피스 5개를 받고 본선에 복귀하며, 패자는 최종 탈락합니다.
대화·협상·관계 평가는 없습니다. 짧은 판단 요약과 행동은 한 번에 제출합니다.

시뮬레이터 보완: 같은 개수의 5목으로 비기거나 더 고를 빈 세 점이 없으면 새 판과 새 포인트로 재경기합니다.
재경기 첫 선택자는 직전 판의 첫 선택자와 반대로 바꿉니다. 임의 점수나 추첨으로 승자를 정하지 않습니다.
시간을 넘긴 선택은 합법적인 시연 위치로, 늦은 입찰은 각 점 1포인트로 바꿉니다.
잘못된 형식·호출 상한 뒤에도 같은 합법 행동 검증을 거친 시연 선택으로 진행합니다.
"""


def parse_selection(text, grid):
    data = json.loads(text)
    if (not isinstance(data, dict) or set(data) != {"points"} or not isinstance(data["points"], list)
            or len(data["points"]) != 3):
        raise ValueError("points에 빈 교차점 세 개를 지정하세요.")
    points = data["points"]
    if any(not isinstance(point, list) or len(point) != 2
           or any(type(value) is not int or not 1 <= value <= SIZE for value in point) for point in points):
        raise ValueError("좌표는 1~15 정수 x·y 쌍이어야 합니다.")
    ordered = sorted(points)
    delta = ordered[1][0] - ordered[0][0], ordered[1][1] - ordered[0][1]
    if (delta not in DIRECTIONS or any(ordered[2][axis] - ordered[1][axis] != delta[axis] for axis in (0, 1))
            or any(grid[y - 1][x - 1] is not None for x, y in points)):
        raise ValueError("가로·세로·대각선으로 연속된 빈 점 세 개를 골라야 합니다.")
    return points


def parse_bid(text, available):
    data = json.loads(text)
    if (not isinstance(data, dict) or set(data) != {"bids"} or not isinstance(data["bids"], list)
            or len(data["bids"]) != 3 or any(type(value) is not int or value < 1 for value in data["bids"])
            or sum(data["bids"]) > available):
        raise ValueError("각 점에 정수 1포인트 이상을 쓰고 합계는 보유량 이하여야 합니다.")
    return data["bids"]


def _accepts(parser, text, argument):
    try:
        parser(text, argument)
        return True
    except (ValueError, TypeError, RecursionError):
        return False


def settle(grid, points, bids, available, players, selector):
    """Resolve all three cells before judging any maximal five."""
    parse_selection(encode({"points": points}), grid)
    for name in players:
        parse_bid(encode({"bids": bids[name]}), available[name])
    other = next(name for name in players if name != selector)
    result = [row.copy() for row in grid]
    owners = []
    for index, (x, y) in enumerate(points):
        owner = selector if bids[selector][index] > bids[other][index] else other
        owners.append(owner)
        result[y - 1][x - 1] = owner
    lines = {name: five_lines(result, name) for name in players}
    counts = {name: len(lines[name]) for name in players}
    best = max(counts.values())
    winner = max(players, key=counts.get) if counts[players[0]] != counts[players[1]] else None
    reason = "five" if winner else "equal_fives" if best else "no_triples" if not legal_triples(result) else None
    carries = {name: (available[name] - sum(bids[name])) // 2 for name in players}
    return result, owners, lines, winner, reason, carries


def _scripted_selection(grid, players, selector, policy):
    """A legal demonstration policy; no candidate evaluations enter model prompts."""
    triples = legal_triples(grid)
    if not triples:
        return None
    # Prefer play near existing stones and the centre instead of filling distant rows.
    def score(points):
        return sum(sum(grid[yy][xx] == selector for yy in range(max(0, y - 3), min(SIZE, y + 2))
                       for xx in range(max(0, x - 3), min(SIZE, x + 2))) * 5
                   - abs(x - 8) - abs(y - 8) for x, y in points)
    best = max(map(score, triples))
    return policy.choice([points for points in triples if score(points) == best])


def _scripted_bid(available, policy):
    spending = policy.randint(3, available)
    first = policy.randint(1, spending - 2)
    second = policy.randint(1, spending - first - 1)
    bids = [first, second, spending - first - second]
    policy.shuffle(bids)
    return bids


def _observations(name, events):
    observations = []
    for event in events:
        if event.visible_to != "all" and name not in event.visible_to:
            continue
        if event.msg_type == "gomoku_placement":
            data = json.loads(event.content)
            observations.append(replace(event, content=encode({key: data[key] for key in ("game", "round", "selector", "points", "owners")})))
        elif event.msg_type in {"rules", "gomoku_setup", "gomoku_game_result", "gomoku_bid", "decision_note", "invalid_action"}:
            observations.append(event)
    return observations


def play(match: Match):
    players = list(match.players)
    if len(players) != 2 or len(set(players)) != 2:
        raise ValueError("포인트 오목에는 서로 다른 참가자 두 명이 필요합니다.")
    match.relationship_reviews_enabled = False
    match.model_observations = _observations
    match.event("rules", RULES)
    match.event("gomoku_setup", {"version": 1, "players": players, "size": SIZE,
        "colors": {players[0]: "black", players[1]: "white"}, "first_selector": players[0],
        "points_per_round": GRANT, "selection_seconds": SECONDS, "bid_seconds": SECONDS})
    games, total_rounds, results = 0, 0, []
    winner = None
    while winner is None:
        games += 1
        grid, carry = empty_board(), dict.fromkeys(players, 0)
        first = players[(games - 1) % 2]
        match.event("gomoku_game", {"game": games, "replay": games - 1, "first_selector": first,
                                    "board": board(grid, players)})
        number = 0
        while winner is None:
            number += 1
            total_rounds += 1
            selector = players[(players.index(first) + number - 1) % 2]
            context = {"game": games, "round": number}
            match.event("gomoku_round", {**context, "selector": selector})
            available = {name: GRANT + carry[name] for name in players}
            for name in players:
                match.event("gomoku_wallet", {**context, "player": name, "available": available[name],
                    "carry": carry[name]}, actor=name, private=[name])
            default = _scripted_selection(grid, players, selector, match.policy)
            if default is None:
                raise RuntimeError("재경기 전에 유효한 교차점이 소진되었습니다.")
            view = board(grid, players)
            times = {}
            selection = match.decide_together("gomoku_select", {selector: Decision(
                f"포인트 오목 {games}번째 판 {number}라운드. 당신은 {selector}, 이번 선택자입니다. "
                "생존과 본선 복귀를 위해 상대의 5목을 막고 자신의 정확한 5목을 노리세요. "
                "첨부 공개 판에서 가로·세로·대각선으로 연속된 빈 교차점 세 개를 고르세요. "
                "x는 왼쪽부터, y는 위쪽부터 1~15입니다. 지금은 위치만 고르며 입찰은 다음에 합니다. "
                '90초 안에 JSON {"points":[[x,y],[x,y],[x,y]]}만 제출하세요.',
                encode({"points": default}), valid=lambda text: _accepts(parse_selection, text, grid))},
                response_times=times, images=(b64decode(view["image"].partition(",")[2]),), max_reviews=0)[selector]
            late = times.get(selector, 0) > SECONDS * 1_000_000_000
            points = default if late else parse_selection(selection, grid)
            if late:
                match.event("gomoku_selection_timeout", {**context, "selector": selector, "elapsed_ns": times[selector]})
            view = board(grid, players, selected=points)
            match.event("gomoku_select", {**context, "selector": selector, "points": points, "board": view})
            defaults = {name: _scripted_bid(available[name], match.policy) for name in players}
            decisions = {name: Decision(
                f"포인트 오목 {games}번째 판 {number}라운드 · {name}. "
                f"이번 선택자는 {selector}입니다. A·B·C 좌표: {encode(points)}. "
                f"내 보유 포인트 {available[name]}(이번 지급 10 + 이월 {carry[name]}). "
                "상대의 이번 입찰과 잔액은 알 수 없습니다. 상대에게 없는 정보를 가정하지 마세요. "
                "최종 탈락을 피하고 본선 복귀를 노리며, 꼭 필요한 칸을 확보하고 다음 라운드의 자원도 고려하세요. "
                "동률인 점은 이번 선택자가 아닌 참가자의 돌입니다. 세 돌을 모두 놓은 뒤 정확한 5목만 판정합니다. "
                '90초 안에 A·B·C 순서로 JSON {"bids":[정수,정수,정수]}를 비공개 제출하세요. '
                "각각 최소 1, 합계는 보유 포인트 이하여야 합니다. 남은 절반만 버림 이월됩니다.",
                encode({"bids": defaults[name]}), valid=lambda text, name=name: _accepts(parse_bid, text, available[name])) for name in players}
            times = {}
            replies = match.decide_together("gomoku_bid", decisions, response_times=times,
                images=(b64decode(view["image"].partition(",")[2]),), max_reviews=0)
            bids = {name: [1, 1, 1] if times.get(name, 0) > SECONDS * 1_000_000_000
                    else parse_bid(replies[name], available[name]) for name in players}
            grid, owners, lines, winner, reason, carry = settle(grid, points, bids, available, players, selector)
            for name in players:
                spent = sum(bids[name])
                match.event("gomoku_bid", {**context, "player": name, "bids": bids[name], "spent": spent,
                    "remaining": available[name] - spent, "carry": carry[name],
                    "timeout": times.get(name, 0) > SECONDS * 1_000_000_000,
                    "elapsed_ns": times.get(name, 0)}, actor=name, private=[name])
            match.event("gomoku_placement", {**context, "selector": selector, "points": points, "owners": owners,
                "stones": stone_list(grid), "winning_lines": lines, "board": board(grid, players, winning_lines=lines)})
            if reason:
                result = {**context, "winner": winner, "reason": reason,
                          "counts": {name: len(lines[name]) for name in players}, "winning_lines": lines}
                results.append(result)
                match.event("gomoku_game_result", result)
                break
    loser = next(name for name in players if name != winner)
    match.pieces = {winner: 5, loser: 0}
    awarded = {winner: 5, loser: 0}
    match.event("gomoku_finish", {"winner": winner, "eliminated": [loser], "pieces_awarded": awarded})
    return {"ranking": [winner, loser], "ranking_groups": [[winner], [loser]], "winner": winner,
            "returnee": winner, "survivors": [winner], "eliminated": [loser], "scores": {winner: 1, loser: 0},
            "pieces": match.pieces.copy(), "pieces_awarded": awarded, "rounds": total_rounds,
            "games": results, "replays": games - 1}
