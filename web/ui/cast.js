const cast = new Map([
  ["P01", {color: "#c69858", skin: "#efba93", hair: "#30252a", head: "bob", outfit: "coat", accessory: "glasses"}],
  ["P02", {color: "#74a6ad", skin: "#c99676", hair: "#302320", head: "crop", outfit: "vest"}],
  ["P03", {color: "#a79bbb", skin: "#edb492", hair: "#422936", head: "bun", outfit: "sweater"}],
  ["P04", {color: "#a3ae71", skin: "#be8867", hair: "#362720", head: "cap", outfit: "hoodie"}],
  ["P05", {color: "#ce8477", skin: "#f0c2a2", hair: "#603630", head: "waves", outfit: "cardigan", accessory: "earring"}],
  ["P06", {color: "#8f9bb8", skin: "#d6a07e", hair: "#252832", head: "part", outfit: "shirt"}],
  ["P07", {color: "#86ba9e", skin: "#b77f60", hair: "#39272d", head: "ponytail", outfit: "overalls"}],
  ["P08", {color: "#dbae70", skin: "#e4ad83", hair: "#553825", head: "spikes", outfit: "varsity"}],
  ["P09", {color: "#be99a6", skin: "#eab493", hair: "#543744", head: "beanie", outfit: "coat"}],
  ["P10", {color: "#8aa997", skin: "#a9775d", hair: "#2d2327", head: "curls", outfit: "sweater", accessory: "glasses"}],
  ["P11", {color: "#c6aa76", skin: "#ecc09b", hair: "#7c4b35", head: "bob", outfit: "overalls"}],
  ["P12", {color: "#91b0c6", skin: "#dca583", hair: "#353241", head: "cap", outfit: "varsity", accessory: "earring"}],
  ["P13", {color: "#d7989d", skin: "#d5a183", hair: "#342833", head: "ponytail", outfit: "vest", accessory: "glasses"}],
  ["P14", {color: "#86ae81", skin: "#cc936e", hair: "#453124", head: "beanie", outfit: "shirt"}],
  ["P15", {color: "#a298c1", skin: "#efb892", hair: "#684337", head: "waves", outfit: "hoodie"}],
  ["P16", {color: "#cf9a77", skin: "#b98369", hair: "#3c2c29", head: "spikes", outfit: "cardigan", accessory: "earring"}],
]);

const fallback = {color: "#a1adb9", skin: "#d6a07e", hair: "#30252a", head: "crop", outfit: "shirt"};

export function playerColor(id) {
  return (cast.get(id) ?? fallback).color;
}

const heads = {
  bob: ["....hhhh....", "..hhhhhhhh..", "..hhhhhhhh..", ".hhhhhhhhh..",
    ".hhh....hhh.", ".hh......hh.", ".hh......hh.", ".hh......hh.", "..h......h.."],
  crop: ["....hhhh....", "...hhhhhh...", "..hhhhhhhh..", "..hhhhhhhh..", "..hh....hh.."],
  bun: [".....hh.....", "....hhhh....", "...hhhhhh...", "..hhhhhhhh..", "..hhh..hhh..", "..h......h.."],
  cap: ["....cccc....", "...cccccc...", "..ccwwcccc..", "..ddddddddd.", "..hh.....h.."],
  waves: ["...hhhhhh...", "..hhhhhhhh..", ".hhhhhhhhh..", ".hhhh...hhh.",
    ".hhh.....hh.", "hhh......hh.", "hh.......hhh", ".hh......hhh", ".hhh......hh"],
  part: ["...hhhhhh...", "..hhhhhhhh..", "..hhh.hhhh..", "..hh...hhh..", "..h......h.."],
  ponytail: ["....hhhh....", "..hhhhhhhh..", "..hhhhhhhhh.", "..hh..hhhhhw", "..h......hhh",
    ".........hhh", "..........hh", ".........hh."],
  spikes: ["...h..h.....", "...hhhhhh...", "..hhhhhhhhh.", "..hhhhh.hhh.", "..hh.....h.."],
  beanie: [".....ww.....", "....cccc....", "...cccccc...", "..cccccccc..", "..dddddddd..", "..h......h.."],
  curls: ["...hh.hh....", "..hhhhhhh...", ".hhhhhhhhh..", ".hhhhhhhhhh.", ".hhh..hhh.h.", "..h......h.."],
};

const outfits = {
  coat: ["...cwwwwc...", "..ccdwddcc..", ".cccdwddccc.", ".cccdwddccc.", ".cccdwddccc.",
    ".sccdwddccs.", "..ccdwddcc..", "..ccdwddcc..", "..cccccccc.."],
  vest: ["...wccccw...", "..wwcdccww..", ".wwwcdccwww.", ".wwwccdcwww.", ".s.wccccw.s.", "...cddcc...", "...cccccc..."],
  sweater: ["...cccccc...", "..cccccccc..", ".cccccccccc.", ".ddwwwwwwdd.", ".cccccccccc.", ".s.cccccc.s.", "...dddddd..."],
  hoodie: ["...ddccdd...", "..cdwwwwdc..", ".cccwcwcccc.", ".cccccccccc.", ".ccccddcccc.", ".s.ccddcc.s.", "...cccccc..."],
  cardigan: ["...cwwwwc...", "..ccdccdcc..", ".cccdccdccc.", ".cccdcddccc.",
    ".cccdccdccc.", ".s.ccdccd.s.", "...cdccdc..."],
  shirt: ["...wwwwww...", "..cwwddwwc..", ".cccwddwccc.", ".ccccddcccc.", ".s.ccddcc.s.", "...ccdccc...", "...cccccc..."],
  overalls: ["...wcwwcw...", "..wwcwwcww..", ".wwwcddcwww.", ".s.wccccw.s.", "...ccwwcc...", "...cccccc...", "...cccccc..."],
  varsity: ["...wccccw...", "..wwcddcww..", ".wwccdwccww.", ".wwccdccwww.",
    ".ddccdccddd.", ".s.ccdccc.s.", "...dddddd..."],
};

const legs = ["...pppppp...", "...pppppp...", "...pp.ppp...", "...pp.ppp...", "..bbb..bbb..", "..wwb..bww.."];

export function drawSprite(canvas, id) {
  const {color, skin, hair, head, outfit, accessory} = cast.get(id) ?? fallback;
  const context = canvas.getContext("2d");
  context.setTransform(2, 0, 0, 2, 0, 0);
  context.clearRect(0, 0, 16, 23);
  const palette = {h: hair, s: skin, c: color, w: "#eedbc4", d: "#3b4052", p: "#333545", b: "#171e28"};
  const rect = (fill, x, y, width, height) => {
    context.fillStyle = fill;
    context.fillRect(x, y, width, height);
  };
  const draw = (rows, top) => rows.forEach((row, y) => [...row].forEach((pixel, x) => {
    if (pixel !== ".") rect(palette[pixel], x + 2, top + y, 1, 1);
  }));

  draw(legs, 17);
  draw(outfits[outfit], 10);
  rect(skin, 5, 4, 6, 5);
  rect(skin, 4, 6, 8, 2);
  rect(skin, 6, 9, 4, 2);
  draw(heads[head], 0);
  rect("#28212a", 6, 6, 1, 1);
  rect("#28212a", 9, 6, 1, 1);
  if (accessory === "glasses") {
    rect("#1e2731", 5, 5, 6, 1);
    rect("#354555", 5, 6, 2, 1);
    rect("#354555", 9, 6, 2, 1);
  } else if (accessory === "earring") {
    rect("#ffe0a0", 11, 7, 1, 2);
  }
}
