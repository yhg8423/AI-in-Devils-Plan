import {useEffect, useState} from "react";
import {en, language, tr} from "./locale.js";

export const phaseNames = {
  choice_2_negotiation: tr("팀 구성 협상", "Team formation talks"),
  choice_4_negotiation: tr("공공의 이익 협상", "Public benefit talks"),
  choice_9_negotiation: tr("피스 모금 협상", "Piece pledge talks"),
  cubes: tr("큐브 세기", "Cube Counting"), representative: tr("팀 대표 투표", "Vote for a team representative"),
  memory_poker: tr("포커 카드 선택", "Choose poker cards"), rectangles: tr("네모 세기", "Rectangle Counting"),
  rectangle_challenge: tr("추가 네모 대결", "Extra rectangle challenge"), memorize: tr("카드 암기", "Memorize cards"),
  nominate: tr("대결 상대 지목", "Nominate an opponent"), alliance: tr("연맹의 징표", "Alliance Token"),
  submit: tr("카드와 칩 제출", "Submit card and chip"), trade: tr("주문", "Place an order"),
  secret: tr("시크릿 예약", "Reserve a Secret"), piece: tr("피스 사용", "Use a Piece"), market_turn: tr("거래소", "Stock exchange"),
  credit: tr("크레딧 사용", "Spend credits"), swap: tr("조작 위치 선택", "Choose slots to swap"),
  roulette_talk: tr("러시안 룰렛 대화", "Russian Roulette conversation"), roulette_reflection: tr("행동 후 복기", "Post-action reflection"),
  before_choice: tr("선택 5 전 협상", "Talks before Choice 5"), choice_five: tr("선택 5 · 점수 또는 정보", "Choice 5 · Points or information"),
  plan: tr("미리보기 계획", "Preview plan"), talk: tr("미리보기 후 협상", "Talks after the preview"),
  draft: tr("타일 선택", "Choose a tile"), stance: tr("선택 6 · 공격 또는 방어", "Choice 6 · Attack or defend"),
  partner: tr("선택 7 · 상생 또는 견제", "Choice 7 · Cooperate or compete"),
  obstacle: tr("선택 8 · 가로수 또는 맨홀", "Choice 8 · Tree or manhole"),
  manhole: tr("맨홀 설치", "Place a manhole"), tree: tr("가로수 설치", "Plant a tree"),
  place: tr("타일 배치", "Place a tile"), split: tr("상생 점수 정산", "Settle cooperation points"),
};
const channels = {public: tr("전체", "Public"), room: tr("룸 발언", "Room chat"), whisper: tr("귓속말", "Whisper")};
const invitationLabels = {room_invite: tr("룸 초대", "Room invite"), room_invite_response: tr("초대 응답", "Invite response")};
const boardPhases = new Set(["manhole", "tree", "place", "split"]);
export function scoreText(score) {
  return score > 0 ? "+" + score : String(score);
}

export function locationName(room) {
  return room ? tr(`${room}번룸`, `Room ${room}`) : tr("복도", "Hallway");
}

export function formatRoomRecord(text) {
  return text.replace(/([1-4])번\s*논의실/g, "$1번룸");
}

export function roomRecordText(text, type) {
  const normalized = formatRoomRecord(text);
  if (!en) return normalized;
  if (type === "room_move") {
    return normalized.replace(/→\s*(?:([1-4])번룸|복도)$/, (_, room) => `→ ${locationName(Number(room) || 0)}`);
  }
  const invite = normalized.match(/^초대 #(\d+) · ([1-4])번룸 · ([\s\S]*)$/);
  if (!invite) return normalized;
  const [, id, room, message] = invite;
  const response = type === "room_invite_response" ? {수락: "Accepted", 거절: "Declined"}[message] : undefined;
  return `Invite #${id} · ${locationName(Number(room))} · ${response ?? message}`;
}

export function decisionNoteLabel(phase) {
  const choice = phase.match(/^choice_(\d+)/)?.[1];
  const label = phaseNames[phase] ?? (choice ? tr(`선택 ${choice}`, `Choice ${choice}`) : tr("선택", "Decision"));
  return label + tr(" · 전략", " · Strategy");
}

const relationshipCheckpoints = {
  "이전 매치에서 이어받음": "Carried over from the previous match", "매치 종료": "End of match",
  "팀 구성 및 네모 세기 결과": "Teams and Rectangle Counting results", "선택 4 투표 공개": "Choice 4 votes revealed",
  "선택 5 전 협상 종료": "End of negotiations before Choice 5", "미리보기 후 협상 종료": "End of negotiations after the preview",
  "잔디 깔기 배치 전 협상 종료": "End of talks before tile placement", "잔디 깔기 결과": "Lay the Grass results",
  "선택 9 모금 결과": "Choice 9 pledge results", "무거운 13 전반 종료": "End of the first half of Heavy 13",
};

export function checkpointLabel(checkpoint, translated) {
  if (!en || !checkpoint) return checkpoint;
  const round = checkpoint.match(/^(거래소|러시안 룰렛) (\d+)라운드 종료$/);
  if (round) return `End of round ${round[2]} · ${round[1] === "거래소" ? "Mystery Stock Exchange" : "Russian Roulette"}`;
  return relationshipCheckpoints[checkpoint] ?? translated ?? checkpoint;
}

export function grassBonusText(content) {
  return en ? content.replace(/^견제 \+5점 · /, "Compete bonus: +5 VP · ")
    .replace(/^상생 분배 미합의 · /, "No agreement on cooperation points · ")
    .replace(/^상생 · /, "Cooperation · ") : content;
}

export function eventText(event, fallback = event.content) {
  return en ? event.translation?.text ?? fallback : fallback;
}

export function eventFields(event, data) {
  if (!en || !event.translation?.fields) return data;
  function applyFields(value, fields) {
    if (typeof value === "string") return typeof fields === "string" ? fields : value;
    if (Array.isArray(value)) return Array.isArray(fields) ? value.map((item, index) => applyFields(item, fields[index])) : value;
    if (value && typeof value === "object" && fields && typeof fields === "object") {
      return Object.fromEntries(Object.entries(value).map(([key, item]) =>
        [key, Object.hasOwn(fields, key) ? applyFields(item, fields[key]) : item]));
    }
    return value;
  }
  return applyFields(data, event.translation.fields);
}

export function snapshot(match, frame, perspective) {
  const state = {
    scores: {...match.scores}, locations: {}, tiles: {}, cells: new Map(), obstacles: new Map(),
    choices: {}, participantRecords: [], feed: [], lastSpeech: null, placed: 0, attempts: 0,
  };
  for (const [index, row] of match.steps.slice(0, frame).entries()) {
    if (index && match.steps[index - 1].phase !== row.phase && ["choice_five", "draft"].includes(row.phase)) {
      state.locations = {};
      state.lastSpeech = null;
    }
    for (const event of row.events) {
      const {msg_type: type, agent_name: player, content} = event;
      if (event.visible_to !== "all" && perspective !== "operator"
          && !event.visible_to.includes(perspective)) continue;
      const record = (label, text = eventText(event)) => ({...event, step: row.step ?? index + 1, label, text});
      if (state.lastSpeech?.msg_type === "whisper" && (type === "room_move" || type in invitationLabels)) {
        state.lastSpeech = null;
      }
      if (type === "negotiation_start" || type === "negotiation_end") {
        state.locations = {};
        state.lastSpeech = null;
      } else if (type === "scoreboard") {
        state.scores = JSON.parse(content);
      } else if (type === "room_move") {
        state.locations[player] = Number(formatRoomRecord(content).match(/→\s*([1-4])번룸/)?.[1] ?? 0);
        state.feed.push(record(tr("이동", "Move"), eventText(event, roomRecordText(content, type))));
      } else if (type in channels) {
        const room = state.locations[player] ?? 0;
        const label = type === "room" && room ? `${locationName(room)}${tr(" 발언", " chat")}` : channels[type];
        const speech = {...record(label), room};
        state.feed.push(speech);
        state.lastSpeech = speech;
      } else if (type in invitationLabels) {
        state.feed.push(record(invitationLabels[type], eventText(event, roomRecordText(content, type))));
      } else if (type === "discussion_note") {
        state.participantRecords.push(record(`${phaseNames[row.phase]} · ${tr(`${row.round}턴 전략`, `Turn ${row.round} strategy`)}`));
      } else if (type === "grass_plan") {
        state.participantRecords.push(record(tr("미리보기 직후 계획", "Plan after the preview")));
      } else if (type === "decision_note") {
        const {phase, note} = JSON.parse(content);
        state.participantRecords.push(record(decisionNoteLabel(phase), eventFields(event, {note}).note));
      } else if (type === "grass_tile") {
        state.tiles[player] = Number(content);
        state.participantRecords.push(record(phaseNames.draft, tr(`${content}번 타일`, `Tile ${content}`)));
      } else if (type === "grass_choices") {
        const {choice, decisions} = JSON.parse(content);
        state.choices[choice] = decisions;
        for (const [agent_name, decision] of Object.entries(decisions)) {
          state.participantRecords.push({...record(tr(`선택 ${choice}`, `Choice ${choice}`), decision), agent_name});
        }
      } else if (type === "grass_obstacle") {
        const obstacles = Object.entries(JSON.parse(content));
        for (const [kind, cell] of obstacles) state.obstacles.set(cell.join(), kind);
        const text = obstacles.map(([kind, cell]) =>
          `${kind === "tree" ? tr("가로수", "Tree") : tr(`맨홀 ${kind}1`, `${kind}1 manhole`)} (${cell.join(", ")})`).join(" · ");
        state.participantRecords.push(record(tr("장애물 설치", "Place an obstacle"), text));
      } else if (type === "grass_placement") {
        const placement = JSON.parse(content);
        state.attempts++;
        state.placed += Number(Boolean(placement.placement));
        for (const cell of placement.cells) state.cells.set(cell.join(), player);
        const result = placement.placement ? tr("배치 성공", "Placed") : tr("배치 실패", "Placement failed");
        const text = [tr(`${placement.tile}번`, `Tile ${placement.tile}`), result,
          `${scoreText(placement.points)}${tr("점", " VP")}`].join(" · ");
        state.feed.push(record(tr("배치", "Placement"), text));
      } else if (type === "grass_bonus") {
        state.feed.push(record(tr("정산", "Settlement"), eventText(event, grassBonusText(content))));
      }
    }
  }
  return state;
}

const emptyReplay = {id: "", match: null, frame: 0, mode: "follow", stage: "", view: "operator", selected: ""};
const staticBuild = typeof STATIC_REPLAY_BUILD !== "undefined" && STATIC_REPLAY_BUILD;

async function getJSON(url, signal) {
  const response = await fetch(url, {cache: staticBuild ? "default" : "no-store", signal});
  if (!response.ok) throw new Error(String(response.status));
  return response.json();
}

export function fetchCases(signal) {
  return getJSON(staticBuild ? "/replays/cases.json" : "/api/cases", signal);
}

async function fetchMatch(id, signal) {
  if (!staticBuild) return getJSON(`/api/match?run=${encodeURIComponent(id)}${en ? "&lang=en" : ""}`, signal);

  const segments = id.split("/");
  if (segments.some((segment) => !segment || segment === "." || segment === ".." || segment.includes("\\"))) {
    throw new Error("404");
  }
  const path = segments.map(encodeURIComponent).join("/");
  return getJSON(`/replays/${path}/${language}.json`, signal);
}

export function useReplay(initialRun, caseId) {
  const params = new URLSearchParams(window.location.search);
  const requestedFrame = Number(params.get("at"));
  const initialFrame = Number.isSafeInteger(requestedFrame) && requestedFrame >= 0 ? requestedFrame : 0;
  const initialView = params.get("view");
  const initialPlayer = params.get("player");
  const [caseRecord, setCaseRecord] = useState(null);
  const [{id: chosen, fromStart}, select] = useState({id: initialRun, fromStart: true});
  const [replay, setReplay] = useState(emptyReplay);
  const [connection, setConnection] = useState("loading");
  const [playbackSeconds, setPlaybackSeconds] = useState(1);
  const current = replay.id === chosen ? replay : emptyReplay;

  useEffect(() => {
    const controller = new AbortController();
    const {signal} = controller;
    let timeout;

    async function poll() {
      try {
        const cases = await fetchCases(signal);
        if (signal.aborted) return;
        const activeCase = cases.find((record) => (!caseId || caseId === record.id) &&
          record.matches.some((match) => match.id === chosen)) ?? null;
        setCaseRecord((old) => JSON.stringify(old) === JSON.stringify(activeCase) ? old : activeCase);
        if (caseId && !activeCase) {
          setReplay(emptyReplay);
          setConnection("missing");
          return;
        }
        const data = await fetchMatch(chosen, signal);
        if (signal.aborted) return;
        if (!data.format && !data.scores) {
          setReplay(emptyReplay);
          setConnection("empty");
          return;
        }
        setConnection("ready");
        setReplay((old) => {
          if (old.id !== chosen) {
            const players = data.players ?? Object.keys(data.scores ?? {});
            const view = fromStart && (initialView === "public" || players.includes(initialView)) ? initialView : "operator";
            const selected = fromStart && players.includes(initialPlayer) ? initialPlayer : "";
            return {...emptyReplay, id: chosen, match: data,
              frame: fromStart ? Math.min(initialFrame, data.steps.length) : data.steps.length, view, selected,
              mode: fromStart ? "paused" : "follow"};
          }
          if (old.match.steps.length === data.steps.length && old.match.complete === data.complete &&
              old.match.translation_version === data.translation_version &&
              old.match.next_match?.id === data.next_match?.id && old.match.next_match?.game === data.next_match?.game) {
            return old;
          }
          const frame = old.mode === "follow" ? data.steps.length : Math.min(old.frame, data.steps.length);
          return {...old, match: data, frame};
        });
      } catch (error) {
        if (!signal.aborted) {
          if (error.message === "404") {
            setReplay(emptyReplay);
            setConnection("missing");
          } else setConnection("error");
        }
      } finally {
        if (!staticBuild && !signal.aborted) timeout = setTimeout(poll, 1800);
      }
    }

    poll();
    return () => {
      controller.abort();
      clearTimeout(timeout);
    };
  }, [caseId, chosen, fromStart, initialFrame, initialView, initialPlayer]);

  useEffect(() => {
    if (current.mode !== "play") return;
    const timer = setInterval(() => {
      setReplay((old) => {
        if (old.id !== chosen || old.mode !== "play") return old;
        if (old.frame < old.match.steps.length) return {...old, frame: old.frame + 1};
        return {...old, mode: old.match.complete || old.match.interrupted ? "paused" : "follow"};
      });
    }, playbackSeconds * 1000);
    return () => clearInterval(timer);
  }, [chosen, current.mode, playbackSeconds]);

  const change = (update) => setReplay((old) => old.match && old.id === chosen ? update(old) : old);
  const seek = (step, useDefaultScene = false) => change((old) => ({
    ...old, mode: "paused", stage: useDefaultScene ? "" : old.stage,
    frame: Math.max(0, Math.min(step, old.match.steps.length)),
  }));
  const chooseRun = (id) => {
    if (id === chosen) return;
    setConnection("loading");
    select({id, fromStart: false});
  };
  const follow = () => change((old) => ({...old, mode: "follow", stage: "", frame: old.match.steps.length}));
  const togglePlay = () => change((old) => {
    if (!old.match.steps.length) return old;
    if (old.mode === "play") return {...old, mode: "paused"};
    return {...old, mode: "play", stage: "", frame: old.frame === old.match.steps.length ? 0 : old.frame};
  });
  const chooseScene = (stage) => change((old) => ({...old, stage}));
  const choosePlayer = (selected) => change((old) => ({...old, selected}));
  const chooseView = (view) => change((old) => ({
    ...old, view, selected: (old.match.players ?? Object.keys(old.match.scores ?? {})).includes(view) ? view : old.selected,
  }));

  const row = current.match?.steps[current.frame - 1];
  const scene = current.stage || (boardPhases.has(row?.phase) ? "board" : "rooms");
  const phase = phaseNames[row?.phase] ?? row?.phase ?? tr("플레이 시작", "Play begins");
  const phaseLabel = ["before_choice", "talk"].includes(row?.phase)
    ? `${phase} · ${tr(`${row.round}/${current.match.rounds}턴`, `Turn ${row.round}/${current.match.rounds}`)}` : phase;
  return {
    ...current, caseRecord, chosen, connection, row, scene, phaseLabel, playbackSeconds, setPlaybackSeconds,
    chooseRun, seek, follow, togglePlay, chooseScene, choosePlayer, chooseView,
  };
}
