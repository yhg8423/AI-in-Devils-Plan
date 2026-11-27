import assert from "node:assert/strict";
import {mkdtempSync, rmSync} from "node:fs";
import {createRequire} from "node:module";
import {tmpdir} from "node:os";
import {dirname, join} from "node:path";
import {fileURLToPath} from "node:url";
import {after, test} from "node:test";

const here = dirname(fileURLToPath(import.meta.url));
const ui = here;
const require = createRequire(join(ui, "package.json"));
const {build} = require("esbuild");
const directory = mkdtempSync(join(tmpdir(), "gradation-ui-"));
after(() => rmSync(directory, {recursive: true, force: true}));
const api = {};
for (const language of ["ko", "en"]) {
  const bundle = join(directory, `${language}.cjs`);
  await build({stdin: {contents: `import {MatchReplay} from './match-replay.jsx'; import React from 'react'; import {renderToStaticMarkup} from 'react-dom/server'; import {GradationScene, GradationStage, GradationInformation} from './gradation.jsx'; export {applyGradEvent, gradEventText, gradActionText} from './gradation.jsx'; export const renderReplay = replay => renderToStaticMarkup(<MatchReplay replay={replay} transport={null}/>); export const render = (state, players, selected='') => renderToStaticMarkup(<><GradationScene state={state} players={players} selected={selected} onChoose={()=>{}}/><GradationStage state={state} players={players}/><GradationInformation state={state} replay={{seek:()=>{}}}/></>);`, loader: "jsx", resolveDir: here}, outfile: bundle, bundle: true, platform: "node", format: "cjs", logLevel: "silent", loader: {".css": "empty", ".woff2": "empty", ".md": "text"}, define: {STATIC_REPLAY_BUILD: "false", "process.env.NODE_ENV": '"production"', "globalThis.location": JSON.stringify({search: language === "en" ? "?lang=en" : ""})}});
  api[language] = require(bundle);
}
const players = ["P01", "P02", "P03"];
const colors = ["black", "silver", "gray", "white", "gray", "silver", "black"];
const counts = {black: 2, silver: 2, gray: 2, white: 1};
const setup = {version: 1, players, order: players, colors, goal: 2, duel: false, discussion: false, prepare_seconds: 300};
const match = {match: 1, players: ["P01", "P02"], waiting: "P03", leader: "P01", streak: 0, replay: 0};
const numbers = {P01: [0, 1, 2, 3, 7, 8, 9], P02: [0, 0, 1, 3, 8, 9, 9]};
const round = {match: 1, round: 1, leader: "P01", scores: {P01: 0, P02: 0}, remaining: {P01: counts, P02: counts}};
const initial = [["grad_setup", setup], ["grad_match", match], ...["P01", "P02"].flatMap((player) => [["grad_layout", {match: 1, player, numbers: numbers[player], elapsed_ns: 1, late: false}], ["grad_ready", {match: 1, player}]]), ["grad_round", round]];

test("submitted cups fit inside the central offer panels", () => {
  const state = stateAt([...initial, ["grad_offer", {match: 1, round: 1, player: "P01", color: "black"}],
    ["grad_offer", {match: 1, round: 1, player: "P02", color: "white"}]]);
  const html = api.ko.render(state, players);
  const paths = [...html.matchAll(/class="grad-cup grad-offered-cup"[^>]*>.*?<path d="([^"]+)"/g)];
  assert.equal(paths.length, 2);
  for (const [, path] of paths) {
    const coordinates = path.match(/M([\d.]+) ([\d.]+)H([\d.]+)L([\d.]+) ([\d.]+)H([\d.]+)Z/);
    assert.ok(coordinates, path);
    for (const y of [Number(coordinates[2]), Number(coordinates[5])]) assert.ok(y >= 206 && y <= 297, path);
  }
});

for (const language of ["ko", "en"]) {
  test(`${language}: full replay protects layouts, original slots and strategy notes`, () => {
    const steps = initial.map(([msg_type, data]) => ({events: [{msg_type, content: JSON.stringify(data),
      visible_to: msg_type === "grad_layout" ? [data.player] : "all", agent_name: data.player ?? "System"}]}));
    steps.push({events: [{msg_type: "decision_note", agent_name: "P01", visible_to: ["P01"],
      content: JSON.stringify({phase: "grad_choose", note: "PRIVATE-GRAD-PLAN"})}]});
    steps.push({events: [{msg_type: "grad_reveal", agent_name: "System", visible_to: "all",
      content: JSON.stringify({match: 1, round: 1, choices: {P01: {color: "black", value: 9}, P02: {color: "gray", value: 8}},
        winner: "P01", scores: {P01: 1, P02: 0}, next_leader: "P01"})}]});
    const render = (view, frame = steps.length - 1) => api[language].renderReplay({id: "grad-smoke",
      match: {game: "6일차 감옥 매치 · 그라데이션", players, steps}, frame, view, selected: "", mode: "paused",
      seek: () => {}, chooseView: () => {}, choosePlayer: () => {}});
    const html = render("public");
    assert.doesNotMatch(html, /data-own-slot|data-cup-value|data-offer-value|PRIVATE-GRAD-PLAN/);
    assert.equal((render("P01").match(/data-own-slot=/g) ?? []).length, 7);
    assert.equal((render("operator").match(/data-own-slot=/g) ?? []).length, 14);
    assert.match(render("P01"), /PRIVATE-GRAD-PLAN/);
    assert.doesNotMatch(render("P02"), /PRIVATE-GRAD-PLAN/);
    assert.match(render("public", steps.length), /data-offer-value="9"/);
    assert.match(html, language === "ko" ? /그라데이션 대결과 기록/ : /Gradation matches and records/);
  });
}

function stateAt(events, language = "ko", perspective = "public") {
  const state = {feed: [], gradPerspective: perspective};
  for (const [index, [type, data]] of events.entries()) {
    const event = {step: index + 1, msg_type: type, data, text: api[language].gradEventText(type, data)};
    state.feed.push(event);
    api[language].applyGradEvent(state, type, data, event);
  }
  return state;
}
const valueCount = (html) => (html.match(/data-cup-value=/g) ?? []).length;
const offers = [["grad_selection", {match: 1, round: 1, player: "P01", slot: 7}], ["grad_offer", {match: 1, round: 1, player: "P01", color: "black"}], ["grad_selection", {match: 1, round: 1, player: "P02", slot: 1}], ["grad_offer", {match: 1, round: 1, player: "P02", color: "black"}]];
const reveal = {match: 1, round: 1, choices: {P01: {color: "black", value: 9}, P02: {color: "black", value: 0}}, winner: "P01", scores: {P01: 1, P02: 0}, next_leader: "P01"};
for (const language of ["ko", "en"]) {
  test(`${language}: public rows use anonymous color counts and no private numbers or slots`, () => {
    const html = api[language].render(stateAt(initial, language), players, "P01");
    assert.equal((html.match(/grad-anonymous-row/g) ?? []).length, 2);
    assert.equal((html.match(/data-anonymous-color=/g) ?? []).length, 8);
    assert.equal(valueCount(html), 0);
    assert.doesNotMatch(html, /data-own-slot=|grad-private-row|Own total|내 합계/);
    assert.match(html, /data-waiting="P03"/);
    assert.match(html, language === "ko" ? /원래 위치는 비공개/ : /Original positions hidden/);
  });
  test(`${language}: either black cup produces byte-identical public HTML`, () => {
    const left = [...initial, ["grad_selection", {match: 1, round: 1, player: "P01", slot: 1}], ["grad_offer", {match: 1, round: 1, player: "P01", color: "black"}]];
    const right = [...initial, ["grad_selection", {match: 1, round: 1, player: "P01", slot: 7}], ["grad_offer", {match: 1, round: 1, player: "P01", color: "black"}]];
    assert.equal(api[language].render(stateAt(left, language), players), api[language].render(stateAt(right, language), players));
    const otherLayout = initial.map(([type, data]) => [type, type === "grad_layout" ? {...data, numbers: [0, 0, 1, 2, 7, 8, 9], elapsed_ns: 8_000_000, late: true} : data]);
    assert.equal(api[language].render(stateAt(initial, language), players), api[language].render(stateAt(otherLayout, language), players));
  });
  test(`${language}: own rows expose seven slots while opponents remain anonymous`, () => {
    const html = api[language].render(stateAt([...initial, ...offers.slice(0, 2)], language, "P01"), players, "P02");
    assert.equal((html.match(/data-own-slot=/g) ?? []).length, 7);
    assert.equal(valueCount(html), 7);
    assert.equal((html.match(/grad-used-cup/g) ?? []).length, 1);
    assert.equal((html.match(/grad-anonymous-row/g) ?? []).length, 1);
    assert.match(html, language === "ko" ? /내 합계 30/ : /Own total 30/);
    const operator = api[language].render(stateAt(initial, language, "operator"), players);
    assert.equal((operator.match(/data-own-slot=/g) ?? []).length, 14);
    assert.equal(valueCount(operator), 14);
    assert.equal((operator.match(/grad-anonymous-row/g) ?? []).length, 0);
  });
  test(`${language}: pending offers stay color-only until the reveal event`, () => {
    const before = api[language].render(stateAt([...initial, ...offers], language), players);
    assert.equal(valueCount(before), 0);
    assert.doesNotMatch(before, /data-offer-value=|라운드 공개 결과|Revealed round results/);
    const after = api[language].render(stateAt([...initial, ...offers, ["grad_reveal", reveal]], language), players);
    assert.equal(valueCount(after), 2);
    assert.match(after, /data-offer-player="P01" data-offer-value="9"/);
    assert.match(after, /data-offer-player="P02" data-offer-value="0"/);
    assert.match(after, language === "ko" ? /라운드 공개 결과/ : /Revealed round results/);
    assert.match(after, language === "ko" ? /보기/ : /View/);
    assert.doesNotMatch(after, /data-own-slot=|내 합계|Own total/);
  });
  test(`${language}: round ties keep the leader and match ties preserve the streak`, () => {
    const events = [...initial, ["grad_match_result", {...match, scores: {P01: 4, P02: 3}, winner: "P01", tied: false, streak: 1}],
      ["grad_match", {...match, match: 2, players: ["P01", "P03"], waiting: "P02", streak: 1}],
      ["grad_round", {...round, match: 2, players: ["P01", "P03"], scores: {P01: 0, P03: 0}, remaining: {P01: counts, P03: counts}}],
      ["grad_reveal", {...reveal, match: 2, choices: {P01: {color: "white", value: 3}, P03: {color: "white", value: 3}}, winner: null, scores: {P01: 0, P03: 0}}],
      ["grad_match_result", {...match, match: 2, players: ["P01", "P03"], scores: {P01: 2, P03: 2}, winner: null, tied: true, streak: 1}]];
    const state = stateAt(events, language);
    assert.equal(state.gradStreak, 1);
    assert.equal(state.gradHolder, "P01");
    assert.equal(state.gradMatch.leader, "P01");
    const html = api[language].render(state, players);
    assert.match(html, language === "ko" ? /총점 동률은 승리·연승에 더하지 않습니다/ : /A tied match adds no win or streak/);
  });
  test(`${language}: a different winner starts a new one-win streak and changes the waiting player`, () => {
    const state = stateAt([...initial, ["grad_match_result", {...match, scores: {P01: 4, P02: 3}, winner: "P01", tied: false, streak: 1}],
      ["grad_match", {...match, match: 2, players: ["P01", "P03"], waiting: "P02", streak: 1}],
      ["grad_match_result", {...match, match: 2, players: ["P01", "P03"], scores: {P01: 1, P03: 5}, winner: "P03", tied: false, streak: 1}],
      ["grad_match", {...match, match: 3, players: ["P03", "P02"], waiting: "P01", leader: "P03", streak: 1}]], language);
    assert.equal(state.gradHolder, "P03");
    assert.equal(state.gradStreak, 1);
    assert.deepEqual(state.gradLayouts, {});
    assert.deepEqual(state.gradUsed, {P03: [], P02: []});
    const html = api[language].render(state, players);
    assert.match(html, /data-waiting="P01"/);
    assert.equal(valueCount(html), 0);
  });
  test(`${language}: two-player mode clearly names the adaptation and final joint ranks follow groups`, () => {
    const two = players.slice(0, 2);
    const state = stateAt([["grad_setup", {...setup, players: two, order: two, duel: true}], ["grad_match", {...match, waiting: null}]], language);
    const html = api[language].render(state, two);
    assert.doesNotMatch(html, /data-waiting=/);
    assert.match(html, language === "ko" ? /2인 단판 · 시뮬레이터 변형/ : /Two-player single-match adaptation/);
    const final = stateAt(initial, language);
    final.result = {ranking: ["P01", "P02", "P03"], ranking_groups: [["P01"], ["P02", "P03"]], finalists: ["P01"], eliminated: ["P02", "P03"], pieces: {P01: 4, P02: 5, P03: 6}};
    const done = api[language].render(final, players);
    assert.match(done, /<th scope="row">2<\/th><td>P02<\/td>/);
    assert.match(done, /<th scope="row">2<\/th><td>P03<\/td>/);
    assert.match(done, language === "ko" ? /결승 진출/ : /Finalist/);
  });
}
test("remaining color counts decrement on offers exactly once and inputs stay immutable", () => {
  const state = stateAt(initial);
  const offer = {match: 1, round: 1, player: "P01", color: "black"};
  api.ko.applyGradEvent(state, "grad_offer", offer);
  api.ko.applyGradEvent(state, "grad_offer", offer);
  assert.equal(state.gradMatch.remaining.P01.black, 1);
  assert.equal(counts.black, 2);
  state.gradLayouts.P01.numbers.pop();
  assert.equal(numbers.P01.length, 7);
});
test("private layout and slot text never serializes numbers or slot IDs", () => {
  for (const language of ["ko", "en"]) {
    assert.doesNotMatch(api[language].gradEventText("grad_layout", {player: "P01", numbers: numbers.P01}), /7|8|9|30/);
    assert.doesNotMatch(api[language].gradEventText("grad_selection", {player: "P01", slot: 7}), /7/);
    assert.equal(api[language].gradActionText("grad_prepare", JSON.stringify({numbers: numbers.P01})), api[language].gradActionText("grad_prepare", JSON.stringify({numbers: numbers.P02})));
    assert.doesNotMatch(api[language].gradActionText("grad_prepare", JSON.stringify({numbers: numbers.P01})), /0,1|8|9|30/);
    assert.doesNotMatch(api[language].gradActionText("grad_choose", '{"slot":7}'), /7/);
  }
});
test("palette grows lighter toward the center with matching text contrast", () => {
  const html = api.en.render(stateAt(initial, "en", "operator"), players);
  for (const color of ["#20252d", "#697482", "#b4bac2", "#f5f3ec"]) assert.match(html, new RegExp(`fill="${color}"`));
  assert.match(html, /data-cup-color="silver"[\s\S]*?class="grad-cup-number grad-light-ink"/);
});
test("seven round reveals are preserved and two consecutive match wins remain distinct from round points", () => {
  const rounds = Array.from({length: 7}, (_, index) => ["grad_reveal", {...reveal, round: index + 1, winner: index < 4 ? "P01" : "P02", scores: {P01: Math.min(index + 1, 4), P02: Math.max(0, index - 3)}}]);
  const firstResult = {...match, scores: {P01: 4, P02: 3}, winner: "P01", tied: false, streak: 1};
  const state = stateAt([...initial, ...rounds, ["grad_match_result", firstResult]], "en");
  assert.equal(state.gradRounds.length, 7);
  assert.equal(state.gradStreak, 1);
  const html = api.en.render(state, players);
  assert.equal((html.match(/>View<\/button>/g) ?? []).length, 7);
  api.en.applyGradEvent(state, "grad_match", {...match, match: 2, players: ["P01", "P03"], waiting: "P02", streak: 1});
  api.en.applyGradEvent(state, "grad_match_result", {...firstResult, match: 2, players: ["P01", "P03"], scores: {P01: 5, P03: 2}, waiting: "P02", streak: 2});
  assert.equal(state.gradStreak, 2);
  assert.equal(state.gradHolder, "P01");
});
