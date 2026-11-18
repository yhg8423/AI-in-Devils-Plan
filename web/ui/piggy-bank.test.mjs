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

function challengeSequence(correct) {
  const doubt = sequence(true);
  const before = doubt.pending.slice(0, -1);
  const totals = Object.fromEntries([1, 2, 3, 4, 5].map((bank) => [bank, bank === 1 ? actual : {black: 1, white: 1}]));
  const guesses = structuredClone(totals);
  if (!correct) guesses[1].black++;
  const attempt = event("action", {phase: "pig_challenge", action: JSON.stringify(guesses)}, ["P02"], "P02");
  const verdict = event("pig_challenge", {turn: 1, player: "P02", guesses, actual: totals, correct,
    scores: {...scores, P02: correct ? 3 : -2}});
  return {...doubt, before, attempt, verdict};
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

  test(`${language}: a private full-bank challenge and its guesses remain private`, () => {
    const {before, attempt} = challengeSequence(false);
    for (const view of views) {
      const html = replay([...before, attempt], view);
      const scene = arena(html);
      const bubble = openingTag(scene, "pig-challenge-bubble");
      if (view === "operator" || view === "P02") {
        assert.match(bubble ?? "", /data-player="P02"/);
        assert(scene.includes(language === "en" ? "Challenge!" : "도전!"));
      } else {
        assert.equal(bubble, undefined, `${view} must not learn a private challenge choice`);
        assert(!html.includes("992") && !html.includes("993"), `${view} must not see private guesses or totals`);
      }
      assert.equal(openingTag(scene, "pig-challenge-badge"), undefined, "A pending challenge has no verdict yet");
      assert.equal(openingTag(html, "pig-challenge-result"), undefined, "A pending private answer has no public comparison");
      const skipped = arena(replay([...before, event("action", {phase: "pig_challenge", action: "pass"}, ["P02"], "P02")], view));
      assert.equal(openingTag(skipped, "pig-challenge-bubble"), undefined, "Skipping is not a challenge announcement");
    }
  });

  test(`${language}: challenge verdicts announce the challenger and correct point change to everyone`, () => {
    for (const correct of [true, false]) {
      const {before, attempt, verdict} = challengeSequence(correct);
      for (const view of views) {
        const scene = arena(replay([...before, attempt, verdict], view));
        assert.match(openingTag(scene, "pig-challenge-bubble") ?? "", /data-player="P02"/);
        assert.match(openingTag(scene, "pig-challenge-badge") ?? "", new RegExp(`data-correct="${correct}"`));
        assert(scene.includes(language === "en" ? "Challenge!" : "도전!"));
        assert(scene.includes(correct ? language === "en" ? "SUCCESS +3" : "성공 +3" : language === "en" ? "FAIL −2" : "실패 −2"));
        assert.equal(openingTag(scene, "pig-doubt-bubble"), undefined, "The new announcement must not show an old doubt");
      }
    }
  });

  test(`${language}: challenge cues replace doubts and clear at boundaries or when rewinding`, () => {
    const doubt = sequence(true);
    const challenge = challengeSequence(true);
    const oldDoubt = [...doubt.pending, doubt.verdict, doubt.replacement];
    for (const view of views) {
      const pending = arena(replay([...oldDoubt, challenge.attempt], view));
      if (view === "operator" || view === "P02") {
        assert(openingTag(pending, "pig-challenge-bubble"));
        assert.equal(openingTag(pending, "pig-doubt-bubble"), undefined);
      }
      const announced = arena(replay([...oldDoubt, challenge.attempt, challenge.verdict], view));
      assert.equal(openingTag(announced, "pig-doubt-bubble"), undefined);
      for (const boundary of [challenge.nextTurn, challenge.reset, challenge.before[0], challenge.before[2], challenge.result]) {
        const cleared = arena(replay([...challenge.before, challenge.attempt, challenge.verdict, boundary], view));
        assert.equal(openingTag(cleared, "pig-challenge-bubble"), undefined);
        assert.equal(openingTag(cleared, "pig-challenge-badge"), undefined);
      }
      const rewound = arena(replay([...challenge.before, challenge.attempt, challenge.verdict], view, challenge.before.length));
      assert.equal(openingTag(rewound, "pig-challenge-bubble"), undefined, "A future challenge must not survive rewind");
    }
  });

  test(`${language}: bank comparisons show submitted and actual colors, numeric order, and retained results`, () => {
    const {before, attempt, reset, result} = challengeSequence(true);
    const totals = Object.fromEntries([11, 2, 1, 12, 10].map((bank) => [bank, bank === 1 ? actual : {black: 1, white: 1}]));
    for (const mismatch of [null, "black", "white"]) {
      const guesses = structuredClone(totals);
      if (mismatch) guesses[1][mismatch]++;
      const verdict = event("pig_challenge", {turn: 1, player: "P02", guesses, actual: totals,
        correct: !mismatch, scores: {...scores, P02: mismatch ? -2 : 3}});
      for (const view of views) {
        const steps = [...before, attempt, verdict];
        const html = replay(steps, view);
        const tag = openingTag(html, "pig-challenge-result");
        assert(tag, "A public verdict should include bank-by-bank answers");
        const start = html.indexOf(tag);
        const table = html.slice(start, html.indexOf("</table>", start));
        const rows = [...table.matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr>/g)]
          .map(([, body]) => ({body, marker: openingTag(body, "pig-challenge-bank")})).filter(({marker}) => marker);
        assert.deepEqual(rows.map(({marker}) => marker.match(/data-bank="([^"]+)"/)[1]), ["1", "2", "10", "11", "12"]);
        assert.deepEqual(rows.map(({marker}) => marker.match(/data-correct="([^"]+)"/)[1]), [String(!mismatch), "true", "true", "true", "true"]);
        const cells = [...rows[0].body.matchAll(/<td\b[^>]*>([\s\S]*?)<\/td>/g)];
        const numbers = (cell) => cell.replace(/<[^>]*>/g, " ").match(/\d+/g).map(Number);
        assert.deepEqual(numbers(cells[0][1]), [guesses[1].black, guesses[1].white], "Submitted colors should preserve the player's answer");
        assert.deepEqual(numbers(cells[1][1]), [actual.black, actual.white], "Actual colors should come from the public reveal");
        assert(table.includes(language === "en" ? `${mismatch ? 4 : 5} of 5 banks correct` : `5개 저금통 중 ${mismatch ? 4 : 5}개 정답`),
          "Both colors must match for a bank to count as correct");

        const afterReset = replay([...steps, reset], view);
        const panelStart = afterReset.indexOf('class="match-state"');
        const panel = afterReset.slice(panelStart, afterReset.indexOf("</section>", panelStart));
        assert.equal(openingTag(panel, "pig-challenge-result"), undefined, "Reset should clear the current comparison");
        assert(openingTag(afterReset, "pig-challenge-result"), "History should retain publicly revealed answers after reset");

        const final = replay([...steps, result], view);
        const finalStart = final.indexOf('class="match-state"');
        const finalPanel = final.slice(finalStart, final.indexOf("</section>", finalStart));
        assert(openingTag(finalPanel, "pig-challenge-result"), "A match-ending challenge should retain its comparison beside the final result");
      }
    }
  });
}
