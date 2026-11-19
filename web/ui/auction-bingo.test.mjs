import assert from "node:assert/strict";
import {mkdtempSync, rmSync} from "node:fs";
import {createRequire} from "node:module";
import {tmpdir} from "node:os";
import {dirname, join} from "node:path";
import {fileURLToPath} from "node:url";
import {after, test} from "node:test";
import {build} from "esbuild";
import {bingoActionText, bingoBoard, coinValue} from "./auction-bingo-state.js";
import {rulesSummary} from "./rule-summaries.js";

const temporary = mkdtempSync(join(tmpdir(), "bingo-replay-test-"));
after(() => rmSync(temporary, {recursive: true, force: true}));
const require = createRequire(import.meta.url);
const renders = {};
for (const language of ["ko", "en"]) {
  const bundle = join(temporary, `${language}.cjs`);
  await build({
    stdin: {contents: `import React from "react"; import {renderToStaticMarkup} from "react-dom/server";
      import {MatchReplay} from "./match-replay.jsx";
      export const render = (replay) => renderToStaticMarkup(<MatchReplay replay={replay} transport={null} />);`,
    resolveDir: dirname(fileURLToPath(import.meta.url)), loader: "jsx"},
    outfile: bundle, bundle: true, platform: "node", format: "cjs", logLevel: "silent",
    define: {STATIC_REPLAY_BUILD: "false", "process.env.NODE_ENV": '"production"', "globalThis.location": JSON.stringify({search: language === "en" ? "?lang=en" : ""})},
    loader: {".css": "empty", ".md": "text", ".woff2": "empty"},
  });
  renders[language] = require(bundle).render;
}
const regular = Array.from({length: 7}, (_, index) => `P${String(index + 1).padStart(2, "0")}`);
const players = [...regular, "G01"];
const coins = {1: 3, 2: 3, 3: 2, 5: 1, 10: 1};
const choices = {P01: "triangle", P02: "triangle", P03: "circle", P04: "circle", P05: "circle", P06: "star", P07: "star", G01: "star"};
const noOp = () => {};
const event = (msg_type, data, visible_to = "all", agent_name = "System") => ({events: [{msg_type, content: typeof data === "string" ? data : JSON.stringify(data), visible_to, agent_name}]});
const setup = event("bingo_setup", {board: bingoBoard, guest: "G01", base_order: players, coins, pieces: Object.fromEntries(players.map((player) => [player, 1])), rounds: 7});
const pending = [setup, event("bingo_round", {round: 1, phase: "shape"}), event("bingo_shapes", {round: 1, choices}),
  event("bingo_round", {round: 1, phase: "bid"}),
  event("action", {phase: "bingo_bid", action: JSON.stringify({coins: {1: 997}, pieces: 2})}, ["P01"], "P01"),
  event("bingo_bank", {round: 1, coins: {10: 991}, pieces: 1, spent: 997}, ["P01"], "P01"),
  event("bingo_result", {round: 1, counts: {triangle: 2, circle: 3, star: 3}, prices: {triangle: null, circle: 2, star: null}, secret: ["triangle", "star"]})];

function replay(steps, view = "public", selected = "") {
  return {id: "bingo-demo", match: {game: "4일차 메인 매치 · 경매 빙고", players, steps, seed: 1}, frame: steps.length,
    view, selected, choosePlayer: noOp, chooseView: noOp, seek: noOp, mode: "paused"};
}
const render = (steps, view = "public", selected = "", language = "ko") => renders[language](replay(steps, view, selected));
const arena = (html) => html.slice(html.indexOf('class="arena"'), html.indexOf('class="match-state"'));

test("integrated arena retains all rooms and eight players including the guest", () => {
  const html = render([setup]);
  for (const player of players) assert.match(arena(html), new RegExp(`data-player="${player}"`));
  for (let room = 1; room <= 4; room++) assert.match(arena(html), new RegExp(`${room}번룸`));
  assert.match(html, /G01 · 게스트/);
  assert.match(html, /bingo-info/);
  assert.match(html, /라운드 기록/);
  assert.match(html, /입찰 기록/);
  assert.match(html, /최종 결과/);
});

test("sealed bids and balances never leak into public or other-player views", () => {
  for (const view of ["public", "P02", "G01"]) {
    const html = render(pending, view, "P01");
    assert.doesNotMatch(html, /997|9910/);
    assert.doesNotMatch(html, /bingo-wallet/);
  }
});

test("the owner and operator may inspect a private bid but not a hidden allocation", () => {
  for (const view of ["operator", "P01"]) {
    const html = render(pending, view, "P01");
    assert.match(html, /997원/);
    assert.match(html, /9910원/);
    assert.match(html, /비공개 코인 현황/);
    assert.doesNotMatch(arena(html), /997|9910/);
    assert.match(html, /낙찰자와 획득 도형은 7라운드 종료 후 공개/);
  }
});

test("both tied maximum-price shapes are secret and an unbid shape is distinct", () => {
  const html = render(pending);
  assert.equal((html.match(/class="bingo-price" data-secret="true"/g) ?? []).length, 2);
  const empty = render([...pending.slice(0, -1), event("bingo_result", {round: 1, prices: {triangle: 3, circle: null, star: null}, secret: ["triangle"]})]);
  assert.equal((empty.match(/class="bingo-price" data-secret="true"/g) ?? []).length, 1);
  assert.match(empty, /입찰 없음/);
});

test("all three equal maximum prices remain secret", () => {
  const html = render([...pending.slice(0, -1), event("bingo_result", {round: 1, prices: {triangle: null, circle: null, star: null}, secret: ["triangle", "circle", "star"]})]);
  assert.equal((html.match(/class="bingo-price" data-secret="true"/g) ?? []).length, 3);
});

test("a new round clears the previous public choices and prices", () => {
  const html = render([...pending, event("bingo_round", {round: 2, phase: "shape"})]);
  const stage = html.slice(html.indexOf('class="bingo-stage"'), html.indexOf('class="context"'));
  assert.match(stage, /2 \/ 7라운드/);
  assert.match(stage, /선택 공개 대기/);
  assert.doesNotMatch(stage, /data-secret="true"/);
});

test("early submissions show public completion badges without revealing chosen shapes", () => {
  const steps = [event("rules", "경매 빙고 · 게임 규칙\n\n6. 자유 제출\n"), setup,
    event("bingo_round", {round: 1, phase: "shape"}),
    event("bingo_discussion_round", {stage: "before_shape", round: 1, rounds: 6, turn: 2}),
    event("action", {phase: "bingo_shape", action: "star"}, ["P01"], "P01"),
    event("bingo_submission", {round: 1, phase: "shape", player: "P01", submitted: ["P01"], total: 8})];
  for (const view of ["public", "P02", "P01", "operator"]) {
    const html = render(steps, view);
    assert.match(html, /1라운드 도형 선택 제출/);
    assert.match(html, /1 \/ 8/);
    assert.match(arena(html), /class="token-badge">제출 완료/);
    assert.match(html, /2 \/ 6턴/);
    assert.equal((html.match(/class="bingo-tickets"><small>선택 공개 대기/g) ?? []).length, 3);
  }
  const english = render(steps, "public", "", "en");
  assert.match(english, /Shape submissions/);
  assert.match(english, /Submitted/);
  assert.match(english, /Turn 2 of 6/);
});

test("submission progress resets for the next phase and round while early bids remain private", () => {
  const steps = [event("rules", "경매 빙고 · 게임 규칙\n\n6. 자유 제출\n"), setup,
    event("bingo_round", {round: 1, phase: "shape"}),
    event("bingo_submission", {round: 1, phase: "shape", player: "G01", submitted: players, total: 8}),
    event("bingo_shapes", {round: 1, choices}), event("bingo_round", {round: 1, phase: "bid"})];
  const nextPhase = render(steps);
  assert.match(nextPhase, /1라운드 입찰 제출/);
  assert.match(nextPhase, /0 \/ 8/);
  assert.doesNotMatch(arena(nextPhase), /token-badge/);
  steps.push(event("bingo_discussion_round", {stage: "before_bid", round: 1, rounds: 6, turn: 1}),
    event("action", {phase: "bingo_bid", action: JSON.stringify({coins: {1: 997}, pieces: 0})}, ["P01"], "P01"),
    event("bingo_submission", {round: 1, phase: "bid", player: "P01", submitted: ["P01"], total: 8}));
  for (const view of ["public", "P02", "G01"]) {
    const html = render(steps, view);
    assert.match(html, /1라운드 입찰 제출/);
    assert.doesNotMatch(html, /997/);
  }
  assert.match(render(steps, "P01"), /997원/);
  assert.match(render(steps, "operator"), /997원/);
  const nextRound = render([...steps, event("bingo_round", {round: 2, phase: "shape"})]);
  assert.match(nextRound, /2라운드 도형 선택 제출/);
  assert.match(nextRound, /0 \/ 8/);
  assert.doesNotMatch(arena(nextRound), /token-badge/);
});

test("English rules preserve archived discussion limits and explain new free submissions", () => {
  const old = rulesSummary("경매 빙고 · 게임 규칙", "old rules");
  assert.match(old, /12 opening discussion turns and up to four turns/);
  assert.doesNotMatch(old, /Each player may submit their own/);
  const current = rulesSummary("경매 빙고 · 게임 규칙", "rules\n\n6. 자유 제출\n");
  assert.match(current, /10 opening discussion turns and up to six turns/);
  assert.match(current, /submissions are final and cannot be revised/);
  assert.match(current, /Submitted players may continue talking/);
  assert.match(current, /Shape choices are revealed only after everyone submits/);
  assert.doesNotMatch(current, /12 opening discussion turns/);
});

test("final reveal shows cards and prices while sealed bids stay private", () => {
  const results = Object.fromEntries(players.map((player) => [player, {shapes: {triangle: 3, circle: 4, star: 2}, board: bingoBoard, lines: 8, filled: 9, remaining_value: 10, coins: {10: 1}, pieces: 1}]));
  const reveal = event("bingo_reveal", {ranking: regular, all_ranking: ["G01", ...regular], players: results, guest: "G01",
    rounds: [{round: 1, choices, counts: {triangle: 2, circle: 3, star: 3}, prices: {triangle: 777, circle: 2, star: 777}, secret: ["triangle", "star"]}]});
  const result = event("match_result", {ranking: regular, living: regular.slice(0, 3), prison: regular.slice(3, -1), eliminated: ["P07"],
    pieces: Object.fromEntries(players.map((player) => [player, 5])), guest_result: {player: "G01", rank: 1, first: true, full_board: true, prize_won: 20_000_000}});
  const html = render([...pending, reveal, result], "public", "G01");
  assert.match(html, /data-filled="true"/);
  assert.match(html, /생존 판정 제외/);
  assert.match(html, /상금 20,000,000원/);
  assert.match(html, /피스 5개/);
  assert.match(html, /매치 종료/);
  assert.match(html, /777원/);
  assert.match(html, /최종 공개 낙찰가/);
  assert.doesNotMatch(html, /997원/);
  assert.doesNotMatch(render([...pending, reveal, result], "P02", "P01"), /997원/);
  assert.match(render([...pending, reveal, result], "P01", "P01"), /997원/);
  assert.match(render([...pending, reveal, result], "operator", "P01"), /997원/);
  assert.doesNotMatch(arena(html).match(/<button[^>]*data-player="G01"[^>]*>/)[0], /data-status="탈락"/);
});

test("coin exchange is not counted twice in displayed bid totals", () => {
  assert.equal(coinValue(coins), 30);
  assert.match(bingoActionText("bingo_bid", JSON.stringify({coins: {1: 2, 5: 1}, pieces: 2})), /^7원 입찰/);
});

test("English UI includes translated game, phases, guest and rule summary", () => {
  const html = render(pending, "public", "", "en");
  assert.match(html, /Auction Bingo/);
  assert.match(html, /Day 4 Main Match/);
  assert.match(html, /Guest/);
  assert.match(html, /Winning prices revealed/);
  assert.match(html, /Remaining coin value/);
  const summary = rulesSummary("경매 빙고 · 본선 7명과 게스트 G01 · 7라운드", "");
  assert.match(summary, /every shape tied for the round’s highest price/);
  assert.match(summary, /total value of remaining coins/);
});
