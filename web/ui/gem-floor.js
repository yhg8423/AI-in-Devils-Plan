import {rooms, roomWidth, setHeight, setWidth} from "./floor.js";

import {tr} from "./locale.js";

const cardColors = {
  diamond: ["#274a62", "#6a99b0", "#b6e6ef", "#f0ffff"],
  gold: ["#78532f", "#bb8f46", "#e5bd69", "#ffeb9f"],
  silver: ["#4a576c", "#7a8ca1", "#b7c6d7", "#ecf1f8"],
  copper: ["#623e32", "#9e6248", "#d18a63", "#f9bd8b"],
  bomb: ["#512a39", "#71364b", "#ca6377", "#ffb1b7"],
};

export function drawGemSet(canvas, cards = {}) {
  const c = canvas.getContext("2d");
  c.setTransform(canvas.width / setWidth, 0, 0, canvas.height / setHeight, 0, 0);

  function rect(x, y, width, height, color) {
    c.fillStyle = color;
    c.fillRect(x, y, width, height);
  }

  function lamp(x, y) {
    rect(x - 6, y - 2, 14, 8, "#8c6441");
    rect(x - 3, y - 1, 8, 4, "#efbd78");
    rect(x - 1, y - 1, 4, 2, "#ffedb1");
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

  rect(0, 0, setWidth, setHeight, "#101215");
  rect(14, 46, 484, 248, "#171a20");
  rect(32, 26, 448, 292, "#171a20");
  rect(66, 16, 380, 318, "#171a20");
  rect(24, 52, 464, 232, "#243237");
  rect(40, 33, 432, 273, "#243237");
  rect(70, 22, 372, 300, "#243237");

  // Black slate pavers with staggered seams.
  for (let y = 126; y < 290; y += 16) {
    const inset = y < 158 ? 40 : 24;
    rect(inset, y, setWidth - inset * 2, 1, "#151e23");
    for (let x = inset + 16 + y % 32; x < setWidth - inset; x += 32) {
      rect(x, y, 1, 15, "#19262b");
      rect(x + 4, y + 3, 5, 1, "#304045");
    }
  }
  rect(70, 307, 372, 2, "#36454a");
  rect(94, 312, 324, 2, "#172427");

  for (const [x, y] of [[42, 154], [470, 154], [42, 238], [470, 238]]) {
    rect(x - 8, y - 6, 16, 18, "#142024");
    rect(x - 6, y - 4, 12, 13, "#455150");
    lamp(x, y);
  }
  for (const {x, y, tint} of rooms) {
    rect(x + 4, y + 7, roomWidth, 84, "#11181c");
    rect(x, y, roomWidth, 83, "#685b59");
    rect(x + 2, y + 2, roomWidth - 4, 80, "#3a333c");
    rect(x + 5, y + 15, roomWidth - 10, 61, "#292830");
    rect(x + 5, y + 4, roomWidth - 10, 13, tint);
    for (let col = x + 9; col < x + roomWidth - 5; col += 9) {
      rect(col, y + 6, 2, 8, "#241f29");
      rect(col + 2, y + 6, 1, 8, "#ffffff16");
    }
    rect(x + 6, y + 28, roomWidth - 12, 1, "#4a3d43");
    rect(x + 6, y + 48, roomWidth - 12, 1, "#4a3d43");
    rect(x + 10, y + 70, roomWidth - 20, 2, "#59484b");
    rect(x + 46, y + 76, 10, 7, "#b6a076");
    for (const light of [14, roomWidth - 15]) lamp(x + light, y + 13);
  }

  // A row of glass display cases along the back edge of the public hall.
  rect(105, 172, 302, 57, "#172123");
  rect(116, 162, 280, 11, "#283133");
  rect(111, 169, 290, 48, "#53625d");
  rect(108, 205, 296, 18, "#353639");
  rect(112, 221, 288, 2, "#a28d63");
  rect(120, 224, 272, 2, "#141c20");

  for (let index = 0; index < 4; index++) {
    const x = 124 + index * 68;
    const slot = index < 3 ? `buyer${index + 1}` : "trash";
    rect(x, 174, 60, 32, "#171d24");
    rect(x + 2, 176, 56, 28, "#384852");
    rect(x + 4, 178, 52, 24, index < 3 ? "#242e3c" : "#302b32");
    rect(x + 5, 179, 50, 2, "#8fa8a64f");
    rect(x + 5, 201, 50, 1, "#9eb2bb55");
    cardFace(cards?.[slot], x + 19, 174);
    c.font = "bold 6px monospace";
    c.textAlign = "center";
    c.fillStyle = "#e1cfaa";
    c.fillText(index < 3 ? tr(`구매자 ${index + 1}`, `BUYER ${index + 1}`) : tr("휴지통", "TRASH"), x + 30, 214);
  }
}
