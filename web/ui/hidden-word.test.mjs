import assert from "node:assert/strict";
import {mkdtempSync, rmSync} from "node:fs";
import {createRequire} from "node:module";
import {tmpdir} from "node:os";
import {dirname, join} from "node:path";
import {fileURLToPath} from "node:url";
import {after, test} from "node:test";
import {build} from "esbuild";
import {rulesSummary} from "./rule-summaries.js";

const directory = mkdtempSync(join(tmpdir(), "hidden-word-ui-"));
after(() => rmSync(directory, {recursive: true, force: true}));
const require = createRequire(import.meta.url);
const api = {};
for (const language of ["ko", "en"]) {
  const outfile = join(directory, `${language}.cjs`);
  await build({stdin: {contents: `import React from 'react'; import {renderToStaticMarkup} from 'react-dom/server'; import {HiddenWordStage, HiddenWordInformation} from './hidden-word.jsx'; import {MatchReplay} from './match-replay.jsx'; export {applyHiddenEvent, hiddenActionText, hiddenEventText, hiddenSecretFor, similarityLabel} from './hidden-word-state.js'; export const render = (state,replay) => renderToStaticMarkup(<><HiddenWordStage state={state} replay={replay}/><HiddenWordInformation state={state} replay={replay}/></>); export const renderMatch = (replay) => renderToStaticMarkup(<MatchReplay replay={replay} transport={null}/>);`, loader: "jsx", resolveDir: dirname(fileURLToPath(import.meta.url))}, outfile, bundle: true, platform: "node", format: "cjs", logLevel: "silent", loader: {".css": "empty", ".woff2": "empty", ".md": "text"}, define: {STATIC_REPLAY_BUILD: "false", "process.env.NODE_ENV": '"production"', "globalThis.location": JSON.stringify({search: language === "en" ? "?lang=en" : ""})}});
  api[language] = require(outfile);
}

const players = ["P01", "P02", "P03", "P04", "P05", "P06"];
const scores = Object.fromEntries(players.map((player) => [player, 0]));
const pieces = Object.fromEntries(players.map((player) => [player, 1]));
const record = (type, data, actor = "System", visible = "all") => ({type, data, actor, visible});
const setup = record("word_setup", {order: players, players, pieces, rounds: 2, envelopes: 6});
const envelope = record("word_envelope", {envelope: 2, words: ["보름달", "조약돌", "징검다리", "갈대", "들판"]}, "P01", ["P01"]);
const secret = record("word_secret", {round: 1, setter: "P01", word: "보름달"}, "P01", ["P01"]);
const turn = record("word_turn", {round: 1, setter: "P01", index: 1});
const phase = record("word_phase", {round: 1, setter: "P01", phase: 1});
const hint = record("word_hint", {round: 1, setter: "P01", phase: 1, index: 1, word: "추석", similarity: 88.25}, "P01", ["P01"]);
const similarity = record("word_similarity", {round: 1, setter: "P01", phase: 1, index: 1, similarity: 88.25});
const clue = record("word_clue", {round: 1, setter: "P01", phase: 1, word: "위성", similarity: 96.1, forced: false});
const guess = record("word_guess", {round: 1, setter: "P01", phase: 1, answers: ["달빛", "달님"], spent: 1}, "P02", ["P02"]);
const base = [setup, envelope, secret, turn, phase, hint, similarity, clue, guess];

function stateFor(events, view, language) {
  const state = {feed: []};
  events.forEach(({type, data, actor, visible}, index) => {
    if (view !== "operator" && visible !== "all" && !visible.includes(view)) return;
    const entry = {agent_name: actor, step: index + 1};
    api[language].applyHiddenEvent(state, type, data, entry);
    state.feed.push({...entry, msg_type: type, data});
  });
  return state;
}

function render(events, {view = "operator", selected = "", language = "ko", state} = {}) {
  return api[language].render(state ?? stateFor(events, view, language), {
    view, selected, choosePlayer: () => {}, seek: () => {}, match: {players},
  });
}

function renderMatch(events, view, language, selected = "") {
  const steps = events.map(({type, data, actor, visible}) => ({events: [{msg_type: type,
    content: JSON.stringify(data), agent_name: actor, visible_to: visible}]}));
  const noOp = () => {};
  return api[language].renderMatch({id: "hidden-word-demo", frame: steps.length, mode: "paused",
    match: {game: "5일차 메인 매치 · 히든 워드", players: events.find(({type}) => type === "word_setup")?.data.order ?? players, steps, seed: 1}, view, selected,
    choosePlayer: noOp, chooseView: noOp, seek: noOp});
}

for (const language of ["ko", "en"]) {
  test(`${language}: public clues preserve Korean words and hide private hints, secret and guesses`, () => {
    const html = render(base, {view: "public", selected: "P01", language});
    assert.match(html, /위성/);
    assert.match(html, /96\.1%|88\.25%/);
    assert.doesNotMatch(html, /보름달|추석|조약돌|달빛|달님/);
    assert.match(html, language === "ko" ? /히든 워드 결과와 기록/ : /Hidden Word results and history/);
    assert.equal(stateFor(base, "operator", language).wordHints.length, 1);
  });
  test(`${language}: participant selection cannot expose another player's private data`, () => {
    const html = render(base, {view: "P02", selected: "P01", language});
    assert.match(html, /달빛 \/ 달님/);
    assert.doesNotMatch(html, /보름달|추석|조약돌/);
    const setter = render(base, {view: "P01", selected: "P02", language});
    assert.match(setter, /보름달|추석/);
    assert.match(setter, /조약돌/);
    assert.doesNotMatch(setter, /달빛|달님/);
  });
  test(`${language}: components filter private owner even if given an operator state`, () => {
    const state = stateFor(base, "operator", language);
    assert.doesNotMatch(render(base, {view: "public", language, state}), /보름달|추석|조약돌|달빛|달님/);
    assert.doesNotMatch(render(base, {view: "P03", selected: "P01", language, state}), /보름달|추석|조약돌|달빛|달님/);
  });
  test(`${language}: clues stay visible in a later phase without revealing the hidden word`, () => {
    const html = render([...base, record("word_phase", {round: 1, setter: "P01", phase: 2})], {view: "public", language});
    assert.match(html, /위성/);
    assert.doesNotMatch(html, /보름달/);
  });
  test(`${language}: pending or timed-out hints render before a public clue`, () => {
    const pending = render(base.slice(0, 7), {view: "public", language});
    assert.match(pending, /88\.25%/);
    assert.doesNotMatch(pending, /보름달|추석/);
    const timedOut = record("word_clue", {...clue.data, word: null, similarity: null, forced: true});
    const html = render([...base.slice(0, 7), timedOut], {view: "public", language});
    assert.match(html, language === "ko" ? /힌트 없음/ : /No clue/);
    assert.doesNotMatch(html, /null|NaN|10 candidates|후보 10개/);
    const rejected = record("word_similarity", {...similarity.data, similarity: null, valid: false});
    assert.match(render([...base.slice(0, 5), rejected], {view: "public", language}), language === "ko" ? /명사 아님/ : /Not a noun/);
  });
  test(`${language}: failed guesses keep the secret hidden until it is announced`, () => {
    const verdict = record("word_verdict", {round: 1, setter: "P01", phase: 1, word: null, correct: [],
      guesses: {P02: ["달빛", "달님"]}, points: {P01: 1}, scores: {...scores, P01: 1}, pieces, end: false});
    const first = render([...base, verdict], {view: "public", language});
    assert.match(first, /달빛 \/ 달님/);
    assert.doesNotMatch(first, /보름달/);
    const reveal = record("word_verdict", {...verdict.data, phase: 2, word: "보름달", correct: ["P03"],
      guesses: {P03: ["보름달"]}, points: {P03: 1}, scores: {...scores, P01: 1, P03: 1}, end: true});
    assert.match(render([...base, verdict, reveal], {view: "public", language}), /보름달/);
  });
  test(`${language}: a new setter clears the previous displayed secret and hints`, () => {
    const next = [...base, record("word_turn", {round: 1, setter: "P03", index: 2}),
      record("word_phase", {round: 1, setter: "P03", phase: 1})];
    const html = render(next, {view: "public", language});
    const stage = html.slice(0, html.indexOf('class="caption match-info'));
    assert.doesNotMatch(stage, /보름달|위성|추석|88\.25/);
  });
  test(`${language}: final standings retain score and elimination without private envelope leaks`, () => {
    const end = record("word_final", {ranking: players, scores: {...scores, P01: 13}, pieces: {...pieces, P01: 5}, living: ["P01", "P02"], prison: ["P03", "P04", "P05"], eliminated: ["P06"]});
    const html = render([...base, end], {view: "public", language});
    assert.match(html, /13/);
    assert.match(html, language === "ko" ? /생활동/ : /Living Quarters/);
    assert.match(html, language === "ko" ? /탈락/ : /Eliminated/);
    assert.doesNotMatch(html, /보름달|조약돌/);
  });
  test(`${language}: full replay retains the six-player set and enforces perspective visibility`, () => {
    const html = renderMatch(base, "public", language, "P01");
    const arena = html.slice(html.indexOf('class="arena"'), html.indexOf('class="match-state"'));
    for (const player of players) assert.match(arena, new RegExp(`data-player="${player}"`));
    for (let room = 1; room <= 4; room++) assert.match(arena, new RegExp(language === "ko" ? `${room}번룸` : `Room ${room}`));
    assert.match(html, /hidden-word-stage/);
    assert.match(html, /hidden-word-info/);
    assert.match(html, /위성/);
    assert.doesNotMatch(html, /보름달|추석|조약돌|달빛|달님/);
    assert.doesNotMatch(renderMatch(base, "P03", language, "P01"), /보름달|추석|조약돌|달빛|달님/);
    assert.match(renderMatch(base, "P02", language, "P01"), /달빛/);
    assert.match(renderMatch(base, "operator", language, "P02"), /보름달/);
  });
  test(`${language}: full replay displays discussion and dealer events with readable labels`, () => {
    const events = [setup, record("word_discussion", {stage: "opening", round: 0, rounds: 10}),
      record("word_discussion_round", {stage: "opening", round: 0, rounds: 10, turn: 3}),
      record("word_discussion_end", {stage: "opening", round: 0}),
      record("word_dealer", {player: "P01", stage: "enter"})];
    const html = renderMatch(events, "public", language);
    assert.match(html, language === "ko" ? /시작 전 대화|딜러룸 입장/ : /Opening discussion|Enters dealer room/);
    assert.doesNotMatch(html, /word_(discussion|dealer)/);
  });
  test(`${language}: Word2Vec shows raw signed scores and vocabulary misses without a noun judgment`, () => {
    const vectorSetup = record("word_setup", {...setup.data, version: 2, score_mode: "word2vec"});
    const negative = record("word_similarity", {...similarity.data, similarity: -40, valid: true});
    const unknown = record("word_similarity", {...similarity.data, index: 2, similarity: null, valid: false, reason: "out_of_vocabulary"});
    const events = [vectorSetup, ...base.slice(1, 5), negative, unknown];
    const html = renderMatch(events, "public", language);
    assert.match(html, /Word2Vec/);
    assert.match(html, /−100[~–]100%/);
    assert.match(html, /-40%/);
    assert.match(html, /data-signed="true" data-negative="true"><span style="width:20%;left:30%"/);
    assert.match(html, language === "ko" ? /벡터 사전에 없음/ : /Not in vector vocabulary/);
    assert.doesNotMatch(html, /명사 아님|Not a noun|NaN|보름달|추석/);
    const label = api[language].hiddenEventText("word_similarity", unknown.data);
    assert.match(label, language === "ko" ? /벡터 사전에 없음/ : /Not in vector vocabulary/);
  });
  test(`${language}: inherited five-player roster renders without adding a sixth player`, () => {
    const five = record("word_setup", {...setup.data, order: players.slice(0, 5), players: 5});
    const html = renderMatch([five, ...base.slice(1)], "public", language);
    const arena = html.slice(html.indexOf('class="arena"'), html.indexOf('class="match-state"'));
    assert.equal((arena.match(/data-player="P0[1-6]"/g) ?? []).length, 5);
    assert.doesNotMatch(arena, /data-player="P06"/);
  });
}

test("operator can inspect private candidates and sealed guesses", () => {
  const html = render(base, {selected: "P02", language: "en"});
  assert.match(html, /보름달|추석|조약돌/);
  assert.match(html, /보름달/);
  assert.match(html, /달빛 \/ 달님/);
  assert.equal(api.en.similarityLabel(95), "95%");
  assert.equal(api.en.similarityLabel(95.001), ">95%");
  assert.equal(api.en.hiddenEventText("word_similarity", similarity.data), "Candidate 1 · Similarity 88.25%");
});

test("English rules distinguish raw Word2Vec rules from archived AI judgments", () => {
  const heading = "히든 워드 · 참가자 5~6명 · 2라운드";
  const legacy = rulesSummary(heading, "독립된 AI 판정 문맥입니다. 방송의 Word2Vec 수치와 일치하지 않습니다.");
  assert.match(legacy, /isolated AI similarity judgments/);
  assert.match(legacy, /scripted play uses fixed associations/);
  const current = rulesSummary(heading, "Word2Vec 코사인 유사도 × 100");
  assert.match(current, /direct Korean Word2Vec cosine similarity × 100/);
  assert.match(current, /−100% to 100%/);
  assert.match(current, /same vector vocabulary and raw scores/);
  assert.doesNotMatch(current, /isolated AI|fixed associations/);
});
