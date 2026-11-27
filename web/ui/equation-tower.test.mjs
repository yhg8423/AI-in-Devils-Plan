import assert from "node:assert/strict";
import {mkdtempSync, rmSync} from "node:fs";
import {createRequire} from "node:module";
import {tmpdir} from "node:os";
import {dirname, join} from "node:path";
import {fileURLToPath} from "node:url";
import {after, test} from "node:test";
import {build} from "esbuild";

const directory = mkdtempSync(join(tmpdir(), "equation-tower-ui-"));
after(() => rmSync(directory, {recursive: true, force: true}));
const require = createRequire(import.meta.url), api = {};
for (const language of ["ko", "en"]) {
  const bundle = join(directory, `${language}.cjs`);
  await build({stdin: {contents: `import React from 'react'; import {renderToStaticMarkup} from 'react-dom/server'; import {MatchReplay} from './match-replay.jsx'; import {EquationTowerScene, EquationTowerStage, EquationTowerInformation} from './equation-tower.jsx'; export {applyTowerEvent, towerEventText, towerActionText} from './equation-tower.jsx'; export const renderMatch = replay => renderToStaticMarkup(<MatchReplay replay={replay} transport={null}/>); export const render = (state, players) => renderToStaticMarkup(<><EquationTowerScene state={state} players={players} selected="P02" onChoose={()=>{}}/><EquationTowerStage state={state} players={players}/><EquationTowerInformation state={state} replay={{seek:()=>{}}}/></>);`, loader: "jsx", resolveDir: dirname(fileURLToPath(import.meta.url))}, outfile: bundle, bundle: true, platform: "node", format: "cjs", logLevel: "silent", loader: {".css": "empty", ".woff2": "empty", ".md": "text"}, define: {STATIC_REPLAY_BUILD: "false", "process.env.NODE_ENV": '"production"', "globalThis.location": JSON.stringify({search: language === "en" ? "?lang=en" : ""})}});
  api[language] = require(bundle);
}
const players = ["P01", "P02", "P03"];
const blocks = Object.fromEntries(Array.from({length: 20}, (_, index) => [`b${index}`, {value: index % 7 + 1, operator: index < 4 ? null : "+", label: index < 4 ? String(index + 1) : `+${index % 7 + 1}`} ]));
const stacks = Array.from({length: 4}, (_, index) => Array.from({length: 5}, (_, level) => `b${index * 5 + level}`));
const setup = {players, order: ["P03", "P01", "P02"], stacks, blocks, goal: 7, timing: {opening: 300, counter: 120, challenge: 120}, discussion: false};
const problem = {round: 1, players, scores: {P01: 2, P02: 0, P03: -1}, target: "7/2", height: 4, stacks};
const movedStacks = [stacks[0].slice(0, 3), [...stacks[1], ...stacks[0].slice(3).reverse()], stacks[2], stacks[3]];
const move = {round: 1, player: "P02", index: 1, from: 1, to: 2, count: 2, flip: true, stacks: movedStacks};
const verdict = {round: 1, player: "P02", success: false, reason: "incorrect", change: -2, scores: {P01: 2, P02: -2, P03: -1}, target: "7/2", height: 4, expression: "3 ÷ 2", value: "3/2", stacks: movedStacks, used: 1, allowed: 2};
function stateAt(events, language = "ko") {
  const state = {feed: []};
  for (const [index, [type, data]] of events.entries()) {
    const event = {step: index + 1, msg_type: type, data, text: api[language].towerEventText(type, data)};
    state.feed.push(event);
    api[language].applyTowerEvent(state, type, data, event);
  }
  return state;
}
const start = [["tower_setup", setup], ["tower_problem", problem]];
const event = (msg_type, data, visible_to = "all", agent_name = "System") => ({events: [{msg_type, content: JSON.stringify(data), visible_to, agent_name}]});
function renderMatch(steps, {language = "ko", view = "public", frame = steps.length} = {}) {
  return api[language].renderMatch({id: "tower-demo", match: {game: "5일차 감옥 매치 · 수식의 탑", players, steps}, frame, view, selected: "", choosePlayer: () => {}, chooseView: () => {}, seek: () => {}, mode: "paused"});
}
for (const language of ["ko", "en"]) {
  test(`${language}: four towers retain all 20 blocks in bottom-to-top order`, () => {
    const html = api[language].render(stateAt(start, language), players);
    assert.equal((html.match(/data-stack=/g) ?? []).length, 4);
    assert.equal((html.match(/data-block=/g) ?? []).length, 20);
    assert.equal((html.match(/class="tower-player"/g) ?? []).length, 3);
    assert.ok(html.indexOf('data-block="b0"') < html.indexOf('data-block="b1"'));
    assert.match(html, /7\/2/);
    assert.match(html, language === "ko" ? /아래에서 위/ : /Bottom to top/);
    assert.match(html, language === "ko" ? /대화 없이 진행/ : /No discussion/);
    assert.match(html, /aria-pressed="true"/);
    assert.doesNotMatch(html, /tower-moved-block|tower-move-cue|tower-failure/);
  });
  test(`${language}: challenge, flip and move highlight only after their events`, () => {
    const events = [...start, ["tower_bid_window", {round: 1, stage: "opening", seconds: 300}], ["tower_bid", {round: 1, player: "P02", moves: 2, first: true}], ["tower_challenge", {round: 1, player: "P02", bid: 2, stake: 1, seconds: 120}], ["tower_move", move]];
    const html = api[language].render(stateAt(events, language), players);
    assert.equal((html.match(/tower-moved-block/g) ?? []).length, 2);
    assert.match(html, /tower-move-cue/);
    assert.match(html, language === "ko" ? /뒤집어 이동/ : /Flip and move/);
    assert.match(html, language === "ko" ? /사용 이동/ : /Moves used/);
    assert.doesNotMatch(api[language].render(stateAt(start, language), players), /tower-moved-block|tower-move-cue/);
  });
  test(`${language}: verdicts preserve fractional values and score history`, () => {
    const state = stateAt([...start, ["tower_move", move], ["tower_verdict", verdict]], language);
    const html = api[language].render(state, players);
    assert.match(html, /tower-failure/);
    assert.match(html, /3 ÷ 2 = 3\/2/);
    assert.match(html, language === "ko" ? /목표 숫자·층수 미완성/ : /Target number or height not met/);
    assert.match(html, language === "ko" ? /판정 후 승점/ : /Scores after the challenge/);
    assert.equal(state.towerGame.scores.P02, -2);
    api[language].applyTowerEvent(state, "tower_problem", {...problem, round: 2, scores: {P01: 3, P02: -2, P03: -1}});
    assert.equal(state.towerVerdict, null);
    assert.equal(state.towerLastMove, null);
    assert.equal(state.towerResults[0].scores.P01, 2);
    assert.equal(state.towerResults[0].step, 4);
  });
  test(`${language}: final rank follows result order instead of sorting race scores`, () => {
    const state = stateAt(start, language);
    state.result = {ranking: ["P01", "P03", "P02"], eliminated: ["P02"], scores: {P01: 7, P02: 4, P03: 9}, pieces: {P01: 5, P02: 2, P03: 2}};
    const html = api[language].render(state, players);
    assert.match(html, language === "ko" ? /최종 순위/ : /Final standings/);
    assert.match(html, /<th scope="row">2<\/th><td>P03<\/td>/);
    assert.match(html, language === "ko" ? /탈락/ : /Eliminated/);
  });
  test(`${language}: rules and actions have readable localized copy`, () => {
    const html = api[language].render({feed: []}, players);
    assert.match(html, language === "ko" ? /사칙연산의 우선순위/ : /normal arithmetic precedence/);
    assert.match(api[language].towerActionText("tower_opening_bid", '{"type":"bid","moves":2}'), language === "ko" ? /입찰 2회/ : /Bid 2 moves/);
    assert.equal(api[language].towerActionText("tower_counter_bid", '{"type":"wait"}'), language === "ko" ? "입찰하지 않음" : "Pass");
    assert.match(api[language].towerActionText("tower_execute", '{"moves":[{"from":1,"to":1,"count":3,"flip":true}]}'), language === "ko" ? /뒤집기/ : /Flip/);
    assert.match(api[language].towerActionText("tower_execute", '{"moves":[]}'), language === "ko" ? /수식 제출/ : /Submit without moving blocks/);
  });
  test(`${language}: MatchReplay integrates all phases without showing future moves or verdicts`, () => {
    const steps = [event("tower_setup", setup), event("tower_problem", problem),
      event("action", {phase: "tower_opening_bid", action: '{"type":"bid","moves":3}'}, "all", "P01"),
      event("tower_bid", {round: 1, player: "P01", moves: 3, first: true}),
      event("tower_bid_window", {round: 1, stage: "counter", seconds: 120, first: {player: "P01", moves: 3}}),
      event("action", {phase: "tower_counter_bid", action: '{"type":"bid","moves":2}'}, "all", "P02"),
      event("tower_bid", {round: 1, player: "P02", moves: 2, first: false}),
      event("tower_challenge", {round: 1, player: "P02", bid: 2, stake: 2, seconds: 120}),
      event("action", {phase: "tower_execute", action: JSON.stringify({moves: [{from: 1, to: 2, count: 2, flip: true}]})}, "all", "P02"),
      event("tower_move", move), event("tower_verdict", verdict)];
    const before = renderMatch(steps, {language, frame: 8});
    assert.match(before, language === "ko" ? /수식의 탑 결과와 기록/ : /Tower of Equations results and records/);
    assert.doesNotMatch(before, /tower-move-cue|tower-failure|3 ÷ 2/);
    assert.doesNotMatch(before, /arena-speech|match-talk/);
    const after = renderMatch(steps, {language});
    assert.match(after, /tower-move-cue/);
    assert.match(after, /tower-failure/);
    assert.match(after, language === "ko" ? /입찰 3회/ : /Bid 3 moves/);
    assert.match(after, language === "ko" ? /뒤집기/ : /Flip/);
    assert.doesNotMatch(after, /&quot;moves&quot;|&quot;from&quot;/);
    assert.equal((after.match(/data-block=/g) ?? []).length, 20);
  });
}
test("MatchReplay keeps strategy notes private across public tower events", () => {
  const steps = [event("tower_setup", setup), event("tower_problem", problem),
    event("decision_note", {phase: "tower_execute", note: "PRIVATE-TOWER-PLAN"}, ["P01"], "P01"), event("tower_move", move)];
  assert.doesNotMatch(renderMatch(steps), /PRIVATE-TOWER-PLAN/);
  assert.doesNotMatch(renderMatch(steps, {view: "P02"}), /PRIVATE-TOWER-PLAN/);
  assert.match(renderMatch(steps, {view: "P01"}), /PRIVATE-TOWER-PLAN/);
  assert.match(renderMatch(steps, {view: "operator"}), /PRIVATE-TOWER-PLAN/);
});
test("events clone inputs, safe players persist, and tied players alone reset to zero", () => {
  const state = stateAt(start);
  api.ko.applyTowerEvent(state, "tower_move", move);
  state.towerGame.stacks[1].pop();
  assert.equal(move.stacks[1].length, 7);
  api.ko.applyTowerEvent(state, "tower_advance", {round: 1, winner: "P01", safe: ["P01"], tied: ["P02", "P03"], reset_scores: true});
  assert.deepEqual(state.towerSafe, ["P01"]);
  assert.equal(state.towerGame.scores.P01, 2);
  assert.deepEqual(state.towerGame.scores, {P01: 2, P02: 0, P03: 0});
  api.ko.applyTowerEvent(state, "tower_problem", {...problem, round: 2, players: ["P02", "P03"], scores: {P02: 0, P03: 0}});
  assert.deepEqual(state.towerSafe, ["P01"]);
  assert.equal(state.towerChallenge, null);
  assert.equal(state.towerBid, null);
});
test("single stack can hold all 20 blocks and remains in the fixed scene", () => {
  const state = stateAt([["tower_setup", {...setup, stacks: [Object.keys(blocks), [], [], []]}]]);
  const html = api.en.render(state, players);
  assert.equal((html.match(/data-block=/g) ?? []).length, 20);
  assert.doesNotMatch(html, /NaN|undefined|Infinity/);
});
