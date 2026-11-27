"""Race to prepare a rectangle count, buzz, and say it immediately."""

from base64 import b64decode
import json

from ...match import Decision, Match, encode
from .puzzles import board, make_puzzle


LIMIT_SECONDS = 300
VERSION = 2
ANSWER_SECONDS = 10
WAIT_WINDOWS = 3
INVALID_BUZZ = encode({"type": "buzz", "count": -1})

RULES = """네모 세기 · 4인 개인전

첨부된 격자의 칸을 더해 목표 합이 되는 축 정렬 직사각형의 수를 세세요.
정사각형·한 칸·판 전체도 포함하며 빈칸은 0입니다. 음수도 그대로 더하고, 정답이 0개일 수도 있습니다.
먼저 한 문제를 맞힌 참가자는 즉시 생존하고 이후 문제에서 빠집니다. 두 명이 생존하면 끝나며, 남은 두 명은 탈락합니다.
문제당 5분이며 버저 뒤에는 10초 안에 답해야 합니다. 오답자는 같은 문제에서 다시 누를 수 없습니다.
아무도 정답을 맞히지 못한 채 5분이 지나거나 전원이 오답이면 새 문제를 제시합니다.

시뮬레이션에서는 답을 준비한 뒤 JSON {"type":"buzz","count":0}으로 버저와 즉시 발언을 함께 제출합니다.
아직 준비되지 않았다면 {"type":"wait"}를 제출하세요. 답은 0 이상의 정수입니다.
한 생각 구간의 답은 동시에 비공개로 받으며, 실제 응답이 도착한 순서대로 버저를 처리합니다.
시드로 추첨한 공개 우선순위로 같은 시각의 버저 순서를 정합니다. 발언 시간은 0초로 기록합니다.
한 사람이 정답을 맞히면 뒤에 대기 중인 버저와 답은 공개하거나 판정하지 않습니다.
대기자만 다음 생각 구간에 참여하며, 전원 대기가 세 구간 쌓여도 새 문제로 넘어갑니다.
문제 그림은 모두에게 같고 모델에게 정답 수나 프로그램의 계산 결과는 제공하지 않습니다.
방송과 같은 숫자 판을 복제하지 않고 음수·0과 불가능한 목표 합을 포함한 자체 문제를 사용합니다.
대화·협상·관계 평가는 없습니다. 호출 상한이 끝나면 스크립트 시연 행동으로 이어갑니다.
"""

LEGACY_RULES = RULES.replace("네모 세기 · 4인 개인전", "네모 세기 · 유배지 개인전").replace(
    "먼저 한 문제를 맞힌 참가자는 즉시 생존하고 이후 문제에서 빠집니다. 두 명이 생존하면 끝나며, 남은 두 명은 탈락합니다.",
    "먼저 한 문제를 맞힌 참가자는 즉시 생존하고 이후 문제에서 빠집니다. 남은 마지막 한 명이 탈락합니다.",
)


def parse_action(text):
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("버저 또는 대기 JSON 객체가 필요합니다.")
    if value == {"type": "wait"}:
        return value
    if (set(value) != {"type", "count"} or value["type"] != "buzz"
            or type(value["count"]) is not int or abs(value["count"]) > 1_000_000):
        raise ValueError("버저에는 정수 count를 지정하세요.")
    return value


def _accepts(text):
    try:
        parse_action(text)
        return True
    except (ValueError, TypeError, RecursionError):
        return False


def play(match: Match):
    players = list(match.players)
    saved, saved_rules = None, None
    if match.resume_log is not None and match.resume_log.resume:
        saved = next((json.loads(row["content"]) for row in match.resume_log.events if row["msg_type"] == "rect_setup"), None)
        saved_rules = next((row["content"] for row in match.resume_log.events if row["msg_type"] == "rules"), None)
        if not isinstance(saved, dict):
            raise ValueError("재개할 네모 세기 준비 기록이 없습니다.")
    version = saved.get("version") if saved is not None else VERSION
    if type(version) is not int or version not in (1, 2):
        raise ValueError("지원하지 않는 네모 세기 기록 버전입니다.")
    puzzle_pack = saved.get("puzzle_pack", "authored_v1") if saved is not None else "full_grid_v2"
    if puzzle_pack not in ("authored_v1", "full_grid_v2"):
        raise ValueError("저장된 네모 세기 문제 구성이 올바르지 않습니다.")
    if len(set(players)) != len(players) or (len(players) not in (3, 4) if version == 1 else len(players) != 4):
        raise ValueError("네모 세기에는 서로 다른 참가자 4명이 필요합니다.")
    survivor_count = saved.get("survivor_count") if saved is not None else (len(players) - 1 if version == 1 else 2)
    if (type(survivor_count) is not int or not 0 < survivor_count < len(players)
            or version == 2 and survivor_count != 2 or saved is not None and saved.get("players") != players):
        raise ValueError("저장된 네모 세기 참가자·생존 인원이 올바르지 않습니다.")
    match.relationship_reviews_enabled = False
    match.model_observations = lambda name, events: [event for event in events if event.msg_type == "rules"]
    priority = match.rng.sample(players, len(players))
    match.event("rules", saved_rules or (LEGACY_RULES if version == 1 else RULES))
    match.event("rect_setup", {"version": version, "players": players, "survivor_count": survivor_count,
                "limit_seconds": LIMIT_SECONDS, "answer_seconds": ANSWER_SECONDS, "priority": priority,
                **({"puzzle_pack": puzzle_pack} if saved is None or "puzzle_pack" in saved else {})})
    winners, round_winners, questions = [], [], 0
    for number in range(1, survivor_count + 1):
        active = [name for name in players if name not in winners]
        winner = None
        while winner is None:
            questions += 1
            puzzle = make_puzzle(match.rng.randrange(2 ** 32), questions, pack=puzzle_pack)
            view = board(puzzle)
            image = b64decode(view["image"].partition(",")[2], validate=True)
            common = {"round": number, "question": questions}
            match.event("rect_question", {**common, "players": active.copy(), "board": view,
                        "target": puzzle["target"], "limit_seconds": LIMIT_SECONDS})
            locked, attempts, window, waits, clock = [], [], 0, 0, 0
            while winner is None:
                window += 1
                eligible = [name for name in active if name not in locked]
                match.event("rect_window", {**common, "window": window, "eligible": eligible,
                            "elapsed_ns": clock})
                scripted = {name: match.policy.randrange(1_000_000_000, 60_000_000_000) for name in eligible}
                decisions = {name: Decision(
                    f"{number}차 생존 결정 / {questions}번 문제 / 생각 구간 {window} · {name}\n"
                    f"생존 확정: {encode(winners)}. 이번 문제 오답·시간 초과 잠금: {encode(locked)}. "
                    f"동률 우선순위: {encode(priority)}. 공개 시도: {encode(attempts)}. "
                    f"남은 생각 시간: {max(0, LIMIT_SECONDS - clock / 1_000_000_000):.3f}초.\n"
                    f"첨부된 숫자 판에서 합이 {puzzle['target']}인 모든 축 정렬 네모를 세세요. "
                    "빈칸은 0이며 음수도 더합니다. 한 칸도 포함하고, 맞는 네모가 하나도 없으면 답은 0입니다. "
                    '답을 준비한 뒤 {"type":"buzz","count":0} 형식으로 버저와 즉시 발언을 제출하세요. '
                    '아직 준비되지 않았다면 {"type":"wait"}를 제출하세요. '
                    "정답 한 번이면 생존하며 이후 문제에서 빠집니다. 다른 참가자의 비공개 답은 알 수 없습니다.",
                    encode({"type": "buzz", "count": puzzle["answer"]}), valid=_accepts,
                    invalid_default=INVALID_BUZZ) for name in eligible}
                elapsed = {}
                responses = match.decide_together("rect_think", decisions, response_times=elapsed, images=(image,))
                actions = {name: parse_action(responses[name]) for name in eligible}
                finish = {name: clock + elapsed.get(name, scripted[name]) for name in eligible}
                buzzers = sorted((name for name in eligible if actions[name]["type"] == "buzz"
                                 and finish[name] <= LIMIT_SECONDS * 1_000_000_000),
                                 key=lambda name: (finish[name], priority.index(name)))
                if not buzzers:
                    waits += 1
                for name in buzzers:
                    count = actions[name]["count"]
                    match.event("rect_buzz", {**common, "player": name, "elapsed_ns": finish[name]}, actor=name)
                    valid = count >= 0
                    correct = valid and count == puzzle["answer"]
                    attempt = {**common, "player": name, "count": count, "correct": correct,
                        "reason": None if correct else "incorrect" if valid else "invalid",
                        "elapsed_ns": finish[name], "answer_seconds": 0}
                    match.event("rect_attempt", attempt, actor=name)
                    attempts.append(attempt)
                    if correct:
                        winner = name
                        winners.append(name)
                        result = {**common, "winner": name, "count": count, "rank": number}
                        round_winners.append(result)
                        match.event("rect_round_result", result)
                        break
                    locked.append(name)
                if winner is not None:
                    break
                for name in eligible:
                    if finish[name] > LIMIT_SECONDS * 1_000_000_000 and name not in locked:
                        locked.append(name)
                        match.event("rect_timeout", {**common, "player": name, "elapsed_ns": finish[name]}, actor=name)
                clock = max(finish.values())
                timed_out = clock >= LIMIT_SECONDS * 1_000_000_000
                if len(locked) == len(active) or waits >= WAIT_WINDOWS or timed_out:
                    reason = "timeout" if timed_out else "all_locked" if len(locked) == len(active) else "no_buzz"
                    match.event("rect_question_end", {**common, "winner": None, "count": puzzle["answer"], "reason": reason})
                    break
    ranking = winners + [name for name in players if name not in winners]
    groups = [[name] for name in ranking] if version == 1 else [[name] for name in winners] + [ranking[survivor_count:]]
    return {"ranking": ranking, "ranking_groups": groups, "survivors": winners,
            "eliminated": ranking[survivor_count:], "scores": {name: int(name in winners) for name in players},
            "finish_rounds": {row["winner"]: row["round"] for row in round_winners},
            "round_winners": round_winners, "rounds": survivor_count, "questions": questions,
            "pieces": match.pieces.copy()}
