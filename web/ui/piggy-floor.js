import {setHeight, setWidth} from "./floor.js";

export const piggySeats = [76, 196, 316, 436];

// Native canvas pixels keep the set sharp at the same resolution as the other arenas.
export function drawPiggySet(canvas) {
  const c = canvas.getContext("2d");
  c.imageSmoothingEnabled = false;
  const rect = (x, y, w, h, fill) => { c.fillStyle = fill; c.fillRect(x, y, w, h); };
  rect(0, 0, setWidth, setHeight, "#10151c");
  rect(0, 0, setWidth, 113, "#1d2731");
  for (let row = 0; row < 8; row++) {
    for (let col = -1; col < 11; col++) {
      rect(col * 56 + row % 2 * 28, row * 14, 54, 12, row % 3 ? "#26323d" : "#293641");
    }
  }
  for (const x of [9, 486]) {
    rect(x, 12, 17, 106, "#111820");
    for (let bar = 0; bar < 3; bar++) rect(x + 2 + bar * 5, 14, 2, 100, "#65717b");
  }
  rect(0, 112, setWidth, 6, "#0c1117");
  rect(0, 118, setWidth, 230, "#222c35");
  for (let y = 120; y < setHeight; y += 24) {
    rect(0, y, setWidth, 1, "#34404a");
    for (let x = (y / 24 % 2) * 40; x < setWidth; x += 80) rect(x, y, 1, 24, "#34404a");
  }
  rect(180, 22, 152, 36, "#0a0f16");
  rect(182, 24, 148, 2, "#9d825c");
  rect(182, 54, 148, 2, "#624c37");
  c.font = "bold 13px monospace";
  c.textAlign = "center";
  c.fillStyle = "#d9b47f";
  c.fillText("PIGGY BANK", 256, 46);
  for (const x of piggySeats) {
    rect(x - 20, 63, 40, 5, "#0d1217");
    rect(x - 15, 68, 30, 3, "#cdbd94");
    rect(x - 11, 71, 22, 2, "#f3e1ab");
    rect(x - 12, 91, 24, 31, "#18222a");
    rect(x - 14, 124, 28, 8, "#0f171f");
    rect(x - 47, 146, 94, 136, "#0a1118");
    rect(x - 45, 145, 90, 128, "#594b3c");
    rect(x - 43, 146, 86, 3, "#bf9a69");
    rect(x - 40, 151, 80, 51, "#344443");
    rect(x - 38, 152, 76, 2, "#617164");
    rect(x - 45, 202, 90, 6, "#a17c52");
    rect(x - 40, 208, 80, 53, "#202d32");
    rect(x - 43, 263, 86, 8, "#806043");
    rect(x - 39, 273, 6, 24, "#2d2825");
    rect(x + 33, 273, 6, 24, "#2d2825");
    rect(x - 36, 274, 2, 21, "#775b42");
  }
  rect(0, 330, setWidth, 18, "#101923");
  rect(0, 330, setWidth, 2, "#485562");
}
