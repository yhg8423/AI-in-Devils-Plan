import React, {useEffect, useId, useRef, useState} from "react";
import {Tab, TabList} from "@astryxdesign/core/TabList";
import {ExileCast, ExileRoom} from "./exile-match.jsx";
import {tr} from "./locale.js";
import {Table} from "./records.jsx";
import "./loop-fence.css";

const copyEdges = (edges = []) => edges.map((edge) => [...edge]);
const copyImage = ({id, width, height, image}) => ({id, width, height, image});
const copyWorking = ({player, window, edges, crosses, board, submitted}) => ({player, window, edges: copyEdges(edges), crosses: copyEdges(crosses), board: copyImage(board), submitted});
const copyAttempt = ({player, window, attempt, elapsed_ns}) => ({player, window, attempt, elapsed_ns});
const progressText = (board) => {
  const lines = board?.edges.length ?? 0, crosses = board?.crosses.length ?? 0;
  return tr(`선 ${lines}개 · X ${crosses}개`, `${lines} ${lines === 1 ? "line" : "lines"} · ${crosses} X ${crosses === 1 ? "mark" : "marks"}`);
};
const windowText = (window) => tr(`생각 차례 ${window}`, `Thinking window ${window}`);

export function applyFenceEvent(state, type, data, event = {}) {
  switch (type) {
    case "fence_setup":
      state.fenceSetup = {version: data.version, players: [...data.players], priority: [...data.priority], size: data.size, survivors: data.survivors};
      state.fencePuzzle = null;
      state.fenceBoards = {};
      state.fenceOperations = [];
      state.fenceAttempts = [];
      state.fenceFinishes = [];
      state.fenceWindow = null;
      state.fenceBuzz = null;
      state.fenceVerdict = null;
      state.fenceRevealed = false;
      break;
    case "fence_puzzle":
      state.fencePuzzle = {id: data.puzzle.id, size: data.puzzle.size, board: copyImage(data.puzzle.board), step: event.step};
      break;
    case "fence_window":
      state.fenceWindow = {window: data.window, active: [...data.active]};
      state.fenceBuzz = null;
      state.fenceVerdict = null;
      break;
    case "fence_board": {
      const working = {...copyWorking(data), step: event.step};
      state.fenceBoards ??= {};
      state.fenceBoards[data.player] = working;
      state.fenceOperations ??= [];
      state.fenceOperations.push(working);
      break;
    }
    case "fence_buzz": state.fenceBuzz = {...copyAttempt(data), step: event.step}; state.fenceVerdict = null; break;
    case "fence_verdict":
      state.fenceVerdict = {...copyAttempt(data), correct: data.correct, reason: data.reason, step: event.step};
      state.fenceAttempts ??= [];
      state.fenceAttempts.push(state.fenceVerdict);
      break;
    case "fence_finish":
      state.fenceFinishes ??= [];
      state.fenceFinishes.push({...copyAttempt(data), rank: data.rank, step: event.step});
      break;
    case "fence_reveal":
      // A finished player's board remains private until all three survival places are secured.
      if ((state.fenceFinishes?.length ?? 0) < (state.fenceSetup?.survivors ?? 3)) break;
      state.fenceBoards = Object.fromEntries(Object.entries(data.boards).map(([player, board]) => [player, {...copyWorking({...board, player}), step: event.step}]));
      state.fenceRevealed = true;
      state.fenceRevealStep = event.step;
      break;
  }
}

export function fenceBoardFor(state, players, selected, perspective = state.exilePerspective ?? "operator") {
  const participant = players.includes(perspective) ? perspective : null;
  const owner = perspective === "operator" || state.fenceRevealed ? (players.includes(selected) ? selected : participant ?? players[0]) : participant;
  const working = owner ? state.fenceBoards?.[owner] : null;
  return {owner, working, board: working?.board ?? state.fencePuzzle?.board ?? null};
}

export function fenceActionText(action) {
  let value;
  try { value = typeof action === "string" ? JSON.parse(action) : action; } catch { return tr("잘못된 그리기 형식", "Invalid drawing action"); }
  if (value?.type === "wait") return tr("대기 · 현재 선 유지", "Wait · Keep the current drawing");
  if (value?.type !== "draw") return tr("잘못된 그리기 형식", "Invalid drawing action");
  return `${tr("작업판 교체", "Replace drawing")} · ${progressText({edges: value.edges ?? [], crosses: value.crosses ?? []})}${value.submit ? tr(" · 버저 제출", " · Submit with buzzer") : ""}`;
}

export function fenceEventText(type, data) {
  switch (type) {
    case "fence_setup": return tr(`${data.size}×${data.size} 격자 · 하나의 닫힌 고리 · 먼저 완성한 ${data.survivors}명 생존`, `${data.size}×${data.size} grid · One closed loop · First ${data.survivors} finishers survive`);
    case "fence_puzzle": return tr("네 참가자에게 같은 울타리 퍼즐 공개", "The same Loop Fence Puzzle is revealed to all four players");
    case "fence_window": return `${windowText(data.window)} · ${data.active.join(" · ")}`;
    case "fence_board": return `${data.player} · ${progressText(data)}${data.submitted ? tr(" · 버저 제출", " · Submitted with buzzer") : ""}`;
    case "fence_buzz": return tr(`${data.player} · 버저! · ${data.attempt}번째 제출`, `${data.player} · BUZZ! · Attempt ${data.attempt}`);
    case "fence_verdict": return `${data.player} · ${data.correct ? tr("정답 · 올바른 고리", "Correct · Valid loop") : tr("오답 · 수정 후 재제출 가능", "Incorrect · Revise and resubmit")}`;
    case "fence_finish": return tr(`${data.player} · ${data.rank}위 완성 · 생존`, `${data.player} · Finished ${data.rank}${data.rank === 1 ? "st" : data.rank === 2 ? "nd" : "rd"} · Safe`);
    case "fence_reveal": return tr("세 명 생존 확정 · 모든 작업판 공개", "Three survivors secured · All drawings revealed");
  }
}

export function fencePlayerStatus(state, player) {
  const finish = state.fenceFinishes?.find((entry) => entry.player === player);
  if (state.result?.eliminated?.includes(player)) return {status: "eliminated", label: tr("탈락", "Eliminated"), call: tr("탈락", "OUT"), detail: tr("탈락", "Eliminated")};
  if (finish || state.result?.survivors?.includes(player)) return {status: "safe", label: tr("생존 확정", "Safe"), call: tr("완성!", "COMPLETE!"), detail: finish ? tr(`${finish.rank}위 생존`, `Rank ${finish.rank} · Safe`) : tr("생존", "Safe")};
  const incorrect = state.fenceVerdict?.player === player && !state.fenceVerdict.correct;
  const buzzed = state.fenceBuzz?.player === player && !state.fenceVerdict;
  return {status: "solving", label: tr("풀이 중", "Solving"), incorrect,
    call: incorrect ? tr("오답 · 재도전", "INCORRECT · RETRY") : buzzed ? tr("버저!", "BUZZ!") : undefined};
}

function FenceZoom({board, owner}) {
  const dialog = useRef(null), title = useId();
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(false), [owner]);
  useEffect(() => {
    if (open && board) { if (!dialog.current.open) dialog.current.showModal(); }
    else if (dialog.current.open) dialog.current.close();
  }, [open, board]);
  const label = owner ? tr(`${owner}의 작업판`, `${owner}’s drawing`) : tr("공개 퍼즐 · 표시 없음", "Public puzzle · Unmarked");
  return <>
    <button className="fence-zoom-button" type="button" aria-haspopup="dialog" disabled={!board} onClick={() => setOpen(true)}>{tr("퍼즐 확대", "Enlarge puzzle")}</button>
    <dialog className="fence-zoom-dialog" ref={dialog} aria-labelledby={title} onClose={() => setOpen(false)}>
      <header><h2 id={title}>{label}</h2><form method="dialog"><button type="submit" aria-label={tr("확대 퍼즐 닫기", "Close enlarged puzzle")}>{tr("닫기", "Close")}</button></form></header>
      {open && board && <img src={board.image} width={board.width} height={board.height} alt={label} />}
    </dialog>
  </>;
}

export function LoopFenceScene({state, players, selected, onChoose}) {
  const {owner, board} = fenceBoardFor(state, players, selected);
  const view = state.exilePerspective ?? "operator";
  const statuses = Object.fromEntries(players.map((player) => [player, fencePlayerStatus(state, player)]));
  const verdict = state.fenceVerdict;
  return <section className="exile-arena fence-arena pixel-frame" aria-label={tr("유배지 울타리 치기 세트장", "Exile Loop Fence Puzzle arena")}>
    <div className="exile-room">
      <ExileRoom title={tr("유배지 · 울타리 치기", "EXILE · LOOP FENCE PUZZLE")}
        label={tr("울타리 퍼즐과 네 참가자의 발판", "Loop Fence Puzzle and four player platforms")}
        caption={owner ? tr(`${owner}의 작업판${state.fenceRevealed ? " · 최종 공개" : " · 비공개"}`, `${owner}’s drawing · ${state.fenceRevealed ? "Final reveal" : "Private"}`) : tr("공개 퍼즐 · 각자의 선은 비공개", "PUBLIC PUZZLE · DRAWINGS ARE PRIVATE")}>
        <g className="fence-screen">
          <rect x="124" y="103" width="392" height="264" fill="#0b121a" stroke="#6c716f" strokeWidth="4" />
          {board ? <image href={board.image} x="128" y="107" width="384" height="256" preserveAspectRatio="none" data-board-id={board.id} data-board-owner={owner ?? "public"} className="fence-board" /> :
            <text className="fence-screen-cover" x="320" y="240">{tr("퍼즐 공개 대기", "WAITING FOR THE PUZZLE")}</text>}
        </g>
        {(verdict || state.fenceBuzz) && <g className="fence-scene-feedback" data-correct={verdict?.correct}>
          <rect x="154" y="377" width="332" height="30" rx="3" />
          <text x="320" y="397">{verdict ? `${verdict.player} · ${verdict.correct ? tr("정답!", "CORRECT!") : tr("오답 · 수정 후 재도전", "INCORRECT · TRY AGAIN")}` : `${state.fenceBuzz.player} · ${tr("버저!", "BUZZ!")}`}</text>
        </g>}
      </ExileRoom>
      <ExileCast players={players} selected={owner} onChoose={onChoose} statuses={statuses} canChoose={(player) => view === "operator" || state.fenceRevealed || view === player} />
    </div>
    <div className="fence-view-controls">
      <div className="exile-player-picker" role="group" aria-label={tr("작업판 참가자", "Drawing player")}>{players.map((player) => <button key={player} type="button" aria-pressed={owner === player}
        disabled={view !== "operator" && !state.fenceRevealed && view !== player} onClick={() => onChoose(player)}>{player}</button>)}</div>
      <FenceZoom board={board} owner={owner} />
    </div>
  </section>;
}

export function LoopFenceStage({state, replay}) {
  const {owner, working} = fenceBoardFor(state, replay.match.players, replay.selected, replay.view);
  const finishes = state.fenceFinishes ?? [], slots = state.fenceSetup?.survivors ?? 3;
  const cue = state.fenceVerdict ?? state.fenceBuzz;
  return <div className="fence-stage">
    <h2>{tr("울타리 치기", "Loop Fence Puzzle")}</h2>
    <p className="fence-phase">{state.result ? tr("최종 결과", "Final results") : state.fenceWindow ? tr(`하나의 퍼즐 · ${windowText(state.fenceWindow.window)}`, `One shared puzzle · ${windowText(state.fenceWindow.window)}`) : tr("게임 규칙", "Game rules")}</p>
    <ol className="fence-finish-slots" aria-label={tr("생존 세 자리", "Three survival places")}>{Array.from({length: slots}, (_, index) => {
      const finish = finishes.find((entry) => entry.rank === index + 1);
      return <li key={index} data-filled={Boolean(finish)}><small>{tr(`${index + 1}위`, `Rank ${index + 1}`)}</small><strong>{finish?.player ?? tr("미정", "Open")}</strong><span>{finish ? tr("생존", "Safe") : tr("완성 대기", "Awaiting finish")}</span></li>;
    })}</ol>
    <div className="fence-buzzer" data-correct={state.fenceVerdict?.correct}><strong>{tr("버저", "BUZZER")}</strong><p>{cue ? fenceEventText(state.fenceVerdict ? "fence_verdict" : "fence_buzz", cue) : tr("완성한 뒤 버저로 제출합니다.", "Submit with the buzzer when your loop is complete.")}</p></div>
    <Table caption={tr("참가자 상태", "Player status")} headers={tr(["참가자", "상태"], ["Player", "Status"])} rows={(state.result?.ranking ?? replay.match.players).map((player) => [player, fencePlayerStatus(state, player).label])} />
    {owner ? <section className="fence-own-progress" aria-label={tr(`${owner}의 그리기 현황`, `${owner}’s drawing progress`)}><h3>{tr(`${owner}의 작업판`, `${owner}’s drawing`)}</h3><p>{progressText(working)}</p><small>{state.fenceRevealed ? tr("경기 종료 후 공개된 작업판입니다.", "This drawing is public after the race.") : tr("현재 시점에 이 참가자에게만 보이는 선과 X입니다.", "These lines and X marks are private to this player at this point.")}</small></section> : <p className="fence-instructions muted">{tr("작업판의 선과 X는 각 참가자에게만 보입니다. 먼저 생존한 참가자의 완성판도 경기 종료 전에는 공개되지 않습니다.", "Lines and X marks are private to each player. Even a survivor’s completed drawing stays hidden until the race ends.")}</p>}
    <h3>{tr("하나의 닫힌 고리", "One closed loop")}</h3>
    <p className="fence-instructions">{tr("가로·세로로 이웃한 점을 이어 하나의 고리를 만드세요. 숫자 0–3은 그 칸의 네 변 중 선이 놓이는 수입니다. 빈칸에는 개수 조건이 없습니다. 선이 닿는 점에서는 반드시 두 선이 만나야 하며, 갈림길·교차·끊긴 끝은 허용되지 않습니다.", "Join adjacent dots horizontally or vertically to make one closed loop. Each 0–3 clue counts the lines on its four borders; blank cells have no count constraint. Every used dot must meet exactly two lines, with no branches, crossings or loose ends.")}</p>
    <p className="fence-instructions">{tr("같은 퍼즐을 먼저 완성한 세 명이 생존하고 마지막 한 명이 탈락합니다. 이 시뮬레이션에서는 오답을 수정해 재제출할 수 있습니다.", "The first three players to complete the same puzzle survive; the last player is eliminated. In this simulation, an incorrect submission may be revised and submitted again.")}</p>
    <details className="fence-syntax"><summary>{tr("선·X의 좌표 읽기", "Reading line and X coordinates")}</summary><p>{tr("점 좌표는 (열, 행)이며 0–7입니다. [H, 행, 열]은 오른쪽 이웃 점까지, [V, 행, 열]은 아래 이웃 점까지 한 칸을 잇습니다. X는 선을 놓지 않을 변의 메모입니다. 그리기는 기존 작업판 전체를 교체하고 대기는 그대로 유지합니다.", "Dot coordinates are (column, row), from 0–7. [H, row, column] joins the dot to its right neighbor; [V, row, column] joins it to the dot below. X marks note unused borders. Drawing replaces the entire previous working board; waiting keeps it unchanged.")}</p></details>
    {state.fenceSetup?.priority.length > 0 && <p className="fence-priority">{tr("제출은 기록된 응답 시간순으로 판정합니다. 시간이 같으면 추첨 우선순위", "Submissions follow recorded response times. Drawn priority for equal times")} · {state.fenceSetup.priority.join(" → ")}</p>}
  </div>;
}

export function LoopFenceInformation({state, replay}) {
  const [tab, setTab] = useState("attempts");
  const {owner} = fenceBoardFor(state, replay.match.players, replay.selected, replay.view);
  const attempts = state.fenceAttempts ?? [], finishes = state.fenceFinishes ?? [];
  const operations = (state.fenceOperations ?? []).filter((entry) => (!owner || entry.player === owner) && (replay.view === "operator" || entry.player === replay.view));
  return <aside className="caption fence-information" aria-label={tr("울타리 치기 제출과 기록", "Loop Fence Puzzle submissions and records")}>
    <TabList role="tablist" aria-label={tr("울타리 치기 정보 종류", "Loop Fence Puzzle information categories")} value={tab} onChange={setTab} size="sm" hasDivider>
      <Tab id="fence-attempts" value="attempts" label={tr("버저·판정", "Attempts")} panelId="fence-records-panel" />
      <Tab id="fence-drawings" value="drawings" label={tr("그리기 기록", "Drawings")} panelId="fence-records-panel" />
      <Tab id="fence-finishes" value="finishes" label={tr("완성 순위", "Finish order")} panelId="fence-records-panel" />
    </TabList>
    <div id="fence-records-panel" role="tabpanel" aria-labelledby={`fence-${tab}`}>
      {tab === "attempts" ? attempts.length ? <ol className="fence-history">{[...attempts].reverse().map((attempt) => <li key={attempt.step} data-correct={attempt.correct}><button type="button" onClick={() => replay.seek(attempt.step)}>
        <small>{windowText(attempt.window)} · {tr(`${attempt.attempt}번째 제출`, `Attempt ${attempt.attempt}`)}</small><strong>{fenceEventText("fence_verdict", attempt)}</strong></button></li>)}</ol> : <p className="muted">{tr("아직 버저 판정이 없어요.", "No buzzer verdicts yet.")}</p> : tab === "drawings" ? <>
        {owner && <h3>{tr(`${owner}의 그리기 기록`, `${owner}’s drawing history`)}</h3>}
        {operations.length ? <ol className="fence-history">{[...operations].reverse().map((entry) => <li key={entry.step}><button type="button" onClick={() => replay.seek(entry.step)}><small>{windowText(entry.window)}</small><strong>{fenceEventText("fence_board", entry)}</strong></button></li>)}</ol> : <p className="muted">{tr("이 시점에 볼 수 있는 비공개 그리기 기록이 없어요.", "No private drawing history is visible at this point.")}</p>}
      </> : <>
        {state.result && <Table caption={tr("최종 순위", "Final standings")} headers={tr(["순위", "참가자", "완성 차례", "결과"], ["Rank", "Player", "Finish window", "Result"])} rows={state.result.ranking.map((player, index) => [index + 1, player, state.result.finish_turns?.[player] ?? "–", state.result.eliminated.includes(player) ? tr("탈락", "Eliminated") : tr("생존", "Safe")])} />}
        {finishes.length ? <ol className="fence-history">{finishes.map((finish) => <li key={finish.step} data-correct="true"><button type="button" onClick={() => replay.seek(finish.step)}><strong>{fenceEventText("fence_finish", finish)}</strong><span>{windowText(finish.window)}</span></button></li>)}</ol> : <p className="muted">{tr("아직 완성한 참가자가 없어요.", "No players have finished yet.")}</p>}
        {state.fenceRevealed && <button type="button" className="fence-reveal-link" onClick={() => replay.seek(state.fenceRevealStep)}>{tr("경기 종료 후 작업판 공개로 이동", "Jump to the final drawing reveal")}</button>}
      </>}
    </div>
  </aside>;
}
