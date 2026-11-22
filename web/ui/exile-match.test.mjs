import assert from "node:assert/strict";
import {mkdtempSync, rmSync} from "node:fs";
import {createRequire} from "node:module";
import {tmpdir} from "node:os";
import {dirname, join} from "node:path";
import {fileURLToPath} from "node:url";
import {after, test} from "node:test";
import {build} from "esbuild";

const directory = mkdtempSync(join(tmpdir(), "exile-ui-"));
after(() => rmSync(directory, {recursive: true, force: true}));
const require = createRequire(import.meta.url), api = {};
for (const language of ["ko", "en"]) {
  const bundle = join(directory, `${language}.cjs`);
  await build({stdin: {contents: `import React from 'react'; import {renderToStaticMarkup} from 'react-dom/server'; import {MatchReplay} from './match-replay.jsx'; export {applyExileEvent, exileActionText, exileEventText, exileBoardFor} from './exile-match.jsx'; export const render = replay => renderToStaticMarkup(<MatchReplay replay={replay} transport={null}/>);`, loader: "jsx", resolveDir: dirname(fileURLToPath(import.meta.url))}, outfile: bundle, bundle: true, platform: "node", format: "cjs", logLevel: "silent", loader: {".css": "empty", ".woff2": "empty", ".md": "text"}, define: {STATIC_REPLAY_BUILD: "false", "process.env.NODE_ENV": '"production"', "globalThis.location": JSON.stringify({search: language === "en" ? "?lang=en" : ""})}});
  api[language] = require(bundle);
}
const players = ["P01", "P02", "P03", "P04"], noop = () => {};
const pieces = Array.from({length: 8}, (_, i) => ({id: `K${i + 1}`, sides: [0, 0, 1, 1], depths: [58, 83, 58, 83]}));
const event = (msg_type, data, visible_to = "all", agent_name = "System") => ({events: [{msg_type, content: typeof data === "string" ? data : JSON.stringify(data), visible_to, agent_name}]});
const setup = event("exile_setup", {version: 1, size: 4, players, pieces, turn_order: players, source_url: "https://source.invalid", adapted: true});
const turn = event("exile_turn", {turn: 1, active: players});
const board1 = {player: "P01", turn: 1, placements: [{piece: "K1", axis: "row", slot: 1, reverse: false, flip: false}, {piece: "K2", axis: "col", slot: 1, reverse: true, flip: true}, {piece: "K3", axis: "row", slot: 4, reverse: true, flip: false}], joints: [{row: 1, col: 1, ok: false}, {row: 4, col: 1, ok: true}], errors: 1, placed: 3};
const board2 = {player: "P02", turn: 1, placements: [{piece: "K6", axis: "col", slot: 4, reverse: false, flip: true}], joints: [], errors: 0, placed: 1};
const own = event("exile_board", board1, ["P01"], "P01"), other = event("exile_board", board2, ["P02"], "P02");
function render(steps, {language = "ko", view = "operator", selected = "", frame = steps.length} = {}) {
  return api[language].render({id: "exile-demo", match: {game: "유배지 매치 1 · 피스 퍼즐", players, steps}, frame, view, selected, choosePlayer: noop, chooseView: noop, seek: noop, mode: "paused"});
}
for (const language of ["ko", "en"]) {
  test(`${language}: native scene and eight notch diagrams appear through MatchReplay`, () => {
    const html = render([setup, turn, own], {language});
    assert.match(html, /exile-arena/);
    assert.equal((html.match(/data-piece-card=/g) ?? []).length, 8);
    assert.equal((html.match(/data-notch=/g) ?? []).length, 32);
    assert.match(html, /data-assembly-owner="P01"/);
    assert.match(html, /data-joint="blocked"/);
    assert.match(html, /data-joint="ok"/);
    assert.match(html, language === "ko" ? /피스 퍼즐 결과와 기록/ : /Piece Puzzle results and records/);
    assert.doesNotMatch(html, /arena-speech|match-talk|source.invalid|adapted|fan recreation/);
  });
  test(`${language}: public and other participants cannot expose a selected private board`, () => {
    const steps = [setup, turn, own, other];
    const hidden = render(steps, {language, view: "public", selected: "P01"});
    assert.doesNotMatch(hidden, /data-assembly-owner=|data-piece="K1"|data-piece="K6"/);
    assert.match(hidden, language === "ko" ? /비공개 조립 중/ : /PRIVATE ASSEMBLY/);
    assert.doesNotMatch(hidden, language === "ko" ? /미배치/ : /In tray/);
    const participant = render(steps, {language, view: "P02", selected: "P01"});
    assert.match(participant, /data-assembly-owner="P02"/);
    assert.match(participant, /data-piece="K6"/);
    assert.doesNotMatch(participant, /data-assembly-owner="P01"|data-piece="K1"/);
    assert.match(render(steps, {language, selected: "P01"}), /data-piece="K1"/);
  });
  test(`${language}: only an end reveal makes another assembly public`, () => {
    const reveal = event("exile_reveal", {boards: {P01: board1, P02: board2}});
    const steps = [setup, turn, own, other, reveal];
    assert.doesNotMatch(render(steps, {language, view: "public", selected: "P02", frame: 4}), /data-assembly-owner=/);
    assert.match(render(steps, {language, view: "public", selected: "P02"}), /data-assembly-owner="P02"/);
    assert.match(render(steps, {language, view: "P01", selected: "P02"}), /data-assembly-owner="P02"/);
  });
  test(`${language}: completion and final elimination remain distinct when all four submit`, () => {
    const attempts = players.map((player, i) => event("exile_attempt", {player, turn: 9, correct: true, place: i + 1}));
    const result = event("match_result", {ranking: players, survivors: players.slice(0, 3), eliminated: ["P04"], finish_turns: {P01: 9, P02: 9, P03: 9, P04: 9}, turns: 9, pieces: {P01: 0, P02: 0, P03: 0, P04: 0}});
    const final = render([setup, ...attempts, result], {language});
    assert.match(final, language === "ko" ? /최종 결과/ : /Final results/);
    assert.match(final, language === "ko" ? /탈락/ : /Eliminated/);
    assert.match(final, /data-status="eliminated"/);
    assert.doesNotMatch(final, language === "ko" ? /4위 생존/ : /Rank 4, safe|Rank 4 · Safe/);
    assert.doesNotMatch(render([setup, ...attempts, result], {language, frame: 1}), /data-status="safe"|data-status="eliminated"/);
    assert.match(api[language].exileEventText("exile_attempt", {player: "P04", correct: true, place: 4}), language === "ko" ? /4위$/ : /Rank 4$/);
  });
}
test("exile replay state stores only observed boards, resets, and does not mutate event data", () => {
  const state = {};
  const original = structuredClone(board1);
  api.ko.applyExileEvent(state, "exile_setup", setup.events[0] && JSON.parse(setup.events[0].content));
  assert.deepEqual(state.exileBoards, {});
  api.ko.applyExileEvent(state, "exile_board", board1, {step: 3});
  state.exileBoards.P01.placements[0].slot = 2;
  assert.deepEqual(board1, original);
  api.ko.applyExileEvent(state, "exile_setup", JSON.parse(setup.events[0].content));
  assert.deepEqual(state.exileBoards, {});
  assert.deepEqual(state.exileAttempts, []);
  assert.equal(state.exileRevealed, false);
});
test("board ownership is enforced even when state contains every private board", () => {
  const state = {exilePerspective: "P02", exileBoards: {P01: board1, P02: board2}};
  assert.equal(api.ko.exileBoardFor(state, players, "P01").board, board2);
  assert.deepEqual(api.ko.exileBoardFor({...state, exilePerspective: "public"}, players, "P01"), {owner: null, board: null});
});
test("action labels expose the actual operation and both orientation changes", () => {
  const action = JSON.stringify({type: "place", piece: "K8", axis: "col", slot: 2, reverse: true, flip: true});
  assert.match(api.en.exileActionText("exile_move", action), /K8 → Column 2 · Reversed · Flipped/);
  assert.match(api.ko.exileActionText("exile_move", '{"type":"submit"}'), /버저/);
  assert.equal(api.en.exileActionText("exile_move", "broken JSON"), "broken JSON");
});
