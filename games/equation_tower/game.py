"""Public stack puzzles, descending move bids, and timed demonstrations.

The broadcast block inventory/initial layout are not public. This simulator
uses 20 fixed blocks, seeded five-per-position dealing, normal arithmetic
precedence, and zero-score overtime for only the tied lowest players.
Rules source: https://namu.moe/w/데블스%20플랜:%20데드%20어게인/5일차#s-5.1
Inventory, five-per-position dealing, ordinary precedence, bid upper bounds,
simultaneous-buzzer ordering, and overtime resets are explicit simulator policy.
"""

from copy import deepcopy
from fractions import Fraction
from io import BytesIO
import json

import pygame

from ..match import Decision, Match, encode


GOAL = 7
TIMING = {"opening": 300, "counter": 120, "execution": 120}
VALUES = (2, 3, 5, 7)
OPERATORS = (("n", None, ""), ("add", "+", "+"), ("sub", "-", "−"),
             ("mul", "*", "×"), ("div", "/", "÷"))
BLOCKS = {f"{prefix}{value}": {"operator": operator, "value": value, "label": f"{label}{value}"}
          for prefix, operator, label in OPERATORS for value in VALUES}
WAIT = encode({"type": "wait"})
EMPTY_PLAN = encode({"moves": []})
RULES = """수식의 탑 · 2~3인 공개 퍼즐 감옥 매치

매 문제에는 타깃 넘버와 목표 층수가 공개됩니다. 네 자리의 블록을 옮겨 정확히 그 높이의 탑을
만들고 타깃 값을 완성하세요. 각 stack은 아래→위 순서의 블록 ID 배열입니다.
1회 이동은 한 자리의 맨 위에서 연속된 블록을 원하는 개수만큼 들어 다른 자리 위에 놓는 것입니다.
묶음을 상하로 뒤집을 수 있고, 제자리에서 두 개 이상을 뒤집는 것도 1회입니다.
완성한 탑은 맨 위가 기호 없는 숫자, 그 아래는 기호 블록이어야 합니다.
위→아래로 수식을 읽고 ×·÷를 +·−보다 먼저 계산합니다. 분수도 정확하게 계산합니다.

첫 입찰은 공개 후 300초 이내 버저로 이동 횟수를 제출합니다. 아무도 입찰하지 않으면 다음 문제입니다.
첫 입찰 즉시 다른 참가자는 새로 120초 동안 한 번씩 더 적은 횟수를 부를 수 있습니다.
응답 시간 순으로 처리하며 현재 최저보다 적어야 합니다. 같은 시각은 공개한 추첨 순서로 처리합니다.
최저 입찰자만 120초 이내 실연 계획을 한 번 제출합니다. 입찰 횟수 이내에 완성하면 성공합니다.
최초 입찰자가 도전하면 성공 +1점/실패 −1점, 추가 입찰자가 도전하면 성공 +2점/실패 −2점입니다.
시간을 넘긴 계획은 실행하지 않습니다. 형식·이동·횟수 오류는 실패하며 앞서 옮긴 유효 블록은 유지합니다.
블록 상태는 성공·실패 모두 다음 문제로 이어집니다. 대화·협상·관계 평가는 없습니다.

누군가 7점 이상이면 최하위 한 명이 탈락하고 나머지는 생존합니다.
최하위 동점이면 다른 참가자는 생존을 고정하고 동점자만 0점부터 7점까지 새 승부를 진행합니다.
최초 승부 1위만 피스 3개를 받습니다. 모델 호출 예산이 끝나면 스크립트 시연으로 이어갑니다.

시뮬레이터 가정: 방송의 전체 블록·첫 배치를 확인할 수 없어 무기호와 +,−,×,÷ 각각에 2,3,5,7을
결합한 20개 고정 블록을 사용합니다. 시드로 섞어 네 자리에 5개씩 배치합니다.
산술 우선순위·입찰 상한 방식·동률 시각 순서·연장 점수 초기화도 공개 자료의 빈틈을 보완한 정책입니다.
"""


class Board:
    def __init__(self, stacks):
        if (not isinstance(stacks, (list, tuple)) or len(stacks) != 4
                or any(not isinstance(stack, (list, tuple)) for stack in stacks)):
            raise ValueError("네 자리의 블록 배열이 필요합니다.")
        ids = [block for stack in stacks for block in stack]
        if len(ids) != len(BLOCKS) or any(not isinstance(block, str) for block in ids) or set(ids) != set(BLOCKS):
            raise ValueError("20개 고유 블록을 각각 한 번 배치하세요.")
        self.stacks = [list(stack) for stack in stacks]

    def snapshot(self):
        return [stack.copy() for stack in self.stacks]

    def move(self, action):
        if not isinstance(action, dict) or set(action) != {"from", "to", "count", "flip"}:
            raise ValueError("from, to, count, flip을 지정하세요.")
        source, destination, count, flip = (action[key] for key in ("from", "to", "count", "flip"))
        if (type(source) is not int or type(destination) is not int or not 1 <= source <= 4
                or not 1 <= destination <= 4 or type(count) is not int
                or not 1 <= count <= len(self.stacks[source - 1]) or type(flip) is not bool):
            raise ValueError("자리 1~4, 유효한 상단 블록 수, 불리언 flip이 필요합니다.")
        if source == destination and (not flip or count < 2):
            raise ValueError("제자리에서는 두 개 이상을 뒤집어야 합니다.")
        bundle = self.stacks[source - 1][-count:]
        del self.stacks[source - 1][-count:]
        self.stacks[destination - 1].extend(reversed(bundle) if flip else bundle)

    def legal_moves(self):
        return [{"from": source + 1, "to": destination + 1, "count": count, "flip": flip}
                for source, stack in enumerate(self.stacks) for destination in range(4)
                for count in range(1, len(stack) + 1) for flip in (False, True)
                if source != destination or (flip and count > 1)]

    def expression(self, index):
        blocks = [BLOCKS[key] for key in reversed(self.stacks[index])]
        if not blocks or blocks[0]["operator"] is not None or any(b["operator"] is None for b in blocks[1:]):
            return None, None
        total, term = Fraction(0), Fraction(blocks[0]["value"])
        for block in blocks[1:]:
            operator, value = block["operator"], block["value"]
            if operator in ("+", "-"):
                total += term
                term = Fraction(value if operator == "+" else -value)
            elif operator == "*":
                term *= value
            else:
                term /= value
        return "".join(block["label"] for block in blocks), total + term

    def solution(self, target, height):
        for index, stack in enumerate(self.stacks):
            expression, value = self.expression(index)
            if len(stack) == height and value == target:
                return expression, value
        return None, None


def board_image(board, target=None, height=None):
    """Use the repository's pygame raster convention for every decision phase."""
    pygame.font.init()
    surface = pygame.Surface((1024, 900))
    surface.fill("#101820")
    heading, font = pygame.font.Font(None, 36), pygame.font.Font(None, 25)
    surface.blit(heading.render("TOWER OF EQUATIONS", True, "#f2e9da"), (30, 24))
    surface.blit(font.render(f"Target: {target if target is not None else '-'}    Height: {height or '-'}",
                             True, "#efc674"), (30, 72))
    surface.blit(font.render("Read top to bottom. Multiply/divide before add/subtract.", True, "#d7dce1"), (30, 110))
    colors = {None: "#3159a6", "+": "#a42e3e", "-": "#bc9c29", "*": "#75419b", "/": "#287853"}
    step = min(45, 660 // max(1, max(map(len, board.stacks))))
    for index, stack in enumerate(board.stacks):
        x = 30 + index * 249
        pygame.draw.rect(surface, "#72808e", (x, 824, 220, 3))
        for level, block_id in enumerate(stack):
            block = BLOCKS[block_id]
            y = 823 - (level + 1) * step
            pygame.draw.rect(surface, colors[block["operator"]], (x, y, 220, step - 2))
            label = f"{block_id}  {block['operator'] or ''}{block['value']}"
            surface.blit(font.render(label, True, "#ffffff"), (x + 12, y + 3))
        surface.blit(font.render(f"Position {index + 1} / {len(stack)} blocks", True, "#f2e9da"), (x, 846))
    output = BytesIO()
    pygame.image.save(surface, output, "equation-tower.png")
    return output.getvalue()


def make_problem(board, rng):
    """Find a reachable target; retain its witness only for scripted fallback."""
    for _ in range(128):
        trial, path = Board(board.snapshot()), []
        for _ in range(10):
            action = rng.choice(trial.legal_moves())
            trial.move(action)
            path.append(action)
            for index, stack in enumerate(trial.stacks):
                if not 3 <= len(stack) <= 6 or len(path) < 2:
                    continue
                _, value = trial.expression(index)
                if (value is not None and value.denominator == 1 and 0 < value <= 999
                        and board.solution(value, len(stack))[0] is None):
                    return int(value), len(stack), path
    return constructive_problem(board)


def constructive_problem(board):
    """Build one of four distinct formulas absent from the current board."""
    patterns = ((17, ("mul5", "add3", "n2")), (38, ("mul7", "add5", "n3")),
                (13, ("mul2", "add3", "n7")), (19, ("mul7", "add2", "n5")))
    # With twenty blocks, at most three positions can have height three.
    target, blocks = next((target, blocks) for target, blocks in patterns if board.solution(target, 3)[0] is None)
    trial, path = Board(board.snapshot()), []
    def move(source, destination, count):
        action = {"from": source + 1, "to": destination + 1, "count": count, "flip": False}
        trial.move(action)
        path.append(action)
    if trial.stacks[0]:
        move(0, 1, len(trial.stacks[0]))
    for block_id in blocks:
        source = next(i for i, stack in enumerate(trial.stacks) if block_id in stack)
        above = len(trial.stacks[source]) - trial.stacks[source].index(block_id) - 1
        if above:
            move(source, 1 if source != 1 else 2, above)
        move(source, 0, 1)
    return target, 3, path


def parse_bid(text):
    action = json.loads(text)
    if action == {"type": "wait"}:
        return action
    if (not isinstance(action, dict) or set(action) != {"type", "moves"}
            or action["type"] != "bid" or type(action["moves"]) is not int or action["moves"] < 1):
        raise ValueError("wait 또는 양의 정수 moves를 가진 bid가 필요합니다.")
    return action


def accepts_bid(text):
    try:
        parse_bid(text)
        return True
    except (ValueError, TypeError, RecursionError):
        return False


def accepts_plan(text):
    # Shape validation belongs in replay so an illegal later move retains its prefix.
    return isinstance(text, str)


def execute(board, text, target, height, allowed, *, late=False, on_move=None):
    used, reason = 0, "incorrect"
    if late:
        return {"success": False, "reason": "timeout", "used": used, "expression": None, "value": None}
    try:
        plan = json.loads(text)
        if not isinstance(plan, dict) or set(plan) != {"moves"} or not isinstance(plan["moves"], list):
            raise ValueError("moves 배열이 필요합니다.")
        for action in plan["moves"]:
            if used >= allowed:
                reason = "move_limit"
                break
            try:
                board.move(action)
            except (ValueError, TypeError, KeyError):
                reason = "invalid_move"
                break
            used += 1
            if on_move is not None:
                on_move(used, action)
        else:
            reason = "complete"
    except (ValueError, TypeError, RecursionError):
        reason = "invalid_plan"
    expression, value = board.solution(target, height)
    success = reason == "complete" and expression is not None
    if expression is None:
        expression, value = next((board.expression(i) for i, stack in enumerate(board.stacks)
                                  if len(stack) == height and board.expression(i)[0] is not None), (None, None))
    return {"success": success, "reason": "success" if success else "incorrect" if reason == "complete" else reason,
            "used": used, "expression": expression, "value": str(value) if value is not None else None}


def play(match: Match):
    players = list(match.players)
    if len(players) not in (2, 3) or len(set(players)) != len(players):
        raise ValueError("수식의 탑에는 서로 다른 2~3명이 필요합니다.")
    match.relationship_reviews_enabled = False
    match.model_observations = lambda name, events: [
        e for e in events if e.msg_type == "rules" or e.msg_type.startswith("tower_")
        or (e.msg_type in {"action", "decision_note", "invalid_action"}
            and (e.agent_name == name or (e.visible_to != "all" and name in e.visible_to)))]
    order = match.rng.sample(players, len(players))
    ids = list(BLOCKS)
    match.rng.shuffle(ids)
    board = Board([ids[index * 5:(index + 1) * 5] for index in range(4)])
    scores = dict.fromkeys(players, 0)
    match.event("rules", RULES)
    match.event("tower_setup", {"version": 1, "players": players.copy(), "order": order.copy(),
                               "stacks": board.snapshot(), "blocks": deepcopy(BLOCKS), "goal": GOAL,
                               "timing": TIMING.copy(), "discussion": False,
                               "fixture": "simulator-20-blocks", "assumptions": "20 fixed blocks; seeded five-per-stack deal; tied-lowest zero-score overtime"})
    active, safe, ranking, rounds, first_winner = players.copy(), [], [], 0, None
    while True:
        rounds += 1
        target, height, witness = make_problem(board, match.rng)
        match.event("tower_problem", {"round": rounds, "players": active.copy(), "scores": scores.copy(),
                                     "target": target, "height": height, "stacks": board.snapshot()})
        image = board_image(board, target, height)
        public = (f"수식의 탑 문제 {rounds}. 목표값 {target}, 높이 {height}. 공개 순서 {encode(order)}. "
                  f"참가자 {encode(active)}, 점수 {encode(scores)}, 생존 확정 {encode(safe)}.\n"
                  f"블록 {encode(BLOCKS)}\n현재 stacks 아래→위 {encode(board.snapshot())}.\n")

        def bids(stage, names, first=None):
            seconds = TIMING[stage]
            event = {"round": rounds, "stage": stage, "seconds": seconds}
            if first is not None:
                event["first"] = first.copy()
            match.event("tower_bid_window", event)
            scripted = {name: match.policy.randrange(1_000_000_000, 60_000_000_000) for name in names}
            decisions = {name: Decision(
                public + (f"최초 입찰: {seconds}초 이내 이동 횟수를 부르세요. " if stage == "opening" else
                          f"추가 입찰: 최초 입찰 {encode(first)}. {seconds}초 이내 더 적은 횟수를 한 번 부르세요. ")
                + '{"type":"bid","moves":3} 또는 {"type":"wait"}를 제출하세요. 해법은 입찰 후 직접 시연합니다.',
                encode({"type": "bid", "moves": len(witness)}) if stage == "opening" else WAIT,
                valid=accepts_bid, invalid_default=WAIT) for name in names}
            elapsed = {}
            answers = match.decide_together(f"tower_{stage}_bid", decisions, response_times=elapsed,
                                            images=(image,), max_reviews=0)
            return [(name, parse_bid(answers[name]), elapsed.get(name, scripted[name]))
                    for name in sorted(names, key=lambda n: (elapsed.get(n, scripted[n]), order.index(n)))
                    if elapsed.get(name, scripted[name]) <= seconds * 1_000_000_000]

        opening = next(((name, action, elapsed) for name, action, elapsed in bids("opening", active)
                        if action["type"] == "bid"), None)
        if opening is None:
            match.event("tower_skip", {"round": rounds, "reason": "no_bid", "stacks": board.snapshot()})
            continue
        name, action, elapsed = opening
        first = {"player": name, "moves": action["moves"]}
        selected, allowed, stake = name, action["moves"], 1
        match.event("tower_bid", {"round": rounds, **first, "first": True, "elapsed_ns": elapsed}, actor=name)
        for name, action, elapsed in bids("counter", [p for p in active if p != selected], first):
            if action["type"] == "bid" and action["moves"] < allowed:
                selected, allowed, stake = name, action["moves"], 2
                match.event("tower_bid", {"round": rounds, "player": name, "moves": allowed,
                                          "first": False, "elapsed_ns": elapsed}, actor=name)
        match.event("tower_challenge", {"round": rounds, "player": selected, "bid": allowed,
                                        "stake": stake, "seconds": TIMING["execution"]})
        times = {}
        plan = match.decide_together("tower_execute", {selected: Decision(
            public + f"실연자 {selected}, 허용 이동 {allowed}회, 총120초. 한 번에 계획 전체를 제출하세요. "
            '형식 {"moves":[{"from":1,"to":2,"count":1,"flip":false}]}. '
            "자리번호는1~4. 뒤집기는 선택한 상단 묶음의 순서를 뒤집습니다. 불법수 전 유효 이동은 유지됩니다.",
            encode({"moves": witness}), valid=accepts_plan, invalid_default=EMPTY_PLAN)},
            response_times=times, images=(image,), max_reviews=0)[selected]
        def moved(index, action):
            match.event("tower_move", {"round": rounds, "player": selected, "index": index,
                                       **action, "stacks": board.snapshot()}, actor=selected)
        verdict = execute(board, plan, target, height, allowed,
                          late=times.get(selected, 0) > TIMING["execution"] * 1_000_000_000, on_move=moved)
        change = stake if verdict["success"] else -stake
        scores[selected] += change
        match.event("tower_verdict", {"round": rounds, "player": selected, **verdict, "change": change,
                                      "scores": scores.copy(), "target": target, "height": height,
                                      "stacks": board.snapshot(), "allowed": allowed,
                                      "elapsed_ns": times.get(selected, 0)}, actor=selected)
        if max(scores[p] for p in active) < GOAL:
            continue
        ordered = sorted(active, key=lambda p: (-scores[p], order.index(p)))
        winner = ordered[0]
        first_winner = first_winner or winner
        lowest = [p for p in ordered if scores[p] == scores[ordered[-1]]]
        newly_safe = [p for p in ordered if p not in lowest]
        safe.extend(newly_safe)
        ranking.extend(newly_safe)
        tied = lowest if len(lowest) > 1 else []
        match.event("tower_advance", {"round": rounds, "winner": winner, "safe": safe.copy(),
                                      "tied": tied.copy(), "reset_scores": bool(tied)})
        if not tied:
            ranking.extend(lowest)
            break
        active = tied
        for name in active:
            scores[name] = 0
    awards = {name: 3 if name == first_winner else 0 for name in players}
    return {"ranking": ranking, "ranking_groups": [[name] for name in ranking], "survivors": ranking[:-1],
            "eliminated": ranking[-1:], "pieces_awarded": awards,
            "pieces": {name: match.pieces[name] + awards[name] for name in players},
            "rounds": rounds, "scores": scores.copy()}
