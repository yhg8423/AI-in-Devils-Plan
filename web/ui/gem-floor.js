import {drawSet, setHeight, setPoint, setWidth} from "./floor.js";

import {tr} from "./locale.js";

const cardColors = {
  diamond: ["#274a62", "#6a99b0", "#b6e6ef", "#f0ffff"],
  gold: ["#78532f", "#bb8f46", "#e5bd69", "#ffeb9f"],
  silver: ["#4a576c", "#7a8ca1", "#b7c6d7", "#ecf1f8"],
  copper: ["#623e32", "#9e6248", "#d18a63", "#f9bd8b"],
  bomb: ["#512a39", "#71364b", "#ca6377", "#ffb1b7"],
};

export function gemSetPoint(room, index, count) {
  if (room) return setPoint(room, index);
  const row = Math.floor(index / 5);
  const columns = Math.min(5, count - row * 5);
  return [256 + (index % 5 - (columns - 1) / 2) * 58, 251 + row * 25];
}

export function drawGemSet(canvas, cards = {}) {
  drawSet(canvas);
  const c = canvas.getContext("2d");
  c.setTransform(canvas.width / setWidth, 0, 0, canvas.height / setHeight, 0, 0);

  function rect(x, y, width, height, color) {
    c.fillStyle = color;
    c.fillRect(x, y, width, height);
  }

  function cardFace(card, x, y) {
    const colors = cardColors[card?.kind];
    rect(x, y, 22, 29, colors?.[0] ?? "#3a354d");
    rect(x + 1, y + 1, 20, 27, colors?.[1] ?? "#5c496f");
    rect(x + 2, y + 2, 18, 25, colors?.[0] ?? "#302b43");
    if (card) {
      rect(x + 7, y + 5, 8, 4, colors[3]);
      rect(x + 5, y + 9, 12, 3, colors[2]);
      rect(x + 7, y + 12, 8, 3, colors[1]);
      rect(x + 9, y + 15, 4, 2, colors[1]);
    }
    c.font = "bold 8px monospace";
    c.textAlign = "center";
    c.fillStyle = colors?.[3] ?? "#bba4d1";
    c.fillText(card ? String(card.value) : "?", x + 11, y + 25);
  }

  // A freestanding felt table sits in front of the players on the lower floor.
  rect(164, 334, 184, 6, "#111920");
  rect(175, 329, 8, 11, "#3b302b");
  rect(329, 329, 8, 11, "#3b302b");
  rect(176, 330, 2, 9, "#927457");
  rect(330, 330, 2, 9, "#927457");
  rect(166, 284, 180, 49, "#503e33");
  rect(168, 285, 176, 2, "#bc9a6d");
  rect(170, 288, 172, 40, "#1e3836");
  rect(172, 289, 168, 1, "#4c6960");
  rect(166, 330, 180, 5, "#684d3a");
  rect(168, 331, 176, 1, "#a88a62");

  for (let index = 0; index < 4; index++) {
    const x = 191 + index * 36;
    const slot = index < 3 ? `buyer${index + 1}` : "trash";
    cardFace(cards?.[slot], x, 290);
    c.font = "bold 6px monospace";
    c.textAlign = "center";
    c.fillStyle = "#e1cfaa";
    c.fillText(index < 3 ? tr(`구매자 ${index + 1}`, `BUYER ${index + 1}`) : tr("휴지통", "TRASH"), x + 11, 327);
  }
}
