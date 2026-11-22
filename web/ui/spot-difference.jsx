import React, {useEffect, useId, useRef, useState} from "react";
import {Tab, TabList} from "@astryxdesign/core/TabList";
import {tr} from "./locale.js";
import {Table} from "./records.jsx";
import {ExileCast, ExileRoom} from "./exile-match.jsx";
import "./spot-difference.css";

const roundText = (round, overtime = false) => overtime ? tr(`연장 ${Math.max(1, round - 3)}라운드`, `Overtime ${Math.max(1, round - 3)}`) : tr(`${round}라운드`, `Round ${round}`);
const stageText = (stage) => ({observe: tr("원본 관찰", "Observe the original"), blank: tr("그림 숨김", "Picture hidden"), answer: tr("달라진 부분 찾기", "Find the changes"), reveal: tr("정답·점수 공개", "Answers and scores")})[stage];
const themes = {fishing: tr("낚시터", "Fishing pond"), market: tr("시장", "Market"), beach: tr("해변", "Beach"), cafe: tr("카페", "Café")};
const coordinates = (marks) => marks.length ? marks.map(({x, y}) => `(${x}, ${y})`).join(" · ") : tr("표시 없음", "No marks");
const copyMarks = (marks = []) => marks.map((mark) => ({...mark}));

export function applyPictureEvent(state, type, data, event = {}) {
  switch (type) {
    case "picture_setup":
      state.pictureSetup = {...data};
      state.picturePhase = null;
      state.pictureMemories = {};
      state.pictureSubmissions = {};
      state.pictureResults = [];
      state.pictureTotals = Object.fromEntries(data.players.map((player) => [player, 0]));
      state.pictureTiebreak = null;
      break;
    case "picture_phase":
      if (state.picturePhase?.round !== data.round) state.pictureMemories = {};
      state.picturePhase = {...data, picture: data.stage === "blank" ? null : data.picture};
      break;
    case "picture_memory":
      state.pictureMemories ??= {};
      state.pictureMemories[data.player] = {...data, text: event.translation?.fields?.memory ?? data.memory};
      break;
    case "picture_marks":
      state.pictureSubmissions ??= {};
      state.pictureSubmissions[`${data.round}:${data.player}`] = {...data, marks: copyMarks(data.marks), step: event.step, revealed: false};
      break;
    case "picture_result": {
      const result = {...data, step: event.step};
      state.pictureResults ??= [];
      state.pictureResults.push(result);
      state.pictureTotals = {...data.totals};
      state.scores = {...data.totals};
      state.picturePhase = {...state.picturePhase, stage: "reveal", picture: data.picture};
      state.pictureSubmissions ??= {};
      for (const [player, marks] of Object.entries(data.answers)) {
        state.pictureSubmissions[`${data.round}:${player}`] = {round: data.round, player, marks: copyMarks(marks), step: event.step, revealed: true};
      }
      break;
    }
    case "picture_tiebreak": state.pictureTiebreak = {...data}; break;
  }
}

export function pictureActionText(phase, action) {
  let value;
  try { value = JSON.parse(action); } catch { return action; }
  if (phase === "picture_memorize") return value.memory || tr("기억 요약 없음", "No memory summary");
  if (phase === "picture_answer") return coordinates(value.marks ?? []);
  return action;
}

export function pictureEventText(type, data) {
  switch (type) {
    case "picture_setup": return tr("원본 관찰 → 그림 숨김 → 달라진 5곳 찾기 · 총 3라운드", "Observe → Hide → Find five changes · Three rounds");
    case "picture_phase": return `${roundText(data.round, data.overtime)} · ${stageText(data.stage)}`;
    case "picture_memory": return data.memory || tr("기억 요약 없음", "No memory summary");
    case "picture_marks": return `${data.player} · ${coordinates(data.marks ?? [])}`;
    case "picture_timeout": return tr(`${data.player} · ${data.seconds}초 제한 시간 초과`, `${data.player} · ${data.seconds}-second limit exceeded`);
    case "picture_result": return `${roundText(data.round, data.overtime)} · ${Object.entries(data.scores).map(([player, score]) => tr(`${player} ${score}점`, `${player} ${score} points`)).join(" · ")}`;
    case "picture_tiebreak": return tr(`동점자 연장전 · ${data.players.join(" · ")} · 생존 ${data.slots}자리`, `Tied-player overtime · ${data.players.join(" · ")} · ${data.slots} survival ${data.slots === 1 ? "place" : "places"}`);
  }
}

export function pictureSelection(state, players, selected, perspective = state.exilePerspective ?? "operator") {
  const phase = state.picturePhase;
  const revealed = phase?.stage === "reveal" && state.pictureResults?.some((result) => result.round === phase.round);
  const participant = players.includes(perspective) ? perspective : null;
  const owner = perspective === "operator" || revealed ? (players.includes(selected) ? selected : participant ?? players[0]) : participant;
  const memory = owner && (perspective === "operator" || perspective === owner) ? state.pictureMemories?.[owner] : null;
  const submission = owner ? state.pictureSubmissions?.[`${phase?.round}:${owner}`] : null;
  return {owner, memory, marks: submission && (revealed || perspective === "operator" || perspective === owner) ? submission.marks : [], revealed};
}

function Drawing({picture}) {
  if (picture.image) return <image className="spot-raster" href={picture.image} x="0" y="0" width={picture.width} height={picture.height} preserveAspectRatio="none" />;
  return (picture.shapes ?? []).map((shape, index) => {
    if (shape.kind === "rect") return <rect key={index} x={shape.x} y={shape.y} width={shape.w} height={shape.h} fill={shape.fill} />;
    if (shape.kind === "ellipse") return <ellipse key={index} cx={shape.x + shape.w / 2} cy={shape.y + shape.h / 2} rx={shape.w / 2} ry={shape.h / 2} fill={shape.fill} />;
    const points = shape.points.map((point) => point.join(",")).join(" ");
    if (shape.kind === "polygon") return <polygon key={index} points={points} fill={shape.fill} />;
    if (shape.kind === "line") return <polyline key={index} points={points} fill="none" stroke={shape.stroke} strokeWidth={shape.width} />;
    return null;
  });
}

function Picture({picture, marks, targets, ...props}) {
  return <svg {...props} viewBox={`0 0 ${picture.width} ${picture.height}`} data-picture-id={picture.id} role="img" aria-label={tr(`${themes[picture.theme] ?? picture.theme} 그림`, `${themes[picture.theme] ?? picture.theme} picture`)} shapeRendering={picture.image ? "auto" : "crispEdges"}>
    <Drawing picture={picture} />
    {targets.map((target) => {
      const bounds = {x: target.x, y: target.y, width: target.w, height: target.h};
      return <g key={target.id} className="spot-target" data-target={target.id} fill="none" strokeDasharray="10 6">
        <rect {...bounds} stroke="#111827" strokeWidth="9" />
        <rect {...bounds} stroke="#ff208c" strokeWidth="5" />
      </g>;
    })}
    {marks.map((mark, index) => {
      const cross = `M${mark.x - 16} ${mark.y - 16}l32 32m0-32l-32 32`;
      return <g key={index} className="spot-mark" data-correct={mark.correct} data-mark={`${mark.x},${mark.y}`} fill="none" strokeLinecap="round">
        <path d={cross} stroke="#111827" strokeWidth="16" />
        <path d={cross} stroke="#ffffff" strokeWidth="11" />
        <path d={cross} stroke={mark.correct === true ? "#39ff6a" : mark.correct === false ? "#ff3347" : "#00e5ff"} strokeWidth="7" />
      </g>;
    })}
  </svg>;
}

function PictureZoom({picture, marks, targets, phaseKey}) {
  const dialog = useRef(null);
  const title = useId();
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(false), [phaseKey]);
  useEffect(() => {
    if (open && picture) {
      if (!dialog.current.open) dialog.current.showModal();
    } else if (dialog.current.open) dialog.current.close();
  }, [open, picture]);
  return <>
    <button className="spot-zoom-button" type="button" aria-haspopup="dialog" disabled={!picture} onClick={() => setOpen(true)}>{tr("그림 확대", "Enlarge picture")}</button>
    <dialog className="spot-zoom-dialog" ref={dialog} aria-labelledby={title} onClose={() => setOpen(false)}>
      <header><h2 id={title}>{tr("현재 그림 확대", "Current picture enlarged")}</h2><form method="dialog"><button type="submit" aria-label={tr("확대 그림 닫기", "Close enlarged picture")}>{tr("닫기", "Close")}</button></form></header>
      {open && picture && <Picture picture={picture} marks={marks} targets={targets} />}
    </dialog>
  </>;
}

export function SpotScene({state, players, selected, onChoose}) {
  const phase = state.picturePhase;
  const {owner, marks, revealed} = pictureSelection(state, players, selected);
  const result = revealed ? state.pictureResults.findLast((result) => result.round === phase.round) : null;
  const picture = phase?.stage !== "blank" ? phase?.picture : null;
  const visibleMarks = phase?.stage === "observe" ? [] : marks;
  const targets = result?.targets ?? [];
  const perspective = state.exilePerspective ?? "operator";
  const statuses = Object.fromEntries(players.map((player) => {
    const out = state.result?.eliminated?.includes(player);
    const safe = state.result?.survivors?.includes(player);
    return [player, {status: out ? "eliminated" : safe ? "safe" : "assembling", label: out ? tr("탈락", "Eliminated") : safe ? tr("생존", "Survived") : tr(`${state.pictureTotals?.[player] ?? 0}점`, `${state.pictureTotals?.[player] ?? 0} points`), detail: out ? tr("탈락", "Eliminated") : safe ? tr("생존", "Survived") : undefined}];
  }));
  return <section className="exile-arena spot-arena pixel-frame" aria-label={tr("유배지 달라진 그림 찾기 세트장", "Exile Spot the Difference arena")}>
    <div className="exile-room">
      <ExileRoom title={tr("유배지 · 달라진 그림 찾기", "EXILE · SPOT THE DIFFERENCE")}
        label={tr("관찰 화면과 네 참가자의 발판", "Picture screen and four player platforms")}
        caption={phase ? `${roundText(phase.round, phase.overtime)} · ${stageText(phase.stage)}${owner && phase.stage !== "observe" && phase.stage !== "blank" ? tr(` · ${owner}의 표시`, ` · ${owner}’s marks`) : ""}` : tr("상위 2명이 생존합니다", "The top two survive")}>
        <g className="spot-screen">
          <rect x="124" y="103" width="392" height="264" fill="#0b121a" stroke="#6c716f" strokeWidth="4" />
          {picture ? <Picture x="128" y="107" width="384" height="256" picture={picture} marks={visibleMarks} targets={targets} /> :
            <g className="spot-screen-cover"><text x="320" y="226">{phase?.stage === "blank" ? tr("원본 그림이 사라졌습니다", "THE ORIGINAL IS HIDDEN") : tr("그림 공개 대기", "WAITING FOR THE PICTURE")}</text>
              <text x="320" y="260">{phase?.stage === "blank" ? tr(`${phase.blank_seconds}초 뒤 변경된 그림 공개`, `The changed picture follows after ${phase.blank_seconds} seconds`) : tr("원본을 기억하고 달라진 5곳을 찾으세요", "Remember the original and find five changes")}</text></g>}
        </g>
      </ExileRoom>
      <ExileCast players={players} selected={owner} onChoose={onChoose} statuses={statuses}
        canChoose={(player) => perspective === "operator" || revealed || perspective === player} />
    </div>
    <div className="spot-view-controls">
      <div className="exile-player-picker" role="group" aria-label={tr("표시 확인 참가자", "Player marks")}>
        {players.map((player) => <button key={player} type="button" aria-pressed={owner === player} disabled={perspective !== "operator" && !revealed && perspective !== player} onClick={() => onChoose(player)}>{player}</button>)}
      </div>
      <PictureZoom picture={picture} marks={visibleMarks} targets={targets} phaseKey={`${phase?.round}:${phase?.stage}`} />
    </div>
  </section>;
}

export function SpotStage({state, replay}) {
  const {players} = replay.match;
  const phase = state.picturePhase;
  const {owner, memory, marks, revealed} = pictureSelection(state, players, replay.selected, replay.view);
  const result = state.result;
  const latest = state.pictureResults?.findLast((entry) => entry.round === phase?.round);
  return <div className="spot-stage">
    <h2>{tr("달라진 그림 찾기", "Spot the Difference")}</h2>
    {!phase ? <div className="spot-rules"><h3>{tr("게임 규칙", "Game rules")}</h3>
      <p>{tr("원본을 3분간 관찰하고, 그림이 사라진 뒤 10초 후 달라진 그림을 봅니다. 2분 안에 바뀐 5곳을 찾아 표시합니다.", "Observe the original for three minutes. It disappears, and the changed picture follows ten seconds later. Mark up to five changed areas within two minutes.")}</p>
      <p>{tr("정답당 1점, 3라운드 총점 하위 2명이 탈락합니다. 생존 경계의 동점자는 원본 관찰 시간이 2분인 연장전을 진행합니다.", "Each correct mark scores one point. The bottom two after three rounds are eliminated. Boundary-tied players play overtime with a two-minute original observation phase.")}</p>
    </div> : <>
      <p className="spot-phase">{result ? tr("최종 결과", "Final results") : `${roundText(phase.round, phase.overtime)} · ${stageText(phase.stage)}`}</p>
      {!result && <ol className="spot-timing" aria-label={tr("라운드 진행 단계", "Round stages")}>
        <li data-active={phase.stage === "observe"}>{tr("관찰", "Observe")} <strong>{phase.observe_seconds}{tr("초", "s")}</strong></li>
        <li data-active={phase.stage === "blank"}>{tr("숨김", "Hidden")} <strong>{phase.blank_seconds}{tr("초", "s")}</strong></li>
        <li data-active={phase.stage === "answer"}>{tr("표시", "Mark")} <strong>{phase.answer_seconds}{tr("초", "s")}</strong></li>
      </ol>}
      {phase.overtime && <p className="spot-overtime">{tr(`동점자만 참가 · 생존 ${state.pictureTiebreak?.slots ?? 1}자리`, `Tied players only · ${state.pictureTiebreak?.slots ?? 1} survival places`)}</p>}
      <Table caption={result ? tr("최종 순위", "Final standings") : tr("정규 라운드 누적 점수", "Main-round total scores")} headers={tr(["참가자", "순위", "총점", "이번 점수", "상태"], ["Player", "Rank", "Total", "This round", "Status"])}
        rows={(result?.ranking ?? players).map((player) => {
          const total = result?.scores?.[player] ?? state.pictureTotals?.[player] ?? 0;
          const group = result?.ranking_groups?.find((group) => group.includes(player));
          const rank = result ? result.ranking.findIndex((name) => name === (group?.[0] ?? player)) + 1 : 1 + Object.values(state.pictureTotals ?? {}).filter((score) => score > total).length;
          return [player, rank, total, latest?.scores?.[player] ?? "–", result?.eliminated?.includes(player) ? tr("탈락", "Eliminated") : result?.survivors?.includes(player) ? tr("생존", "Survived") : phase.players.includes(player) ? tr("참가 중", "Playing") : tr("대기", "Waiting")];
        })} />
      {owner && <section className="spot-personal" aria-label={tr(`${owner}의 기억과 표시`, `${owner}’s memory and marks`)}>
        <h3>{tr(`${owner}의 기억`, `${owner}’s memory`)}</h3>
        <p className="spot-memory" lang={memory?.text && /[가-힣]/.test(memory.text) ? "ko" : undefined}>{memory?.text || tr("이 시점에 볼 수 있는 기억 요약이 없어요.", "No memory summary is visible at this point.")}</p>
        {phase.stage !== "observe" && phase.stage !== "blank" && <><h3>{tr(`${owner}의 표시`, `${owner}’s marks`)}</h3>
          <p className="spot-coordinate-list">{coordinates(marks)}</p>
          <p className="muted">{revealed ? tr("초록 X는 정답, 붉은 X는 오답이며 점선은 달라진 영역입니다.", "Green Xs are correct, red Xs are incorrect, and dashed outlines show changed areas.") : tr("정답 판정은 모든 참가자의 제출이 끝난 뒤 공개됩니다.", "Marks are judged publicly after everyone submits.")}</p></>}
      </section>}
      <p className="muted spot-guidance">{tr("그림 좌표는 왼쪽 위 (0, 0)부터 오른쪽 아래 (959, 639)까지입니다. X의 중심으로 판정합니다.", "Picture coordinates run from (0, 0) at the top left to (959, 639) at the bottom right. The center of each X is judged.")}</p>
    </>}
  </div>;
}

export function SpotInformation({state, replay}) {
  const [tab, setTab] = useState("rounds");
  const players = replay.match.players;
  const results = state.pictureResults ?? [];
  const {owner} = pictureSelection(state, players, replay.selected, replay.view);
  const submissions = Object.values(state.pictureSubmissions ?? {}).filter((entry) => !owner || entry.player === owner);
  return <aside className="caption spot-information" aria-label={tr("달라진 그림 찾기 결과와 기록", "Spot the Difference results and records")}>
    <TabList role="tablist" aria-label={tr("달라진 그림 찾기 정보 종류", "Spot the Difference information categories")} value={tab} onChange={setTab} size="sm" hasDivider>
      <Tab id="spot-rounds" value="rounds" label={tr("라운드 점수", "Round scores")} panelId="spot-records-panel" />
      <Tab id="spot-marks" value="marks" label={tr("표시 기록", "Mark history")} panelId="spot-records-panel" />
    </TabList>
    <div id="spot-records-panel" role="tabpanel" aria-labelledby={`spot-${tab}`}>
      {tab === "rounds" ? results.length ? <ol className="spot-history">{[...results].reverse().map((entry) => <li key={entry.round}>
        <button type="button" className="spot-round-link" onClick={() => replay.seek(entry.step)}>{roundText(entry.round, entry.overtime)} · {tr("그림·정답 보기", "View picture and answers")}</button>
        <Table caption={entry.overtime ? tr("연장전 점수 · 정규 총점에 미합산", "Overtime scores · Separate from main totals") : tr("라운드 점수", "Round scores")} headers={tr(["참가자", "정답", "정규 총점"], ["Player", "Correct", "Main total"])} rows={entry.players.map((player) => [player, entry.scores[player], entry.totals[player]])} />
      </li>)}</ol> : <p className="muted">{tr("아직 공개된 라운드 점수가 없어요.", "No round scores have been revealed yet.")}</p> : <>
        {owner && <h3>{tr(`${owner}의 표시 기록`, `${owner}’s mark history`)}</h3>}
        {submissions.length ? <ol className="spot-history">{[...submissions].reverse().map((entry) => <li key={`${entry.round}:${entry.player}`}>
          <button type="button" onClick={() => replay.seek(entry.step)}><strong>{roundText(entry.round, entry.round > 3)} · {entry.player}</strong><span>{coordinates(entry.marks)}</span>
            {entry.revealed && <small>{tr(`정답 ${entry.marks.filter((mark) => mark.correct).length}개`, `${entry.marks.filter((mark) => mark.correct).length} correct marks`)}</small>}</button>
        </li>)}</ol> : <p className="muted">{tr("볼 수 있는 표시 기록이 없어요.", "No mark submissions are visible.")}</p>}
      </>}
    </div>
  </aside>;
}
