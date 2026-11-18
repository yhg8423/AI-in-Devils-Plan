import React, {useLayoutEffect, useRef} from "react";
import {setHeight, setWidth} from "./floor.js";
import {tr} from "./locale.js";
import {ArenaSpeech, Sprite, whisperRecipients} from "./scene.jsx";

const center = [setWidth / 2, setHeight / 2];
const rouletteAngles = Array.from({length: 6}, (_, index) => index * Math.PI / 3 - Math.PI / 2);
const inspectionStates = {
  marked: {symbol: "", label: tr("총알", "Marked")},
  empty: {symbol: "X", label: tr("빈칸", "Empty")},
  unknown: {symbol: "?", label: tr("미확인", "Unknown")},
};

function inspectionLabel(slot, status) {
  return tr(`${slot}번 ${inspectionStates[status].label}`, `Slot ${slot}: ${inspectionStates[status].label}`);
}

function polar(radius, angle) {
  return [center[0] + radius * Math.cos(angle), center[1] + radius * Math.sin(angle)];
}

const seatPoints = rouletteAngles.map((angle) => {
  const [x, y] = polar(122, angle);
  return [x, y + 15];
});

function position(x, y) {
  return {left: `${x / setWidth * 100}%`, top: `${y / setHeight * 100}%`};
}

export function RouletteInspection({slots = {}, offset = 0, compact = false}) {
  const cells = rouletteAngles.map((_, index) => {
    const slot = index + 1;
    const status = slots[slot] === true ? "marked" : slots[slot] === false ? "empty" : "unknown";
    return {slot, status, angle: rouletteAngles[(index + offset) % rouletteAngles.length]};
  });
  const label = cells.map(({slot, status}) => inspectionLabel(slot, status)).join(", ");
  return <span className={compact ? "roulette-inspection compact" : "roulette-inspection ring"} role="img" aria-label={label}>
    {cells.map(({slot, status, angle}) => <span key={slot} className="inspection-cell" data-slot={slot} data-state={status}
      aria-hidden="true" title={inspectionLabel(slot, status)}
      style={compact ? undefined : {left: `${50 + 34 * Math.cos(angle)}%`, top: `${50 + 34 * Math.sin(angle)}%`}}>
      <span className="inspection-number">{slot}</span><span className="inspection-symbol" data-state={status}>{inspectionStates[status].symbol}</span>
    </span>)}
  </span>;
}

export function RouletteInspectionLegend() {
  return <p className="inspection-legend">{Object.entries(inspectionStates).map(([status, {symbol, label}]) =>
    <span key={status}><span className="inspection-symbol" data-state={status} aria-hidden="true">{symbol}</span> {label}</span>)}</p>;
}

function drawRouletteSet(canvas) {
  const context = canvas.getContext("2d");
  const [cx, cy] = center;
  const concrete = context.createRadialGradient(cx, cy, 90, cx, cy, 260);
  concrete.addColorStop(0, "#435666");
  concrete.addColorStop(0.6, "#2a3b4c");
  concrete.addColorStop(1, "#121b25");
  context.fillStyle = concrete;
  context.fillRect(0, 0, setWidth, setHeight);
  for (let y = 8; y < setHeight; y += 24) {
    context.fillStyle = "#8ca1b00d";
    context.fillRect(0, y, setWidth, 1);
    for (let x = 16 + y % 48; x < setWidth; x += 48) context.fillRect(x, y, 1, 24);
  }

  function disc(radius, fill) {
    context.beginPath();
    context.arc(cx, cy, radius, 0, 2 * Math.PI);
    context.fillStyle = fill;
    context.fill();
  }
  disc(136, "#53697b");
  disc(134, "#263747");
  disc(64, "#162735");
  disc(60, "#71c6e6");
  disc(57, "#a8e6f7");
  disc(29, "#5ca8c6");

  for (const angle of rouletteAngles) {
    const [x, y] = polar(122, angle);
    context.save();
    context.translate(x, y);
    context.rotate(angle + Math.PI / 2);
    context.fillStyle = "#131d27";
    context.fillRect(-29, -19, 60, 42);
    context.fillStyle = "#596e7e";
    context.fillRect(-28, -20, 56, 35);
    context.fillStyle = "#273949";
    context.fillRect(-25, -17, 50, 29);
    context.fillStyle = "#6f8aa1";
    context.fillRect(-11, -11, 22, 12);
    context.fillStyle = "#344d63";
    context.fillRect(-9, -9, 18, 7);
    context.restore();
  }
}

function Venue({label, draw, children}) {
  const canvas = useRef(null);
  useLayoutEffect(() => draw(canvas.current), [draw]);
  return <section className="stage-window pixel-frame match-set day-two-set" aria-label={label}>
    <div className="floor">
      <canvas ref={canvas} className="set-map" width={setWidth} height={setHeight} aria-hidden="true" />
      {children}
    </div>
  </section>;
}

function Seat({player, point, label, status, selected, acting, speaking, whispering, onChoose}) {
  return <button type="button" className={`token day-two-seat${acting ? " acting" : ""}`}
    style={position(...point)} aria-label={label} title={label} aria-pressed={player === selected}
    data-status={status} data-speaking={speaking || undefined} data-whispering={whispering || undefined}
    onClick={() => onChoose(player)}>
    <Sprite player={player} /><span>{player}</span>
  </button>;
}

export function RouletteScene({players, state, frame, selected, onChoose}) {
  const offset = state.seats?.indexOf(state.first) ?? 0;
  const active = state.feed.at(-1)?.agent_name;
  const speech = state.feed.findLast(({msg_type, step}) =>
    frame - step <= 5 && (msg_type === "public" || msg_type === "whisper"));
  const recipients = whisperRecipients(speech, players);
  return <div className="arena">
    <Venue draw={drawRouletteSet} label={tr("러시안 룰렛 감옥 매치 세트장", "Russian Roulette prison match arena")}>
    {state.seats && <div className="roulette-board" role="img" aria-label={tr(`1번 칸 · ${state.first} 방향`, `Slot 1 · facing ${state.first}`)}>
      {rouletteAngles.map((angle, index) => {
        const slot = (index - offset + rouletteAngles.length) % rouletteAngles.length + 1;
        return <span key={index} className="roulette-slot" data-first={slot === 1 || undefined} aria-hidden="true"
          style={position(...polar(43, angle))}>{slot}</span>;
      })}
      <span className="roulette-pointer" aria-hidden="true" style={{"--rotation": `${offset * 60}deg`}} />
    </div>}
    {state.seats?.map((player, index) => {
      const status = state.result?.eliminated.includes(player) ? "탈락" : player === state.leader ? "선" : null;
      const slot = (index - offset + rouletteAngles.length) % rouletteAngles.length + 1;
      const speaking = player === speech?.agent_name;
      return <Seat key={player} player={player} point={seatPoints[index]}
        label={[player, tr(`${slot}번 칸`, `Slot ${slot}`), tr(status, {탈락: "Eliminated", 선: "Lead player"}[status])].filter(Boolean).join(" · ")}
        status={status} selected={selected} acting={active === player} speaking={speaking}
        whispering={recipients.length > 0 && (speaking || recipients.includes(player))} onChoose={onChoose} />;
    })}
    </Venue>
    <ArenaSpeech speech={speech} recipients={recipients} />
  </div>;
}
