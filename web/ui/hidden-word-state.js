import {tr} from "./locale.js";

const keyFor = ({round, setter}) => `${round}:${setter}`;
const hintKey = ({round, setter, phase, index}) => `${round}:${setter}:${phase}:${index}`;
const number = new Intl.NumberFormat("en", {maximumFractionDigits: 2});
export function similarityLabel(value) {
  if (!Number.isFinite(value)) return "–";
  const rounded = number.format(value);
  return value > 95 && rounded === "95" ? ">95%" : `${rounded}%`;
}
export function hintScoreLabel({similarity, valid, reason}) {
  if (reason === "out_of_vocabulary") return tr("벡터 사전에 없음", "Not in vector vocabulary");
  return valid === false ? tr("명사 아님", "Not a noun") : similarityLabel(similarity);
}
export const hiddenRoundLabel = (round) => tr(`${round}라운드`, `Round ${round}`);

export function applyHiddenEvent(state, type, data, event = {}) {
  switch (type) {
    case "word_setup":
      state.wordSetup = {...data, order: [...data.order]};
      state.wordScores = Object.fromEntries(data.order.map((player) => [player, 0]));
      state.wordPieces = {...data.pieces};
      state.wordEnvelopes = {};
      state.wordSecrets = {};
      state.wordHints = [];
      state.wordGuesses = [];
      state.wordVerdicts = [];
      state.wordClues = [];
      break;
    case "word_envelope":
      state.wordEnvelopes ??= {};
      state.wordEnvelopes[event.agent_name] = {...data, words: [...data.words]};
      break;
    case "word_secret":
      state.wordSecrets ??= {};
      state.wordSecrets[keyFor(data)] = {...data};
      break;
    case "word_round":
      state.wordRound = {...data};
      state.rounds = data.round;
      break;
    case "word_dealer": state.wordDealer = {...data}; break;
    case "word_discussion": state.wordDiscussion = {...data, turn: 0}; break;
    case "word_discussion_round": state.wordDiscussion = {...state.wordDiscussion, ...data}; break;
    case "word_discussion_end": state.wordDiscussion = null; break;
    case "word_turn":
      state.wordTurn = {...data};
      state.wordPhase = null;
      state.wordClue = null;
      state.wordVerdict = null;
      state.wordDiscussion = null;
      break;
    case "word_phase":
      state.wordPhase = {...data};
      state.wordClue = null;
      state.wordVerdict = null;
      break;
    case "word_similarity":
    case "word_hint": {
      state.wordHints ??= [];
      const previous = state.wordHints.find((hint) => hintKey(hint) === hintKey(data));
      const update = {round: data.round, setter: data.setter, phase: data.phase,
        index: data.index, similarity: data.similarity, valid: data.valid, reason: data.reason, step: event.step};
      if (type === "word_hint") update.word = data.word;
      if (previous) Object.assign(previous, update);
      else state.wordHints.push(update);
      break;
    }
    case "word_clue":
    case "word_closest":
      state.wordClue = {...data, step: event.step};
      state.wordClues ??= [];
      state.wordClues.push(state.wordClue);
      break;
    case "word_guess":
      state.wordGuesses ??= [];
      state.wordGuesses.push({...data, player: event.agent_name, step: event.step});
      break;
    case "word_verdict":
      state.wordVerdict = {...data, step: event.step};
      state.wordVerdicts ??= [];
      state.wordVerdicts.push(state.wordVerdict);
      state.wordScores = {...data.scores};
      state.wordPieces = {...data.pieces};
      break;
    case "word_final":
      state.wordFinal = {...data};
      state.wordScores = {...data.scores};
      state.wordPieces = {...data.pieces};
      break;
  }
}

export function hiddenActionText(phase, action) {
  let data;
  try { data = typeof action === "string" ? JSON.parse(action) : action; } catch { data = action; }
  if (phase === "word_envelope") return tr(`봉투 ${data} 선택`, `Choose envelope ${data}`);
  if (phase === "word_secret") return tr(`히든 워드 선택 · ${data}`, `Choose hidden word · ${data}`);
  if (phase === "word_hint") return tr(`비공개 힌트 후보 · ${data}`, `Private hint candidate · ${data}`);
  if (phase === "word_guess") {
    const answers = Array.isArray(data) ? data : data?.answers;
    if (Array.isArray(answers)) return tr(`답안 · ${answers.join(" / ")}`, `Answers · ${answers.join(" / ")}`);
  }
  return typeof data === "string" ? data : JSON.stringify(data);
}

export function hiddenEventText(type, data) {
  switch (type) {
    case "word_setup": return tr(`참가자 ${data.order.length}명 · ${data.rounds}라운드`, `${data.order.length} players · ${data.rounds} rounds`) + (data.score_mode === "word2vec" ? " · Word2Vec" : "");
    case "word_envelope": return tr(`봉투 ${data.envelope} · ${data.words.join(" · ")}`, `Envelope ${data.envelope} · ${data.words.join(" · ")}`);
    case "word_secret": return `${hiddenRoundLabel(data.round)} · ${tr("비공개 히든 워드", "Private hidden word")} · ${data.word}`;
    case "word_round": return `${hiddenRoundLabel(data.round)} · ${tr(`승점 ×${data.multiplier}`, `VP ×${data.multiplier}`)}`;
    case "word_dealer": return tr(`${data.player} · 딜러룸 ${data.stage === "enter" ? "입장" : "퇴장"}`, `${data.player} · ${data.stage === "enter" ? "Enters" : "Leaves"} dealer room`);
    case "word_discussion":
    case "word_discussion_round": {
      const title = data.stage === "opening" ? tr("시작 전 대화", "Opening discussion") : tr("출제 전 대화", "Pre-setter discussion");
      return data.turn ? `${title} · ${tr(`${data.turn} / ${data.rounds}턴`, `Turn ${data.turn} of ${data.rounds}`)}` : title;
    }
    case "word_discussion_end": return tr("대화 종료", "Discussion complete");
    case "word_turn": return `${hiddenRoundLabel(data.round)} · ${tr("출제자", "Setter")} ${data.setter}`;
    case "word_phase": return `${hiddenRoundLabel(data.round)} · ${data.setter} · ${tr(`${data.phase}차 힌트`, `Hint phase ${data.phase}`)}`;
    case "word_hint": return tr(`비공개 후보 ${data.index} · ${data.word} · ${hintScoreLabel(data)}`, `Private candidate ${data.index} · ${data.word} · ${hintScoreLabel(data)}`);
    case "word_similarity": return tr(`후보 ${data.index} · 유사도 ${hintScoreLabel(data)}`, `Candidate ${data.index} · Similarity ${hintScoreLabel(data)}`);
    case "word_clue":
    case "word_closest": return data.word ? tr(`공개 힌트 · ${data.word} · ${similarityLabel(data.similarity)}`, `Public clue · ${data.word} · ${similarityLabel(data.similarity)}`) :
      tr("시간 내 유효한 힌트 없음", "No valid clue submitted in time");
    case "word_guess": return `${data.answers.join(" / ")}${data.spent ? tr(" · 피스 1개 사용", " · 1 Piece spent") : ""}`;
    case "word_verdict": {
      const correct = data.correct ?? [];
      return correct.length ? tr(`정답 ${correct.join(" · ")} · 히든 워드 ${data.word}`, `Correct ${correct.join(" · ")} · Hidden word ${data.word}`) :
        tr(`${data.setter} 득점 · 정답자 없음${data.word ? ` · 히든 워드 ${data.word}` : ""}`, `${data.setter} scores · No correct answers${data.word ? ` · Hidden word ${data.word}` : ""}`);
    }
    case "word_final": return tr("히든 워드 최종 순위 공개", "Hidden Word final standings revealed");
  }
}

export function hiddenPrivateOwner(state, replay) {
  if (replay.view === "operator") {
    return replay.selected || state.wordTurn?.setter || state.wordSetup?.order[0];
  }
  return replay.view === "public" ? null : replay.view;
}

export function hiddenSecretFor(state, replay) {
  const turn = state.wordTurn;
  if (!turn) return null;
  const verdict = state.wordVerdicts?.findLast((item) => keyFor(item) === keyFor(turn) && item.word);
  if (verdict) return {word: verdict.word, revealed: true};
  const owner = hiddenPrivateOwner(state, replay);
  const secret = replay.view === "operator" || owner === turn.setter ? state.wordSecrets?.[keyFor(turn)] : null;
  return secret ? {word: secret.word, revealed: false} : null;
}
