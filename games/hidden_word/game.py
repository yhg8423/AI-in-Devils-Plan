"""Private noun clues, shared Word2Vec scoring, and sealed guesses."""

import json

from ..either_or.discussion import Discussion
from ..match import Decision, Match, encode
from ..models import STRATEGY_NOTE_LIMIT
from .vectors import load_vectors
from .words import ASSOCIATIONS, DECK_SHA256, ENVELOPES, WORDS, is_noun_word, scripted_guess


ROUNDS = 2
PHASES = 3
MAX_HINTS = 10
HINT_SECONDS = 15 * 60
GUESS_SECONDS = 5 * 60
THRESHOLD = 95
OPENING_TURNS = 10
DISCUSSION_TURNS = 4

RULES = """히든 워드 · 참가자 5~6명 · 2라운드

각자 비공개 봉투 하나를 골라 보통명사 다섯 개를 받습니다. 고유명사는 사용하지 않습니다.
추첨한 순서대로 매 라운드 한 번씩 출제자가 됩니다. 첫 라운드에는 받은 단어 중 하나를,
둘째 라운드에는 첫 라운드에 쓰지 않은 나머지 네 단어 중 하나를 히든 워드로 정합니다.
출제자는 자신의 정답을 숨기면서 득점하고, 다른 참가자는 상대의 단어를 맞혀 생존과 우승을 노리세요.

출제자의 힌트 단어는 딜러에게 비공개로 제출하는 한글 명사입니다.
제출한 힌트의 유사도 수치만 공개됩니다. 한 차례 힌트 제시는 최대 15분, 최대 10개입니다.
유사도가 95%를 초과하면 즉시 힌트를 마치고 그 단어를 공개합니다.
10개 또는 제한 시간 안에 기준을 넘지 못하면 그 단계에 제출한 힌트 중 유사도가 가장 높은 단어를 공개합니다.
최고 유사도가 같으면 먼저 제출한 단어를 택합니다.
공개된 이전 힌트는 이후 단계에서도 볼 수 있습니다.

출제자를 제외한 참가자는 5분 안에 추측 단어를 동시에 비공개 제출합니다.
한 히든 워드에 한 번만 피스 1개를 써서 답 하나를 추가할 수 있습니다. 피스는 정답 여부와 관계없이 소모됩니다.
맞힌 참가자는 각각 승점 1점을 얻고 그 출제자의 차례가 종료됩니다.
아무도 맞히지 못하면 출제자는 1차 1점, 2차 2점, 3차 3점을 차례로 얻습니다.
힌트 제시와 답 제출은 최대 세 차례 반복하며 실패 단계의 출제자 득점은 누적됩니다.
둘째 라운드는 모든 승점이 두 배입니다. 마지막 단계가 끝나거나 정답자가 나오면 히든 워드를 공개합니다.

2라운드 종료 후 승점 상위 2명은 생활동, 최하위 한 명은 탈락하며 나머지는 감옥동으로 갑니다.
1위는 피스 4개를 얻습니다. 이 매치에는 연맹의 징표 구제가 없습니다.

시뮬레이터 진행
방송의 봉투와 다른 새 보통명사 묶음을 사용합니다. 유사도는 모든 참가자에게 같은 사전학습 모델의
Word2Vec 코사인 유사도 × 100을 적용합니다. 음수도 그대로 표시하며 기준은 95% 초과입니다.
방송의 학습 모델과 같은 수치를 보장하지 않습니다. 참가자의 제공자·모델·호출 상한은 유사도에 영향을 주지 않습니다.
사전에 없는 힌트는 점수 없이 한 번의 제출 기회를 소모합니다. 시연 행동에도 같은 Word2Vec 판정을 사용합니다.
시뮬레이터에서는 정답 자체를 힌트로 제출할 수 없습니다.
방송은 6인 경기이며 이전 매치 생존자가 5명인 경로는 복귀자를 추가하지 않고 5인으로 진행합니다.
첫 대화 전에 각자 비공개 전략 요약을 정리하고 시작 전 10턴, 각 출제 차례 전 최대 4턴 대화합니다.
전체·논의실 대화, 이동, 초대와 같은 장소의 그룹 귓속말을 쓸 수 있습니다.
힌트 제시와 동시 정답 제출 중에는 대화하지 않습니다. 대화와 판정 후 친밀도·신뢰도를 검토합니다.
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
    unavailable = [word for word in WORDS if not any(hint in vectors for hint in ASSOCIATIONS[word])]
    if missing or unavailable:
        problems = []
        if missing:
            problems.append("봉투 단어 누락: " + ", ".join(missing))
        if unavailable:
            problems.append("시연 힌트 누락: " + ", ".join(unavailable))
        raise ValueError("Word2Vec 사전이 히든 워드 단어를 지원하지 않습니다. " + "; ".join(problems))
    return vectors


def validate_saved_setup(setup, vectors):
    if not isinstance(setup, dict) or setup.get("version") != 2:
        raise ValueError("이전 유사도 판정으로 시작한 히든 워드는 재개할 수 없습니다. Word2Vec으로 새 경기를 시작하세요.")
    if setup.get("scorer") != vectors.metadata:
        raise ValueError("저장된 경기와 Word2Vec 모델 정보·체크섬이 다릅니다. 당시 모델 파일을 사용하세요.")
    if setup.get("deck_sha256") != DECK_SHA256:
        raise ValueError("단어 봉투 구성이 변경되었습니다. 새 경기를 시작하세요.")


def _judge(vectors, secret, hint, cache):
    key = tuple(sorted((secret, hint)))
    if key in cache:
        return cache[key]
    try:
        result = {"similarity": vectors.similarity(secret, hint), "valid": True, "mode": "word2vec"}
    except KeyError:
        result = {"similarity": None, "valid": False, "mode": "word2vec", "reason": "out_of_vocabulary"}
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


def _discuss(match, discussion, order, topic, *, stage, round_number, turns):
    context = {"stage": stage, "round": round_number, "rounds": turns}
    match.event("word_discussion", context)
    discussion.rounds = turns
    for current in range(1, turns + 1):
        match.event("word_discussion_round", {**context, "turn": current})
        active = False
        for seat, name in enumerate(order):
            if name not in match.backends or match.live_turns <= 0:
                continue
            turn = len(match.events)
            prompt = discussion.request(name, turn, topic + (
                '\nJSON 전체 발언 {"type":"speak","channel":"public","text":"...","note":"전략 요약"}, '
                '논의실 대화는 channel:"room", 같은 장소 귓속말은 channel:"whisper", to에 상대 ID 또는 ID 배열. '
                '이동은 {"type":"move","room":1,"note":"전략 요약"}, 복도는 room:0. '
                '초대는 channel:"room_invite", room·to·text를 지정. '
                '응답은 {"type":"respond_invite","invite_id":0,"decision":"accept","note":"전략 요약"}. '
                '패스는 {"type":"pass","note":"전략 요약"}.'
            ), action_index=(current - 1) * len(order) + seat, notes=True,
                progress=f"대화 {current}/{turns}턴")
            def valid(action):
                try:
                    discussion.parse(name, action, turn, notes=True)
                except (ValueError, TypeError, RecursionError):
                    return False
                return True
            answer = match.request_action(name, "word_discussion", prompt.content,
                encode({"type": "pass", "note": "들은 제안과 현재 순위를 비교해 계획을 검토한다."}),
                valid=valid, request_type=prompt.msg_type)
            action = discussion.parse(name, answer, turn, notes=True)
            active = active or action.room is not None or bool(action.messages)
            for event in discussion.record(name, action, turn):
                match.event(event.msg_type, event.content, actor=event.agent_name,
                            private=() if event.visible_to == "all" else event.visible_to)
        if not active and stage != "opening":
            break
    match.event("word_discussion_end", context)
    match.review_relationships(f"히든 워드 {round_number}라운드 {stage} 대화 종료")


def play(match: Match, *, vectors=None):
    players = match.players
    if len(players) not in (5, 6) or len(set(players)) != len(players):
        raise ValueError("히든 워드에는 서로 다른 참가자 5~6명이 필요합니다.")
    vectors = validate_vectors(load_vectors() if vectors is None else vectors)
    if match.resume_log is not None and match.resume_log.resume:
        setup = next((json.loads(event["content"]) for event in match.resume_log.events
                      if event["msg_type"] == "word_setup"), None)
        validate_saved_setup(setup, vectors)
    demo_hints = {word: tuple(hint for hint in ASSOCIATIONS[word] if hint in vectors) for word in WORDS}
    order = match.rng.sample(list(players), len(players))
    scores = dict.fromkeys(players, 0)
    similarity_cache = {}
    envelopes, used = {}, {}
    discussion = Discussion(players, DISCUSSION_TURNS)
    match.event("rules", RULES)
    match.event("word_setup", {"version": 2, "players": players, "rounds": ROUNDS,
        "order": order, "envelopes": len(ENVELOPES), "threshold": THRESHOLD,
        "max_hints": MAX_HINTS, "hint_seconds": HINT_SECONDS, "guess_seconds": GUESS_SECONDS,
        "score_mode": "word2vec", "scorer": vectors.metadata, "deck_sha256": DECK_SHA256,
        "pieces": match.pieces.copy()})
    _strategy(match, "word_preparation", "첫 대화 전 협상과 출제·추측 계획을 정리하세요.", players)
    _discuss(match, discussion, order, "비공개 단어를 받기 전 생존과 협력 방안을 논의하세요.",
             stage="opening", round_number=0, turns=OPENING_TURNS)
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
            _discuss(match, discussion, order, f"{setter}의 출제 전입니다. 공개할 정보와 추측·피스 사용을 논의하세요.",
                     stage="before_setter", round_number=number, turns=DISCUSSION_TURNS)
            match.event("word_turn", {**context, "index": index})
            secret, clues = secrets[setter], []
            paid = set()
            for phase in range(1, PHASES + 1):
                stage = {**context, "phase": phase}
                match.event("word_phase", stage)
                elapsed = 0
                revealed = None
                candidates = []
                for hint_index in range(1, MAX_HINTS + 1):
                    default = demo_hints[secret][(hint_index + phase - 2) % len(demo_hints[secret])]
                    times = {}
                    hint = match.decide_together("word_hint", {setter: Decision(
                        f"{phase}차 힌트 {hint_index}/{MAX_HINTS}. 정답 {secret!r}은 다른 참가자에게 숨겨져 있습니다. "
                        "정답을 알아맞히기 어렵게 하면서 95%를 초과할 의미상 가까운 보통명사 한 개를 골라 딜러에게 비공개 제출하세요. "
                        "힌트 자체와 판정 수치는 출제자만 보고, 다른 참가자는 기준을 통과하기 전에는 수치만 봅니다. "
                        "고유명사, 정답 자체와 설명을 제외하고 한글 명사 한 개만 출력하세요.", default,
                        valid=lambda value: is_noun_word(value) and value != secret,
                    )}, response_times=times)[setter]
                    elapsed += times.get(setter, 0)
                    if elapsed > HINT_SECONDS * 1_000_000_000:
                        break
                    judgement = _judge(vectors, secret, hint, similarity_cache)
                    similarity = judgement["similarity"]
                    if judgement["valid"]:
                        candidates.append({"word": hint, "similarity": similarity, "forced": True})
                    else:
                        match.event("invalid_action", {"phase": "word_hint", "action": hint}, private=[setter])
                    record = {**stage, "index": hint_index, "word": hint, **judgement}
                    match.event("word_hint", record, actor=setter, private=[setter])
                    match.event("word_similarity", {key: value for key, value in record.items() if key != "word"})
                    if similarity is not None and similarity > THRESHOLD:
                        revealed = {"word": hint, "similarity": similarity, "forced": False}
                        break
                if revealed is None:
                    revealed = max(candidates, key=lambda entry: entry["similarity"], default={
                        "word": None, "similarity": None, "forced": True})
                match.event("word_clue", {**stage, **revealed})
                if revealed["word"] is not None:
                    clues.append(revealed["word"])
                preparation_times = _strategy(match, "word_guess_preparation", "공개 힌트와 수치에서 답 후보와 피스 사용 계획을 정리하세요.", [name for name in players if name != setter])
                decisions = {}
                for seat, name in enumerate(players):
                    if name == setter:
                        continue
                    fallback = encode({"answers": [scripted_guess(clues, seat + index + number, phase, vectors)], "spend": False})
                    decisions[name] = Decision(
                        f"{setter}의{phase}차 히든 워드를 추측하세요. 공개 힌트 {encode(clues)}. "
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
