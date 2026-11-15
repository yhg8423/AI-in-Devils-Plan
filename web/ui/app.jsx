import React, {useMemo, useState} from "react";
import {createRoot} from "react-dom/client";
import {Theme} from "@astryxdesign/core/theme";
import {neutralTheme} from "@astryxdesign/theme-neutral/built";
import {Button} from "@astryxdesign/core/Button";
import {IconButton} from "@astryxdesign/core/IconButton";
import {Selector} from "@astryxdesign/core/Selector";
import {Slider} from "@astryxdesign/core/Slider";
import {Tab, TabList} from "@astryxdesign/core/TabList";
import {snapshot, useReplay} from "./replay.js";
import {BoardScene, RoomScene, Sprite} from "./scene.jsx";
import {Participant, Records} from "./records.jsx";
import {MatchReplay} from "./match-replay.jsx";
import {CasePicker, Home, Mast, SiteFooter, runHref} from "./home.jsx";
import {InfoPage, infoPages} from "./info-pages.jsx";
import {LoadingStatus} from "./loading-status.jsx";
import {caseTitle} from "./cases.js";
import {en, gameTitle, language, siteTitle, tr} from "./locale.js";
import "@astryxdesign/core/reset.css";
import "@astryxdesign/core/astryx.css";
import "@astryxdesign/theme-neutral/theme.css";
import "./style.css";

const chapters = [
  ["before_choice", tr("첫 협상", "First negotiation")], ["talk", tr("두 번째 협상", "Second negotiation")],
  ["draft", tr("타일 선택", "Tile selection")], ["place", tr("타일 배치", "Tile placement")],
];

function CaseNavigation({replay}) {
  const {caseRecord, chosen, chooseRun} = replay;
  const selectorLabel = tr("매치 선택", "Choose a match");
  return <Selector label={selectorLabel} aria-label={selectorLabel} isLabelHidden size="sm" variant="secondary"
    value={chosen} options={caseRecord.matches.map(({id, game}) => ({value: id, label: gameTitle(game)}))}
    onChange={(id) => {
      if (!caseRecord.matches.some((match) => match.id === id)) return;
      window.history.replaceState(null, "", runHref(id, caseRecord.id));
      chooseRun(id);
    }} />;
}

function PixelIcon({name}) {
  return <span className="pixel-icon" data-icon={name} aria-hidden="true" />;
}

function Transport({replay}) {
  const [intervalInput, setIntervalInput] = useState(null);
  const max = replay.match?.steps.length ?? 0;
  const playing = replay.mode === "play";
  const full = replay.match?.format === "match";
  return <section className="transport" aria-label={tr("재생 조작", "Playback controls")}>
    <div className="transport-buttons">
      <IconButton className="play-control" variant="secondary" size="sm" label={playing ? tr("일시정지", "Pause") : tr("재생", "Play")}
        isDisabled={!max} icon={<PixelIcon name={playing ? "pause" : "play"} />} onClick={replay.togglePlay} />
      <IconButton variant="secondary" size="sm" label={tr("이전 행동", "Previous action")} isDisabled={replay.frame === 0}
        icon={<PixelIcon name="previous" />} onClick={() => replay.seek(replay.frame - 1)} />
      <IconButton variant="secondary" size="sm" label={tr("다음 행동", "Next action")} isDisabled={replay.frame === max}
        icon={<PixelIcon name="next" />} onClick={() => replay.seek(replay.frame + 1)} />
    </div>
    <div className="track">
      <Slider label={tr("재생 위치", "Playback position")} isLabelHidden valueDisplay="none" value={replay.frame}
        max={Math.max(1, max)} isDisabled={!max} width="100%" onChange={(value) => replay.seek(value)}
        formatValue={(value) => full ? tr(`${value}번째 기록`, `Event ${value}`) : tr(`${value}턴`, `Turn ${value}`)} />
    </div>
    <span className="counter">{replay.frame} / {max}</span>
    <div className="transport-settings">
      <label className="playback-interval">
        {tr("재생 간격", "Interval")}
        <input type="number" aria-label={tr("재생 간격(초)", "Playback interval in seconds")} inputMode="decimal" min="0.1" max="60" step="0.1"
          value={intervalInput ?? replay.playbackSeconds} disabled={!max}
          onChange={({currentTarget}) => {
            setIntervalInput(currentTarget.value);
            if (currentTarget.validity.valid && currentTarget.value !== "") {
              replay.setPlaybackSeconds(currentTarget.valueAsNumber);
            }
          }}
          onBlur={() => setIntervalInput(null)} />
        {tr("초", "sec")}
      </label>
      <Button label={tr("최신으로", "Jump to latest")} variant="ghost" size="sm" isDisabled={!max}
        aria-pressed={replay.mode === "follow"} onClick={replay.follow} />
    </div>
  </section>;
}

function Dialogue({event, players}) {
  if (!event) return <section className="caption caption-empty"><p>{tr("이 시점에 볼 수 있는 대화가 없어요.", "No conversation is visible at this point.")}</p></section>;
  const isPlayer = players.includes(event.agent_name);
  return <section className="caption" aria-label={tr("최근 플레이 기록", "Latest replay event")}>
    <div className="speaker">
      {isPlayer && <span className="portrait"><Sprite player={event.agent_name} /></span>}
      <div>
        <strong>{isPlayer ? event.agent_name : event.label}</strong>
        <small>{tr(`${event.step}턴`, `Turn ${event.step}`)} · {event.label}</small>
      </div>
    </div>
    <p>{event.text}</p>
  </section>;
}

function Replay({initialRun, caseId}) {
  const replay = useReplay(initialRun, caseId);
  const {match, frame, view} = replay;
  const loading = !match && replay.connection === "loading";
  const full = match?.format === "match";
  const players = useMemo(() => Object.keys(match?.scores ?? {}), [match]);
  const state = useMemo(() => match && !full ? snapshot(match, frame, view) : null, [match, full, frame, view]);
  const [drawer, setDrawer] = useState(false);
  const [tab, setTab] = useState("talk");

  function showRecords(nextTab) {
    setTab(nextTab);
    setDrawer(true);
  }
  function showPlayer(player) {
    replay.choosePlayer(player);
    setDrawer(false);
  }

  const chapterOptions = chapters.flatMap(([phase, label]) => {
    const start = match?.steps.findIndex((row) => row.phase === phase) ?? -1;
    return start >= 0 ? [{value: String(start + 1), label}] : [];
  });
  const status = replay.connection === "error" ? tr("연결 끊김", "Connection lost") :
    replay.connection === "empty" ? tr("플레이 기록 대기 중", "Waiting for a replay") :
    replay.connection === "missing" ? tr("플레이 기록을 찾을 수 없어요", "Replay not found") :
    match?.complete ? tr("플레이 종료", "Run complete") :
    replay.mode === "follow" ? tr("실시간 추적 중", "Following live") : tr("다시 보기", "Replay");
  const live = Boolean(match && !match.complete && replay.mode === "follow" && replay.connection === "ready");
  const cue = state?.lastSpeech ?? state?.feed.at(-1);

  return <>
    <Mast replayPosition={match ? replay : undefined}>
      {replay.caseRecord && <CaseNavigation replay={replay} />}
    </Mast>
    {loading ? <main className="shell replay-loading"><LoadingStatus /></main> :
    !match ? <main className="shell replay"><p className="empty" role="status">{status}</p></main> :
    full ? <MatchReplay key={replay.id} replay={replay} caseName={replay.caseRecord && caseTitle(replay.caseRecord)}
      transport={<Transport replay={replay} />} /> : <>
    <main className="shell replay">
      <div className="heading">
        <div className="match-title"><h1>{gameTitle("잔디 깔기")}</h1><span>{gameTitle("1일차 · 양자택일")}</span></div>
        <TabList role="tablist" aria-label={tr("세트장과 공원판", "Set and game board")} size="sm" value={replay.scene} onChange={replay.chooseScene}>
          <Tab id="tab-rooms" value="rooms" label={tr("세트장", "Set")} panelId="scene" />
          <Tab id="tab-board" value="board" label={tr("공원판", "Park board")} panelId="scene" />
        </TabList>
      </div>
      <div id="scene" role="tabpanel" aria-labelledby={"tab-" + replay.scene}>
        {replay.scene === "rooms" ?
          <RoomScene key={replay.id} state={state} players={players} row={replay.row} frame={frame} following={replay.mode === "follow"}
            selected={replay.selected} onChoose={showPlayer} label={tr("잔디 깔기 세트장", "Lay the Grass set")} standalone /> :
          <section className="stage-window pixel-frame">
            <BoardScene board={match.board} state={state} players={players} selected={replay.selected} />
          </section>}
      </div>
      <Transport replay={replay} />
      <div className="context">
        <div className="context-start">
          <strong>{replay.phaseLabel}</strong>
          <Selector label={tr("구간 이동", "Jump to section")} aria-label={tr("구간 이동", "Jump to section")} isLabelHidden size="sm" variant="ghost" value=""
            isDisabled={!chapterOptions.length} options={[{value: "", label: tr("구간 이동", "Jump to section")}, ...chapterOptions]}
            onChange={(value) => { if (value) replay.seek(Number(value), true); }} />
        </div>
        <div className="context-end">
          {view !== "public" && <span className="status">{view === "operator" ? tr("운영자 시점", "Operator view") : tr(`${view} 시점`, `${view} view`)}</span>}
          <span className={live ? "status live" : "status"} role="status">{status}</span>
          <Button label={tr("플레이 기록", "Replay log")} variant="secondary" size="sm" icon={<PixelIcon name="record" />}
            onClick={() => showRecords("talk")} />
        </div>
      </div>
      {state && replay.selected ?
        <Participant key={replay.selected} state={state} player={replay.selected}
          onSeek={replay.seek} onClose={() => replay.choosePlayer("")} /> :
        <Dialogue event={cue} players={players} />}
    </main>
    <Records replay={replay} state={state} players={players} tab={tab} onTab={setTab}
      open={drawer} onOpenChange={setDrawer} onPlayer={showPlayer} />
    </>}
  </>;
}

const params = new URLSearchParams(window.location.search);
const run = params.get("run");
const caseId = params.get("case");
const page = params.get("page");
const showInfo = Object.hasOwn(infoPages, page);
document.documentElement.lang = language;
document.title = showInfo ? `${infoPages[page].label} · ${siteTitle}` : siteTitle;
if (en) document.querySelector('meta[name="description"]').content =
  "What if AI played The Devil’s Plan Season 3? Replay the choices, conversations, and strategies of 16 AI players.";

function Site() {
  const [casePickerGame, setCasePickerGame] = useState(() => !showInfo && !run && window.location.hash === "#matches" ? "" : null);
  const openCasePicker = (game = "") => setCasePickerGame(game);
  function closeCasePicker() {
    setCasePickerGame(null);
    if (!showInfo && !run && window.location.hash === "#matches") {
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
      window.dispatchEvent(new Event("hashchange"));
      document.getElementById("watch-from-day-one")?.focus({preventScroll: true});
    }
  }
  return <Theme theme={neutralTheme} mode="dark">
    <div className="site-layout">
      {showInfo ? <><Mast currentPage={page} /><InfoPage page={page} /></> :
        !run ? <Home onChooseCase={openCasePicker} /> : <Replay initialRun={run} caseId={caseId} />}
      <SiteFooter currentPage={showInfo ? page : undefined} />
      {!showInfo && !run && <CasePicker game={casePickerGame} onClose={closeCasePicker} />}
    </div>
  </Theme>;
}

createRoot(document.getElementById("root")).render(<Site />);
