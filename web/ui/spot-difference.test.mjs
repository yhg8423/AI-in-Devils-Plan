import assert from "node:assert/strict";
import {mkdtempSync, rmSync} from "node:fs";
import {createRequire} from "node:module";
import {tmpdir} from "node:os";
import {dirname, join} from "node:path";
import {fileURLToPath} from "node:url";
import {after, test} from "node:test";
import {build} from "esbuild";

const directory = mkdtempSync(join(tmpdir(), "spot-ui-"));
after(() => rmSync(directory, {recursive: true, force: true}));
const require = createRequire(import.meta.url), api = {};
for (const language of ["ko", "en"]) {
  const bundle = join(directory, `${language}.cjs`);
  await build({stdin: {contents: `import React from 'react'; import {renderToStaticMarkup} from 'react-dom/server'; import {MatchReplay} from './match-replay.jsx'; export {applyPictureEvent,pictureSelection,pictureActionText} from './spot-difference.jsx'; export const render = replay => renderToStaticMarkup(<MatchReplay replay={replay} transport={null}/>);`, loader: "jsx", resolveDir: dirname(fileURLToPath(import.meta.url))}, outfile: bundle, bundle: true, platform: "node", format: "cjs", logLevel: "silent", loader: {".css": "empty", ".woff2": "empty", ".md": "text"}, define: {STATIC_REPLAY_BUILD: "false", "process.env.NODE_ENV": '"production"', "globalThis.location": JSON.stringify({search: language === "en" ? "?lang=en" : ""})}});
  api[language] = require(bundle);
}
const players = ["P01", "P02", "P03", "P04"], noop = () => {};
const event = (msg_type, data, visible_to = "all", agent_name = "System") => ({events: [{msg_type, content: typeof data === "string" ? data : JSON.stringify(data), visible_to, agent_name}]});
const original = {id: "ORIGINAL-ONLY", theme: "fishing", width: 960, height: 640, shapes: [{kind: "rect", x: 0, y: 0, w: 960, h: 640, fill: "#f01234"}, {kind: "ellipse", x: 50, y: 40, w: 30, h: 20, fill: "#fff"}, {kind: "polygon", points: [[0, 0], [10, 0], [5, 8]], fill: "#fef"}, {kind: "line", points: [[80, 80], [100, 100]], width: 3, stroke: "#ffe"}]};
const changed = {...original, id: "CHANGED-ONLY", shapes: [{kind: "rect", x: 0, y: 0, w: 960, h: 640, fill: "#1234ab"}]};
const setup = event("picture_setup", {version: 1, players, normal_rounds: 3, change_count: 5, memory_limit: 300, width: 960, height: 640});
const phase = (stage, round = 1, overtime = false, active = players) => event("picture_phase", {round, stage, players: active, overtime, observe_seconds: overtime ? 120 : 180, blank_seconds: 10, answer_seconds: 120, picture: stage === "blank" ? null : stage === "observe" ? original : changed});
const mem1 = event("picture_memory", {round: 1, player: "P01", memory: "PRIVATE-MEMORY-P01"}, ["P01"], "P01");
const mem2 = event("picture_memory", {round: 1, player: "P02", memory: "PRIVATE-MEMORY-P02"}, ["P02"], "P02");
const marks1 = event("picture_marks", {round: 1, player: "P01", marks: [{x: 100, y: 120}]}, ["P01"], "P01");
const marks2 = event("picture_marks", {round: 1, player: "P02", marks: [{x: 250, y: 350}]}, ["P02"], "P02");
const resultData = {round: 1, players, overtime: false, scores: {P01: 1, P02: 0, P03: 0, P04: 0}, totals: {P01: 1, P02: 0, P03: 0, P04: 0}, answers: {P01: [{x: 100, y: 120, correct: true, target: "change-1"}], P02: [{x: 250, y: 350, correct: false, target: null}], P03: [], P04: []}, targets: Array.from({length: 5}, (_, i) => ({id: `change-${i + 1}`, x: i * 160 + 50, y: 110, w: 40, h: 40})), picture: changed};
const result = event("picture_result", resultData);
function render(steps, {language = "ko", view = "operator", selected = "", frame = steps.length} = {}) {
  return api[language].render({id: "spot-demo", match: {game: "유배지 매치 2 · 달라진 그림 찾기", players, steps}, frame, view, selected, choosePlayer: noop, chooseView: noop, seek: noop, mode: "paused"});
}

for (const language of ["ko", "en"]) {
  test(`${language}: raster replays expose only the current image and provide a native enlargement dialog`, () => {
    const rasterOriginal = {id: "RASTER-ORIGINAL", theme: "market", width: 960, height: 640, image: "data:image/png;base64,b3JpZ2luYWw="};
    const rasterChanged = {...rasterOriginal, id: "RASTER-CHANGED", image: "data:image/png;base64,Y2hhbmdlZA=="};
    const rasterPhase = (stage, picture) => event("picture_phase", {round: 1, stage, players, overtime: false, observe_seconds: 180, blank_seconds: 10, answer_seconds: 120, picture});
    const observe = rasterPhase("observe", rasterOriginal);
    const hidden = rasterPhase("blank", null);
    const answer = rasterPhase("answer", rasterChanged);
    const observed = render([setup, observe], {language});
    assert.match(observed, /class="spot-raster"/);
    assert.match(observed, /href="data:image\/png;base64,b3JpZ2luYWw="/);
    assert.match(observed, /<dialog[^>]*aria-labelledby=/);
    assert.match(observed, /aria-haspopup="dialog"/);
    assert.match(observed, language === "ko" ? /확대 그림 닫기/ : /Close enlarged picture/);
    assert.doesNotMatch(observed, /Y2hhbmdlZA==/);
    const blank = render([setup, observe, hidden], {language});
    assert.doesNotMatch(blank, /<image|b3JpZ2luYWw=|Y2hhbmdlZA==/);
    assert.match(blank, /class="spot-zoom-button"[^>]*disabled/);
    const answering = render([setup, observe, hidden, answer, marks1], {language, view: "P01"});
    assert.match(answering, /href="data:image\/png;base64,Y2hhbmdlZA=="/);
    assert.match(answering, /data-mark="100,120"/);
    assert.doesNotMatch(answering, /b3JpZ2luYWw=|data-target=/);
  });
  test(`${language}: original, blank and answer phases never render both pictures`, () => {
    const observed = render([setup, phase("observe")], {language});
    assert.match(observed, /data-picture-id="ORIGINAL-ONLY"/);
    assert.match(observed, /<ellipse|<polygon|<polyline/);
    assert.doesNotMatch(observed, /CHANGED-ONLY|match-talk/);
    assert.match(observed, /match-strategy/);
    const hidden = render([setup, phase("observe"), mem1, phase("blank")], {language});
    assert.doesNotMatch(hidden, /data-picture-id=|#f01234|#1234ab/);
    assert.match(hidden, language === "ko" ? /원본 그림이 사라졌습니다/ : /THE ORIGINAL IS HIDDEN/);
    const answering = render([setup, phase("observe"), mem1, phase("blank"), phase("answer")], {language});
    assert.match(answering, /data-picture-id="CHANGED-ONLY"/);
    assert.doesNotMatch(answering, /ORIGINAL-ONLY|#f01234/);
  });
  test(`${language}: private memory and X coordinates stay private until marks are revealed`, () => {
    const steps = [setup, phase("observe"), mem1, mem2, phase("blank"), phase("answer"), marks1, marks2];
    const publicView = render(steps, {language, view: "public", selected: "P01"});
    assert.doesNotMatch(publicView, /PRIVATE-MEMORY|data-mark=|data-target=/);
    const ownView = render(steps, {language, view: "P01", selected: "P02"});
    assert.match(ownView, /PRIVATE-MEMORY-P01/);
    assert.match(ownView, /data-mark="100,120"/);
    assert.doesNotMatch(ownView, /PRIVATE-MEMORY-P02|data-mark="250,350"|data-target=|data-correct=/);
    const operator = render(steps, {language, selected: "P02"});
    assert.match(operator, /PRIVATE-MEMORY-P02/);
    assert.match(operator, /data-mark="250,350"/);
    assert.doesNotMatch(operator, /data-target=|data-correct=/);
  });
  test(`${language}: public results reveal exact targets and marks but never private memories`, () => {
    const steps = [setup, phase("observe"), mem1, mem2, phase("answer"), marks1, marks2, phase("reveal"), result];
    const before = render(steps, {language, view: "public", frame: steps.length - 1});
    assert.doesNotMatch(before, /data-target=|data-mark=/);
    const final = render(steps, {language, view: "public", selected: "P01"});
    assert.equal((final.match(/data-target=/g) ?? []).length, 5);
    assert.match(final, /data-mark="100,120"/);
    assert.match(final, /data-correct="true"/);
    assert.doesNotMatch(final, /PRIVATE-MEMORY/);
    const other = render(steps, {language, view: "P01", selected: "P02"});
    assert.match(other, /data-mark="250,350"/);
    assert.match(other, /data-correct="false"/);
    assert.doesNotMatch(other, /PRIVATE-MEMORY-P02/);
  });
  test(`${language}: later rounds clear memories and targets; overtime shows its shorter observation`, () => {
    const steps = [setup, phase("observe"), mem1, phase("answer"), result, phase("observe", 2)];
    const next = render(steps, {language, view: "P01"});
    assert.doesNotMatch(next, /data-target=|data-mark=/);
    assert.doesNotMatch(next.match(/<section class="spot-personal"[\s\S]*?<\/section>/)[0], /PRIVATE-MEMORY-P01/);
    const tie = event("picture_tiebreak", {round: 4, players: ["P02", "P03"], slots: 1});
    const overtime = render([...steps, tie, phase("observe", 4, true, ["P02", "P03"])], {language});
    assert.match(overtime, language === "ko" ? /연장 1라운드/ : /Overtime 1/);
    assert.match(overtime, /120/);
    assert.match(overtime, language === "ko" ? /동점자만 참가/ : /Tied players only/);
  });
  test(`${language}: final standings lower both eliminated players and retain safe ties`, () => {
    const final = event("match_result", {ranking: ["P01", "P02", "P03", "P04"], ranking_groups: [["P01", "P02"], ["P03"], ["P04"]], survivors: ["P01", "P02"], eliminated: ["P03", "P04"], scores: {P01: 10, P02: 10, P03: 8, P04: 7}, pieces: {P01: 0, P02: 0, P03: 0, P04: 0}, tiebreaks: []});
    const html = render([setup, phase("answer"), result, final], {language});
    assert.equal((html.match(/data-status="eliminated"/g) ?? []).length, 2);
    assert.equal((html.match(/data-status="safe"/g) ?? []).length, 2);
    assert.equal((html.match(/class="exile-lift"/g) ?? []).length, 4);
    assert.match(html, language === "ko" ? /최종 순위/ : /Final standings/);
    assert.doesNotMatch(render([setup, phase("answer"), result, final], {language, frame: 2}), /data-status="eliminated"/);
  });
}

test("picture state keeps input immutable and distinguishes reveal from a visible drawing", () => {
  const state = {exilePerspective: "public"};
  api.ko.applyPictureEvent(state, "picture_setup", {players});
  api.ko.applyPictureEvent(state, "picture_phase", {round: 1, stage: "answer", picture: changed});
  api.ko.applyPictureEvent(state, "picture_marks", {round: 1, player: "P01", marks: [{x: 100, y: 120}]}, {step: 4});
  assert.equal(api.ko.pictureSelection(state, players, "P01").marks.length, 0);
  api.ko.applyPictureEvent(state, "picture_phase", {round: 1, stage: "reveal", picture: changed});
  assert.equal(api.ko.pictureSelection(state, players, "P01").marks.length, 0);
  const originalData = structuredClone(resultData);
  api.ko.applyPictureEvent(state, "picture_result", resultData, {step: 5});
  state.pictureSubmissions["1:P01"].marks[0].x = 600;
  assert.deepEqual(resultData, originalData);
  api.ko.applyPictureEvent(state, "picture_phase", {round: 2, stage: "blank", picture: original});
  assert.equal(state.picturePhase.picture, null);
  assert.equal(api.ko.pictureSelection(state, players, "P01").marks.length, 0);
});
test("memory summary and coordinate actions have readable labels", () => {
  assert.equal(api.en.pictureActionText("picture_memorize", '{"memory":"Blue hat near the pond"}'), "Blue hat near the pond");
  assert.equal(api.en.pictureActionText("picture_answer", '{"marks":[{"x":123,"y":456}]}'), "(123, 456)");
  assert.equal(api.en.pictureActionText("picture_answer", '{"marks":[]}'), "No marks");
});
