"""Study flags, retain a private bounded memory, and select five remembered flags."""

from base64 import b64decode
import json

from ...match import Decision, Match, encode
from .puzzles import board, frame, make_puzzle


NORMAL_ROUNDS = 3
VERSION = 2
MEMORY_LIMIT = 300
STUDY_SECONDS = 30
BLANK_SECONDS = 5
ANSWER_SECONDS = 60
EMPTY_MEMORY = encode({"memory": ""})

RULES = """만국기 · 4인 개인전

서로 다른 국기 10개를 한 장에 1초씩, 같은 순서로 세 번 관찰합니다(총 30초).
5초 뒤 국기 25개의 보기가 나타나며, 그중 앞서 관찰한 국기는 정확히 5개입니다.
1분 안에 해당하는 보기 번호 다섯 개에 동그라미를 표시하세요. 국기 이름을 맞힐 필요는 없습니다.
맞힌 국기 한 개당 1점이며 오답 감점은 없습니다. 같은 번호를 두 번 고를 수 없습니다.
정규 3라운드의 합계로 순위를 정합니다. 생존 경계에 동점이 있으면 해당 동점자만
새 국기로 연장전을 진행합니다. 연장전 점수로 그 동점자들의 순위를 나누며, 경계 동점이 남으면 반복합니다.
4명이 참가하며 정규·연장전 결과 상위 3명이 생존하고 최하위 1명은 탈락합니다.

모델은 관찰 때만 열 국기를 순서대로 배치한 이미지를 보고 300자 이내 기억 요약을 작성합니다.
답안 때는 25개 보기 이미지와 본인의 이번 라운드 기억 요약만 받습니다.
이전 관찰 이미지·전체 행동 기록·전략 메모는 다시 제공하지 않고 기억을 자동 보정하지 않습니다.
기억 요약이 30초를 넘기면 빈 기억, 답안이 60초를 넘기거나 형식이 틀리면 0점입니다.
모든 기억·답안은 동시에 비공개 제출하며, 전원의 제출 뒤 정답과 점수를 공개합니다.
관찰·대기 구간은 기록만 남기고 실제로 기다리지는 않습니다. 대화·협상·관계 평가는 없습니다.
모델 호출 상한이 끝나면 스크립트 시연 행동으로 이어갑니다.
"""

LEGACY_RULES = RULES.replace("만국기 · 4인 개인전", "만국기 · 유배지 개인전").replace(
    "4명이 참가하며 정규·연장전 결과 상위 3명이 생존하고 최하위 1명은 탈락합니다.",
    "방송의 3인 경기에서는 상위 2명이 생존합니다. 연속 실행의 인원 차이가 있어도 상위 2명만 생존합니다.",
)


def parse_memory(text):
    value = json.loads(text)
    if (not isinstance(value, dict) or set(value) != {"memory"}
            or not isinstance(value["memory"], str) or len(value["memory"]) > MEMORY_LIMIT):
        raise ValueError("memory에 300자 이내 기억 요약을 지정하세요.")
    return value["memory"]


def parse_marks(text):
    value = json.loads(text)
    if not isinstance(value, dict) or set(value) != {"marks"} or not isinstance(value["marks"], list):
        raise ValueError("marks에 보기 번호 다섯 개를 지정하세요.")
    marks = value["marks"]
    if (len(marks) != 5 or any(type(mark) is not int or not 1 <= mark <= 25 for mark in marks)
            or len(set(marks)) != 5):
        raise ValueError("서로 다른 1~25 정수 번호를 정확히 다섯 개 지정하세요.")
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


def _boundary(groups, slots):
    before = 0
    for index, group in enumerate(groups):
        if before < slots < before + len(group):
            return index, slots - before
        before += len(group)
    return None


def play(match: Match):
    players = list(match.players)
    saved, saved_rules = None, None
    if match.resume_log is not None and match.resume_log.resume:
        saved = next((json.loads(row["content"]) for row in match.resume_log.events if row["msg_type"] == "flag_setup"), None)
        saved_rules = next((row["content"] for row in match.resume_log.events if row["msg_type"] == "rules"), None)
        if not isinstance(saved, dict):
            raise ValueError("재개할 만국기 준비 기록이 없습니다.")
    version = saved.get("version") if saved is not None else VERSION
    if type(version) is not int or version not in (1, 2):
        raise ValueError("지원하지 않는 만국기 기록 버전입니다.")
    if (len(set(players)) != len(players) or (not 3 <= len(players) <= 6 if version == 1 else len(players) != 4)):
        raise ValueError("만국기에는 서로 다른 참가자 4명이 필요합니다.")
    survivor_count = saved.get("survivor_count") if saved is not None else (2 if version == 1 else 3)
    if (type(survivor_count) is not int or not 0 < survivor_count < len(players)
            or version == 2 and survivor_count != 3 or saved is not None and saved.get("players") != players):
        raise ValueError("저장된 만국기 참가자·생존 인원이 올바르지 않습니다.")
    match.relationship_reviews_enabled = False
    match.model_observations = lambda name, events: [event for event in events if event.msg_type == "rules"]
    totals = dict.fromkeys(players, 0)
    match.event("rules", saved_rules or (LEGACY_RULES if version == 1 else RULES))
    match.event("flag_setup", {"version": version, "players": players, "normal_rounds": NORMAL_ROUNDS,
        "survivor_count": survivor_count, "memory_limit": MEMORY_LIMIT, "study_seconds": STUDY_SECONDS,
        "blank_seconds": BLANK_SECONDS, "answer_seconds": ANSWER_SECONDS})

    def play_round(number, active, *, overtime=False):
        puzzle = make_puzzle(match.rng.randrange(2 ** 32))
        study, choices = board(puzzle["study"], study=True), board(puzzle["choices"])
        common = {"round": number, "players": list(active), "overtime": overtime,
                  "study_seconds": STUDY_SECONDS, "blank_seconds": BLANK_SECONDS, "answer_seconds": ANSWER_SECONDS}

        def phase(stage, picture):
            match.event("flag_phase", {**common, "stage": stage, "picture": picture})

        phase("observe", study)
        frames = [frame(code) for code in puzzle["study"]]
        for index in range(30):
            match.event("flag_frame", {"round": number, "index": index + 1, "seconds": 1,
                                       "picture": frames[index % 10]})
        context = f"이번 라운드 참가자: {encode(active)}. 정규 누적 점수: {encode(totals)}. "
        if overtime:
            context += "생존 경계 동점자끼리 이번 라운드 점수로 다시 비교합니다. "
        elapsed = {}
        responses = match.decide_together("flag_memorize", {name: Decision(
            f"{number}라운드 국기 관찰 · {name}. {context}\n"
            "첨부 그림의 국기 10개를 번호 순서대로 관찰하세요. 실제 제시는 각 1초씩 같은 순서 세 번입니다. "
            "30초 안에 색·배열·문양 등 기억할 특징을 고르세요. 다음 단계에는 본인이 쓴 300자 이내 기억만 보존됩니다. "
            '외부 기록장을 사용하지 말고 JSON {"memory":"기억 요약"}만 제출하세요.',
            EMPTY_MEMORY, valid=lambda action: _accepts(parse_memory, action), invalid_default=EMPTY_MEMORY)
            for name in active}, response_times=elapsed,
            images=(b64decode(study["image"].partition(",")[2]),))
        memories = {}
        for name in active:
            late = elapsed.get(name, 0) > STUDY_SECONDS * 1_000_000_000
            memories[name] = "" if late else parse_memory(responses[name])
            if late:
                match.event("flag_timeout", {"round": number, "player": name, "phase": "flag_memorize", "seconds": STUDY_SECONDS}, actor=name)
            match.event("flag_memory", {"round": number, "player": name, "memory": memories[name]}, private=[name], actor=name)
        phase("blank", None)
        phase("answer", choices)
        order = match.policy.sample(list(active), len(active))
        counts = ({name: index for index, name in enumerate(order)} if overtime else
                  {name: match.policy.randrange(6) for name in order})
        correct = set(puzzle["correct"])
        incorrect = [index for index in range(1, 26) if index not in correct]
        scripted = {name: match.policy.sample(puzzle["correct"], counts[name])
                     + match.policy.sample(incorrect, 5 - counts[name]) for name in active}
        elapsed, start = {}, len(match.events)
        responses = match.decide_together("flag_answer", {name: Decision(
            f"{number}라운드 국기 선택 · {name}. {context}\n"
            f"관찰 그림은 다시 볼 수 없습니다. 내 기억 요약: {encode(memories[name])}\n"
            "첨부된 보기 25개 중 앞서 본 국기 5개를 골라 번호에 동그라미를 표시하세요. 정답 한 개당 1점입니다. "
            '60초 안에 서로 다른 번호 다섯 개를 JSON {"marks":[1,2,3,4,5]} 형식으로 제출하세요.',
            encode({"marks": scripted[name]}), valid=lambda action: _accepts(parse_marks, action))
            for name in active}, response_times=elapsed,
            images=(b64decode(choices["image"].partition(",")[2]),))
        invalid = {event.visible_to[0] for event in match.events[start:] if event.msg_type == "invalid_action"
                   and json.loads(event.content).get("phase") == "flag_answer" and isinstance(event.visible_to, list)}
        answers, scores = {}, {}
        for name in active:
            late = elapsed.get(name, 0) > ANSWER_SECONDS * 1_000_000_000
            marks = [] if late or name in invalid else parse_marks(responses[name])
            if late:
                match.event("flag_timeout", {"round": number, "player": name, "phase": "flag_answer", "seconds": ANSWER_SECONDS}, actor=name)
            match.event("flag_marks", {"round": number, "player": name, "marks": marks}, private=[name], actor=name)
            right = sorted(set(marks) & correct)
            scores[name] = len(right)
            answers[name] = {"marks": marks, "correct": right, "score": scores[name]}
            if not overtime:
                totals[name] += scores[name]
        phase("reveal", choices)
        match.event("flag_result", {**common, "scores": scores.copy(), "totals": totals.copy(),
                    "answers": answers, "correct": puzzle["correct"], "picture": choices})
        return scores

    for number in range(1, NORMAL_ROUNDS + 1):
        play_round(number, players)
    groups, tiebreaks = _groups(players, totals), []
    while (boundary := _boundary(groups, survivor_count)) is not None:
        index, slots = boundary
        active = groups[index]
        number = NORMAL_ROUNDS + len(tiebreaks) + 1
        match.event("flag_tiebreak", {"round": number, "players": active.copy(), "slots": slots})
        scores = play_round(number, active, overtime=True)
        tiebreaks.append({"round": number, "players": active.copy(), "slots": slots, "scores": scores})
        groups[index:index + 1] = _groups(active, scores)
    ranking = [name for group in groups for name in group]
    return {"ranking": ranking, "ranking_groups": groups, "survivors": ranking[:survivor_count],
            "eliminated": ranking[survivor_count:], "scores": totals, "pieces": match.pieces.copy(),
            "rounds": NORMAL_ROUNDS, "tiebreaks": tiebreaks}
