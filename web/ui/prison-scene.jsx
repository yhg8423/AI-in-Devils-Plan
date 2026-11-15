import React, {useLayoutEffect, useRef} from "react";
import {chipColorLabel} from "./heavy-13.js";
import {tr} from "./locale.js";
import {setHeight, setWidth} from "./floor.js";
import {Sprite} from "./scene.jsx";

const tableRim = [[96, 166], [68, 191], [90, 224], [180, 256], [332, 256], [422, 224], [444, 191], [416, 166]];
const tableOpening = [[149, 173], [137, 187], [155, 203], [207, 221], [305, 221], [357, 203], [375, 187], [363, 173]];
const seats = [[455, 175], [468, 222], [416, 269], [256, 302], [96, 269], [44, 222], [57, 175]];
const stands = [
  {color: "빨강", x: 222, face: "#ed7888", edge: "#762e45"},
  {color: "초록", x: 256, face: "#a2d39c", edge: "#42674c"},
  {color: "파랑", x: 290, face: "#83c3e8", edge: "#346487"},
];

function drawPrisonSet(canvas) {
  const context = canvas.getContext("2d");
  function rect(x, y, width, height, fill) {
    context.fillStyle = fill;
    context.fillRect(x, y, width, height);
  }
  function polygon(points, fill, stroke) {
    context.beginPath();
    context.moveTo(...points[0]);
    for (const point of points.slice(1)) context.lineTo(...point);
    context.closePath();
    context.fillStyle = fill;
    context.fill();
    if (stroke) {
      context.strokeStyle = stroke;
      context.stroke();
    }
  }

  rect(0, 0, setWidth, setHeight, "#0c1219");
  const floor = context.createLinearGradient(0, 155, 0, setHeight);
  floor.addColorStop(0, "#121b26");
  floor.addColorStop(0.58, "#303c49");
  floor.addColorStop(1, "#18212e");
  polygon([[0, 184], [155, 143], [357, 143], [512, 184], [512, 348], [0, 348]], floor, "#2c3640");
  for (const x of [0, 83, 172, 256, 340, 429, 512]) {
    polygon([[256 + (x - 256) * 0.46, 150], [x, 348], [x + 2, 348]], "#11192385");
  }
  for (const y of [252, 297, 330]) rect(0, y, setWidth, 1, "#77859522");

  // Steel mullions and dim reflections in the dark panes behind the table.
  for (const [index, x] of [0, 53, 115, 179, 332, 397, 459].entries()) {
    const glass = context.createLinearGradient(x, 0, x + 52, 136);
    glass.addColorStop(0, "#1b2735");
    glass.addColorStop(0.5, "#0b131b");
    glass.addColorStop(1, "#202d37");
    rect(x, 0, index === 3 ? 29 : 54, 153, glass);
    const lightY = [31, 46, 25, 39, 37, 27, 45][index];
    rect(x + 8, lightY, 28, 13, "#384966");
    rect(x + 9, lightY + 1, 26, 7, "#7e8dac");
    rect(x + 11, lightY + 2, 20, 2, "#a5aec4");
    rect(x + 9, lightY + 16, 24, 2, "#4963827a");
    rect(x + 4, 112, 42, 3, "#35434b");
    rect(x, 0, 5, 176, "#111a23");
    rect(x + 5, 0, 2, 170, "#455367");
  }
  rect(0, 63, setWidth, 3, "#26323d");
  rect(0, 66, setWidth, 1, "#5b6b7e69");

  rect(199, 45, 114, 126, "#18232c");
  rect(203, 49, 106, 119, "#45505b");
  rect(205, 51, 102, 2, "#71808a");
  for (let y = 58; y < 166; y += 6) {
    for (let x = 208; x < 306; x += 7) rect(x, y, 4, 2, "#18222c");
  }
  rect(323, 135, 39, 56, "#26313c");
  rect(327, 141, 31, 46, "#3a4651");
  rect(320, 130, 45, 5, "#707d88");
  rect(326, 112, 32, 17, "#a6b0b9");
  rect(328, 114, 28, 13, "#c0c8d0");

  // The three coloured stands sit together on a low central pedestal.
  rect(202, 174, 108, 43, "#202a34");
  rect(207, 176, 98, 34, "#434e59");
  rect(205, 210, 102, 3, "#687581");
  polygon([[209, 164], [303, 164], [311, 174], [201, 174]], "#576773", "#87949f");
  for (const {x, face, edge} of stands) {
    rect(x - 11, 166, 22, 5, edge);
    rect(x - 9, 166, 18, 2, face);
  }

  // Seven faceted workstations wrap around the front of the pedestal.
  for (let index = 0; index < tableRim.length - 1; index++) {
    const [left, right] = tableRim.slice(index, index + 2);
    const [innerLeft, innerRight] = tableOpening.slice(index, index + 2);
    polygon([left, right, [right[0], right[1] + 34], [left[0], left[1] + 34]], "#161f29", "#3e4b55");
    polygon([left, right, innerRight, innerLeft], index % 2 ? "#515b67" : "#47515d", "#8796a1");
    const x = Math.round((left[0] + right[0] + innerLeft[0] + innerRight[0]) / 4);
    const y = Math.round((left[1] + right[1] + innerLeft[1] + innerRight[1]) / 4);
    polygon([[x - 13, y - 3], [x, y - 5], [x + 3, y + 3], [x - 10, y + 5]], "#33265f", "#51427b");
    polygon([[x + 5, y - 4], [x + 15, y - 5], [x + 17, y + 1], [x + 7, y + 2]], "#abb4be");
  }
}

export function PrisonScene({players, state, selected, onChoose}) {
  const canvas = useRef(null);
  useLayoutEffect(() => drawPrisonSet(canvas.current), []);

  return <section className="stage-window pixel-frame match-set prison-set" aria-label={tr("무거운 13 감옥 매치 세트장", "Heavy 13 prison match arena")}>
    <div className="floor">
      <canvas ref={canvas} className="set-map" width={setWidth} height={setHeight} aria-hidden="true" />
      {stands.map(({color, x, face, edge}) => {
        const weights = state.stacks[color] ?? [];
        const total = weights.reduce((sum, weight) => sum + weight, 0);
        const active = state.placement?.color === color;
        return <div className="prison-stand" key={color} data-active={active || undefined} role="img"
          aria-label={[tr(`${color} 받침대`, `${chipColorLabel(color)} stand`), weights.length ? weights.join(", ") : tr("빈 받침대", "Empty stand"),
            tr(`합계 ${total}`, `Total ${total}`)].join(" · ")}
          style={{left: `${x / setWidth * 100}%`, "--cube-face": face, "--cube-edge": edge}}>
          <ol aria-hidden="true">{weights.map((weight, index) => <li key={index}>{weight}</li>)}</ol>
          <span aria-hidden="true">{total}</span>
        </div>;
      })}
      <div className="cast" aria-label={tr("감옥 매치 참가자 자리", "Prison match seats")}>
        {players.map((player, index) => {
          const [x, y] = seats[index];
          const penalty = state.penalties[player] ?? 0;
          const label = `${player} · ${tr(`벌점 ${penalty}`, `Penalty ${penalty}`)}${player === state.leader ? tr(" · 선 플레이어", " · Lead player") : ""}`;
          return <button key={player} className={`token prison-seat${state.placement?.player === player ? " acting" : ""}`}
            type="button" aria-pressed={player === selected} aria-label={label} title={label}
            data-leader={player === state.leader || undefined}
            style={{left: `${x / setWidth * 100}%`, top: `${y / setHeight * 100}%`}}
            onClick={() => onChoose(player)}>
            <Sprite player={player} /><span>{player}</span>
          </button>;
        })}
      </div>
    </div>
  </section>;
}
