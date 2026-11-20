import React, {useState} from "react";
import {Tab, TabList} from "@astryxdesign/core/TabList";
import {tr} from "./locale.js";
import {Table} from "./records.jsx";
import {Sprite} from "./scene.jsx";
import "./exile-match.css";

const axisText = (axis) => axis === "row" ? tr("행", "Row") : tr("열", "Column");
const placementText = (placement) => `${axisText(placement.axis)} ${placement.slot}${placement.reverse ? tr(" · 역순", " · Reversed") : ""}${placement.flip ? tr(" · 상하 반전", " · Flipped") : ""}`;
const cloneBoard = (board) => ({...board, placements: (board.placements ?? []).map((placement) => ({...placement})), joints: (board.joints ?? []).map((joint) => ({...joint}))});

export function applyExileEvent(state, type, data, event = {}) {
  switch (type) {
    case "exile_setup":
      state.exileSetup = {...data, pieces: data.pieces.map((piece) => ({...piece, sides: [...piece.sides], depths: [...piece.depths]}))};
      state.exileBoards = {};
      state.exileAttempts = [];
      state.exileOperations = [];
      state.exileTurn = null;
      state.exileRevealed = false;
      break;
    case "exile_turn": state.exileTurn = data; break;
    case "exile_board": {
      const board = cloneBoard(data);
      state.exileBoards ??= {};
      state.exileBoards[data.player] = board;
      state.exileOperations ??= [];
      state.exileOperations.push({...board, step: event.step});
      break;
    }
    case "exile_attempt":
      state.exileAttempts ??= [];
      state.exileAttempts.push({...data, step: event.step});
      break;
    case "exile_reveal":
      state.exileBoards = Object.fromEntries(Object.entries(data.boards).map(([player, board]) => [player, cloneBoard(board)]));
      state.exileRevealed = true;
      break;
  }
}

export function exileEventText(type, data) {
  switch (type) {
    case "exile_setup": return tr("피스 8개 · 가로 4줄 · 세로 4줄", "Eight Pieces · Four rows · Four columns");
    case "exile_turn": return tr(`${data.turn}턴 · ${data.active.join(" · ")} 조립 중`, `Turn ${data.turn} · ${data.active.join(" · ")} assembling`);
    case "exile_board": return tr(`${data.player} · ${data.placed} / 8개 배치 · 맞지 않는 교차점 ${data.errors}개`, `${data.player} · ${data.placed} of 8 Pieces placed · ${data.errors} incompatible crossings`);
    case "exile_attempt": return `${data.player} · ${data.correct ? data.place ? tr(`완성 · ${data.place}위${data.place <= 3 ? " 생존" : ""}`, `Complete · Rank ${data.place}${data.place <= 3 ? ", safe" : ""}`) : tr("퍼즐 완성", "Puzzle complete") : tr("오답 · 다시 조립", "Incorrect · Continue assembling")}`;
    case "exile_reveal": return tr("조립판 공개", "Assemblies revealed");
  }
}

export function exileActionText(phase, action) {
  let move;
  try { move = JSON.parse(action); } catch { return action; }
  if (!move || typeof move !== "object") return action;
  switch (move.type) {
    case "place": return `${move.piece} → ${placementText(move)}`;
    case "remove": return tr(`${move.piece} 회수`, `Return ${move.piece} to the tray`);
    case "submit": return tr("버저 · 완성 제출", "Buzzer · Submit assembly");
    case "pass": return tr("대기", "Wait");
    default: return action;
  }
}

export function exileBoardFor(state, players, selected, perspective = state.exilePerspective ?? "operator") {
  const isPlayer = players.includes(perspective);
  const owner = perspective === "operator" || state.exileRevealed ?
    (players.includes(selected) ? selected : isPlayer ? perspective : players[0]) : isPlayer ? perspective : null;
  return {owner, board: owner ? state.exileBoards?.[owner] ?? null : null};
}

function boardPicker(state, players, selected, onChoose, perspective = state.exilePerspective ?? "operator") {
  const {owner} = exileBoardFor(state, players, selected, perspective);
  return <div className="exile-player-picker" role="group" aria-label={tr("조립판 참가자", "Assembly player")}>
    {players.map((player) => <button key={player} type="button" aria-pressed={owner === player}
      disabled={perspective !== "operator" && !state.exileRevealed && perspective !== player}
      onClick={() => onChoose(player)}>{player}</button>)}
  </div>;
}

function orientedPiece(piece, placement) {
  const order = placement.reverse ? [3, 2, 1, 0] : [0, 1, 2, 3];
  return {...piece, sides: order.map((index) => placement.flip ? 1 - piece.sides[index] : piece.sides[index]), depths: order.map((index) => piece.depths[index])};
}

function PieceDiagram({piece, placement}) {
  const shape = placement ? orientedPiece(piece, placement) : piece;
  return <svg className="exile-piece-diagram" viewBox="0 0 100 75" role="img" aria-label={`${piece.id} · ${shape.sides.map((side, index) => `${side === 0 ? tr("위", "Top") : tr("아래", "Bottom")} ${shape.depths[index]}`).join(" · ")}`} shapeRendering="crispEdges">
    <rect x="0" y="0" width="100" height="75" fill="#d6ae63" />
    <path d="M0 75V0H100" fill="none" stroke="#f7d995" strokeWidth="3" />
    {shape.sides.map((side, index) => <rect key={index} x={15 + index * 20} y={side === 0 ? 0 : 75 * (1 - shape.depths[index] / 100)} width="10" height={75 * shape.depths[index] / 100} fill="#17212b" data-notch={index + 1} data-side={side} data-depth={shape.depths[index]} />)}
  </svg>;
}

const point = (x, y, z = 0) => [320 + (x - y) * 43, 188 + (x + y) * 24 - z];
const pointsText = (points) => points.map((point) => point.map((value) => value.toFixed(2)).join(",")).join(" ");
function slatPoints(piece, placement) {
  const shape = orientedPiece(piece, placement), high = 38, points = [[-.65, 0]];
  for (let index = 0; index < 4; index++) {
    if (shape.sides[index] === 1) points.push([index - .13, 0], [index - .13, high * shape.depths[index] / 100], [index + .13, high * shape.depths[index] / 100], [index + .13, 0]);
  }
  points.push([3.65, 0], [3.65, high]);
  for (let index = 3; index >= 0; index--) {
    if (shape.sides[index] === 0) points.push([index + .13, high], [index + .13, high * (1 - shape.depths[index] / 100)], [index - .13, high * (1 - shape.depths[index] / 100)], [index - .13, high]);
  }
  points.push([-.65, high]);
  return points.map(([along, z]) => placement.axis === "row" ? point(along, placement.slot - 1, z) : point(placement.slot - 1, along, z));
}

function Assembly({board, pieces, owner}) {
  const placements = board?.placements ?? [];
  const rows = new Set(placements.filter((item) => item.axis === "row").map((item) => item.slot));
  const columns = new Set(placements.filter((item) => item.axis === "col").map((item) => item.slot));
  return <g className="exile-assembly" data-assembly-owner={board ? owner : undefined}>
    <polygon points={pointsText([point(-1, -1, -8), point(4, -1, -8), point(4, 4, -8), point(-1, 4, -8)])} fill="#1d2026" stroke="#775f3f" strokeWidth="3" />
    {Array.from({length: 4}, (_, index) => <g key={index}>
      <path d={`M${point(-.65, index).join(" ")}L${point(3.65, index).join(" ")}M${point(index, -.65).join(" ")}L${point(index, 3.65).join(" ")}`} fill="none" stroke="#82704f" strokeDasharray="4 5" strokeWidth="2" />
      <text x={point(3.95, index)[0]} y={point(3.95, index)[1] + 3} className="exile-axis">R{index + 1}</text>
      <text x={point(index, 3.95)[0]} y={point(index, 3.95)[1] + 3} className="exile-axis">C{index + 1}</text>
    </g>)}
    {[...placements].sort((a, b) => a.slot - b.slot || a.axis.localeCompare(b.axis)).map((placement) => {
      const piece = pieces.find((piece) => piece.id === placement.piece);
      if (!piece) return null;
      const face = slatPoints(piece, placement);
      const labelAt = placement.axis === "row" ? point(-.9, placement.slot - 1, 42) : point(placement.slot - 1, -.9, 42);
      return <g key={placement.piece} className="exile-slat" data-piece={placement.piece} data-axis={placement.axis} data-slot={placement.slot}>
        <title>{placement.piece} · {placementText(placement)}</title>
        <polygon points={pointsText(face.map(([x, y]) => [x + 3, y + 4]))} fill="#70502f" />
        <polygon points={pointsText(face)} fill={placement.axis === "row" ? "#ddb466" : "#c99d53"} stroke="#f6d99b" strokeWidth="1.3" />
        <text x={labelAt[0]} y={labelAt[1]} className="exile-slat-label">{placement.piece}</text>
      </g>;
    })}
    {(board?.joints ?? []).filter((joint) => rows.has(joint.row) && columns.has(joint.col)).map((joint) => {
      const [x, y] = point(joint.col - 1, joint.row - 1, 20);
      return joint.ok ? <rect key={`${joint.row}-${joint.col}`} x={x - 2} y={y - 2} width="4" height="4" fill="#b7e2b1" data-joint="ok" /> :
        <path key={`${joint.row}-${joint.col}`} d={`M${x - 5} ${y - 5}l10 10m0-10l-10 10`} stroke="#ff8473" strokeWidth="3" data-joint="blocked" />;
    })}
  </g>;
}

export function ExileScene({state, players, selected, onChoose}) {
  const {owner, board} = exileBoardFor(state, players, selected);
  const view = state.exilePerspective ?? "operator";
  const completed = (state.exileAttempts ?? []).filter((attempt) => attempt.correct && attempt.place && attempt.place <= 3);
  const latest = state.exileAttempts?.at(-1);
  const positions = [[11.5, 29], [88.5, 29], [11.5, 76], [88.5, 76]];
  return <section className="exile-arena pixel-frame" aria-label={tr("유배지 피스 퍼즐 세트장", "Exile Piece Puzzle arena")}>
    <div className="exile-room">
      <svg viewBox="0 0 640 470" role="img" aria-label={tr("네 참가자의 발판과 피스 조립판", "Four player platforms and the Piece assembly")} shapeRendering="crispEdges">
        <rect width="640" height="470" fill="#151c24" />
        <path d="M12 12H628V458H12Z" fill="none" stroke="#48515b" strokeWidth="6" />
        <path d="M28 102H612V426H28Z" fill="#20252c" stroke="#333c46" strokeWidth="4" />
        <path d="M28 102L114 66H526L612 102M28 426L116 446H524L612 426" fill="none" stroke="#555047" strokeWidth="4" />
        {Array.from({length: 7}, (_, index) => <path key={index} d={`M${46 + index * 90} 106v316M30 ${138 + index * 43}H610`} stroke="#353a41" strokeWidth="1" />)}
        <path d="M282 60l18-13h40l18 13-18 13h-40z" fill="#7f3f3e" stroke="#c0755e" strokeWidth="3" />
        <path d="M315 46h10v29h-10z" fill="#15171d" />
        <text x="320" y="31" className="exile-room-title">{tr("유배지 · 피스 퍼즐", "EXILE · PIECE PUZZLE")}</text>
        {positions.map(([x, y], index) => <g key={index}>
          <rect x={640 * x / 100 - 43} y={470 * y / 100 + 25} width="86" height="49" fill="#11171d" stroke="#5c605e" strokeWidth="3" />
          <rect x={640 * x / 100 - 39} y={470 * y / 100 + 29} width="78" height="7" fill="#7a674a" />
          <path d={`M${640 * x / 100 - 32} ${470 * y / 100 + 43}h64`} stroke="#3a424b" strokeWidth="3" />
        </g>)}
        <Assembly board={board} pieces={state.exileSetup?.pieces ?? []} owner={owner} />
        {!board && <g className="exile-board-cover"><rect x="224" y="205" width="192" height="61" fill="#141d27" stroke="#6e6756" strokeWidth="2" />
          <text x="320" y="230">{owner ? tr("배치 기록 대기", "Awaiting assembly") : tr("비공개 조립 중", "PRIVATE ASSEMBLY")}</text>
          <text x="320" y="251">{tr("목표 · 4×4 교차 격자", "Target · 4×4 crossing grid")}</text></g>}
        <text x="320" y="435" className="exile-room-caption">{board ? tr(`${owner} 조립판 · ${board.placed} / 8개`, `${owner}’s assembly · ${board.placed} of 8 Pieces`) : tr("먼저 완성한 세 명이 생존합니다", "The first three to finish survive")}</text>
      </svg>
      <div className="exile-cast">
        {players.map((player, index) => {
          const finish = completed.find((attempt) => attempt.player === player);
          const out = state.result?.eliminated?.includes(player);
          const failed = latest?.player === player && !latest.correct && latest.turn === state.exileTurn?.turn;
          const [left, top] = positions[index] ?? [50, 50];
          const canChoose = view === "operator" || state.exileRevealed || view === player;
          return <button key={player} type="button" className="exile-player" style={{left: `${left}%`, top: `${top}%`}}
            data-status={out ? "eliminated" : finish ? "safe" : "assembling"} data-call={failed ? "incorrect" : undefined} aria-pressed={owner === player} disabled={!canChoose}
            aria-label={`${player} · ${out ? tr("탈락", "Eliminated") : finish ? tr(`${finish.place}위 생존`, `Rank ${finish.place}, safe`) : tr("조립 중", "Assembling")}`}
            onClick={() => onChoose(player)}>
            {(finish || failed || out) && <strong className="exile-player-call">{out ? tr("탈락", "OUT") : finish ? tr("완성!", "COMPLETE!") : tr("오답", "INCORRECT")}</strong>}
            <Sprite player={player} /><span>{player}{finish && <small>{tr(`${finish.place}위 생존`, `Rank ${finish.place} · Safe`)}</small>}</span>
          </button>;
        })}
      </div>
    </div>
    {boardPicker(state, players, selected, onChoose)}
  </section>;
}

export function ExileStage({state, players, selected, onChoose, perspective}) {
  const setup = state.exileSetup;
  const {owner, board} = exileBoardFor(state, players, selected, perspective);
  const completed = (state.exileAttempts ?? []).filter((attempt) => attempt.correct && attempt.place && attempt.place <= 3).sort((a, b) => a.place - b.place);
  const result = state.result;
  return <div className="exile-stage">
    <h2>{tr("피스 퍼즐", "Piece Puzzle")}</h2>
    {!setup ? <div className="exile-rules"><h3>{tr("게임 규칙", "Game rules")}</h3>
      <p>{tr("8개 피스를 가로 4줄·세로 4줄에 배치해 16개 교차점을 모두 맞추세요.", "Arrange eight Pieces in four rows and four columns so all sixteen crossings fit.")}</p>
      <p>{tr("방향과 홈 깊이를 확인하고, 완성하면 버저로 제출합니다. 먼저 완성한 세 명은 생존하고 마지막 한 명은 탈락합니다.", "Check notch directions and depths, then submit with the buzzer. The first three finishers survive; the last player is eliminated.")}</p>
    </div> : <>
      <p className="exile-phase">{result ? tr("최종 결과", "Final results") : tr(`${state.exileTurn?.turn ?? 0}턴 · 완성 ${completed.length} / 3명`, `Turn ${state.exileTurn?.turn ?? 0} · ${completed.length} of 3 survivors` )}</p>
      <Table caption={tr("완성 순위", "Completion order")} headers={tr(["참가자", "완성 턴", "상태"], ["Player", "Finish turn", "Status"])}
        rows={(result?.ranking ?? players).map((player) => {
          const finish = completed.find((attempt) => attempt.player === player);
          return [player, result?.finish_turns?.[player] ?? finish?.turn ?? "–", result?.eliminated?.includes(player) ? tr("탈락", "Eliminated") : finish ? tr(`${finish.place}위 생존`, `Rank ${finish.place} · Safe`) : tr("조립 중", "Assembling")];
        })} />
      {owner ? <section className="exile-own-board" aria-label={tr(`${owner} 조립 현황`, `${owner}’s assembly status`)}>
        <h3>{tr(`${owner} 조립판`, `${owner}’s assembly`)}</h3>
        <p>{board ? tr(`배치 ${board.placed} / 8개 · 맞물림 ${board.joints.filter((joint) => joint.ok).length} / 16곳`, `${board.placed} of 8 Pieces placed · ${board.joints.filter((joint) => joint.ok).length} of 16 crossings fit`) : tr("첫 배치 기록을 기다립니다.", "Waiting for the first assembly record.")}</p>
      </section> : <p className="muted exile-private-status">{tr("조립판은 각 참가자에게만 보입니다. 경기가 끝나면 모두 공개됩니다.", "Each assembly is visible only to its owner. All boards are revealed when the match ends.")}</p>}
      <div className="exile-piece-tray" aria-label={tr("8개 피스의 홈 모양", "Notch patterns of the eight Pieces")}>
        {setup.pieces.map((piece) => {
          const placed = board?.placements.find((item) => item.piece === piece.id);
          return <div key={piece.id} className="exile-piece-card" data-piece-card={piece.id} data-placed={Boolean(placed)}>
            <strong>{piece.id}</strong><PieceDiagram piece={piece} placement={placed} />
            <small>{placed ? placementText(placed) : board ? tr("미배치", "In tray") : tr("홈 모양", "Notches")}</small>
          </div>;
        })}
      </div>
      <p className="muted exile-instructions">{tr("행 R1–R4 · 열 C1–C4 · 역순은 홈 순서, 상하 반전은 홈 방향을 바꿉니다.", "Rows R1–R4 · Columns C1–C4 · Reverse changes notch order; flip changes notch sides.")}</p>
      <p className="muted exile-instructions">{tr("교차하는 홈은 서로 반대 방향이어야 하며, 두 깊이의 합이 100 이상이어야 합니다.", "Crossing notches must face opposite sides and their depths must sum to at least 100.")}</p>
    </>}
  </div>;
}

export function ExileInformation({state, replay}) {
  const [tab, setTab] = useState("results");
  const players = replay.match.players;
  const perspective = state.exilePerspective ?? replay.view ?? "operator";
  const allowed = (player) => perspective === "operator" || state.exileRevealed || perspective === player;
  const {owner} = exileBoardFor(state, players, replay.selected, perspective);
  const attempts = state.exileAttempts ?? [];
  const actions = (state.feed ?? []).filter((event) => event.msg_type === "action" && event.data?.phase?.startsWith("exile") && allowed(event.agent_name) && (!owner || owner === event.agent_name));
  const operations = actions.length ? actions.map((event) => ({step: event.step, text: `${event.agent_name} · ${exileActionText(event.data.phase, event.data.action)}`})) :
    (state.exileOperations ?? []).filter((board) => allowed(board.player) && (!owner || owner === board.player)).map((board) => ({step: board.step, text: exileEventText("exile_board", board)}));
  return <aside className="caption exile-information" aria-label={tr("피스 퍼즐 결과와 기록", "Piece Puzzle results and records")}>
    <TabList role="tablist" aria-label={tr("피스 퍼즐 정보 종류", "Piece Puzzle information categories")} value={tab} onChange={setTab} size="sm" hasDivider>
      <Tab id="exile-results" value="results" label={tr("제출·결과", "Submissions and results")} panelId="exile-records-panel" />
      <Tab id="exile-operations" value="operations" label={tr("조립 기록", "Assembly history")} panelId="exile-records-panel" />
    </TabList>
    {state.exileSetup?.turn_order && <p className="exile-tie-order">{tr("동시 완성 우선순위", "Same-turn priority")} · {state.exileSetup.turn_order.join(" → ")}</p>}
    <div id="exile-records-panel" role="tabpanel" aria-labelledby={`exile-${tab}`}>
      {tab === "results" ? <>
        {state.result?.ranking && <Table caption={tr("최종 순위", "Final standings")} headers={tr(["순위", "참가자", "완성 턴", "결과"], ["Rank", "Player", "Finish turn", "Result"])}
          rows={state.result.ranking.map((player, index) => [index + 1, player, state.result.finish_turns?.[player] ?? "–", state.result.eliminated.includes(player) ? tr("탈락", "Eliminated") : tr("생존", "Survived")])} />}
        {attempts.length ? <ol className="exile-history">{[...attempts].reverse().map((attempt) => <li key={attempt.step} data-correct={attempt.correct}>
          <button type="button" onClick={() => replay.seek(attempt.step)}><small>{tr(`${attempt.turn}턴`, `Turn ${attempt.turn}`)}</small>{exileEventText("exile_attempt", attempt)}</button>
        </li>)}</ol> : <p className="muted">{tr("아직 버저 제출 기록이 없어요.", "No buzzer submissions yet.")}</p>}
      </> : <>
        {owner && <h3 className="exile-history-owner">{tr(`${owner} 조립 기록`, `${owner}’s assembly history`)}</h3>}
        {operations.length ? <ol className="exile-history">{[...operations].reverse().map((operation) => <li key={operation.step}><button type="button" onClick={() => replay.seek(operation.step)}>{operation.step} · {operation.text}</button></li>)}</ol> :
          <p className="muted">{tr("볼 수 있는 조립 기록이 없어요.", "No assembly operations are visible.")}</p>}
      </>}
    </div>
  </aside>;
}
