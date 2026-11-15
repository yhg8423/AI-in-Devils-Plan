import React, {useMemo, useState} from "react";
import {Selector} from "@astryxdesign/core/Selector";
import {Tab, TabList} from "@astryxdesign/core/TabList";
import {chipColorLabel, chipColors, heavy13Players} from "./heavy-13.js";
import {tr} from "./locale.js";
import {Table} from "./records.jsx";

function Cards({values}) {
  return values.length ? <span className="heavy-hand" aria-label={tr(`남은 바위 카드 ${values.join(", ")}`, `Remaining rock cards: ${values.join(", ")}`)}>
    {values.map((value) => <span className="heavy-card" key={value}>{value}</span>)}
  </span> : tr("없음", "None");
}

function Chip({color, count}) {
  return <span className="heavy-chip-count"><i className="heavy-chip" data-color={color} aria-hidden="true" />
    {chipColorLabel(color)}{count !== undefined && ` ${count}`}
  </span>;
}

function Chips({values}) {
  const remaining = chipColors.filter((color) => values[color] > 0);
  return remaining.length ? <span className="heavy-hand">
    {remaining.map((color) => <Chip key={color} color={color} count={values[color]} />)}
  </span> : tr("없음", "None");
}

function roundCells(entry, seek) {
  if (!entry) return ["–", "–", "–", "–", "–"];
  const {weight, chip, passed, placement, penalty, total, step} = entry;
  const action = placement ? tr(`${passed ? "패스 → " : ""}${placement} 배치`, `${passed ? "Pass → " : ""}Placed on ${chipColorLabel(placement)}`)
    : passed ? tr("패스 · 배치 대기", "Passed · awaiting placement") : "–";
  return [weight ?? "–", chip ? <Chip color={chip} /> : "–", action === "–" ? action :
    <button type="button" className="result-link" onClick={() => seek(step)}>{action}</button>, penalty ?? "–", total];
}

export function Heavy13Information({state, replay}) {
  const {selected, choosePlayer, seek, match: {players}} = replay;
  const [tab, setTab] = useState("hand");
  const [roundChoice, setRoundChoice] = useState("");
  const accounts = useMemo(() => heavy13Players(players, state.feed), [players, state.feed]);
  const round = Math.min(Number(roundChoice) || state.rounds, state.rounds);
  const current = selected ? [selected] : players;
  const historyHeaders = tr(["카드", "칩", "배치", "벌점", "누적"], ["Card", "Chip", "Placement", "Penalty", "Total"]);

  return <aside className="caption match-info heavy-info" aria-label={tr("무거운 13 게임 정보", "Heavy 13 match information")}>
    <TabList role="tablist" aria-label={tr("무거운 13 정보 종류", "Heavy 13 information tabs")} size="sm" value={tab} onChange={setTab} hasDivider>
      <Tab id="heavy-hand" value="hand" label={tr("남은 카드·칩", "Remaining cards and chips")} panelId="heavy-info-panel" />
      <Tab id="heavy-history" value="history" label={tr("라운드 기록", "Round history")} panelId="heavy-info-panel" />
    </TabList>
    <div className="heavy-filters">
      <Selector label={tr("기록을 볼 참가자", "Filter by player")} isLabelHidden value={selected} size="sm" onChange={choosePlayer}
        options={[{value: "", label: tr("전체 참가자", "All players")}, ...players.map((player) => ({value: player, label: player}))]} />
      {tab === "history" && !selected && state.rounds > 0 && <Selector label={tr("기록을 볼 라운드", "Filter by round")} isLabelHidden size="sm"
        value={Number(roundChoice) > state.rounds ? "" : roundChoice} onChange={setRoundChoice}
        options={[{value: "", label: tr(`현재 라운드 · ${state.rounds}라운드`, `Current round · Round ${state.rounds}`)},
          ...Array.from({length: state.rounds}, (_, index) => ({value: String(index + 1), label: tr(`${index + 1}라운드`, `Round ${index + 1}`)}))]} />}
    </div>
    <div id="heavy-info-panel" className="match-info-scroll" role="tabpanel" aria-labelledby={`heavy-${tab}`} tabIndex={0}>
      {tab === "hand" ? <Table caption={state.rounds ? tr(`${state.rounds}라운드 보유 현황`, `Holdings in Round ${state.rounds}`) : tr("시작 보유 현황", "Starting holdings")}
        headers={tr(["참가자", "남은 바위 카드", "남은 색 칩", "누적 벌점"], ["Player", "Rock cards left", "Chips left", "Total penalty"])} rows={current.map((player) => {
          const {cards, chips, penalties} = accounts.get(player);
          return [player, <Cards values={cards} />, <Chips values={chips} />, penalties];
        })} /> : !round ? <p className="empty">{tr("아직 시작한 라운드가 없어요.", "No rounds have started yet.")}</p> : selected ?
        <Table caption={tr(`${selected} 라운드별 기록`, `${selected}'s round history`)} headers={[tr("라운드", "Round"), ...historyHeaders]}
          rows={accounts.get(selected).rounds.map((entry) => [tr(`${entry.round}라운드`, `Round ${entry.round}`), ...roundCells(entry, seek)])} /> :
        <Table caption={tr(`${round}라운드 참가자 기록`, `Round ${round} player records`)} headers={[tr("참가자", "Player"), ...historyHeaders]}
          rows={players.map((player) => [player, ...roundCells(accounts.get(player).rounds[round - 1], seek)])} />}
    </div>
  </aside>;
}
