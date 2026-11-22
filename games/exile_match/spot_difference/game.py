"""Remember a picture, then privately mark five changes without seeing it again."""

import json

from ...match import Decision, Match, encode
from .scenes import judge_marks, make_scene, picture, render_picture


WIDTH, HEIGHT = 960, 640
MEMORY_LIMIT = 300
NORMAL_ROUNDS = 3
CHANGE_COUNT = 5
ANSWER_SECONDS = 120
BLANK_SECONDS = 10
EMPTY_MEMORY = encode({"memory": ""})
EMPTY_MARKS = encode({"marks": []})

RULES = """달라진 그림 찾기 · 4인 개인전

1. 목표와 점수
본인의 생존을 위해 경쟁하세요. 각 그림에서 달라진 부분 5곳을 찾습니다.
정답 한 곳당 1점이며, 같은 변경 부분에 여러 번 표시해도 1점만 받습니다.
정규 3라운드의 합계로 순위를 정하고 하위 2명은 최종 탈락합니다.
생존·탈락 경계에 동점이 있으면 해당 동점자들만 새 그림으로 연장전을 진행합니다.
연장전도 경계 동점이 남으면 그 동점자들끼리 다시 진행하며 추첨하지 않습니다.

2. 원본 관찰과 기억
정규 라운드는 원본을 3분, 연장전은 2분 동안 관찰합니다.
관찰 뒤 원본을 숨기고 10초 대기 구간을 거쳐 달라진 그림을 공개합니다.
모델은 관찰 요청에서 원본 이미지를 보고, 본인이 작성한 300자 이내 기억 요약 하나만 보존합니다.
이 기억은 틀려도 자동 보정하지 않으며 다음 라운드에는 초기화합니다.
이전 원본·전체 행동 기록·전략 메모는 답안 요청에서 다시 제공하지 않습니다.

3. 답안
달라진 그림을 보고 2분 안에 최대 5곳에 X를 표시합니다.
그림은 가로 960, 세로 640픽셀이고 왼쪽 위가 (0,0)입니다.
X의 교차점을 정수 좌표 x=0~959, y=0~639로 제출하세요.
X의 교차점이 실제 달라진 부분 안에 있어야 정답입니다.
관찰·답안은 전원이 동시에 비공개로 제출하고, 전원의 답안 제출 뒤 정답 위치와 점수를 공개합니다.
모델 응답이 관찰 또는 답안의 제한 시간을 넘으면 해당 기억이나 답안은 빈 값으로 처리합니다.
관찰·대기 시간은 재생 단계로 기록하며 진행을 위해 별도로 기다리지 않습니다.
대화·협상·관계 평가는 없습니다. 호출 상한이 끝나면 스크립트 시연 행동으로 이어갑니다.
"""


def parse_memory(text):
    value = json.loads(text)
    if (not isinstance(value, dict) or set(value) != {"memory"}
            or not isinstance(value["memory"], str) or len(value["memory"]) > MEMORY_LIMIT):
        raise ValueError(f"memory에 {MEMORY_LIMIT}자 이내의 기억 요약만 지정하세요.")
    return value["memory"]


def parse_marks(text):
    value = json.loads(text)
    if not isinstance(value, dict) or set(value) != {"marks"} or not isinstance(value["marks"], list):
        raise ValueError("marks에 X 교차점의 좌표 목록을 지정하세요.")
    marks = value["marks"]
    if len(marks) > CHANGE_COUNT or any(
        not isinstance(mark, dict) or set(mark) != {"x", "y"}
        or type(mark["x"]) is not int or type(mark["y"]) is not int
        or not 0 <= mark["x"] < WIDTH or not 0 <= mark["y"] < HEIGHT
        for mark in marks
    ):
        raise ValueError("X를 최대 5개, 그림 범위 안의 정수 좌표로 지정하세요.")
    return marks


def _accepts(parser, text):
    try:
        parser(text)
        return True
    except (ValueError, TypeError, RecursionError):
        return False


def _groups(players, scores):
    return [[name for name in players if scores[name] == score]
            for score in sorted(set(scores.values()), reverse=True)]


def _boundary(groups):
    before = 0
    for index, group in enumerate(groups):
        if before < 2 < before + len(group):
            return index, 2 - before
        before += len(group)
    return None


def _scripted_marks(match, scene, players, overtime):
    order = match.policy.sample(list(players), len(players))
    counts = ({name: index for index, name in enumerate(order)} if overtime else
              {name: match.policy.randrange(CHANGE_COUNT + 1) for name in order})
    return {name: [{"x": target["x"] + target["w"] // 2,
                    "y": target["y"] + target["h"] // 2}
                   for target in match.policy.sample(scene["targets"], counts[name])]
            for name in players}


def play(match: Match):
    players = list(match.players)
    if len(players) != 4 or len(set(players)) != 4:
        raise ValueError("달라진 그림 찾기에는 서로 다른 참가자 4명이 필요합니다.")
    match.relationship_reviews_enabled = False
    # Backend.reset() in Match._query also discards Concordia's accumulated memory.
    # Every request receives current scores and only its own current-round recall explicitly.
    match.model_observations = lambda name, events: [event for event in events if event.msg_type == "rules"]
    totals = dict.fromkeys(players, 0)
    rules = RULES
    if match.resume_log is not None and match.resume_log.resume:
        rules = next((row["content"] for row in match.resume_log.events if row["msg_type"] == "rules"), RULES)
    match.event("rules", rules)
    match.event("picture_setup", {"version": 1, "players": players, "normal_rounds": NORMAL_ROUNDS,
                                   "change_count": CHANGE_COUNT, "memory_limit": MEMORY_LIMIT,
                                   "width": WIDTH, "height": HEIGHT})

    def play_round(number, active, *, overtime=False):
        scene = make_scene(match.rng.randrange(2 ** 32), number)
        original, changed = picture(scene), picture(scene, changed=True)
        scripted = _scripted_marks(match, scene, active, overtime)
        observe_seconds = 120 if overtime else 180
        common = {"round": number, "players": list(active), "overtime": overtime,
                  "observe_seconds": observe_seconds, "blank_seconds": BLANK_SECONDS,
                  "answer_seconds": ANSWER_SECONDS}

        def phase(stage, view):
            match.event("picture_phase", {**common, "stage": stage, "picture": view})

        score_context = f"정규 라운드 누적 점수: {encode(totals)}. "
        if overtime:
            score_context += "생존 경계 동점자끼리의 연장전이며 이번 그림의 점수로 다시 비교합니다. "
        phase("observe", original)
        decisions = {name: Decision(
            f"{number}라운드 원본 관찰 · {name}. {score_context}\n"
            f"첨부된 원본 그림을 관찰하고 {observe_seconds}초 안에 기억 요약을 작성하세요. "
            f"다음 답안 단계에 보존되는 기억은 본인이 쓴 {MEMORY_LIMIT}자 이내 요약 하나뿐입니다. "
            "위치, 물체, 색과 방향 중 필요한 것을 골라 기억하고, 외부 기록장을 사용하지 마세요. "
            '그림의 좌상단은 (0,0), 우하단은 (959,639)입니다. JSON {"memory":"기억 요약"}로 제출하세요.',
            EMPTY_MEMORY, valid=lambda action: _accepts(parse_memory, action), invalid_default=EMPTY_MEMORY)
                     for name in active}
        elapsed = {}
        responses = match.decide_together("picture_memorize", decisions, response_times=elapsed,
                                          images=(render_picture(original),))
        memories = {}
        for name in active:
            late = elapsed.get(name, 0) > observe_seconds * 1_000_000_000
            memories[name] = "" if late else parse_memory(responses[name])
            if late:
                match.event("picture_timeout", {"round": number, "player": name,
                                                 "phase": "picture_memorize", "seconds": observe_seconds}, actor=name)
            match.event("picture_memory", {"round": number, "player": name, "memory": memories[name]},
                        private=[name], actor=name)
        phase("blank", None)
        phase("answer", changed)
        decisions = {name: Decision(
            f"{number}라운드 달라진 부분 찾기 · {name}. {score_context}\n"
            f"첨부된 그림은 달라진 그림입니다. 원본은 다시 볼 수 없습니다. 내 기억 요약: {encode(memories[name])}\n"
            "원본과 달라진 부분 5곳 중 찾을 수 있는 곳에 X를 최대 5개 표시하세요. 정답 한 곳당 1점입니다. "
            f"{ANSWER_SECONDS}초 안에 제출해야 합니다. 좌상단 (0,0), 우하단 (959,639)이며 "
            'X 교차점의 정수 좌표를 JSON {"marks":[{"x":100,"y":200}]} 형식으로 제출하세요. '
            '표시하지 않으려면 {"marks":[]}를 제출하세요.',
            encode({"marks": scripted[name]}), valid=lambda action: _accepts(parse_marks, action),
            invalid_default=EMPTY_MARKS) for name in active}
        elapsed = {}
        responses = match.decide_together("picture_answer", decisions, response_times=elapsed,
                                          images=(render_picture(changed),))
        answers, scores, targets = {}, {}, None
        for name in active:
            late = elapsed.get(name, 0) > ANSWER_SECONDS * 1_000_000_000
            marks = [] if late else parse_marks(responses[name])
            if late:
                match.event("picture_timeout", {"round": number, "player": name,
                                                 "phase": "picture_answer", "seconds": ANSWER_SECONDS}, actor=name)
            match.event("picture_marks", {"round": number, "player": name, "marks": marks},
                        private=[name], actor=name)
            judged = judge_marks(scene, marks)
            answers[name], scores[name], targets = judged["marks"], judged["score"], judged["targets"]
            if not overtime:
                totals[name] += scores[name]
        phase("reveal", changed)
        match.event("picture_result", {"round": number, "players": list(active), "overtime": overtime,
                                        "scores": scores.copy(), "totals": totals.copy(), "answers": answers,
                                        "targets": targets, "picture": changed})
        return scores

    for number in range(1, NORMAL_ROUNDS + 1):
        play_round(number, players)
    groups = _groups(players, totals)
    tiebreaks = []
    while (boundary := _boundary(groups)) is not None:
        index, slots = boundary
        active = groups[index]
        number = NORMAL_ROUNDS + len(tiebreaks) + 1
        match.event("picture_tiebreak", {"round": number, "players": active.copy(), "slots": slots})
        scores = play_round(number, active, overtime=True)
        tiebreaks.append({"round": number, "players": active.copy(), "slots": slots, "scores": scores})
        groups[index:index + 1] = _groups(active, scores)
    ranking = [name for group in groups for name in group]
    return {"ranking": ranking, "ranking_groups": groups, "survivors": ranking[:2], "eliminated": ranking[2:],
            "scores": totals, "pieces": match.pieces.copy(), "rounds": NORMAL_ROUNDS, "tiebreaks": tiebreaks}
