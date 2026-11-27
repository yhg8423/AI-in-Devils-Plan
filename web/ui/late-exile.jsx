import React, {useEffect, useId, useRef, useState} from "react";
import {Tab, TabList} from "@astryxdesign/core/TabList";
import {ExileCast, ExileRoom} from "./exile-match.jsx";
import {Table} from "./records.jsx";
import {tr} from "./locale.js";
import "./late-exile.css";

const imageView = (picture) => picture ? {id: picture.id, width: picture.width, height: picture.height,
  image: picture.image, alt: picture.alt, ...(picture.grid && {grid: {...picture.grid}})} : null;
const copyPoints = (points = []) => points.map((point) => [...point]);
const sameRound = (a, b) => a?.round === b?.round && (a?.question === undefined || a?.question === b?.question);
const phaseLabel = (phase) => ({observe: tr("국기 관찰", "Study the flags"), blank: tr("그림 없는 5초", "Five-second blank"), answer: tr("기억한 국기 5개 선택", "Choose five remembered flags"), reveal: tr("정답과 점수 공개", "Answers and scores revealed")})[phase] ?? tr("게임 규칙", "Game rules");
const roundLabel = (round) => tr(`${round}라운드`, `Round ${round}`);
const numbers = (items = []) => items.length ? items.join(" · ") : "–";
const ownerFor = (players, selected, perspective) => perspective === "operator" ? (players.includes(selected) ? selected : players[0]) : players.includes(perspective) ? perspective : null;

export function applyFlagEvent(state, type, data, event = {}) {
  switch (type) {
    case "flag_setup":
      state.flagSetup = {...data, players: [...data.players]}; state.flagPhase = null;
      state.flagFrame = null; state.flagResults = []; state.flagMemories = {}; state.flagMarks = {}; state.flagTotals = {}; break;
    case "flag_phase":
      state.flagPhase = {round: data.round, players: [...data.players], overtime: data.overtime,
        stage: data.stage, picture: imageView(data.picture), step: event.step};
      state.flagFrame = null;
      if (data.stage === "observe") { state.flagMarks = {}; state.flagMemories = {}; }
      break;
    case "flag_frame":
      state.flagFrame = {round: data.round, index: data.index, seconds: data.seconds, picture: imageView(data.picture)}; break;
    case "flag_memory": state.flagMemories ??= {}; state.flagMemories[data.player] = {round: data.round, memory: event.translation?.fields?.memory ?? data.memory}; break;
    case "flag_marks": state.flagMarks ??= {}; state.flagMarks[data.player] = {round: data.round, marks: [...data.marks]}; break;
    case "flag_result": {
      const result = {round: data.round, players: [...data.players], overtime: data.overtime, scores: {...data.scores},
        totals: {...data.totals}, correct: [...data.correct], picture: imageView(data.picture),
        answers: Object.fromEntries(Object.entries(data.answers).map(([player, answer]) => [player, {
          marks: [...answer.marks], correct: [...answer.correct], score: answer.score}])), step: event.step};
      state.flagResults ??= []; state.flagResults.push(result); state.flagTotals = {...data.totals};
      state.flagPhase = {round: data.round, players: [...data.players], overtime: data.overtime, stage: "reveal", picture: result.picture};
      state.flagFrame = null; break;
    }
    case "flag_tiebreak": state.flagTiebreak = {round: data.round, players: [...data.players], slots: data.slots}; break;
  }
}

export function applyRectEvent(state, type, data, event = {}) {
  switch (type) {
    case "rect_setup":
      state.rectSetup = {...data, players: [...data.players], priority: [...data.priority]};
      state.rectQuestions = []; state.rectAttempts = []; state.rectResults = []; state.rectQuestion = null; break;
    case "rect_question": {
      const question = {round: data.round, question: data.question, players: [...data.players], board: imageView(data.board),
        target: data.target, limit_seconds: data.limit_seconds, step: event.step};
      state.rectQuestions ??= []; state.rectQuestions.push(question); state.rectQuestion = question;
      state.rectWindow = null; state.rectBuzz = null; state.rectFeedback = null; break;
    }
    case "rect_window": state.rectWindow = {...data, eligible: [...data.eligible]}; state.rectBuzz = null; state.rectFeedback = null; break;
    case "rect_buzz": state.rectBuzz = {...data, step: event.step}; state.rectFeedback = null; break;
    case "rect_attempt":
      state.rectFeedback = {round: data.round, question: data.question, player: data.player, count: data.count,
        correct: data.correct, reason: data.reason, elapsed_ns: data.elapsed_ns, step: event.step};
      state.rectAttempts ??= []; state.rectAttempts.push(state.rectFeedback); break;
    case "rect_round_result":
    case "rect_question_end": {
      const result = {round: data.round, question: data.question, winner: data.winner, count: data.count,
        rank: data.rank, reason: data.reason, step: event.step};
      if (sameRound(state.rectQuestion, data)) Object.assign(state.rectQuestion, {ended: true, result});
      if (type === "rect_round_result") { state.rectResults ??= []; state.rectResults.push(result); }
      break;
    }
  }
}

export function applyGomokuEvent(state, type, data, event = {}) {
  switch (type) {
    case "gomoku_setup":
      state.gomokuSetup = {...data, players: [...data.players], colors: {...data.colors}};
      state.gomokuPlacements = []; state.gomokuBids = []; state.gomokuResults = []; break;
    case "gomoku_game":
      state.gomokuGame = {game: data.game, replay: data.replay, first_selector: data.first_selector};
      state.gomokuStones = []; state.gomokuPoints = []; state.gomokuWallets = {}; state.gomokuRound = null;
      state.gomokuStage = "select"; break;
    case "gomoku_round":
      state.gomokuRound = {game: data.game, round: data.round, selector: data.selector}; state.gomokuPoints = [];
      state.gomokuWallets = {}; state.gomokuStage = "select"; break;
    case "gomoku_wallet": state.gomokuWallets ??= {}; state.gomokuWallets[data.player] = {game: data.game, round: data.round, available: data.available, carry: data.carry}; break;
    case "gomoku_select":
      state.gomokuPoints = copyPoints(data.points); state.gomokuStage = "bid"; break;
    case "gomoku_bid":
      state.gomokuBids ??= []; state.gomokuBids.push({game: data.game, round: data.round, player: data.player,
        bids: [...data.bids], spent: data.spent, remaining: data.remaining, carry: data.carry, timeout: data.timeout, step: event.step}); break;
    case "gomoku_placement": {
      const placement = {game: data.game, round: data.round, selector: data.selector, points: copyPoints(data.points),
        owners: [...data.owners], stones: data.stones.map((stone) => ({x: stone.x, y: stone.y, player: stone.player})),
        winning_lines: structuredClone(data.winning_lines ?? {}), step: event.step};
      state.gomokuPlacements ??= []; state.gomokuPlacements.push(placement); state.gomokuStones = placement.stones;
      state.gomokuPoints = placement.points; state.gomokuStage = "placed"; break;
    }
    case "gomoku_game_result": state.gomokuResults ??= []; state.gomokuResults.push({...data, step: event.step}); state.gomokuStage = "result"; break;
    case "gomoku_finish": state.gomokuFinish = {winner: data.winner, eliminated: [...data.eliminated], pieces_awarded: {...data.pieces_awarded}}; break;
    case "gomoku_selection_timeout": state.gomokuTimeout = {...data}; break;
  }
}

export function lateExileActionText(phase, action) {
  let value;
  try { value = JSON.parse(action); } catch { return action; }
  if (phase.startsWith("flag_")) return Array.isArray(value?.marks) ? `${tr("선택", "Choices")} · ${numbers(value.marks)}` : typeof value?.memory === "string" ? `${tr("기억 메모", "Memory note")} · ${value.memory}` : action;
  if (phase.startsWith("rect_")) return value?.type === "wait" ? tr("대기", "Wait") : value?.type === "buzz" ? `${tr("버저", "Buzzer")} · ${value.count}` : action;
  if (Array.isArray(value?.points)) return `${tr("세 교점 선택", "Choose three intersections")} · ${value.points.map((p) => `(${p.join(", ")})`).join(" · ")}`;
  if (Array.isArray(value?.bids)) return `${tr("비공개 입찰", "Sealed bid")} · ${value.bids.join(" / ")}`;
  return action;
}

export function lateExileEventText(type, data) {
  switch (type) {
    case "flag_setup": return tr(`${data.players.length}명 · 3라운드 · 상위 ${data.survivor_count}명 생존`, `${data.players.length} players · Three rounds · Top ${data.survivor_count} survive`);
    case "flag_phase": return `${roundLabel(data.round)} · ${phaseLabel(data.stage)}`;
    case "flag_frame": return `${roundLabel(data.round)} · ${tr("국기", "Flag")} ${data.index} / 30`;
    case "flag_memory": return tr(`${data.player}의 비공개 기억 메모`, `${data.player}’s private memory note`);
    case "flag_marks": return `${data.player} · ${tr("비공개 선택", "Private choices")} ${numbers(data.marks)}`;
    case "flag_result": return `${roundLabel(data.round)} · ${tr("정답 국기", "Correct flags")} ${numbers(data.correct)}`;
    case "flag_tiebreak": return tr(`동률 재경기 · ${data.players.join(" · ")} · 생존 ${data.slots}자리`, `Tiebreak · ${data.players.join(" · ")} · ${data.slots} survival places`);
    case "rect_setup": return tr(`네모 세기 · 먼저 맞힌 ${data.survivor_count}명 생존`, `Rectangle Counting · First ${data.survivor_count} correct players survive`);
    case "rect_question": return `${roundLabel(data.round)} · ${tr("문제", "Question")} ${data.question} · ${tr("목표 합", "Target sum")} ${data.target}`;
    case "rect_window": return `${roundLabel(data.round)} · ${tr("생각 차례", "Thinking window")} ${data.window}`;
    case "rect_buzz": return `${data.player} · ${tr("버저!", "BUZZ!")}`;
    case "rect_attempt": return `${data.player} · ${data.count ?? "–"} · ${data.correct ? tr("정답! 생존", "CORRECT! SAFE") : tr("오답 · 이번 문제 응답 불가", "Incorrect · Locked out of this question")}`;
    case "rect_round_result": return tr(`${data.winner} · ${data.rank}위 생존 · 정답 ${data.count}개`, `${data.winner} · Rank ${data.rank}, safe · Answer: ${data.count}`);
    case "rect_timeout": return tr(`${data.player} · 5분 제한 초과`, `${data.player} · Five-minute limit exceeded`);
    case "flag_timeout": return tr(`${data.player} · 제한 시간 초과`, `${data.player} · Time limit exceeded`);
    case "rect_question_end": return tr(`문제 종료 · 정답 ${data.count}개 · 새 문제`, `Question ended · Answer: ${data.count} · New question`);
    case "gomoku_setup": return tr("15×15 판 · 매 라운드 10포인트 · 세 교점 비공개 입찰", "15×15 board · Ten points per round · Sealed bids for three intersections");
    case "gomoku_game": return tr(`${data.game}번째 대결 · 선 선택자 ${data.first_selector}`, `Game ${data.game} · First selector ${data.first_selector}`);
    case "gomoku_round": return tr(`${data.round}라운드 · 교점 선택 ${data.selector}`, `Round ${data.round} · ${data.selector} selects intersections`);
    case "gomoku_select": return `${data.selector} · ${copyPoints(data.points).map((p) => `(${p.join(", ")})`).join(" · ")}`;
    case "gomoku_wallet": return tr(`${data.player} · 사용 가능 ${data.available}포인트 · 이월 ${data.carry}`, `${data.player} · ${data.available} points available · ${data.carry} carried over`);
    case "gomoku_bid": return `${data.player} · ${tr("비공개 입찰", "Sealed bids")} ${numbers(data.bids)} · ${tr("잔액", "Remaining")} ${data.remaining}`;
    case "gomoku_placement": return tr(`${data.round}라운드 · 돌 배치 ${data.owners.join(" · ")}`, `Round ${data.round} · Stones placed for ${data.owners.join(" · ")}`);
    case "gomoku_game_result": return data.winner ? tr(`${data.winner} · 오목 완성`, `${data.winner} · Five in a row`) : tr("무승부 · 선 선택자를 바꿔 재경기", "Draw · Replay with the other first selector");
    case "gomoku_finish": return tr(`${data.winner} · 본선 복귀 · 피스 5개`, `${data.winner} · Returns to the main match · Five Pieces`);
    case "gomoku_selection_timeout": return tr(`${data.selector} · 선택 시간 초과`, `${data.selector} · Selection timed out`);
  }
}

export function flagView(state, players, selected, perspective = state.exilePerspective ?? "operator") {
  const owner = ownerFor(players, selected, perspective), phase = state.flagPhase;
  const result = state.flagResults?.findLast((row) => row.round === phase?.round);
  const marks = result?.answers?.[owner]?.marks ?? (phase && state.flagMarks?.[owner]?.round === phase.round ? state.flagMarks[owner].marks : []);
  const picture = phase?.stage === "blank" ? null : phase?.stage === "observe" ? state.flagFrame?.picture ?? phase.picture : phase?.picture;
  const memory = owner && phase && state.flagMemories?.[owner]?.round === phase.round ? state.flagMemories[owner].memory : null;
  return {owner, picture, marks, correct: phase?.stage === "reveal" ? result?.correct ?? [] : [], memory, result};
}

function FlagPicture({picture, marks = [], correct = []}) {
  if (!picture) return null;
  const grid = picture.grid;
  const centre = (index) => [grid.left + ((index - 1) % grid.columns) * grid.cell_width + grid.cell_width / 2,
    grid.top + Math.floor((index - 1) / grid.columns) * grid.cell_height + grid.cell_height / 2];
  return <svg viewBox={`0 0 ${picture.width} ${picture.height}`} role="img" aria-label={tr("국기 그림과 답안 표시", "Flags and answer marks")} className="late-picture" data-picture-id={picture.id}>
    <image href={picture.image} width={picture.width} height={picture.height} />
    {grid && marks.map((index) => { const [x, y] = centre(index); return <g key={`mark-${index}`} data-mark={index} className="flag-choice"><circle cx={x} cy={y} r={Math.min(grid.cell_width, grid.cell_height) * .40} /></g>; })}
    {grid && correct.map((index) => { const [x, y] = centre(index); return <g key={`correct-${index}`} data-answer={index} className="flag-check"><rect x={x - grid.cell_width / 2 + 4} y={y - grid.cell_height / 2 + 4} width={grid.cell_width - 8} height={grid.cell_height - 8} /><path d={`M${x - 23} ${y}l18 18 32-39`} /></g>; })}
  </svg>;
}

function PictureZoom({picture, marks, correct, label}) {
  const dialog = useRef(null), title = useId(); const [open, setOpen] = useState(false);
  useEffect(() => setOpen(false), [picture?.id]);
  useEffect(() => { if (open && picture) dialog.current?.showModal(); else dialog.current?.close(); }, [open, picture]);
  return <><button className="late-zoom" type="button" disabled={!picture} aria-haspopup="dialog" onClick={() => setOpen(true)}>{label ?? tr("그림 확대", "Enlarge picture")}</button>
    <dialog className="late-zoom-dialog" ref={dialog} aria-labelledby={title} onClose={() => setOpen(false)}><header><h2 id={title}>{label ?? tr("공개 문제", "Public puzzle")}</h2><form method="dialog"><button type="submit">{tr("닫기", "Close")}</button></form></header>
      {open && picture && <FlagPicture picture={picture} marks={marks} correct={correct} />}</dialog></>;
}

function FinalTable({state, players, scores}) {
  return <Table caption={state.result ? tr("최종 순위", "Final standings") : tr("참가자 점수", "Player scores")} headers={tr(["순위", "참가자", "점수", "상태"], ["Rank", "Player", "Score", "Status"])} rows={(state.result?.ranking ?? players).map((player, index) => [state.result ? index + 1 : "–", player, state.result?.scores?.[player] ?? scores?.[player] ?? 0,
    state.result?.eliminated?.includes(player) ? tr("탈락", "Eliminated") : state.result?.survivors?.includes(player) ? tr("생존", "Safe") : tr("경기 중", "Playing")])} />;
}

export function FlagsScene({state, players, selected, onChoose}) {
  const view = flagView(state, players, selected), phase = state.flagPhase;
  const statuses = Object.fromEntries(players.map((player) => [player, {status: state.result?.eliminated?.includes(player) ? "eliminated" : state.result?.survivors?.includes(player) ? "safe" : "playing",
    label: state.result?.eliminated?.includes(player) ? tr("탈락", "Eliminated") : tr(`${state.flagTotals?.[player] ?? 0}점`, `${state.flagTotals?.[player] ?? 0} points`),
    call: state.result?.eliminated?.includes(player) ? tr("탈락", "OUT") : state.result?.survivors?.includes(player) ? tr("생존!", "SAFE!") : undefined}]));
  return <section className="exile-arena late-arena flag-arena pixel-frame" aria-label={tr("유배지 만국기 세트장", "Exile Flags arena")}><div className="exile-room"><ExileRoom title={tr("유배지 · 만국기", "EXILE · FLAGS")} label={tr("국기 그림과 참가자 발판", "Flag screen and player platforms")} caption={phase ? `${roundLabel(phase.round)} · ${phaseLabel(phase.stage)}` : tr("국기 기억 게임", "Flag memory game")}>
      <rect x="123" y="103" width="394" height="274" fill="#0b121a" stroke="#727569" strokeWidth="4" />
      {view.picture ? <svg x="128" y="108" width="384" height="264" viewBox={`0 0 ${view.picture.width} ${view.picture.height}`}><FlagPicture {...view} /></svg> : <text className="late-cover" x="320" y="242">{phase?.stage === "blank" ? tr("기억하세요 · 5초", "REMEMBER · FIVE SECONDS") : tr("국기 공개 대기", "WAITING FOR FLAGS")}</text>}
    </ExileRoom><ExileCast players={players} selected={view.owner ?? selected} onChoose={onChoose} statuses={statuses} canChoose={(player) => (state.exilePerspective ?? "operator") === "operator" || player === state.exilePerspective} /></div>
    <div className="late-controls"><span>{phase?.stage === "observe" && state.flagFrame ? `${state.flagFrame.index} / 30 · 1${tr("초", "s")}` : phaseLabel(phase?.stage)}</span><PictureZoom {...view} /></div></section>;
}

export function FlagsStage({state, replay}) {
  const view = flagView(state, replay.match.players, replay.selected, replay.view), phase = state.flagPhase;
  return <div className="late-stage"><h2>{tr("만국기", "Flags")}</h2><p className="late-phase">{state.result ? tr("최종 결과", "Final results") : phase ? `${roundLabel(phase.round)} · ${phaseLabel(phase.stage)}` : tr("게임 규칙", "Game rules")}</p>
    <p>{tr("국기 10개를 같은 순서로 세 번 봅니다. 그림이 사라진 뒤 25개 중 앞서 관찰한 국기 5개를 고릅니다.", "Study ten flags three times in the same order. After the blank interval, choose the five flags among 25 that appeared earlier.")}</p>
    <p>{tr(`${replay.match.players.length}명 중 상위 ${state.flagSetup?.survivor_count ?? 3}명이 생존합니다.`, `The top ${state.flagSetup?.survivor_count ?? 3} of ${replay.match.players.length} players survive.`)}</p>
    <div className="late-timing"><span>30{tr("초 관찰", "s study")}</span><span>5{tr("초 공백", "s blank")}</span><span>60{tr("초 답안", "s answer")}</span></div>
    {phase?.stage === "answer" && <p className="late-sealed">{tr("관찰 그림은 숨겨졌습니다. 다른 참가자의 답안도 공개 전까지 비공개입니다.", "The study picture is hidden. Other players’ choices remain sealed until the reveal.")}</p>}
    {view.owner && view.marks.length > 0 && <p className="late-selection">{view.owner} · {tr("선택 번호", "Selected numbers")} <strong>{numbers(view.marks)}</strong></p>}
    {view.memory && <section className="late-memory"><h3>{tr(`${view.owner}의 비공개 기억 메모`, `${view.owner}’s private memory note`)}</h3><p>{view.memory}</p></section>}
    {state.flagTiebreak && phase?.overtime && <p className="late-timing">{lateExileEventText("flag_tiebreak", state.flagTiebreak)}</p>}
    <FinalTable state={state} players={replay.match.players} scores={state.flagTotals} />
  </div>;
}

export function FlagsInformation({state, replay}) {
  const [tab, setTab] = useState("rounds");
  return <aside className="caption late-information"><h2>{tr("라운드별 국기 결과", "Flag round results")}</h2><TabList role="tablist" aria-label={tr("만국기 기록", "Flags records")} size="sm" value={tab} onChange={setTab} hasDivider><Tab id="flag-rounds" value="rounds" label={tr("라운드 점수", "Round scores")} panelId="flag-information-panel" /><Tab id="flag-answers" value="answers" label={tr("선택·정답", "Choices and answers")} panelId="flag-information-panel" /></TabList>
    <div id="flag-information-panel" role="tabpanel" aria-labelledby={`flag-${tab}`}>{(state.flagResults ?? []).length ? <ol className="late-history">{state.flagResults.map((result) => <li key={result.round}><button type="button" onClick={() => replay.seek(result.step)}><strong>{roundLabel(result.round)}{result.overtime ? tr(" · 연장", " · Overtime") : ""}</strong><span>{tr("정답 국기", "Correct flags")} · {numbers(result.correct)}</span></button>
      <Table caption={roundLabel(result.round)} headers={tab === "rounds" ? tr(["참가자", "이번 점수", "누적"], ["Player", "Round", "Total"]) : tr(["참가자", "선택", "맞힌 번호"], ["Player", "Choices", "Correct choices"])} rows={result.players.map((player) => tab === "rounds" ? [player, result.scores[player] ?? 0, result.totals[player] ?? 0] : [player, numbers(result.answers[player]?.marks), numbers(result.answers[player]?.correct)])} /></li>)}</ol> : <p>{tr("라운드가 끝나면 선택과 점수를 공개합니다.", "Choices and scores appear when the round ends.")}</p>}</div></aside>;
}

function rectStatus(state, player) {
  const finish = state.rectResults?.find((result) => result.winner === player);
  const safe = finish || state.result?.survivors?.includes(player);
  const failed = state.rectAttempts?.some((attempt) => sameRound(attempt, state.rectQuestion) && attempt.player === player && !attempt.correct);
  const out = state.result?.eliminated?.includes(player);
  return {status: out ? "eliminated" : safe ? "safe" : failed ? "locked" : "playing", incorrect: failed,
    label: out ? tr("탈락", "Eliminated") : finish ? tr(`${finish.rank}위 생존`, `Rank ${finish.rank} · Safe`) : safe ? tr("생존", "Safe") : failed ? tr("이번 문제 응답 불가", "Locked out of this question") : tr("네모 세는 중", "Counting rectangles"),
    call: out ? tr("탈락", "OUT") : safe ? tr("정답!", "CORRECT!") : failed ? tr("오답!", "INCORRECT!") : state.rectBuzz?.player === player && !state.rectFeedback ? tr("버저!", "BUZZ!") : undefined};
}

export function RectangleExileScene({state, players, selected, onChoose}) {
  const picture = state.rectQuestion?.board, feedback = state.rectFeedback;
  return <section className="exile-arena late-arena pixel-frame" aria-label={tr("유배지 네모 세기 세트장", "Exile Rectangle Counting arena")}><div className="exile-room"><ExileRoom title={tr("유배지 · 네모 세기", "EXILE · RECTANGLE COUNTING")} label={tr("숫자 격자와 참가자 발판", "Number grid and player platforms")} caption={state.rectQuestion ? `${roundLabel(state.rectQuestion.round)} · ${tr("목표 합", "Target sum")} ${state.rectQuestion.target}` : tr("네모 세기 공개 문제", "Public Rectangle Counting puzzle")}>
      <rect x="123" y="103" width="394" height="274" fill="#0b121a" stroke="#727569" strokeWidth="4" />
      {picture ? <image href={picture.image} x="128" y="108" width="384" height="264" preserveAspectRatio="xMidYMid meet" data-picture-id={picture.id} /> : <text className="late-cover" x="320" y="242">{tr("문제 공개 대기", "WAITING FOR THE PUZZLE")}</text>}
      {(feedback || state.rectBuzz) && <g className="late-feedback" data-correct={feedback?.correct}><rect x="152" y="382" width="336" height="28" /><text x="320" y="401">{feedback ? `${feedback.player} · ${feedback.count ?? "–"} · ${feedback.correct ? tr("정답!", "CORRECT!") : tr("오답!", "INCORRECT!")}` : `${state.rectBuzz.player} · ${tr("버저!", "BUZZ!")}`}</text></g>}
    </ExileRoom><ExileCast players={players} selected={selected} onChoose={onChoose} statuses={Object.fromEntries(players.map((player) => [player, rectStatus(state, player)]))} /></div><div className="late-controls"><span>{tr("숫자의 합이 목표인 모든 직사각형", "Every rectangle whose cells sum to the target")}</span><PictureZoom picture={picture} /></div></section>;
}

export function RectangleExileStage({state, replay}) {
  const q = state.rectQuestion, feedback = state.rectFeedback;
  return <div className="late-stage"><h2>{tr("네모 세기", "Rectangle Counting")}</h2><p className="late-phase">{state.result ? tr("최종 결과", "Final results") : q ? `${roundLabel(q.round)} · ${tr("문제", "Question")} ${q.question}` : tr("게임 규칙", "Game rules")}</p>
    <p className="late-target">{tr("목표 합", "Target sum")} <strong>{q?.target ?? "–"}</strong></p><p>{tr("한 칸부터 판 전체까지, 칸의 합이 목표인 모든 직사각형을 셉니다. 빈칸은 0입니다.", "Count every grid-aligned rectangle whose cells sum to the target, including a single cell and the whole board. Blank cells count as zero.")}</p>
    <p className="late-timing">{q?.limit_seconds ?? 300}{tr("초 안에 버저 · 버저 뒤 답변 10초", "s to buzz · Ten seconds to answer after buzzing")}</p>
    {feedback && <p className="late-feedback-text" data-correct={feedback.correct}>{lateExileEventText("rect_attempt", feedback)}</p>}
    {q?.result && <p className="late-selection">{tr("공개 정답", "Revealed answer")} · <strong>{q.result.count}</strong></p>}
    <p>{tr(`먼저 정답을 맞힌 ${state.rectSetup?.survivor_count ?? 2}명이 생존하고 나머지 ${replay.match.players.length - (state.rectSetup?.survivor_count ?? 2)}명은 탈락합니다. 정답자는 이후 문제에서 빠지고 오답자는 이번 문제에 다시 답할 수 없습니다.`, `The first ${state.rectSetup?.survivor_count ?? 2} correct players survive; the other ${replay.match.players.length - (state.rectSetup?.survivor_count ?? 2)} players are eliminated. Correct players leave later questions; wrong players cannot answer the current question again.`)}</p>
    <Table caption={tr("참가자 상태", "Player status")} headers={tr(["참가자", "상태"], ["Player", "Status"])} rows={(state.result?.ranking ?? replay.match.players).map((player) => [player, rectStatus(state, player).label])} />
  </div>;
}

export function RectangleExileInformation({state, replay}) {
  const [tab, setTab] = useState("attempts");
  return <aside className="caption late-information"><h2>{tr("문제·버저 판정 기록", "Questions and buzzer results")}</h2><TabList role="tablist" aria-label={tr("네모 세기 기록", "Rectangle Counting records")} size="sm" value={tab} onChange={setTab} hasDivider><Tab id="rect-attempts" value="attempts" label={tr("제출·판정", "Answers and verdicts")} panelId="rect-information-panel" /><Tab id="rect-questions" value="questions" label={tr("문제별 결과", "Question results")} panelId="rect-information-panel" /></TabList>
    <div id="rect-information-panel" role="tabpanel" aria-labelledby={`rect-${tab}`}><ol className="late-history">{(tab === "attempts" ? state.rectAttempts ?? [] : state.rectQuestions ?? []).map((item, index) => <li key={index}><button type="button" onClick={() => replay.seek(item.step)}><strong>{tab === "attempts" ? lateExileEventText("rect_attempt", item) : `${roundLabel(item.round)} · ${tr("문제", "Question")} ${item.question}`}</strong><span>{tab === "attempts" ? `${roundLabel(item.round)} · ${tr("문제", "Question")} ${item.question}` : `${tr("목표 합", "Target sum")} ${item.target} · ${item.result ? `${tr("정답", "Answer")} ${item.result.count} · ${item.result.winner ?? tr("승자 없음", "No winner")}` : tr("정답 비공개", "Answer sealed")}`}</span></button></li>)}</ol></div></aside>;
}

function GomokuBoard({state}) {
  const size = state.gomokuSetup?.size ?? 15, step = 36, position = (n) => 58 + (n - 1) * step;
  const placement = state.gomokuPlacements?.at(-1);
  const wins = placement?.game === state.gomokuGame?.game ? Object.values(placement.winning_lines ?? {}).flat() : [];
  return <svg className="gomoku-board" viewBox="0 0 620 620" role="img" aria-label={tr("15×15 포인트 오목 판", "15×15 Point Gomoku board")} data-board-size={size}>
    <rect width="620" height="620" rx="6" fill="#c59a58" stroke="#edd095" strokeWidth="5" />
    {Array.from({length: size}, (_, i) => <g key={i}><path d={`M${position(1)} ${position(i + 1)}H${position(size)}M${position(i + 1)} ${position(1)}V${position(size)}`} stroke="#5a4126" strokeWidth="1.4" /><text x={position(i + 1)} y="35" textAnchor="middle">{i + 1}</text><text x="30" y={position(i + 1) + 5} textAnchor="middle">{i + 1}</text></g>)}
    {(state.gomokuStones ?? []).map(({x, y, player}) => <g key={`${x}-${y}`} data-stone-player={player}><circle cx={position(x)} cy={position(y)} r="14" fill={state.gomokuSetup?.colors?.[player] === "white" ? "#fff6dd" : "#19202b"} stroke={state.gomokuSetup?.colors?.[player] === "white" ? "#535e75" : "#ffe4a1"} strokeWidth="2.5" /></g>)}
    {wins.map((line, index) => line.length > 1 && <path key={index} data-winning-line={index + 1} d={`M${position(line[0][0])} ${position(line[0][1])}L${position(line.at(-1)[0])} ${position(line.at(-1)[1])}`} stroke="#e8435c" strokeWidth="6" opacity=".85" />)}
    {(state.gomokuPoints ?? []).map(([x, y], index) => <g key={index} data-selected-point={index + 1}><circle cx={position(x)} cy={position(y)} r="19" fill="none" stroke={state.gomokuStage === "bid" ? "#b50062" : "#275ba4"} strokeWidth="3" strokeDasharray="5 3" /><text x={position(x) + 18} y={position(y) - 17} className="gomoku-point-label">{"ABC"[index]}</text></g>)}
  </svg>;
}

export function gomokuPrivateRows(state, players, selected, perspective = state.exilePerspective ?? "operator") {
  const owners = perspective === "operator" ? players : players.includes(perspective) ? [perspective] : [];
  return (state.gomokuBids ?? []).filter((row) => owners.includes(row.player));
}

export function PointGomokuScene({state, players, selected, onChoose}) {
  const winner = state.gomokuFinish?.winner ?? state.result?.survivors?.[0];
  const statuses = Object.fromEntries(players.map((player) => [player, {status: winner ? winner === player ? "safe" : "eliminated" : "playing", label: winner ? winner === player ? tr("본선 복귀", "Returns to main match") : tr("최종 탈락", "Eliminated") : state.gomokuRound?.selector === player ? tr("교점 선택", "Selects intersections") : tr("비공개 입찰", "Sealed bid"), call: winner ? winner === player ? tr("복귀!", "RETURNS!") : tr("탈락", "OUT") : undefined}]));
  return <section className="exile-arena late-arena gomoku-arena pixel-frame" aria-label={tr("유배지 포인트 오목 세트장", "Exile Point Gomoku arena")}><div className="exile-room"><ExileRoom title={tr("유배지 · 포인트 오목", "EXILE · POINT GOMOKU")} label={tr("오목 판과 두 참가자의 발판", "Gomoku board and two player platforms")} caption={state.gomokuRound ? `${roundLabel(state.gomokuRound.round)} · ${state.gomokuRound.selector} ${tr("교점 선택", "selects intersections")}` : tr("마지막 본선 복귀권", "The last return ticket")}>
      <svg x="148" y="81" width="344" height="344" viewBox="0 0 620 620"><GomokuBoard state={state} /></svg>
    </ExileRoom><ExileCast players={players} selected={selected} onChoose={onChoose} statuses={statuses} /></div><div className="late-controls gomoku-legend">{players.map((player) => <span key={player}><i data-color={state.gomokuSetup?.colors?.[player] ?? "black"} />{player}</span>)}</div></section>;
}

export function PointGomokuStage({state, replay}) {
  const players = replay.match.players, own = ownerFor(players, replay.selected, replay.view), winner = state.gomokuFinish?.winner ?? state.result?.survivors?.[0];
  const wallets = replay.view === "operator" ? players : own ? [own] : [];
  const round = state.gomokuRound;
  return <div className="late-stage"><h2>{tr("포인트 오목", "Point Gomoku")}</h2><p className="late-phase">{winner ? tr("최종 복귀자 결정", "Final returnee decided") : round ? `${roundLabel(round.round)} · ${state.gomokuStage === "select" ? tr("세 교점 선택", "Select three intersections") : state.gomokuStage === "bid" ? tr("비공개 입찰", "Sealed bidding") : tr("돌 배치 공개", "Stone placement revealed")}` : tr("게임 규칙", "Game rules")}</p>
    {winner && <div className="gomoku-returnee"><strong>{winner}</strong><span>{tr("본선 복귀 · 피스 5개 획득", "Returns to the main match · Gains five Pieces")}</span></div>}
    <p>{tr("선택자가 가로·세로·대각선으로 연속한 빈 교점 3개를 고르면 각자 비공개로 포인트를 입찰합니다. 각 교점의 승자가 자기 돌을 놓습니다.", "The selector chooses three consecutive empty intersections horizontally, vertically or diagonally. Both players bid privately, and each intersection’s winner places a stone.")}</p>
    <p className="late-timing">{tr("교점 선택 90초 · 입찰 90초 · 매 라운드 10포인트", "90 seconds to select · 90 seconds to bid · Ten points per round")}</p>
    <p>{tr("각 점에 최소 1포인트를 쓰며, 동률이면 선택자가 아닌 쪽의 돌을 놓습니다. 입찰은 승패와 관계없이 소모하고 잔액의 절반을 버림해 이월합니다. 정확한 5목만 인정하며 6목 이상은 제외합니다.", "Bid at least one point per intersection. Ties place the non-selector’s stone. Every bid is spent, and half the remainder, rounded down, carries over. Only exact fives count; overlines do not.")}</p>
    <p className="late-selection">{tr("선택한 교점", "Selected intersections")} · {(state.gomokuPoints ?? []).map((p, index) => `${"ABC"[index]} (${p.join(", ")})`).join(" · ") || "–"}</p>
    {wallets.length ? <Table caption={tr("비공개 포인트", "Private points")} headers={tr(["참가자", "사용 가능", "이월"], ["Player", "Available", "Carry"])} rows={wallets.map((player) => [player, state.gomokuWallets?.[player]?.available ?? "–", state.gomokuWallets?.[player]?.carry ?? "–"])} /> : <p className="late-sealed">{tr("입찰액과 남은 포인트는 공개되지 않습니다.", "Bid amounts and remaining points are private.")}</p>}
    <Table caption={tr("돌·대결 결과", "Stones and game result")} headers={tr(["참가자", "돌 수", "상태"], ["Player", "Stones", "Status"])} rows={players.map((player) => [player, (state.gomokuStones ?? []).filter((s) => s.player === player).length, winner ? winner === player ? tr("본선 복귀", "Returnee") : tr("탈락", "Eliminated") : tr("경기 중", "Playing")])} />
    {state.gomokuResults?.at(-1)?.winner === null && state.gomokuStage === "result" && <p>{tr("무승부입니다. 선 선택자를 바꾸고 새 판에서 재경기합니다.", "Draw. Replay on a fresh board with the other first selector.")}</p>}
  </div>;
}

export function PointGomokuInformation({state, replay}) {
  const [tab, setTab] = useState("placements"), bids = gomokuPrivateRows(state, replay.match.players, replay.selected, replay.view);
  return <aside className="caption late-information"><h2>{tr("라운드·입찰 기록", "Round and bid history")}</h2><TabList role="tablist" aria-label={tr("포인트 오목 기록", "Point Gomoku records")} size="sm" value={tab} onChange={setTab} hasDivider><Tab id="gomoku-placements" value="placements" label={tr("돌 배치", "Stone placements")} panelId="gomoku-information-panel" /><Tab id="gomoku-bids" value="bids" label={tr("비공개 입찰", "Sealed bids")} panelId="gomoku-information-panel" /></TabList>
    <div id="gomoku-information-panel" role="tabpanel" aria-labelledby={`gomoku-${tab}`}>{tab === "placements" ? <ol className="late-history">{(state.gomokuPlacements ?? []).map((row) => <li key={`${row.game}-${row.round}`}><button type="button" onClick={() => replay.seek(row.step)}><strong>{tr(`${row.game}번째 대결 · ${row.round}라운드`, `Game ${row.game} · Round ${row.round}`)}</strong><span>{row.points.map((p, index) => `${"ABC"[index]} (${p.join(", ")}) → ${row.owners[index]}`).join(" · ")}</span></button></li>)}</ol> : bids.length ? <Table caption={tr("본인 또는 운영자에게만 보이는 입찰", "Bids visible only to their owner or the operator")} headers={tr(["대결·라운드", "참가자", "A / B / C", "잔액", "이월"], ["Game · Round", "Player", "A / B / C", "Remaining", "Carry"])} rows={bids.map((row) => [`${row.game} · ${row.round}`, row.player, row.bids.join(" / "), row.remaining, row.carry])} /> : <p>{tr("이 시점에 볼 수 있는 비공개 입찰이 없습니다.", "No private bids are visible from this viewpoint.")}</p>}</div></aside>;
}
