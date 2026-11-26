import React, {useState} from "react";
import {Selector} from "@astryxdesign/core/Selector";
import {Tab, TabList} from "@astryxdesign/core/TabList";
import {Table} from "./records.jsx";
import {tr} from "./locale.js";
import {scoreText} from "./replay.js";
import {hiddenEventText, hiddenPrivateOwner, hiddenRoundLabel, hiddenScorerLabel, hiddenSecretFor, hintScoreLabel, normalizedHiddenScores, similarityLabel, standardDictionaryScorer} from "./hidden-word-state.js";
import "./hidden-word.css";

export {applyHiddenEvent, hiddenEventText, hiddenActionText} from "./hidden-word-state.js";

const sameTurn = (item, turn) => item && turn && item.round === turn.round && item.setter === turn.setter;
const pointsText = (points) => tr(`${scoreText(points)}점`, `${scoreText(points)} VP`);

function Outcome({result, player}) {
  return result?.eliminated?.includes(player) ? tr("탈락", "Eliminated") :
    result?.living?.includes(player) ? tr("생활동", "Living Quarters") :
      result?.prison?.includes(player) ? tr("감옥동", "Prison Wing") : "–";
}

function Scoreboard({state, replay}) {
  const result = state.wordFinal ?? state.result;
  const scores = state.wordScores ?? {};
  const order = result?.ranking ?? state.wordSetup?.order ?? replay.match.players;
  return <Table caption={result ? tr("최종 순위", "Final standings") : tr("누적 승점", "Cumulative VP")}
    headers={tr(["참가자", "승점", "피스", "결과"], ["Player", "VP", "Pieces", "Result"])}
    rows={order.map((player, index) => [
      <button type="button" className="result-link" aria-pressed={replay.selected === player} onClick={() => replay.choosePlayer(player)}>{result ? `${index + 1}. ` : ""}{player}</button>,
      pointsText(result?.scores?.[player] ?? scores[player] ?? 0),
      result?.pieces?.[player] ?? state.wordPieces?.[player] ?? "–", <Outcome result={result} player={player} />,
    ])} />;
}

function Envelope({state, replay}) {
  const owner = hiddenPrivateOwner(state, replay);
  const envelope = owner ? state.wordEnvelopes?.[owner] : null;
  if (!envelope) return null;
  return <section className="hidden-envelope" data-envelope-owner={owner} aria-label={tr(`${owner}의 비공개 봉투`, `${owner}’s private envelope`)}>
    <h3>{tr(`${owner} · 봉투 ${envelope.envelope}`, `${owner} · Envelope ${envelope.envelope}`)}</h3>
    <div>{envelope.words.map((word) => <span key={word} lang="ko">{word}</span>)}</div>
    <p>{tr("이 단어들은 봉투를 고른 참가자에게만 공개됩니다.", "These words are visible only to the player who chose this envelope.")}</p>
  </section>;
}

function SimilarityTrail({state, replay}) {
  const turn = state.wordTurn;
  const phase = state.wordPhase?.phase;
  const own = replay.view === "operator" || hiddenPrivateOwner(state, replay) === turn?.setter;
  const normalized = normalizedHiddenScores(state.wordSetup);
  const signed = !normalized && ["word2vec", "fasttext"].includes(state.wordSetup?.score_mode);
  const relative = state.wordSetup?.reveal_rule === "nearest_noun_ratio_v1";
  const publicHints = state.wordSetup?.hint_visibility === "public";
  const hints = state.wordHints?.filter((hint) => sameTurn(hint, turn) && (hint.phase === phase || hint.publicWord)) ?? [];
  return <section className="hidden-similarities" aria-label={tr("힌트 후보 유사도", "Hint candidate similarities")}>
    <div className="hidden-similarity-heading"><h3>{normalized ? tr("보정 유사도", "Normalized similarity") : relative ? tr("원본 유사도", "Raw similarity") : tr("유사도", "Similarity")}</h3><span>{publicHints ? tr("95점 초과 시 힌트 제시 종료", "Hint submission ends above 95 points") : normalized ? tr("95점 초과 시 공개", "Reveal above 95 points") : relative ?
      tr("최근접 일반명사 유사도의 95% 초과 시 공개", "Reveal above 95% of the nearest common noun’s similarity") :
      tr("95% 초과 시 공개", "Reveal above 95%")}</span></div>
    {!hints.length ? <p className="muted">{tr("출제자가 힌트 후보를 고르고 있습니다.", "The setter is choosing a hint candidate.")}</p> : <ol>
      {hints.map((hint) => {
        const clue = state.wordClues?.findLast((item) => sameTurn(item, turn) && item.phase === hint.phase);
        const revealed = sameTurn(clue, turn) && clue.phase === hint.phase && clue.word === hint.word;
        const word = hint.publicWord || own && hint.word || revealed && clue.word;
        const ceiling = normalized ? 99.9 : 100;
        const score = Number.isFinite(hint.similarity) ? Math.max(signed ? -100 : 0, Math.min(ceiling, hint.similarity)) : 0;
        const qualifies = typeof hint.qualifies === "boolean" ? hint.qualifies : !relative && hint.similarity > 95;
        return <li key={`${hint.phase}:${hint.index}`} data-threshold={qualifies}>
          <span className="hidden-candidate-name">{(publicHints || hint.phase !== phase) && tr(`${hint.phase}차 · `, `Phase ${hint.phase} · `)}{hint.index}. <strong lang={word ? "ko" : undefined}>{word || tr("비공개 후보", "Private candidate")}</strong>{(relative || normalized) && qualifies && <small>{tr(" · 기준 충족", " · Criterion met")}</small>}</span>
          <span className="hidden-meter" data-signed={signed} data-negative={score < 0}><span style={{width: `${signed ? Math.abs(score) / 2 : score / ceiling * 100}%`, left: signed ? `${50 + Math.min(0, score) / 2}%` : undefined}} /></span>
          <strong>{hintScoreLabel(hint, state.wordSetup)}</strong>
        </li>;
      })}
    </ol>}
  </section>;
}

function PendingGuesses({state, replay}) {
  const phase = state.wordPhase;
  const owner = hiddenPrivateOwner(state, replay);
  const guesses = state.wordGuesses?.filter((guess) => sameTurn(guess, state.wordTurn) && guess.phase === phase?.phase &&
    (replay.view === "operator" || guess.player === owner)) ?? [];
  if (!guesses.length || state.wordVerdict) return null;
  return <section className="hidden-pending-guesses">
    <h3>{tr("비공개 제출 답안", "Private submitted answers")}</h3>
    <Table caption={tr("동시 공개 대기", "Awaiting simultaneous reveal")}
      headers={tr(["참가자", "답안", "사용 피스"], ["Player", "Answers", "Pieces spent"])}
      rows={guesses.map(({player, answers, spent}) => [player, answers.join(" / "), spent ?? 0])} />
  </section>;
}

function CurrentVerdict({state}) {
  const verdict = state.wordVerdict;
  if (!verdict) return null;
  const correct = verdict.correct ?? [];
  return <section className="hidden-verdict" data-correct={correct.length > 0}>
    <h3>{correct.length ? tr("정답!", "CORRECT!") : tr("정답자 없음", "No correct answers")}</h3>
    {verdict.word && <p className="hidden-answer" lang="ko">{verdict.word}</p>}
    <p>{correct.length ? correct.join(" · ") : tr(`${verdict.setter} 득점`, `${verdict.setter} scores`)}</p>
    <p>{Object.entries(verdict.points ?? {}).filter(([, points]) => points).map(([player, points]) => `${player} ${pointsText(points)}`).join(" · ")}</p>
  </section>;
}

export function HiddenWordStage({state, replay}) {
  const {wordSetup: setup, wordTurn: turn, wordPhase: phase} = state;
  const clues = state.wordClues?.filter((item) => sameTurn(item, turn)) ?? [];
  const result = state.wordFinal ?? state.result;
  const secret = hiddenSecretFor(state, replay);
  const scorer = hiddenScorerLabel(setup);
  const normalized = normalizedHiddenScores(setup);
  return <div className="hidden-word-stage">
    <div className="hidden-heading"><h2>{result ? tr("최종 결과", "Final results") : turn ? tr(`${turn.round} / ${setup?.rounds ?? 2}라운드`, `Round ${turn.round} of ${setup?.rounds ?? 2}`) : tr("히든 워드", "Hidden Word")}</h2>
      {turn && !result && <span>{tr(`승점 ×${turn.round === 2 ? 2 : 1}`, `VP ×${turn.round === 2 ? 2 : 1}`)}</span>}</div>
    {scorer && <p className="hidden-score-method"><strong>{scorer}</strong> · {standardDictionaryScorer(setup) && <>{tr("표준국어대사전 명사", "Standard Korean Language Dictionary nouns")} · </>}{normalized ? tr("보정 유사도 · 0–99.9점", "Normalized similarity · 0–99.9 points") : tr("코사인 유사도 × 100 · −100~100%", "Cosine similarity × 100 · −100–100%")}</p>}
    {setup?.display_projection === "raw_cosine_v1" && <p className="hidden-score-method">{tr("기존 기록은 판정을 유지하고 점수 표시만 보정합니다.", "Existing verdicts are retained; only score display is normalized.")}</p>}
    {result ? <Scoreboard state={state} replay={replay} /> : <>
      {setup?.discussion !== false && state.wordDiscussion && <p className="hidden-discussion">{hiddenEventText(state.wordDiscussion.turn ? "word_discussion_round" : "word_discussion", state.wordDiscussion)}</p>}
      {state.wordDealer?.stage === "enter" && <p className="hidden-discussion">{hiddenEventText("word_dealer", state.wordDealer)}</p>}
      {turn ? <>
        <div className="hidden-setter"><span>{tr("출제자", "Setter")}</span><strong>{turn.setter}</strong><span>{phase ? tr(`${phase.phase} / 3차 힌트`, `Hint phase ${phase.phase} of 3`) : tr("힌트 준비", "Preparing hints")}</span></div>
        <div className="hidden-secret" data-revealed={Boolean(secret?.revealed)}>
          <small>{secret?.revealed ? tr("공개된 히든 워드", "Revealed hidden word") : tr("히든 워드", "Hidden word")}</small>
          <strong lang={secret ? "ko" : undefined}>{secret?.word ?? "? ? ?"}</strong>
          {!secret && <span>{tr("정답 공개 전에는 출제자만 확인합니다.", "Only the setter knows the word until it is revealed.")}</span>}
        </div>
        <SimilarityTrail state={state} replay={replay} />
        {clues.map((clue) => <section key={clue.phase} className="hidden-clue"><small>{setup?.hint_visibility === "public" ? tr(`${clue.phase}차 선정 힌트`, `Phase ${clue.phase} selected clue`) : tr(`${clue.phase}차 공개 힌트`, `Phase ${clue.phase} public clue`)}</small><strong lang={clue.word ? "ko" : undefined}>{clue.word || tr("힌트 없음", "No clue")}</strong><span>{similarityLabel(clue.similarity, setup)}</span>
          {clue.word && clue.forced ? <p>{clue.source === "openai_stdict_nearest" ?
            tr("표준국어대사전 명사 중 정답과 가장 가까운 단어입니다.", "The closest noun to the answer among Standard Korean Language Dictionary entries.") : clue.source === "fasttext_nearest" ?
            tr("fastText 사전에서 정답과 가장 가까운 일반명사입니다.", "The closest common noun to the answer in the fastText vocabulary.") : clue.source === "word2vec_nearest" ?
            tr("Word2Vec 사전에서 정답과 가장 가까운 단어입니다.", "The closest word to the answer in the Word2Vec vocabulary.") :
            tr("이 단계에서 제출한 후보 중 유사도가 가장 높은 단어입니다.", "The most similar word among the candidates submitted in this phase.")}</p> : !clue.word ? <p>{tr("시간 내에 유효한 힌트가 제출되지 않았습니다.", "No valid clue was submitted before time ran out.")}</p> : null}</section>)}
        <PendingGuesses state={state} replay={replay} />
        <CurrentVerdict state={state} />
      </> : <div className="hidden-opening"><div className="hidden-envelope-art" aria-hidden="true"><span>?</span></div>
        <p>{tr("나의 단어는 숨기고, 유사도와 공개 힌트로 상대의 단어를 추리합니다.", "Hide your word and use similarities and public clues to deduce your opponents’ words.")}</p>
        <p>{tr("두 라운드 동안 모두 한 번씩 출제자가 됩니다. 2라운드는 모든 승점이 두 배입니다.", "Everyone sets one word per round. All Victory Points are doubled in Round 2.")}</p></div>}
      <Envelope state={state} replay={replay} />
      {setup && <Scoreboard state={state} replay={replay} />}
    </>}
  </div>;
}

export function HiddenWordInformation({state, replay}) {
  const [tab, setTab] = useState("history");
  const [round, setRound] = useState("");
  const {selected, choosePlayer, seek, match: {players}} = replay;
  const history = state.wordVerdicts?.filter((entry) => (!round || entry.round === Number(round)) && (!selected || entry.setter === selected || entry.correct?.includes(selected))) ?? [];
  return <aside className="caption match-info hidden-word-info" aria-label={tr("히든 워드 결과와 기록", "Hidden Word results and history")}>
    <TabList role="tablist" aria-label={tr("히든 워드 기록 종류", "Hidden Word record tabs")} size="sm" value={tab} onChange={setTab} hasDivider>
      <Tab id="hidden-history" value="history" label={tr("출제 기록", "Word history")} panelId="hidden-history-panel" />
      <Tab id="hidden-scores" value="scores" label={tr("승점", "Scores")} panelId="hidden-scores-panel" />
    </TabList>
    <div className="match-info-games">
      <Selector label={tr("기록을 볼 참가자", "Filter by player")} isLabelHidden value={selected} size="sm" onChange={choosePlayer}
        options={[{value: "", label: tr("전체 참가자", "All players")}, ...players.map((player) => ({value: player, label: player}))]} />
      <Selector label={tr("기록을 볼 라운드", "Filter by round")} isLabelHidden value={round} size="sm" onChange={setRound}
        options={[{value: "", label: tr("전체 라운드", "All rounds")}, ...[1, 2].map((value) => ({value: String(value), label: hiddenRoundLabel(value)}))]} />
    </div>
    <div id="hidden-history-panel" className="match-info-scroll" role="tabpanel" aria-labelledby="hidden-history" hidden={tab !== "history"} tabIndex={0}>
      {!history.length ? <p className="empty">{tr("아직 발표된 답안이 없습니다.", "No answers have been announced yet.")}</p> : history.map((verdict) => <section className="hidden-history-entry" key={verdict.step}>
        <h3><button className="result-link" type="button" onClick={() => seek(verdict.step)}>{hiddenRoundLabel(verdict.round)} · {verdict.setter} · {tr(`${verdict.phase}차`, `Phase ${verdict.phase}`)}</button></h3>
        <p>{hiddenEventText("word_verdict", verdict)}</p>
        {verdict.guesses && <Table caption={tr("공개된 답안", "Revealed answers")}
          headers={tr(["참가자", "답안", "승점"], ["Player", "Answers", "VP"])}
          rows={Object.entries(verdict.guesses).map(([player, answers]) => [player, Array.isArray(answers) ? answers.join(" / ") : String(answers), pointsText(verdict.points?.[player] ?? 0)])} />}
      </section>)}
    </div>
    <div id="hidden-scores-panel" className="match-info-scroll" role="tabpanel" aria-labelledby="hidden-scores" hidden={tab !== "scores"} tabIndex={0}>
      <Scoreboard state={state} replay={replay} />
    </div>
  </aside>;
}
