import assert from "node:assert/strict";
import {mkdtempSync, rmSync} from "node:fs";
import {createRequire} from "node:module";
import {tmpdir} from "node:os";
import {dirname, join} from "node:path";
import {fileURLToPath} from "node:url";
import {after, test} from "node:test";
import {build} from "esbuild";

const temporary = mkdtempSync(join(tmpdir(), "piggy-replay-test-"));
const bundle = join(temporary, "replay.cjs");
after(() => rmSync(temporary, {recursive: true, force: true}));
await build({
  stdin: {contents: `import React from "react";
    import {renderToStaticMarkup} from "react-dom/server";
    import {MatchReplay} from "./match-replay.jsx";
    export const render = (replay) => renderToStaticMarkup(<MatchReplay replay={replay} transport={null} />);`,
  resolveDir: dirname(fileURLToPath(import.meta.url)), loader: "jsx"},
  outfile: bundle, bundle: true, platform: "node", format: "cjs", logLevel: "silent",
  define: {STATIC_REPLAY_BUILD: "false", "process.env.NODE_ENV": '"production"'},
  loader: {".css": "empty", ".md": "text", ".woff2": "empty"},
});

const require = createRequire(import.meta.url);
const players = ["P01", "P02", "P03", "P04"];
const views = ["operator", "public", ...players];
const scores = Object.fromEntries(players.map((player) => [player, 0]));
const lower = {P01: 1, P02: 2, P03: 3, P04: 4};
const upper = {P01: 5, P02: null, P03: null, P04: null};
const passedLower = {...lower, P01: 5};
const passedUpper = {...upper, P01: null, P03: 1};
const actual = {black: 991, white: 993};
const noOp = () => {};
const event = (msg_type, data, visible_to = "all", agent_name = "System") => ({
  events: [{msg_type, content: JSON.stringify(data), visible_to, agent_name}],
});

function sequence(correct) {
  const claimed = correct ? 0 : actual.black;
  const penalized = correct ? "P03" : "P02";
  const nextScores = {...scores, P02: correct ? 1 : -1, P03: correct ? -1 : 0};
  const nextUpper = {...passedUpper, P03: null, [penalized]: 6};
  const pending = [
    event("pig_setup", {order: players, lower, upper, scores}),
    event("pig_turn", {turn: 1, player: "P01", color: "black", lower, upper, scores}),
    event("pig_deposit", {turn: 1, player: "P01", to: "P03", bank: 1, black: 2, white: 0,
      lower: passedLower, upper: passedUpper}),
    event("pig_contents", {banks: {1: actual}}, ["__operator__"]),
    event("pig_claim", {turn: 1, player: "P03", bank: 1, color: "black", count: claimed}),
    event("action", {phase: "pig_doubt", action: "doubt"}, ["P02"], "P02"),
  ];
  const verdict = event("pig_doubt", {turn: 1, challenger: "P02", player: "P03", bank: 1,
    color: "black", claimed, actual, correct, scores: nextScores});
  const replacement = event("pig_replace", {player: penalized, next_player: penalized, old_bank: 1,
    bank: 6, initial: {black: 1, white: 1}, lower: passedLower, upper: nextUpper});
  const nextTurn = event("pig_turn", {turn: 2, player: penalized, color: "white",
    lower: passedLower, upper: nextUpper, scores: nextScores});
  const reset = event("pig_reset", {reset: 1, order: players, lower,
    upper: {...upper, P01: null, [penalized]: 5}, scores: nextScores, next_player: penalized});
  const result = event("match_result", {ranking: players, scores: nextScores, pieces_awarded: {}, eliminated: ["P04"]});
  return {pending, verdict, replacement, nextTurn, reset, result, penalized};
}

function arena(html) {
  const start = html.indexOf('class="arena pig-arena"');
  const end = html.indexOf('class="arena-speech"', start);
  assert(start >= 0 && end > start, "The integrated replay should contain the Piggy Bank arena");
  return html.slice(start, end);
}

function openingTag(html, className) {
  return html.match(new RegExp(`<[^>]+class="[^"]*\\b${className}\\b[^"]*"[^>]*>`))?.[0];
}

for (const language of ["ko", "en"]) {
  const savedLocation = Object.getOwnPropertyDescriptor(globalThis, "location");
  let render;
  try {
    Object.defineProperty(globalThis, "location", {configurable: true, value: {search: language === "en" ? "?lang=en" : ""}});
    delete require.cache[require.resolve(bundle)];
    ({render} = require(bundle));
  } finally {
    if (savedLocation) Object.defineProperty(globalThis, "location", savedLocation);
    else delete globalThis.location;
  }
  function replay(steps, view, frame = steps.length) {
    return render({id: "piggy-regression", match: {format: "match", game: "3일차 감옥 매치 · 돼지 저금통",
      players, steps, board: null, model_players: []}, frame, view, selected: "", mode: "paused",
    choosePlayer: noOp, chooseView: noOp, seek: noOp});
  }

  test(`${language}: private doubt choices and unopened totals stay private`, () => {
    const {pending} = sequence(true);
    for (const view of views) {
      const scene = arena(replay(pending, view));
      const bubble = openingTag(scene, "pig-doubt-bubble");
      if (view === "operator" || view === "P02") assert.match(bubble ?? "", /data-player="P02"/);
      else assert.equal(bubble, undefined, `${view} must not learn a private buzzer choice`);
      assert.equal(openingTag(scene, "pig-opened-bank"), undefined);
      if (view === "operator") assert(scene.includes("993"), "The operator control should see stored contents");
      else assert(!scene.includes("993"), `${view} must not see the unopened white total`);
    }
  });

  test(`${language}: public verdicts show the caller, opened bank, and success or failure`, () => {
    for (const correct of [true, false]) {
      const {pending, verdict, replacement} = sequence(correct);
      for (const view of views) {
        const scene = arena(replay([...pending, verdict], view));
        assert.match(openingTag(scene, "pig-doubt-bubble") ?? "", /data-player="P02"/);
        assert.match(openingTag(scene, "pig-opened-bank") ?? "", /data-bank="1"/);
        assert.match(openingTag(scene, "pig-opened-bank") ?? "", new RegExp(`data-correct="${correct}"`));
        assert.match(openingTag(scene, "pig-doubt-badge") ?? "", new RegExp(`data-correct="${correct}"`));
        assert(scene.includes(correct ? language === "en" ? "SUCCESS +1" : "성공 +1" : language === "en" ? "FAIL −1" : "실패 −1"));
        assert(scene.includes("991") && scene.includes("993"), "An opened bank should reveal both colors");
        assert(scene.includes(language === "en" ? "Doubt!" : "의심!"));

        const replaced = arena(replay([...pending, verdict, replacement], view));
        assert.match(openingTag(replaced, "pig-retired-bank") ?? "", /data-bank="1"/);
        const freshTag = replaced.match(/<div class="pig-physical-bank[^"]*"[^>]*data-bank="6"[^>]*>/)?.[0];
        assert(freshTag, "The replacement should have its own physical bank");
        assert(!freshTag.includes("pig-opened-bank"), "A fresh bank must not appear opened");
        const position = replaced.indexOf(freshTag);
        const fresh = replaced.slice(position, replaced.indexOf("</div>", position));
        assert(fresh.includes(language === "en" ? "#6" : "6번"));
        assert(!fresh.includes("991") && !fresh.includes("993"), "Retired contents must not follow the fresh bank");
      }
    }
  });

  test(`${language}: turn changes, resets, setup, results, and rewinding clear the visual cue`, () => {
    const {pending, verdict, replacement, nextTurn, reset, result} = sequence(true);
    const resolved = [...pending, verdict, replacement];
    for (const boundary of [nextTurn, reset, pending[0], result]) {
      for (const view of views) {
        const scene = arena(replay([...resolved, boundary], view));
        assert.equal(openingTag(scene, "pig-doubt-bubble"), undefined);
        assert.equal(openingTag(scene, "pig-opened-bank"), undefined);
        assert.equal(openingTag(scene, "pig-retired-bank"), undefined);
      }
    }
    for (const view of views) {
      const scene = arena(replay(resolved, view, pending.length - 1));
      assert.equal(openingTag(scene, "pig-doubt-bubble"), undefined, "Future verdicts must not survive rewind");
      assert.equal(openingTag(scene, "pig-opened-bank"), undefined);
    }
  });
}
