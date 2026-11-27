import React, {useState} from "react";
import {Tab, TabList} from "@astryxdesign/core/TabList";
import {en, tr} from "./locale.js";
import {Table} from "./records.jsx";
import "./equation-tower.css";

const cloneStacks = (stacks = []) => stacks.map((stack) => [...stack]);
const roundText = (round) => tr(`${round}라운드`, `Round ${round}`);
const movesText = (moves) => tr(`${moves}회`, `${moves} moves`);
const colors = ["#ff8b78", "#70c6ef", "#f4d77c"];
const blockText = (block, id) => {
  if (!block) return String(id);
  if (block.label != null) return String(block.label);
  const operator = ({"*": "×", "/": "÷", mul: "×", div: "÷", add: "+", sub: "−"})[block.operator] ?? block.operator ?? "";
  return `${operator}${block.value}`;
};
const changeText = (change) => Number(change) > 0 ? `+${change}` : String(change ?? 0);
const verdictReason = (reason) => ({
  incorrect: tr("목표 숫자·층수 미완성", "Target number or height not met"),
  invalid_plan: tr("올바르지 않은 이동 계획", "Invalid move plan"),
  timeout: tr("제한 시간 초과", "Time limit exceeded"),
  time_limit: tr("제한 시간 초과", "Time limit exceeded"),
  invalid_move: tr("허용되지 않은 이동", "Invalid move"),
  move_limit: tr("이동 횟수 초과", "Move limit exceeded"),
  moves_exceeded: tr("이동 횟수 초과", "Move limit exceeded"),
  wrong_height: tr("목표 층수 불일치", "Target height not met"),
  wrong_target: tr("목표 숫자 불일치", "Target number not met"),
  invalid_top: tr("맨 위 블록은 연산자 없는 숫자여야 합니다", "The top block must be a plain number"),
})[reason];

export function applyTowerEvent(state, type, data, event = {}) {
  if (!type.startsWith("tower_")) return;
  const record = () => ({...data, stacks: data.stacks ? cloneStacks(data.stacks) : undefined, scores: data.scores ? {...data.scores} : undefined, step: event.step});
  switch (type) {
    case "tower_setup":
      state.towerGame = {...data, players: [...data.players], order: [...(data.order ?? data.players)], stacks: cloneStacks(data.stacks),
        blocks: Object.fromEntries(Object.entries(data.blocks ?? {}).map(([id, block]) => [id, {...block}])), scores: Object.fromEntries(data.players.map((player) => [player, 0]))};
      state.towerResults = [];
      state.towerWindow = state.towerBid = state.towerChallenge = state.towerLastMove = state.towerVerdict = state.towerSkip = state.towerAdvance = null;
      state.towerSafe = [];
      break;
    case "tower_problem":
      if (!state.towerGame) break;
      Object.assign(state.towerGame, data, {stacks: cloneStacks(data.stacks), scores: {...state.towerGame.scores, ...data.scores}});
      state.towerWindow = state.towerBid = state.towerChallenge = state.towerLastMove = state.towerVerdict = state.towerSkip = state.towerAdvance = null;
      break;
    case "tower_bid_window": state.towerWindow = {...data}; state.towerChallenge = null; break;
    case "tower_bid": state.towerBid = {...data}; break;
    case "tower_challenge": state.towerChallenge = {...data}; state.towerWindow = null; state.towerVerdict = null; break;
    case "tower_move":
      if (state.towerGame && data.stacks) state.towerGame.stacks = cloneStacks(data.stacks);
      state.towerLastMove = record();
      break;
    case "tower_verdict":
      if (state.towerGame) {
        if (data.stacks) state.towerGame.stacks = cloneStacks(data.stacks);
        if (data.scores) state.towerGame.scores = {...state.towerGame.scores, ...data.scores};
      }
      state.towerVerdict = record();
      state.towerResults ??= [];
      state.towerResults.push(state.towerVerdict);
      state.towerChallenge = state.towerWindow = null;
      break;
    case "tower_skip": state.towerSkip = {...data}; state.towerWindow = state.towerChallenge = null; break;
    case "tower_advance":
      state.towerAdvance = {...data};
      state.towerSafe = [...new Set([...(state.towerSafe ?? []), ...(Array.isArray(data.safe) ? data.safe : data.safe ? [data.safe] : data.winner ? [data.winner] : [])])];
      state.towerWindow = state.towerChallenge = null;
      if (state.towerGame && data.reset_scores) state.towerGame.scores = {...state.towerGame.scores, ...Object.fromEntries((data.tied ?? []).map((player) => [player, 0]))};
      break;
  }
}

export function towerEventText(type, data) {
  switch (type) {
    case "tower_setup": return tr(`탑 ${data.stacks.length}개 · 블록 ${Object.keys(data.blocks).length}개 · 목표 ${data.goal}점`, `${data.stacks.length} towers · ${Object.keys(data.blocks).length} blocks · Goal: ${data.goal} points`);
    case "tower_problem": return `${roundText(data.round)} · ${tr("목표", "Target")} ${data.target} · ${tr(`${data.height}층`, `${data.height} blocks high`)}`;
    case "tower_bid_window": return tr(`${data.stage === "counter" ? "더 적은 이동으로 재입찰" : "최초 입찰 버저"} · ${data.seconds}초`, `${data.stage === "counter" ? "Counterbid with fewer moves" : "Opening bid buzzer"} · ${data.seconds}s`);
    case "tower_bid": return `${data.player} · ${tr("입찰", "Bid")} ${movesText(data.moves)}${data.first ? tr(" · 첫 버저", " · First buzzer") : ""}`;
    case "tower_challenge": return `${data.player} · ${tr("도전", "Challenge")} ${movesText(data.bid)} · ${tr("승점", "Stake")} ${data.stake} · ${data.seconds}s`;
    case "tower_move": return tr(`${data.player} · ${data.index}번째 이동 · 탑 ${data.from} → ${data.to} · 위에서 ${data.count}개${data.flip ? " · 뒤집기" : ""}`, `${data.player} · Move ${data.index} · Tower ${data.from} → ${data.to} · Top ${data.count} block${data.count === 1 ? "" : "s"}${data.flip ? " · Flip" : ""}`);
    case "tower_verdict": return `${roundText(data.round)} · ${data.player} · ${data.success ? tr("성공", "Success") : tr("실패", "Failed")} · ${changeText(data.change)}${tr("점", " points")}${verdictReason(data.reason) ? ` · ${verdictReason(data.reason)}` : ""}`;
    case "tower_skip": return `${roundText(data.round)} · ${tr("입찰 없이 다음 문제로", "No bid · Next problem")}`;
    case "tower_advance": return data.winner ? data.tied?.length ? tr(`${data.winner} 생존 확정 · 최하위 동점자 재대결`, `${data.winner} secures survival · Last-place tie continues`) : tr(`${data.winner} 1위 · 최하위 탈락 확정`, `${data.winner} wins · Last place is eliminated`) : tr("동점자 재대결 · 승점 초기화", "Tied players continue · Scores reset");
  }
}

export function towerActionText(phase, action) {
  let data;
  try { data = typeof action === "string" ? JSON.parse(action) : action; } catch { return action; }
  if (!data || typeof data !== "object") return action;
  if (["tower_bid", "tower_opening_bid", "tower_counter_bid"].includes(phase)) return data.moves == null ? tr("입찰하지 않음", "Pass") : `${tr("입찰", "Bid")} ${movesText(data.moves)}`;
  const describeMove = (move) => tr(`탑 ${move.from} → ${move.to} · 위에서 ${move.count}개${move.flip ? " · 뒤집기" : ""}`, `Tower ${move.from} → ${move.to} · Top ${move.count} block${move.count === 1 ? "" : "s"}${move.flip ? " · Flip" : ""}`);
  if (phase === "tower_execute") return data.moves?.length ? data.moves.map((move, index) => `${index + 1}. ${describeMove(move)}`).join(" / ") : tr("이동 없이 수식 제출", "Submit without moving blocks");
  if (phase === "tower_move") return describeMove(data);
  return typeof action === "string" ? action : JSON.stringify(action);
}

function phaseText(state) {
  if (state.result) return tr("최종 결과", "Final results");
  if (state.towerAdvance) return towerEventText("tower_advance", state.towerAdvance);
  if (state.towerVerdict) return state.towerVerdict.success ? tr("도전 성공", "Challenge complete") : tr("도전 실패", "Challenge failed");
  if (state.towerSkip) return tr("입찰 없음 · 다음 문제 준비", "No bids · Preparing the next problem");
  if (state.towerChallenge) return tr(`${state.towerChallenge.player}의 이동 도전`, `${state.towerChallenge.player} is solving`);
  if (state.towerWindow) return state.towerWindow.stage === "counter" ? tr("더 적은 이동 횟수로 재입찰", "Counterbid with fewer moves") : tr("입찰 버저 대기", "Waiting for an opening bid");
  return state.towerGame?.round ? tr("목표 수식 확인", "Inspect the target equation") : tr("게임 준비", "Preparing the match");
}

export function EquationTowerScene({state, players, selected, onChoose}) {
  const game = state.towerGame;
  const stacks = game?.stacks ?? [[], [], [], []];
  const move = state.towerLastMove;
  const challenge = state.towerChallenge;
  const verdict = state.towerVerdict;
  const roster = players ?? game?.players ?? [];
  const maxHeight = Math.max(10, ...stacks.map((stack) => stack.length));
  const blockHeight = Math.min(23, 227 / maxHeight);
  const baseY = 324;
  const stackX = (index) => 64 + index * 132;
  const activePlayer = challenge?.player ?? verdict?.player ?? state.towerBid?.player;
  return <section className="tower-arena pixel-frame" aria-label={tr("수식의 탑 감옥 게임판", "Tower of Equations prison board")}>
    <svg viewBox="0 0 590 455" role="img" aria-label={tr("4개의 탑 · 블록은 아래에서 위 순서", "Four towers · Blocks ordered bottom to top")}>
      <rect width="590" height="455" fill="#171d28" />
      <path d="M10 10H580V445H10Z" fill="none" stroke="#4c5665" strokeWidth="6" />
      <path d="M24 366H566M24 371H566" stroke="#7b684e" strokeWidth="4" />
      {[45, 94, 496, 545].map((x) => <path key={x} d={`M${x} 25V76`} stroke="#3a4654" strokeWidth="7" />)}
      <text x="295" y="30" className="tower-room-title">{tr("감옥 매치 · 수식의 탑", "PRISON MATCH · TOWER OF EQUATIONS")}</text>
      <g className="tower-target-board" aria-label={tr("목표 숫자와 층수", "Target number and height")}>
        <rect x="150" y="44" width="290" height="42" fill="#2b2c2a" stroke="#b39660" strokeWidth="3" />
        <text x="295" y="62" className="tower-target-label">{game?.round ? roundText(game.round) : tr("목표 수식", "TARGET EQUATION")}</text>
        <text x="295" y="79" className="tower-target-value">{game?.target != null ? tr(`숫자 ${game.target} · ${game.height}층`, `Number ${game.target} · Height ${game.height}`) : tr("목표 공개 대기", "Waiting for the target")}</text>
      </g>
      {stacks.map((stack, index) => <g key={index} data-stack={index + 1} className={`tower-stack${move?.to === index + 1 ? " tower-destination" : ""}`} aria-label={tr(`탑 ${index + 1} · 아래에서 위 ${stack.map((id) => blockText(game?.blocks[id], id)).join(", ") || "비어 있음"}`, `Tower ${index + 1} · Bottom to top: ${stack.map((id) => blockText(game?.blocks[id], id)).join(", ") || "empty"}`)}>
        <rect x={stackX(index) - 22} y="94" width="111" height="239" fill="#202733" stroke="#394352" strokeWidth="2" />
        {stack.map((id, level) => {
          const label = blockText(game?.blocks[id], id);
          const recent = move?.to === index + 1 && level >= stack.length - move.count;
          return <g key={id} data-block={id} data-level={level + 1} className={`tower-block${recent ? " tower-moved-block" : ""}`}>
            <rect x={stackX(index) - 10} y={baseY - (level + 1) * blockHeight} width="87" height={blockHeight - 1} rx="1" />
            <text x={stackX(index) + 33.5} y={baseY - (level + .5) * blockHeight + Math.min(4, blockHeight / 4)} style={{fontSize: Math.min(label.length > 7 ? 11 : 14, blockHeight * .68)}}>{label}</text>
          </g>;
        })}
        <path d={`M${stackX(index) - 19} 333H${stackX(index) + 85}`} stroke="#b89866" strokeWidth="5" />
        <text x={stackX(index) + 33} y="350" className="tower-stack-label">{tr(`탑 ${index + 1}`, `Tower ${index + 1}`)} · {stack.length}</text>
      </g>)}
      {move && <g className="tower-move-cue" aria-label={towerEventText("tower_move", move)}>
        <path d={move.from === move.to ? `M${stackX(move.to - 1) + 13} 109q20 -24 41 0l-3 -12m3 12l-13 -1` : `M${stackX(move.from - 1) + 33} 102H${stackX(move.to - 1) + 33}l${move.to > move.from ? -9 : 9} -5m${move.to > move.from ? 9 : -9} 5l${move.to > move.from ? -9 : 9} 5`} />
        <text x="295" y="365">{move.flip ? tr("↶ 뒤집어 이동", "↶ Flip and move") : tr("→ 블록 묶음 이동", "→ Move top blocks")}</text>
      </g>}
      {roster.map((player, index) => {
        const x = 295 + (index - (roster.length - 1) / 2) * 145;
        const active = activePlayer === player;
        const label = `${player} · ${active ? challenge ? tr("도전 중", "Solving") : verdict ? verdict.success ? tr("도전 성공", "Challenge complete") : tr("도전 실패", "Challenge failed") : tr("버저 입찰", "Buzzer bid") : (state.towerSafe ?? []).includes(player) ? tr("생존 확정", "Safe") : tr("입찰 참가자", "Bidder")}`;
        return <g key={player} data-player={player} className="tower-player" role="button" tabIndex="0" aria-label={label} aria-pressed={selected === player}
          onClick={() => onChoose?.(player)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onChoose?.(player); } }}>
          <title>{label}</title>
          <rect x={x - 36} y="384" width="72" height="44" fill={selected === player ? "#4c4851" : "#2c3440"} stroke={active ? "#ffe6a7" : "#505a68"} strokeWidth={active ? 3 : 1} />
          <rect x={x - 8} y="379" width="16" height="14" fill="#d9b897" />
          <path d={`M${x - 12} 397H${x + 12}V408H${x - 12}Z`} fill={colors[index % colors.length]} />
          <rect x={x - 14} y="408" width="28" height="6" fill={active ? "#ed795f" : "#65524a"} />
          <text x={x} y="424" className="tower-player-label">{player}</text>
        </g>;
      })}
      <text x="295" y="441" className="tower-bottom-label">{verdict ? verdict.success ? tr("✓ 목표 완성", "✓ Target complete") : tr("× 도전 실패", "× Challenge failed") : tr("맨 위에서 묶어 이동 · 뒤집기 가능 · 연산자 없는 숫자가 맨 위", "Move top blocks · Flips allowed · Plain number on top")}</text>
    </svg>
    <p className={`tower-scene-status${verdict ? verdict.success ? " tower-success" : " tower-failure" : ""}`} role="status">{phaseText(state)}{challenge && ` · ${movesText(challenge.bid)} · ${challenge.seconds}s`}</p>
  </section>;
}

const englishRules = "Build a tower with exactly the target height and value. Read its equation from top to bottom using normal arithmetic precedence; its top block must be a plain number. Buzz with a move count within 5 minutes. Others have 2 minutes to bid fewer moves. The winner has 2 minutes to solve. Each move takes one or more top blocks to a tower, optionally flipping the group. Opening bidders gain or lose 1 point; counterbidders gain or lose 2. Once a player reaches 7 points, last place is eliminated. A last-place tie starts a fresh race for those players. No discussion.";
const koreanRules = "목표 숫자와 층수를 만족하는 탑을 만듭니다. 맨 위에는 연산자 없는 숫자가 와야 하며, 수식은 위에서 아래로 읽고 사칙연산의 우선순위를 따릅니다. 5분 안에 버저로 이동 횟수를 입찰합니다. 다른 참가자는 2분 동안 더 적은 횟수로 입찰할 수 있습니다. 낙찰자는 2분 안에 도전합니다. 맨 위 블록 묶음을 옮기며 뒤집을 수 있습니다. 최초 입찰자의 성공·실패는 ±1점, 후발 입찰자는 ±2점입니다. 7점에 도달하면 최하위가 탈락하고, 최하위 동점자는 승점을 초기화해 재대결합니다. 대화 없이 진행합니다.";

export function EquationTowerStage({state, players}) {
  const game = state.towerGame;
  const roster = players ?? game?.players ?? [];
  const challenge = state.towerChallenge;
  const verdict = state.towerVerdict;
  const result = state.result;
  const rules = state.feed?.findLast((event) => event.msg_type === "rules");
  return <div className="tower-stage">
    <h2>{tr("수식의 탑", "Tower of Equations")}</h2>
    {!game ? <div className="tower-rules"><h3>{tr("게임 규칙", "Game rules")}</h3><p>{en ? englishRules : rules?.content ?? koreanRules}</p></div> : <>
      <p className="tower-phase">{phaseText(state)}</p>
      {game.target != null && <div className="tower-objective"><span>{roundText(game.round)}</span><strong>{tr(`목표 숫자 ${game.target}`, `Target number ${game.target}`)}</strong><strong>{tr(`${game.height}층`, `Height ${game.height}`)}</strong></div>}
      {result ? <Table caption={tr("최종 순위", "Final standings")} headers={tr(["순위", "참가자", "결과", "피스"], ["Rank", "Player", "Result", "Pieces"])} rows={result.ranking.map((player, index) => [index + 1, player, result.eliminated.includes(player) ? tr("탈락", "Eliminated") : tr("생존", "Survived"), result.pieces?.[player] ?? "–"])} /> :
        <Table caption={tr("참가자 승점", "Player scores")} headers={tr(["참가자", "승점", "상태"], ["Player", "Points", "Status"])} rows={roster.map((player) => [player, game.scores?.[player] ?? "–", (state.towerSafe ?? []).includes(player) ? tr("생존 확정", "Safe") : challenge?.player === player ? tr("도전 중", "Solving") : state.towerBid?.player === player ? tr(`입찰 ${state.towerBid.moves}회`, `Bid: ${state.towerBid.moves} moves`) : (game.players ?? []).includes(player) ? tr("입찰 대기", "Ready to bid") : tr("대기", "Waiting")])} />}
      {state.towerWindow && <p className="tower-bid-window">{towerEventText("tower_bid_window", state.towerWindow)}{state.towerBid && ` · ${state.towerBid.player} ${movesText(state.towerBid.moves)}`}</p>}
      {challenge && <section className="tower-challenge" aria-label={tr("현재 도전", "Current challenge")}><h3>{challenge.player}</h3><p>{tr("허용 이동", "Move allowance")}: {movesText(challenge.bid)} · {tr("제한 시간", "Time limit")}: {challenge.seconds}s</p><p>{tr("걸린 승점", "Points at stake")}: {challenge.stake} · {tr("사용 이동", "Moves used")}: {state.towerLastMove?.index ?? 0}</p></section>}
      {state.towerLastMove && <p className="tower-last-move">{towerEventText("tower_move", state.towerLastMove)}</p>}
      {verdict && <section className={`tower-verdict ${verdict.success ? "tower-success" : "tower-failure"}`} aria-label={tr("도전 판정", "Challenge verdict")}><h3>{towerEventText("tower_verdict", verdict)}</h3>
        {verdict.expression && <p className="tower-expression">{verdict.expression} = {verdict.value ?? "–"}</p>}
        <p>{tr("사용 이동 / 허용 이동", "Used / allowed moves")}: {verdict.used ?? "–"} / {verdict.allowed ?? "–"}</p>
      </section>}
      {state.towerSkip && <p className="muted">{towerEventText("tower_skip", state.towerSkip)}</p>}
      <p className="muted">{tr(`목표 ${game.goal}점 · 블록은 아래→위로 표시 · 대화 없이 진행`, `Goal: ${game.goal} points · Blocks shown bottom to top · No discussion`)}</p>
    </>}
  </div>;
}

export function EquationTowerInformation({state, replay}) {
  const [tab, setTab] = useState("rounds");
  const results = state.towerResults ?? [];
  const records = (state.feed ?? []).filter((event) => ["tower_bid_window", "tower_bid", "tower_challenge", "tower_move", "tower_skip", "tower_advance"].includes(event.msg_type));
  return <aside className="caption tower-information" aria-label={tr("수식의 탑 결과와 기록", "Tower of Equations results and records")}>
    <TabList role="tablist" aria-label={tr("수식의 탑 정보 종류", "Tower of Equations information tabs")} value={tab} onChange={setTab} size="sm" hasDivider>
      <Tab id="tower-rounds" value="rounds" label={tr("라운드 점수", "Round scores")} panelId="tower-records-panel" />
      <Tab id="tower-moves" value="moves" label={tr("입찰·이동 기록", "Bids and moves")} panelId="tower-records-panel" />
    </TabList>
    <div id="tower-records-panel" role="tabpanel" aria-labelledby={`tower-${tab}`}>
      {tab === "rounds" ? results.length ? results.map((result, index) => <section key={`${result.step}-${index}`} className="tower-round-result">
        <h3><button type="button" onClick={() => replay.seek(result.step)}>{roundText(result.round)} · {result.player} · {result.success ? tr("성공", "Success") : tr("실패", "Failed")} · {changeText(result.change)}</button></h3>
        {result.expression && <p className="tower-expression">{result.expression} = {result.value ?? "–"}</p>}
        <Table caption={tr("판정 후 승점", "Scores after the challenge")} headers={tr(["참가자", "승점"], ["Player", "Points"])} rows={Object.entries(result.scores ?? {})} />
      </section>) : <p className="muted">{tr("아직 도전 판정이 없어요.", "No challenges have been judged yet.")}</p> : records.length ? <ol className="tower-move-log">{records.map((event) => <li key={event.step}><button type="button" onClick={() => replay.seek(event.step)}>{event.step} · {event.text ?? towerEventText(event.msg_type, event.data)}</button></li>).reverse()}</ol> : <p className="muted">{tr("아직 입찰·이동 기록이 없어요.", "No bids or moves have been recorded yet.")}</p>}
    </div>
  </aside>;
}
