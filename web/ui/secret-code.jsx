import React, {useEffect, useId, useRef, useState} from "react";
import {Tab, TabList} from "@astryxdesign/core/TabList";
import {ExileCast, ExileRoom} from "./exile-match.jsx";
import {en, tr} from "./locale.js";
import {Table} from "./records.jsx";
import "./secret-code.css";

const questionText = ({round, question}) => tr(`${round}라운드 · 문제 ${question}`, `Round ${round} · Question ${question}`);
const sameQuestion = (a, b) => a?.round === b?.round && a?.question === b?.question;
const clueText = (clue) => en ? clue.en ?? clue.text : clue.text;
const codeText = (code) => typeof code === "string" && code.length ? code : tr("답안 없음", "No code");
const waitRule = () => tr("모두 세 번 대기하거나 모두 오답이면 새 문제로 교체합니다. 생존자는 그대로입니다.", "Three all-wait windows or all players answering incorrectly replace the question without changing survivors.");

export function applyCodeEvent(state, type, data, event = {}) {
  switch (type) {
    case "code_setup":
      state.codeSetup = {...data, players: [...data.players], priority: [...(data.priority ?? [])]};
      state.codeQuestions = [];
      state.codeAttempts = [];
      state.codeResults = [];
      state.codeQuestion = null;
      state.codeBuzz = null;
      state.codeFeedback = null;
      state.codeWindow = null;
      break;
    case "code_question": {
      // Keep the public drawing and clues only; puzzle internals never enter the view model.
      const question = {round: data.round, question: data.question, players: [...data.players],
        board: {id: data.board.id, width: data.board.width, height: data.board.height, image: data.board.image},
        clues: data.clues.map(({id, text, en}) => ({id, text, en})), answer_seconds: data.answer_seconds, step: event.step};
      state.codeQuestions ??= [];
      state.codeQuestions.push(question);
      state.codeQuestion = question;
      state.codeBuzz = null;
      state.codeFeedback = null;
      state.codeWindow = null;
      break;
    }
    case "code_window":
      state.codeWindow = {...data, eligible: [...data.eligible]};
      state.codeBuzz = null;
      state.codeFeedback = null;
      break;
    case "code_buzz": state.codeBuzz = {...data, step: event.step}; state.codeFeedback = null; break;
    case "code_attempt":
      state.codeAttempts ??= [];
      state.codeFeedback = {round: data.round, question: data.question, player: data.player, code: data.code,
        correct: data.correct, reason: data.reason, elapsed_ns: data.elapsed_ns, answer_seconds: data.answer_seconds, step: event.step};
      state.codeAttempts.push(state.codeFeedback);
      break;
    case "code_question_end":
    case "code_round_result": {
      const result = {round: data.round, question: data.question, winner: data.winner, code: data.code,
        reason: data.reason, rank: data.rank, step: event.step};
      if (sameQuestion(state.codeQuestion, result)) Object.assign(state.codeQuestion, {ended: true, result});
      if (type === "code_round_result") {
        state.codeResults ??= [];
        state.codeResults.push(result);
      }
      break;
    }
  }
}

export function codeActionText(action) {
  let value;
  try { value = typeof action === "string" ? JSON.parse(action) : action; } catch { return tr("잘못된 답안", "Invalid code action"); }
  return value?.type === "wait" ? tr("대기", "Wait") : value?.type === "buzz" ? tr(`버저 · ${codeText(value.code)}`, `Buzzer · ${codeText(value.code)}`) : tr("잘못된 답안", "Invalid code action");
}

export function codeEventText(type, data) {
  switch (type) {
    case "code_setup": return tr("26장 카드 · 서로 다른 네 글자를 알파벳순으로 답하세요. 먼저 맞힌 세 명이 생존합니다.", "26 cards · Answer with four distinct letters in alphabetical order. The first three correct players survive.");
    case "code_question": return `${questionText(data)} · ${tr("카드와 단서 공개", "Cards and clues revealed")}`;
    case "code_window": return `${questionText(data)} · ${tr(`생각 시간 ${data.window}`, `Thinking window ${data.window}`)} · ${data.eligible.join(" · ")}`;
    case "code_buzz": return `${data.player} · ${tr("버저! 답변 대기", "BUZZ! Awaiting answer")}`;
    case "code_attempt": return `${data.player} · ${codeText(data.code)} · ${data.correct ? tr("정답 · 생존", "Correct · Safe") : data.reason === "invalid" ? tr("형식 오류 · 이 문제 응답 불가", "Invalid code · Locked out of this question") : tr("오답 · 이 문제 응답 불가", "Incorrect · Locked out of this question")}`;
    case "code_question_end": return `${questionText(data)} · ${data.reason === "all_locked" ? tr("전원 오답 · 새 문제", "All locked out · New question") : tr("전원 대기 · 새 문제", "All waited · New question")} · ${tr("정답", "Answer")} ${data.code}`;
    case "code_round_result": return `${questionText(data)} · ${data.winner} · ${tr(`${data.rank}위 생존`, `Rank ${data.rank} · Safe`)} · ${data.code}`;
  }
}

export function codePlayerStatus(state, player) {
  const finish = state.codeResults?.find((result) => result.winner === player);
  const attempts = (state.codeAttempts ?? []).filter((attempt) => sameQuestion(attempt, state.codeQuestion));
  const correct = attempts.find((attempt) => attempt.player === player && attempt.correct);
  if (state.result?.eliminated?.includes(player)) return {status: "eliminated", label: tr("탈락", "Eliminated"), call: tr("탈락", "OUT"), detail: tr("탈락", "Eliminated")};
  if (finish || correct || state.result?.survivors?.includes(player)) {
    const rank = finish?.rank ?? state.result?.ranking?.indexOf(player) + 1;
    return {status: "safe", label: tr("생존 확정", "Safe"), call: tr("정답!", "CORRECT!"), detail: rank ? tr(`${rank}위 생존`, `Rank ${rank} · Safe`) : tr("생존 확정", "Safe")};
  }
  const locked = attempts.some((attempt) => attempt.player === player && !attempt.correct);
  const buzzed = state.codeBuzz?.player === player && !state.codeFeedback;
  return {status: locked ? "locked" : "eligible", incorrect: locked,
    label: locked ? tr("이번 문제 응답 불가", "Locked out of this question") : tr("응답 가능", "Eligible"),
    call: locked ? tr("오답", "INCORRECT") : buzzed ? tr("버저!", "BUZZ!") : undefined,
    detail: locked ? tr("이번 문제 잠금", "Question locked") : undefined};
}

function Clues({clues = []}) {
  return <ol className="code-clues">{clues.map((clue) => <li key={clue.id}>{clueText(clue)}</li>)}</ol>;
}

function CodeZoom({question}) {
  const dialog = useRef(null), title = useId();
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(false), [question?.board.id]);
  useEffect(() => {
    if (open && question) { if (!dialog.current.open) dialog.current.showModal(); }
    else if (dialog.current.open) dialog.current.close();
  }, [open, question]);
  return <>
    <button className="code-zoom-button" type="button" aria-haspopup="dialog" disabled={!question} onClick={() => setOpen(true)}>{tr("카드·단서 확대", "Enlarge cards and clues")}</button>
    <dialog className="code-zoom-dialog" ref={dialog} aria-labelledby={title} onClose={() => setOpen(false)}>
      <header><h2 id={title}>{tr("카드와 공개 단서", "Cards and public clues")}</h2><form method="dialog"><button type="submit" aria-label={tr("확대 화면 닫기", "Close enlarged board")}>{tr("닫기", "Close")}</button></form></header>
      {open && question && <><img src={question.board.image} width={question.board.width} height={question.board.height} alt={tr("알파벳 A–Z 카드 26장: 각 카드의 숫자·색·도형", "26 cards A–Z, each showing a number, color and shape")} /><Clues clues={question.clues} /></>}
    </dialog>
  </>;
}

export function SecretCodeScene({state, players, selected, onChoose}) {
  const question = state.codeQuestion;
  const statuses = Object.fromEntries(players.map((player) => [player, codePlayerStatus(state, player)]));
  const feedback = state.codeFeedback;
  return <section className="exile-arena code-arena pixel-frame" aria-label={tr("유배지 비밀 코드 세트장", "Exile Secret Code arena")}>
    <div className="exile-room">
      <ExileRoom title={tr("유배지 · 비밀 코드", "EXILE · SECRET CODE")}
        label={tr("공개 카드 26장과 네 참가자의 발판", "26 public cards and four player platforms")}
        caption={question ? `${questionText(question)} · ${tr("먼저 정답을 맞히면 생존", "A correct answer secures survival")}` : tr("먼저 정답을 맞힌 세 명이 생존합니다", "The first three correct players survive")}>
        <g className="code-screen">
          <rect x="124" y="103" width="392" height="264" fill="#0b121a" stroke="#6c716f" strokeWidth="4" />
          {question ? <image href={question.board.image} x="128" y="107" width="384" height="256" preserveAspectRatio="none" data-board-id={question.board.id} className="code-board" /> :
            <text className="code-screen-cover" x="320" y="240">{tr("카드와 단서 공개 대기", "WAITING FOR CARDS AND CLUES")}</text>}
        </g>
        {(feedback || state.codeBuzz) && <g className="code-scene-feedback" data-correct={feedback?.correct}>
          <rect x="154" y="377" width="332" height="30" rx="3" />
          <text x="320" y="397">{feedback ? `${feedback.player} · ${codeText(feedback.code)} · ${feedback.correct ? tr("정답! 생존", "CORRECT! SAFE") : tr("오답 · 이번 문제 잠금", "INCORRECT · LOCKED")}` : `${state.codeBuzz.player} · ${tr("버저!", "BUZZ!")}`}</text>
        </g>}
      </ExileRoom>
      <ExileCast players={players} selected={selected} onChoose={onChoose} statuses={statuses} />
    </div>
    <div className="code-view-controls"><span>{tr("네 글자 · 알파벳순", "Four letters · Alphabetical order")}</span><CodeZoom question={question} /></div>
  </section>;
}

export function SecretCodeStage({state, replay}) {
  const question = state.codeQuestion;
  const answer = question?.result?.code ?? state.codeFeedback?.code ?? "";
  const feedback = state.codeFeedback;
  return <div className="code-stage">
    <h2>{tr("비밀 코드", "Secret Code")}</h2>
    <p className="code-phase">{state.result ? tr("최종 결과 · 생존 3명", "Final results · Three survivors") : question ? `${questionText(question)}${question.ended && !question.result.winner ? tr(" · 승자 없이 문제 종료", " · Ended without a winner") : ""}` : tr("게임 규칙", "Game rules")}</p>
    <div className="code-answer" data-correct={feedback?.correct}>
      <span className="code-buzzer" data-active={Boolean(state.codeBuzz)} aria-label={tr("버저", "Buzzer")}>BUZZ</span>
      <div><span className="code-answer-label">{question?.result ? tr("공개 정답", "Revealed answer") : feedback ? tr(`${feedback.player}의 답안`, `${feedback.player}’s answer`) : state.codeBuzz ? tr("버저 뒤 즉시 답변", "Answer immediately after buzzing") : tr("공개 답안 대기", "Awaiting a public answer")}</span>
        <div className="code-slots" aria-label={answer ? codeText(answer) : tr("답안 네 칸", "Four answer slots")}>{Array.from({length: 4}, (_, index) => <span key={index}>{answer[index] ?? "–"}</span>)}</div>
      </div>
    </div>
    {feedback && <p className="code-feedback" data-correct={feedback.correct}>{codeEventText("code_attempt", feedback)}</p>}
    <p className="code-timer"><strong>{question?.answer_seconds ?? state.codeSetup?.answer_seconds ?? 10}{tr("초", "s")}</strong> {tr("버저 후 답변 제한", "Answer limit after buzzing")}</p>
    <p className="code-instructions">{tr("서로 다른 카드 4장을 찾아 알파벳순으로 답합니다. 코드를 미리 준비하고 버저와 즉시 답변을 한 번에 제출합니다. 생각하는 시간은 버저 뒤 10초 제한에 포함되지 않습니다.", "Find four distinct cards and answer in alphabetical order. Prepare the code, then submit the buzzer and immediate answer together. Thinking time before buzzing is separate from the ten-second answer limit.")}</p>
    <Table caption={tr("참가자 상태", "Player status")} headers={tr(["참가자", "상태"], ["Player", "Status"])} rows={(state.result?.ranking ?? replay.match.players).map((player) => [player, codePlayerStatus(state, player).label])} />
    {question && <section aria-label={tr("공개 단서", "Public clues")}><h3>{tr("공개 단서", "Public clues")}</h3><Clues clues={question.clues} /></section>}
    <p className="muted code-instructions">{tr("정답자는 즉시 생존하고 이후 문제에 참여하지 않습니다. 오답자는 이번 문제만 잠깁니다.", "A correct player is immediately safe and leaves later questions. A wrong player is locked out of this question only.")} {waitRule()}</p>
    {state.codeSetup?.priority?.length > 0 && <p className="code-priority">{tr("버저 전 응답 시간순으로 판정합니다. 시간이 같으면 추첨 우선순위", "Answers are processed by pre-buzzer response time. Drawn priority for equal times")} · {state.codeSetup.priority.join(" → ")}</p>}
  </div>;
}

export function SecretCodeInformation({state, replay}) {
  const [tab, setTab] = useState("attempts");
  const attempts = state.codeAttempts ?? [], questions = state.codeQuestions ?? [], results = state.codeResults ?? [];
  return <aside className="caption code-information" aria-label={tr("비밀 코드 답안과 기록", "Secret Code answers and records")}>
    <TabList role="tablist" aria-label={tr("비밀 코드 정보 종류", "Secret Code information categories")} value={tab} onChange={setTab} size="sm" hasDivider>
      <Tab id="code-attempts" value="attempts" label={tr("버저·답안", "Attempts")} panelId="code-records-panel" />
      <Tab id="code-questions" value="questions" label={tr("문제 기록", "Questions")} panelId="code-records-panel" />
      <Tab id="code-results" value="results" label={tr("생존 결과", "Results")} panelId="code-records-panel" />
    </TabList>
    <div id="code-records-panel" role="tabpanel" aria-labelledby={`code-${tab}`}>
      {tab === "attempts" ? attempts.length ? <ol className="code-history">{[...attempts].reverse().map((attempt) => <li key={attempt.step} data-correct={attempt.correct}>
        <button type="button" onClick={() => replay.seek(attempt.step)}><small>{questionText(attempt)}</small><strong>{codeEventText("code_attempt", attempt)}</strong>
          {Number.isFinite(attempt.elapsed_ns) && <span>{tr(`버저 전 응답 ${(attempt.elapsed_ns / 1e9).toFixed(2)}초 · 즉시 답변`, `Pre-buzzer response ${(attempt.elapsed_ns / 1e9).toFixed(2)}s · Immediate answer`)}</span>}</button>
      </li>)}</ol> : <p className="muted">{tr("아직 공개된 버저 답안이 없어요.", "No buzzer answers have been made public yet.")}</p> : tab === "questions" ? questions.length ? <ol className="code-history">{[...questions].reverse().map((question) => <li key={question.step}>
        <button type="button" onClick={() => replay.seek(question.step)}><strong>{questionText(question)} · {tr("카드·단서 보기", "View cards and clues")}</strong><span>{question.result ? question.result.winner ? tr(`${question.result.winner} 생존 · 정답 ${question.result.code}`, `${question.result.winner} safe · Answer ${question.result.code}`) : tr(`새 문제로 교체 · 정답 ${question.result.code}`, `Replaced · Answer ${question.result.code}`) : tr("진행 중 · 정답 미공개", "In progress · Answer unrevealed")}</span></button>
      </li>)}</ol> : <p className="muted">{tr("아직 공개된 문제가 없어요.", "No questions have been revealed yet.")}</p> : <>
        {state.result && <Table caption={tr("최종 순위", "Final standings")} headers={tr(["순위", "참가자", "결과"], ["Rank", "Player", "Result"])} rows={state.result.ranking.map((player, index) => [index + 1, player, state.result.eliminated.includes(player) ? tr("탈락", "Eliminated") : tr(`${state.result.finish_rounds?.[player] ?? index + 1}라운드 생존`, `Safe in round ${state.result.finish_rounds?.[player] ?? index + 1}`)])} />}
        {results.length ? <ol className="code-history">{results.map((result) => <li key={result.step} data-correct="true"><button type="button" onClick={() => replay.seek(result.step)}><strong>{codeEventText("code_round_result", result)}</strong><span>{tr("해당 문제와 정답 보기", "View this question and answer")}</span></button></li>)}</ol> : <p className="muted">{tr("아직 생존 확정자가 없어요.", "No survivors have been confirmed yet.")}</p>}
      </>}
    </div>
  </aside>;
}
