import React, {useLayoutEffect, useRef, useState} from "react";
import {drawSprite, playerColor} from "./cast.js";
import {drawSet, rooms, roomWidth, setHeight, setPoint, setWidth, walkRoute} from "./floor.js";
import {tr} from "./locale.js";
import {locationName, scoreText} from "./replay.js";

const walkDuration = 540;
const statusLabels = {탈락: tr("탈락", "Eliminated"), 생활동: tr("생활동", "Living Quarters"), 감옥동: tr("감옥동", "Prison Wing")};

export function Sprite({player}) {
  const canvas = useRef(null);
  useLayoutEffect(() => {
    drawSprite(canvas.current, player);
  }, [player]);
  return <canvas ref={canvas} width={32} height={46} aria-hidden="true" />;
}

export function whisperRecipient(speech, players) {
  if (speech?.msg_type === "whisper" && Array.isArray(speech.visible_to)) {
    return speech.visible_to.find((name) => name !== speech.agent_name && players.includes(name));
  }
}

export function ArenaSpeech({speech, recipient}) {
  const panel = useRef(null);
  const [scrollable, setScrollable] = useState(false);
  useLayoutEffect(() => {
    const box = panel.current;
    box.scrollTop = 0;
    const measure = () => setScrollable(box.scrollHeight > box.clientHeight);
    measure();
    const resize = new ResizeObserver(measure);
    resize.observe(box);
    return () => resize.disconnect();
  }, [speech]);

  const text = speech?.text ?? speech?.content;
  return <section className="arena-speech" ref={panel} aria-label={tr("세트장 대화", "Arena conversation")} tabIndex={scrollable ? 0 : undefined}>
    {speech ? <>
      <strong>{speech.agent_name}{recipient && ` → ${recipient}`} · {speech.label}</strong>
      <p lang={/[가-힣]/.test(text) ? "ko" : undefined}>{text}</p>
    </> : <p className="muted">{tr("이 시점에 볼 수 있는 대화가 없어요.", "No conversation to show at this point.")}</p>}
  </section>;
}

function position(x, y) {
  return {left: x / setWidth * 100 + "%", top: y / setHeight * 100 + "%"};
}

function walk(button, points, width, height) {
  const [x, y] = points.at(-1);
  let distance = 0;
  const keyframes = points.map(([px, py], i) => {
    if (i) distance += Math.hypot(px - points[i - 1][0], py - points[i - 1][1]);
    const dx = (px - x) * width / setWidth;
    const dy = (py - y) * height / setHeight;
    return {transform: "translate(" + dx + "px," + dy + "px)", offset: distance};
  });
  if (!distance) return;
  for (const keyframe of keyframes) keyframe.offset /= distance;
  button.classList.add("walking");
  const animation = button.animate(keyframes, {duration: walkDuration, easing: "linear"});
  const settle = () => button.classList.remove("walking");
  animation.onfinish = settle;
  animation.oncancel = settle;
}

export function RoomScene({state, players, row, frame, following, selected, onChoose, playerDetails, label, standalone, drawMap = drawSet}) {
  const floor = useRef(null);
  const map = useRef(null);
  const previous = useRef({frame: -1, locations: {}, points: {}, pair: []});
  const counts = [0, 0, 0, 0, 0];
  for (const player of players) counts[state.locations[player] ?? 0]++;
  const speech = state.lastSpeech;
  const showSpeech = speech && frame - speech.step <= 5 &&
    (state.locations[speech.agent_name] ?? 0) === speech.room;
  const recipient = whisperRecipient(speech, players);
  const partner = recipient && (state.locations[recipient] ?? 0) === speech.room &&
    (state.locations[speech.agent_name] ?? 0) === speech.room ? recipient : undefined;
  const pair = partner ? [speech.agent_name, partner] : [];
  const points = Object.fromEntries(players.map((name, index) => [name, setPoint(state.locations[name] ?? 0, index)]));
  if (partner) {
    const speaker = speech.agent_name;
    const [speakerX, speakerY] = points[speaker];
    const [partnerX, partnerY] = points[partner];
    const centerX = (speakerX + partnerX) / 2;
    const centerY = (speakerY + partnerY) / 2;
    const gap = Math.min(36, Math.hypot(partnerX - speakerX, partnerY - speakerY) * 0.8);
    const speakerOnLeft = speakerX < partnerX || (speakerX === partnerX && speakerY <= partnerY);
    const direction = speakerOnLeft ? 1 : -1;
    points[speaker] = [centerX - direction * gap / 2, centerY];
    points[partner] = [centerX + direction * gap / 2, centerY];
  }

  useLayoutEffect(() => drawMap(map.current), [drawMap]);
  useLayoutEffect(() => {
    const scene = floor.current;
    const {width, height} = scene.getBoundingClientRect();
    const previousFrame = previous.current.frame;
    const animate = previousFrame >= 0 && frame > previousFrame &&
      !matchMedia("(prefers-reduced-motion: reduce)").matches;
    const nextFrame = frame === previousFrame + 1;
    for (const token of scene.querySelectorAll("[data-player]")) {
      const player = token.dataset.player;
      const fromRoom = previous.current.locations[player] ?? 0;
      const toRoom = state.locations[player] ?? 0;
      const from = previous.current.points[player];
      const to = points[player];
      const moved = from && (fromRoom !== toRoom || from[0] !== to[0] || from[1] !== to[1]);
      if (frame < previousFrame || moved) {
        for (const animation of token.getAnimations()) animation.cancel();
      }
      const whisperMovement = following && (pair.includes(player) || previous.current.pair.includes(player));
      if (animate && moved && (nextFrame || whisperMovement)) {
        const between = fromRoom === toRoom ? [] : walkRoute(fromRoom, toRoom, players.indexOf(player)).slice(1, -1);
        walk(token, [from, ...between, to], width, height);
      }
    }
    previous.current = {frame, locations: state.locations, points, pair};
  }, [frame, following, players, state.locations, pair, points]);

  return <div className="arena">
    <section className={`stage-window pixel-frame${standalone ? "" : " match-set"}${drawMap === drawSet ? "" : " pixel-map"}`} aria-label={label}>
      <div className="floor" ref={floor} aria-label={tr("네 개의 룸과 복도", "Four rooms and a hallway")}>
        <canvas ref={map} className="set-map" width={setWidth * 2} height={setHeight * 2} aria-hidden="true" />
        {rooms.map(({x, y}, index) => <span key={index} className="zone-label room-label"
          style={position(x + roomWidth / 2, y)}>{locationName(index + 1)} · {counts[index + 1]}{tr("명", "")}</span>)}
        <span className="zone-label hall-label">{locationName(0)} · {counts[0]}{tr("명", "")}</span>
        <div className="cast" aria-label={tr("세트장의 참가자", "Players in the arena")}>
          {players.map((player) => {
            const room = state.locations[player] ?? 0;
            const [x, y] = points[player];
            const score = state.scores[player];
            const {rank, status} = playerDetails?.get(player) ?? {};
            const label = [player, locationName(room), score == null ? null : `${scoreText(score)}${tr("점", " VP")}`,
              rank, statusLabels[status] ?? status].filter(Boolean).join(" · ");
            return <button key={player} className={row?.player === player ? "token acting" : "token"}
              type="button" data-player={player} data-room={room} data-status={status} aria-pressed={player === selected}
              data-speaking={showSpeech && player === speech.agent_name ? "true" : undefined}
              data-whispering={showSpeech && pair.includes(player) ? "true" : undefined}
              aria-label={label} title={label} style={{...position(x, y), zIndex: Math.floor(y)}}
              onClick={() => onChoose(player)}>
              <Sprite player={player} /><span>{player}</span>
            </button>;
          })}
        </div>
      </div>
    </section>
    <ArenaSpeech speech={showSpeech ? speech : null} recipient={recipient} />
  </div>;
}

export function BoardScene({board, state, players, selected}) {
  return <div className="board-view">
    <div className="board" role="img" aria-label={tr(`공원판 · 배치 성공 ${state.placed} / ${state.attempts}명`,
      `Park board · ${state.placed} of ${state.attempts} tiles placed`)}
      style={{"--cols": board[0].length}}>
      {board.flatMap((line, row) => [...line].map((marker, col) => {
        const key = [row, col].join();
        const player = state.cells.get(key);
        const obstacle = state.obstacles.get(key);
        const index = players.indexOf(player);
        const text = obstacle === "tree" ? "▲" : obstacle === "-" ? "−" : obstacle || (player ? index + 1 : "");
        const className = ["cell", marker !== "#" && "outside", player && "placed", player && player === selected && "selected"]
          .filter(Boolean).join(" ");
        const title = marker === "#" ? "(" + row + ", " + col + ")" + (player ? " · " + player : "") +
          (obstacle === "tree" ? tr(" · 가로수", " · Tree") : obstacle ? ` · ${obstacle}1 ${tr("맨홀", "manhole")}` : "") : undefined;
        return <span key={key} className={className} title={title}
          style={player ? {"--player": playerColor(player)} : undefined}>{text}</span>;
      }))}
    </div>
    <p className="legend"><span>{tr("▲ 가로수", "▲ Tree")}</span><span>{tr("+ / − 맨홀", "+ / − Manhole")}</span>
      <span>{tr("숫자 · 타일을 놓은 참가자", "Number · Player who placed the tile")}</span></p>
  </div>;
}
