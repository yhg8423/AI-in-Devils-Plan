"use strict";

const setWidth = 512;
const setHeight = 348;
const roomWidth = 102;
const upperWalk = 154;
const lowerWalk = 226;
const rooms = [
  {x: 30, y: 62, side: -1, tint: "#8d503a"},
  {x: 140, y: 43, side: -1, tint: "#41667e"},
  {x: 268, y: 43, side: 1, tint: "#626944"},
  {x: 378, y: 62, side: 1, tint: "#525b61"},
];

function stairX(side, tread) {
  return setWidth / 2 + side * (65 + tread * 3);
}

function setPoint(room, index) {
  const column = index % 4;
  const row = Math.floor(index / 4);
  if (!room) {
    const span = [112, 109, 101, 83][row];
    const stagger = [-11, 11, -11, 23][row];
    return [256 + stagger + span * [-1, -0.34, 0.34, 1][column], [251, 273, 295, 315][row]];
  }
  const {x, y} = rooms[room - 1];
  return [x + [16, 38, 62, 84][column], y + [34, 50, 66, 82][row]];
}

function walkRoute(fromRoom, toRoom, index) {
  function boothExit(room) {
    const [x, y] = setPoint(room, index);
    const booth = rooms[room - 1];
    const door = booth.x + 50;
    return [[x, y], [x, booth.y + 76], [door, booth.y + 76], [door, upperWalk]];
  }
  if (fromRoom && toRoom) {
    return [...boothExit(fromRoom), ...boothExit(toRoom).reverse()];
  }
  const booth = fromRoom || toRoom;
  const {side} = rooms[booth - 1];
  const top = stairX(side, 0);
  const bottom = stairX(side, 9);
  const [x, y] = setPoint(0, index);
  const down = [...boothExit(booth), [top, upperWalk], [top, 160], [bottom, 214],
    [bottom, lowerWalk], [x, lowerWalk], [x, y]];
  return fromRoom ? down : down.reverse();
}

function drawSet(canvas) {
  const c = canvas.getContext("2d");
  c.setTransform(canvas.width / setWidth, 0, 0, canvas.height / setHeight, 0, 0);
  function rect(x, y, w, h, color) {
    c.fillStyle = color;
    c.fillRect(x, y, w, h);
  }
  function polygon(points, color) {
    c.beginPath();
    points.forEach(([x, y], i) => i ? c.lineTo(x, y) : c.moveTo(x, y));
    c.closePath();
    c.fillStyle = color;
    c.fill();
  }
  function ellipse(x, y, rx, ry, color) {
    c.beginPath();
    c.ellipse(x, y, rx, ry, 0, 0, Math.PI * 2);
    c.fillStyle = color;
    c.fill();
  }
  let seed = 341;
  const noise = () => {
    seed = (seed * 48271) % 2147483647;
    return seed / 2147483647;
  };
  function lamp(x, y) {
    rect(x - 5, y - 1, 11, 6, "#e6ad6240");
    rect(x - 3, y - 1, 7, 4, "#bd8f60");
    rect(x - 2, y - 1, 5, 2, "#ffe4ba");
    rect(x - 2, y - 1, 5, 0.5, "#fff3db");
  }

  rect(0, 0, setWidth, setHeight, "#101318");
  ellipse(256, 184, 251, 159, "#252a30");
  ellipse(256, 186, 246, 151, "#555d66");
  ellipse(256, 192, 241, 143, "#1c2129");
  ellipse(256, 207, 236, 127, "#414a51");

  // The lower concrete floor and the shadows cast by the upper balcony.
  c.save();
  c.beginPath();
  c.ellipse(256, 207, 234, 125, 0, 0, Math.PI * 2);
  c.clip();
  const concrete = c.createLinearGradient(0, 170, 0, 332);
  concrete.addColorStop(0, "#202630");
  concrete.addColorStop(0.52, "#434d54");
  concrete.addColorStop(1, "#535f64");
  rect(20, 79, 472, 253, concrete);
  for (let i = 0; i < 1850; i++) {
    const x = 20 + Math.floor(noise() * 472);
    const y = 160 + Math.floor(noise() * 172);
    rect(x, y, 1 + Math.floor(noise() * 3), 1, noise() > 0.5 ? "#dae8ed16" : "#090f191f");
  }
  c.restore();

  const lowerLip = [[12, 117], [47, 132], [103, 148], [166, 160], [220, 165], [292, 165],
    [346, 160], [409, 148], [465, 132], [500, 117]];
  const upperLip = lowerLip.map(([x, y]) => [x, y - 9]);
  polygon([[12, 117], [20, 75], [69, 47], [143, 29], [256, 22], [369, 29],
    [443, 47], [492, 75], [500, 117], ...lowerLip.slice().reverse()], "#3a414a");
  polygon([...upperLip, ...lowerLip.slice().reverse()], "#13171e");
  for (let i = 1; i < upperLip.length; i++) {
    const [x, y] = upperLip[i - 1];
    const [xx, yy] = upperLip[i];
    c.strokeStyle = "#899099";
    c.beginPath();
    c.moveTo(x, y - 3);
    c.lineTo(xx, yy - 3);
    c.stroke();
    rect(x, y - 9, 2, 12, "#222831");
  }

  // Four windowed booths flank the upper landing. The interior depth is schematic.
  rooms.forEach(({x, y, tint}) => {
    rect(x + 3, y + 5, 103, 84, "#1a1d25");
    rect(x, y, roomWidth, 83, "#69717b");
    rect(x, y, roomWidth, 0.5, "#b4bac0");
    rect(x, y, 0.5, 83, "#98a1aa");
    rect(x + 3, y + 3, 96, 77, "#2e343c");
    rect(x + 4, y + 4, 94, 10, tint);
    for (let yy = y + 5; yy < y + 14; yy += 4) {
      for (let xx = x + 7; xx < x + 96; xx += 6) rect(xx + (yy % 3), yy, 2, 2, "#21262c");
    }
    rect(x + 4, y + 14, 94, 12, "#24313c");
    rect(x + 4, y + 14, 94, 1, "#adbdc9");
    for (const pane of [5, 28, 51, 74]) {
      rect(x + pane, y + 14, 2, 13, "#8494a1");
      rect(x + pane + 2, y + 15, 21, 11, "#6a8da424");
      rect(x + pane + 4, y + 17, 12, 1, "#b6d1df66");
      rect(x + pane + 7, y + 20, 5, 1, "#b6d1df3d");
      rect(x + pane + 13, y + 22.5, 6, 0.5, "#b6d1df66");
    }
    for (let yy = y + 31; yy < y + 78; yy += 11) rect(x + 4, yy, 94, 1, "#3b424d");
    rect(x + 3, y + 79, 96, 3, "#999ea7");
    for (const mullion of [5, 26, 72, 95]) rect(x + mullion, y + 64, 2, 15, "#87929b");
    rect(x + 45, y + 80, 11, 4, "#b0b5bc");
    lamp(x + 51, y + 8);
  });

  // The central black panel, five white strips, mirrored steel stairs and amber practicals.
  rect(194, 158, 124, 60, "#161e26");
  rect(201, 162, 110, 53, "#202931");
  rect(195, 155, 122, 5, "#65717b");
  rect(227, 119, 58, 34, "#252931");
  rect(228, 120, 56, 2, "#9299a3");
  for (let i = 0; i < 5; i++) {
    const x = 222 + 17 * i;
    rect(x - 2, 164, 5, 47, "#a8c4ee32");
    rect(x, 163, 2, 48, "#d8e6fa");
    rect(x - 3, 178, 8, 6, "#7e8a94");
    rect(x - 1, 179, 4, 4, "#222b35");
  }
  for (const side of [-1, 1]) {
    for (let i = 0; i < 10; i++) {
      const center = stairX(side, i);
      const y = 160 + i * 6;
      rect(center - 15, y + 1, 31, 6, "#121820");
      rect(center - 15, y, 31, 2, "#7a8790");
      rect(center - 13, y, 27, 0.5, "#c2c9ce");
      rect(center - 15, y - 1, 2, 6, "#99a3ad");
      rect(center + 14, y - 1, 2, 6, "#99a3ad");
    }
  }
  for (const [x, y] of [[38, 180], [74, 193], [110, 204], [402, 204], [438, 193], [474, 180], [256, 127]]) lamp(x, y);
}

export {drawSet, rooms, roomWidth, setHeight, setPoint, setWidth, walkRoute};
