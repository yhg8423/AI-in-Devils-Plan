"""A simultaneous race to solve one shared Slitherlink puzzle privately."""

from base64 import b64decode
from copy import deepcopy
import json

from ...match import Decision, Match, encode
from .puzzles import all_edges, board, judge, make_puzzle


SIZE = 7
WAIT = encode({"type": "wait"})

RULES = """울타리 치기 · 4인 개인전

모두 같은 7×7 문제를 풀며, 각자 그림에 선과 X를 그립니다.
가로·세로로 이웃한 점만 선으로 이으세요. 숫자 0~3은 해당 칸의 네 변 중 그어야 할 선의 수입니다.
빈칸은 선의 수를 제한하지 않습니다. 사용한 점에는 선이 정확히 2개 연결되어야 합니다.
갈림길·교차·막다른 길 없이 단 하나의 닫힌 고리를 만드세요. 모든 점을 지날 필요는 없습니다.
X는 선을 긋지 않겠다는 개인 메모이며 고리의 일부가 아닙니다.

답안은 자신만 볼 수 있습니다. 완성했다고 판단하면 버저를 눌러 현재 답안을 검사받습니다.
먼저 올바른 고리를 제출한 3명은 순서대로 생존을 확정하고, 남은 1명은 탈락합니다.
한 문제를 끝까지 함께 풀며 별도 라운드나 전체 시간 제한은 없습니다.
검사에 실패해도 답안을 지우거나 고쳐 다시 제출할 수 있습니다. 이는 이 시뮬레이션의 재시도 정책입니다.
같은 생각 구간의 버저는 저장된 응답 시간이 짧은 순서로 처리하며, 동률은 시작 시 공개한
시드 기반 우선순위를 따릅니다. 세 번째 생존자가 정해지면 이후 버저는 처리하지 않습니다.
생존자의 답안과 정답 고리는 경기가 끝나 3명이 생존한 뒤에만 모두 공개합니다.

매번 전체 답안을 교체하는 JSON 행동을 제출하세요.
{"type":"draw","edges":[["H",0,0]],"crosses":[["V",0,0]],"submit":false}
위 예에서 H는 (행0,열0)과 (행0,열1), V는 (행0,열0)과 (행1,열0)을 잇습니다.
행·열은 그림의 점 좌표 0~7이며, H의 열과 V의 행은 0~6입니다.
edges는 그을 선, crosses는 X를 표시할 변입니다. 같은 변에 선과 X를 함께 둘 수 없습니다.
수정할 때 남길 선과 X를 모두 포함하세요. 빠진 표시는 지워집니다. crosses는 생략할 수 있습니다.
submit:true이면 이 답안을 그린 직후 버저를 눌러 제출하고, false이면 작업만 저장합니다.
{"type":"wait"}는 현재 답안을 그대로 둡니다. 형식 오류도 현재 답안을 유지하며 정답으로 보정하지 않습니다.
대화·협상·관계 평가는 없습니다. 호출 상한이 끝나면 스크립트 시연 행동으로 이어갑니다.
"""


def parse_action(text, size=SIZE):
    value = json.loads(text)
    if value == {"type": "wait"}:
        return value
    if (not isinstance(value, dict) or not {"type", "edges", "submit"} <= set(value)
            or not set(value) <= {"type", "edges", "crosses", "submit"}
            or value["type"] != "draw" or type(value["submit"]) is not bool):
        raise ValueError("전체 선·X와 submit 여부를 draw JSON으로 지정하세요.")
    allowed = set(all_edges(size, size))

    def marks(items):
        if (not isinstance(items, list) or len(items) > len(allowed)
                or any(not isinstance(edge, list) or len(edge) != 3
                       or not isinstance(edge[0], str) or edge[0] not in {"H", "V"}
                       or type(edge[1]) is not int or type(edge[2]) is not int
                       or tuple(edge) not in allowed for edge in items)):
            raise ValueError("그림 안에서 이웃한 두 점을 잇는 H·V 변만 지정하세요.")
        unique = set(map(tuple, items))
        if len(unique) != len(items):
            raise ValueError("같은 변은 한 번만 지정하세요.")
        return sorted(unique)

    edges, crosses = marks(value["edges"]), marks(value.get("crosses", []))
    if set(edges) & set(crosses):
        raise ValueError("같은 변에 선과 X를 함께 둘 수 없습니다.")
    return {"type": "draw", "edges": [list(edge) for edge in edges],
            "crosses": [list(edge) for edge in crosses], "submit": value["submit"]}


def _accepts(text):
    try:
        parse_action(text)
        return True
    except (ValueError, TypeError, RecursionError):
        return False


def play(match: Match):
    players = list(match.players)
    if len(players) != 4 or len(set(players)) != 4:
        raise ValueError("울타리 치기에는 서로 다른 참가자 4명이 필요합니다.")
    match.relationship_reviews_enabled = False
    # Explicit current-state prompts and own PNGs prevent private boards surviving in another history.
    match.model_observations = lambda name, events: [event for event in events if event.msg_type == "rules"]
    priority = match.rng.sample(players, len(players))
    puzzle = make_puzzle(match.rng.randrange(2 ** 32), size=SIZE)
    public_board = board(puzzle)
    puzzle_id = public_board["id"]
    states = {name: {"edges": [], "crosses": [], "board": public_board} for name in players}
    attempts, last_verdict = dict.fromkeys(players, 0), dict.fromkeys(players, None)
    finishes, winners, window = [], [], 0
    match.event("rules", RULES)
    match.event("fence_setup", {"version": 1, "players": players, "priority": priority,
                                "size": SIZE, "survivors": 3})
    match.event("fence_puzzle", {"puzzle": {"id": puzzle_id, "size": SIZE, "board": public_board}})
    while len(winners) < 3:
        window += 1
        active = [name for name in players if name not in winners]
        match.event("fence_window", {"window": window, "active": active})
        # Draw for every active player even when a live response supplies its own persisted timing.
        scripted_times = {name: match.policy.randrange(1_000_000_000, 60_000_000_000) for name in active}
        decisions = {name: Decision(
            f"생각 구간 {window} · {name}. 같은 7×7 울타리 문제를 푸는 개인전입니다.\n"
            f"생존 확정 순서: {encode(winners)}. 아직 참가 중: {encode(active)}. "
            f"공개 버저 횟수: {encode(attempts)}. 동률 우선순위: {encode(priority)}.\n"
            f"내 현재 작업: 선 {len(states[name]['edges'])}개, X {len(states[name]['crosses'])}개. "
            f"내 마지막 검사 결과: {encode(last_verdict[name])}.\n"
            "첨부 그림은 공개 문제와 나의 현재 선·X를 합친 것입니다. 다른 사람의 작업이나 정답은 보이지 않습니다. "
            "숫자마다 네 변의 선 수를 맞추고, 각 사용한 점에 선 2개가 만나는 하나의 닫힌 고리를 만드세요. "
            "빈칸은 선 수의 제한이 없고 모든 점을 지날 필요는 없습니다.\n"
            '전체 답안을 {"type":"draw","edges":[["H",0,0]],"crosses":[],"submit":false}로 교체하세요. '
            "그림의 점 좌표는 행·열 0~7입니다. H r c는 (r,c)-(r,c+1), V r c는 (r,c)-(r+1,c)입니다. "
            "H의 열과 V의 행은 0~6이며, 나머지 좌표는 0~7입니다. 중복 변이나 선·X 겹침은 허용하지 않습니다. "
            "남길 선과 X를 매번 모두 포함하세요. 빠진 표시는 지워집니다. crosses는 생략할 수 있습니다. "
            '완성했으면 submit:true로 즉시 버저를 함께 누르세요. 현재 답안을 유지하려면 {"type":"wait"}를 제출하세요. '
            "검사에 실패해도 같은 문제를 수정해 다시 제출할 수 있습니다.",
            encode({"type": "draw", "edges": puzzle["solution"], "crosses": [], "submit": True}),
            valid=_accepts, invalid_default=WAIT) for name in active}
        elapsed = {}
        replies = match.decide_together("fence_draw", decisions, response_times=elapsed,
            images_by_player={name: (b64decode(states[name]["board"]["image"].partition(",")[2], validate=True),)
                              for name in active})
        submitting = []
        for name in active:
            action = parse_action(replies[name])
            if action["type"] == "wait":
                continue
            states[name] = {"edges": action["edges"], "crosses": action["crosses"],
                            "board": board(puzzle, action["edges"], action["crosses"])}
            match.event("fence_board", {"player": name, "window": window, **states[name],
                                        "submitted": action["submit"]}, private=[name], actor=name)
            if action["submit"]:
                submitting.append(name)
        submitting.sort(key=lambda name: (elapsed.get(name, scripted_times[name]), priority.index(name)))
        for name in submitting:
            attempts[name] += 1
            timing = elapsed.get(name, scripted_times[name])
            common = {"player": name, "window": window, "attempt": attempts[name], "elapsed_ns": timing}
            match.event("fence_buzz", common, actor=name)
            correct = judge(puzzle, states[name]["edges"])
            last_verdict[name] = correct
            match.event("fence_verdict", {**common, "correct": correct,
                                          "reason": None if correct else "invalid_loop"}, actor=name)
            if correct:
                winners.append(name)
                finish = {**common, "rank": len(winners)}
                finishes.append(finish)
                match.event("fence_finish", finish)
                if len(winners) == 3:
                    break
    match.event("fence_reveal", {"boards": deepcopy(states), "solution": puzzle["solution"], "puzzle_id": puzzle_id})
    ranking = winners + [name for name in players if name not in winners]
    return {"ranking": ranking, "ranking_groups": [[name] for name in ranking], "survivors": winners,
            "eliminated": ranking[3:], "scores": {name: int(name in winners) for name in players},
            "finish_turns": {finish["player"]: finish["window"] for finish in finishes},
            "finishes": finishes, "turns": window, "attempts": attempts, "pieces": match.pieces.copy()}
