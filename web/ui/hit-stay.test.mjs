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
const directory = mkdtempSync(join(tmpdir(), "hit-stay-ui-"));
after(() => rmSync(directory, {recursive: true, force: true}));
const api = {};
for (const language of ["ko", "en"]) {
  const bundle = join(directory, `${language}.cjs`);
  await build({stdin: {contents: `import {MatchReplay} from './match-replay.jsx'; import React from 'react'; import {renderToStaticMarkup} from 'react-dom/server'; import {HitStayScene, HitStayStage, HitStayInformation} from './hit-stay.jsx'; export {applyHitEvent, hitEventText, hitActionText} from './hit-stay.jsx'; export const renderReplay = replay => renderToStaticMarkup(<MatchReplay replay={replay} transport={null}/>); export const render = (state, players, selected='') => renderToStaticMarkup(<><HitStayScene state={state} players={players} selected={selected} onChoose={()=>{}}/><HitStayStage state={state} players={players}/><HitStayInformation state={state} replay={{seek:()=>{}}}/></>);`, loader: "jsx", resolveDir: here}, outfile: bundle, bundle: true, platform: "node", format: "cjs", logLevel: "silent", loader: {".css": "empty", ".woff2": "empty", ".md": "text"}, define: {STATIC_REPLAY_BUILD: "false", "process.env.NODE_ENV": '"production"', "globalThis.location": JSON.stringify({search: language === "en" ? "?lang=en" : ""})}});
  api[language] = require(bundle);
}
const players = ["P01", "P02", "P03", "P04", "P05"];
const chips = Object.fromEntries(players.map((player) => [player, 30]));
const contributions = Object.fromEntries(players.map((player) => [player, 1]));
const hands = {P01: [7, 6, -1], P02: [5, 4, 1], P03: [3, 2, 1], P04: [2, 2, 1], P05: [1, 1, -1]};
const public_cards = {P01: [-1], P02: [1], P03: [1], P04: [1], P05: [-1]};
const context = {round: 1, tiebreak: 0, first: "P01", players, limit: 10};
const setup = {version: 1, players, seats: players, deck_counts: {"7": 1, "6": 2, "5": 3, "4": 4, "3": 5, "2": 6, "1": 7, "-1": 7}, initial_chips: chips, pieces_spent: {P01: 2}, cap_policy: "smallest_stack", tie_policy: "replay", opening_turns: 10};
const round = {...context, ante: 1, scheduled_ante: 1, pot: 5, chips, contributions, deck_remaining: 35};
const snapshot = {public_cards, hand_counts: Object.fromEntries(players.map((player) => [player, 3])), folded: [], stayed: [], pot: 5, chips, contributions, deck_remaining: 20};
const reveal = {...context, cards: Object.fromEntries(players.map((player) => [player, public_cards[player][0]])), hidden_counts: Object.fromEntries(players.map((player) => [player, 2])), deck_remaining: 20};
const opening = [["hit_setup", setup], ["hit_round", round], ...players.map((player) => ["hit_hand", {player, cards: hands[player]}]), ["hit_reveal", reveal]];

for (const language of ["ko", "en"]) {
  test(`${language}: full replay filters private hands and notes before rendering`, () => {
    const steps = opening.map(([msg_type, data]) => ({events: [{msg_type, content: JSON.stringify(data),
      visible_to: msg_type === "hit_hand" ? [data.player] : "all", agent_name: "System"}]}));
    steps.push({events: [{msg_type: "decision_note", agent_name: "P01", visible_to: ["P01"],
      content: JSON.stringify({phase: "hit_draw", note: "PRIVATE-HIT-PLAN"})}]});
    const render = (view) => api[language].renderReplay({id: "hit-smoke", match: {game: "6일차 메인 매치 · HIT, STAY", players, steps},
      frame: steps.length, view, selected: "", mode: "paused", seek: () => {}, chooseView: () => {}, choosePlayer: () => {}});
    for (const view of ["public", "P02"]) {
      const html = render(view);
      assert.deepEqual(valuesFor(html, "P01"), [-1]);
      assert.doesNotMatch(html, /PRIVATE-HIT-PLAN/);
      assert.match(html, language === "ko" ? /HIT, STAY 결과와 기록/ : /HIT, STAY results and records/);
    }
    assert.deepEqual(valuesFor(render("P01"), "P01"), [7, 6, -1]);
    assert.match(render("P01"), /PRIVATE-HIT-PLAN/);
    assert.match(render("operator"), /PRIVATE-HIT-PLAN/);
  });
}

function stateAt(events, language = "ko", perspective = "public") {
  const state = {feed: [], hitPerspective: perspective};
  for (const [index, [type, data]] of events.entries()) {
    const event = {step: index + 1, msg_type: type, data, text: api[language].hitEventText(type, data)};
    state.feed.push(event);
    api[language].applyHitEvent(state, type, data, event);
  }
  return state;
}
const valuesFor = (html, player) => [...html.matchAll(new RegExp(`data-card-owner="${player}" data-card-value="([^"]+)"`, "g"))].map((match) => Number(match[1]));
for (const language of ["ko", "en"]) {
  test(`${language}: public sees one initial card and two backs per seat`, () => {
    const html = api[language].render(stateAt(opening, language), players, "P01");
    assert.equal((html.match(/data-player=/g) ?? []).length, 5);
    assert.equal((html.match(/data-card-hidden="true"/g) ?? []).length, 10);
    assert.deepEqual(valuesFor(html, "P01"), [-1]);
    assert.deepEqual(valuesFor(html, "P02"), [1]);
    assert.match(html, language === "ko" ? /비공개 카드 2장은 뒷면/ : /TWO PRIVATE CARDS STAY FACE DOWN/);
    assert.doesNotMatch(html, /7,6,-1|5,4,1/);
  });
  test(`${language}: own and operator views reveal only authorized private cards`, () => {
    const own = api[language].render(stateAt(opening, language, "P01"), players, "P02");
    assert.deepEqual(valuesFor(own, "P01"), [7, 6, -1]);
    assert.deepEqual(valuesFor(own, "P02"), [1]);
    assert.equal((own.match(/data-card-hidden="true"/g) ?? []).length, 8);
    const operator = api[language].render(stateAt(opening, language, "operator"), players);
    assert.deepEqual(valuesFor(operator, "P02"), [5, 4, 1]);
    assert.equal((operator.match(/data-card-hidden="true"/g) ?? []).length, 0);
  });
  test(`${language}: public HIT cards append without exposing either hidden card`, () => {
    const hit = {...context, ...snapshot, player: "P01", type: "HIT", value: 2, count: 4, public_cards: {...public_cards, P01: [-1, 2]}, hand_counts: {...snapshot.hand_counts, P01: 4}, deck_remaining: 19};
    const html = api[language].render(stateAt([...opening, ["hit_card", hit]], language), players);
    assert.deepEqual(valuesFor(html, "P01"), [-1, 2]);
    assert.equal((html.match(/data-card-hidden="true"/g) ?? []).length, 10);
    const own = api[language].render(stateAt([...opening, ["hit_card", hit]], language, "P01"), players);
    assert.deepEqual(valuesFor(own, "P01"), [7, 6, -1, 2]);
    assert.match(html, /HIT 2/);
    assert.deepEqual(valuesFor(api[language].render(stateAt(opening, language), players), "P01"), [-1]);
  });
  test(`${language}: showdown reveals nonfolded hands and keeps folded hands private`, () => {
    const fold = {...context, ...snapshot, phase: "bet1", player: "P01", type: "fold", paid: 0, total: 1, folded: ["P01"]};
    const showdown = {...context, hands: {P02: hands.P02, P03: hands.P03, P04: hands.P04, P05: hands.P05}, sums: {P02: 10, P03: 6, P04: 5, P05: 1}, counts: {P02: 3, P03: 3, P04: 3, P05: 3}, winners: ["P02"], payouts: {P02: 5}, pot: 5, remaining_pot: 0, chips: {...chips, P02: 35}, reason: "best_hand"};
    const state = stateAt([...opening, ["hit_bet", fold], ["hit_showdown", showdown]], language);
    const html = api[language].render(state, players);
    assert.deepEqual(valuesFor(html, "P01"), [-1]);
    assert.deepEqual(valuesFor(html, "P02"), [5, 4, 1]);
    assert.equal((html.match(/data-card-hidden="true"/g) ?? []).length, 2);
    assert.match(html, /hit-folded/);
    assert.match(html, /hit-winner/);
    assert.equal(state.hitGame.pot, 0);
    assert.equal(state.hitResults[0].pot, 5);
    assert.match(html, language === "ko" ? /공개된 손패 비교/ : /Revealed hands/);
    const malformed = {...state, hitShowdown: {...state.hitShowdown, hands: {...state.hitShowdown.hands, P01: hands.P01}}};
    assert.deepEqual(valuesFor(api[language].render(malformed, players), "P01"), [-1]);
  });
  test(`${language}: betting caps, raises and actions use stable readable labels`, () => {
    const turn = {...context, ...snapshot, phase: "bet1", player: "P02", current_total: 4, cap: 12};
    const html = api[language].render(stateAt([...opening, ["hit_turn", turn]], language), players);
    assert.match(html, /hit-acting/);
    assert.match(html, language === "ko" ? /최대 누적 베팅/ : /Maximum total bet/);
    assert.match(api[language].hitActionText("hit_bet1", '{"type":"raise","total":12}'), language === "ko" ? /누적 12칩.*기본 베팅 포함/ : /12 chips total.*including ante/);
    assert.equal(api[language].hitActionText("hit_bet2", '{"type":"fold"}'), language === "ko" ? "포기" : "Fold");
    assert.equal(api[language].hitActionText("hit_draw", "HIT"), "HIT");
    assert.equal(api[language].hitActionText("hit_interest", "public"), language === "ko" ? "공공의 이익" : "Public interest");
    assert.equal(api[language].hitActionText("hit_reveal", "0"), language === "ko" ? "배부 순서 1번 카드 공개" : "Reveal dealt card 1");
  });
  test(`${language}: four-player tables and final standings follow the event order`, () => {
    const four = players.slice(0, 4);
    const state = stateAt([["hit_setup", {...setup, players: four, seats: ["P03", "P01", "P04", "P02"]}]], language);
    assert.equal((api[language].render(state, four).match(/data-player=/g) ?? []).length, 4);
    api[language].applyHitEvent(state, "hit_final", {ranking: ["P03", "P02", "P01", "P04"], living: ["P03"], prison: ["P02", "P01"], eliminated: ["P04"], chips: {P03: 99, P02: 0, P01: 0, P04: 0}});
    const html = api[language].render(state, four);
    assert.match(html, /<th scope="row">1<\/th><td>P03<\/td>/);
    assert.match(html, language === "ko" ? /결승 진출/ : /Finalist/);
    assert.match(html, language === "ko" ? /감옥 매치/ : /Prison match/);
    assert.match(html, language === "ko" ? /탈락/ : /Eliminated/);
  });
}
test("new rounds clear private hands, public cards and previous showdown state", () => {
  const state = stateAt(opening, "en", "operator");
  api.en.applyHitEvent(state, "hit_round", {...round, round: 2, first: "P02"});
  assert.deepEqual(state.hitHands, {});
  assert.deepEqual(state.hitPublicCards, {});
  assert.deepEqual(state.hitHiddenCounts, {});
  assert.equal(state.hitShowdown, null);
  assert.equal((api.en.render(state, players).match(/data-card-value=/g) ?? []).length, 0);
});
test("snapshot reducers clone input arrays and private-hand event text never includes values", () => {
  const state = stateAt(opening);
  state.hitHands.P01.pop();
  state.hitPublicCards.P02.push(7);
  assert.deepEqual(hands.P01, [7, 6, -1]);
  assert.deepEqual(public_cards.P02, [1]);
  for (const language of ["ko", "en"]) assert.doesNotMatch(api[language].hitEventText("hit_hand", {player: "P01", cards: [7, 6, -1]}), /7|6|-1/);
});
test("large public HIT hands wrap within their fixed seat instead of dropping cards", () => {
  const state = stateAt(opening);
  state.hitPublicCards.P01 = Array.from({length: 24}, (_, index) => index % 7 + 1);
  state.hitGame.hand_counts.P01 = 26;
  const html = api.en.render(state, players);
  assert.equal(valuesFor(html, "P01").length, 24);
  assert.doesNotMatch(html, /NaN|undefined|Infinity/);
});
