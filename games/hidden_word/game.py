"""Public noun candidates, shared fastText scoring, and sealed guesses."""

import json

from ..match import Decision, Match, encode
from ..models import STRATEGY_NOTE_LIMIT
from .vectors import load_vectors, normalized_score
from .words import ASSOCIATIONS, DECK_SHA256, ENVELOPES, WORDS, is_noun_word, scripted_guess


ROUNDS = 2
PHASES = 3
MAX_HINTS = 10
HINT_SECONDS = 15 * 60
GUESS_SECONDS = 5 * 60
THRESHOLD = 95

RULES = """히든 워드 · 참가자 5~6명 · 2라운드

각자 비공개 봉투 하나를 골라 보통명사 다섯 개를 받습니다. 고유명사는 사용하지 않습니다.
추첨한 순서대로 매 라운드 한 번씩 출제자가 됩니다. 첫 라운드에는 받은 단어 중 하나를,
둘째 라운드에는 첫 라운드에 쓰지 않은 나머지 네 단어 중 하나를 히든 워드로 정합니다.
출제자는 자신의 정답을 숨기면서 득점하고, 다른 참가자는 상대의 단어를 맞혀 생존과 우승을 노리세요.

출제자가 제출하는 모든 힌트 후보 단어와 보정 점수는 즉시 모든 참가자에게 공개됩니다.
한 차례 힌트 제시는 최대 15분, 최대 10개입니다.
보정 점수가 95점을 초과하면 즉시 힌트를 마치고 그 단어를 최종 힌트로 강조합니다.
10개를 제출하거나 제한 시간이 끝날 때까지
기준을 넘지 못하면 제출한 힌트와 관계없이 fastText 사전에서 정답 자체를 제외하고 가장 가까운 일반명사를 공개합니다.
최고 유사도가 같으면 사전에서 먼저 나온 단어를 택합니다. 이전에 공개한 단어가 다시 나올 수 있습니다.
이전 단계의 모든 후보 단어와 점수, 최종 힌트는 이후 단계에서도 볼 수 있습니다.

출제자를 제외한 참가자는 5분 안에 추측 단어를 동시에 비공개 제출합니다.
한 히든 워드에 한 번만 피스 1개를 써서 답 하나를 추가할 수 있습니다. 피스는 정답 여부와 관계없이 소모됩니다.
맞힌 참가자는 각각 승점 1점을 얻고 그 출제자의 차례가 종료됩니다.
아무도 맞히지 못하면 출제자는 1차 1점, 2차 2점, 3차 3점을 차례로 얻습니다.
힌트 제시와 답 제출은 최대 세 차례 반복하며 실패 단계의 출제자 득점은 누적됩니다.
둘째 라운드는 모든 승점이 두 배입니다. 마지막 단계가 끝나거나 정답자가 나오면 히든 워드를 공개합니다.

2라운드 종료 후 승점 상위 2명은 생활동, 최하위 한 명은 탈락하며 나머지는 감옥동으로 갑니다.
1위는 피스 4개를 얻습니다. 이 매치에는 연맹의 징표 구제가 없습니다.

시뮬레이터 진행
방송의 봉투와 다른 새 보통명사 묶음을 사용합니다. 모든 참가자에게 같은 사전학습 fastText 모델을 적용합니다.
정답을 제외한 최근접 일반명사를 99.9점으로 놓고 보정합니다.
코사인 유사도를 최근접 일반명사의 코사인 유사도로 나눈 뒤 100을 곱하고, 0~99.9점으로 제한합니다.
이 보정·공개 기준은 시뮬레이터의 진행 규칙입니다.
방송의 학습 모델과 같은 수치를 보장하지 않습니다. 참가자의 제공자·모델·호출 상한은 유사도에 영향을 주지 않습니다.
사전에 없거나 일반명사로 인정되지 않은 힌트도 단어와 무효 사유가 공개되며 점수 없이 한 번의 제출 기회를 소모합니다.
제출 힌트와 최근접 명사 검색에 같은 명사 판정 기준을 적용하며 시연 행동에도 같은 fastText 판정을 사용합니다.
시뮬레이터에서는 정답 자체를 힌트로 제출할 수 없습니다.
방송은 6인 경기이며 이전 매치 생존자가 5명인 경로는 복귀자를 추가하지 않고 5인으로 진행합니다.
각자 게임 시작 전과 정답 제출 전에 비공개 전략 요약을 정리합니다.
참가자 간 대화·협상·귓속말과 룸 이동은 없습니다.
판정 결과를 확인한 뒤 친밀도·신뢰도를 검토합니다.
출제 힌트는 출제자의 응답 시간을, 정답 제출은 각 추측자의 전략 요약과 답 응답 시간을 합산합니다.
기다리는 시간을 별도로 재현하지 않습니다.
완전 동점은 처음 공개한 추첨 순서로 판정합니다. 잘못된 형식이나 호출 상한 뒤에는 시연 행동을 사용합니다.
"""


def parse_guesses(text, pieces, spent):
    payload = json.loads(text)
    if not isinstance(payload, dict) or set(payload) != {"answers", "spend"}:
        raise ValueError("answers 배열과 spend 불리언을 지정하세요.")
    answers, spend = payload["answers"], payload["spend"]
    if (not isinstance(answers, list) or type(spend) is not bool
            or any(not is_noun_word(word) for word in answers)
            or len(answers) != len(set(answers))
            or len(answers) > 1 + int(spend)
            or spend and (spent or pieces < 1 or len(answers) != 2)):
        raise ValueError("기본 답 하나와 피스 1개당 추가 답 하나만 제출할 수 있습니다.")
    return answers, spend


def _valid_guesses(text, pieces, spent):
    try:
        parse_guesses(text, pieces, spent)
    except (ValueError, TypeError, RecursionError):
        return False
    return True


def validate_vectors(vectors):
    """Check the complete envelope bank and scripted actions before starting a log."""
    missing = [word for word in WORDS if word not in vectors]
    unavailable = [word for word in WORDS if not any(vectors.is_hint(hint) for hint in ASSOCIATIONS[word])]
    if missing or unavailable:
        problems = []
        if missing:
            problems.append("봉투 단어 누락: " + ", ".join(missing))
        if unavailable:
            problems.append("시연 힌트 누락: " + ", ".join(unavailable))
        raise ValueError("fastText 사전이 히든 워드 단어를 지원하지 않습니다. " + "; ".join(problems))
    nonpositive = [word for word in WORDS if vectors.nearest(word)["similarity"] <= 0]
    if nonpositive:
        raise ValueError("최근접 일반명사의 유사도가 양수인 정답이 필요합니다: " + ", ".join(nonpositive))
    return vectors


def validate_saved_setup(setup, vectors):
    if not isinstance(setup, dict) or setup.get("version") != 2:
        raise ValueError("이전 유사도 판정으로 시작한 히든 워드는 재개할 수 없습니다. fastText로 새 경기를 시작하세요.")
    if setup.get("hint_visibility") != "public":
        raise ValueError("힌트 후보가 비공개였던 이전 경기는 재개할 수 없습니다. 새 경기를 시작하세요.")
    if setup.get("scorer") != vectors.metadata:
        raise ValueError("저장된 경기와 fastText 모델 정보·체크섬이 다릅니다. 당시 모델 파일을 사용하세요.")
    if setup.get("deck_sha256") != DECK_SHA256:
        raise ValueError("단어 봉투 구성이 변경되었습니다. 새 경기를 시작하세요.")
    if setup.get("discussion") is not False:
        raise ValueError("대화 구간이 있는 이전 진행 방식의 경기는 재개할 수 없습니다. 새 경기를 시작하세요.")
    if setup.get("fallback") != "vocabulary_nearest":
        raise ValueError("힌트 공개 규칙이 변경되었습니다. 새 경기를 시작하세요.")
    if setup.get("reveal_rule") != "nearest_noun_ratio_v1":
        raise ValueError("힌트 공개 기준이 변경되었습니다. 새 경기를 시작하세요.")
    if setup.get("hint_filter") != "same_as_nearest":
        raise ValueError("힌트 명사 판정 규칙이 변경되었습니다. 새 경기를 시작하세요.")
    if setup.get("score_display") != "nearest_noun_99_9" or setup.get("score_ceiling") != 99.9:
        raise ValueError("저장된 경기의 점수 표시 규칙을 지원하지 않습니다. 새 경기를 시작하세요.")


def _judge(vectors, secret, hint, cache):
    if hint not in vectors:
        return {"similarity": None, "valid": False, "mode": "fasttext", "reason": "out_of_vocabulary"}
    if not vectors.is_hint(hint):
        return {"similarity": None, "valid": False, "mode": "fasttext", "reason": "not_common_noun"}
    key = tuple(sorted((secret, hint)))
    if key in cache:
        return cache[key]
    result = {"similarity": vectors.similarity(secret, hint), "valid": True, "mode": "fasttext"}
    cache[key] = result
    return result


def _strategy(match, phase, focus, names):
    times = {}
    notes = match.decide_together(phase, {
        name: Decision(
            f"히든 워드 비공개 전략 요약. {focus} 내 피스는 {match.pieces[name]}개입니다. "
            "확인된 사실, 상대의 주장과 추측을 구분하고 자신의 생존·생활동 진출·우승에 유리한 계획을 세우세요. "
            f"공개할 메시지 대신 전략 요약만 한국어 {STRATEGY_NOTE_LIMIT}자 이내로 출력하세요.",
            "공개 힌트와 순위를 비교해 정답을 추론하고 피스 사용의 이득과 위험을 검토한다.",
            valid=lambda value: isinstance(value, str) and 0 < len(value.strip()) <= STRATEGY_NOTE_LIMIT,
        ) for name in names
    }, record_actions=False, response_times=times)
    for name, note in notes.items():
        match.event("decision_note", {"phase": phase, "note": note}, actor=name, private=[name])
    return times


def play(match: Match, *, vectors=None):
    players = match.players
    if len(players) not in (5, 6) or len(set(players)) != len(players):
        raise ValueError("히든 워드에는 서로 다른 참가자 5~6명이 필요합니다.")
    vectors = validate_vectors(load_vectors() if vectors is None else vectors)
    if match.resume_log is not None and match.resume_log.resume:
        setup = next((json.loads(event["content"]) for event in match.resume_log.events
                      if event["msg_type"] == "word_setup"), None)
        validate_saved_setup(setup, vectors)
    demo_hints = {word: tuple(hint for hint in ASSOCIATIONS[word] if vectors.is_hint(hint)) for word in WORDS}
    order = match.rng.sample(list(players), len(players))
    scores = dict.fromkeys(players, 0)
    similarity_cache = {}
    envelopes, used = {}, {}
    match.event("rules", RULES)
    setup = {"version": 2, "players": players, "rounds": ROUNDS,
        "order": order, "envelopes": len(ENVELOPES), "threshold": THRESHOLD,
        "max_hints": MAX_HINTS, "hint_seconds": HINT_SECONDS, "guess_seconds": GUESS_SECONDS,
        "score_mode": "fasttext", "scorer": vectors.metadata, "deck_sha256": DECK_SHA256,
        "discussion": False, "fallback": "vocabulary_nearest", "reveal_rule": "nearest_noun_ratio_v1",
        "hint_filter": "same_as_nearest", "pieces": match.pieces.copy(),
        "score_display": "nearest_noun_99_9", "score_ceiling": 99.9, "hint_visibility": "public"}
    match.event("word_setup", setup)
    _strategy(match, "word_preparation", "게임 시작 전 자신의 출제·추측 계획을 정리하세요.", players)
    remaining = list(range(1, len(ENVELOPES) + 1))
    for name in order:
        match.event("word_dealer", {"player": name, "stage": "enter"})
        choice = int(match.decide(name, "word_envelope",
            "딜러룸에서 아직 남은 봉투 하나를 고르세요. 다른 참가자는 봉투 속 단어를 볼 수 없습니다.",
            str(remaining[0]), options=tuple(map(str, remaining)), private=True))
        remaining.remove(choice)
        envelopes[name] = ENVELOPES[choice - 1]
        used[name] = set()
        match.event("word_envelope", {"envelope": choice, "words": envelopes[name]}, actor=name, private=[name])
        match.event("word_dealer", {"player": name, "stage": "exit"})
    for number in range(1, ROUNDS + 1):
        multiplier = number
        match.event("word_round", {"round": number, "multiplier": multiplier})
        secrets = match.decide_together("word_secret", {
            name: Decision(
                f"{number}라운드 출제할 히든 워드를 고르세요. 이전 라운드 단어는 다시 쓸 수 없습니다. "
                "자신이 숨기기 유리한 단어를 선택하세요.",
                match.policy.choice([word for word in envelopes[name] if word not in used[name]]),
                options=tuple(word for word in envelopes[name] if word not in used[name]))
            for name in players
        })
        for name, secret in secrets.items():
            used[name].add(secret)
            match.event("word_secret", {"round": number, "setter": name, "word": secret}, actor=name, private=[name])
        for index, setter in enumerate(order, 1):
            context = {"round": number, "setter": setter}
            match.event("word_turn", {**context, "index": index})
            secret, clues, candidates = secrets[setter], [], []
            nearest = vectors.nearest(secret)
            paid = set()
            for phase in range(1, PHASES + 1):
                stage = {**context, "phase": phase}
                match.event("word_phase", stage)
                elapsed = 0
                revealed = None
                for hint_index in range(1, MAX_HINTS + 1):
                    default = demo_hints[secret][(hint_index + phase - 2) % len(demo_hints[secret])]
                    times = {}
                    history = f"이번 출제자의 모든 공개 후보와 보정 점수: {encode(candidates)}. 최종 힌트: {encode(clues)}. "
                    hint = match.decide_together("word_hint", {setter: Decision(
                        f"{phase}차 힌트 {hint_index}/{MAX_HINTS}. 정답 {secret!r}은 다른 참가자에게 숨겨져 있습니다. "
                        "정답을 알아맞히기 어렵게 하면서 보정 점수 95점을 초과할 의미상 가까운 보통명사 한 개를 제출하세요. "
                        "제출한 후보 단어와 보정 점수는 즉시 모든 참가자에게 공개됩니다. "
                        f"{history}"
                        "고유명사, 정답 자체와 설명을 제외하고 한글 명사 한 개만 출력하세요.", default,
                        valid=lambda value: is_noun_word(value) and value != secret,
                    )}, response_times=times)[setter]
                    elapsed += times.get(setter, 0)
                    if elapsed > HINT_SECONDS * 1_000_000_000:
                        break
                    judgement = _judge(vectors, secret, hint, similarity_cache)
                    similarity = normalized_score(judgement["similarity"], nearest["similarity"])
                    qualifies = similarity is not None and similarity > THRESHOLD
                    if not judgement["valid"]:
                        match.event("invalid_action", {"phase": "word_hint", "action": hint}, private=[setter])
                    record = {**stage, "index": hint_index, "word": hint, **judgement, "qualifies": qualifies}
                    record.update(similarity=similarity, score_display="nearest_noun_99_9")
                    candidates.append(record)
                    match.event("word_hint", record, actor=setter)
                    match.event("word_similarity", record)
                    if qualifies:
                        revealed = {"word": hint, "similarity": similarity, "forced": False, "source": "submitted_hint"}
                        break
                if revealed is None:
                    revealed = {**nearest, "similarity": 99.9, "forced": True, "source": "fasttext_nearest"}
                revealed["score_display"] = "nearest_noun_99_9"
                match.event("word_clue", {**stage, **revealed})
                if revealed["word"] is not None:
                    clues.append(revealed)
                evidence = f"이번 출제자의 모든 공개 후보와 보정 점수: {encode(candidates)}. 최종 힌트: {encode(clues)}. "
                preparation_times = _strategy(match, "word_guess_preparation", evidence + "모든 후보를 함께 비교해 답 후보와 피스 사용 계획을 정리하세요.", [name for name in players if name != setter])
                strongest = max((item for item in [*candidates, *clues] if item["similarity"] is not None),
                                key=lambda item: item["similarity"], default=None)
                fallback_clues = [strongest["word"]] if strongest else []
                decisions = {}
                for seat, name in enumerate(players):
                    if name == setter:
                        continue
                    fallback = encode({"answers": [scripted_guess(fallback_clues, seat + index + number, phase, vectors)], "spend": False})
                    decisions[name] = Decision(
                        f"{setter}의{phase}차 히든 워드를 추측하세요. {evidence}"
                        f"내 피스 {match.pieces[name]}개, 이번 워드 추가 답 사용 {'완료' if name in paid else '가능'}. "
                        'JSON {"answers":["단어"],"spend":false} 형식으로 한글 명사 답 하나를 제출하세요. '
                        '한 워드에 한 번만 피스 1개를 소모해 {"answers":["단어","다른단어"],"spend":true}로 추가 답을 쓸 수 있습니다. '
                        "답은 전원이 제출하기 전까지 비공개입니다.", fallback,
                        valid=lambda text, name=name: _valid_guesses(text, match.pieces[name], name in paid),
                        invalid_default=encode({"answers": [], "spend": False}),
                    )
                times = {}
                submitted = match.decide_together("word_guess", decisions, response_times=times)
                guesses = {}
                for name, raw in submitted.items():
                    answers, spend = parse_guesses(raw, match.pieces[name], name in paid)
                    if preparation_times.get(name, 0) + times.get(name, 0) > GUESS_SECONDS * 1_000_000_000:
                        answers, spend = [], False
                    if spend:
                        paid.add(name)
                        match.pieces[name] -= 1
                    guesses[name] = answers
                    match.event("word_guess", {**stage, "answers": answers, "spent": int(spend)}, actor=name, private=[name])
                correct = [name for name, answers in guesses.items() if secret in answers]
                points = {name: multiplier for name in correct} if correct else {setter: phase * multiplier}
                for name, points_earned in points.items():
                    scores[name] += points_earned
                end = bool(correct) or phase == PHASES
                match.event("word_verdict", {**stage, "word": secret if end else None, "correct": correct,
                    "guesses": guesses, "points": points, "scores": scores.copy(), "pieces": match.pieces.copy(), "end": end})
                match.review_relationships(f"히든 워드 {number}라운드 {setter} {phase}차 판정")
                if end:
                    break
    ranking = sorted(players, key=lambda name: (-scores[name], order.index(name)))
    match.pieces[ranking[0]] += 4
    result = {"ranking": ranking, "scores": scores, "pieces": match.pieces.copy(),
              "living": ranking[:2], "prison": ranking[2:-1], "eliminated": ranking[-1:],
              "pieces_awarded": {ranking[0]: 4}, "tie_order": order}
    match.event("word_final", result)
    match.review_relationships("히든 워드 매치 종료")
    return result
