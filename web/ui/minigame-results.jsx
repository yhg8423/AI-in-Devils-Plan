import React, {useState} from "react";
import {Button} from "@astryxdesign/core/Button";
import {tr} from "./locale.js";
import {rankedScores, Table} from "./records.jsx";
import {scoreText} from "./replay.js";

function RecordLink({step, label, onSeek, children}) {
  return <button type="button" className="result-link" aria-label={label} onClick={() => onSeek(step)}>{children}</button>;
}

export function GrassResults({state, priority, players, onSeek}) {
  const picks = new Map();
  const placements = new Map();
  for (const event of state.feed) {
    if (event.msg_type === "grass_tile") picks.set(event.agent_name, {...event, order: picks.size + 1});
    if (event.msg_type === "grass_placement") placements.set(event.agent_name, {...event, order: placements.size + 1});
  }
  const settled = Boolean(state.grassScores);
  const order = settled ? rankedScores(state.grassScores, priority, players) :
    [...new Set([...picks.keys(), ...placements.keys()])].map((player) => ({player}));
  const rows = order.map(({player, rank, score}) => {
    const pick = picks.get(player);
    const attempt = placements.get(player);
    const placement = attempt?.data.placement;
    const selectedTile = pick ? <RecordLink step={pick.step} label={tr(`${player} 타일 선택 장면`, `${player}'s tile choice`)} onSeek={onSeek}>
      {tr(`${pick.order}번째 · ${pick.data}번`, `Pick ${pick.order} · Tile ${pick.data}`)}
    </RecordLink> : attempt ? tr(`${attempt.data.tile}번`, `Tile ${attempt.data.tile}`) : "–";
    const placementRecord = attempt ? <>
      <RecordLink step={attempt.step} label={tr(`${player} 타일 배치 장면`, `${player}'s tile placement`)} onSeek={onSeek}>
        {tr(`${attempt.order}번째`, `Attempt ${attempt.order}`)} · {placement ? tr("성공", "Success") : tr("실패", "Failed")}
      </RecordLink>
      {placement && <small className="result-detail">
        ({placement.row}, {placement.col}) · {placement.rotation}°
        {placement.cut?.length > 0 && tr(` · ${placement.cut.length}칸 제거`, ` · ${placement.cut.length} removed`)}
      </small>}
    </> : tr("대기", "Waiting");
    const row = [rank ? tr(`${rank}위 · ${player}`, `Rank ${rank} · ${player}`) : player, selectedTile, placementRecord,
      attempt ? `${scoreText(attempt.data.points)}${tr("점", " VP")}` : "–"];
    if (settled) row.push(`${scoreText(score)}${tr("점", " VP")}`);
    return row;
  });
  const headers = tr(["참가자", "타일 선택", "배치 기록", "배치 승점"], ["Player", "Tile choice", "Placement", "Placement VP"]);
  if (settled) headers.push(tr("정산 승점", "Final VP"));
  return <>
    <p className="muted">{tr(`타일 선택 ${picks.size}명`, `${picks.size} tiles chosen`)}{placements.size > 0 &&
      tr(` · 배치 성공 ${state.scene.placed} / ${placements.size}명`, ` · ${state.scene.placed} of ${placements.size} tiles placed`)}</p>
    <Table caption={tr("잔디 깔기 기록", "Lay the Grass results")} headers={headers} rows={rows} />
  </>;
}

export const cardPositions = "ABCDEFGHIJKLMNOP";
export const handNames = tr(["하이 카드", "원 페어", "투 페어", "트리플", "스트레이트", "플러시",
  "풀하우스", "포카드", "스트레이트 플러시"], ["High card", "One pair", "Two pair", "Three of a kind",
  "Straight", "Flush", "Full house", "Four of a kind", "Straight flush"]);

export function formatPokerCards(cards) {
  return cards.replace(/\bT(?=[♠♥♦♣])/g, "10");
}

export function PokerCard({card, position, picked}) {
  const face = formatPokerCards(card);
  const suit = face.at(-1);
  return <div className="poker-card" data-picked={picked} data-red={suit === "♥" || suit === "♦"}>
    {position && <small>{position}</small>}
    <strong><span>{face.slice(0, -1)}</span><span>{suit}</span></strong>
  </div>;
}

export function CommunityCards({community}) {
  const cards = community?.split(",").map((card) => card.trim()).filter(Boolean);
  if (!cards?.length) return null;
  const label = tr("공유 카드", "Community cards");
  return <div className="poker-community" role="group" aria-label={label}>
    <span aria-hidden="true">{label}</span>
    <div className="poker-community-cards">{cards.map((card) => <PokerCard key={card} card={card} />)}</div>
  </div>;
}

export function duelWinner(poker, first, second) {
  const left = poker.hands?.[first];
  const right = poker.hands?.[second];
  if (!left || !right) return undefined;
  for (let index = 0; index < Math.max(left.length, right.length); index++) {
    const comparison = (left[index] ?? -1) - (right[index] ?? -1);
    if (comparison) return comparison > 0 ? first : second;
  }
  return null;
}

export function PokerResults({state, order, onSeek}) {
  const [section, setSection] = useState("duels");
  const start = state.feed.find((event) => event.msg_type === "pre_poker_ranking")?.data.ranking ?? [];
  const totals = new Map(order.map((player) => [player, {wins: 0, losses: 0, draws: 0}]));
  const duels = state.feed.filter((event) => event.msg_type === "poker_result").map((event) => {
    const contestants = Object.keys(event.data.picks);
    const winner = duelWinner(event.data, ...contestants);
    if (winner !== undefined) {
      for (const name of contestants) {
        const record = totals.get(name);
        if (record) record[winner === null ? "draws" : name === winner ? "wins" : "losses"]++;
      }
    }
    return {event, contestants, winner};
  });
  const rows = order.map((player, index) => {
    const before = start.indexOf(player) + 1;
    const {wins, losses, draws} = totals.get(player);
    const played = duels.some(({contestants}) => contestants.includes(player));
    const result = wins + losses + draws ? tr(`${wins}승 ${losses}패${draws ? ` ${draws}무` : ""}`,
      `${wins}W ${losses}L${draws ? ` ${draws}D` : ""}`) : played ? tr("승패 기록 없음", "No result recorded") : tr("미출전", "Did not play");
    return [player, before ? tr(`${before}위 → ${index + 1}위`, `${before} → ${index + 1}`) : tr(`${index + 1}위`, `${index + 1}`), result];
  });
  return <>
    <div className="match-info-games" role="group" aria-label={tr("기억 포커 결과 보기", "Memory Poker results")}>
      {[["duels", tr("대결 기록", "Duel history")], ["players", tr("참가자 전적", "Player records")]].map(([value, label]) =>
        <Button key={value} label={label} size="sm" variant={section === value ? "secondary" : "ghost"}
          aria-pressed={section === value} onClick={() => setSection(value)} />)}
    </div>
    {section === "players" ? <Table caption={tr("기억 포커 순위와 전적", "Memory Poker standings and results")}
      headers={tr(["참가자", "순위 변화", "전적"], ["Player", "Rank change", "Record"])} rows={rows} /> :
      duels.length ? <ol className="poker-duel-list">{duels.map(({event, contestants, winner}, index) => {
        const {display, community, picks, hands} = event.data;
        const outcome = winner === undefined ? tr("승패 기록 없음", "No result recorded") : winner === null ? tr("무승부", "Draw")
          : tr(`${winner} 승리`, `${winner} wins`);
        return <li key={event.step}>
          <details>
            <summary>{tr(`${index + 1}번째 대결`, `Duel ${index + 1}`)} · {contestants.join(" vs ")} · <strong>{outcome}</strong></summary>
            <CommunityCards community={community} />
            <Table caption={tr("선택한 카드와 족보", "Selected cards and hands")}
              headers={tr(["참가자", "카드 (위치)", "족보", "결과"], ["Player", "Cards (positions)", "Hand", "Result"])}
              rows={contestants.map((name) => {
                const cards = picks[name].split(/\s+/).map((position) => {
                  const card = display?.[cardPositions.indexOf(position)];
                  return card ? `${formatPokerCards(card)} (${position})` : position;
                }).join(" · ");
                const result = winner === undefined ? "–" : winner === null ? tr("무승부", "Draw") : name === winner ? tr("승리", "Win") : tr("패배", "Loss");
                return [name, cards, handNames[hands?.[name]?.[0]] ?? "–", result];
              })} />
            <RecordLink step={event.step} label={tr(`${index + 1}번째 포커 대결 장면`, `Go to poker duel ${index + 1}`)} onSeek={onSeek}>
              {tr("대결 장면 보기", "Go to duel")}</RecordLink>
          </details>
        </li>;
      })}</ol> : <p className="empty">{tr("이 시점에 공개된 포커 대결이 없어요.", "No poker duels have been revealed at this point.")}</p>}
  </>;
}
