import React, {useLayoutEffect, useRef, useState} from "react";
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
const coinText = (coins) => coins ? tr(`흑 ${coins.black} · 백 ${coins.white}`, `Black ${coins.black} · White ${coins.white}`) : tr("미개봉", "Unopened");
const knownCoins = (state, bank) => state.pigContents?.[bank] ?? state.pigKnown?.[bank];
const position = (x, y) => ({left: `${x / setWidth * 100}%`, top: `${y / setHeight * 100}%`});

export function pigActionText(phase, action) {
  let data;
  try { data = JSON.parse(action); } catch { data = action; }
  if (phase === "pig_count") return tr(`${action}개 선언`, `Declare ${action} coins`);
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
    case "pig_reset_vote": return tr(`${data.player} 리셋 요청 · ${data.voters.length} / 3명`, `${data.player} requests reset · ${data.voters.length} of 3`);
    case "pig_challenge": return tr(`${data.player} 전체 암기 ${data.correct ? "성공 · +3점" : "실패 · −2점"}`, `${data.player}’s full-memory challenge ${data.correct ? "succeeds · +3 VP" : "fails · −2 VP"}`);
    case "pig_reset": return tr("전체 저금통 리셋 · 승점 유지", "All banks reset · Scores retained");
    case "pig_contents": return tr("운영자 전용 · 저금통 내부", "Operator only · Bank contents");
    case "pig_discussion": return data.stage === "opening" ? tr("게임 시작 전 대화", "Opening discussion") : tr(`${data.turn}턴 행동 전 대화`, `Discussion before turn ${data.turn}`);
    case "pig_discussion_end": return tr("대화 종료", "Discussion complete");
    case "pig_preparation": return tr("비공개 전략 준비", "Private strategy preparation");
    case "pig_preparation_end": return tr("전략 준비 완료", "Strategy preparation complete");
  }
}

export function applyPigEvent(state, type, data) {
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
      state.pigDeposit = null;
      state.pigContents = {};
      state.pigActive = data.next_player ?? Object.keys(data.upper).find((player) => data.upper[player] != null);
      state.pigKnown = Object.fromEntries([...Object.values(data.lower), ...Object.values(data.upper)]
        .filter((bank) => bank != null).map((bank) => [bank, {black: 1, white: 1}]));
      break;
    }
    case "pig_turn": state.pigTurn = data; state.pigActive = data.player; state.pigClaim = null; state.pigVerdict = null; break;
    case "pig_deposit":
      state.pigDeposit = data;
      state.pigActive = data.to;
      state.pigClaim = null;
      delete state.pigKnown?.[data.bank];
      delete state.pigContents?.[data.bank];
      break;
    case "pig_claim": state.pigClaim = data; state.pigActive = data.player; break;
    case "pig_doubt":
      state.pigKnown ??= {};
      state.pigKnown[data.bank] = data.actual;
      state.pigVerdict = {type, data};
      break;
    case "pig_replace":
      delete state.pigKnown?.[data.old_bank];
      delete state.pigContents?.[data.old_bank];
      state.pigKnown[data.bank] = {black: 1, white: 1};
      state.pigClaim = null;
      state.pigActive = data.next_player ?? data.player;
      break;
    case "pig_reset_vote": state.pigVoters = data.voters; break;
    case "pig_challenge": state.pigKnown = {...state.pigKnown, ...data.actual}; state.pigVerdict = {type, data}; break;
    case "pig_contents": state.pigContents = {...data.banks}; break;
  }
  if (type !== "pig_contents") state.pigLast = {type, data};
}

function PigIcon({bank, coins, compact = false}) {
  return <span className={`pig-icon${compact ? " compact" : ""}`} role="img" aria-label={`${bankLabel(bank)} · ${bank == null ? tr("빈칸", "Empty") : coinText(coins)}`}>
    <svg viewBox="0 0 32 24" aria-hidden="true" shapeRendering="crispEdges" data-empty={bank == null || undefined}>
      <path fill="#55353c" d="M6 4h3V1h5v3h9v3h4v4h4v7h-5v3h-4v3h-5v-3h-6v3H6v-5H3v-3H0V9h3V6h3z" />
      <path fill="#d48c95" d="M6 6h5V3h2v3h10v3h3v4h3v3h-5v3H7v-3H4V9h2z" />
      <path fill="#efb3ab" d="M8 7h13v3H7v4H5v-4h3zM25 13h4v3h-4z" />
      <path fill="#a35f74" d="M8 17h15v2H8zM7 20h3v2H7zM19 20h3v2h-3z" />
      <path fill="#241e2c" d="M21 9h2v2h-2zM12 5h7v2h-7zM27 13h1v1h-1z" />
    </svg>
    <strong>{bank == null ? "–" : bankLabel(bank)}</strong>
  </span>;
}

function Coins({coins}) {
  return coins ? <span className="pig-coins"><span><i data-color="black" aria-hidden="true" />{coins.black}</span><span><i data-color="white" aria-hidden="true" />{coins.white}</span></span> :
    <span className="pig-hidden">{tr("미개봉", "Unopened")}</span>;
}

export function PiggyScene({players, state, frame, selected, onChoose}) {
  const canvas = useRef(null);
  useLayoutEffect(() => drawPiggySet(canvas.current), []);
  const order = state.pigOrder ?? players;
  const active = state.pigActive;
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
          <button type="button" className={`token pig-seat${active === player ? " acting" : ""}`} style={position(piggySeats[index], 134)}
            aria-label={tr(`${player} · 승점 ${state.pigScores?.[player] ?? 0}`, `${player} · ${state.pigScores?.[player] ?? 0} VP`)} aria-pressed={selected === player}
            data-status={state.result?.eliminated.includes(player) ? "탈락" : undefined} data-speaking={speech?.agent_name === player || undefined}
            onClick={() => onChoose(player)}><Sprite player={player} /><span>{player} · {state.pigScores?.[player] ?? 0}</span></button>
          <div className="pig-station" style={position(piggySeats[index], 153)} data-active={active === player || undefined}>
            {["upper", "lower"].map((tier) => {
              const bank = (tier === "upper" ? state.pigUpper : state.pigLower)?.[player];
              return <div className="pig-tier" key={tier} aria-label={`${player} · ${tier === "upper" ? tr("위칸", "Upper tier") : tr("아래칸", "Lower tier")}`}>
                <span className="pig-tier-label">{tier === "upper" ? tr("위", "UP") : tr("아래", "LOW")}</span>
                <PigIcon bank={bank} compact />{bank != null && <Coins coins={knownCoins(state, bank)} />}
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
    <ArenaSpeech speech={speech} recipients={recipients} />
  </div>;
}

export function PiggyStage({state, players, selected, onChoose}) {
  const {pigTurn: turn, pigClaim: claim, pigScores: scores = {}, pigLast: latest, pigVerdict: verdict, result} = state;
  const rules = state.feed.find((event) => event.msg_type === "rules");
  const rawRules = rules ? typeof rules.data === "string" ? rules.data : rules.content : "";
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
    <Table caption={tr("돼지 저금통 최종 순위", "Piggy Bank final standings")} headers={tr(["참가자", "승점", "획득 피스", "결과"], ["Player", "VP", "Pieces earned", "Result"])}
      rows={order.map((player, index) => [`${index + 1}. ${player}`, result.scores?.[player] ?? scores[player] ?? 0,
        result.pieces_awarded?.[player] ?? 0, result.eliminated.includes(player) ? tr("탈락", "Eliminated") : tr("생존", "Survived")])} />
  </div>;
  return <div className="pig-stage">
    <h2>{turn ? tr(`${turn.turn}턴`, `Turn ${turn.turn}`) : tr("돼지 저금통 준비", "Preparing Piggy Bank")}</h2>
    <p className="pig-stage-status">{latest ? pigEventText(latest.type, latest.data) : tr("규칙 공개 대기", "Awaiting the game rules")}</p>
    {claim && <div className="pig-current-claim"><PigIcon bank={claim.bank} /><div><strong>{claim.player}</strong>
      <p>{tr(`${pigColorLabel(claim.color)} ${claim.count}개 선언`, `Claims ${claim.count} ${pigColorLabel(claim.color)} coins`)}</p>
      <small>{verdict?.type === "pig_doubt" && verdict.data.bank === claim.bank ? coinText(verdict.data.actual) :
        tr("선언은 개봉 전까지 확인되지 않은 값입니다.", "The claim remains unverified until the bank opens.")}</small></div></div>}
    {verdict && <div className="pig-verdict" data-correct={verdict.data.correct}>
      <strong>{verdict.type === "pig_doubt" ? tr("의심 판정", "Doubt verdict") : tr("전체 암기 판정", "Full-memory verdict")}</strong>
      <p>{pigEventText(verdict.type, verdict.data)}</p>
    </div>}
    <div className="pig-scoreboard" aria-label={tr("현재 승점", "Current scores")}>{order.map((player) =>
      <button type="button" key={player} aria-pressed={player === selected} onClick={() => onChoose(player)}>
        <span>{player}</span><strong>{scores[player] ?? 0}<small> / 5</small></strong>
        <span className="pig-score-track" aria-hidden="true">{Array.from({length: 5}, (_, index) => <i key={index} data-earned={index < (scores[player] ?? 0) || undefined} />)}</span>
      </button>)}</div>
    <p className="muted">{tr("누군가 5점을 얻으면 종료 · 최하위 1명 탈락", "Ends when anyone reaches 5 VP · One last-place player is eliminated")}</p>
    <p className="pig-reset-status">{tr("리셋 요청", "Reset requests")} <strong>{state.pigVoters?.length ?? 0} / 3</strong>
      {state.pigVoters?.length > 0 && <span>{state.pigVoters.join(" · ")}</span>}</p>
    {rules && <details className="stage-details"><summary>{tr("게임 규칙", "Game rules")}</summary><p className="choice-rules">{explanation}</p></details>}
  </div>;
}

export function PiggyInformation({state, replay}) {
  const {selected, choosePlayer, seek, match: {players}} = replay;
  const [tab, setTab] = useState("history");
  const [turnChoice, setTurnChoice] = useState("");
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
          ({pig_deposit: tr("전달", "Pass"), pig_claim: tr("개수 선언", "Claim"), pig_pass: tr("의심 없음", "No doubt"), pig_doubt: tr("의심 판정", "Doubt verdict"), pig_replace: tr("교체", "Replace"), pig_reset: tr("리셋", "Reset"), pig_challenge: tr("전체 암기", "Full recall")})[msg_type], pigEventText(msg_type, data)])} /> :
        <p className="empty">{tr("이 조건에 해당하는 기록이 없어요.", "No records match these filters.")}</p>}
    </div>
    <div id="pig-banks-panel" className="match-info-scroll" role="tabpanel" aria-labelledby="pig-banks" hidden={tab !== "banks"} tabIndex={0}>
      <p className="muted">{tr("미개봉 저금통의 누적 동전 수는 공개하지 않습니다. 운영자 시점에서는 내부를 확인할 수 있습니다.", "Accumulated counts in unopened banks remain hidden. The operator view can inspect their contents.")}</p>
      {banks.length ? <Table caption={tr("현재 사용 중인 저금통", "Banks currently in play")} headers={tr(["저금통", "위치", "확인된 동전"], ["Bank", "Location", "Known contents"])} rows={banks.map((bank) => {
        const upper = Object.entries(state.pigUpper ?? {}).find(([, id]) => id === bank)?.[0];
        const lower = Object.entries(state.pigLower ?? {}).find(([, id]) => id === bank)?.[0];
        return [bankLabel(bank), `${upper ?? lower} · ${upper ? tr("위칸", "Upper tier") : tr("아래칸", "Lower tier")}`, <Coins coins={knownCoins(state, bank)} />];
      }).filter(([, location]) => !selected || location.startsWith(`${selected} ·`))} /> : <p className="empty">{tr("저금통 배분 대기 중입니다.", "Waiting for banks to be distributed.")}</p>}
    </div>
    <div id="pig-scores-panel" className="match-info-scroll" role="tabpanel" aria-labelledby="pig-scores" hidden={tab !== "scores"} tabIndex={0}>
      <Table caption={tr("현재 공개 승점", "Current public scores")} headers={tr(["참가자", "누적 승점", "리셋 요청"], ["Player", "Total VP", "Reset requested"])}
        rows={(selected ? [selected] : state.pigOrder ?? players).map((player) => [player, state.pigScores?.[player] ?? 0, state.pigVoters?.includes(player) ? tr("요청함", "Requested") : "–"])} />
      {state.feed.some(({msg_type}) => ["pig_doubt", "pig_challenge"].includes(msg_type)) && <Table caption={tr("판정 후 승점", "Scores after verdicts")} headers={[tr("기록", "Event"), ...(selected ? [selected] : players)]}
        rows={state.feed.filter(({msg_type}) => ["pig_doubt", "pig_challenge"].includes(msg_type)).map(({data, step}) => [
          <button type="button" className="result-link" onClick={() => seek(step)}>{step}</button>, ...(selected ? [selected] : players).map((player) => scoreText(data.scores?.[player] ?? 0))])} />}
    </div>
  </aside>;
}
