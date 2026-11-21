"""Race to assemble three privately editable reflection-symmetric silhouettes."""

from base64 import b64decode
from copy import deepcopy
import json

from ...match import Decision, Match, encode
from .puzzles import COLORS, align_placement, assembled_shape, board, judge, make_puzzles, placement_polygon, reflection_axes


WAIT = encode({"type": "wait"})
MAX_ACTION_SIZE = 8192

RULES = """대칭 퍼즐 · 개인전

파랑·빨강·초록, 세 색의 조각을 각각 하나의 선대칭 도형으로 만드세요.
각 색의 조각을 빠짐없이 한 번씩 쓰고, 서로 겹치거나 떨어지지 않게 변끼리 이어 붙여야 합니다.
대칭은 조각의 경계가 아닌 전체 도형과 빈 공간의 윤곽으로 판단합니다.
어느 방향이든 반사 대칭축이 하나 이상 있으면 됩니다. 대칭축이 여러 개여도 됩니다.
정해진 정답 윤곽을 따라 만드는 문제가 아니며, 조건을 만족하는 다른 모양도 정답입니다.
세 색을 모두 완성한 뒤 버저를 눌러 한 번에 검사받으세요.
참가자 수보다 한 명 적은 인원이 올바르게 완성하면 경기가 끝나고, 남은 마지막 한 명이 탈락합니다.

파랑은 2개, 빨강과 초록은 각각 3개인 실제 다각형 조각을 사용합니다.
조각은 뒤집을 수 없고 시계 방향으로 원하는 각도만큼 회전할 수 있습니다.
정해진 격자나 테두리 없이 조각을 자유롭게 놓으세요. x는 오른쪽, y는 아래쪽으로 증가하는 연속 좌표입니다.
회전 뒤 조각의 가장 왼쪽·위쪽을 기준으로 위치를 잡으므로, x/y는 회전한 조각 경계 상자의 왼쪽 위입니다.
음수와 소수 좌표도 허용하며, 그림의 표시 범위는 현재 배치에 맞춰 자동으로 조절됩니다.
작업 중에는 미완성 배치나 겹침을 저장할 수 있습니다.
매번 세 색의 전체 배치를 다음 JSON으로 교체하세요. 빠진 조각은 작업판에서 치웁니다.
{"type":"arrange","placements":{"blue":[{"piece":"B1","x":0,"y":1,"rotation":90}],"red":[],"green":[]},"submit":false}
세 색의 키를 모두 쓰세요. 좌표 배치에는 조각 ID·유한한 수 x/y·rotation만 지정합니다. 뒤집기 옵션은 없습니다.
각도는 360도로 나눈 나머지를 사용합니다.
정확히 붙일 때는 조각 그림의 꼭짓점 v번호와 변 e번호를 선택할 수 있습니다.
변 e번호는 같은 번호의 꼭짓점에서 다음 꼭짓점으로 가는 변입니다. 마지막 변은 v0으로 돌아갑니다.
좌표 배치 대신 {"piece":"B2","edge":0,"vertex":0,"to_piece":"B1","to_edge":1,"to_vertex":1} 형식도 허용합니다.
먼저 이 색의 목록에 배치한 to_piece의 변과 반대 방향으로 edge를 맞추고, vertex를 to_vertex에 붙입니다.
vertex와 to_vertex는 선택한 변의 끝점일 필요가 없습니다. 조각은 회전·이동만 하고 크기는 바꾸지 않습니다.
어떤 조각·변·꼭짓점을 붙일지는 직접 고르세요. 이 기능은 정답을 찾아주거나 잘못 고른 변을 고치지 않습니다.
submit:true이면 배치와 버저를 한 행동으로 제출합니다. false이면 작업만 저장합니다.
{"type":"wait"}는 모든 작업을 그대로 둡니다. 형식 오류도 이전 작업을 보존하며 정답으로 보정하지 않습니다.

작업 그림은 자신만 볼 수 있고, 다른 사람의 완성 그림도 경기 종료 전에는 공개하지 않습니다.
버저 검사에서는 세 색을 모두 완성했는지만 공개하며, 색별 정답 여부는 알려주지 않습니다.
실패하면 수정해 다시 제출할 수 있습니다. 이는 이 시뮬레이션의 재시도 정책입니다.
같은 생각 구간의 버저는 저장된 응답 시간이 짧은 순서로 처리하고, 동률은 시작 시 공개한
시드 기반 우선순위를 따릅니다. 마지막 생존 자리가 채워지면 뒤의 버저는 처리하지 않습니다.
별도 라운드·전체 시간 제한·대화·관계 평가는 없습니다. 호출 상한이 끝나면 스크립트 시연 행동으로 이어갑니다.
"""


def parse_action(text, puzzles):
    if not isinstance(text, str) or len(text) > MAX_ACTION_SIZE:
        raise ValueError("대칭 퍼즐 행동이 너무 크거나 문자열이 아닙니다.")
    value = json.loads(text)
    if value == {"type": "wait"}:
        return value
    if (not isinstance(value, dict) or set(value) != {"type", "placements", "submit"}
            or value["type"] != "arrange" or type(value["submit"]) is not bool
            or not isinstance(value["placements"], dict) or set(value["placements"]) != set(COLORS)):
        raise ValueError("세 색의 전체 placements와 submit 여부를 arrange JSON으로 지정하세요.")
    normalized = {}
    for puzzle in puzzles:
        placements = value["placements"][puzzle["id"]]
        if not isinstance(placements, list) or len(placements) > len(puzzle["pieces"]):
            raise ValueError("해당 색의 조각 배치 목록을 지정하세요.")
        used, resolved = set(), []
        for placement in placements:
            if isinstance(placement, dict) and "to_piece" in placement:
                placement = align_placement(puzzle, placement, resolved)
            placement_polygon(puzzle, placement)
            if placement["piece"] in used:
                raise ValueError("각 조각 ID는 한 번만 지정하세요.")
            used.add(placement["piece"])
            resolved.append(placement)
        normalized[puzzle["id"]] = sorted(resolved, key=lambda placement: placement["piece"])
    return {"type": "arrange", "placements": normalized, "submit": value["submit"]}


def _accepts(text, puzzles):
    try:
        parse_action(text, puzzles)
        return True
    except (ValueError, TypeError, RecursionError):
        return False


def play(match: Match):
    players = list(match.players)
    if len(players) not in (3, 4) or len(set(players)) != len(players):
        raise ValueError("대칭 퍼즐에는 서로 다른 참가자 3명 또는 4명이 필요합니다.")
    match.relationship_reviews_enabled = False
    match.model_observations = lambda name, events: [event for event in events if event.msg_type == "rules"]
    priority = match.rng.sample(players, len(players))
    puzzles = make_puzzles(match.rng.randrange(2 ** 32))
    initial_boards = {puzzle["id"]: board(puzzle) for puzzle in puzzles}
    states = {name: {"placements": {color: [] for color in COLORS}, "boards": initial_boards.copy()}
              for name in players}
    attempts, last_verdict = dict.fromkeys(players, 0), dict.fromkeys(players, None)
    finishes, winners, window = [], [], 0
    slots = len(players) - 1
    match.event("rules", RULES)
    match.event("sym_setup", {"version": 2, "players": players, "priority": priority,
                              "survivors": slots, "mode": "polygons"})
    match.event("sym_puzzles", {"puzzles": [{"id": puzzle["id"], "label": puzzle["label"],
        "piece_ids": [piece["id"] for piece in puzzle["pieces"]], "board": initial_boards[puzzle["id"]]}
        for puzzle in puzzles]})
    while len(winners) < slots:
        window += 1
        active = [name for name in players if name not in winners]
        match.event("sym_window", {"window": window, "active": active})
        scripted_times = {name: match.policy.randrange(1_000_000_000, 60_000_000_000) for name in active}
        decisions = {name: Decision(
            f"생각 구간 {window} · {name}. 파랑·빨강·초록 세 대칭 퍼즐을 모두 완성하세요.\n"
            f"생존 확정 순서: {encode(winners)}. 아직 참가 중: {encode(active)}. "
            f"공개 버저 횟수: {encode(attempts)}. 동률 우선순위: {encode(priority)}.\n"
            f"내 마지막 전체 검사 결과: {encode(last_verdict[name])}. "
            f"내 이전 작업 배치: {encode(states[name]['placements'])}\n"
            "첨부 이미지 세 장은 차례로 blue·red·green의 조각 보관함과 나의 현재 작업판입니다. "
            "다른 참가자의 작업과 완성 예는 제공되지 않습니다. 각 색의 모든 조각을 겹침 없이 변으로 연결하고, "
            "빈 공간을 포함한 전체 모양에 방향 제한 없이 하나 이상의 반사 대칭축을 만드세요. "
            "조각 경계 자체가 대칭일 필요는 없으며, 세 색 모두 조건을 만족해야 생존합니다.\n"
            "그림의 x는 오른쪽, y는 아래쪽으로 증가하는 연속 좌표입니다. 음수·소수도 허용합니다. "
            "격자나 정해진 판의 테두리는 없으며 그림의 표시 범위는 배치에 맞춰 바뀝니다. "
            "시계 방향으로 원하는 각도를 회전할 수 있고 뒤집기는 금지합니다. "
            "x/y는 회전한 조각 경계 상자의 왼쪽 위입니다. "
            "정밀한 접합은 그림의 v꼭짓점/e변 번호로 선택하세요. "
            "e번호는 v번호에서 다음 꼭짓점으로 향하는 변입니다. "
            '{"piece":"B2","edge":0,"vertex":0,"to_piece":"B1","to_edge":1,"to_vertex":1}은 '
            "먼저 목록에 배치한 B1의 e1과 B2의 e0을 반대 방향으로 맞춘 뒤 B2의 v0을 B1의 v1에 붙입니다. "
            "형식 예시이며 이 변들이 정답이라는 뜻은 아닙니다. 변과 꼭짓점은 직접 고르세요. "
            "접합 기능은 선택한 변의 방향과 꼭짓점만 맞추며 겹침이나 대칭을 자동으로 고치지 않습니다.\n"
            '{"type":"arrange","placements":{"blue":[{"piece":"B1","x":0,"y":1,"rotation":90}],'
            '"red":[],"green":[]},"submit":false} 형식으로 세 색 전체 작업을 교체하세요. '
            "유지할 조각을 모두 포함하고 좌표 배치나 위의 접합 형식을 쓰세요. 빠진 조각은 치워지며 빈 목록은 그 색을 비웁니다. "
            "submit:true이면 세 색을 검사받도록 즉시 버저도 누릅니다. false이면 작업만 저장합니다. "
            '{"type":"wait"}는 전체 작업을 그대로 유지합니다. 실패한 답안은 고쳐 다시 제출할 수 있습니다.',
            encode({"type": "arrange", "placements": {puzzle["id"]: puzzle["solution"] for puzzle in puzzles},
                    "submit": True}), valid=lambda action: _accepts(action, puzzles), invalid_default=WAIT)
            for name in active}
        elapsed = {}
        replies = match.decide_together("symmetry_arrange", decisions, response_times=elapsed,
            images_by_player={name: tuple(b64decode(states[name]["boards"][puzzle["id"]]["image"].partition(",")[2],
                                                     validate=True) for puzzle in puzzles) for name in active})
        submitting = []
        for name in active:
            action = parse_action(replies[name], puzzles)
            if action["type"] == "wait":
                continue
            states[name] = {"placements": action["placements"],
                           "boards": {puzzle["id"]: board(puzzle, action["placements"][puzzle["id"]]) for puzzle in puzzles}}
            match.event("sym_board", {"player": name, "window": window, **states[name],
                                      "submitted": action["submit"]}, private=[name], actor=name)
            if action["submit"]:
                submitting.append(name)
        submitting.sort(key=lambda name: (elapsed.get(name, scripted_times[name]), priority.index(name)))
        for name in submitting:
            attempts[name] += 1
            common = {"player": name, "window": window, "attempt": attempts[name],
                      "elapsed_ns": elapsed.get(name, scripted_times[name])}
            match.event("sym_buzz", common, actor=name)
            correct = all(judge(puzzle, states[name]["placements"][puzzle["id"]]) for puzzle in puzzles)
            last_verdict[name] = correct
            match.event("sym_verdict", {**common, "correct": correct, "reason": None if correct else "not_symmetric"}, actor=name)
            if correct:
                winners.append(name)
                finish = {**common, "rank": len(winners)}
                finishes.append(finish)
                match.event("sym_finish", finish)
                if len(winners) == slots:
                    break
    scores, axes = {}, {}
    for name in players:
        axes[name] = {}
        for puzzle in puzzles:
            shape = assembled_shape(puzzle, states[name]["placements"][puzzle["id"]])
            found = reflection_axes(shape)
            axes[name][puzzle["id"]] = found[0] if found else None
        scores[name] = sum(axis is not None for axis in axes[name].values())
    match.event("sym_reveal", {"boards": deepcopy(states), "axes": axes})
    ranking = winners + [name for name in players if name not in winners]
    return {"ranking": ranking, "ranking_groups": [[name] for name in ranking], "survivors": winners,
            "eliminated": ranking[-1:], "scores": scores, "finish_turns": {row["player"]: row["window"] for row in finishes},
            "finishes": finishes, "turns": window, "attempts": attempts, "pieces": match.pieces.copy()}
