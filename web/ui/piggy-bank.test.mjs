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
  const speech = html.indexOf('class="arena-speech"', start);
  const end = speech >= 0 ? speech : html.indexOf('class="match-state"', start);
  assert(start >= 0 && end > start, "The integrated replay should contain the Piggy Bank arena");
  return html.slice(start, end);
}

function openingTag(html, className) {
  return html.match(new RegExp(`<[^>]+class="[^"]*\\b${className}\\b[^"]*"[^>]*>`))?.[0];
}

function memorySequence() {
  const pass = (player, to, bank, lower, upper) => event("pig_deposit", {turn: 1, player, to, bank, black: 1, white: 0, lower, upper});
  const recalled = {1: {black: 631, white: 633}, 3: {black: 1, white: 1}, 5: {black: 2, white: 1}};
  const other = {2: {black: 871, white: 873}, 4: {black: 1, white: 1}, 5: {black: 2, white: 1}};
  const finalLower = {P01: 2, P02: 5, P03: 3, P04: 4};
  const finalUpper = {P01: null, P02: null, P03: 1, P04: null};
  const selection = (owner, banks, reset = 0) => event("pig_memory_selection", {reset, capacity: 3, banks}, [owner], owner);
  const recall = (owner, banks, reset = 0) => event("pig_recall", {reset, banks}, [owner], owner);
  const steps = [
    event("rules", "돼지 저금통 · 참가자 4명\n\n5. 기억 슬롯\n리셋마다 저금통 3개를 선택합니다."),
    event("pig_setup", {order: players, lower, upper, scores}),
    selection("P01", [1, 3, 5]), selection("P02", [2, 4, 5]),
    pass("P01", "P02", 1, passedLower, {...upper, P01: null, P02: 1}),
    pass("P02", "P01", 2, {...passedLower, P02: 1}, {...upper, P01: 2}),
    pass("P01", "P02", 5, {...finalLower, P02: 1}, {...upper, P01: null, P02: 5}),
    pass("P02", "P03", 1, finalLower, finalUpper),
    event("pig_contents", {banks: {...recalled, ...other}}, ["__operator__"]),
    recall("P01", recalled), recall("P02", other),
  ];
  return {steps, finalLower, finalUpper, selection, recall};
}

function physicalBank(html, bank) {
  const tag = html.match(new RegExp(`<div class="pig-physical-bank[^\"]*"[^>]*data-bank="${bank}"[^>]*>`))?.[0];
  assert(tag, `Physical bank ${bank} should be rendered`);
  const start = html.indexOf(tag);
  return html.slice(start, html.indexOf("</div>", start));
}

function freeMemorySequence() {
  const text = "P04보다 P02 신뢰. 1·2·3·4·5·88번은 확신 없음. 1번 흑 7777? 🪙 <img src=x>";
  const recall = (owner, text, reset = 0, updated_turn = 1) => event("pig_recall", {
    reset, mode: "summary", updated_turn, text, limit: 300,
  }, [owner], owner);
  const steps = [
    event("rules", "돼지 저금통 · 참가자 4명\n\n5. 비공개 기억 요약\n각자 300자 이내로 기억할 내용을 남깁니다."),
    ...sequence(true).pending.slice(0, -1),
    event("action", {phase: "pig_memory_update", action: '{"strategy":"summary-only","ids":[1,2,3,4,5]}'}, ["P01"], "P01"),
    recall("P01", text), recall("P02", "다른 기억: P03에게 질문하기"),
  ];
  return {steps, text, recall};
}

function freeSummary(html) {
  const tag = openingTag(html, "pig-free-memory");
  assert(tag, "The chosen owner should have a private free-memory panel");
  const start = html.indexOf(tag);
  return html.slice(start, html.indexOf("</section>", start));
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
  function replay(steps, view, frame = steps.length, selected = "") {
    return render({id: "piggy-regression", match: {format: "match", game: "3일차 감옥 매치 · 돼지 저금통",
      players, steps, board: null, model_players: []}, frame, view, selected, mode: "paused",
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

  test(`${language}: memory choices and counts stay private and operator owner filters suppress omniscient totals`, () => {
    const {steps} = memorySequence();
    for (const view of views) {
      const html = replay(steps, view);
      const scene = arena(html);
      if (view === "P01") {
        assert(scene.includes("631") && scene.includes("633"));
        assert(physicalBank(scene, 1).includes("631") && physicalBank(scene, 1).includes("633"));
        assert(!html.includes("871") && !html.includes("873"));
      } else if (view === "operator") {
        assert(scene.includes("631") && scene.includes("873"), "Unfiltered operator view keeps the full contents");
      } else {
        assert(!html.includes("631") && !html.includes("633"), `${view} cannot see P01’s private recalled totals`);
      }
    }
    const selected = arena(replay(steps, "operator", steps.length, "P01"));
    assert(selected.includes("631") && selected.includes("633"));
    assert(!selected.includes("871") && !selected.includes("873"), "Owner-filtered operator graphics must hide unselected bank truth");
    const own = arena(replay(steps, "P01", steps.length, "P02"));
    assert(own.includes("631") && !own.includes("873"), "Participant filters must not change the viewer’s memory owner");
    const publicSelected = arena(replay(steps, "public", steps.length, "P01"));
    assert(!publicSelected.includes("631") && !publicSelected.includes("633"), "Public participant filters do not reveal recalled counts");
  });

  test(`${language}: memory slots follow moving banks and their fresh replacements`, () => {
    const {steps, finalLower, finalUpper, selection, recall} = memorySequence();
    const moved = arena(replay(steps, "P01"));
    assert(physicalBank(moved, 1).includes("631") && physicalBank(moved, 1).includes("633"));
    assert.match(moved, new RegExp(`data-bank="1"[^>]*aria-label="P03 · ${language === "en" ? "Upper tier" : "위칸"}"`));
    const replacement = event("pig_replace", {turn: 1, player: "P03", next_player: "P03", old_bank: 1,
      bank: 6, initial: {black: 1, white: 1}, lower: finalLower, upper: {...finalUpper, P03: 6}});
    const replaced = [...steps, replacement, selection("P01", [6, 3, 5]),
      recall("P01", {6: {black: 1, white: 1}, 3: {black: 1, white: 1}, 5: {black: 2, white: 1}})];
    for (const view of ["P01", "operator"]) {
      const scene = arena(replay(replaced, view, replaced.length, view === "operator" ? "P01" : ""));
      assert(physicalBank(scene, 6).includes(language === "en" ? "Black 1 · White 1" : "흑 1 · 백 1"));
      assert(!scene.includes("631") && !scene.includes("633"), "Retired memory counts cannot follow the replacement bank");
    }
  });

  test(`${language}: model memory preserves wrong or uncertain estimates without exposing or substituting true counts`, () => {
    const fixture = memorySequence();
    const rules = event("rules", "돼지 저금통 · 참가자 4명\n\n5. 기억 슬롯\n저금통 3개를 선택합니다.\n\n6. 기억 직접 갱신\n모르는 개수는 null로 남깁니다.");
    const update = event("pig_recall", {reset: 0, mode: "model", updated_turn: 4,
      banks: {1: {black: 614, white: null}, 3: {black: null, white: null}, 5: {black: 0, white: 2}}}, ["P01"], "P01");
    const steps = [rules, ...fixture.steps.slice(1), update];
    for (const view of ["P01", "operator"]) {
      const selected = view === "operator" ? "P01" : "P02";
      const html = replay(steps, view, steps.length, selected);
      const scene = arena(html);
      const wrong = physicalBank(scene, 1);
      assert(wrong.includes("614") && wrong.includes("?"));
      assert(!wrong.includes("631") && !wrong.includes("633"), "Remembered estimates must not be corrected with hidden totals");
      assert(physicalBank(scene, 3).includes(language === "en" ? "Black ? · White ?" : "흑 ? · 백 ?"),
        "Unknown estimates must not fall back to publicly known starting counts");
      assert(physicalBank(scene, 5).includes(language === "en" ? "Black 0 · White 2" : "흑 0 · 백 2"), "Zero is a remembered value, not uncertainty");
      assert(wrong.includes(language === "en" ? "Memory estimate" : "기억 추정"));
      const marker = openingTag(html, "pig-memory-summary");
      assert.match(marker ?? "", /data-mode="model"/);
      const start = html.indexOf(marker);
      const memory = html.slice(start, html.indexOf("</section>", start));
      assert(memory.includes(language === "en" ? "Last updated · Turn 4" : "마지막 갱신 · 4턴"));
      assert(!memory.includes("null") && memory.includes("?"));
    }
    for (const view of ["public", "P02", "P03", "P04"]) {
      assert(!replay(steps, view).includes("614"), `${view} cannot see another player’s memory estimates`);
    }
    const omniscient = arena(replay(steps, "operator"));
    assert(omniscient.includes("631") && !omniscient.includes("614"), "Unfiltered operators retain the actual-count view");
    const legacy = arena(replay(fixture.steps, "P01"));
    assert(legacy.includes("631") && !legacy.includes(language === "en" ? "Memory estimate" : "기억 추정"),
      "Previous exact-memory logs retain their original presentation");
  });

  test(`${language}: free memory accepts arbitrary text privately without selecting banks or creating bank tallies`, () => {
    const {steps, text} = freeMemorySequence();
    for (const view of ["P01", "operator"]) {
      const selected = view === "operator" ? "P01" : "";
      const html = replay(steps, view, steps.length, selected);
      const memory = freeSummary(html);
      assert.match(openingTag(memory, "pig-free-memory"), /data-owner="P01"/);
      assert(memory.includes("7777") && memory.includes("88"), "Free memory can retain arbitrary banks, uncertainty, and social facts");
      assert(memory.includes(`${Array.from(text).length} / 300`), "The length counter must count Unicode code points");
      assert(memory.includes("&lt;img src=x&gt;") && !memory.includes("<img"), "Memory text must be rendered as text");
      assert.equal(openingTag(html, "pig-memory-bank"), undefined, "Free summaries must not create fixed bank slots");
      const scene = arena(html);
      assert(!scene.includes("7777"), "Narrative memory must not be parsed into a bank tally");
      assert(!scene.includes("991") && !scene.includes("993"), "A chosen owner’s arena must not show operator-only totals");
    }
    const own = replay(steps, "P01");
    assert(own.includes("summary-only"), "A JSON-shaped memory action remains valid plain text");
    assert.match(openingTag(freeSummary(replay(steps, "P01", steps.length, "P02")), "pig-free-memory"), /data-owner="P01"/);
    for (const view of ["public", "P02", "P03", "P04"]) {
      const html = replay(steps, view);
      assert(!html.includes("7777") && !html.includes("summary-only"), `${view} cannot see another player’s memory or update`);
    }
    const other = freeSummary(replay(steps, "operator", steps.length, "P02"));
    assert(!other.includes("7777") && other.includes("P03"));
    const omniscient = arena(replay(steps, "operator"));
    assert(omniscient.includes("993") && !omniscient.includes("7777"), "Unfiltered operator counts remain independent of free summaries");
  });

  test(`${language}: changeable memory replaces all three banks without restoring forgotten totals or leaking private estimates`, () => {
    const base = [event("rules", "돼지 저금통 · 참가자 4명\n\n5. 변경 가능한 기억 슬롯\n매번 저금통 3개를 다시 고를 수 있습니다."),
      ...sequence(true).pending.slice(0, -1)];
    const recall = (banks, reset = 0, turn = 1) => event("pig_recall", {
      reset, mode: "dynamic", updated_turn: turn, banks,
    }, ["P01"], "P01");
    const initial = [...base, recall({1: {black: 111, white: 112}, 2: {black: 2222, white: 2223}, 3: {black: 3332, white: 3333}})];
    const changed = [...initial, recall({1: {black: 114, white: 115}, 4: {black: null, white: null}, 5: {black: 51, white: 52}}, 0, 2)];
    const restored = [...changed, recall({1: {black: 114, white: 115}, 2: {black: null, white: null}, 3: {black: null, white: null}}, 0, 3)];
    const reset = event("pig_reset", {reset: 1, order: players, lower, upper, scores, next_player: "P01"});
    const fresh = [...restored, reset, recall({3: {black: 1, white: 1}, 4: {black: 1, white: 1}, 5: {black: 1, white: 1}}, 1, 3), initial.at(-1)];
    const bankIds = (html) => [...html.matchAll(/class="pig-memory-bank"[^>]*data-bank="(\d+)"/g)].map(([, bank]) => Number(bank));
    for (const view of ["P01", "operator"]) {
      const selected = view === "operator" ? "P01" : "P02";
      assert.deepEqual(bankIds(replay(initial, view, initial.length, selected)), [1, 2, 3]);
      const changedHtml = replay(changed, view, changed.length, selected);
      const changedScene = arena(changedHtml);
      assert.deepEqual(bankIds(changedHtml), [1, 4, 5]);
      assert(!changedScene.includes("2222") && !changedScene.includes("3333"), "Dropped banks must lose their previous private estimates");
      assert(physicalBank(changedScene, 4).includes(language === "en" ? "Black ? · White ?" : "흑 ? · 백 ?"),
        "A newly selected unknown bank must not fall back to its public starting counts");
      assert(!changedScene.includes("991") && !changedScene.includes("993"), "Chosen-owner graphics must not reveal operator truth");
      const restoredHtml = replay(restored, view, restored.length, selected);
      const restoredScene = arena(restoredHtml);
      assert.deepEqual(bankIds(restoredHtml), [1, 2, 3]);
      for (const bank of [2, 3]) assert(physicalBank(restoredScene, bank).includes(language === "en" ? "Black ? · White ?" : "흑 ? · 백 ?"),
        "Selecting an old bank again must not magically restore its forgotten estimates");
      const resetHtml = replay([...restored, reset], view, restored.length + 1, selected);
      assert.deepEqual(bankIds(resetHtml), [], "Reset clears the previous bank bindings");
      assert.deepEqual(bankIds(replay(fresh, view, fresh.length, selected)), [3, 4, 5], "Old-epoch recalls cannot overwrite new bindings");
      assert.deepEqual(bankIds(replay(fresh, view, base.length, selected)), [], "Future bindings cannot survive rewind");
      assert.equal(openingTag(changedHtml, "pig-free-memory"), undefined, "New dynamic slots do not show the old free-summary panel");
    }
    for (const view of ["public", "P02", "P03", "P04"]) {
      const html = replay(changed, view);
      assert(!html.includes("2222") && !html.includes("3333"), `${view} must not see another player's past memory`);
      assert.deepEqual(bankIds(html), []);
    }
  });

  test(`${language}: silent rules omit conversation guidance and speech boxes while retaining private dynamic memory`, () => {
    const oldRules = "돼지 저금통 · 참가자 4명\n\n5. 변경 가능한 기억 슬롯\n저금통 3개를 기억합니다.";
    const silentRules = oldRules + "\n\n6. 대화 없는 진행\n비공개 준비와 기억 갱신 뒤 입금을 시작합니다.";
    const currentRules = silentRules + "\n\n7. 관계 평가 없음\n매치 중과 종료 시 관계 평가를 요청하지 않습니다.";
    const recall = event("pig_recall", {reset: 0, mode: "dynamic", updated_turn: 0,
      banks: {1: {black: 77, white: null}, 3: {black: 1, white: 1}, 4: {black: 1, white: 1}}}, ["P01"], "P01");
    const steps = [event("rules", currentRules), ...sequence(true).pending.slice(0, -1), recall];
    const html = replay(steps, "P01");
    assert.equal(openingTag(html, "arena-speech"), undefined, "New silent games should not reserve an empty conversation panel");
    assert(physicalBank(arena(html), 1).includes("77"), "Private memory still works without conversation");
    assert.match(openingTag(html, "pig-memory-summary"), /data-mode="dynamic"/);
    if (language === "en") {
      assert(html.includes("Players privately prepare and update their initial memory before the first deposit."));
      assert(!html.includes("four opening discussion turns") && !html.includes("two discussion turns"));
      assert(html.includes("Relationship assessments are disabled during and at the end of this match."));
      const previous = replay([event("rules", silentRules), ...steps.slice(1)], "P01");
      assert(!previous.includes("Relationship assessments are disabled"), "Older silent rules do not gain the new assessment policy");
    } else assert(html.includes("대화 없는 진행"));
    const old = replay([event("rules", oldRules), ...steps.slice(1)], "P01");
    assert(openingTag(old, "arena-speech"), "Previously saved games retain their conversation panel");
    if (language === "en") assert(old.includes("four opening discussion turns"));
  });

  test(`${language}: simultaneous reset choices stay private until the final voter list is published and four requests display clearly`, () => {
    const previousRules = "돼지 저금통 · 참가자 4명\n\n5. 변경 가능한 기억 슬롯\n저금통 3개를 기억합니다.\n\n6. 대화 없는 진행\n대화를 생략합니다.\n\n7. 관계 평가 없음\n관계 평가를 생략합니다.";
    const rules = previousRules + "\n\n8. 리셋 동시 판단\n아직 누르지 않은 전원이 동시에 판단하며 4명이면 도전 없이 리셋합니다.";
    const setup = event("pig_setup", {order: players, lower, upper, scores});
    const pending = [event("rules", rules), setup, ...players.map((player) =>
      event("action", {phase: "pig_reset_vote", action: "reset"}, [player], player))];
    const vote = event("pig_reset_vote", {turn: 1, player: "P01", voters: players, simultaneous: true});
    for (const view of views) {
      const before = replay(pending, view);
      assert.equal([...arena(before).matchAll(/data-voted="true"/g)].length, 0, "Private submissions must not light any public reset buttons");
      assert(!before.includes(language === "en" ? "Simultaneous submission" : "동시 제출"));
      const html = replay([...pending, vote], view);
      assert.equal([...arena(html).matchAll(/data-voted="true"/g)].length, 4, "The final public list marks all four requesters");
      assert(html.includes(language === "en" ? "Simultaneous submission" : "동시 제출"));
      const tag = openingTag(html, "pig-reset-status");
      const start = html.indexOf(tag);
      const status = html.slice(start, html.indexOf("</p>", start));
      assert(status.includes(language === "en" ? "4 requests · 3 required" : "4명 요청 · 기준 3명"));
      assert(players.every((player) => status.includes(player)), "The current status lists every requester");
      assert(!status.includes("4 / 3"));
      if (language === "en") assert(html.includes("If all four request a reset, reset directly without a challenge."));
    }
    const old = replay([event("rules", previousRules), setup,
      event("pig_reset_vote", {turn: 1, player: "P03", voters: players.slice(0, 3)})], "public");
    assert(old.includes("3 / 3"));
    assert(!old.includes(language === "en" ? "Simultaneous submission" : "동시 제출"));
    if (language === "en") assert(old.includes("Before it, the remaining player may recall both colors"), "Saved sequential rules keep their original translation");
    const reset = event("pig_reset", {reset: 1, order: players, lower, upper, scores, next_player: "P01"});
    assert.equal([...arena(replay([...pending, vote, reset], "public")).matchAll(/data-voted="true"/g)].length, 0);
  });

  test(`${language}: free memory survives reset until rewritten and supports forgetting, clearing, and rewind`, () => {
    const {steps, recall} = freeMemorySequence();
    const reset = event("pig_reset", {reset: 1, order: players, lower, upper, scores, next_player: "P01"});
    const afterReset = [...steps, reset];
    const rewritten = [...afterReset, recall("P01", "P02에게 묻기", 1, 2)];
    const cleared = [...rewritten, recall("P01", "", 1, 3), recall("P01", "old-epoch-7777", 0, 1)];
    for (const view of ["P01", "operator"]) {
      const selected = view === "operator" ? "P01" : "";
      const retained = freeSummary(replay(afterReset, view, afterReset.length, selected));
      assert(retained.includes("7777"), "Reset retains the previous summary until its owner rewrites it");
      assert(retained.includes(language === "en" ? "pre-reset" : "리셋 전"));
      const changed = freeSummary(replay(rewritten, view, rewritten.length, selected));
      assert(!changed.includes("7777") && changed.includes("P02에게 묻기"), "A new summary can discard every previous bank fact");
      const empty = freeSummary(replay(cleared, view, cleared.length, selected));
      assert.match(openingTag(empty, "pig-memory-text"), /data-empty="true"/);
      assert(empty.includes("0 / 300") && !empty.includes("7777") && !empty.includes("P02에게 묻기"));
      const beforeRecall = freeSummary(replay(cleared, view, 2, selected));
      assert(beforeRecall.includes("0 / 300") && !beforeRecall.includes("7777"), "Future summaries cannot survive rewind");
    }
  });

  test(`${language}: reset epochs, reused IDs, rewinding, and legacy logs cannot retain stale memory slots`, () => {
    const {steps, selection, recall} = memorySequence();
    const reset = event("pig_reset", {reset: 1, order: players, lower, upper, scores, next_player: "P01"});
    const resetOnly = [...steps, reset];
    const newSelection = [...resetOnly, selection("P01", [2, 4, 5], 1),
      recall("P01", {2: {black: 47, white: 49}, 4: {black: 1, white: 1}, 5: {black: 1, white: 1}}, 1),
      recall("P01", {1: {black: 631, white: 633}, 3: {black: 1, white: 1}, 5: {black: 1, white: 1}}, 0)];
    for (const view of ["P01", "operator"]) {
      const selected = view === "operator" ? "P01" : "";
      const resetHtml = replay(resetOnly, view, resetOnly.length, selected);
      assert(!arena(resetHtml).includes("631"));
      assert.equal(openingTag(resetHtml, "pig-memory-bank"), undefined);
      const current = arena(replay(newSelection, view, newSelection.length, selected));
      assert(current.includes("47") && current.includes("49"));
      assert(!current.includes("631") && !current.includes("633"), "An old-epoch recall must not overwrite reused bank IDs");
      assert(physicalBank(current, 2).includes("47") && physicalBank(current, 2).includes("49"));
      const rewound = replay(newSelection, view, 2, selected);
      assert.equal(openingTag(rewound, "pig-memory-bank"), undefined, "Future selections must not survive rewind");
    }
    const legacy = replay(sequence(true).pending, "P01");
    assert.equal(openingTag(legacy, "pig-memory-summary"), undefined);
    assert(!legacy.includes('id="pig-memory"'), "Logs without the version heading keep their original UI");
  });
}
