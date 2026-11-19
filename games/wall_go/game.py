"""Public territory strategy with distinct square and round counters."""

import json

from ..match import Decision, Match, encode


SIZE = 7
DIRECTIONS = ((-1, 0), (0, 1), (1, 0), (0, -1))
CELLS = tuple((row, col) for row in range(1, SIZE + 1) for col in range(1, SIZE + 1))
CORNERS = (((2, 2), (6, 6)), ((2, 6), (6, 2)))
RULES = """벽바둑 2 · 7×7 영역 확보 · 3인전 후 2인전

1. 준비와 승리
1라운드는 3인전입니다. 추첨한 순서로 사각 말과 원형 말을 하나씩 원하는 빈 칸에 배치합니다.
첫 배치는 정순, 두 번째 배치는 역순입니다. 자신의 생존과 더 넓은 영역을 위해 경쟁하세요.
대화·협상·관계 평가 없이 진행합니다. 매 선택에서 현재 공개된 판과 상대의 다음 수를 보고 판단하세요.

2. 말 이동
사각 말은 상하좌우 한 방향으로 1~2칸 이동합니다. 원형 말은 상하좌우 한 칸 이동하거나,
한 칸 이동 후 왼쪽 또는 오른쪽으로 꺾어 한 칸 더 이동합니다. 0칸 이동·원위치 왕복은 불가합니다.
다른 말이 있는 칸으로 이동하거나 그 말을 뛰어넘을 수 없고, 이동 경로의 벽도 통과할 수 없습니다.

3. 벽 설치와 부수기
자기 차례에는 말 하나를 이동하고 도착 칸의 상하좌우 변 중 빈 변에 벽 하나를 반드시 설치합니다.
판의 바깥 경계는 이미 벽이며 기존 벽과 겹쳐 설치할 수 없습니다. 한 턴의 제한 시간은 90초입니다.
시간을 넘기면 유효한 이동은 유지하되 벽은 가능한 면 중 임의로 정합니다.
행동 형식이 올바르지 않거나 모델 호출 예산이 끝나면 제시된 유효 행동으로 진행합니다.
1라운드에만 각자 한 번, 이동 경로를 막는 벽 하나를 부수고 이동할 수 있습니다.
자기 말이 속한 영역이 다른 참가자의 말과 완전히 분리되면 그 말로 불필요한 수순을 진행하지 않습니다.
단, 벽 부수기가 남고 자기 영역과 다른 색의 영역이 벽 하나를 사이에 두고 있다면
벽을 부술 위치까지 가는 준비 이동과 벽 설치도 진행할 수 있습니다.

4. 종료와 점수
각 참가자의 말이 속한 영역이 모두 분리되면 벽 부수기가 남아도 즉시 종료합니다.
자신만 있는 연결 영역의 칸 수를 합산합니다. 같은 영역에 자기 말이 여럿 있어도 한 번만 셉니다.
어느 참가자도 유효한 이동과 벽 설치를 할 수 없는 교착 상태이면 종료합니다.
교착 시 서로 다른 색의 말이 함께 갇힌 영역은 각 말이 현재 서 있는 칸만 각각 1칸짜리 영역으로 인정합니다.
혼합 영역의 빈 칸은 누구의 점수에도 넣지 않고, 이미 분리된 단독 영역은 그대로 합산합니다.
합계 동점이면 가장 큰 단일 영역으로 비교합니다. 이 값도 같으면 동률자끼리만 순서를 뒤집어 재경기합니다.
1라운드 1위가 생존을 확정하고 나머지 두 명은 2라운드로 갑니다.

5. 2라운드
1라운드에서 더 넓은 영역을 확보한 사람이 선입니다. 각자 사각 말 2개와 원형 말 2개를 사용합니다.
선의 원형 말은 (행,열) (2,2)·(6,6), 후의 원형 말은 (2,6)·(6,2)에 고정 배치합니다.
사각 말은 선·후·후·선 순서로 빈 칸에 놓습니다. 벽 부수기는 없습니다.
완전 동률이면 선후공을 바꾸어 재경기합니다. 2라운드 패자는 탈락하고 생존한 두 명은 피스 1개씩 받습니다.
"""


def cell(value):
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or any(type(number) is not int or not 1 <= number <= SIZE for number in value)):
        raise ValueError("칸은 1~7의 행·열 좌표여야 합니다.")
    return tuple(value)


def edge(first, second):
    first, second = cell(first), cell(second)
    if sum(abs(a - b) for a, b in zip(first, second)) != 1:
        raise ValueError("벽은 인접한 두 칸 사이에만 설치합니다.")
    return tuple(sorted((first, second)))


def adjacent(position):
    row, col = position
    return [(row + dr, col + dc) for dr, dc in DIRECTIONS
            if 1 <= row + dr <= SIZE and 1 <= col + dc <= SIZE]


class Board:
    def __init__(self, players, order=None, round_number=1):
        if len(players) not in (2, 3) or len(set(players)) != len(players) or round_number not in (1, 2):
            raise ValueError("벽바둑 판에는 서로 다른 2~3명의 참가자가 필요합니다.")
        if round_number == 2 and len(players) != 2:
            raise ValueError("2라운드는 두 명만 참가합니다.")
        self.players = tuple(players)
        self.order = tuple(order if order is not None else players)
        if len(self.order) != len(self.players) or set(self.order) != set(self.players):
            raise ValueError("차례에는 각 참가자가 한 번씩 있어야 합니다.")
        self.round_number = round_number
        self.walls = set()
        self.breakers = dict.fromkeys(players, int(round_number == 1))
        self.pieces = {
            f"{player}:{kind}:{number}": {"player": player, "kind": kind, "position": None}
            for player in self.order for kind in ("square", "round")
            for number in range(1, (2 if round_number == 2 else 1) + 1)
        }
        if round_number == 2:
            for player, positions in zip(self.order, CORNERS, strict=True):
                for number, position in enumerate(positions, 1):
                    self.pieces[f"{player}:round:{number}"]["position"] = position

    def snapshot(self):
        return {"pieces": {key: {**piece, "position": list(piece["position"]) if piece["position"] else None}
                           for key, piece in self.pieces.items()},
                "walls": [[list(first), list(second)] for first, second in sorted(self.walls)],
                "breakers": self.breakers.copy()}

    def placement_options(self, player):
        occupied = {piece["position"] for piece in self.pieces.values() if piece["position"]}
        return [{"piece": key, "position": list(position)}
                for key, piece in self.pieces.items() if piece["player"] == player and piece["position"] is None
                for position in CELLS if position not in occupied]

    def place(self, player, action):
        if not isinstance(action, dict) or action.keys() != {"piece", "position"}:
            raise ValueError("배치할 말과 좌표를 지정하세요.")
        position = cell(action["position"])
        normalized = {"piece": action["piece"], "position": list(position)}
        if normalized not in self.placement_options(player):
            raise ValueError("자기 미배치 말을 빈 칸에 배치하세요.")
        self.pieces[action["piece"]]["position"] = position

    def territories(self, *, stalemate=False):
        occupied = {}
        for piece in self.pieces.values():
            if piece["position"] is not None:
                occupied.setdefault(piece["position"], set()).add(piece["player"])
        remaining = set(CELLS)
        territories = []
        while remaining:
            start = min(remaining)
            remaining.remove(start)
            component, pending, owners = [start], [start], set()
            while pending:
                current = pending.pop()
                owners.update(occupied.get(current, ()))
                for neighbor in adjacent(current):
                    if neighbor in remaining and edge(current, neighbor) not in self.walls:
                        remaining.remove(neighbor)
                        component.append(neighbor)
                        pending.append(neighbor)
            if stalemate and len(owners) > 1:
                empty = []
                for position in sorted(component):
                    cell_owners = occupied.get(position, set())
                    if len(cell_owners) == 1:
                        territories.append({"owner": next(iter(cell_owners)), "cells": [list(position)]})
                    else:
                        empty.append(list(position))
                if empty:
                    territories.append({"owner": None, "cells": empty})
            else:
                territories.append({"owner": next(iter(owners)) if len(owners) == 1 else None,
                                    "cells": [list(position) for position in sorted(component)]})
        return territories

    def scores(self, *, stalemate=False):
        scores, largest = dict.fromkeys(self.players, 0), dict.fromkeys(self.players, 0)
        for territory in self.territories(stalemate=stalemate):
            owner = territory["owner"]
            if owner is not None:
                size = len(territory["cells"])
                scores[owner] += size
                largest[owner] = max(largest[owner], size)
        return scores, largest

    def ranking(self, *, stalemate=False):
        scores, largest = self.scores(stalemate=stalemate)
        groups = []
        for player in sorted(self.order, key=lambda name: (-scores[name], -largest[name])):
            if groups and (scores[player], largest[player]) == (scores[groups[-1][0]], largest[groups[-1][0]]):
                groups[-1].append(player)
            else:
                groups.append([player])
        return groups

    def separated(self):
        if any(piece["position"] is None for piece in self.pieces.values()):
            return False
        for territory in self.territories():
            owners = {piece["player"] for piece in self.pieces.values()
                      if piece["position"] is not None and list(piece["position"]) in territory["cells"]}
            if len(owners) > 1:
                return False
        return True

    def _paths(self, piece):
        start = piece["position"]
        occupied = {other["position"] for other in self.pieces.values() if other["position"] is not None}
        row, col = start
        for dr, dc in DIRECTIONS:
            first = (row + dr, col + dc)
            if first not in CELLS or first in occupied:
                continue
            yield [first]
            directions = ((dr, dc),) if piece["kind"] == "square" else ((dc, -dr), (-dc, dr))
            for nr, nc in directions:
                second = (first[0] + nr, first[1] + nc)
                if second in CELLS and second not in occupied:
                    yield [first, second]

    def legal_actions(self, player):
        if player not in self.players or any(piece["position"] is None for piece in self.pieces.values()):
            return []
        territories = self.territories()
        owners = {tuple(position): territory["owner"] for territory in territories for position in territory["cells"]}
        components = {tuple(position): index for index, territory in enumerate(territories)
                      for position in territory["cells"]}
        members = [set() for _ in territories]
        for piece in self.pieces.values():
            members[components[piece["position"]]].add(piece["player"])
        reopenable = set()
        if self.breakers[player]:
            for first, second in self.walls:
                left, right = components[first], components[second]
                if left == right:
                    continue
                if members[left] == {player} and members[right] - {player}:
                    reopenable.add(left)
                if members[right] == {player} and members[left] - {player}:
                    reopenable.add(right)
        actions = []
        for key, piece in self.pieces.items():
            if piece["player"] != player:
                continue
            start = piece["position"]
            for path in self._paths(piece):
                crossed = [edge(first, second) for first, second in zip([start, *path[:-1]], path)]
                broken = [wall for wall in crossed if wall in self.walls]
                if len(broken) > self.breakers[player]:
                    continue
                # Keep preparation moves while an unused breaker can reopen an adjacent enemy region.
                if owners[start] == player and components[start] not in reopenable:
                    continue
                destination = path[-1]
                for neighbor in adjacent(destination):
                    wall = edge(destination, neighbor)
                    if wall in self.walls and wall not in broken:
                        continue
                    actions.append({"piece": key, "path": [list(position) for position in path],
                                    "wall": [list(position) for position in wall]})
        return actions

    def apply(self, player, action):
        if not isinstance(action, dict) or action.keys() != {"piece", "path", "wall"}:
            raise ValueError("말·이동 경로·설치할 벽을 지정하세요.")
        if (not isinstance(action["path"], list) or len(action["path"]) not in (1, 2)
                or not isinstance(action["wall"], list) or len(action["wall"]) != 2):
            raise ValueError("한두 칸의 경로와 인접한 두 칸 사이의 벽을 지정하세요.")
        path = [cell(position) for position in action["path"]]
        wall = edge(*action["wall"])
        normalized = {"piece": action["piece"], "path": [list(position) for position in path],
                      "wall": [list(position) for position in wall]}
        if normalized not in self.legal_actions(player):
            raise ValueError("현재 판에서 가능한 이동과 벽 설치를 선택하세요.")
        piece = self.pieces[action["piece"]]
        start = piece["position"]
        crossed = [edge(first, second) for first, second in zip([start, *path[:-1]], path)]
        broken = next((crossing for crossing in crossed if crossing in self.walls), None)
        if broken is not None:
            self.walls.remove(broken)
            self.breakers[player] -= 1
        piece["position"] = path[-1]
        self.walls.add(wall)
        return {"piece": action["piece"], "path": [list(position) for position in path],
                "from": list(start), "to": list(path[-1]), "wall": [list(position) for position in wall],
                "broken": [list(position) for position in broken] if broken is not None else None,
                "breakers": self.breakers.copy()}


def play(match: Match) -> dict:
    if len(match.players) != 3:
        raise ValueError("벽바둑 2 감옥 매치는 참가자 세 명이 필요합니다.")
    match.relationship_reviews_enabled = False
    match.event("rules", RULES)
    game_number = 0
    history = []
    total_turns = 0

    def choose(player, phase, prompt, options, *, timed=False):
        default = encode(match.policy.choice(options))
        encoded = [encode(action) for action in options]
        def parse(text):
            action = json.loads(text)
            if not isinstance(action, dict):
                raise ValueError("JSON 행동 객체를 지정하세요.")
            if "position" in action:
                action["position"] = list(cell(action["position"]))
            if "path" in action:
                if not isinstance(action["path"], list):
                    raise ValueError("이동 경로는 좌표 배열이어야 합니다.")
                action["path"] = [list(cell(position)) for position in action["path"]]
            if "wall" in action:
                if not isinstance(action["wall"], list) or len(action["wall"]) != 2:
                    raise ValueError("벽의 두 칸을 지정하세요.")
                action["wall"] = [list(position) for position in edge(*action["wall"])]
            if action not in options:
                raise ValueError("제시된 유효 행동을 선택하세요.")
            return action

        def accepts(text):
            try:
                parse(text)
            except (ValueError, TypeError, RecursionError):
                return False
            return True

        times = {}
        answers = match.decide_together(phase, {player: Decision(
            prompt, default, options=encoded, valid=accepts,
        )}, response_times=times, record_actions=False)
        chosen = parse(answers[player])
        late = timed and times.get(player, 0) > 90_000_000_000
        if late:
            candidates = [action for action in options
                          if action["piece"] == chosen["piece"] and action["path"] == chosen["path"]]
            chosen = match.policy.choice(candidates)
        return chosen, late

    def game(players, order, round_number, replay):
        nonlocal game_number, total_turns
        game_number += 1
        current_game = game_number
        board = Board(players, order, round_number)
        context = {"game": current_game, "round": round_number}
        match.event("wall_setup", {**context, "replay": replay, "players": list(players), "order": list(order),
                                   "size": SIZE, "scores": dict.fromkeys(players, 0),
                                   "largest": dict.fromkeys(players, 0), **board.snapshot()})
        for player in (*order, *reversed(order)):
            options = board.placement_options(player)
            action, _ = choose(player, "wall_place",
                               f"벽바둑 2 {round_number}라운드 · 배치. 좌표는 (행,열) 1~7입니다. "
                               f"이번 순서는 {player}입니다. 공개 판 {encode(board.snapshot())}. "
                               "아래 유효한 배치 중 자기 말 하나와 빈 칸을 선택하세요. "
                               "상대의 이동과 벽 설치를 예상해 가장 넓은 영역과 생존을 노리세요.", options)
            board.place(player, action)
            match.event("wall_place", {**context, "player": player, **action}, actor=player)
        turn = 0
        reason = "separated"
        while not board.separated():
            available = {player: board.legal_actions(player) for player in order}
            if not any(available.values()):
                reason = "stalemate"
                break
            player = order[turn % len(order)]
            turn += 1
            total_turns += 1
            match.event("wall_turn", {**context, "turn": turn, "player": player})
            options = available[player]
            if not options:
                positions = {piece["position"] for piece in board.pieces.values() if piece["player"] == player}
                isolated = all(territory["owner"] == player for territory in board.territories()
                               if any(tuple(position) in positions for position in territory["cells"]))
                match.event("wall_pass", {**context, "turn": turn, "player": player,
                                          "reason": "isolated" if isolated else "no_moves"}, actor=player)
                continue
            scores, largest = board.scores()
            action, late = choose(
                player, "wall_move",
                f"벽바둑 2 {round_number}라운드 {turn}턴. {player}의 차례입니다. "
                f"공개 판 {encode(board.snapshot())}. 현재 확정 영역 {encode(scores)}, 최대 단일 영역 {encode(largest)}. "
                "상대가 다음에 가둘 수 있는 말과 본인이 확보할 영역을 비교해 생존을 노리세요. "
                "이 판의 승리 판정은 전체 영역 합계, 최대 단일 영역 순입니다. "
                "아래 유효 행동 중 말·이동 경로·도착 칸 옆에 설치할 벽을 하나 선택하세요. "
                "경로에는 출발 칸을 제외한 지나갈 칸을 순서대로 넣습니다. "
                "경로에 벽이 포함되면 남은 벽 부수기를 사용합니다. 제자리 이동이나 다른 말 뛰어넘기는 불가능합니다. "
                "90초를 넘기면 유효한 이동은 유지하되 벽은 가능한 면 중 임의로 정합니다.",
                options, timed=True,
            )
            if late:
                match.event("wall_timeout", {**context, "turn": turn, "player": player, "seconds": 90})
            moved = board.apply(player, action)
            scores, largest = board.scores()
            match.event("wall_move", {**context, "turn": turn, "player": player, **moved,
                                      "scores": scores, "largest": largest}, actor=player)
        scores, largest = board.scores(stalemate=reason == "stalemate")
        ranking = board.ranking(stalemate=reason == "stalemate")
        summary = {**context, "replay": replay, "players": list(players), "order": list(order),
                   "scores": scores, "largest": largest,
                   "territories": board.territories(stalemate=reason == "stalemate"),
                   "ranking": ranking, "winner": ranking[0][0] if len(ranking[0]) == 1 else None,
                   "turns": turn, "reason": reason}
        match.event("wall_end", summary)
        history.append(summary)
        return ranking, scores, largest

    def ranked_game(players, order, round_number, replay=0):
        ranking, scores, largest = game(players, order, round_number, replay)
        resolved = []
        for tied in ranking:
            if len(tied) == 1:
                resolved.extend(tied)
                continue
            reversed_order = [player for player in reversed(order) if player in tied]
            match.event("wall_replay", {"round": round_number, "players": tied,
                                        "order": reversed_order, "replay": replay + 1})
            extra, _, _ = ranked_game(tied, reversed_order, round_number, replay + 1)
            resolved.extend(extra)
        return resolved, scores, largest

    first_order = match.rng.sample(list(match.players), len(match.players))
    first_ranking, first_scores, first_largest = ranked_game(list(match.players), first_order, 1)
    second_order = first_ranking[1:]
    match.event("wall_advance", {"survivor": first_ranking[0], "players": second_order,
                                "order": second_order, "round": 2})
    second_ranking, second_scores, second_largest = ranked_game(second_order, second_order, 2)
    ranking = [first_ranking[0], *second_ranking]
    survivors, eliminated = ranking[:2], ranking[2:]
    awards = {player: int(player in survivors) for player in match.players}
    return {"ranking": ranking, "survivors": survivors, "eliminated": eliminated,
            "scores": first_scores, "largest": first_largest, "second_scores": second_scores,
            "second_largest": second_largest, "rounds": 2, "turns": total_turns, "games": history,
            "pieces_awarded": awards,
            "pieces": {player: match.pieces[player] + awards[player] for player in match.players}}
