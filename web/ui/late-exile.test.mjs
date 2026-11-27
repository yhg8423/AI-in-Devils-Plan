import assert from "node:assert/strict";
import {mkdtempSync, rmSync} from "node:fs";
import {createRequire} from "node:module";
import {tmpdir} from "node:os";
import {dirname, join} from "node:path";
import {fileURLToPath} from "node:url";
import {after, test} from "node:test";
import {build} from "esbuild";

const directory = mkdtempSync(join(tmpdir(), "late-exile-ui-"));
after(() => rmSync(directory, {recursive: true, force: true}));
const require = createRequire(import.meta.url), api = {};
for (const language of ["ko", "en"]) {
  const bundle = join(directory, `${language}.cjs`);
  await build({stdin: {contents: `import React from 'react'; import {renderToStaticMarkup} from 'react-dom/server'; import {MatchReplay} from './match-replay.jsx'; export * from './late-exile.jsx'; export {rulesSummary} from './rule-summaries.js'; export {gameTitle} from './locale.js'; export const render = replay => renderToStaticMarkup(<MatchReplay replay={replay} transport={null}/>);`, loader: "jsx", resolveDir: dirname(fileURLToPath(import.meta.url))}, outfile: bundle, bundle: true, platform: "node", format: "cjs", logLevel: "silent", loader: {".css": "empty", ".woff2": "empty", ".md": "text"}, define: {STATIC_REPLAY_BUILD: "false", "process.env.NODE_ENV": '"production"', "globalThis.location": JSON.stringify({search: language === "en" ? "?lang=en" : ""})}});
  api[language] = require(bundle);
}
const noop = () => {}, four = ["P01", "P02", "P03", "P04"], two = four.slice(0, 2);
const plainText = (html) => html.replace(/<[^>]+>/g, " ");
const event = (msg_type, data, visible_to = "all", agent_name = "System") => ({events: [{msg_type, content: typeof data === "string" ? data : JSON.stringify(data), visible_to, agent_name}]});
const picture = (id) => ({id, image: `data:image/png;base64,${id}`, width: 1000, height: 760, grid: {columns: 5, rows: 5, left: 25, top: 70, cell_width: 190, cell_height: 132}});
const flagSetup = event("flag_setup", {version: 2, players: four, normal_rounds: 3, survivor_count: 3, study_seconds: 30, blank_seconds: 5, answer_seconds: 60});
const flagPhase = (stage, id, round = 1) => event("flag_phase", {round, players: four, overtime: false, stage, picture: id ? picture(id) : null});
const flagResults = event("flag_result", {round: 1, players: four, overtime: false, scores: Object.fromEntries(four.map((p) => [p, 3])), totals: Object.fromEntries(four.map((p) => [p, 3])), correct: [2, 4, 6, 8, 10], picture: picture("CHOICES"), answers: Object.fromEntries(four.map((p) => [p, {marks: [1, 2, 4, 6, 9], correct: [2, 4, 6], score: 3}]))});
const flagSteps = [flagSetup, flagPhase("observe", "STUDY-SECRET"), event("flag_frame", {round: 1, index: 5, seconds: 1, picture: picture("SINGLE-STUDY")}), event("flag_memory", {round: 1, player: "P01", memory: "PRIVATE-MEMORY-ONE"}, ["P01"], "P01"), event("flag_memory", {round: 1, player: "P02", memory: "PRIVATE-MEMORY-TWO"}, ["P02"], "P02"), flagPhase("blank"), flagPhase("answer", "CHOICES"), event("flag_marks", {round: 1, player: "P01", marks: [1, 2, 4, 6, 9]}, ["P01"], "P01")];
function render(steps, game, players, {language = "ko", view = "public", selected = "", frame = steps.length} = {}) {
  return api[language].render({id: "late-exile-demo", match: {game, players, steps}, frame, view, selected, choosePlayer: noop, chooseView: noop, seek: noop, mode: "paused"});
}
const flagRender = (steps, options) => render(steps, "유배지 매치 6 · 만국기", four, options);
const rectSetup = event("rect_setup", {version: 2, players: four, survivor_count: 2, priority: four, limit_seconds: 300, answer_seconds: 10});
const rectQuestion = (question = 1) => event("rect_question", {round: 1, question, players: four, board: picture(`RECT-${question}`), target: 7, limit_seconds: 300});
const rectRender = (steps, options) => render(steps, "유배지 매치 7 · 네모 세기", four, options);
const gomokuSetup = event("gomoku_setup", {version: 1, players: two, size: 15, colors: {P01: "black", P02: "white"}, points_per_round: 10});
const gameStart = (game = 1, first_selector = "P01") => event("gomoku_game", {game, replay: game - 1, first_selector});
const gomokuRound = event("gomoku_round", {game: 1, round: 1, selector: "P01"});
const points = [[1, 1], [2, 1], [3, 1]];
const gomokuSteps = [gomokuSetup, gameStart(), gomokuRound,
  event("gomoku_wallet", {game: 1, round: 1, player: "P01", available: 991, carry: 771}, ["P01"], "P01"),
  event("gomoku_wallet", {game: 1, round: 1, player: "P02", available: 992, carry: 772}, ["P02"], "P02"),
  event("gomoku_select", {game: 1, round: 1, selector: "P01", points}),
  event("gomoku_bid", {game: 1, round: 1, player: "P01", bids: [111, 222, 333], spent: 666, remaining: 325, carry: 162}, ["P01"], "P01"),
  event("gomoku_bid", {game: 1, round: 1, player: "P02", bids: [112, 223, 334], spent: 669, remaining: 323, carry: 161}, ["P02"], "P02")];
const placement = event("gomoku_placement", {game: 1, round: 1, selector: "P01", points, owners: ["P01", "P02", "P01"], stones: [{x: 1, y: 1, player: "P01"}, {x: 2, y: 1, player: "P02"}, {x: 3, y: 1, player: "P01"}], winning_lines: {P01: [], P02: []}});
const gomokuRender = (steps, options) => render(steps, "유배지 매치 8 · 포인트 오목", two, options);

for (const language of ["ko", "en"]) {
  test(`${language}: Flags uses four distinct platforms, retains strategy tabs and hides study images while answering`, () => {
    const study = flagRender(flagSteps, {language, frame: 3});
    assert.match(study, /SINGLE-STUDY/);
    assert.equal((study.match(/class="exile-lift"/g) ?? []).length, 4);
    const positions = [...study.matchAll(/class="exile-player" style="([^"]+)"/g)].map((match) => match[1]);
    assert.equal(new Set(positions).size, 4);
    assert.deepEqual(positions.slice(0, 4), ["left:11.5%;top:29%", "left:88.5%;top:29%", "left:11.5%;top:76%", "left:88.5%;top:76%"]);
    const answer = flagRender(flagSteps, {language});
    assert.match(answer, /CHOICES/);
    assert.doesNotMatch(answer, /STUDY-SECRET|SINGLE-STUDY|PRIVATE-MEMORY/);
    assert.match(answer, /match-strategy/);
    assert.match(answer, /flag-rounds/);
    assert.doesNotMatch(answer, /match-talk/);
    assert.match(answer, language === "ko" ? /앞서 관찰한 국기 5개/ : /flags among 25 that appeared earlier/);
    assert.match(answer, language === "ko" ? /4명 중 상위 3명이 생존/ : /top 3 of 4 players survive/);
    const own = flagRender(flagSteps, {language, view: "P01", selected: "P02"});
    assert.match(own, /PRIVATE-MEMORY-ONE/);
    assert.doesNotMatch(own, /PRIVATE-MEMORY-TWO|data-answer=/);
    assert.match(own, /data-mark="1"/);
    assert.match(own, /class="flag-choice"/);
  });
  test(`${language}: Flags reveals correct circles and round scores, then lowers only eliminated players`, () => {
    const final = event("match_result", {ranking: four, scores: Object.fromEntries(four.map((p) => [p, 9])), survivors: four.slice(0, 3), eliminated: four.slice(3)});
    const html = flagRender([...flagSteps, flagResults, final], {language});
    assert.match(html, /data-answer="10"/);
    assert.match(html, /flag-answers/);
    assert.equal((html.match(/data-status="eliminated"/g) ?? []).length, 1);
    assert.equal((html.match(/data-status="safe"/g) ?? []).length, 3);
    assert.match(html, language === "ko" ? /정답 국기/ : /Correct flags/);
  });
  test(`${language}: historical Flags and Rectangle setups retain their recorded player and survivor counts`, () => {
    const legacyPlayers = four.slice(0, 3);
    for (const [game, type, label] of [["만국기", "flag_setup", /top 2 of 3 players survive/], ["네모 세기", "rect_setup", /first 2 correct players survive; the other 1/]]) {
      const setup = event(type, {version: 1, players: legacyPlayers, priority: legacyPlayers, survivor_count: 2});
      const ended = event("match_result", {ranking: legacyPlayers, survivors: two, eliminated: ["P03"]});
      const html = render([setup, ended], `유배지 매치 ${game === "만국기" ? 6 : 7} · ${game}`, legacyPlayers, {language});
      assert.equal((html.match(/data-status="safe"/g) ?? []).length, 2);
      assert.equal((html.match(/data-status="eliminated"/g) ?? []).length, 1);
      if (language === "en") assert.match(html, label);
      else assert.match(html, game === "만국기" ? /3명 중 상위 2명이 생존/ : /2명이 생존하고 나머지 1명/);
    }
  });
  test(`${language}: Rectangle Counting shows the grid, buzzer and wrong-answer lock, resetting only the next question`, () => {
    const steps = [rectSetup, rectQuestion(), event("rect_window", {round: 1, question: 1, window: 1, eligible: four}), event("rect_buzz", {round: 1, question: 1, player: "P01", elapsed_ns: 123}), event("rect_attempt", {round: 1, question: 1, player: "P01", count: 19, correct: false})];
    const buzzing = rectRender(steps, {language, frame: 4});
    assert.match(buzzing, language === "ko" ? /버저!/ : /BUZZ!/);
    const wrong = rectRender(steps, {language});
    assert.match(wrong, /data-status="locked"/);
    assert.match(wrong, /RECT-1/);
    assert.match(wrong, /match-strategy/);
    assert.match(wrong, /rect-attempts/);
    assert.doesNotMatch(wrong, /match-talk/);
    const next = rectRender([...steps, event("rect_question_end", {round: 1, question: 1, count: 17, winner: null}), rectQuestion(2)], {language});
    assert.match(next, /RECT-2/);
    assert.doesNotMatch(next, /data-status="locked"/);
  });
  test(`${language}: Rectangle Counting keeps exactly two survivors and lowers the other two platforms`, () => {
    const steps = [rectSetup, rectQuestion(), event("rect_round_result", {round: 1, question: 1, winner: "P01", count: 17, rank: 1}), rectQuestion(2), event("rect_round_result", {round: 2, question: 2, winner: "P02", count: 12, rank: 2})];
    const policy = rectRender(steps, {language});
    assert.match(policy, language === "ko" ? /먼저 정답을 맞힌 2명이 생존하고 나머지 2명/ : /first 2 correct players survive; the other 2/);
    const html = rectRender([...steps, event("match_result", {ranking: four, ranking_groups: [["P01"], ["P02"], ["P03", "P04"]], survivors: two, eliminated: four.slice(2), scores: {P01: 1, P02: 1, P03: 0, P04: 0}})], {language});
    assert.equal((html.match(/data-status="safe"/g) ?? []).length, 2);
    assert.equal((html.match(/data-status="eliminated"/g) ?? []).length, 2);
  });
  test(`${language}: Point Gomoku fits a 15×15 board, colors stones clearly, and never publishes private bids or carry`, () => {
    const publicView = gomokuRender([...gomokuSteps, placement], {language});
    assert.match(publicView, /viewBox="0 0 620 620"/);
    assert.match(publicView, /data-board-size="15"/);
    assert.match(publicView, /data-selected-point="3"/);
    assert.match(publicView, /data-stone-player="P01"/);
    assert.match(publicView, /fill="#fff6dd"/);
    assert.match(publicView, /fill="#19202b"/);
    assert.doesNotMatch(plainText(publicView), /991|992|771|772|111|222|333|112|223|334/);
    const own = gomokuRender([...gomokuSteps, placement], {language, view: "P01", selected: "P02"});
    assert.match(own, /991/);
    assert.match(own, /111/);
    assert.doesNotMatch(plainText(own), /992|772|112|223|334/);
    const operator = gomokuRender([...gomokuSteps, placement], {language, view: "operator"});
    assert.match(operator, /991/); assert.match(operator, /992/);
    assert.match(operator, /111/); assert.match(operator, /112/);
    assert.match(publicView, /gomoku-bids/);
    assert.match(publicView, /match-strategy/);
  });
  test(`${language}: a Gomoku replay clears stones and selection and final result names the returnee and five Pieces`, () => {
    const drawnPlacement = structuredClone(placement);
    const data = JSON.parse(drawnPlacement.events[0].content);
    data.winning_lines = {P01: [[[1, 1], [2, 1], [3, 1], [4, 1], [5, 1]]]};
    drawnPlacement.events[0].content = JSON.stringify(data);
    const steps = [...gomokuSteps, drawnPlacement, event("gomoku_game_result", {game: 1, round: 1, winner: null, reason: "equal_fives", counts: {P01: 1, P02: 1}}), gameStart(2, "P02")];
    assert.match(gomokuRender(steps, {language, frame: 9}), /data-winning-line="1"/);
    const draw = gomokuRender(steps, {language});
    assert.doesNotMatch(draw, /data-stone-player=|data-selected-point=|data-winning-line=/);
    const html = gomokuRender([...steps, event("gomoku_finish", {winner: "P02", eliminated: ["P01"], pieces_awarded: {P01: 0, P02: 5}})], {language});
    assert.equal((html.match(/data-status="eliminated"/g) ?? []).length, 1);
    assert.match(html, /gomoku-returnee/);
    assert.match(html, language === "ko" ? /본선 복귀 · 피스 5개 획득/ : /Returns to the main match · Gains five Pieces/);
  });
}

test("reducers copy public payloads without puzzle solutions or mutation and defensive owner helpers reject cross-player selection", () => {
  const state = {};
  api.en.applyFlagEvent(state, "flag_setup", {players: four});
  const phase = {round: 1, stage: "answer", players: four, picture: picture("CHOICES"), solution: "DO-NOT-KEEP"};
  const original = structuredClone(phase);
  api.en.applyFlagEvent(state, "flag_phase", phase);
  api.en.applyFlagEvent(state, "flag_marks", {round: 1, player: "P02", marks: [24, 25]});
  api.en.applyFlagEvent(state, "flag_memory", {round: 1, player: "P02", memory: "NOT-YOURS"});
  assert.doesNotMatch(JSON.stringify(state), /DO-NOT-KEEP/);
  assert.deepEqual(phase, original);
  assert.equal(api.en.flagView(state, four, "P02", "P01").memory, null);
  assert.deepEqual(api.en.flagView(state, four, "P02", "P01").marks, []);
  state.gomokuBids = [{player: "P01", bids: [1, 2, 3]}, {player: "P02", bids: [2, 3, 4]}];
  assert.deepEqual(api.en.gomokuPrivateRows(state, two, "P02", "P01").map((r) => r.player), ["P01"]);
  assert.deepEqual(api.en.gomokuPrivateRows(state, two, "P02", "public"), []);
});

test("new English names and rules retain remembered-flags, negative rectangles, sealed bids, exact fives and draw policies", () => {
  assert.equal(api.en.gameTitle("유배지 매치 8 · 포인트 오목"), "Exile Match 8 · Point Gomoku");
  assert.match(api.en.rulesSummary("만국기 · 유배지 개인전", ""), /previously shown flags/);
  assert.doesNotMatch(api.en.rulesSummary("만국기 · 유배지 개인전", ""), /unseen|did not appear/);
  assert.match(api.en.rulesSummary("네모 세기 · 유배지 개인전", ""), /negative values|Negative values/);
  const rules = api.en.rulesSummary("포인트 오목 · 유배지 최후의 대결", "");
  for (const pattern of [/non-selector/, /rounded down/, /remain private/, /exact fives/, /fresh-board replay/, /five Pieces/]) assert.match(rules, pattern);
});

test("English rule summaries preserve recorded survivor counts while describing the corrected four-player defaults", () => {
  const rules = api.en.rulesSummary;
  const newFlags = rules("만국기 · 4인 개인전", "4명이 참가하며 정규·연장전 결과 상위 3명이 생존하고 최하위 1명은 탈락합니다.");
  assert.match(newFlags, /Four players compete, and the top three survive/);
  assert.doesNotMatch(newFlags, /six participants|top two survive/);
  assert.match(rules("만국기 · 유배지 개인전", "방송의 3인 경기에서는 상위 2명이 생존합니다."), /The top two survive/);
  assert.match(rules("네모 세기 · 4인 개인전", "두 명이 생존하면 끝나며, 남은 두 명은 탈락합니다."), /first two correct players survive; the other two are eliminated/);
  assert.match(rules("네모 세기 · 유배지 개인전", "남은 마지막 한 명이 탈락합니다."), /The last remaining player is eliminated/);
  for (const body of ["참가자 수보다 한 명 적은 인원이 완성하면 끝나고 남은 한 명이 탈락합니다.", "참가자보다 한 명 적은 인원이 완성하면 끝나고 남은 한 명이 탈락합니다."]) {
    const legacy = rules("대칭 퍼즐 · 유배지", body);
    assert.match(legacy, /exactly one player eliminated/);
    assert.doesNotMatch(legacy, /other two are eliminated/);
  }
  assert.match(rules("대칭 퍼즐 · 유배지", "참가자 4명 중 먼저 완성한 2명이 생존하고 남은 2명은 탈락합니다."), /first two to complete all three colors survive, and the other two are eliminated/);
  assert.match(rules("울타리 치기 · 4인 개인전", "먼저 올바른 고리를 제출한 3명은 순서대로 생존을 확정하고, 남은 1명은 탈락합니다."), /first three valid finishers survive and the last player is eliminated/);
  assert.match(rules("울타리 치기 · 4인 개인전", "먼저 올바른 고리를 제출한 2명은 순서대로 생존을 확정하고, 남은 2명은 탈락합니다."), /first two valid finishers survive and the other two players are eliminated/);
});

test("a new Gomoku round clears every old wallet before new private balances arrive", () => {
  const state = {};
  api.en.applyGomokuEvent(state, "gomoku_setup", {players: two, colors: {P01: "black", P02: "white"}});
  api.en.applyGomokuEvent(state, "gomoku_game", {game: 1, replay: 0, first_selector: "P01"});
  api.en.applyGomokuEvent(state, "gomoku_wallet", {game: 1, round: 1, player: "P01", available: 10, carry: 0});
  api.en.applyGomokuEvent(state, "gomoku_wallet", {game: 1, round: 1, player: "P02", available: 11, carry: 1});
  api.en.applyGomokuEvent(state, "gomoku_round", {game: 1, round: 2, selector: "P02"});
  assert.deepEqual(state.gomokuWallets, {});
  api.en.applyGomokuEvent(state, "gomoku_wallet", {game: 1, round: 2, player: "P01", available: 13, carry: 3});
  assert.equal(state.gomokuWallets.P01.available, 13);
  assert.equal(state.gomokuWallets.P02, undefined);
});
