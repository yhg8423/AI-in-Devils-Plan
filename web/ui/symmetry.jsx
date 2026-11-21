import React, {useEffect, useId, useRef, useState} from "react";
import {Tab, TabList} from "@astryxdesign/core/TabList";
import {ExileCast, ExileRoom} from "./exile-match.jsx";
import {tr} from "./locale.js";
import {Table} from "./records.jsx";
import "./symmetry.css";

export const symmetryColors = ["blue", "red", "green"];
const colorLabel = (color) => ({blue: tr("파랑", "Blue"), red: tr("빨강", "Red"), green: tr("초록", "Green")})[color];
const copyImage = (board) => board ? {id: board.id, width: board.width, height: board.height, image: board.image} : null;
const copyWorking = ({placements, boards}) => ({
  placements: Object.fromEntries(symmetryColors.map((color) => [color, (placements?.[color] ?? []).map(({piece, x, y, rotation}) => ({piece, x, y, rotation}))])),
  boards: Object.fromEntries(symmetryColors.map((color) => [color, copyImage(boards?.[color])])),
});
const copyAttempt = ({player, window, attempt, elapsed_ns}) => ({player, window, attempt, elapsed_ns});
const windowText = (window) => tr(`생각 차례 ${window}`, `Thinking window ${window}`);
const placementText = (placements) => symmetryColors.map((color) => `${colorLabel(color)} ${placements?.[color]?.length ?? 0}`).join(" · ");

export function applySymmetryEvent(state, type, data, event = {}) {
  switch (type) {
    case "sym_setup":
      state.symSetup = {version: data.version, mode: data.mode, players: [...data.players], priority: [...data.priority], survivors: data.survivors, thinking_passes: data.thinking_passes};
      state.symPuzzles = [];
      state.symTutorial = null;
      state.symBoards = {};
      state.symOperations = [];
      state.symAttempts = [];
      state.symFinishes = [];
      state.symWindow = null;
      state.symBuzz = null;
      state.symVerdict = null;
      state.symRevealed = false;
      state.symRevealStep = null;
      break;
    case "sym_puzzles":
      state.symPuzzles = data.puzzles.map(({id, label, piece_ids, board, details}) => ({id, label, piece_ids: [...piece_ids], board: copyImage(board), details: copyImage(details), step: event.step}));
      break;
    case "sym_tools":
      if (state.symSetup) state.symSetup = {...state.symSetup, version: data.version, thinking_passes: data.thinking_passes};
      state.symPuzzles = (state.symPuzzles ?? []).map((puzzle) => {
        const details = data.puzzles.find(({id}) => id === puzzle.id)?.details;
        return details ? {...puzzle, details: copyImage(details)} : puzzle;
      });
      break;
    case "sym_tutorial":
      state.symTutorial = {version: data.version, board: copyImage(data.board), explanations: {ko: data.explanations.ko, en: data.explanations.en}, step: event.step};
      break;
    case "sym_window":
      state.symWindow = {window: data.window, active: [...data.active]};
      state.symBuzz = null;
      state.symVerdict = null;
      break;
    case "sym_board": {
      const working = {...copyWorking(data), player: data.player, window: data.window, submitted: data.submitted, step: event.step};
      state.symBoards ??= {};
      state.symBoards[data.player] = working;
      state.symOperations ??= [];
      state.symOperations.push(working);
      break;
    }
    case "sym_buzz": state.symBuzz = {...copyAttempt(data), step: event.step}; state.symVerdict = null; break;
    case "sym_verdict":
      state.symVerdict = {...copyAttempt(data), correct: data.correct, reason: data.reason, step: event.step};
      state.symAttempts ??= [];
      state.symAttempts.push(state.symVerdict);
      break;
    case "sym_finish":
      state.symFinishes ??= [];
      state.symFinishes.push({...copyAttempt(data), rank: data.rank, step: event.step});
      break;
    case "sym_reveal":
      // Finishing does not expose a player's three assemblies before the race ends.
      if ((state.symFinishes?.length ?? 0) < (state.symSetup?.survivors ?? Infinity)) break;
      state.symBoards = Object.fromEntries(Object.entries(data.boards).map(([player, working]) => [player, {...copyWorking(working), player, step: event.step}]));
      state.symRevealed = true;
      state.symRevealStep = event.step;
      break;
  }
}

export function symmetryBoardFor(state, players, selected, color = "blue", perspective = state.exilePerspective ?? "operator") {
  const participant = players.includes(perspective) ? perspective : null;
  const owner = perspective === "operator" || state.symRevealed ? (players.includes(selected) ? selected : participant ?? players[0]) : participant;
  const working = owner ? state.symBoards?.[owner] : null;
  const puzzle = state.symPuzzles?.find((entry) => entry.id === color);
  return {owner, working, puzzle, board: working?.boards?.[color] ?? puzzle?.board ?? null};
}

export function symmetryActionText(action) {
  let value;
  try { value = typeof action === "string" ? JSON.parse(action) : action; } catch { return tr("잘못된 배치 형식", "Invalid arrangement action"); }
  if (value?.type === "wait") return tr("대기 · 세 작업판 유지", "Wait · Keep all three assemblies");
  if (value?.type !== "arrange") return tr("잘못된 배치 형식", "Invalid arrangement action");
  return `${tr("세 작업판 교체", "Replace all three assemblies")} · ${placementText(value.placements)}${value.submit ? tr(" · 버저 제출", " · Submit with buzzer") : ""}`;
}

export function symmetryEventText(type, data) {
  switch (type) {
    case "sym_setup": return tr(`파랑·빨강·초록 세 퍼즐 · 먼저 모두 완성한 ${data.survivors}명 생존`, `Blue, red and green puzzles · First ${data.survivors} to finish all three survive`);
    case "sym_puzzles": return tr("세 색의 조각과 빈 작업판 공개", "Pieces and empty workspaces for all three colors revealed");
    case "sym_tools": return tr("조각 세부 이미지와 비공개 전략 검토 적용", "Piece detail images and private strategy reviews enabled");
    case "sym_tutorial": return tr("별도 연습 조각의 조립 예시 공개", "Worked example using a separate practice set revealed");
    case "sym_window": return `${windowText(data.window)} · ${data.active.join(" · ")}`;
    case "sym_board": return `${data.player} · ${placementText(data.placements)}${data.submitted ? tr(" · 버저 제출", " · Submitted with buzzer") : ""}`;
    case "sym_buzz": return tr(`${data.player} · 버저! · ${data.attempt}번째 제출`, `${data.player} · BUZZ! · Attempt ${data.attempt}`);
    case "sym_verdict": return `${data.player} · ${data.correct ? tr("정답 · 세 색 모두 완성", "Correct · All three colors complete") : tr("오답 · 세 색을 검토하고 재제출", "Incorrect · Review all three colors and resubmit")}`;
    case "sym_finish": return tr(`${data.player} · ${data.rank}위 완성 · 생존`, `${data.player} · Rank ${data.rank} finish · Safe`);
    case "sym_reveal": return tr("생존자 확정 · 모든 색의 작업판 공개", "Survivors secured · All color assemblies revealed");
  }
}

export function symmetryPlayerStatus(state, player) {
  const finish = state.symFinishes?.find((entry) => entry.player === player);
  if (state.result?.eliminated?.includes(player)) return {status: "eliminated", label: tr("탈락", "Eliminated"), call: tr("탈락", "OUT"), detail: tr("탈락", "Eliminated")};
  if (finish || state.result?.survivors?.includes(player)) return {status: "safe", label: tr("생존 확정", "Safe"), call: tr("세 색 완성!", "ALL THREE!"), detail: finish ? tr(`${finish.rank}위 생존`, `Rank ${finish.rank} · Safe`) : tr("생존", "Safe")};
  const incorrect = state.symVerdict?.player === player && !state.symVerdict.correct;
  const buzzed = state.symBuzz?.player === player && !state.symVerdict;
  return {status: "assembling", label: tr("조립 중", "Assembling"), incorrect,
    call: incorrect ? tr("오답 · 재도전", "INCORRECT · RETRY") : buzzed ? tr("버저!", "BUZZ!") : undefined};
}

function SymmetryZoom({board, details, owner, color, example = false}) {
  const dialog = useRef(null), title = useId(), panel = useId();
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState("details"), [actualSize, setActualSize] = useState(false);
  const activeTab = tab === "details" && details ? "details" : "workspace";
  const image = activeTab === "details" ? details : board;
  useEffect(() => {
    if (open && image) { if (!dialog.current.open) dialog.current.showModal(); }
    else if (dialog.current.open) dialog.current.close();
  }, [open, image]);
  const workspaceLabel = example ? tr("조립 연습 예시", "Worked assembly example") : owner ? tr(`${owner}의 ${colorLabel(color)} 작업판`, `${owner}’s ${colorLabel(color).toLowerCase()} assembly`) : tr(`${colorLabel(color)} 공개 조각·빈 작업판`, `${colorLabel(color)} public pieces and empty workspace`);
  const label = activeTab === "details" ? tr(`${colorLabel(color)} 공개 조각 세부`, `${colorLabel(color)} public piece details`) : workspaceLabel;
  return <>
    <button className="sym-zoom-button" type="button" aria-haspopup="dialog" disabled={!image} onClick={() => setOpen(true)}>{example ? tr("연습 예시 확대", "Enlarge worked example") : tr("조각·작업판 확대", "Enlarge pieces and workspace")}</button>
    <dialog className="sym-zoom-dialog" ref={dialog} aria-labelledby={title} onClose={() => setOpen(false)}>
      <header><h2 id={title}>{label}</h2><form method="dialog"><button type="submit" aria-label={tr("확대 이미지 닫기", "Close enlarged image")}>{tr("닫기", "Close")}</button></form></header>
      {details && <TabList role="tablist" aria-label={tr("확대 이미지 종류", "Enlarged image type")} value={activeTab} onChange={setTab} size="sm" hasDivider>
        <Tab id={`${panel}-details`} value="details" label={tr("조각 세부", "Piece details")} panelId={panel} />
        <Tab id={`${panel}-workspace`} value="workspace" label={tr("작업판", "Workspace")} panelId={panel} />
      </TabList>}
      <div className="sym-zoom-scale" role="group" aria-label={tr("이미지 배율", "Image scale")}>
        <button type="button" aria-pressed={!actualSize} onClick={() => setActualSize(false)}>{tr("화면에 맞춤", "Fit to view")}</button>
        <button type="button" aria-pressed={actualSize} onClick={() => setActualSize(true)}>{tr("원본 크기 · 100%", "Original size · 100%")}</button>
      </div>
      <p className="sym-zoom-help">{details ? tr("조각 세부에서 꼭짓점 v와 변 e 번호를 확인하세요. 원본 크기에서는 가로·세로로 스크롤할 수 있습니다.", "Read vertex v and edge e labels in Piece details. Scroll horizontally and vertically at original size.") : tr("원본 크기에서는 가로·세로로 스크롤할 수 있습니다.", "Scroll horizontally and vertically at original size.")}</p>
      <div id={panel} role={details ? "tabpanel" : undefined} aria-labelledby={details ? `${panel}-${activeTab}` : undefined}>
        <div className="sym-zoom-image" data-scale={actualSize ? "actual" : "fit"}>
          {image && <img src={image.image} width={image.width} height={image.height} alt={label} loading="lazy" data-image-kind={example ? "tutorial" : activeTab} data-image-id={image.id} />}
        </div>
      </div>
    </dialog>
  </>;
}

export function SymmetryScene({state, players, selected, onChoose}) {
  const [color, setColor] = useState("blue");
  const {owner, board, puzzle} = symmetryBoardFor(state, players, selected, color);
  const view = state.exilePerspective ?? "operator";
  const statuses = Object.fromEntries(players.map((player) => [player, symmetryPlayerStatus(state, player)]));
  const verdict = state.symVerdict;
  return <section className="exile-arena sym-arena pixel-frame" aria-label={tr("유배지 대칭 퍼즐 세트장", "Exile Symmetrical Puzzle arena")}>
    <div id="sym-color-panel" role="tabpanel" aria-labelledby={`sym-color-${color}`}>
      <div className="exile-room">
        <ExileRoom title={tr("유배지 · 대칭 퍼즐", "EXILE · SYMMETRICAL PUZZLE")}
          label={tr(`대칭 퍼즐과 참가자 ${players.length}명의 발판`, `Symmetrical Puzzle and ${players.length} player platforms`)}
          caption={owner ? tr(`${owner} · ${colorLabel(color)} · ${state.symRevealed ? "최종 공개" : "비공개"}`, `${owner} · ${colorLabel(color)} · ${state.symRevealed ? "Final reveal" : "Private"}`) : tr(`${colorLabel(color)} 공개 조각 · 배치는 비공개`, `${colorLabel(color)} public pieces · Assemblies are private`)}>
          <g className="sym-screen">
            <rect x="124" y="103" width="392" height="264" fill="#0b121a" stroke="#6c716f" strokeWidth="4" />
            {board ? <image href={board.image} x="128" y="107" width="384" height="256" preserveAspectRatio="xMidYMid meet" data-board-id={board.id} data-board-owner={owner ?? "public"} data-puzzle-color={color} className="sym-board" /> :
              <text className="sym-screen-cover" x="320" y="240">{tr("세 색의 조각 공개 대기", "WAITING FOR THREE SETS OF PIECES")}</text>}
          </g>
          {(verdict || state.symBuzz) && <g className="sym-scene-feedback" data-correct={verdict?.correct}>
            <rect x="154" y="377" width="332" height="30" rx="3" />
            <text x="320" y="397">{verdict ? `${verdict.player} · ${verdict.correct ? tr("정답! 세 색 완성", "CORRECT! ALL THREE") : tr("오답 · 수정 후 재도전", "INCORRECT · TRY AGAIN")}` : `${state.symBuzz.player} · ${tr("버저!", "BUZZ!")}`}</text>
          </g>}
        </ExileRoom>
        <ExileCast players={players} selected={owner} onChoose={onChoose} statuses={statuses} canChoose={(player) => view === "operator" || state.symRevealed || view === player} />
      </div>
    </div>
    <div className="sym-color-controls">
      <TabList role="tablist" aria-label={tr("퍼즐 색 선택", "Puzzle color")} value={color} onChange={setColor} size="sm" hasDivider>
        {symmetryColors.map((entry) => <Tab key={entry} id={`sym-color-${entry}`} value={entry} label={colorLabel(entry)} panelId="sym-color-panel" />)}
      </TabList>
      <span>{colorLabel(color)} · {tr(`조각 ${puzzle?.piece_ids.length ?? 0}개`, `${puzzle?.piece_ids.length ?? 0} pieces`)}</span>
    </div>
    <div className="sym-view-controls">
      <div className="exile-player-picker" role="group" aria-label={tr("작업판 참가자", "Assembly player")}>{players.map((player) => <button key={player} type="button" aria-pressed={owner === player}
        disabled={view !== "operator" && !state.symRevealed && view !== player} onClick={() => onChoose(player)}>{player}</button>)}</div>
      <SymmetryZoom key={`${owner}:${color}`} board={board} details={puzzle?.details} owner={owner} color={color} />
    </div>
  </section>;
}

export function SymmetryStage({state, replay}) {
  const {owner, working} = symmetryBoardFor(state, replay.match.players, replay.selected, "blue", replay.view);
  const finishes = state.symFinishes ?? [], slots = state.symSetup?.survivors ?? replay.match.players.length - 1;
  const cue = state.symVerdict ?? state.symBuzz;
  return <div className="sym-stage">
    <h2>{tr("대칭 퍼즐", "Symmetrical Puzzle")}</h2>
    <p className="sym-phase">{state.result ? tr("최종 결과", "Final results") : state.symWindow ? tr(`세 색 한 세트 · ${windowText(state.symWindow.window)}`, `One three-color set · ${windowText(state.symWindow.window)}`) : tr("게임 규칙", "Game rules")}</p>
    <p className="sym-all-three">{tr("파랑·빨강·초록 세 퍼즐을 모두 완성한 뒤 버저를 누르세요.", "Complete the blue, red and green puzzles before pressing the buzzer.")}</p>
    <ol className="sym-finish-slots" style={{"--sym-slots": slots}} aria-label={tr(`생존 ${slots}자리`, `${slots} survival places`)}>{Array.from({length: slots}, (_, index) => {
      const finish = finishes.find((entry) => entry.rank === index + 1);
      return <li key={index} data-filled={Boolean(finish)}><small>{tr(`${index + 1}위`, `Rank ${index + 1}`)}</small><strong>{finish?.player ?? tr("미정", "Open")}</strong><span>{finish ? tr("생존", "Safe") : tr("세 색 완성 대기", "Awaiting all three")}</span></li>;
    })}</ol>
    <div className="sym-buzzer" data-correct={state.symVerdict?.correct}><strong>{tr("버저", "BUZZER")}</strong><p>{cue ? symmetryEventText(state.symVerdict ? "sym_verdict" : "sym_buzz", cue) : tr("세 색 전체를 한 번에 판정합니다.", "All three colors are judged together.")}</p></div>
    <section className="sym-placement-progress" aria-label={tr("색별 배치 수", "Placements by color")}>
      <h3>{owner ? tr(`${owner}의 배치 현황`, `${owner}’s placements`) : tr("공개 조각 수", "Public piece counts")}</h3>
      <ul>{symmetryColors.map((color) => {
        const total = state.symPuzzles?.find((entry) => entry.id === color)?.piece_ids.length ?? 0;
        return <li key={color} data-progress-color={color}><span>{colorLabel(color)}</span><strong>{owner ? working?.placements[color].length ?? 0 : "–"} / {total}</strong><small>{owner ? tr("배치", "Placed") : tr("배치 비공개", "Placements private")}</small></li>;
      })}</ul>
      <small>{tr("배치 수는 정답 판정이 아닙니다.", "Placement counts do not judge symmetry.")}</small>
    </section>
    <Table caption={tr("참가자 상태", "Player status")} headers={tr(["참가자", "상태"], ["Player", "Status"])} rows={(state.result?.ranking ?? replay.match.players).map((player) => [player, symmetryPlayerStatus(state, player).label])} />
    <h3>{tr("색마다 하나의 대칭 도형", "One symmetric shape per color")}</h3>
    <p className="sym-instructions">{tr("각 색의 조각을 빠짐없이 사용해 겹치지 않고 변으로 이어진 하나의 도형을 만드세요. 전체 도형과 그 안의 빈 공간이 하나 이상의 대칭축을 기준으로 일치해야 합니다. 조각 사이의 경계는 대칭일 필요가 없습니다.", "Use every piece of each color to build one shape, joined along edges without overlaps. The whole shape, including its empty spaces, must have at least one reflection axis. Piece boundaries do not need to be symmetric.")}</p>
    <p className="sym-instructions">{tr("길이가 다른 변이나 변의 일부끼리 맞닿아도 됩니다. 꼭짓점만 닿으면 연결로 인정하지 않습니다. 버저 판정은 세 색 전체의 정답 여부만 알리며, 색별 정답 여부나 정답 대칭축은 알려주지 않습니다.", "Edges may have different lengths and touch along only part of an edge. Point-only contact does not connect pieces. The buzzer reports only whether all three colors are correct, without color-specific feedback or solution axes.")}</p>
    <p className="sym-instructions">{tr(`먼저 세 색을 모두 완성한 ${slots}명이 생존하고 마지막 한 명이 탈락합니다. 생존자의 완성판도 경기 종료 전에는 공개되지 않습니다. 이 시뮬레이션에서는 오답을 수정해 재제출할 수 있습니다.`, `The first ${slots} players to finish all three colors survive; the last player is eliminated. Finished assemblies stay private until the race ends. In this simulation, incorrect submissions may be revised and resubmitted.`)}</p>
    {state.symSetup?.version >= 3 && <p className="sym-instructions">{tr(`자신의 메모와 최근 실패 기록은 다음 생각 차례에도 유지됩니다. 비공개 전략 검토는 차례마다 최대 ${state.symSetup.thinking_passes ?? 3}번이며, 준비되면 그 전에 배치를 확정할 수 있습니다.`, `Your own memo and recent failed attempts carry into the next thinking window. Each window allows up to ${state.symSetup.thinking_passes ?? 3} private strategy passes; you may finalize the arrangement earlier.`)}</p>}
    {state.symTutorial?.board && <section className="sym-tutorial" aria-label={tr("별도 조각 조립 연습", "Separate practice-piece assembly")}>
      <h3>{tr("조립 연습 예시", "Worked assembly example")}</h3>
      <p>{tr("EX1…은 접합과 대칭을 설명하는 별도의 연습용 조각입니다.", "EX1… are a separate practice set for learning edge joins and reflection symmetry.")}</p>
      <img className="sym-tutorial-preview" src={state.symTutorial.board.image} width={state.symTutorial.board.width} height={state.symTutorial.board.height} alt={tr("EX1… 연습 조각의 조립 예시", "Worked example with EX1… practice pieces")} data-tutorial-image-id={state.symTutorial.board.id} loading="lazy" />
      <p>{tr(state.symTutorial.explanations.ko, state.symTutorial.explanations.en)}</p>
      <SymmetryZoom key={state.symTutorial.board.id} board={state.symTutorial.board} example />
    </section>}
    <details className="sym-syntax"><summary>{tr("배치와 회전 방법", "Placement and rotation")}</summary>
      <p>{tr("고정된 게임판이나 정답 윤곽 없이 다각형 조각을 자유롭게 배치합니다. 조각은 원하는 각도로 시계 방향 회전할 수 있고, 360°마다 한 바퀴로 계산하며 뒤집을 수 없습니다. 좌표 (x, y)는 회전 후 조각을 감싸는 사각형의 왼쪽 위이며 소수와 음수도 사용할 수 있습니다. 화면은 배치에 맞춰 자동으로 조정됩니다. 직접 배치는 piece·x·y·rotation 네 항목을 지정합니다. 배치 행동은 세 색의 작업판을 모두 교체하며, 대기는 현재 배치를 유지합니다.", "Freely arrange polygon pieces without a fixed game board or target outline. Rotate clockwise by any angle in degrees, wrapping every 360°; pieces cannot be flipped. Coordinates (x, y) locate the upper-left corner of the rotated piece's bounding box and may be decimal or negative. The view fits the current arrangement automatically. Direct placement uses four fields: piece, x, y and rotation. An arrangement action replaces all three workspaces; waiting keeps the current placements.")}</p>
      <p>{tr("정확히 맞대려면 x·y·rotation 대신 edge·vertex·to_piece·to_edge·to_vertex를 지정할 수 있습니다. 기준 조각은 같은 색의 전체 배치 목록에서 앞에 있어야 합니다. 보관함의 변 e와 꼭짓점 v 번호는 0부터 시작하며, e_i는 v_i에서 다음 꼭짓점으로 이어집니다. 두 변이 반대 방향이 되도록 회전한 뒤 지정한 꼭짓점을 겹칩니다. 꼭짓점은 선택한 변의 끝점이 아니어도 됩니다. 이 기능은 조각을 이동·회전할 뿐 정답을 찾거나 선택을 고쳐주지 않습니다.", "For optional exact alignment, replace x, y and rotation with edge, vertex, to_piece, to_edge and to_vertex. The target piece must appear earlier in the same color's full replacement list. Tray edge e and vertex v labels start at zero; e_i runs from v_i to the next vertex. The source edge is rotated opposite the target edge, then the chosen vertices are matched. Those vertices need not be edge endpoints. This only moves and rotates pieces; it does not search for solutions or correct choices.")}</p>
    </details>
    {state.symSetup?.priority.length > 0 && <p className="sym-priority">{tr("제출은 기록된 응답 시간순으로 판정합니다. 시간이 같으면 추첨 우선순위", "Submissions follow recorded response times. Drawn priority for equal times")} · {state.symSetup.priority.join(" → ")}</p>}
  </div>;
}

export function SymmetryInformation({state, replay}) {
  const [tab, setTab] = useState("attempts");
  const {owner} = symmetryBoardFor(state, replay.match.players, replay.selected, "blue", replay.view);
  const attempts = state.symAttempts ?? [], finishes = state.symFinishes ?? [];
  const operations = (state.symOperations ?? []).filter((entry) => (!owner || entry.player === owner) && (replay.view === "operator" || entry.player === replay.view));
  return <aside className="caption sym-information" aria-label={tr("대칭 퍼즐 제출과 기록", "Symmetrical Puzzle submissions and records")}>
    <TabList role="tablist" aria-label={tr("대칭 퍼즐 정보 종류", "Symmetrical Puzzle information categories")} value={tab} onChange={setTab} size="sm" hasDivider>
      <Tab id="sym-attempts" value="attempts" label={tr("버저·판정", "Attempts")} panelId="sym-records-panel" />
      <Tab id="sym-assemblies" value="assemblies" label={tr("배치 기록", "Assemblies")} panelId="sym-records-panel" />
      <Tab id="sym-finishes" value="finishes" label={tr("완성 순위", "Finish order")} panelId="sym-records-panel" />
    </TabList>
    <div id="sym-records-panel" role="tabpanel" aria-labelledby={`sym-${tab}`}>
      {tab === "attempts" ? attempts.length ? <ol className="sym-history">{[...attempts].reverse().map((attempt) => <li key={attempt.step} data-correct={attempt.correct}><button type="button" onClick={() => replay.seek(attempt.step)}><small>{windowText(attempt.window)} · {tr(`${attempt.attempt}번째 제출`, `Attempt ${attempt.attempt}`)}</small><strong>{symmetryEventText("sym_verdict", attempt)}</strong></button></li>)}</ol> : <p className="muted">{tr("아직 버저 판정이 없어요.", "No buzzer verdicts yet.")}</p> : tab === "assemblies" ? <>
        {owner && <h3>{tr(`${owner}의 배치 기록`, `${owner}’s assembly history`)}</h3>}
        {operations.length ? <ol className="sym-history">{[...operations].reverse().map((entry) => <li key={entry.step}><button type="button" onClick={() => replay.seek(entry.step)}><small>{windowText(entry.window)}</small><strong>{symmetryEventText("sym_board", entry)}</strong></button></li>)}</ol> : <p className="muted">{tr("이 시점에 볼 수 있는 비공개 배치 기록이 없어요.", "No private assembly history is visible at this point.")}</p>}
      </> : <>
        {state.result && <Table caption={tr("최종 순위", "Final standings")} headers={tr(["순위", "참가자", "완성 색", "결과"], ["Rank", "Player", "Valid colors", "Result"])} rows={state.result.ranking.map((player, index) => [index + 1, player, `${state.result.scores?.[player] ?? "–"} / 3`, state.result.eliminated.includes(player) ? tr("탈락", "Eliminated") : tr("생존", "Safe")])} />}
        {finishes.length ? <ol className="sym-history">{finishes.map((finish) => <li key={finish.step} data-correct="true"><button type="button" onClick={() => replay.seek(finish.step)}><strong>{symmetryEventText("sym_finish", finish)}</strong><span>{windowText(finish.window)}</span></button></li>)}</ol> : <p className="muted">{tr("아직 세 색을 모두 완성한 참가자가 없어요.", "No player has finished all three colors yet.")}</p>}
        {state.symRevealed && <button type="button" className="sym-reveal-link" onClick={() => replay.seek(state.symRevealStep)}>{tr("경기 종료 후 작업판 공개로 이동", "Jump to the final assembly reveal")}</button>}
      </>}
    </div>
  </aside>;
}
