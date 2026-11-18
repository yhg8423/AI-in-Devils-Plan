import React, {useId, useLayoutEffect, useRef, useState} from "react";
import {Selector} from "@astryxdesign/core/Selector";
import {Tab, TabList} from "@astryxdesign/core/TabList";
import {setHeight, setWidth} from "./floor.js";
import {en, tr} from "./locale.js";
import {Table} from "./records.jsx";
import {scoreText} from "./replay.js";
import {ArenaSpeech, Sprite, whisperRecipients} from "./scene.jsx";
import {drawPiggySet, piggySeats} from "./piggy-floor.js";
import {rulesSummary} from "./rule-summaries.js";
import "./piggy-bank.css";

export const pigColorLabel = (color) => color === "black" ? tr("흑", "Black") : tr("백", "White");
const bankLabel = (bank) => bank == null ? "–" : tr(`${bank}번`, `#${bank}`);
const coinText = (coins) => coins ? tr(`흑 ${coins.black ?? "?"} · 백 ${coins.white ?? "?"}`, `Black ${coins.black ?? "?"} · White ${coins.white ?? "?"}`) : tr("미개봉", "Unopened");
function knownCoins(state, bank, owner) {
  const memory = state.pigMemories?.[owner];
  if (["model", "dynamic"].includes(memory?.mode) && memory.banks.includes(bank)) return memory.counts[bank] ?? {black: null, white: null};
  return (owner ? memory?.counts[bank] : state.pigContents?.[bank]) ?? state.pigKnown?.[bank];
}
const position = (x, y) => ({left: `${x / setWidth * 100}%`, top: `${y / setHeight * 100}%`});

function memoryOwner(state, selected) {
  const owner = state.pigPerspective === "operator" ? selected : state.pigPerspective;
  return owner && owner !== "public" && (state.pigMemories?.[owner] || state.pigSummaries?.[owner] ||
    (hasMemorySlots(state) || hasFreeMemory(state)) && state.pigOrder?.includes(owner)) ? owner : null;
}

function hasMemorySlots(state) {
  return state.feed.some((event) => event.msg_type === "rules" &&
    ["\n\n5. 기억 슬롯\n", "\n\n5. 변경 가능한 기억 슬롯\n"].some((heading) =>
      (typeof event.data === "string" ? event.data : event.content)?.includes(heading)));
}

function hasDynamicMemory(state) {
  return state.feed.some((event) => event.msg_type === "rules" &&
    (typeof event.data === "string" ? event.data : event.content)?.includes("\n\n5. 변경 가능한 기억 슬롯\n"));
}

function hasModelMemory(state) {
  return state.feed.some((event) => event.msg_type === "rules" &&
    (typeof event.data === "string" ? event.data : event.content)?.includes("\n\n6. 기억 직접 갱신\n"));
}

function hasFreeMemory(state) {
  return state.feed.some((event) => event.msg_type === "rules" &&
    (typeof event.data === "string" ? event.data : event.content)?.includes("\n\n5. 비공개 기억 요약\n"));
}

function hasSilentRules(state) {
  return state.feed.some((event) => event.msg_type === "rules" &&
    (typeof event.data === "string" ? event.data : event.content)?.includes("\n\n6. 대화 없는 진행\n"));
}

export function pigActionText(phase, action) {
  let data;
  try { data = JSON.parse(action); } catch { data = action; }
  if (phase === "pig_count") return tr(`${action}개 선언`, `Declare ${action} coins`);
  if (phase === "pig_memory_select" && Array.isArray(data)) return tr(`기억할 저금통 선택 · ${data.map(bankLabel).join(" · ")}`, `Memory banks selected · ${data.map(bankLabel).join(" · ")}`);
  if (phase === "pig_memory_update") return tr("기억 갱신 · ", "Update memory · ") + (action || tr("기억 비움", "Memory cleared"));
  if (phase === "pig_doubt") return action === "doubt" ? tr("의심 선언", "Call doubt") : tr("의심하지 않음", "Do not doubt");
  if (phase === "pig_reset_vote") return action === "reset" ? tr("리셋 버튼 누름", "Press reset") : tr("리셋 보류", "Wait");
  if (phase === "pig_deposit" && data && typeof data === "object") {
    return tr(`흑 ${data.black} · 백 ${data.white}개 넣기 → ${data.to}`, `Deposit ${data.black} black and ${data.white} white → ${data.to}`);
  }
  if (phase === "pig_challenge") return action === "pass" ? tr("전체 암기 도전 보류", "Skip full-memory challenge") : tr("전체 저금통 암기 도전", "Full-memory challenge");
  if (phase === "pig_talk" && data && typeof data === "object") {
    if (data.type === "pass") return tr("대화 패스", "Pass conversation");
    if (data.type === "speak") {
      const recipients = Array.isArray(data.to) ? data.to.join(", ") : data.to;
      return `${data.channel === "whisper" ? tr(`귓속말 → ${recipients}`, `Whisper → ${recipients}`) : tr("전체 발언", "Public speech")} · ${data.text}`;
    }
  }
  return typeof data === "object" ? JSON.stringify(data) : String(action);
}

export function pigEventText(type, data) {
  switch (type) {
    case "pig_setup": return tr(`추첨 순서 ${data.order.join(" → ")} · 저금통 5개`, `Drawn order ${data.order.join(" → ")} · Five banks`);
    case "pig_turn": return tr(`${data.turn}턴 · ${data.player} 동전 넣기 · 다음 선언 ${pigColorLabel(data.color)}`, `Turn ${data.turn} · ${data.player} deposits · Next claim: ${pigColorLabel(data.color)}`);
    case "pig_deposit": return tr(`${data.player} → ${data.to} · ${bankLabel(data.bank)}에 흑 ${data.black}, 백 ${data.white}개 넣음`, `${data.player} → ${data.to} · ${bankLabel(data.bank)}: added ${data.black} black, ${data.white} white`);
    case "pig_claim": return tr(`${data.player} · ${bankLabel(data.bank)} ${pigColorLabel(data.color)} ${data.count}개 선언`, `${data.player} · ${bankLabel(data.bank)}: claims ${data.count} ${pigColorLabel(data.color)} coins`);
    case "pig_pass": return tr(`${data.player}의 선언 통과 · 의심 없음`, `${data.player}’s claim passes without doubt`);
    case "pig_doubt": return tr(`${data.challenger} 의심 ${data.correct ? "성공" : "실패"} · ${bankLabel(data.bank)} 실제 ${coinText(data.actual)}`, `${data.challenger}’s doubt ${data.correct ? "succeeds" : "fails"} · ${bankLabel(data.bank)} revealed: ${coinText(data.actual)}`);
    case "pig_replace": return tr(`${data.player} · ${bankLabel(data.old_bank)} 제외 → 새 ${bankLabel(data.bank)}`, `${data.player} · Retire ${bankLabel(data.old_bank)} → New bank ${bankLabel(data.bank)}`);
    case "pig_reset_vote": {
      const prefix = data.simultaneous ? tr("동시 제출 · ", "Simultaneous submission · ") : "";
      return prefix + (data.voters.length > 3 ?
        tr(`${data.player} 리셋 요청 · ${data.voters.length}명 요청 · 기준 3명`, `${data.player} requests reset · ${data.voters.length} requests · 3 required`) :
        tr(`${data.player} 리셋 요청 · ${data.voters.length} / 3명`, `${data.player} requests reset · ${data.voters.length} of 3`));
    }
    case "pig_challenge": return tr(`${data.player} 전체 암기 ${data.correct ? "성공 · +3점" : "실패 · −2점"}`, `${data.player}’s full-memory challenge ${data.correct ? "succeeds · +3 VP" : "fails · −2 VP"}`);
    case "pig_reset": return tr("전체 저금통 리셋 · 승점 유지", "All banks reset · Scores retained");
    case "pig_contents": return tr("운영자 전용 · 저금통 내부", "Operator only · Bank contents");
    case "pig_memory_selection": return tr(`기억 슬롯 ${data.banks.map(bankLabel).join(" · ")}`, `Memory slots: ${data.banks.map(bankLabel).join(" · ")}`);
    case "pig_recall": return data.mode === "summary" ? tr("기억 요약 · ", "Memory summary · ") + (data.text || tr("비움", "Cleared")) :
      (["model", "dynamic"].includes(data.mode) ? tr("기억 추정 · ", "Memory estimates · ") : "") +
        Object.entries(data.banks).map(([bank, coins]) => `${bankLabel(bank)} · ${coinText(coins)}`).join(" / ");
    case "pig_discussion": return data.stage === "opening" ? tr("게임 시작 전 대화", "Opening discussion") : tr(`${data.turn}턴 행동 전 대화`, `Discussion before turn ${data.turn}`);
    case "pig_discussion_end": return tr("대화 종료", "Discussion complete");
    case "pig_preparation": return tr("비공개 전략 준비", "Private strategy preparation");
    case "pig_preparation_end": return tr("전략 준비 완료", "Strategy preparation complete");
  }
}

export function applyPigEvent(state, type, data, event = {}) {
  if (type === "action" && data.phase === "pig_doubt" && data.action === "doubt" &&
      state.pigClaim && !state.pigDoubtCue) {
    const {player, bank, color, count} = state.pigClaim;
    state.pigDoubtCue = {challenger: event.agent_name, player, bank, color, claimed: count, step: event.step};
  }
  if (type === "action" && data.phase === "pig_challenge") {
    state.pigChallengeCue = data.action === "pass" ? null : {player: event.agent_name, step: event.step};
    if (state.pigChallengeCue) {
      state.pigDoubtCue = null;
      state.pigVerdict = null;
    }
  }
  if (!type.startsWith("pig_")) return;
  if (data.scores) state.pigScores = {...data.scores};
  if (data.lower) state.pigLower = {...data.lower};
  if (data.upper) state.pigUpper = {...data.upper};
  if (data.order) state.pigOrder = data.order;
  switch (type) {
    case "pig_setup":
    case "pig_reset": {
      state.pigSetup ??= data;
      state.pigVoters = [];
      state.pigTurn = null;
      state.pigClaim = null;
      state.pigVerdict = null;
      state.pigDoubtCue = null;
      state.pigChallengeCue = null;
      state.pigDeposit = null;
      state.pigContents = {};
      state.pigMemoryReset = data.reset ?? 0;
      state.pigMemories = {};
      if (type === "pig_setup") state.pigSummaries = {};
      else state.pigSummaries ??= {};
      state.pigActive = data.next_player ?? Object.keys(data.upper).find((player) => data.upper[player] != null);
      state.pigKnown = Object.fromEntries([...Object.values(data.lower), ...Object.values(data.upper)]
        .filter((bank) => bank != null).map((bank) => [bank, {black: 1, white: 1}]));
      break;
    }
    case "pig_turn":
      state.pigTurn = data;
      state.pigActive = data.player;
      state.pigClaim = null;
      state.pigVerdict = null;
      state.pigDoubtCue = null;
      state.pigChallengeCue = null;
      break;
    case "pig_deposit":
      state.pigDeposit = data;
      state.pigActive = data.to;
      state.pigClaim = null;
      state.pigDoubtCue = null;
      state.pigChallengeCue = null;
      delete state.pigKnown?.[data.bank];
      delete state.pigContents?.[data.bank];
      for (const memory of Object.values(state.pigMemories ?? {})) {
        if (!["model", "dynamic"].includes(memory.mode)) delete memory.counts[data.bank];
      }
      break;
    case "pig_claim": state.pigClaim = data; state.pigActive = data.player; break;
    case "pig_doubt":
      state.pigKnown ??= {};
      state.pigKnown[data.bank] = data.actual;
      state.pigVerdict = {type, data};
      state.pigDoubtCue = {...data, step: event.step};
      break;
    case "pig_replace":
      delete state.pigKnown?.[data.old_bank];
      delete state.pigContents?.[data.old_bank];
      state.pigKnown[data.bank] = {black: 1, white: 1};
      state.pigClaim = null;
      state.pigActive = data.next_player ?? data.player;
      for (const memory of Object.values(state.pigMemories ?? {})) {
        if (memory.banks.includes(data.old_bank)) {
          memory.banks = memory.banks.map((bank) => bank === data.old_bank ? data.bank : bank);
          delete memory.counts[data.old_bank];
          memory.counts[data.bank] = {black: 1, white: 1};
        }
      }
      break;
    case "pig_reset_vote": state.pigVoters = data.voters; break;
    case "pig_challenge":
      state.pigKnown = {...state.pigKnown, ...data.actual};
      state.pigVerdict = {type, data};
      state.pigDoubtCue = null;
      state.pigChallengeCue = {player: data.player, correct: data.correct, step: event.step};
      break;
    case "pig_contents": state.pigContents = {...data.banks}; break;
    case "pig_memory_selection":
      if (data.reset === state.pigMemoryReset) {
        state.pigMemories[event.agent_name] = {reset: data.reset, banks: data.banks.slice(), counts: {},
          mode: hasModelMemory(state) ? "model" : undefined};
      }
      break;
    case "pig_recall": {
      if (data.mode === "dynamic") {
        if (data.reset === state.pigMemoryReset) {
          state.pigMemories[event.agent_name] = {reset: data.reset, mode: "dynamic", updated_turn: data.updated_turn,
            banks: Object.keys(data.banks).map(Number),
            counts: Object.fromEntries(Object.entries(data.banks).map(([bank, coins]) => [bank, {...coins}]))};
        }
        break;
      }
      if (data.mode === "summary") {
        if (data.reset === state.pigMemoryReset) {
          state.pigSummaries[event.agent_name] = {reset: data.reset, text: data.text, limit: data.limit,
            updated_turn: data.updated_turn};
        }
        break;
      }
      const memory = state.pigMemories?.[event.agent_name];
      if (memory && data.reset === state.pigMemoryReset && memory.reset === data.reset) {
        memory.counts = Object.fromEntries(memory.banks.filter((bank) => data.banks[bank])
          .map((bank) => [bank, {...data.banks[bank]}]));
        memory.mode = data.mode;
        memory.updated_turn = data.updated_turn;
      }
      break;
    }
  }
  if (!["pig_contents", "pig_recall"].includes(type)) state.pigLast = {type, data};
}

function PigShell() {
  return <>
      <path fill="#55353c" d="M6 4h3V1h5v3h9v3h4v4h4v7h-5v3h-4v3h-5v-3h-6v3H6v-5H3v-3H0V9h3V6h3z" />
      <path fill="#d48c95" d="M6 6h5V3h2v3h10v3h3v4h3v3h-5v3H7v-3H4V9h2z" />
      <path fill="#efb3ab" d="M8 7h13v3H7v4H5v-4h3zM25 13h4v3h-4z" />
      <path fill="#a35f74" d="M8 17h15v2H8zM7 20h3v2H7zM19 20h3v2h-3z" />
      <path fill="#241e2c" d="M21 9h2v2h-2zM12 5h7v2h-7zM27 13h1v1h-1z" />
  </>;
}

function PigIcon({bank, coins, compact = false, opened = false, estimate = false}) {
  const clip = useId();
  return <span className={`pig-icon${compact ? " compact" : ""}${opened ? " opened" : ""}`} role="img"
    aria-label={`${bankLabel(bank)} · ${opened ? tr("개봉 · ", "Opened · ") : estimate ? tr("기억 추정 · ", "Memory estimate · ") : ""}${bank == null ? tr("빈칸", "Empty") : coinText(coins)}`}>
    <svg viewBox="-4 -3 40 29" aria-hidden="true" shapeRendering="crispEdges" data-empty={bank == null || undefined}>
      {opened ? <>
        <defs>
          <clipPath id={`${clip}-left`}><path d="M0 0H16V7L13 10L17 13L13 16L15 24H0z" /></clipPath>
          <clipPath id={`${clip}-right`}><path d="M16 0H32V24H15L13 16L17 13L13 10L16 7z" /></clipPath>
        </defs>
        <g className="pig-shell-left" clipPath={`url(#${clip}-left)`}><PigShell /></g>
        <g className="pig-shell-right" clipPath={`url(#${clip}-right)`}><PigShell /></g>
        <g className="pig-spilled-coins">
          <path fill="#101721" stroke="#a8b6c0" strokeWidth=".5" d="M11 10h5v3h-5zM12 15h5v3h-5z" />
          <path fill="#e8e8da" stroke="#c7c8b9" strokeWidth=".5" d="M17 9h5v3h-5zM17 14h5v3h-5z" />
        </g>
      </> : <PigShell />}
    </svg>
    <strong>{bank == null ? "–" : bankLabel(bank)}</strong>
  </span>;
}

function Coins({coins, estimate = false}) {
  return coins ? <span className="pig-coins" role={estimate ? "img" : undefined}
    aria-label={estimate ? tr(`기억 추정 · ${coinText(coins)}`, `Memory estimate · ${coinText(coins)}`) : undefined}>
    <span data-uncertain={coins.black == null || undefined}><i data-color="black" aria-hidden="true" />{coins.black ?? "?"}</span>
    <span data-uncertain={coins.white == null || undefined}><i data-color="white" aria-hidden="true" />{coins.white ?? "?"}</span></span> :
    <span className="pig-hidden">{tr("미개봉", "Unopened")}</span>;
}

function PiggyMemorySlots({state, selected}) {
  const owner = memoryOwner(state, selected);
  if (!owner) return state.pigPerspective === "operator" && hasMemorySlots(state) ?
    <p className="pig-memory-help">{tr("참가자를 선택하면 그 참가자의 기억 슬롯 3개를 볼 수 있습니다.", "Select a player to view that player’s three memory slots.")}</p> : null;
  const memory = state.pigMemories?.[owner];
  return <section className="pig-memory-summary" data-owner={owner} data-reset={state.pigMemoryReset} data-mode={memory?.mode}
    aria-label={tr(`${owner} 비공개 기억 슬롯`, `${owner}’s private memory slots`)}>
    <h3>{tr(`${owner} 기억 슬롯`, `${owner}’s memory slots`)} <small>{memory?.banks.length ?? 0} / 3</small></h3>
    {["model", "dynamic"].includes(memory?.mode) && <p className="pig-memory-estimate-note">{tr("본인이 갱신한 추정값이며, 실제 개수로 자동 보정하지 않습니다.", "These are the player’s own estimates; they are not automatically corrected to the actual counts.")}
      {memory.updated_turn != null && <small>{tr(`마지막 갱신 · ${memory.updated_turn}턴`, `Last updated · Turn ${memory.updated_turn}`)}</small>}</p>}
    {memory ? <div className="pig-memory-banks">{memory.banks.map((bank, index) =>
      <div className="pig-memory-bank" key={bank} data-bank={bank}>
        <span className="pig-memory-slot-label">{tr(`슬롯 ${index + 1}`, `Slot ${index + 1}`)}</span>
        <PigIcon bank={bank} coins={knownCoins(state, bank, owner)} compact estimate={["model", "dynamic"].includes(memory.mode)} />
        <Coins coins={knownCoins(state, bank, owner)} estimate={["model", "dynamic"].includes(memory.mode)} />
      </div>)}</div> : <p className="muted">{hasDynamicMemory(state) ? tr("기억 갱신 대기 중입니다.", "Waiting for the private memory update.") :
        tr("기억할 저금통 선택 대기 중입니다.", "Waiting for the memory-bank selection.")}</p>}
  </section>;
}

function PiggyFreeMemory({state, selected}) {
  const owner = memoryOwner(state, selected);
  if (!owner) return state.pigPerspective === "operator" ?
    <p className="pig-memory-help">{tr("참가자를 선택하면 그 참가자의 비공개 기억 요약을 볼 수 있습니다.", "Select a player to view that player’s private memory summary.")}</p> : null;
  const memory = state.pigSummaries?.[owner];
  const text = memory?.text ?? "";
  return <section className="pig-free-memory" data-owner={owner} data-reset={memory?.reset} data-mode="summary"
    aria-label={tr(`${owner} 비공개 기억 요약`, `${owner}’s private memory summary`)}>
    <h3>{tr(`${owner} 기억 요약`, `${owner}’s memory summary`)}</h3>
    <p className="pig-memory-estimate-note">{tr("본인이 남긴 기억입니다. 빠뜨리거나 잘못 기억할 수 있으며, 실제 정보로 자동 보정하지 않습니다.",
      "This is the player’s own memory. It may omit facts or contain mistakes, and is not automatically corrected.")}</p>
    <p className="pig-memory-text" data-empty={memory && text === "" || undefined} lang={/[가-힣]/.test(text) ? "ko" : undefined}>
      {text || (memory ? tr("기억 내용을 비웠습니다.", "Memory has been cleared.") : tr("아직 작성한 기억 요약이 없습니다.", "No memory summary has been written yet."))}</p>
    <p className="pig-memory-meta"><span className="pig-memory-length">{Array.from(text).length} / {memory?.limit ?? 300}</span>
      {memory && <span>{tr(`마지막 갱신 · ${memory.updated_turn}턴`, `Last updated · Turn ${memory.updated_turn}`)}</span>}</p>
    {memory && memory.reset !== state.pigMemoryReset && <p className="pig-memory-help">{tr("리셋 전 요약을 보관 중입니다. 다음 기억 갱신 때 수정합니다.", "The pre-reset summary is retained until the next memory update.")}</p>}
  </section>;
}

export function PiggyScene({players, state, frame, selected, onChoose}) {
  const canvas = useRef(null);
  useLayoutEffect(() => drawPiggySet(canvas.current), []);
  const order = state.pigOrder ?? players;
  const active = state.pigActive;
  const owner = memoryOwner(state, selected);
  const memory = state.pigMemories?.[owner];
  const cue = state.pigDoubtCue;
  const challenge = state.pigChallengeCue;
  const deposit = state.pigDeposit;
  const from = deposit && order.indexOf(deposit.player);
  const to = deposit && order.indexOf(deposit.to);
  const speech = state.feed.findLast(({msg_type, step}) => frame - step <= 7 && ["public", "whisper"].includes(msg_type));
  const recipients = whisperRecipients(speech, players);
  return <div className="arena pig-arena">
    <section className="stage-window pixel-frame match-set pig-set" aria-label={tr("돼지 저금통 감옥 매치 세트장", "Piggy Bank prison match arena")}>
      <div className="floor">
        <canvas ref={canvas} className="set-map" width={setWidth} height={setHeight} aria-hidden="true" />
        {deposit && from >= 0 && to >= 0 && <svg className="pig-route" viewBox={`0 0 ${setWidth} ${setHeight}`} aria-hidden="true">
          <defs><marker id="pig-pass-arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0 0L6 3L0 6z" fill="#ebbb76" /></marker></defs>
          <path d={`M${piggySeats[from]} 290V309H${piggySeats[to]}V290`} markerEnd="url(#pig-pass-arrow)" />
        </svg>}
        {order.map((player, index) => <React.Fragment key={player}>
          {cue?.challenger === player && <div className="pig-action-bubble pig-doubt-bubble" style={position(piggySeats[index], 83)}
            data-player={player} data-correct={cue.correct} key={`${player}-doubt-${cue.step}`} role="status">
            <strong>{tr("의심!", "Doubt!")}</strong>
            {cue.correct != null && <span className="pig-action-badge pig-doubt-badge" data-correct={cue.correct}>
              {cue.correct ? tr("성공 +1", "SUCCESS +1") : tr("실패 −1", "FAIL −1")}</span>}
          </div>}
          {challenge?.player === player && <div className="pig-action-bubble pig-challenge-bubble" style={position(piggySeats[index], 83)}
            data-player={player} data-correct={challenge.correct} key={`${player}-challenge-${challenge.step}`} role="status">
            <strong>{tr("도전!", "Challenge!")}</strong>
            {challenge.correct != null && <span className="pig-action-badge pig-challenge-badge" data-correct={challenge.correct}>
              {challenge.correct ? tr("성공 +3", "SUCCESS +3") : tr("실패 −2", "FAIL −2")}</span>}
          </div>}
          <button type="button" className={`token pig-seat${active === player ? " acting" : ""}`} style={position(piggySeats[index], 134)}
            aria-label={tr(`${player} · 승점 ${state.pigScores?.[player] ?? 0}`, `${player} · ${state.pigScores?.[player] ?? 0} VP`)} aria-pressed={selected === player}
            data-doubt-caller={cue?.challenger === player || undefined}
            data-challenge-caller={challenge?.player === player || undefined}
            data-status={state.result?.eliminated.includes(player) ? "탈락" : undefined} data-speaking={speech?.agent_name === player || undefined}
            onClick={() => onChoose(player)}><Sprite player={player} /><span>{player} · {state.pigScores?.[player] ?? 0}</span></button>
          <div className="pig-station" style={position(piggySeats[index], 153)} data-active={active === player || undefined}>
            {["upper", "lower"].map((tier) => {
              const bank = (tier === "upper" ? state.pigUpper : state.pigLower)?.[player];
              const bankCue = tier === "upper" && cue?.player === player ? cue : null;
              const opened = bankCue?.actual != null && bank === bankCue.bank;
              const retired = bankCue?.actual != null && bank !== bankCue.bank;
              const estimate = !opened && ["model", "dynamic"].includes(memory?.mode) && memory.banks.includes(bank);
              return <div className="pig-tier" key={tier} data-bank={bank} data-suspected={bankCue && !retired || undefined}
                data-retired-reveal={retired || undefined} aria-label={`${player} · ${tier === "upper" ? tr("위칸", "Upper tier") : tr("아래칸", "Lower tier")}`}>
                <span className="pig-tier-label">{tier === "upper" ? tr("위", "UP") : tr("아래", "LOW")}</span>
                {retired && <div className="pig-opened-bank pig-retired-bank" data-bank={bankCue.bank} data-correct={bankCue.correct}
                  aria-label={tr(`직전 개봉 ${bankLabel(bankCue.bank)} · ${coinText(bankCue.actual)}`, `Previously opened ${bankLabel(bankCue.bank)} · ${coinText(bankCue.actual)}`)}>
                  <small>{tr("직전 개봉", "OPENED")}</small><PigIcon bank={bankCue.bank} coins={bankCue.actual} compact opened />
                  <Coins coins={bankCue.actual} />
                </div>}
                <div className={`pig-physical-bank${opened ? " pig-opened-bank" : ""}`} data-bank={bank} data-correct={opened ? bankCue.correct : undefined}>
                  {retired && bank != null && <small>{tr("현재 저금통", "CURRENT")}</small>}
                  <PigIcon bank={bank} coins={opened ? bankCue.actual : knownCoins(state, bank, owner)} compact opened={opened} estimate={estimate} />
                  {bank != null && <Coins coins={opened ? bankCue.actual : knownCoins(state, bank, owner)} estimate={estimate} />}
                </div>
              </div>;
            })}
            <span className="pig-reset-button" data-voted={state.pigVoters?.includes(player) || undefined} role="img"
              aria-label={state.pigVoters?.includes(player) ? tr(`${player} 리셋 요청함`, `${player} requested reset`) : tr(`${player} 리셋 대기`, `${player} has not requested reset`)}>
              <i aria-hidden="true" />RESET</span>
          </div>
        </React.Fragment>)}
        <span className="pig-floor-caption">{state.pigClaim ? pigEventText("pig_claim", state.pigClaim) : state.pigTurn ?
          tr(`다음 선언 · ${pigColorLabel(state.pigTurn.color)} 동전`, `Next claim · ${pigColorLabel(state.pigTurn.color)} coins`) : tr("기억하고, 의심하세요", "Remember. Then call doubt.")}</span>
      </div>
    </section>
    {!hasSilentRules(state) && <ArenaSpeech speech={speech} recipients={recipients} />}
  </div>;
}

function PiggyChallengeResult({data}) {
  if (!data.guesses || !data.actual) return null;
  const banks = Object.keys(data.actual).sort((left, right) => Number(left) - Number(right));
  const matches = (bank) => data.guesses[bank]?.black === data.actual[bank].black &&
    data.guesses[bank]?.white === data.actual[bank].white;
  const correct = banks.filter(matches).length;
  return <section className="pig-challenge-result" aria-label={tr("저금통별 도전 결과", "Bank-by-bank challenge results")}>
    <p><strong>{tr(`${data.player} · ${banks.length}개 저금통 중 ${correct}개 정답`,
      `${data.player} · ${correct} of ${banks.length} banks correct`)}</strong></p>
    <Table caption={tr("제출 개수와 실제 개수", "Submitted and actual counts")}
      headers={tr(["저금통", "제출", "실제", "판정"], ["Bank", "Submitted", "Actual", "Result"])}
      rows={banks.map((bank) => [<span className="pig-challenge-bank" data-bank={bank} data-correct={matches(bank)}>{bankLabel(bank)}</span>,
        data.guesses[bank] ? coinText(data.guesses[bank]) : "–", coinText(data.actual[bank]),
        <span className="pig-challenge-match" data-correct={matches(bank)}>{matches(bank) ? tr("정답", "Correct") : tr("오답", "Incorrect")}</span>])} />
  </section>;
}

export function PiggyStage({state, players, selected, onChoose}) {
  const {pigTurn: turn, pigClaim: claim, pigScores: scores = {}, pigLast: latest, pigVerdict: verdict, result} = state;
  const rules = state.feed.find((event) => event.msg_type === "rules");
  const rawRules = rules ? typeof rules.data === "string" ? rules.data : rules.content : "";
  const turnLimit = result?.turn_limit ?? (rawRules.includes("\n\n100턴 상한\n") ? 100 : null);
  const [rulesTitle, ...rulesBody] = rawRules.split("\n");
  const explanation = en ? rulesSummary(rulesTitle, rulesBody.join("\n")) ?? rules?.text : rawRules;
  const order = result?.ranking ?? [...(state.pigOrder ?? players)].sort((a, b) => (scores[b] ?? 0) - (scores[a] ?? 0));
  if (!state.pigSetup) return <div className="pig-stage">
    <h2>{rules ? tr("게임 규칙", "Game rules") : tr("게임 시작 전", "Before the game")}</h2>
    {rules ? <><p className="choice-rules">{explanation}</p>{en && <details className="stage-details"><summary>Original rules (Korean)</summary><p className="choice-rules" lang="ko">{rawRules}</p></details>}</> :
      <p className="muted">{tr("게임 규칙 공개 대기", "Waiting for the game rules")}</p>}
  </div>;
  if (result) return <div className="pig-stage">
    <h2>{tr("최종 결과", "Final results")}</h2>
    {result.end_reason === "turn_limit" && <p className="muted">{tr(`${turnLimit}턴 상한 도달 · 최종 승점으로 순위 결정`,
      `Reached the ${turnLimit}-turn limit · Ranked by final VP`)}</p>}
    {result.end_reason === "win_score" && <p className="muted">{tr("5점 이상 달성으로 종료", "Ended after a player reached 5 VP")}</p>}
    <Table caption={tr("돼지 저금통 최종 순위", "Piggy Bank final standings")} headers={tr(["참가자", "승점", "획득 피스", "결과"], ["Player", "VP", "Pieces earned", "Result"])}
      rows={order.map((player, index) => [`${index + 1}. ${player}`, result.scores?.[player] ?? scores[player] ?? 0,
        result.pieces_awarded?.[player] ?? 0, result.eliminated.includes(player) ? tr("탈락", "Eliminated") : tr("생존", "Survived")])} />
    {verdict?.type === "pig_challenge" && <PiggyChallengeResult data={verdict.data} />}
  </div>;
  return <div className="pig-stage">
    <h2>{turn ? tr(turnLimit ? `${turn.turn} / ${turnLimit}턴` : `${turn.turn}턴`,
      turnLimit ? `Turn ${turn.turn} / ${turnLimit}` : `Turn ${turn.turn}`) : tr("돼지 저금통 준비", "Preparing Piggy Bank")}</h2>
    <p className="pig-stage-status">{latest ? pigEventText(latest.type, latest.data) : tr("규칙 공개 대기", "Awaiting the game rules")}</p>
    {claim && verdict?.type !== "pig_challenge" && <div className="pig-current-claim"><PigIcon bank={claim.bank} /><div><strong>{claim.player}</strong>
      <p>{tr(`${pigColorLabel(claim.color)} ${claim.count}개 선언`, `Claims ${claim.count} ${pigColorLabel(claim.color)} coins`)}</p>
      <small>{verdict?.type === "pig_doubt" && verdict.data.bank === claim.bank ? coinText(verdict.data.actual) :
        tr("선언은 개봉 전까지 확인되지 않은 값입니다.", "The claim remains unverified until the bank opens.")}</small></div></div>}
    {verdict && <div className="pig-verdict" data-correct={verdict.data.correct}>
      <strong>{verdict.type === "pig_doubt" ? tr("의심 판정", "Doubt verdict") : tr("전체 암기 판정", "Full-memory verdict")}</strong>
      <p>{pigEventText(verdict.type, verdict.data)}</p>
      {verdict.type === "pig_challenge" && <PiggyChallengeResult data={verdict.data} />}
    </div>}
    <div className="pig-scoreboard" aria-label={tr("현재 승점", "Current scores")}>{order.map((player) =>
      <button type="button" key={player} aria-pressed={player === selected} onClick={() => onChoose(player)}>
        <span>{player}</span><strong>{scores[player] ?? 0}<small> / 5</small></strong>
        <span className="pig-score-track" aria-hidden="true">{Array.from({length: 5}, (_, index) => <i key={index} data-earned={index < (scores[player] ?? 0) || undefined} />)}</span>
      </button>)}</div>
    <p className="muted">{turnLimit ? tr(`5점 이상 달성 또는 ${turnLimit}턴 완료 시 종료 · 최하위 1명 탈락`,
      `Ends at 5 VP or after Turn ${turnLimit} · One last-place player is eliminated`) :
      tr("누군가 5점을 얻으면 종료 · 최하위 1명 탈락", "Ends when anyone reaches 5 VP · One last-place player is eliminated")}</p>
    <p className="pig-reset-status">{tr("리셋 요청", "Reset requests")} <strong>{state.pigVoters?.length > 3 ?
      tr(`${state.pigVoters.length}명 요청 · 기준 3명`, `${state.pigVoters.length} requests · 3 required`) : `${state.pigVoters?.length ?? 0} / 3`}</strong>
      {state.pigVoters?.length > 0 && <span>{state.pigVoters.join(" · ")}</span>}</p>
    {rules && <details className="stage-details"><summary>{tr("게임 규칙", "Game rules")}</summary><p className="choice-rules">{explanation}</p></details>}
  </div>;
}

export function PiggyInformation({state, replay}) {
  const {selected, choosePlayer, seek, match: {players}} = replay;
  const [tab, setTab] = useState("history");
  const [turnChoice, setTurnChoice] = useState("");
  const owner = memoryOwner(state, selected);
  const freeMemory = hasFreeMemory(state);
  const dynamicMemory = hasDynamicMemory(state);
  const memoryEnabled = hasMemorySlots(state) || freeMemory;
  const memoryRecord = owner && state.feed.findLast((event) => event.msg_type === "pig_recall" &&
    event.agent_name === owner && (freeMemory || event.data.reset === state.pigMemoryReset));
  const latestTurn = state.feed.findLast(({msg_type}) => msg_type === "pig_turn")?.data.turn ?? 0;
  const filteredTurn = Number(turnChoice) <= latestTurn ? Number(turnChoice) : 0;
  let eventTurn = 0;
  const history = state.feed.filter(({msg_type, data}) => {
    if (msg_type === "pig_turn") eventTurn = data.turn;
    return ["pig_deposit", "pig_claim", "pig_pass", "pig_doubt", "pig_challenge", "pig_replace", "pig_reset"].includes(msg_type) &&
      (!selected || [data.player, data.to, data.challenger].includes(selected)) && (!filteredTurn || (data.turn ?? eventTurn) === filteredTurn);
  });
  const banks = [...new Set([...Object.values(state.pigLower ?? {}), ...Object.values(state.pigUpper ?? {})].filter((bank) => bank != null))].sort((a, b) => a - b);
  return <aside className="caption match-info pig-info" aria-label={tr("돼지 저금통 게임 정보", "Piggy Bank information")}>
    <TabList role="tablist" aria-label={tr("돼지 저금통 정보 종류", "Piggy Bank information tabs")} size="sm" value={tab} onChange={setTab} hasDivider>
      <Tab id="pig-history" value="history" label={tr("전달·판정 기록", "Passes and verdicts")} panelId="pig-history-panel" />
      <Tab id="pig-banks" value="banks" label={tr("저금통 현황", "Bank positions")} panelId="pig-banks-panel" />
      {memoryEnabled && <Tab id="pig-memory" value="memory" label={freeMemory ? tr("기억 요약", "Memory summary") : tr("기억 슬롯", "Memory slots")} panelId="pig-memory-panel" />}
      <Tab id="pig-scores" value="scores" label={tr("승점 기록", "Score history")} panelId="pig-scores-panel" />
    </TabList>
    <div className="match-info-games">
      <Selector label={tr("기록을 볼 참가자", "Filter by player")} isLabelHidden value={selected} size="sm" onChange={choosePlayer}
        options={[{value: "", label: tr("전체 참가자", "All players")}, ...players.map((player) => ({value: player, label: player}))]} />
      {tab === "history" && latestTurn > 0 && <Selector label={tr("기록을 볼 턴", "Filter by turn")} isLabelHidden value={String(filteredTurn || "")} size="sm" onChange={setTurnChoice}
        options={[{value: "", label: tr("모든 턴", "All turns")}, ...Array.from({length: latestTurn}, (_, index) => ({value: String(index + 1), label: tr(`${index + 1}턴`, `Turn ${index + 1}`)}))]} />}
    </div>
    <div id="pig-history-panel" className="match-info-scroll" role="tabpanel" aria-labelledby="pig-history" hidden={tab !== "history"} tabIndex={0}>
      {history.length ? <Table caption={tr("동전 전달과 의심·리셋 판정", "Coin passes, doubts, and reset verdicts")} headers={tr(["기록", "행동", "내용"], ["Event", "Action", "Details"])}
        rows={history.map(({msg_type, data, step}) => [<button type="button" className="result-link" onClick={() => seek(step)}>{step}</button>,
          ({pig_deposit: tr("전달", "Pass"), pig_claim: tr("개수 선언", "Claim"), pig_pass: tr("의심 없음", "No doubt"), pig_doubt: tr("의심 판정", "Doubt verdict"), pig_replace: tr("교체", "Replace"), pig_reset: tr("리셋", "Reset"), pig_challenge: tr("전체 암기", "Full recall")})[msg_type],
          msg_type === "pig_challenge" ? <details className="pig-challenge-details"><summary>{pigEventText(msg_type, data)}</summary>
            <PiggyChallengeResult data={data} /></details> : pigEventText(msg_type, data)])} /> :
        <p className="empty">{tr("이 조건에 해당하는 기록이 없어요.", "No records match these filters.")}</p>}
    </div>
    <div id="pig-banks-panel" className="match-info-scroll" role="tabpanel" aria-labelledby="pig-banks" hidden={tab !== "banks"} tabIndex={0}>
      <p className="muted">{owner ? freeMemory ? tr(`${owner} 시점에서 공개된 동전 정보만 표시합니다. 기억 요약은 수량표로 변환하지 않습니다.`,
        `Showing publicly known coin counts for ${owner}’s view. The memory summary is not converted into a tally.`) : ["model", "dynamic"].includes(state.pigMemories?.[owner]?.mode) ?
        tr(`${owner}이 직접 갱신한 추정값과 공개된 정보입니다. 기억은 실제 개수와 다를 수 있습니다.`, `These are ${owner}’s own estimates and publicly known contents. Recalled counts may differ from the actual counts.`) :
        tr(`${owner}의 기억 슬롯과 공개된 정보만 표시합니다.`, `Showing ${owner}’s memory slots and publicly known contents.`) :
        tr("미개봉 저금통의 누적 동전 수는 공개하지 않습니다. 운영자 시점에서는 내부를 확인할 수 있습니다.", "Accumulated counts in unopened banks remain hidden. The operator view can inspect their contents.")}</p>
      {banks.length ? <Table caption={tr("현재 사용 중인 저금통", "Banks currently in play")} headers={tr(["저금통", "위치", freeMemory ? "확인된 동전" : "기억·공개 정보"], ["Bank", "Location", freeMemory ? "Known contents" : "Recalled/public counts"])} rows={banks.map((bank) => {
        const upper = Object.entries(state.pigUpper ?? {}).find(([, id]) => id === bank)?.[0];
        const lower = Object.entries(state.pigLower ?? {}).find(([, id]) => id === bank)?.[0];
        const memory = state.pigMemories?.[owner];
        return [bankLabel(bank), `${upper ?? lower} · ${upper ? tr("위칸", "Upper tier") : tr("아래칸", "Lower tier")}`,
          <Coins coins={knownCoins(state, bank, owner)} estimate={["model", "dynamic"].includes(memory?.mode) && memory.banks.includes(bank)} />];
      }).filter(([, location]) => !selected || location.startsWith(`${selected} ·`))} /> : <p className="empty">{tr("저금통 배분 대기 중입니다.", "Waiting for banks to be distributed.")}</p>}
    </div>
    {memoryEnabled && <div id="pig-memory-panel" className="match-info-scroll" role="tabpanel" aria-labelledby="pig-memory" hidden={tab !== "memory"} tabIndex={0}>
      {state.pigPerspective === "public" ? <p className="empty">{freeMemory ? tr("비공개 기억 요약은 본인만 확인할 수 있습니다.", "Memory summaries are private to each player.") :
        tr("기억할 저금통 선택과 기억 내용은 본인만 확인할 수 있습니다.", "Memory-bank choices and recalled counts are private to each player.")}</p> : <>
        {freeMemory ? <PiggyFreeMemory state={state} selected={selected} /> : <PiggyMemorySlots state={state} selected={selected} />}
        {owner && !freeMemory && <p className="muted">{dynamicMemory ?
          tr("기억을 갱신할 때 현재 저금통 중 3개를 다시 고를 수 있습니다. 슬롯에서 뺀 저금통의 과거 기억은 되살리지 않습니다.", "Each memory update can choose any three current banks. Dropped banks’ previous memories are not restored when selected again.") :
          tr("리셋까지 같은 저금통 3개를 기억합니다. 선택한 저금통이 교체되면 해당 슬롯에 새 저금통이 들어갑니다.", "These three banks stay selected until reset. A retired selected bank is replaced in the same slot by the fresh bank.")}</p>}
        {memoryRecord && <button type="button" className="result-link" onClick={() => seek(memoryRecord.step)}>{tr("이 기억 상태의 기록 보기", "View this memory snapshot")}</button>}
      </>}
    </div>}
    <div id="pig-scores-panel" className="match-info-scroll" role="tabpanel" aria-labelledby="pig-scores" hidden={tab !== "scores"} tabIndex={0}>
      <Table caption={tr("현재 공개 승점", "Current public scores")} headers={tr(["참가자", "누적 승점", "리셋 요청"], ["Player", "Total VP", "Reset requested"])}
        rows={(selected ? [selected] : state.pigOrder ?? players).map((player) => [player, state.pigScores?.[player] ?? 0, state.pigVoters?.includes(player) ? tr("요청함", "Requested") : "–"])} />
      {state.feed.some(({msg_type}) => ["pig_doubt", "pig_challenge"].includes(msg_type)) && <Table caption={tr("판정 후 승점", "Scores after verdicts")} headers={[tr("기록", "Event"), ...(selected ? [selected] : players)]}
        rows={state.feed.filter(({msg_type}) => ["pig_doubt", "pig_challenge"].includes(msg_type)).map(({data, step}) => [
          <button type="button" className="result-link" onClick={() => seek(step)}>{step}</button>, ...(selected ? [selected] : players).map((player) => scoreText(data.scores?.[player] ?? 0))])} />}
    </div>
  </aside>;
}
