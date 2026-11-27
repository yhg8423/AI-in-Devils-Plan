import React, {useState} from "react";
import {Tab, TabList} from "@astryxdesign/core/TabList";
import {en, tr} from "./locale.js";
import {Table} from "./records.jsx";
import "./gradation.css";

const colors = ["black", "silver", "gray", "white"];
const fixedColors = ["black", "silver", "gray", "white", "gray", "silver", "black"];
const palette = {black: "#20252d", silver: "#697482", gray: "#b4bac2", white: "#f5f3ec"};
const colorNames = {black: tr("검정", "Black"), silver: tr("은색", "Silver"), gray: tr("회색", "Gray"), white: tr("흰색", "White")};
const freshCounts = () => ({black: 2, silver: 2, gray: 2, white: 1});
const cloneRemaining = (remaining) => Object.fromEntries(Object.entries(remaining ?? {}).map(([player, counts]) => [player, {...counts}]));
const matchText = (number) => tr(`대결 ${number}`, `Match ${number}`);
const roundText = (number) => tr(`${number}라운드`, `Round ${number}`);
const choicesText = (choices) => Object.entries(choices ?? {}).map(([player, choice]) => `${player} ${colorNames[choice.color]} ${choice.value}`).join(" · ");

export function applyGradEvent(state, type, data, event = {}) {
  if (!type.startsWith("grad_")) return;
  switch (type) {
    case "grad_setup":
      state.gradGame = {...data, players: [...data.players], order: [...data.order], colors: [...data.colors]};
      state.gradMatch = null;
      state.gradLayouts = {};
      state.gradUsed = {};
      state.gradReady = [];
      state.gradOffers = {};
      state.gradReveal = state.gradEnd = null;
      state.gradMatches = [];
      state.gradRounds = [];
      state.gradStreak = 0;
      state.gradHolder = null;
      break;
    case "grad_match":
      state.gradMatch = {...data, players: [...data.players], round: 0, scores: Object.fromEntries(data.players.map((player) => [player, 0])), remaining: Object.fromEntries(data.players.map((player) => [player, freshCounts()]))};
      state.gradLayouts = {};
      state.gradUsed = Object.fromEntries(data.players.map((player) => [player, []]));
      state.gradReady = [];
      state.gradOffers = {};
      state.gradReveal = state.gradEnd = null;
      state.gradStreak = data.streak;
      break;
    case "grad_layout": state.gradLayouts ??= {}; state.gradLayouts[data.player] = {...data, numbers: [...data.numbers]}; break;
    case "grad_ready": state.gradReady = [...new Set([...(state.gradReady ?? []), data.player])]; break;
    case "grad_round":
      if (state.gradMatch) Object.assign(state.gradMatch, data, {scores: {...data.scores}, remaining: cloneRemaining(data.remaining)});
      state.gradOffers = {};
      state.gradReveal = null;
      break;
    case "grad_selection":
      state.gradUsed ??= {};
      state.gradUsed[data.player] = [...new Set([...(state.gradUsed[data.player] ?? []), data.slot])];
      break;
    case "grad_offer": {
      state.gradOffers ??= {};
      if (!state.gradOffers[data.player] && state.gradMatch?.remaining[data.player]?.[data.color] > 0) state.gradMatch.remaining[data.player][data.color] -= 1;
      state.gradOffers[data.player] = {color: data.color};
      break;
    }
    case "grad_reveal":
      state.gradReveal = {...data, choices: Object.fromEntries(Object.entries(data.choices).map(([player, choice]) => [player, {...choice}])), scores: {...data.scores}, step: event.step};
      if (state.gradMatch) {state.gradMatch.scores = {...data.scores}; state.gradMatch.leader = data.next_leader;}
      state.gradRounds ??= [];
      state.gradRounds.push(state.gradReveal);
      break;
    case "grad_match_result":
      state.gradEnd = {...data, players: [...data.players], scores: {...data.scores}, step: event.step};
      state.gradMatches ??= [];
      state.gradMatches.push(state.gradEnd);
      state.gradStreak = data.streak;
      if (data.winner) state.gradHolder = data.winner;
      break;
  }
}

export function gradEventText(type, data) {
  switch (type) {
    case "grad_setup": return data.duel ? tr("2인 단판 변형 · 동점은 재대결", "Two-player single-match adaptation · Replay ties") : tr("3인 승자 잔류 · 대결 2연승으로 결승 진출", "Three-player winner stays · Two consecutive match wins reach the final");
    case "grad_match": return `${matchText(data.match)} · ${data.players.join(" vs ")}${data.waiting ? ` · ${tr("대기", "Waiting")} ${data.waiting}` : ""}${data.replay ? tr(` · 동률 재대결 ${data.replay}`, ` · Tied-match replay ${data.replay}`) : ""}`;
    case "grad_layout": return `${data.player} · ${tr("비공개 숫자 배치 확인", "Private number layout received")}`;
    case "grad_ready": return `${data.player} · ${tr("숫자 배치 준비 완료", "Number layout ready")}`;
    case "grad_round": return `${matchText(data.match)} · ${roundText(data.round)} · ${tr("선공", "Leader")} ${data.leader}`;
    case "grad_selection": return `${data.player} · ${tr("비공개 통 선택 완료", "Private cup selection complete")}`;
    case "grad_offer": return `${data.player} · ${colorNames[data.color]} · ${tr("숫자 비공개", "Number hidden")}`;
    case "grad_reveal": return `${choicesText(data.choices)} · ${data.winner ? tr(`${data.winner} +1점`, `${data.winner} +1 point`) : tr("비김 · 승점·선공 유지", "Tie · Scores and leader unchanged")}`;
    case "grad_match_result": return `${matchText(data.match)} · ${data.tied ? tr("총점 동률 · 같은 대진 재대결", "Tied score · Same players replay") : tr(`${data.winner} 승리 · 대결 ${data.streak}연승`, `${data.winner} wins · ${data.streak} consecutive match win${data.streak === 1 ? "" : "s"}`)}`;
  }
}

export function gradActionText(phase, action) {
  if (phase === "grad_prepare") return tr("비공개 숫자 7개 배치 제출", "Submit seven private numbers");
  if (phase === "grad_choose") return tr("비공개 통 선택", "Choose a private cup");
  return action;
}

function phaseText(state) {
  if (state.result) return tr("최종 결과", "Final results");
  if (state.gradEnd) return gradEventText("grad_match_result", state.gradEnd);
  if (state.gradReveal) return state.gradReveal.winner ? tr(`${state.gradReveal.winner} 1점 획득 · 다음 선공`, `${state.gradReveal.winner} scores 1 · Leads next`) : tr("라운드 비김 · 선공 유지", "Tied round · Leader unchanged");
  if (state.gradMatch?.round) {
    const count = Object.keys(state.gradOffers ?? {}).length;
    return count === 2 ? tr("두 통 제출 완료 · 숫자 공개 대기", "Both cups submitted · Awaiting reveal") : count === 1 ? tr("선공의 색 공개 · 후공 선택 중", "Leader's color shown · Follower choosing") : tr("선공 통 선택", "Leader choosing a cup");
  }
  return state.gradMatch ? tr(`비공개 숫자 배치 · 준비 ${state.gradReady?.length ?? 0}/2`, `Private layouts · ${state.gradReady?.length ?? 0}/2 ready`) : tr("대진 추첨·게임 준비", "Drawing the first match and leader");
}

function Cup({x, y, color, value, used, slot, player, offered = false}) {
  return <g className={`grad-cup${used ? " grad-used-cup" : ""}${offered ? " grad-offered-cup" : ""}`} data-cup-color={color} data-cup-value={value ?? undefined} data-own-slot={slot} data-cup-player={player}>
    <title>{slot ? tr(`내 통 ${slot} · ${colorNames[color]} · ${value ?? "배치 대기"}${used ? " · 사용함" : ""}`, `Own cup ${slot} · ${colorNames[color]} · ${value ?? "Awaiting layout"}${used ? " · Used" : ""}`) : `${colorNames[color]} · ${value == null ? tr("숫자 비공개", "Number hidden") : value}`}</title>
    <path d={`M${x - 23} ${y - 17}H${x + 23}L${x + 19} ${y + 24}H${x - 19}Z`} fill={palette[color]} />
    <path d={`M${x - 25} ${y - 20}H${x + 25}V${y - 13}H${x - 25}Z`} fill={palette[color]} className="grad-cup-rim" />
    <text x={x} y={y + 10} className={`grad-cup-number${color === "black" || color === "silver" ? " grad-light-ink" : ""}`}>{value ?? "?"}</text>
    {used && <path className="grad-used-mark" d={`M${x - 22} ${y - 22}L${x + 22} ${y + 25}M${x + 22} ${y - 22}L${x - 22} ${y + 25}`} />}
  </g>;
}

function CupRow({state, player, y}) {
  const perspective = state.gradPerspective ?? "public";
  const privateView = perspective === "operator" || perspective === player;
  const layout = state.gradLayouts?.[player];
  const remaining = state.gradMatch?.remaining?.[player] ?? freshCounts();
  return <g className={`grad-cup-row${privateView ? " grad-private-row" : " grad-anonymous-row"}`} data-row-player={player}>
    <rect x="44" y={y - 31} width="590" height="96" fill="#303944" stroke="#68737d" strokeWidth="3" />
    {privateView ? <>
      {(state.gradGame?.colors ?? fixedColors).map((color, index) => <g key={index}><Cup x={82 + index * 86} y={y} color={color} value={layout?.numbers[index]} used={state.gradUsed?.[player]?.includes(index + 1)} slot={index + 1} player={player} /><text x={82 + index * 86} y={y + 42} className="grad-slot-label">{index + 1} · {colorNames[color]}</text></g>)}
      <text x="339" y={y + 59} className="grad-row-caption">{layout ? tr(`내 합계 ${layout.numbers.reduce((sum, value) => sum + value, 0)} / 30 · 왼쪽→오른쪽 비감소`, `Own total ${layout.numbers.reduce((sum, value) => sum + value, 0)} / 30 · Nondecreasing left to right`) : tr("내 고정 슬롯 · 숫자 배치 대기", "Own fixed slots · Awaiting layout")}{layout?.late ? tr(" · 시간 초과 대체 배치", " · Fallback after timeout") : ""}</text>
    </> : <>
      {colors.map((color, index) => <g key={color} data-anonymous-color={color} data-remaining-count={remaining[color] ?? 0}>
        <rect x={52 + index * 145} y={y - 25} width="136" height="74" fill="#222d38" stroke="#465260" />
        {Array.from({length: remaining[color] ?? 0}, (_, cup) => <Cup key={cup} x={remaining[color] === 1 ? 120 + index * 145 : 91 + index * 145 + cup * 58} y={y} color={color} player={player} />)}
        <text x={120 + index * 145} y={y + 43} className="grad-color-count">{colorNames[color]} ×{remaining[color] ?? 0}</text>
      </g>)}
      <text x="339" y={y + 59} className="grad-row-caption">{tr("색별 남은 통 · 원래 위치는 비공개", "Remaining cups by color · Original positions hidden")}</text>
    </>}
  </g>;
}

export function GradationScene({state, players, selected, onChoose}) {
  const match = state.gradMatch;
  const active = match?.players ?? state.gradGame?.order?.slice(0, 2) ?? players?.slice(0, 2) ?? [];
  const waiting = match?.waiting ?? (!match ? state.gradGame?.order?.[2] : null);
  const leader = match?.leader;
  const perspective = state.gradPerspective ?? "public";
  return <section className="grad-arena pixel-frame" aria-label={tr("그라데이션 감옥 게임판", "Gradation prison board")}>
    <svg viewBox="0 0 740 520" role="img" aria-label={tr("두 참가자의 통과 중앙 제출 구역 · 상대는 색별 익명 표시", "Two cup tables and a central offer area · Opponents shown as anonymous color counts")}>
      <rect width="740" height="520" fill="#171e28" />
      <path d="M10 10H730V510H10Z" fill="none" stroke="#53606e" strokeWidth="6" />
      {[25, 75, 125, 605, 655, 705].map((x) => <path key={x} d={`M${x} 20V73M${x - 8} 74H${x + 8}`} stroke="#394758" strokeWidth="7" />)}
      <path d="M29 300H712M29 305H712" stroke="#655c4e" strokeWidth="4" />
      <text x="370" y="30" className="grad-room-title">{tr("감옥 매치 · 그라데이션", "PRISON MATCH · GRADATION")}</text>
      {active.map((player, index) => <g key={player}>
        <g role="button" tabIndex="0" className="grad-player" data-player={player} aria-pressed={selected === player} aria-label={`${player} · ${leader === player ? tr("선공", "Leader") : tr("후공", "Follower")}`}
          onClick={() => onChoose?.(player)} onKeyDown={(event) => {if (event.key === "Enter" || event.key === " ") {event.preventDefault(); onChoose?.(player);}}}>
          <rect x="254" y={index === 0 ? 47 : 333} width="170" height="27" fill={selected === player ? "#4a4354" : "#26313e"} stroke={leader === player ? "#e5cb87" : "#5c6979"} strokeWidth="2" />
          <rect x="266" y={index === 0 ? 54 : 340} width="12" height="12" fill={index === 0 ? "#df9989" : "#8bbad2"} />
          <text x="342" y={index === 0 ? 65 : 351} className="grad-player-name">{player}{leader === player ? tr(" · 선공", " · LEADER") : ""}</text>
        </g>
        <CupRow state={state} player={player} y={index === 0 ? 120 : 406} />
      </g>)}
      <g className="grad-round-board"><rect x="38" y="214" width="127" height="73" fill="#2c3031" stroke="#a18e62" strokeWidth="3" /><text x="101" y="235">{match ? matchText(match.match) : tr("대결 준비", "SETUP")}</text><text x="101" y="256">{match?.round ? `${match.round} / 7` : tr("배치 5분", "5 MIN SETUP")}</text><text x="101" y="276">{active.map((player) => match?.scores?.[player] ?? 0).join(" : ")}</text></g>
      {active.map((player, index) => {
        const offer = state.gradOffers?.[player];
        const revealed = state.gradReveal?.choices?.[player];
        const x = 265 + index * 145;
        return <g key={player} className="grad-central-offer" data-offer-player={player} data-offer-value={revealed?.value}>
          <rect x={x - 53} y="206" width="106" height="91" fill="#242d38" stroke="#526172" strokeWidth="2" />
          <text x={x} y="222" className="grad-offer-player">{player}</text>
          {offer || revealed ? <Cup x={x} y={253} color={revealed?.color ?? offer.color} value={revealed?.value} offered player={player} /> : <text x={x} y="258" className="grad-offer-wait">{tr("선택 대기", "WAITING")}</text>}
          <text x={x} y="291" className="grad-offer-label">{offer || revealed ? colorNames[revealed?.color ?? offer.color] : "–"}</text>
        </g>;
      })}
      {waiting && <g className="grad-waiting-player" data-waiting={waiting} role="button" tabIndex="0" aria-label={tr(`대기 참가자 ${waiting}`, `Waiting player ${waiting}`)} aria-pressed={selected === waiting}
        onClick={() => onChoose?.(waiting)} onKeyDown={(event) => {if (event.key === "Enter" || event.key === " ") {event.preventDefault(); onChoose?.(waiting);}}}>
        <path d="M565 271H700V283H565ZM580 283V300M685 283V300" fill="#5e5b56" stroke="#8a8170" strokeWidth="2" />
        <rect x="624" y="224" width="21" height="21" fill="#d0b395" /><path d="M619 248H650V273H619Z" fill="#b9a0d4" />
        <text x="634" y="207">{tr("대기", "WAITING")}</text><text x="634" y="320">{waiting}</text>
      </g>}
      <text x="370" y="494" className="grad-view-label">{perspective === "operator" ? tr("운영자 시점 · 두 배치의 고정 슬롯 공개", "OPERATOR VIEW · BOTH PRIVATE ROWS VISIBLE") : perspective === "public" ? tr("공개 시점 · 상대 통의 위치·합계·숫자는 비공개", "PUBLIC VIEW · PRIVATE POSITIONS, TOTALS AND NUMBERS HIDDEN") : tr(`${perspective} 시점 · 내 슬롯만 표시`, `${perspective} VIEW · ONLY YOUR FIXED SLOTS ARE SHOWN`)}</text>
    </svg>
    <p className={`grad-scene-status${state.gradReveal ? " grad-revealed" : ""}`} role="status">{phaseText(state)}</p>
  </section>;
}

const englishRules = "Hide seven cubes in seven fixed cups within 5 minutes. Numbers are 0–9, at most two of each, in nondecreasing left-to-right order with a total of 30 or less. Cup colors are symmetric: black, silver, gray, white, gray, silver, black. Your opponent sees only anonymous remaining counts for each color.\n\nThe leader submits one unused cup, then the follower answers after seeing only its color. Reveal both numbers together: the larger number scores 1, a tie scores 0. The winner leads next; a tie keeps the leader. Compare totals after all 7 rounds. A tied match is replayed with fresh layouts and adds no match win.\n\nWith three players, the winner stays and faces the waiting player. Two consecutive match wins earn the final spot; the others are eliminated. The two-player single-match route is a simulator adaptation. Tied-match first-leader retention and valid fallback layouts after invalid or late preparation are also simulator policies. No discussion or Piece spending.";
const koreanRules = "5분 안에 숫자 7개를 통에 비공개 배치합니다. 0~9 각 두 개 재고에서 골라 왼쪽→오른쪽 비감소 순서, 합계 30 이하로 만듭니다. 선공의 통 색을 본 뒤 후공이 통을 내고, 두 숫자를 동시에 공개합니다. 큰 숫자가 1점이며 비기면 0점입니다. 승자가 다음 선공이고, 비기면 선공을 유지합니다. 7라운드 총점 동률은 새 배치로 재대결합니다. 3인은 대결 2연승이 결승 진출 조건이며, 2인 단판은 시뮬레이터 변형입니다. 상대의 원래 통 위치와 비공개 숫자는 볼 수 없습니다.";

export function GradationStage({state, players}) {
  const game = state.gradGame;
  const match = state.gradMatch;
  const result = state.result;
  const roster = players ?? game?.players ?? [];
  const rules = state.feed?.findLast((event) => event.msg_type === "rules");
  const finalRank = (player, index) => {
    let rank = 1;
    for (const group of result?.ranking_groups ?? []) {if (group.includes(player)) return rank; rank += group.length;}
    return index + 1;
  };
  return <div className="grad-stage"><h2>{tr("그라데이션", "Gradation")}</h2>
    {!game ? <div className="grad-rules"><h3>{tr("게임 규칙", "Game rules")}</h3><p>{en ? englishRules : rules?.content ?? koreanRules}</p></div> : <>
      <p className="grad-phase">{phaseText(state)}</p>
      <p className="grad-mode">{game.duel ? tr("2인 단판 · 시뮬레이터 변형 · 동률은 재대결", "Two-player single-match adaptation · Replay ties") : tr("3인 승자 잔류 · 대결 2연승으로 결승 진출", "Three-player winner stays · Two consecutive match wins reach the final")}</p>
      {match && <div className="grad-score-board"><strong>{matchText(match.match)}{match.replay ? tr(` · 재대결 ${match.replay}`, ` · Replay ${match.replay}`) : ""}</strong><span>{match.players.join(" vs ")}</span><b>{match.players.map((player) => match.scores[player] ?? 0).join(" : ")}</b><span>{match.round ? `${roundText(match.round)} / 7` : tr("비공개 배치 · 5분", "Private layout · 5 minutes")}</span></div>}
      {result ? <div className="match-table-wrap"><table className="match-table"><caption>{tr("최종 순위", "Final standings")}</caption><thead><tr>{tr(["순위", "참가자", "결과", "피스"], ["Rank", "Player", "Result", "Pieces"]).map((header) => <th scope="col" key={header}>{header}</th>)}</tr></thead><tbody>{(result.ranking ?? []).map((player, index) => <tr key={player}><th scope="row">{finalRank(player, index)}</th><td>{player}</td><td>{result.finalists?.includes(player) || result.survivors?.includes(player) ? tr("결승 진출", "Finalist") : tr("탈락", "Eliminated")}</td><td>{result.pieces?.[player] ?? "–"}</td></tr>)}</tbody></table></div> :
        <Table caption={tr("참가자 현황", "Player status")} headers={tr(["참가자", "현재 승점", "대결 연승", "상태"], ["Player", "Current points", "Match streak", "Status"])} rows={roster.map((player) => [player, match?.scores?.[player] ?? "–", state.gradHolder === player ? state.gradStreak : 0, match?.waiting === player ? tr("대기", "Waiting") : match?.round ? match.leader === player ? tr("다음 선공", "Leads next") : tr("후공", "Follower") : state.gradReady?.includes(player) ? tr("배치 준비 완료", "Layout ready") : tr("배치 중", "Preparing layout")])} />}
      {state.gradHolder && !game.duel && <p className="grad-streak">{tr(`${state.gradHolder} · 대결 ${state.gradStreak}연승 / 목표 ${game.goal}연승`, `${state.gradHolder} · ${state.gradStreak} consecutive match win${state.gradStreak === 1 ? "" : "s"} / ${game.goal} needed`)}</p>}
      {match?.waiting && <p>{tr(`대기 참가자 ${match.waiting} · 대결 승자와 다음 대결`, `Waiting player ${match.waiting} faces the match winner next`)}</p>}
      {state.gradReveal && <p className="grad-last-reveal">{gradEventText("grad_reveal", state.gradReveal)}</p>}
      {state.gradEnd?.tied && <p className="grad-tie">{tr("총점 동률은 승리·연승에 더하지 않습니다. 같은 대진이 새 숫자로 재대결합니다.", "A tied match adds no win or streak. The same players submit new layouts and replay.")}</p>}
      <p className="muted">{tr("숫자는 둘 다 제출한 뒤 공개 · 상대의 원래 좌우 위치는 끝까지 비공개 · 대화 없음", "Reveal numbers only after both submit · Opponent positions stay private · No discussion")}</p>
    </>}
  </div>;
}

export function GradationInformation({state, replay}) {
  const [tab, setTab] = useState("matches");
  const matches = state.gradMatches ?? [];
  const rounds = state.gradRounds ?? [];
  const numbers = [...new Set([...matches.map((match) => match.match), ...(state.gradMatch ? [state.gradMatch.match] : [])])];
  const records = (state.feed ?? []).filter((event) => ["grad_ready", "grad_offer", "grad_reveal", "grad_match_result"].includes(event.msg_type));
  return <aside className="caption grad-information" aria-label={tr("그라데이션 대결과 기록", "Gradation matches and records")}>
    <TabList role="tablist" aria-label={tr("그라데이션 정보 종류", "Gradation information tabs")} value={tab} onChange={setTab} size="sm" hasDivider>
      <Tab id="grad-matches" value="matches" label={tr("대결·라운드 점수", "Matches and round scores")} panelId="grad-records-panel" />
      <Tab id="grad-offers" value="offers" label={tr("제출·공개 기록", "Offers and reveals")} panelId="grad-records-panel" />
    </TabList>
    <div id="grad-records-panel" role="tabpanel" aria-labelledby={`grad-${tab}`}>
      {tab === "matches" ? numbers.length ? numbers.map((number) => {
        const result = matches.find((match) => match.match === number);
        const scored = rounds.filter((round) => round.match === number);
        const participants = result?.players ?? state.gradMatch?.players ?? [];
        return <section key={number} className="grad-match-result"><h3>{result ? <button type="button" onClick={() => replay.seek(result.step)}>{gradEventText("grad_match_result", result)}</button> : `${matchText(number)} · ${tr("진행 중", "In progress")}`}</h3>
          {scored.length ? <Table caption={tr("라운드 공개 결과", "Revealed round results")} headers={[tr("라운드", "Round"), ...participants, tr("승점", "Points"), tr("이동", "Seek")]} rows={scored.map((round) => [round.round, ...participants.map((player) => {const choice = round.choices[player]; return choice ? `${colorNames[choice.color]} ${choice.value}` : "–";}), participants.map((player) => round.scores[player] ?? 0).join(" : "), <button type="button" onClick={() => replay.seek(round.step)}>{tr("보기", "View")}</button>])} /> : <p className="muted">{tr("아직 공개된 숫자가 없어요.", "No numbers have been revealed yet.")}</p>}
        </section>;
      }) : <p className="muted">{tr("아직 시작한 대결이 없어요.", "No matches have started yet.")}</p> : records.length ? <ol className="grad-offer-log">{records.map((event) => <li key={event.step}><button type="button" onClick={() => replay.seek(event.step)}>{event.step} · {event.text ?? gradEventText(event.msg_type, event.data)}</button></li>).reverse()}</ol> : <p className="muted">{tr("아직 제출 기록이 없어요.", "No cups have been submitted yet.")}</p>}
    </div>
  </aside>;
}
