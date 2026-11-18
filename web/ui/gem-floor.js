import {drawSet, setHeight, setWidth} from "./floor.js";

import {tr} from "./locale.js";

const cardColors = {
  diamond: ["#274a62", "#6a99b0", "#b6e6ef", "#f0ffff"],
  gold: ["#78532f", "#bb8f46", "#e5bd69", "#ffeb9f"],
  silver: ["#4a576c", "#7a8ca1", "#b7c6d7", "#ecf1f8"],
  copper: ["#623e32", "#9e6248", "#d18a63", "#f9bd8b"],
  bomb: ["#512a39", "#71364b", "#ca6377", "#ffb1b7"],
};

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

  // The card table fits between the original stairs and their walking routes.
  rect(204, 168, 104, 49, "#53625d");
  rect(206, 170, 100, 45, "#172123");
  rect(204, 215, 104, 2, "#a28d63");

  for (let index = 0; index < 4; index++) {
    const x = 205 + index * 25;
    const slot = index < 3 ? `buyer${index + 1}` : "trash";
    cardFace(cards?.[slot], x, 172);
    c.font = "bold 6px monospace";
    c.textAlign = "center";
    c.fillStyle = "#e1cfaa";
    c.fillText(index < 3 ? tr(`구매자 ${index + 1}`, `BUYER ${index + 1}`) : tr("휴지통", "TRASH"), x + 11, 211);
  }
}
