import React, {useState} from "react";
import {Selector} from "@astryxdesign/core/Selector";
import {Tab, TabList} from "@astryxdesign/core/TabList";
import {gemSlotLabel} from "./gem-exchange.jsx";
import {tr} from "./locale.js";
import {Table} from "./records.jsx";
import {scoreText} from "./replay.js";

export function GemInformation({state, replay}) {
  const {selected, choosePlayer, seek, match: {players}} = replay;
  const [tab, setTab] = useState("scores");
  const [roundChoice, setRoundChoice] = useState("");
  const latest = state.feed.findLast((event) => event.msg_type === "gem_round")?.data.round ?? 0;
  const round = Math.min(Number(roundChoice) || latest, latest);
  const reveal = state.feed.findLast((event) => event.msg_type === "gem_reveal" && event.data.round === round);
  const previous = state.feed.findLast((event) => event.msg_type === "gem_reveal" && event.data.round < round)?.data.scores ?? {};
  const bonuses = Object.fromEntries(players.map((player) => [player, 0]));
  for (const event of state.feed) {
    if (event.msg_type === "gem_bonus" && event.data.round === round) bonuses[event.data.player] += event.data.points;
  }
  const current = selected ? [selected] : players;
  const swaps = state.feed.filter((event) => event.msg_type === "gem_swap" && event.data.round === round)
    .map((event, index) => ({...event, order: index + 1}))
    .filter(({data}) => !selected || data.player === selected || data.target === selected);

  return <aside className="caption match-info" aria-label={tr("보석 암시장 게임 정보", "Gem Black Market information")}>
    <TabList role="tablist" aria-label={tr("보석 암시장 정보 종류", "Gem Black Market information tabs")} size="sm" value={tab} onChange={setTab} hasDivider>
      <Tab id="gem-scores" value="scores" label={tr("라운드별 점수", "Round scores")} panelId="gem-scores-panel" />
      <Tab id="gem-swaps" value="swaps" label={tr("교환 기록", "Swap history")} panelId="gem-swaps-panel" />
    </TabList>
    <div className="match-info-games">
      <Selector label={tr("기록을 볼 참가자", "Filter by player")} isLabelHidden value={selected} size="sm" onChange={choosePlayer}
        options={[{value: "", label: tr("전체 참가자", "All players")}, ...players.map((player) => ({value: player, label: player}))]} />
      {latest > 0 && <Selector label={tr("기록을 볼 라운드", "Filter by round")} isLabelHidden size="sm"
        value={Number(roundChoice) > latest ? "" : roundChoice} onChange={setRoundChoice}
        options={[{value: "", label: tr(`현재 라운드 · ${latest}라운드`, `Current round · Round ${latest}`)},
          ...Array.from({length: latest}, (_, index) => ({value: String(index + 1), label: tr(`${index + 1}라운드`, `Round ${index + 1}`)}))]} />}
    </div>
    <div id="gem-scores-panel" className="match-info-scroll" role="tabpanel" aria-labelledby="gem-scores" hidden={tab !== "scores"} tabIndex={0}>
      {!round ? <p className="empty">{tr("아직 시작한 라운드가 없어요.", "No rounds have started yet.")}</p> : <>
        {!reveal && <p className="muted">{tr("라운드 정산 대기 중입니다.", "Awaiting round scoring.")}</p>}
        <Table caption={<>{tr(`${round}라운드 점수`, `Round ${round} scores`)}{reveal && <> · <button type="button" className="result-link" onClick={() => seek(reveal.step)}>
          {tr("정산 기록 보기", "View scoring event")}</button></>}</>}
          headers={tr(["참가자", "카드 승점", "폭탄 보너스", "라운드 합계", "누적 승점"], ["Player", "Card VP", "Bomb bonus", "Round total", "Cumulative VP"])}
          rows={current.map((player) => {
            const card = reveal?.data.points[player];
            const total = reveal ? card + bonuses[player] : null;
            const cumulative = reveal ? reveal.data.scores[player] : (previous[player] ?? 0) + bonuses[player];
            return [player, card == null ? "–" : scoreText(card), scoreText(bonuses[player]),
              total == null ? "–" : scoreText(total), scoreText(cumulative)];
          })} />
      </>}
    </div>
    <div id="gem-swaps-panel" className="match-info-scroll" role="tabpanel" aria-labelledby="gem-swaps" hidden={tab !== "swaps"} tabIndex={0}>
      {!round ? <p className="empty">{tr("아직 시작한 라운드가 없어요.", "No rounds have started yet.")}</p> :
        !swaps.length ? <p className="empty">{tr("이 라운드에 공개된 교환 기록이 없어요.", "No swaps are visible in this round.")}</p> :
          <Table caption={tr(`${round}라운드 교환 기록`, `Round ${round} swap history`)}
            headers={tr(["순서", "진행", "교환자", "대상"], ["Order", "Pass", "Player", "Target"])}
            rows={swaps.map(({data, step, order}) => [order, data.pass === 1 ? tr("정순", "Forward") : tr("역순", "Reverse"),
              <button type="button" className="result-link" onClick={() => seek(step)}>{data.player}</button>, gemSlotLabel(data.target)])} />}
    </div>
  </aside>;
}
