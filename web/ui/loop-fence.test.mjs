import assert from "node:assert/strict";
import {mkdtempSync, rmSync} from "node:fs";
import {createRequire} from "node:module";
import {tmpdir} from "node:os";
import {dirname, join} from "node:path";
import {fileURLToPath} from "node:url";
import {after, test} from "node:test";
import {build} from "esbuild";

const directory = mkdtempSync(join(tmpdir(), "loop-fence-ui-"));
after(() => rmSync(directory, {recursive: true, force: true}));
const require = createRequire(import.meta.url), api = {};
for (const language of ["ko", "en"]) {
  const bundle = join(directory, `${language}.cjs`);
  await build({stdin: {contents: `import React from 'react'; import {renderToStaticMarkup} from 'react-dom/server'; import {MatchReplay} from './match-replay.jsx'; export {applyFenceEvent,fenceBoardFor,fencePlayerStatus,fenceActionText} from './loop-fence.jsx'; export const render = replay => renderToStaticMarkup(<MatchReplay replay={replay} transport={null}/>);`, loader: "jsx", resolveDir: dirname(fileURLToPath(import.meta.url))}, outfile: bundle, bundle: true, platform: "node", format: "cjs", logLevel: "silent", loader: {".css": "empty", ".woff2": "empty", ".md": "text"}, define: {STATIC_REPLAY_BUILD: "false", "process.env.NODE_ENV": '"production"', "globalThis.location": JSON.stringify({search: language === "en" ? "?lang=en" : ""})}});
  api[language] = require(bundle);
}
const players = ["P01", "P02", "P03", "P04"], noop = () => {};
const event = (msg_type, data, visible_to = "all", agent_name = "System") => ({events: [{msg_type, content: typeof data === "string" ? data : JSON.stringify(data), visible_to, agent_name}]});
const setupData = {version: 1, players, priority: ["P03", "P01", "P04", "P02"], size: 7, survivors: 3};
const setup = event("fence_setup", setupData);
const image = (id) => ({id, width: 960, height: 640, image: `data:image/png;base64,${Buffer.from(id).toString("base64")}`});
const base = image("UNMARKED-BASE");
const puzzleData = {puzzle: {id: "SINGLE-PUZZLE", size: 7, board: base}};
const puzzle = event("fence_puzzle", puzzleData);
const window = (number, active = players) => event("fence_window", {window: number, active});
const loop = [["H", 0, 0], ["H", 1, 0], ["V", 0, 0], ["V", 0, 1]];
const workingData = (player, number = 1, solved = false) => ({player, window: number, edges: solved ? loop : [["H", 0, 0]], crosses: solved ? [] : [["H", 2, 2], ["V", 3, 3]], board: image(`${player}-${solved ? "COMPLETED" : "PRIVATE-PARTIAL"}`), submitted: solved});
const drawing = (player, number = 1, solved = false) => event("fence_board", workingData(player, number, solved), [player], player);
const buzz = (player, number = 1, attempt = 1) => event("fence_buzz", {player, window: number, attempt, elapsed_ns: 15_000_000_000});
const verdict = (player, correct, number = 1, attempt = 1) => event("fence_verdict", {player, window: number, attempt, correct, reason: correct ? null : "invalid_loop", elapsed_ns: 15_000_000_000});
const finishData = (player, rank) => ({player, rank, window: 2, attempt: 1, elapsed_ns: 15_000_000_000});
const finish = (player, rank) => event("fence_finish", finishData(player, rank));
const revealData = {boards: Object.fromEntries(players.map((player) => [player, workingData(player, 2, player !== "P04")])), solution: loop, puzzle_id: "SINGLE-PUZZLE"};
const reveal = event("fence_reveal", revealData);
const final = event("match_result", {ranking: players, ranking_groups: players.map((player) => [player]), survivors: players.slice(0, 3), eliminated: ["P04"], finish_turns: {P01: 2, P02: 2, P03: 2}, scores: {P01: 1, P02: 1, P03: 1, P04: 0}, pieces: Object.fromEntries(players.map((player) => [player, 0]))});
const privateNote = (player) => event("decision_note", {phase: "fence_draw", note: `PRIVATE-STRATEGY-${player}`}, [player], player);
function render(steps, {language = "ko", view = "public", selected = "", frame = steps.length} = {}) {
  return api[language].render({id: "loop-fence-demo", match: {game: "유배지 매치 4 · 울타리 치기", players, steps}, frame, view, selected, choosePlayer: noop, chooseView: noop, seek: noop, mode: "paused"});
}
const completedSteps = [setup, puzzle, window(1), drawing("P01"), drawing("P02"), privateNote("P01"), privateNote("P02"), window(2), ...players.map((player) => drawing(player, 2, true)), buzz("P01", 2), verdict("P01", true, 2), finish("P01", 1), buzz("P02", 2), verdict("P02", true, 2), finish("P02", 2), buzz("P03", 2), verdict("P03", true, 2), finish("P03", 3), reveal, final];

for (const language of ["ko", "en"]) {
  test(`${language}: shared puzzle has four corner platforms, a native enlargement dialog and single-race progress`, () => {
    const html = render([setup, puzzle, window(1)], {language});
    assert.match(html, /data-board-id="UNMARKED-BASE"/);
    assert.match(html, /data-board-owner="public"/);
    assert.equal((html.match(/class="exile-lift"/g) ?? []).length, 4);
    assert.match(html, /<dialog[^>]*aria-labelledby=/);
    assert.match(html, /aria-haspopup="dialog"/);
    assert.match(html, /fence-finish-slots/);
    assert.equal((html.match(/data-filled="false"/g) ?? []).length, 3);
    assert.match(html, /match-strategy/);
    assert.match(html, /class="match-details"/);
    assert.match(html, /fence-attempts/);
    assert.match(html, /fence-drawings/);
    assert.match(html, /fence-finishes/);
    assert.match(html, language === "ko" ? /빈칸에는 개수 조건이 없습니다/ : /blank cells have no count constraint/);
    assert.doesNotMatch(html, /match-talk|10초|10s|라운드|Round /);
  });
  test(`${language}: public sees only the base, owners and operator see the selected private PNG and X counts`, () => {
    const steps = completedSteps.slice(0, 7);
    const publicView = render(steps, {language, selected: "P02"});
    assert.match(publicView, /data-board-id="UNMARKED-BASE"/);
    assert.doesNotMatch(publicView, /PRIVATE-PARTIAL|PRIVATE-STRATEGY/);
    const ownView = render(steps, {language, view: "P01", selected: "P02"});
    assert.match(ownView, /data-board-id="P01-PRIVATE-PARTIAL"/);
    assert.match(ownView, /data-board-owner="P01"/);
    assert.match(render(steps, {language, view: "P01", selected: "P01"}), /PRIVATE-STRATEGY-P01/);
    assert.doesNotMatch(ownView, /P02-PRIVATE-PARTIAL|PRIVATE-STRATEGY-P02/);
    assert.match(ownView, language === "ko" ? /선 1개 · X 2개/ : /1 line · 2 X marks/);
    const operator = render(steps, {language, view: "operator", selected: "P02"});
    assert.match(operator, /data-board-id="P02-PRIVATE-PARTIAL"/);
    assert.match(operator, /PRIVATE-STRATEGY-P02/);
  });
  test(`${language}: a finished player's solution remains hidden until all three finishes and the end reveal`, () => {
    const firstSafe = render(completedSteps, {language, frame: 15, selected: "P01"});
    assert.equal((firstSafe.match(/data-status="safe"/g) ?? []).length, 1);
    assert.match(firstSafe, /data-board-id="UNMARKED-BASE"/);
    assert.doesNotMatch(firstSafe, /data-board-id="P0[1-4]-COMPLETED"|PRIVATE-STRATEGY|data-status="eliminated"/);
    const threeSafeBeforeReveal = render(completedSteps, {language, frame: 21});
    assert.equal((threeSafeBeforeReveal.match(/data-status="safe"/g) ?? []).length, 3);
    assert.match(threeSafeBeforeReveal, /data-board-id="UNMARKED-BASE"/);
    const revealed = render(completedSteps, {language, frame: 22, selected: "P02"});
    assert.match(revealed, /data-board-id="P02-COMPLETED"/);
    assert.match(revealed, /data-board-owner="P02"/);
    assert.doesNotMatch(revealed, /PRIVATE-STRATEGY/);
    const otherView = render(completedSteps, {language, frame: 22, view: "P01", selected: "P02"});
    assert.match(otherView, /data-board-id="P02-COMPLETED"/);
    assert.doesNotMatch(otherView, /PRIVATE-STRATEGY-P02/);
  });
  test(`${language}: wrong verdict leaves the player eligible to retry and replaces the visible board only for its owner`, () => {
    const steps = [setup, puzzle, window(1), drawing("P01"), buzz("P01"), verdict("P01", false)];
    const buzzing = render(steps, {language, frame: 5});
    assert.match(buzzing, language === "ko" ? /버저!/ : /BUZZ!/);
    const incorrect = render(steps, {language, view: "P01"});
    assert.match(incorrect, language === "ko" ? /수정 후 재제출 가능/ : /Revise and resubmit/);
    assert.match(incorrect, /data-board-id="P01-PRIVATE-PARTIAL"/);
    assert.equal((incorrect.match(/data-status="solving"/g) ?? []).length, 4);
    assert.doesNotMatch(incorrect, /data-status="locked"|data-status="safe"/);
    const retry = render([...steps, window(2), drawing("P01", 2, true), buzz("P01", 2, 2), verdict("P01", true, 2, 2), finish("P01", 1)], {language, view: "P01"});
    assert.match(retry, /data-board-id="P01-COMPLETED"/);
    assert.equal((retry.match(/data-status="safe"/g) ?? []).length, 1);
  });
  test(`${language}: only final elimination lowers the last platform and retains all three safe players`, () => {
    const html = render(completedSteps, {language});
    assert.equal((html.match(/data-status="safe"/g) ?? []).length, 3);
    assert.equal((html.match(/data-status="eliminated"/g) ?? []).length, 1);
    assert.equal((html.match(/class="exile-lift"/g) ?? []).length, 4);
    assert.match(html, language === "ko" ? /최종 결과/ : /Final results/);
    assert.doesNotMatch(render(completedSteps, {language, frame: 22}), /data-status="eliminated"/);
  });
}

test("view model copies only public puzzle and verdict fields, retains private edges immutably and refuses an early reveal", () => {
  const state = {exilePerspective: "operator"};
  api.en.applyFenceEvent(state, "fence_setup", setupData);
  api.en.applyFenceEvent(state, "fence_puzzle", {puzzle: {...puzzleData.puzzle, solution: ["HIDDEN-SOLUTION"], seed: "HIDDEN-SEED"}}, {step: 2});
  assert.doesNotMatch(JSON.stringify(state), /HIDDEN-/);
  const working = workingData("P01"), original = structuredClone(working);
  api.en.applyFenceEvent(state, "fence_board", working, {step: 4});
  api.en.applyFenceEvent(state, "fence_finish", {...finishData("P01", 1), edges: ["HIDDEN-SAFE-SOLUTION"]}, {step: 5});
  assert.doesNotMatch(JSON.stringify(state), /HIDDEN-/);
  assert.equal(api.en.fenceBoardFor(state, players, "P01", "public").board.id, "UNMARKED-BASE");
  assert.equal(api.en.fenceBoardFor(state, players, "P02", "P01").owner, "P01");
  api.en.applyFenceEvent(state, "fence_reveal", revealData, {step: 6});
  assert.equal(state.fenceRevealed, false);
  api.en.applyFenceEvent(state, "fence_finish", finishData("P02", 2), {step: 7});
  api.en.applyFenceEvent(state, "fence_finish", finishData("P03", 3), {step: 8});
  api.en.applyFenceEvent(state, "fence_reveal", revealData, {step: 9});
  assert.equal(state.fenceRevealed, true);
  assert.equal(api.en.fenceBoardFor(state, players, "P02", "public").board.id, "P02-COMPLETED");
  state.fenceOperations[0].edges[0][1] = 7;
  state.fenceBoards.P02.crosses.push(["H", 7, 6]);
  assert.deepEqual(working, original);
  assert.deepEqual(revealData.boards.P02.crosses, []);
  assert.equal(state.fenceOperations[0].step, 4);
  assert.equal(state.fenceFinishes[0].step, 5);
  assert.equal(state.fenceRevealStep, 9);
});

test("draw action labels show full replacement, X marks and same-action submission without exposing edge arrays", () => {
  assert.equal(api.en.fenceActionText(JSON.stringify({type: "draw", edges: loop, crosses: [["H", 2, 2]], submit: true})), "Replace drawing · 4 lines · 1 X mark · Submit with buzzer");
  assert.equal(api.en.fenceActionText('{"type":"wait"}'), "Wait · Keep the current drawing");
  assert.equal(api.en.fenceActionText('not JSON'), "Invalid drawing action");
});
