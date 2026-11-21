import assert from "node:assert/strict";
import {mkdtempSync, rmSync} from "node:fs";
import {createRequire} from "node:module";
import {tmpdir} from "node:os";
import {dirname, join} from "node:path";
import {fileURLToPath} from "node:url";
import {after, test} from "node:test";
import {build} from "esbuild";

const directory = mkdtempSync(join(tmpdir(), "secret-code-ui-"));
after(() => rmSync(directory, {recursive: true, force: true}));
const require = createRequire(import.meta.url), api = {};
for (const language of ["ko", "en"]) {
  const bundle = join(directory, `${language}.cjs`);
  await build({stdin: {contents: `import React from 'react'; import {renderToStaticMarkup} from 'react-dom/server'; import {MatchReplay} from './match-replay.jsx'; export {applyCodeEvent,codePlayerStatus,codeActionText} from './secret-code.jsx'; export const render = replay => renderToStaticMarkup(<MatchReplay replay={replay} transport={null}/>);`, loader: "jsx", resolveDir: dirname(fileURLToPath(import.meta.url))}, outfile: bundle, bundle: true, platform: "node", format: "cjs", logLevel: "silent", loader: {".css": "empty", ".woff2": "empty", ".md": "text"}, define: {STATIC_REPLAY_BUILD: "false", "process.env.NODE_ENV": '"production"', "globalThis.location": JSON.stringify({search: language === "en" ? "?lang=en" : ""})}});
  api[language] = require(bundle);
}
const players = ["P01", "P02", "P03", "P04"], noop = () => {};
const event = (msg_type, data, visible_to = "all", agent_name = "System") => ({events: [{msg_type, content: typeof data === "string" ? data : JSON.stringify(data), visible_to, agent_name}]});
const setup = event("code_setup", {version: 1, players, rounds: 3, answer_seconds: 10, priority: ["P03", "P01", "P04", "P02"]});
const board = {id: "BOARD-FIRST", width: 960, height: 640, image: "data:image/png;base64,Y2FyZC1ib2FyZA=="};
const questionData = (round = 1, question = 1, active = players) => ({round, question, players: active, board: {...board, id: `BOARD-${question}`}, clues: [{id: "sum", text: "네 숫자의 합은 51입니다.", en: "The four numbers sum to 51."}, {id: "colors", text: "네 색은 모두 다릅니다.", en: "All four colors are different."}], answer_seconds: 10});
const question = (round = 1, number = 1, active = players) => event("code_question", questionData(round, number, active));
const window = (eligible = players, round = 1, question = 1, number = 1) => event("code_window", {round, question, window: number, eligible});
const buzz = (player = "P01", round = 1, question = 1) => event("code_buzz", {round, question, player, elapsed_ns: 15_000_000_000});
const attempt = (player, code, correct, round = 1, question = 1, reason = "incorrect") => event("code_attempt", {round, question, player, code, correct, reason: correct ? null : reason, elapsed_ns: 15_000_000_000, answer_seconds: 0});
const win = (player, code, round = 1, question = 1) => event("code_round_result", {round, question, winner: player, code, rank: round});
const final = event("match_result", {ranking: players, ranking_groups: players.map((player) => [player]), survivors: players.slice(0, 3), eliminated: ["P04"], finish_rounds: {P01: 1, P02: 2, P03: 3}, scores: {P01: 1, P02: 1, P03: 1, P04: 0}, pieces: {P01: 0, P02: 0, P03: 0, P04: 0}});
function render(steps, {language = "ko", view = "public", selected = "", frame = steps.length} = {}) {
  return api[language].render({id: "secret-code-demo", match: {game: "유배지 매치 3 · 비밀 코드", players, steps}, frame, view, selected, choosePlayer: noop, chooseView: noop, seek: noop, mode: "paused"});
}
const privateNote = (player) => event("decision_note", {phase: "secret_think", note: `PRIVATE-STRATEGY-${player}`}, [player], player);
const privateAction = (player, code) => event("action", {phase: "secret_think", action: JSON.stringify({type: "buzz", code})}, [player], player);

for (const language of ["ko", "en"]) {
  test(`${language}: current PNG and translated clues have enlargement, shared cast and separate log panels`, () => {
    const html = render([setup, question(), window()], {language});
    assert.match(html, /href="data:image\/png;base64,Y2FyZC1ib2FyZA=="/);
    assert.match(html, /data-board-id="BOARD-1"/);
    assert.equal((html.match(/class="exile-lift"/g) ?? []).length, 4);
    assert.match(html, /<dialog[^>]*aria-labelledby=/);
    assert.match(html, /aria-haspopup="dialog"/);
    assert.match(html, language === "ko" ? /네 숫자의 합은 51입니다/ : /The four numbers sum to 51/);
    assert.match(html, language === "ko" ? /생각하는 시간은 버저 뒤 10초 제한에 포함되지 않습니다/ : /Thinking time before buzzing is separate/);
    assert.match(html, /match-strategy/);
    assert.match(html, /class="match-details"/);
    assert.match(html, /code-attempts/);
    assert.match(html, /code-questions/);
    assert.match(html, /code-results/);
    assert.doesNotMatch(html, /match-talk/);
  });
  test(`${language}: future solution, other players' prepared answers and strategies never appear before a public answer`, () => {
    const steps = [setup, question(), window(), privateNote("P01"), privateNote("P02"), privateAction("P01", "ABYZ"), privateAction("P02", "WXZA"), buzz(), attempt("P01", "ABYZ", true), win("P01", "ABYZ")];
    const html = render(steps, {language, frame: 7});
    assert.doesNotMatch(html, /ABYZ|WXZA|PRIVATE-STRATEGY|data-correct="true"/);
    const own = render(steps, {language, frame: 7, view: "P01"});
    assert.match(own, /PRIVATE-STRATEGY-P01|ABYZ/);
    assert.doesNotMatch(own, /PRIVATE-STRATEGY-P02|WXZA/);
    const otherSelected = render(steps, {language, frame: 7, view: "P01", selected: "P02"});
    assert.doesNotMatch(otherSelected, /PRIVATE-STRATEGY-P02|WXZA/);
    const publicAnswer = render(steps, {language, frame: 9});
    assert.match(publicAnswer, /ABYZ/);
    assert.doesNotMatch(publicAnswer, /WXZA|PRIVATE-STRATEGY/);
    assert.equal((publicAnswer.match(/data-status="safe"/g) ?? []).length, 1);
  });
  test(`${language}: a buzzer precedes its verdict; wrong unsorted codes remain wrong and lock only this question`, () => {
    const steps = [setup, question(), window(), buzz(), attempt("P01", "DCBA", false, 1, 1, "invalid")];
    const buzzing = render(steps, {language, frame: 4});
    assert.match(buzzing, language === "ko" ? /버저!/ : /BUZZ!/);
    assert.doesNotMatch(buzzing, /DCBA|data-status="locked"/);
    const incorrect = render(steps, {language});
    assert.match(incorrect, /DCBA/);
    assert.match(incorrect, /data-status="locked"/);
    assert.match(incorrect, language === "ko" ? /형식 오류/ : /Invalid code/);
    assert.doesNotMatch(incorrect, /data-status="safe"/);
    const replaced = render([...steps, event("code_question_end", {round: 1, question: 1, winner: null, code: "EFGH", reason: "all_locked"}), question(1, 2), window(players, 1, 2)], {language});
    assert.match(replaced, /data-board-id="BOARD-2"/);
    assert.doesNotMatch(replaced, /data-board-id="BOARD-1"|data-status="locked"/);
    assert.equal((replaced.match(/data-status="eligible"/g) ?? []).length, 4);
  });
  test(`${language}: safe players stay safe in later rounds and exactly one final player descends`, () => {
    const steps = [setup, question(), window(), buzz(), attempt("P01", "ABCD", true), win("P01", "ABCD"), question(2, 2, players.slice(1)), window(players.slice(1), 2, 2), buzz("P02", 2, 2), attempt("P02", "EFGH", true, 2, 2), win("P02", "EFGH", 2, 2), question(3, 3, players.slice(2)), window(players.slice(2), 3, 3), buzz("P03", 3, 3), attempt("P03", "IJKL", true, 3, 3), win("P03", "IJKL", 3, 3), final];
    const halfway = render(steps, {language, frame: 8});
    assert.equal((halfway.match(/data-status="safe"/g) ?? []).length, 1);
    assert.doesNotMatch(halfway, /data-status="eliminated"|IJKL/);
    const html = render(steps, {language});
    assert.equal((html.match(/data-status="safe"/g) ?? []).length, 3);
    assert.equal((html.match(/data-status="eliminated"/g) ?? []).length, 1);
    assert.equal((html.match(/class="exile-lift"/g) ?? []).length, 4);
    assert.match(html, /data-board-id="BOARD-3"/);
    assert.match(html, language === "ko" ? /최종 결과 · 생존 3명/ : /Final results · Three survivors/);
  });
}

test("code view model copies public fields, keeps immutable source data, and resets question lockouts without losing safe players", () => {
  const state = {};
  api.en.applyCodeEvent(state, "code_setup", {players, priority: players});
  const data = {...questionData(), solution: "SECRET-INTERNAL", candidates: ["SECRET-CANDIDATE"]};
  const original = structuredClone(data);
  api.en.applyCodeEvent(state, "code_question", data, {step: 2});
  assert.doesNotMatch(JSON.stringify(state), /SECRET-INTERNAL|SECRET-CANDIDATE/);
  api.en.applyCodeEvent(state, "code_attempt", {round: 1, question: 1, player: "P01", code: "DCBA", correct: false, reason: "invalid"}, {step: 3});
  assert.equal(api.en.codePlayerStatus(state, "P01").status, "locked");
  assert.equal(state.codeAttempts[0].code, "DCBA");
  api.en.applyCodeEvent(state, "code_round_result", {round: 1, question: 1, winner: "P02", code: "ABCD", rank: 1}, {step: 4});
  api.en.applyCodeEvent(state, "code_question", questionData(2, 2, ["P01", "P03", "P04"]), {step: 5});
  assert.equal(api.en.codePlayerStatus(state, "P01").status, "eligible");
  assert.equal(api.en.codePlayerStatus(state, "P02").status, "safe");
  assert.equal(state.codeQuestions[0].result.code, "ABCD");
  assert.equal(state.codeQuestions[0].step, 2);
  assert.equal(state.codeResults[0].step, 4);
  assert.deepEqual(data, original);
});

test("combined buzzer actions preserve code order and never invent a correct answer for invalid output", () => {
  assert.equal(api.en.codeActionText('{"type":"buzz","code":"DCBA"}'), "Buzzer · DCBA");
  assert.equal(api.en.codeActionText('{"type":"wait"}'), "Wait");
  assert.equal(api.en.codeActionText('not JSON'), "Invalid code action");
});
