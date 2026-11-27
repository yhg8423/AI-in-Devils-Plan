import React, {useState} from "react";
import {Tab, TabList} from "@astryxdesign/core/TabList";
import {en, tr} from "./locale.js";
import {Table} from "./records.jsx";
import "./hit-stay.css";

const phaseNames = {bet1: tr("1차 베팅", "First betting"), hit_stay: tr("HIT / STAY 선택", "HIT / STAY decision"), bet2: tr("2차 베팅", "Second betting")};
const actionNames = {call: tr("콜", "Call"), raise: tr("레이즈", "Raise"), fold: tr("포기", "Fold"), HIT: "HIT", STAY: "STAY", hit: "HIT", stay: "STAY"};
const chipsText = (value) => tr(`${value}칩`, `${value} chips`);
const roundText = (data) => tr(`${data.round}라운드${data.tiebreak ? ` · 연장 ${data.tiebreak}` : ""}`, `Round ${data.round}${data.tiebreak ? ` · Tiebreak ${data.tiebreak}` : ""}`);
const cloneCards = (cards = {}) => Object.fromEntries(Object.entries(cards).map(([player, hand]) => [player, [...hand]]));
const interestText = (choice) => ["public", "public_interest", "공공의 이익"].includes(choice) ? tr("공공의 이익", "Public interest") : ["private", "personal", "personal_interest", "개인의 이익"].includes(choice) ? tr("개인의 이익", "Personal interest") : tr("선택 완료", "Choice submitted");
const showdownReason = (reason) => ({
  showdown: tr("한계 숫자에 가까운 합계", "Closest total to the limit"),
  best_hand: tr("한계 숫자에 가까운 합계 · 동률이면 카드 장수", "Closest total to the limit · Card count breaks ties"),
  uncontested: tr("유일한 비포기 참가자", "Only player remaining"),
  sole: tr("유일한 비포기 참가자", "Only player remaining"),
  last_player: tr("유일한 비포기 참가자", "Only player remaining"),
  all_folded: tr("비교할 손패 없음", "No hands to compare"),
  all_bust: tr("모두 한계 숫자 초과", "All hands exceed the limit"),
  tie: tr("합계·장수 동률", "Tied total and card count"),
})[reason] ?? tr("라운드 정산", "Round settlement");

function applySnapshot(state, data) {
  const game = state.hitGame;
  if (!game) return;
  for (const field of ["pot", "deck_remaining", "limit", "ante", "current_total", "cap"]) if (data[field] != null) game[field] = data[field];
  for (const field of ["chips", "contributions", "hand_counts"]) if (data[field]) game[field] = {...data[field]};
  for (const field of ["folded", "stayed"]) if (data[field]) game[field] = [...data[field]];
  if (data.public_cards) state.hitPublicCards = cloneCards(data.public_cards);
}

export function applyHitEvent(state, type, data, event = {}) {
  if (!type.startsWith("hit_")) return;
  switch (type) {
    case "hit_setup":
      state.hitGame = {...data, players: [...data.players], seats: [...(data.seats ?? data.players)], chips: {...data.initial_chips}, contributions: {}, folded: [], stayed: [], hand_counts: {}};
      state.hitHands = {};
      state.hitPublicCards = {};
      state.hitHiddenCounts = {};
      state.hitResults = [];
      state.hitPrison = [];
      state.hitEliminated = [];
      state.hitTurn = state.hitLastBet = state.hitLastCard = state.hitShowdown = state.hitTiebreak = state.hitFinal = state.hitInterest = null;
      break;
    case "hit_interest":
      state.hitInterest = {...data, choices: {...data.choices}, chips: {...data.chips}};
      applySnapshot(state, data);
      break;
    case "hit_round":
      if (!state.hitGame) break;
      Object.assign(state.hitGame, data, {players: [...data.players], chips: {...data.chips}, contributions: {...data.contributions}, folded: [], stayed: [], hand_counts: {}});
      state.hitHands = {};
      state.hitPublicCards = {};
      state.hitHiddenCounts = {};
      state.hitTurn = state.hitLastBet = state.hitLastCard = state.hitShowdown = null;
      break;
    case "hit_hand": state.hitHands ??= {}; state.hitHands[data.player] = [...data.cards]; break;
    case "hit_reveal":
      state.hitPublicCards = Object.fromEntries(Object.entries(data.cards ?? {}).map(([player, card]) => [player, Array.isArray(card) ? [...card] : [card]]));
      state.hitHiddenCounts = {...data.hidden_counts};
      if (state.hitGame) {
        state.hitGame.hand_counts = Object.fromEntries(Object.entries(state.hitPublicCards).map(([player, cards]) => [player, cards.length + (data.hidden_counts?.[player] ?? 2)]));
        if (data.deck_remaining != null) state.hitGame.deck_remaining = data.deck_remaining;
      }
      break;
    case "hit_turn": state.hitTurn = {...data}; applySnapshot(state, data); break;
    case "hit_bet": state.hitLastBet = {...data, step: event.step}; applySnapshot(state, data); break;
    case "hit_card": state.hitLastCard = {...data, step: event.step}; applySnapshot(state, data); break;
    case "hit_showdown":
      state.hitShowdown = {...data, hands: cloneCards(data.hands), sums: {...data.sums}, counts: {...data.counts}, winners: [...data.winners], payouts: {...data.payouts}, chips: {...data.chips}, folded: [...(state.hitGame?.folded ?? [])], step: event.step};
      state.hitResults ??= [];
      state.hitResults.push(state.hitShowdown);
      applySnapshot(state, {...data, pot: data.remaining_pot ?? 0});
      state.hitTurn = null;
      break;
    case "hit_bust":
      state.hitBust = {...data};
      state.hitPrison = [...new Set([...(state.hitPrison ?? []), ...(data.prison ?? [])])];
      state.hitEliminated = [...new Set([...(state.hitEliminated ?? []), ...(data.eliminated ?? [])])];
      applySnapshot(state, data);
      break;
    case "hit_tiebreak": state.hitTiebreak = {...data}; state.hitTurn = null; if (data.stage === "start") state.hitShowdown = null; break;
    case "hit_final": state.hitFinal = {...data}; state.result = data; state.hitTurn = null; break;
  }
}

export function hitEventText(type, data) {
  switch (type) {
    case "hit_setup": return tr(`${data.players.length}명 · 숫자 카드 35장 · 좌석 ${data.seats?.join(" → ") ?? data.players.join(" → ")}`, `${data.players.length} players · 35 number cards · Seats: ${data.seats?.join(" → ") ?? data.players.join(" → ")}`);
    case "hit_interest": return tr(`공공의 이익 ${data.public_count}명 / 필요 ${data.threshold}명${data.prize_token ? " · 상금의 징표 획득" : ""}`, `Public interest: ${data.public_count} / ${data.threshold} required${data.prize_token ? " · Prize Token earned" : ""}`);
    case "hit_round": return `${roundText(data)} · ${tr("한계", "Limit")} ${data.limit} · ${tr("기본 베팅", "Ante")} ${chipsText(data.ante)}`;
    case "hit_hand": return `${data.player} · ${tr("비공개 초기 카드 수령", "Private initial hand received")}`;
    case "hit_reveal": return tr("각자 초기 카드 1장 공개 · 나머지 2장은 비공개", "One initial card shown each · Two cards stay private");
    case "hit_turn": return `${data.player} · ${phaseNames[data.phase] ?? tr("행동 차례", "Action turn")}${data.cap != null ? ` · ${tr("최대 누적 베팅", "Maximum total bet")} ${chipsText(data.cap)}` : ""}`;
    case "hit_bet": return `${data.player} · ${actionNames[data.type] ?? tr("베팅", "Bet")} · ${tr("추가", "Paid")} ${data.paid} · ${tr("누적", "Total")} ${data.total}`;
    case "hit_card": return `${data.player} · ${actionNames[data.type] ?? data.type}${data.type === "HIT" && data.value != null ? ` ${data.value}` : ""} · ${tr(`${data.count}장`, `${data.count} cards`)}`;
    case "hit_showdown": return `${roundText(data)} · ${tr("승자", "Winner")}: ${data.winners.join(" · ")} · ${showdownReason(data.reason)}`;
    case "hit_bust": return [data.eliminated?.length ? tr(`탈락 ${data.eliminated.join(" · ")}`, `Eliminated: ${data.eliminated.join(" · ")}`) : "", data.prison?.length ? tr(`감옥 확정 ${data.prison.join(" · ")}`, `Prison: ${data.prison.join(" · ")}`) : "", data.zero?.length && !data.eliminated?.length && !data.prison?.length ? tr(`칩 소진 ${data.zero.join(" · ")}`, `Out of chips: ${data.zero.join(" · ")}`) : ""].filter(Boolean).join(" · ");
    case "hit_tiebreak": return data.stage === "start" ? tr(`최하위 결정 연장전 · ${data.candidates.join(" · ")}`, `Last-place tiebreak · ${data.candidates.join(" · ")}`) : tr(`최하위 ${data.lowest?.join(" · ") ?? "–"} · 생존 ${data.safe?.join(" · ") ?? "–"}`, `Last place: ${data.lowest?.join(" · ") ?? "–"} · Safe: ${data.safe?.join(" · ") ?? "–"}`);
    case "hit_final": return tr("HIT, STAY 종료 · 최종 순위 확정", "HIT, STAY complete · Final standings confirmed");
  }
}

export function hitActionText(phase, action) {
  let data;
  try { data = typeof action === "string" ? JSON.parse(action) : action; } catch { data = action; }
  if (phase.includes("interest")) return interestText(typeof data === "string" ? data : data?.choice ?? data?.type);
  if (phase === "hit_reveal") return tr(`배부 순서 ${Number(typeof data === "object" ? data.index ?? data.card : data) + 1}번 카드 공개`, `Reveal dealt card ${Number(typeof data === "object" ? data.index ?? data.card : data) + 1}`);
  if (typeof data === "string") return actionNames[data] ?? data;
  if (!data || typeof data !== "object") return action;
  if (data.type === "raise") return tr(`레이즈 · 누적 ${data.total}칩 (기본 베팅 포함)`, `Raise · ${data.total} chips total (including ante)`);
  if (actionNames[data.type]) return actionNames[data.type];
  return typeof action === "string" ? action : JSON.stringify(action);
}

function handFor(state, player) {
  const game = state.hitGame;
  const perspective = state.hitPerspective ?? "public";
  const maySeePrivate = perspective === "operator" || perspective === player;
  const folded = (game?.folded ?? []).includes(player);
  const shown = !folded ? state.hitShowdown?.hands?.[player] : undefined;
  if (shown) return [...shown];
  const publicCards = state.hitPublicCards?.[player] ?? [];
  if (maySeePrivate && state.hitHands?.[player]) return [...state.hitHands[player], ...publicCards.slice(1)];
  const hidden = state.hitHiddenCounts?.[player] ?? (game?.hand_counts?.[player] ? Math.max(0, game.hand_counts[player] - publicCards.length) : 0);
  return [...Array(hidden).fill(null), ...publicCards];
}

function statusFor(state, player) {
  const final = state.hitFinal ?? state.result;
  if (final?.eliminated?.includes(player) || state.hitEliminated?.includes(player)) return tr("탈락", "Eliminated");
  if (final?.prison?.includes(player) || state.hitPrison?.includes(player)) return tr("감옥 매치", "Prison match");
  if (final?.living?.includes(player)) return tr("결승 진출", "Finalist");
  if (state.hitGame?.folded?.includes(player)) return tr("포기", "Folded");
  if (state.hitTurn?.player === player) return phaseNames[state.hitTurn.phase] ?? tr("행동 중", "Acting");
  if (state.hitGame?.stayed?.includes(player)) return "STAY";
  if (state.hitGame?.tiebreak && !state.hitGame.players.includes(player)) return tr("연장전 제외", "Not in the tiebreak");
  return tr("대기", "Waiting");
}

function phaseText(state) {
  if (state.hitFinal || state.result) return tr("최종 결과", "Final results");
  if (state.hitTurn) return `${state.hitTurn.player} · ${phaseNames[state.hitTurn.phase] ?? tr("행동 차례", "Action turn")}`;
  if (state.hitShowdown) return hitEventText("hit_showdown", state.hitShowdown);
  if (state.hitTiebreak?.stage === "start" && !state.hitGame?.tiebreak) return hitEventText("hit_tiebreak", state.hitTiebreak);
  if (state.hitGame?.round) return tr("카드 확인·공개 준비", "Preparing the hands");
  return tr("개막 대화·게임 준비", "Opening discussion and setup");
}

const seatPositions = {4: [[350, 62], [574, 178], [350, 365], [126, 178]], 5: [[350, 62], [580, 178], [490, 365], [210, 365], [120, 178]]};
const playerColors = ["#ee8a7c", "#72c5f2", "#e9d26c", "#b2d78e", "#c7a0e7"];
function HitCard({value, player, index, x, y}) {
  return <g data-card-owner={player} data-card-value={value ?? undefined} data-card-hidden={value == null ? "true" : undefined} className={`hit-playing-card${value == null ? " hit-card-back" : ""}`}>
    <title>{value == null ? tr(`${player} · 비공개 카드`, `${player} · Hidden card`) : tr(`${player} · 공개된 숫자 ${value}`, `${player} · Visible number ${value}`)}</title>
    <rect x={x} y={y} width="17" height="23" rx="1" />
    {value == null ? <path d={`M${x + 3} ${y + 4}l11 15m0 -15l-11 15M${x + 3} ${y + 11.5}h11`} /> : <text x={x + 8.5} y={y + 15}>{value}</text>}
  </g>;
}

export function HitStayScene({state, players, selected, onChoose}) {
  const game = state.hitGame;
  const roster = game?.seats ?? players ?? game?.players ?? [];
  const positions = seatPositions[roster.length] ?? seatPositions[5];
  const perspective = state.hitPerspective ?? "public";
  return <section className="hit-arena pixel-frame" aria-label={tr("HIT, STAY 게임홀", "HIT, STAY game hall")}>
    <svg viewBox="0 0 700 540" role="img" aria-label={tr("숫자 카드·공개 베팅·개인 손패 관전 테이블", "Number-card table with public betting and viewpoint-specific hands")}>
      <rect width="700" height="540" fill="#101b28" />
      <path d="M10 10H690V530H10Z" stroke="#425063" strokeWidth="6" fill="none" />
      {[[28, "#b3626c"], [230, "#4a987a"], [438, "#557eae"]].map(([x, color]) => <g key={x}><path d={`M${x} 30h180M${x} 35h180`} stroke={color} strokeWidth="4" /><path d={`M${x + 10} 42v58m25 -58v58m25 -58v58m25 -58v58m25 -58v58m25 -58v58`} stroke="#28384c" strokeWidth="5" /></g>)}
      <text x="350" y="30" className="hit-room-title">HIT, STAY</text>
      <ellipse cx="350" cy="281" rx="303" ry="163" fill="#412f35" stroke="#977b58" strokeWidth="8" />
      <ellipse cx="350" cy="270" rx="286" ry="146" fill="#183b3b" stroke="#50736b" strokeWidth="4" />
      <path d="M118 316Q350 427 582 316" fill="none" stroke="#718e6f" strokeWidth="2" strokeDasharray="6 5" />
      <g className="hit-limit-die" aria-label={tr(`한계 숫자 ${game?.limit ?? "미정"}`, `Limit ${game?.limit ?? "not rolled"}`)}>
        <path d="M330 180H370L384 194V222L370 236H330L316 222V194Z" fill="#d6c49e" stroke="#625b4c" strokeWidth="3" />
        <text x="350" y="202" className="hit-die-label">{tr("한계", "LIMIT")}</text><text x="350" y="226" className="hit-die-number">{game?.limit ?? "?"}</text>
      </g>
      <g className="hit-pot" aria-label={tr(`공동 팟 ${game?.pot ?? 0}칩`, `Pot: ${game?.pot ?? 0} chips`)}>
        {[[-21, "#df8274"], [0, "#75a9d6"], [21, "#d8bc67"]].map(([offset, color]) => <g key={offset}>{[0, 5, 10].map((level) => <rect key={level} x={340 + offset} y={278 - level} width="20" height="5" fill={color} stroke="#263846" strokeWidth="1" />)}</g>)}
        <text x="350" y="301" className="hit-pot-value">{tr("팟", "POT")} {game?.pot ?? 0}</text>
      </g>
      <g className="hit-deck" aria-label={tr(`남은 덱 ${game?.deck_remaining ?? 35}장`, `Deck: ${game?.deck_remaining ?? 35} cards remaining`)}>
        {[0, 1, 2].map((offset) => <rect key={offset} x={431 + offset * 2} y={253 - offset * 2} width="24" height="34" fill="#354b73" stroke="#b4b9b5" strokeWidth="1" />)}
        <text x="446" y="305">{tr("덱", "DECK")} {game?.deck_remaining ?? 35}</text>
      </g>
      <text x="350" y="328" className="hit-round-label">{game?.round ? roundText(game) : tr("개막 대화", "OPENING DISCUSSION")}</text>
      <text x="350" y="344" className="hit-ante-label">{tr("기본 베팅", "ANTE")} {game?.ante ?? "–"}</text>
      {roster.map((player, seat) => {
        const [x, y] = positions[seat] ?? [350, 365];
        const cards = handFor(state, player);
        const height = Math.max(99, 64 + Math.ceil(cards.length / 8) * 25);
        const folded = game?.folded?.includes(player);
        const inactive = state.hitPrison?.includes(player) || state.hitEliminated?.includes(player) || (game?.round && !game.players.includes(player));
        const acting = state.hitTurn?.player === player;
        const winner = state.hitShowdown?.winners?.includes(player);
        const status = statusFor(state, player);
        const label = `${player} · ${chipsText(game?.chips?.[player] ?? 0)} · ${status}`;
        return <g key={player} className={`hit-seat${acting ? " hit-acting" : ""}${folded ? " hit-folded" : ""}${inactive ? " hit-inactive" : ""}${winner ? " hit-winner" : ""}`} data-player={player} role="button" tabIndex="0" aria-label={label} aria-pressed={selected === player}
          onClick={() => onChoose?.(player)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onChoose?.(player); } }}>
          <title>{label}</title>
          <rect className="hit-seat-panel" x={x - 85} y={y} width="170" height={height} rx="3" />
          <rect x={x - 74} y={y + 11} width="10" height="10" fill={playerColors[seat % playerColors.length]} />
          <text x={x} y={y + 19} className="hit-player-name">{player}{winner ? " ★" : ""}</text>
          <text x={x} y={y + 37} className="hit-player-chips">{chipsText(game?.chips?.[player] ?? 0)} · {tr("베팅", "BET")} {game?.contributions?.[player] ?? 0}</text>
          {cards.map((value, index) => <HitCard key={index} player={player} value={value} index={index} x={x - 76 + index % 8 * 19} y={y + 47 + Math.floor(index / 8) * 25} />)}
          <text x={x} y={y + height - 8} className="hit-player-status">{status}</text>
        </g>;
      })}
      <text x="350" y="522" className="hit-view-label">{perspective === "operator" ? tr("운영자 시점 · 개인 카드 포함", "OPERATOR VIEW · PRIVATE CARDS INCLUDED") : perspective === "public" ? tr("공개 시점 · 비공개 카드 2장은 뒷면", "PUBLIC VIEW · TWO PRIVATE CARDS STAY FACE DOWN") : tr(`${perspective} 시점 · 내 카드만 전체 공개`, `${perspective} VIEW · ONLY YOUR HAND IS FULLY VISIBLE`)}</text>
    </svg>
    <p className="hit-scene-status" role="status">{phaseText(state)}</p>
  </section>;
}

const englishRules = "Start with 30 chips and exchange every Piece for one more chip. After the opening discussion, choose public or personal interest in private. A majority choosing public earns a Prize Token; every personal choice adds 10 chips to that player's stack.\n\nEach round uses a fresh 35-card deck: one 7, two 6s, three 5s, four 4s, five 3s, six 2s, seven 1s and seven −1s. Pay the ante, receive three cards and show one simultaneously. The die sets a limit from 5 to 12. The ante increases by one every ten rounds.\n\nBet first, then choose HIT to draw a public card or STAY to stop, then bet again. Bring your sum as close to the limit as possible without exceeding it. A −1 can recover an over-limit hand. Raise totals include the ante; the cap is the smallest total of contributed and remaining chips among players who have not folded. A fold stays out of the cap and gives up its contribution.\n\nAt showdown, the closest sum wins; more cards break equal sums. Exact ties, or all hands over the limit, split the pot. Only nonfolded hands are revealed. The first player out of chips is eliminated; later players out of chips go to prison. The last player goes straight to the final.\n\nSimulator policy: a short stack caps everyone's ante equally. Simultaneous first busts play chip-free card rounds, repeating only among tied lowest hands until one last-place player is determined.";
const koreanRules = "라운드의 한계 숫자를 넘지 않으면서 카드 합을 최대한 가깝게 맞춥니다. 초기 카드 3장 중 1장을 공개합니다. 1차 베팅 후 HIT로 공개 카드를 더 받거나 STAY로 멈춘 뒤, 2차 베팅을 합니다. 베팅은 가장 적은 칩의 한도를 넘을 수 없고 레이즈 누적액에는 기본 베팅이 포함됩니다. 합계가 같으면 카드 장수가 많은 쪽이 이깁니다. 포기한 참가자의 비공개 카드는 공개하지 않습니다.";

export function HitStayStage({state, players}) {
  const game = state.hitGame;
  const roster = players ?? game?.seats ?? game?.players ?? [];
  const result = state.hitFinal ?? state.result;
  const showdown = state.hitShowdown;
  const rules = state.feed?.findLast((event) => event.msg_type === "rules");
  return <div className="hit-stage"><h2>HIT, STAY</h2>
    {!game ? <div className="hit-rules"><h3>{tr("게임 규칙", "Game rules")}</h3><p>{en ? englishRules : rules?.content ?? koreanRules}</p></div> : <>
      <p className="hit-phase">{phaseText(state)}</p>
      {game.round && <div className="hit-round-summary"><strong>{roundText(game)}</strong><span>{tr("한계 숫자", "Limit")} <b>{game.limit}</b></span><span>{tr("기본 베팅", "Ante")} {game.ante}</span><span>{tr("팟", "Pot")} {game.pot}</span><span>{tr("남은 덱", "Deck left")} {game.deck_remaining}</span></div>}
      {state.hitTurn && <p className="hit-bet-cap">{tr("현재 누적 베팅", "Current bet total")}: {state.hitTurn.current_total ?? 0} · {tr("최대 누적 베팅", "Maximum total bet")}: {state.hitTurn.cap ?? "–"}<small>{tr("레이즈 누적액은 기본 베팅을 포함합니다.", "Raise totals include the ante.")}</small></p>}
      {result ? <Table caption={tr("최종 순위", "Final standings")} headers={tr(["순위", "참가자", "결과", "칩"], ["Rank", "Player", "Result", "Chips"])} rows={(result.ranking ?? []).map((player, index) => [index + 1, player, statusFor(state, player), result.chips?.[player] ?? result.scores?.[player] ?? game.chips?.[player] ?? "–"])} /> :
        <Table caption={tr("참가자 현황", "Player status")} headers={tr(["참가자", "칩", "누적 베팅", "상태"], ["Player", "Chips", "Total bet", "Status"])} rows={roster.map((player) => [player, game.chips?.[player] ?? 0, game.contributions?.[player] ?? 0, statusFor(state, player)])} />}
      {state.hitLastBet && <p className="hit-last-action">{hitEventText("hit_bet", state.hitLastBet)}</p>}
      {state.hitLastCard && <p className="hit-last-action">{hitEventText("hit_card", state.hitLastCard)}</p>}
      {showdown && <section className="hit-showdown" aria-label={tr("카드 비교 결과", "Showdown result")}><h3>{tr("승자", "Winner")}: {showdown.winners.join(" · ")}</h3><p>{showdownReason(showdown.reason)}</p><p>{Object.entries(showdown.payouts).map(([player, amount]) => `${player} +${chipsText(amount)}`).join(" · ")}</p></section>}
      {state.hitInterest && <details className="hit-interest"><summary>{tr("게임 전 이익 선택", "Opening interest choices")}</summary><p>{hitEventText("hit_interest", state.hitInterest)}</p><Table caption={tr("선택 공개", "Revealed choices")} headers={tr(["참가자", "선택"], ["Player", "Choice"])} rows={Object.entries(state.hitInterest.choices).map(([player, choice]) => [player, interestText(choice)])} /></details>}
      {state.hitTiebreak && <p className="hit-tiebreak">{hitEventText("hit_tiebreak", state.hitTiebreak)}</p>}
      <p className="muted">{tr("초기 카드 2장은 비공개 · 추가 HIT 카드는 공개 · 포기한 손패는 비공개 유지", "Two initial cards stay private · HIT cards are public · Folded hands stay private")}</p>
    </>}
  </div>;
}

export function HitStayInformation({state, replay}) {
  const [tab, setTab] = useState("rounds");
  const results = state.hitResults ?? [];
  const records = (state.feed ?? []).filter((event) => ["hit_interest", "hit_bet", "hit_card", "hit_bust", "hit_tiebreak"].includes(event.msg_type));
  return <aside className="caption hit-information" aria-label={tr("HIT, STAY 결과와 기록", "HIT, STAY results and records")}>
    <TabList role="tablist" aria-label={tr("HIT, STAY 정보 종류", "HIT, STAY information tabs")} value={tab} onChange={setTab} size="sm" hasDivider>
      <Tab id="hit-rounds" value="rounds" label={tr("라운드 정산", "Round results")} panelId="hit-records-panel" />
      <Tab id="hit-bets" value="bets" label={tr("베팅·카드 기록", "Bets and cards")} panelId="hit-records-panel" />
    </TabList>
    <div id="hit-records-panel" role="tabpanel" aria-labelledby={`hit-${tab}`}>
      {tab === "rounds" ? results.length ? results.map((result, index) => <section className="hit-round-result" key={`${result.step}-${index}`}><h3><button type="button" onClick={() => replay.seek(result.step)}>{roundText(result)} · {result.winners.join(" · ")}</button></h3>
        <p>{showdownReason(result.reason)} · {tr("팟", "Pot")} {result.pot}</p>
        <Table caption={tr("공개된 손패 비교", "Revealed hands")} headers={tr(["참가자", "합계", "장수", "수령 칩"], ["Player", "Sum", "Cards", "Payout"])} rows={Object.keys(result.chips).map((player) => [player, result.folded.includes(player) ? tr("포기", "Folded") : result.sums[player] ?? "–", result.folded.includes(player) ? "–" : result.counts[player] ?? "–", result.payouts[player] ?? 0])} />
      </section>) : <p className="muted">{tr("아직 정산한 라운드가 없어요.", "No rounds have settled yet.")}</p> : records.length ? <ol className="hit-bet-log">{records.map((event) => <li key={event.step}><button type="button" onClick={() => replay.seek(event.step)}>{event.step} · {event.text ?? hitEventText(event.msg_type, event.data)}</button></li>).reverse()}</ol> : <p className="muted">{tr("아직 베팅·카드 기록이 없어요.", "No bets or cards have been recorded yet.")}</p>}
    </div>
  </aside>;
}
