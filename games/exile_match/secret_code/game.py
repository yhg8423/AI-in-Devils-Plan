"""Prepare four letters, then race to buzz and say the prepared answer."""

from base64 import b64decode
from copy import deepcopy
import json
from string import ascii_uppercase

from ...match import Decision, Match, encode
from .puzzles import board, make_puzzle


ROUNDS = 3
ANSWER_SECONDS = 10
WAIT_WINDOWS = 3
INVALID_BUZZ = encode({"type": "buzz", "code": ""})

RULES = """비밀 코드 · 4인 개인전

공개 그림에는 A~Z 카드 26장이 있고, 각 카드에는 숫자·색·도형이 있습니다.
모든 단서를 만족하는 서로 다른 카드 4장을 찾아 알파벳순 네 글자로 답하세요.
문제마다 정답은 하나입니다. 소문자는 대문자로 바꾸지만, 순서를 대신 정렬하지 않습니다.
정답자는 즉시 생존을 확정하고 이후 문제에 참여하지 않습니다.
이렇게 3라운드에서 한 명씩 생존하며, 남은 마지막 한 명은 탈락합니다.

답을 먼저 준비한 뒤 버저와 발언을 하나의 행동으로 제출합니다.
JSON {"type":"buzz","code":"ABCD"}는 버저를 누르자마자 준비한 코드를 말한다는 뜻입니다.
버저 뒤 10초 안에 말해야 하며, 이 결합 행동의 발언 시간은 0초로 기록합니다.
답을 생각하는 모델의 버저 전 응답 시간에는 10초 발언 제한을 적용하지 않습니다.
아직 답을 말하지 않으려면 {"type":"wait"}를 제출하세요.
각 생각 구간의 응답은 동시에 비공개로 받습니다. 버저 전 응답 시간이 짧은 순서로 처리하며,
동률은 시작할 때 공개한 시드 기반 우선순위를 따릅니다. 이 순서는 재개 후에도 유지됩니다.
오답·중복 글자·알파벳순이 아닌 답·형식 오류는 해당 문제에서 다시 누를 수 없습니다.
한 사람이 정답을 맞히면 뒤에 대기 중인 버저와 비공개 코드는 처리하거나 공개하지 않습니다.
대기자는 다음 생각 구간에도 참여합니다. 모두 대기한 구간이 세 번 쌓이거나 전원이 오답이면
그 문제를 무효로 하고 같은 라운드에 새 그림과 단서를 제시합니다. 추첨으로 생존자를 정하지 않습니다.
대화·협상·관계 평가는 없습니다. 호출 상한이 끝나면 스크립트 시연 행동으로 이어갑니다.
"""


def parse_action(text):
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("버저 또는 대기 JSON 객체가 필요합니다.")
    if value == {"type": "wait"}:
        return value
    if (set(value) != {"type", "code"} or value["type"] != "buzz"
            or not isinstance(value["code"], str) or len(value["code"]) > 64):
        raise ValueError("버저에는 code 문자열을 지정하세요.")
    return {"type": "buzz", "code": value["code"].strip().upper()}


def _accepts(text):
    try:
        parse_action(text)
        return True
    except (ValueError, TypeError, RecursionError):
        return False


def _valid_code(code):
    return (len(code) == 4 and len(set(code)) == 4 and all(letter in ascii_uppercase for letter in code)
            and code == "".join(sorted(code)))


def play(match: Match):
    players = list(match.players)
    if len(players) != 4 or len(set(players)) != 4:
        raise ValueError("비밀 코드에는 서로 다른 참가자 4명이 필요합니다.")
    match.relationship_reviews_enabled = False
    match.model_observations = lambda name, events: [event for event in events if event.msg_type == "rules"]
    priority = match.rng.sample(players, len(players))
    match.event("rules", RULES)
    match.event("code_setup", {"version": 1, "players": players, "rounds": ROUNDS,
                               "answer_seconds": ANSWER_SECONDS, "priority": priority})
    winners, round_winners, questions = [], [], 0
    for number in range(1, ROUNDS + 1):
        active = [name for name in players if name not in winners]
        winner = None
        while winner is None:
            questions += 1
            puzzle = make_puzzle(match.rng.randrange(2 ** 32))
            view = board(puzzle)
            clues = deepcopy(puzzle["clues"])
            image = b64decode(view["image"].partition(",")[2], validate=True)
            common = {"round": number, "question": questions}
            match.event("code_question", {**common, "players": active.copy(), "board": view,
                                          "clues": clues, "answer_seconds": ANSWER_SECONDS})
            locked, attempts, window, waits = [], [], 0, 0
            while winner is None:
                window += 1
                eligible = [name for name in active if name not in locked]
                match.event("code_window", {**common, "window": window, "eligible": eligible})
                # Scripted timing is drawn even for live players, keeping policy replay deterministic.
                scripted_times = {name: match.policy.randrange(1_000_000_000, 60_000_000_000) for name in eligible}
                decisions = {name: Decision(
                    f"{number}라운드 / {questions}번 문제 / 생각 구간 {window} · {name}\n"
                    f"생존 확정: {encode(winners)}. 현재 참가자: {encode(active)}. "
                    f"버저 가능: {encode(eligible)}. 이번 문제 오답 잠금: {encode(locked)}.\n"
                    f"동률 우선순위: {encode(priority)}. 공개된 이번 문제 시도: {encode(attempts)}\n"
                    "첨부된 26장 그림과 아래 단서를 모두 만족하는 카드 4장을 찾으세요. "
                    "숫자 순서와 답의 알파벳 순서를 구분하세요. 정답은 공개되기 전까지 알려지지 않습니다.\n"
                    + "\n".join(f"{clue['id']}. {clue['text']}" for clue in clues)
                    + '\n답을 준비한 뒤 {"type":"buzz","code":"ABCD"}로 버저와 즉시 발언을 함께 제출하세요. '
                    '아직 버저를 누르지 않으려면 {"type":"wait"}를 제출하세요. '
                    "생각 시간은 버저 뒤 10초 발언 제한에 포함되지 않습니다.",
                    encode({"type": "buzz", "code": puzzle["solution"]}), valid=_accepts,
                    invalid_default=INVALID_BUZZ) for name in eligible}
                elapsed = {}
                replies = match.decide_together("secret_think", decisions, response_times=elapsed, images=(image,))
                actions = {name: parse_action(replies[name]) for name in eligible}
                buzzers = sorted((name for name in eligible if actions[name]["type"] == "buzz"),
                                 key=lambda name: (elapsed.get(name, scripted_times[name]), priority.index(name)))
                if not buzzers:
                    waits += 1
                for name in buzzers:
                    timing = elapsed.get(name, scripted_times[name])
                    code = actions[name]["code"]
                    match.event("code_buzz", {**common, "player": name, "elapsed_ns": timing}, actor=name)
                    correct = _valid_code(code) and code == puzzle["solution"]
                    attempt = {**common, "player": name, "code": code, "correct": correct,
                               "reason": None if correct else "incorrect" if _valid_code(code) else "invalid",
                               "elapsed_ns": timing, "answer_seconds": 0}
                    match.event("code_attempt", attempt, actor=name)
                    attempts.append(attempt)
                    if correct:
                        winner = name
                        winners.append(name)
                        result = {**common, "winner": name, "code": code, "rank": number}
                        round_winners.append(result)
                        match.event("code_round_result", result)
                        break
                    locked.append(name)
                if winner is None and (len(locked) == len(active) or waits >= WAIT_WINDOWS):
                    match.event("code_question_end", {**common, "winner": None, "code": puzzle["solution"],
                                                      "reason": "all_locked" if len(locked) == len(active) else "no_buzz"})
                    break
    ranking = winners + [name for name in players if name not in winners]
    return {"ranking": ranking, "ranking_groups": [[name] for name in ranking], "survivors": winners,
            "eliminated": ranking[3:], "scores": {name: int(name in winners) for name in players},
            "finish_rounds": {row["winner"]: row["round"] for row in round_winners},
            "round_winners": round_winners, "rounds": ROUNDS, "questions": questions,
            "pieces": match.pieces.copy()}
