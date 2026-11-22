import React, {useEffect, useRef} from "react";
import {Button} from "@astryxdesign/core/Button";
import {Drawer, DrawerHeader} from "@astryxdesign/core/Drawer";
import {Selector} from "@astryxdesign/core/Selector";
import {Tab, TabList} from "@astryxdesign/core/TabList";
import {playerColor} from "./cast.js";
import {RouletteInspection} from "./day-two-scenes.jsx";
import {choiceOptionLabel} from "./choice-results.js";
import {tr} from "./locale.js";
import {checkpointLabel, eventFields, locationName, scoreText} from "./replay.js";
import {Sprite} from "./scene.jsx";

const playerTextTypes = new Set(["public", "room", "whisper", "discussion_note", "grass_plan", "decision_note", "picture_memory"]);

export function MatchFeed({events, onSeek, unit = "턴", emptyText = tr("이 시점에 볼 수 있는 플레이 기록이 없어요.", "No play records to show at this point.")}) {
  if (!events.length) return <p className="empty">{emptyText}</p>;
  return <ol className="feed">{events.map((event, index) => {
    const recipients = Array.isArray(event.visible_to) ? event.visible_to.filter((name) => name !== event.agent_name)
      .map((name) => name === "__operator__" ? tr("운영자", "Operator") : name) : [];
    const speaker = event.agent_name === "System" || event.msg_type === "room_move" ? "" : event.agent_name;
    const text = event.msg_type === "grass_choices" ? choiceOptionLabel(event.text) : event.text;
    const textLanguage = playerTextTypes.has(event.msg_type) && /[가-힣]/.test(text) ? "ko" : undefined;
    return <li key={event.step + "-" + index}>
      <button type="button" className="entry" onClick={() => onSeek(event.step)}>
        <span className="entry-meta">
          <span>{event.label}{speaker && " · " + speaker}{recipients.length > 0 && " → " + recipients.join(", ")}</span>
          <small>{tr(`${event.step}${unit}`, `${unit === "턴" ? "Turn" : "Event"} ${event.step}`)}</small>
        </span>
        {event.msg_type === "inspection" && event.data?.slots ? <RouletteInspection slots={event.data.slots} compact /> : <span lang={textLanguage}>{text}</span>}
      </button>
    </li>;
  }).reverse()}</ol>;
}

export function rankedScores(scores, priority, players) {
  const sorted = Object.entries(scores).sort(([left, a], [right, b]) =>
    b - a || (priority[left] ?? players.length) - (priority[right] ?? players.length));
  return sorted.map(([player, score]) => ({player, score, rank: sorted.findIndex(([, points]) => points === score) + 1}));
}

export function Standings({scores, priority, players, selected, onPlayer}) {
  return <ol className="standings">{rankedScores(scores, priority, players).map(({player, score, rank}) =>
    <li key={player}>
      <button type="button" className="rank-row" aria-pressed={player === selected}
        onClick={() => onPlayer(player)}>
        <span>{rank}</span>
        <strong style={{"--player": playerColor(player)}}>{player}</strong>
        <span>{scoreText(score)}{tr("점", " VP")}</span>
      </button>
    </li>)}</ol>;
}

export function Table({caption, headers, rows}) {
  return <div className="match-table-wrap"><table className="match-table">
    <caption>{caption}</caption>
    <thead><tr>{headers.map((header) => <th key={header} scope="col">{header}</th>)}</tr></thead>
    <tbody>{rows.map(([name, ...values]) => <tr key={name}><th scope="row">{name}</th>
      {values.map((value, index) => <td key={index}>{value}</td>)}
    </tr>)}</tbody>
  </table></div>;
}

export function isStrategy(event) {
  return ["discussion_note", "grass_plan", "decision_note", "picture_memory"].includes(event.msg_type);
}

function ParticipantRelationships({updates, players, player, onSeek}) {
  const latest = new Map();
  for (const event of updates) {
    const {data, step} = event;
    const translated = eventFields(event, data);
    for (const [name, rating] of Object.entries(translated.ratings)) {
      latest.set(name, {...rating, checkpoint: checkpointLabel(data.checkpoint, translated.checkpoint), step});
    }
  }
  const rows = players.filter((name) => name !== player).map((name) => {
    const rating = latest.get(name);
    if (!rating) return [name, "—", "—", <span className="muted">{tr("미평가", "Unrated")}</span>];
    return [name, rating.affinity, rating.trust, <>
      <span lang={/[가-힣]/.test(rating.reason) ? "ko" : undefined}>{rating.reason}</span>
      <button type="button" className="result-link" onClick={() => onSeek(rating.step)}>
        {tr(`${rating.checkpoint} · ${rating.step}번째 기록`, `${rating.checkpoint} · Event ${rating.step}`)}
      </button>
    </>];
  });

  return <section className="participant-relationships" aria-labelledby="participant-relationships">
    <h3 id="participant-relationships">{tr("친밀도·신뢰도", "Affinity and Trust")}</h3>
    {latest.size ? <div className="participant-scroll" role="region" aria-labelledby="participant-relationships" tabIndex={0}>
      <Table caption={tr(`${player}이 다른 참가자에게 매긴 점수 (0~100점)`, `${player}'s ratings of other players (0–100)`)}
        headers={tr(["상대", "친밀도", "신뢰도", "최근 평가"], ["Player", "Affinity", "Trust", "Latest rating"])} rows={rows} />
    </div> : <p className="empty">{tr("이 시점에 볼 수 있는 관계 평가가 없어요.", "No relationship ratings to show at this point.")}</p>}
  </section>;
}

export function Participant({state, player, players, onSeek, onClose, unit}) {
  const heading = useRef(null);
  useEffect(() => {
    heading.current?.scrollIntoView({block: "nearest"});
  }, [player]);
  const score = state.scores?.[player];
  const rank = score == null ? null : Object.values(state.scores).filter((points) => points > score).length + 1;
  const tile = state.tiles?.[player];
  const details = [score != null && `${scoreText(score)}${tr("점", " VP")}`, rank && tr(`${rank}위`, `Rank ${rank}`),
    state.locations && locationName(state.locations[player]), tile && tr(`${tile}번 타일`, `Tile ${tile}`),
    ...[6, 7, 8].map((choice) => choiceOptionLabel(state.choices?.[choice]?.[player]))].filter(Boolean);
  const records = (state.participantRecords ?? []).filter((event) => event.agent_name === player);
  const entries = state.feed.filter((event) => event.agent_name === player ||
    (Array.isArray(event.visible_to) && event.visible_to.includes(player)))
    .concat(records)
    .sort((a, b) => a.step - b.step);
  const thoughts = entries.filter((event) => event.agent_name === player && isStrategy(event));
  const activity = entries.filter((event) => !isStrategy(event) && event.msg_type !== "relationship_update");
  const relationshipUpdates = entries.filter((event) => event.agent_name === player && event.msg_type === "relationship_update");
  return <section className="caption participant-panel" aria-labelledby="selected-participant">
    <header className="participant-heading" ref={heading}>
      <span className="portrait"><Sprite player={player} /></span>
      <div>
        <h2 id="selected-participant">{player}</h2>
        {details.length > 0 && <p className="muted">{details.join(" · ")}</p>}
      </div>
      <Button label={tr("참가자 기록 닫기", "Close player record")} variant="secondary" size="sm" onClick={onClose} />
    </header>
    <div className="participant-columns">
      <section>
        <h3 id="participant-strategy">{tr("생각과 검토", "Thoughts and Reviews")}</h3>
        <div className="participant-scroll" tabIndex={0} role="region" aria-labelledby="participant-strategy">
          <MatchFeed events={thoughts} onSeek={onSeek} unit={unit}
            emptyText={tr("이 시점에 볼 수 있는 생각이나 검토 메모가 없어요.", "No thoughts or review notes to show at this point.")} />
        </div>
      </section>
      <section>
        <h3 id="participant-activity">{tr("대화와 행동", "Conversations and Actions")}</h3>
        <div className="participant-scroll" tabIndex={0} role="region" aria-labelledby="participant-activity">
          <MatchFeed events={activity} onSeek={onSeek} unit={unit} />
        </div>
      </section>
    </div>
    {players && <ParticipantRelationships updates={relationshipUpdates} players={players} player={player} onSeek={onSeek} />}
  </section>;
}

export function Records({replay, state, players, tab, onTab, open, onOpenChange, onPlayer}) {
  const perspectives = [
    {value: "public", label: tr("공개 시점", "Public view")},
    {value: "operator", label: tr("운영자 · 전체 기록", "Operator · All records")},
    ...players.map((player) => ({value: player, label: tr(`${player} 시점`, `${player}'s view`)})),
  ];
  const title = tr("플레이 기록", "Play records");
  const view = tr("관전 시점", "Perspective");

  return <Drawer label={title} isOpen={open} onOpenChange={onOpenChange} width={408} padding={0}
    className="records-drawer">
    <DrawerHeader className="records-header" title={title} onOpenChange={onOpenChange} />
    <div className="records-body">
      {state && <>
        <TabList role="tablist" aria-label={tr("기록 종류", "Record type")} size="md" value={tab} onChange={onTab} hasDivider>
          <Tab value="talk" label={tr("대화", "Conversation")} id="tab-talk" panelId="record-talk" />
          <Tab value="rank" label={tr("순위", "Standings")} id="tab-rank" panelId="record-rank" />
        </TabList>
        <div className="perspective">
          <Selector label={view} aria-label={view} isLabelHidden size="sm" variant="secondary" options={perspectives}
            value={replay.view} onChange={replay.chooseView} />
        </div>
        <section role="tabpanel" id="record-talk" aria-labelledby="tab-talk" hidden={tab !== "talk"}>
          <MatchFeed events={state.feed.slice(-18)} onSeek={(step) => replay.seek(step)} />
        </section>
        <section role="tabpanel" id="record-rank" aria-labelledby="tab-rank" hidden={tab !== "rank"}>
          <Standings scores={state.scores} priority={replay.match.priority} players={players}
            selected={replay.selected} onPlayer={onPlayer} />
        </section>
      </>}
    </div>
  </Drawer>;
}
