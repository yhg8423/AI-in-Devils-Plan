import React, {useState} from "react";
import {Tab, TabList} from "@astryxdesign/core/TabList";
import {en, tr} from "./locale.js";
import {Table} from "./records.jsx";
import {rulesSummary} from "./rule-summaries.js";
import "./wall-go.css";

const cellText = (cell) => cell ? `(${cell.join(", ")})` : "–";
const kindText = (kind) => kind === "square" ? tr("사각", "Square") : tr("원형", "Round");
const wallColors = [
  {fill: "#ff765e", name: tr("빨강", "Red")},
  {fill: "#55b9ff", name: tr("파랑", "Blue")},
  {fill: "#ffe066", name: tr("노랑", "Yellow")},
];
const pieceText = (id) => {
  const [, kind, number] = (id ?? "").split(":");
  return ["square", "round"].includes(kind) ? `${kindText(kind)} ${number}` : id ?? "";
};
const gameText = (game) => tr(`${game.round}라운드${game.replay ? ` · 재경기 ${game.replay}` : ""}`, `Round ${game.round}${game.replay ? ` · Replay ${game.replay}` : ""}`);
const edgeKey = (edge) => edge.map((cell) => cell.join(",")).sort().join("|");

export function applyWallEvent(state, type, data, event = {}) {
  if (!type.startsWith("wall_")) return;
  switch (type) {
    case "wall_setup":
      state.wallGame = {...data, pieces: Object.fromEntries(Object.entries(data.pieces).map(([id, piece]) => [id, {...piece}])), walls: [...data.walls], breakers: {...data.breakers}};
      state.wallTurn = null;
      state.wallLastMove = null;
      state.wallEnd = null;
      state.wallReplay = null;
      break;
    case "wall_place":
      if (state.wallGame?.pieces[data.piece]) state.wallGame.pieces[data.piece].position = data.position;
      state.wallLastMove = {...data, placement: true, step: event.step};
      break;
    case "wall_turn": state.wallTurn = data; state.wallTimeout = null; break;
    case "wall_timeout": state.wallTimeout = data; break;
    case "wall_advance": state.wallSafe = data.survivor; break;
    case "wall_move": {
      const game = state.wallGame;
      if (!game) break;
      if (game.pieces[data.piece]) game.pieces[data.piece].position = data.to;
      game.walls = game.walls.filter((wall) => !data.broken || edgeKey(wall) !== edgeKey(data.broken));
      game.walls.push(data.wall);
      game.breakers = {...data.breakers};
      game.scores = data.scores ?? game.scores;
      game.largest = data.largest ?? game.largest;
      state.wallLastMove = {...data, timed_out: state.wallTimeout?.player === data.player, step: event.step};
      break;
    }
    case "wall_pass": state.wallLastMove = {...data, pass: true, step: event.step}; break;
    case "wall_end":
      state.wallEnd = data;
      state.wallResults ??= [];
      state.wallResults.push({...data, step: event.step});
      state.wallTurn = null;
      break;
    case "wall_replay": state.wallReplay = data; state.wallGame = null; state.wallEnd = null; state.wallTurn = null; state.wallLastMove = null; break;
  }
}

export function wallEventText(type, data) {
  switch (type) {
    case "wall_setup": return `${gameText(data)} · ${tr("순서", "Order")} ${data.order.join(" → ")}`;
    case "wall_place": return `${data.player} · ${pieceText(data.piece)} → ${cellText(data.position)}`;
    case "wall_turn": return tr(`${data.turn}턴 · ${data.player}`, `Turn ${data.turn} · ${data.player}`);
    case "wall_timeout": return tr(`${data.player} · ${data.seconds}초 초과 · 임의의 벽 설치`, `${data.player} · ${data.seconds}-second limit exceeded · Random wall`);
    case "wall_advance": return tr(`${data.survivor} 생존 확정 · ${data.order.join(" → ")} 순서로 2라운드`, `${data.survivor} secures survival · Round 2 order: ${data.order.join(" → ")}`);
    case "wall_move": return `${data.player} · ${pieceText(data.piece)} ${cellText(data.from)} → ${cellText(data.to)} · ${data.broken ? tr("벽 부수기 · ", "Break wall · ") : ""}${tr("벽 설치", "Build wall")} ${data.wall.map(cellText).join(" ↔ ")}`;
    case "wall_pass": return `${data.player} · ${data.reason === "isolated" ? tr("단독 영역 확정 · 자동 패스", "Isolated territory · Automatic pass") : tr("이동 불가 · 자동 패스", "No legal move · Automatic pass")}`;
    case "wall_end": return `${gameText(data)} · ${Object.entries(data.scores).map(([name, score]) => tr(`${name} ${score}칸`, `${name} ${score} squares`)).join(" · ")}`;
    case "wall_replay": return tr(`완전 동률 · ${data.players.join(" · ")}만 순서를 바꾸어 재경기`, `Complete tie · ${data.players.join(" · ")} replay in reversed order`);
  }
}

export function wallActionText(phase, action) {
  let move;
  try { move = JSON.parse(action); } catch { return action; }
  if (phase === "wall_place") return `${pieceText(move.piece)} → ${cellText(move.position ?? move.cell)}`;
  if (phase === "wall_move") return `${pieceText(move.piece)} · ${(move.path ?? []).map(cellText).join(" → ")} · ${tr("벽 설치", "Build wall")}`;
  return action;
}

const side = 40, left = 70, top = 56;
const point = ([row, col]) => [left + (col - .5) * side, top + (row - .5) * side];
function Wall({edge, broken, recent}) {
  const [[r1, c1], [r2, c2]] = edge;
  const line = r1 === r2 ? {x1: left + Math.min(c1, c2) * side, x2: left + Math.min(c1, c2) * side, y1: top + (r1 - 1) * side, y2: top + r1 * side} :
    {x1: left + (c1 - 1) * side, x2: left + c1 * side, y1: top + Math.min(r1, r2) * side, y2: top + Math.min(r1, r2) * side};
  return <line {...line} className={`wall-segment${broken ? " broken-wall" : ""}${recent ? " recent-wall" : ""}`} data-edge={edgeKey(edge)} />;
}

export function WallGoScene({state, players, selected, onChoose}) {
  const game = state.wallGame;
  const colors = Object.fromEntries((players ?? game?.players ?? []).map((player, index) => [player, wallColors[index]]));
  const color = (player) => colors[player] ?? {fill: "#b8c4d4", name: ""};
  const move = state.wallLastMove;
  const territories = state.wallEnd?.territories ?? [];
  const path = move?.path && move.from ? [move.from, ...move.path] : [];
  const pieces = Object.entries(game?.pieces ?? {});
  return <section className="wall-arena pixel-frame" aria-label={tr("벽바둑 2 게임판", "Wall Go II board")}>
    <svg viewBox="0 0 420 390" role="img" aria-label={tr("7×7 벽바둑판 · 행과 열은 1부터 7", "7 by 7 Wall Go board · Rows and columns 1 through 7")}>
      <rect width="420" height="390" fill="#171c26" />
      <path d="M10 10H410V380H10Z" fill="none" stroke="#49525e" strokeWidth="6" />
      <path d="M22 358H398" stroke="#806b4a" strokeWidth="4" />
      <text x="210" y="22" className="wall-room-title">{tr("감옥 매치 · 벽바둑 2", "PRISON MATCH · WALL GO II")}</text>
      <rect x={left - 7} y={top - 7} width={7 * side + 14} height={7 * side + 14} fill="#927b54" stroke="#080e16" strokeWidth="4" />
      {Array.from({length: 49}, (_, index) => {
        const row = Math.floor(index / 7) + 1, col = index % 7 + 1;
        const owner = territories.find((region) => region.cells.some(([r, c]) => r === row && c === col))?.owner;
        return <rect key={index} x={left + (col - 1) * side} y={top + (row - 1) * side} width={side} height={side}
          fill={owner ? color(owner).fill : (row + col) % 2 ? "#655d4c" : "#756b56"} fillOpacity={owner ? .7 : 1} stroke="#a18b663f" data-cell={`${row},${col}`} data-owner={owner ?? undefined} />;
      })}
      {Array.from({length: 7}, (_, index) => <g key={index} className="wall-coordinates">
        <text x={left + (index + .5) * side} y={top - 10}>{index + 1}</text>
        <text x={left - 20} y={top + (index + .5) * side + 4}>{index + 1}</text>
      </g>)}
      {path.length > 1 && <polyline points={path.map((cell) => point(cell).join(",")).join(" ")} className="wall-move-path" />}
      {(game?.walls ?? []).map((wall) => <Wall key={edgeKey(wall)} edge={wall} recent={move?.wall && edgeKey(move.wall) === edgeKey(wall)} />)}
      {move?.broken && <Wall edge={move.broken} broken />}
      <rect x={left} y={top} width={7 * side} height={7 * side} fill="none" stroke="#d2b580" strokeWidth="5" />
      {pieces.filter(([, piece]) => piece.position).map(([id, piece]) => {
        const [x, y] = point(piece.position);
        const label = `${piece.player} · ${kindText(piece.kind)} · ${cellText(piece.position)}`;
        return <g key={id} data-piece={id} data-player={piece.player} data-kind={piece.kind} className="wall-piece"
          role="button" tabIndex="0" aria-label={label} aria-pressed={selected === piece.player}
          onClick={() => onChoose(piece.player)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onChoose(piece.player); } }}>
          <title>{label}</title>
          {piece.kind === "square" ? <rect x={x - 14} y={y - 14} width="28" height="28" fill={color(piece.player).fill} stroke={selected === piece.player ? "#fff7d1" : "#18212c"} strokeWidth="3" /> :
            <circle cx={x} cy={y} r="15" fill={color(piece.player).fill} stroke={selected === piece.player ? "#fff7d1" : "#18212c"} strokeWidth="3" />}
          <text x={x} y={y + 3} className="wall-piece-label">{piece.player}</text>
        </g>;
      })}
      <text x="210" y="351" className="wall-room-title">{game ? gameText(game) : tr("말 배치 준비", "Preparing the board")}</text>
      <text x="210" y="371" className="wall-bottom-label">{tr("■ 사각 · ● 원형 · 붉은 점선은 부순 벽", "■ Square · ● Round · Red dashes mark a broken wall")}</text>
    </svg>
    {game && <div className="wall-player-legend">{game.players.map((player) => <button key={player} type="button" aria-pressed={selected === player} onClick={() => onChoose(player)} style={{"--wall-player": color(player).fill}}>
      <i aria-hidden="true" />{player} · {color(player).name}{state.wallTurn?.player === player && <strong>{tr("진행 중", "Acting")}</strong>}
    </button>)}</div>}
  </section>;
}

export function WallGoStage({state, players}) {
  const game = state.wallGame;
  const end = state.wallEnd;
  const pending = Object.values(game?.pieces ?? {}).filter((piece) => !piece.position).length;
  const rules = state.feed.findLast((event) => event.msg_type === "rules");
  const result = state.result;
  return <div className="wall-stage">
    <h2>{tr("벽바둑 2", "Wall Go II")}</h2>
    {!game ? state.wallReplay ? <div className="wall-rules"><h3>{tr("동률 재경기 준비", "Preparing a tied-player replay")}</h3><p>{wallEventText("wall_replay", state.wallReplay)}</p><p>{state.wallReplay.order.join(" → ")}</p></div> : <div className="wall-rules"><h3>{tr("게임 규칙", "Game rules")}</h3><p>{en ? rulesSummary("벽바둑 2", rules?.content ?? "") : rules?.content ?? tr("게임 시작을 기다립니다.", "Waiting for the match to begin.")}</p></div> : <>
      <p className="wall-phase">{result ? tr("최종 결과", "Final results") : state.wallReplay ? tr("동률 재경기 준비", "Preparing a tied-player replay") : end ? tr("영역 판정 완료", "Territory scoring complete") : pending ? tr(`말 배치 · ${pending}개 남음`, `Placement · ${pending} remaining`) : tr(`${state.wallTurn?.turn ?? 0}턴 · ${state.wallTurn?.player ?? "–"}`, `Turn ${state.wallTurn?.turn ?? 0} · ${state.wallTurn?.player ?? "–"}`)}</p>
      <p className="muted">{gameText(game)} · {tr("진행 순서", "Turn order")}: {game.order.join(" → ")}</p>
      {result ? <Table caption={tr("최종 순위", "Final standings")} headers={tr(["순위", "참가자", "결과", "피스"], ["Rank", "Player", "Result", "Pieces"])} rows={result.ranking.map((player, index) => [index + 1, player,
        result.eliminated.includes(player) ? tr("탈락", "Eliminated") : tr("생존", "Survived"), result.pieces?.[player] ?? "–"])} /> :
        <Table caption={tr("참가자 현황", "Player status")} headers={tr(["참가자", "영역", "최대 단일 영역", "벽 부수기"], ["Player", "Territory", "Largest region", "Wall breaker"])}
          rows={players.map((player) => [player, end?.scores[player] ?? game.scores?.[player] ?? "–", end?.largest[player] ?? game.largest?.[player] ?? "–", player in game.breakers ? game.breakers[player] ? tr("사용 가능", "Available") : tr("없음", "None") : tr("생존 확정", "Safe")])} />}
      {end && <p className="wall-verdict">{end.winner ? tr(`영역 1위 · ${end.winner}`, `Territory winner · ${end.winner}`) : tr("동률은 순서를 바꾸어 재경기합니다.", "Tied players replay in reversed order.")}</p>}
      {end?.reason === "stalemate" && <p className="wall-verdict">{tr("교착 종료 · 공동 영역은 각 말이 선 칸만 1점씩 인정", "Stalemate · Only occupied squares in shared territory score one point per counter")}</p>}
      {state.wallSafe && !result && <p className="wall-verdict">{tr(`${state.wallSafe} 생존 확정`, `${state.wallSafe} secures survival`)}</p>}
      {state.wallLastMove && <p className="wall-last-action">{wallEventText(state.wallLastMove.pass ? "wall_pass" : state.wallLastMove.placement ? "wall_place" : "wall_move", state.wallLastMove)}{state.wallLastMove.timed_out && tr(" · 시간 초과로 임의의 벽 설치", " · Random wall after timeout")}</p>}
      <p className="muted">{tr("말 이동 → 도착칸에 벽 설치 · 대화 없이 진행", "Move a counter → Build an adjacent wall · No discussion")}</p>
      {game.round === 2 && <p className="muted">{tr("원형 말은 대각선 두 칸씩 같은 편 · 벽 부수기 없음", "Diagonal round-counter pairs belong to the same player · No wall breakers")}</p>}
    </>}
  </div>;
}

export function WallGoInformation({state, replay}) {
  const [tab, setTab] = useState("rounds");
  const results = state.wallResults ?? [];
  const moves = state.feed.filter((event) => ["wall_place", "wall_move", "wall_pass", "wall_replay", "wall_timeout"].includes(event.msg_type));
  return <aside className="caption wall-information" aria-label={tr("벽바둑 결과와 기록", "Wall Go results and records")}>
    <TabList role="tablist" aria-label={tr("벽바둑 정보 종류", "Wall Go information categories")} value={tab} onChange={setTab} size="sm" hasDivider>
      <Tab id="wall-rounds" value="rounds" label={tr("라운드 점수", "Round scores")} panelId="wall-records-panel" />
      <Tab id="wall-moves" value="moves" label={tr("이동·벽 기록", "Moves and walls")} panelId="wall-records-panel" />
    </TabList>
    <div id="wall-records-panel" role="tabpanel" aria-labelledby={`wall-${tab}`}>
      {tab === "rounds" ? results.length ? results.map((result) => <section key={result.game} className="wall-round-result">
        <h3><button type="button" onClick={() => replay.seek(result.step)}>{gameText(result)}</button></h3>
        <Table caption={tr("영역 판정", "Territory scoring")} headers={tr(["참가자", "합계", "최대 단일 영역"], ["Player", "Total", "Largest region"])} rows={result.players.map((name) => [name, result.scores[name], result.largest[name]])} />
        <p>{result.ranking.map((group) => group.join(" = ")).join(" > ")}</p>
        {result.reason === "stalemate" && <p>{tr("교착 판정 · 공동 영역은 말이 선 칸만 계산", "Stalemate scoring · Only occupied squares count in shared territory")}</p>}
      </section>) : <p className="muted">{tr("아직 종료된 라운드가 없어요.", "No rounds have finished yet.")}</p> : moves.length ? <ol className="wall-move-log">{moves.map((event) => <li key={event.step}><button type="button" onClick={() => replay.seek(event.step)}>{event.step} · {event.text}</button></li>).reverse()}</ol> : <p className="muted">{tr("아직 이동 기록이 없어요.", "No moves have been recorded yet.")}</p>}
    </div>
  </aside>;
}
