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

function renderMatch(events, view, language, selected = "", frame = events.length) {
  const steps = events.map(({type, data, actor, visible}) => ({events: [{msg_type: type,
    content: JSON.stringify(data), agent_name: actor, visible_to: visible}]}));
  const noOp = () => {};
  return api[language].renderMatch({id: "hidden-word-demo", frame, mode: "paused",
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
  test(`${language}: vocabulary fallback can reveal an unsubmitted word without changing archived forced labels`, () => {
    const nearest = record("word_clue", {...clue.data, word: "만월", similarity: 83.4, forced: true, source: "word2vec_nearest"});
    const events = [...base.slice(0, 7), nearest];
    const state = stateFor(events, "public", language);
    assert.equal(state.wordClue.source, "word2vec_nearest");
    assert.equal(state.wordHints.length, 1);
    assert.equal(state.wordHints[0].word, undefined);
    const html = renderMatch(events, "public", language);
    assert.match(html, /만월/);
    assert.match(html, language === "ko" ? /Word2Vec 사전에서 정답과 가장 가까운 단어입니다/ : /The closest word to the answer in the Word2Vec vocabulary/);
    assert.doesNotMatch(html, /보름달|추석|submitted in this phase|이 단계에서 제출한 후보 중/);
    const archived = render([...base.slice(0, 7), record("word_clue", {...clue.data, forced: true})], {view: "public", language});
    assert.match(archived, language === "ko" ? /이 단계에서 제출한 후보 중 유사도가 가장 높은 단어입니다/ : /The most similar word among the candidates submitted in this phase/);
    assert.doesNotMatch(archived, /closest word to the answer|Word2Vec 사전에서/);
    const normal = render([...base.slice(0, 7), record("word_clue", {...clue.data, source: "submitted_hint"})], {view: "public", language});
    assert.doesNotMatch(normal, /closest word to the answer|Word2Vec 사전에서|submitted in this phase|이 단계에서 제출한 후보 중/);
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
  test(`${language}: fastText metadata labels the current scorer and noun fallback without changing archived models`, () => {
    const fastText = record("word_setup", {...setup.data, version: 2, score_mode: "fasttext", discussion: false,
      scorer: {id: "fasttext-cc-ko-300", dimensions: 300, vocabulary: 2000000, score: "cosine*100"}});
    const negative = record("word_similarity", {...similarity.data, similarity: -40, valid: true, mode: "fasttext"});
    const unknown = record("word_similarity", {...similarity.data, index: 2, similarity: null, valid: false, reason: "out_of_vocabulary", mode: "fasttext"});
    const nearest = record("word_clue", {...clue.data, word: "만월", similarity: 83.4, forced: true, source: "fasttext_nearest"});
    const events = [fastText, ...base.slice(1, 5), negative, unknown, nearest];
    const html = renderMatch(events, "public", language);
    assert.match(html, /fastText · cc\.ko\.300/);
    assert.match(html, /-40%/);
    assert.match(html, /data-signed="true" data-negative="true"><span style="width:20%;left:30%"/);
    assert.match(html, /만월/);
    assert.match(html, language === "ko" ? /fastText 사전에서 정답과 가장 가까운 일반명사입니다/ : /The closest common noun to the answer in the fastText vocabulary/);
    assert.match(html, language === "ko" ? /벡터 사전에 없음/ : /Not in vector vocabulary/);
    assert.doesNotMatch(html, /Word2Vec|보름달|추석|명사 아님|Not a noun/);
    assert.match(api[language].hiddenEventText("word_setup", fastText.data), /fastText/);
    const legacy = record("word_setup", {...setup.data, version: 2, score_mode: "word2vec", scorer: {id: "kyubyong-ko-word2vec-2016", dimensions: 200}});
    const archived = renderMatch([legacy, ...base.slice(1)], "public", language);
    assert.match(archived, /Word2Vec/);
    assert.doesNotMatch(archived, /fastText/);
  });
  test(`${language}: relative reveal qualification preserves raw scores and hides the private benchmark`, () => {
    const relative = record("word_setup", {...setup.data, version: 2, score_mode: "fasttext", discussion: false,
      reveal_rule: "nearest_noun_ratio_v1", hint_filter: "same_as_nearest"});
    const candidate = (index, data) => record("word_similarity", {...similarity.data, index, valid: true, ...data});
    const events = [relative, ...base.slice(1, 5),
      candidate(1, {similarity: 55.04, qualifies: true, max_similarity: 57.93746, cutoff: 55.040587, nearest_name: "비공개기준명사"}),
      candidate(2, {similarity: 96, qualifies: false}), candidate(3, {similarity: 96}),
      candidate(4, {similarity: -12.34, qualifies: false}),
      candidate(5, {similarity: null, valid: false, reason: "not_common_noun", qualifies: false})];
    const state = stateFor(events, "public", language);
    assert.equal(state.wordHints[0].qualifies, true);
    assert.equal(state.wordHints[1].qualifies, false);
    assert.equal(state.wordHints[2].qualifies, undefined);
    assert.equal(state.wordHints[0].max_similarity, undefined);
    assert.equal(state.wordHints[0].cutoff, undefined);
    assert.equal(state.wordHints[0].nearest_name, undefined);
    const html = render(events, {view: "public", language});
    assert.match(html, language === "ko" ? /최근접 일반명사 유사도의 95% 초과 시 공개/ : /Reveal above 95% of the nearest common noun’s similarity/);
    assert.match(html, language === "ko" ? /원본 유사도/ : /Raw similarity/);
    const rows = [...html.matchAll(/<li data-threshold="(true|false)">([\s\S]*?)<\/li>/g)];
    assert.equal(rows.length, 5);
    assert.equal(rows.filter(([, qualifies]) => qualifies === "true").length, 1);
    assert.equal(rows[0][1], "true");
    assert.match(rows[0][2], /55\.04%/);
    assert.match(rows[0][2], language === "ko" ? /기준 충족/ : /Criterion met/);
    for (const row of rows.slice(1, 3)) {
      assert.equal(row[1], "false");
      assert.match(row[2], /96%/);
      assert.doesNotMatch(row[2], /기준 충족|Criterion met/);
    }
    assert.match(rows[3][2], /-12\.34%/);
    assert.match(rows[4][2], language === "ko" ? /일반명사 아님/ : /Not a common noun/);
    for (const view of ["public", "operator", "P01", "P03"]) {
      assert.doesNotMatch(renderMatch(events, view, language), /비공개기준명사|57\.93746|55\.040587|&gt;95%/);
    }
    const announced = record("word_clue", {...clue.data, word: "비공개기준명사", similarity: 57.94, source: "fasttext_nearest", forced: true});
    assert.match(renderMatch([...events, announced], "public", language), /비공개기준명사/);
    const label = api[language].hiddenEventText("word_similarity", events.at(-1).data);
    assert.match(label, language === "ko" ? /일반명사 아님/ : /Not a common noun/);
  });
  test(`${language}: inherited five-player roster renders without adding a sixth player`, () => {
    const five = record("word_setup", {...setup.data, order: players.slice(0, 5), players: 5});
    const html = renderMatch([five, ...base.slice(1)], "public", language);
    const arena = html.slice(html.indexOf('class="arena"'), html.indexOf('class="match-state"'));
    assert.equal((arena.match(/data-player="P0[1-6]"/g) ?? []).length, 5);
    assert.doesNotMatch(arena, /data-player="P06"/);
  });
  test(`${language}: silent setup suppresses discussion status while archived logs retain it`, () => {
    const discussion = record("word_discussion_round", {stage: "opening", round: 0, rounds: 10, turn: 3});
    const silent = record("word_setup", {...setup.data, version: 2, score_mode: "word2vec", discussion: false});
    assert.doesNotMatch(render([silent, discussion], {view: "public", language}), /class="hidden-discussion"/);
    assert.match(render([setup, discussion], {view: "public", language}), /class="hidden-discussion"/);
    assert.equal(stateFor([silent], "public", language).wordSetup.discussion, false);
  });
  test(`${language}: silent replay keeps private strategy and perspective filtering without conversation UI`, () => {
    const silent = record("word_setup", {...setup.data, version: 2, score_mode: "word2vec", discussion: false});
    const plan = record("decision_note", {phase: "word_preparation", note: "단독검토 전용메모"}, "P01", ["P01"]);
    const events = [silent, ...base.slice(1), plan];
    const html = renderMatch(events, "operator", language);
    assert.match(html, /id="match-strategy"/);
    assert.match(html, /단독검토 전용메모/);
    assert.doesNotMatch(html, /id="match-talk"|arena-speech/);
    assert.match(renderMatch(events, "P01", language), /단독검토 전용메모/);
    assert.doesNotMatch(renderMatch(events, "public", language), /단독검토 전용메모|보름달|추석|조약돌|달빛|달님/);
    assert.doesNotMatch(renderMatch(events, "P03", language), /단독검토 전용메모|보름달|추석|조약돌|달빛|달님/);
    const opening = renderMatch(events, "public", language, "", 0);
    assert.match(opening, /id="match-strategy"/);
    assert.doesNotMatch(opening, /id="match-talk"|arena-speech|단독검토 전용메모|보름달|추석|조약돌|달빛|달님/);
    const archived = renderMatch(base, "public", language);
    assert.match(archived, /id="match-talk"/);
    assert.match(archived, /arena-speech/);
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
  assert.match(current, /ten opening discussion turns and up to four/);
  const silent = rulesSummary(heading, "Word2Vec 코사인 유사도 × 100\n참가자 간 대화·협상·귓속말과 룸 이동은 없습니다.");
  assert.match(silent, /private strategy preparation/);
  assert.match(silent, /cannot discuss, negotiate, whisper or move rooms/);
  assert.match(silent, /Relationship reviews follow verdicts/);
  assert.doesNotMatch(silent, /ten opening discussion turns|up to four before each setter/);
  assert.match(silent, /highest-scoring hint of that phase/);
  const nearest = rulesSummary(heading, "Word2Vec 코사인 유사도 × 100\n참가자 간 대화·협상·귓속말과 룸 이동은 없습니다.\n기준을 넘지 못하면 제출한 힌트와 관계없이 Word2Vec 사전에서 정답 자체를 제외하고 가장 가까운 단어를 공개합니다.");
  assert.match(nearest, /across the full Word2Vec vocabulary, excluding the answer itself, regardless of the submitted candidates/);
  assert.match(nearest, /direct Korean Word2Vec|private strategy preparation/);
  assert.doesNotMatch(nearest, /highest-scoring hint of that phase|opening discussion turns/);
  const fastText = rulesSummary(heading, "fastText 코사인 유사도 × 100\n참가자 간 대화·협상·귓속말과 룸 이동은 없습니다.\n기준을 넘지 못하면 제출한 힌트와 관계없이 fastText 사전에서 정답 자체를 제외하고 가장 가까운 일반명사를 공개합니다.");
  assert.match(fastText, /direct Korean fastText cosine similarity × 100/);
  assert.match(fastText, /closest common noun.*full fastText vocabulary/);
  assert.match(fastText, /cc\.ko\.300 text vectors: 300 dimensions trained on Common Crawl and Wikipedia/);
  assert.match(fastText, /fixed vocabulary and does not generate vectors for unknown words/);
  assert.doesNotMatch(fastText, /Word2Vec|isolated AI|fixed associations|opening discussion turns/);
  const relative = rulesSummary(heading, "fastText 코사인 유사도 × 100\n참가자 간 대화·협상·귓속말과 룸 이동은 없습니다.\n최근접 일반명사 유사도의 95%를 초과하면 힌트를 공개합니다.\n기준을 넘지 못하면 제출한 힌트와 관계없이 fastText 사전에서 정답 자체를 제외하고 가장 가까운 일반명사를 공개합니다.");
  assert.match(relative, /raw cosine similarity exceeds 95% of the similarity of the closest eligible common noun/);
  assert.match(relative, /no submitted hint meets this criterion within the limit/);
  assert.match(relative, /Displayed values remain raw cosine similarity × 100/);
  assert.match(relative, /same dictionary-attested Kiwi common nouns \(NNG\)/);
  assert.match(relative, /Unknown words and words outside that noun set use one attempt without a score/);
  assert.match(relative, /simulator extension; the broadcast’s scoring formula has not been verified/);
  assert.doesNotMatch(relative, /until a score exceeds 95%|no submitted hint exceeds 95%/);
});
