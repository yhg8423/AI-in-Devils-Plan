import assert from "node:assert/strict";
import {mkdtempSync, rmSync} from "node:fs";
import {createRequire} from "node:module";
import {tmpdir} from "node:os";
import {dirname, join} from "node:path";
import {fileURLToPath} from "node:url";
import {after, test} from "node:test";
import {build} from "esbuild";

const directory = mkdtempSync(join(tmpdir(), "symmetry-ui-"));
after(() => rmSync(directory, {recursive: true, force: true}));
const require = createRequire(import.meta.url), api = {};
for (const language of ["ko", "en"]) {
  const bundle = join(directory, `${language}.cjs`);
  await build({stdin: {contents: `import React from 'react'; import {renderToStaticMarkup} from 'react-dom/server'; import {MatchReplay} from './match-replay.jsx'; export {applySymmetryEvent,symmetryBoardFor,symmetryPlayerStatus,symmetryActionText} from './symmetry.jsx'; export {rulesSummary} from './rule-summaries.js'; export const render = replay => renderToStaticMarkup(<MatchReplay replay={replay} transport={null}/>);`, loader: "jsx", resolveDir: dirname(fileURLToPath(import.meta.url))}, outfile: bundle, bundle: true, platform: "node", format: "cjs", logLevel: "silent", loader: {".css": "empty", ".woff2": "empty", ".md": "text"}, define: {STATIC_REPLAY_BUILD: "false", "process.env.NODE_ENV": '"production"', "globalThis.location": JSON.stringify({search: language === "en" ? "?lang=en" : ""})}});
  api[language] = require(bundle);
}
const colors = ["blue", "red", "green"], noop = () => {};
const image = (id) => ({id, width: 960, height: 640, image: `data:image/png;base64,${Buffer.from(id).toString("base64")}`});
const pieces = {blue: ["B1", "B2"], red: ["R1", "R2", "R3"], green: ["G1", "G2", "G3"]};
const event = (msg_type, data, visible_to = "all", agent_name = "System") => ({events: [{msg_type, content: typeof data === "string" ? data : JSON.stringify(data), visible_to, agent_name}]});
const setupData = (players) => ({version: 2, mode: "polygons", players, priority: [...players].reverse(), survivors: players.length - 1});
const puzzlesData = {puzzles: colors.map((color) => ({id: color, label: {blue: "파랑", red: "빨강", green: "초록"}[color], piece_ids: pieces[color], board: image(`PUBLIC-${color}`)}))};
const detailImage = (color) => ({...image(`DETAILS-${color}`), width: 2048, height: 1792});
const detailedPuzzles = {puzzles: puzzlesData.puzzles.map((puzzle) => ({...puzzle, details: detailImage(puzzle.id)}))};
const toolsData = {version: 3, thinking_passes: 3, puzzles: colors.map((id) => ({id, details: detailImage(id)}))};
const overviewImage = (color) => ({...image(`OVERVIEW-${color}`), width: 1440, height: 1100});
const focusPuzzles = {puzzles: detailedPuzzles.puzzles.map((puzzle) => ({...puzzle, overview: overviewImage(puzzle.id)}))};
const focusTools = {...toolsData, version: 4, focus_mode: "one_color", focus_start_window: 2, focus_color: "blue",
  puzzles: colors.map((id) => ({id, details: detailImage(id), overview: overviewImage(id)}))};
const tutorialData = {version: 1, board: {...image("PUBLIC-TUTORIAL"), width: 1800, height: 1150}, explanations: {
  ko: "EX1과 EX2의 변 일부를 붙이고 EX3을 더해 대칭 도형을 만듭니다.",
  en: "Join part of the edges of EX1 and EX2, then add EX3 to form a symmetric shape.",
}};
const puzzles = event("sym_puzzles", puzzlesData);
const window = (players, number = 1) => event("sym_window", {window: number, active: players});
const workingData = (player, full = false) => ({player, window: full ? 2 : 1,
  placements: Object.fromEntries(colors.map((color, index) => [color, pieces[color].slice(0, full ? pieces[color].length : 2 - index).map((piece, i) => ({piece, x: -2.5 + i * 1.25, y: index + 0.375, rotation: [22.5, 137.25, 315.125][i]}))])),
  boards: Object.fromEntries(colors.map((color) => [color, image(`${player}-${full ? "FINISHED" : "PRIVATE"}-${color}`)])), submitted: full});
const drawing = (player, full = false) => event("sym_board", workingData(player, full), [player], player);
const workbenchData = (player, full = false) => ({...workingData(player, full),
  axes: {blue: 20.25, red: null, green: 137.5},
  workbenches: Object.fromEntries(colors.map((color) => [color, {...image(`${player}-WORKBENCH-${color}`), width: 1440, height: 1100}]))});
const buzz = (player, attempt = 1) => event("sym_buzz", {player, window: 2, attempt, elapsed_ns: 16_000_000_000});
const verdict = (player, correct, attempt = 1) => event("sym_verdict", {player, window: 2, attempt, elapsed_ns: 16_000_000_000, correct, reason: correct ? null : "not_symmetric"});
const finishData = (player, rank) => ({player, window: 2, attempt: 1, elapsed_ns: 16_000_000_000, rank});
const finish = (player, rank) => event("sym_finish", finishData(player, rank));
const revealData = (players) => ({boards: Object.fromEntries(players.map((player) => [player, workingData(player, true)])), axes: Object.fromEntries(players.map((player) => [player, {blue: "vertical", red: "horizontal", green: "diagonal"}]))});
const privateNote = (player) => event("decision_note", {phase: "symmetry_arrange", note: `PRIVATE-STRATEGY-${player}`}, [player], player);
function race(players) {
  const start = [event("sym_setup", setupData(players)), puzzles, window(players), ...players.map((player) => drawing(player)), ...players.map(privateNote), window(players, 2), ...players.map((player) => drawing(player, true))];
  const done = players.slice(0, -1).flatMap((player, i) => [buzz(player), verdict(player, true), finish(player, i + 1)]);
  const final = event("match_result", {ranking: players, ranking_groups: players.map((player) => [player]), survivors: players.slice(0, -1), eliminated: players.slice(-1), scores: Object.fromEntries(players.map((player) => [player, 3])), finish_turns: Object.fromEntries(players.slice(0, -1).map((player) => [player, 2])), pieces: Object.fromEntries(players.map((player) => [player, 0]))});
  return {start, done, reveal: event("sym_reveal", revealData(players)), final, steps: [...start, ...done, event("sym_reveal", revealData(players)), final]};
}
function render(players, steps, {language = "ko", view = "public", selected = "", frame = steps.length} = {}) {
  return api[language].render({id: "symmetry-demo", match: {game: "유배지 매치 5 · 대칭 퍼즐", players, steps}, frame, view, selected, choosePlayer: noop, chooseView: noop, seek: noop, mode: "paused"});
}

for (const language of ["ko", "en"]) {
  test(`${language}: recorded survivor slots preserve historical outcomes while new four-player races save two`, () => {
    const players = ["P01", "P02", "P03", "P04"];
    for (const slots of [2, 3]) {
      const prefix = [event("sym_setup", {...setupData(players), survivors: slots}), puzzles, window(players)];
      const html = render(players, prefix, {language});
      assert.equal((html.match(/data-filled="false"/g) ?? []).length, slots);
      assert.match(html, language === "ko" ? new RegExp(`먼저 세 색을 모두 완성한 ${slots}명이 생존하고 나머지 ${4 - slots}명`) : new RegExp(`first ${slots} players to finish all three colors survive; the other ${4 - slots}`));
      const ended = render(players, [...prefix, ...players.slice(0, slots).map((p, i) => finish(p, i + 1)),
        event("sym_reveal", revealData(players)), event("match_result", {ranking: players, survivors: players.slice(0, slots), eliminated: players.slice(slots)})], {language});
      assert.equal((ended.match(/data-status="safe"/g) ?? []).length, slots);
      assert.equal((ended.match(/data-status="eliminated"/g) ?? []).length, 4 - slots);
      assert.match(ended, /data-board-id="P01-FINISHED-blue"/);
    }
  });
  test(`${language}: v5 workbench tab follows private ownership while the arena retains the original board`, () => {
    const players = ["P01", "P02", "P03"];
    const prefix = [event("sym_setup", {...setupData(players), version: 5, focus_mode: "one_color", focus_start_window: 1}),
      event("sym_puzzles", focusPuzzles), event("sym_window", {window: 1, active: players, focus_color: "blue"})];
    const steps = [...prefix, event("sym_board", workbenchData("P01"), ["P01"], "P01"), event("sym_board", workbenchData("P02"), ["P02"], "P02")];
    const publicView = render(players, steps, {language, selected: "P02"});
    assert.doesNotMatch(publicView, /WORKBENCH-|Silhouette &amp; mirror|윤곽·반사축|P0\d-PRIVATE-/);
    assert.match(publicView, /data-board-id="PUBLIC-blue"/);
    const own = render(players, steps, {language, view: "P01", selected: "P02"});
    assert.match(own, language === "ko" ? /윤곽·반사축/ : /Silhouette &amp; mirror/);
    assert.match(own, /role="tab"[^>]*id="[^"]+-workbench"|id="[^"]+-workbench"[^>]*role="tab"/);
    assert.match(own, language === "ko" ? /참가자가 고른 축/ : /their chosen axis/);
    assert.match(own, language === "ko" ? /정답 판정은 아니며 버저는 세 색 전체/ : /not a correctness verdict; the buzzer checks all three colors/);
    assert.match(own, /data-board-id="P01-PRIVATE-blue"/);
    assert.match(own, /data-image-kind="overview" data-image-id="OVERVIEW-blue"/);
    assert.doesNotMatch(own, /P02-PRIVATE-|P02-WORKBENCH-|data-axis=/);
    assert.doesNotMatch(render(players, steps, {language, view: "P01", frame: prefix.length}), /윤곽·반사축|Silhouette &amp; mirror/);
    const operator = render(players, steps, {language, view: "operator", selected: "P02"});
    assert.match(operator, /data-board-id="P02-PRIVATE-blue"/);
    assert.match(operator, language === "ko" ? /윤곽·반사축/ : /Silhouette &amp; mirror/);
  });
  test(`${language}: final reveal makes workbench tabs available only after the actual reveal event`, () => {
    const players = ["P01", "P02", "P03"];
    const working = Object.fromEntries(players.map((player) => [player, workbenchData(player, true)]));
    const prefix = [event("sym_setup", {...setupData(players), version: 5}), event("sym_puzzles", focusPuzzles),
      window(players), ...players.map((player) => event("sym_board", working[player], [player], player)),
      finish("P01", 1), finish("P02", 2)];
    assert.doesNotMatch(render(players, prefix, {language, selected: "P02"}), /윤곽·반사축|Silhouette &amp; mirror/);
    const revealed = render(players, [...prefix, event("sym_reveal", {boards: working})], {language, selected: "P02"});
    assert.match(revealed, /data-board-id="P02-FINISHED-blue"/);
    assert.match(revealed, language === "ko" ? /윤곽·반사축/ : /Silhouette &amp; mirror/);
  });
  test(`${language}: v4 opens the common-scale overview while keeping individual details and private workspace ownership`, () => {
    const players = ["P01", "P02", "P03"];
    const steps = [event("sym_setup", {...setupData(players), version: 4, focus_mode: "one_color", focus_start_window: 1}),
      event("sym_puzzles", focusPuzzles), event("sym_window", {window: 1, active: players, focus_color: "red"}), drawing("P01"), drawing("P02")];
    const html = render(players, steps, {language, selected: "P02"});
    assert.match(html, /data-image-kind="overview" data-image-id="OVERVIEW-blue"/);
    assert.match(html, language === "ko" ? />공통 배율</ : />Common scale</);
    assert.match(html, language === "ko" ? />개별 확대</ : />Individual detail</);
    assert.match(html, language === "ko" ? />작업판</ : />Workspace</);
    assert.match(html, language === "ko" ? /같은 축척을 적용해 상대 크기를 비교/ : /one scale for every piece, so relative sizes can be compared accurately/);
    assert.match(html, /class="sym-focus" data-focus-color="red"/);
    assert.match(html, language === "ko" ? /모델의 자체 평가/ : /the model&#x27;s own judgments/);
    assert.match(html, language === "ko" ? /집중 색을 바꾸는 것은 정답·오답 판정이 아닙니다/ : /changing focus is not a correct\/incorrect verdict/);
    assert.match(html, language === "ko" ? /버저는 세 색 전체를 함께 판정/ : /buzzer still judges all three colors together/);
    assert.match(html, /arrange_color/);
    assert.doesNotMatch(html, /P0\d-PRIVATE-|data-axis=|data-progress-correct=/);
    const own = render(players, steps, {language, view: "P01", selected: "P02"});
    assert.match(own, /data-board-id="P01-PRIVATE-blue"/);
    assert.match(own, /data-image-id="OVERVIEW-blue"/);
    assert.doesNotMatch(own, /P02-PRIVATE-/);
  });
  test(`${language}: v4 migration preserves existing boards and starts focus only at the observed window`, () => {
    const players = ["P01", "P02", "P03"];
    const steps = [event("sym_setup", {...setupData(players), version: 3}), event("sym_puzzles", detailedPuzzles),
      event("sym_window", {window: 1, active: players, focus_color: "green"}), drawing("P01"),
      event("sym_tools", focusTools), event("sym_window", {window: 2, active: players, focus_color: "green"})];
    assert.match(render(players, steps, {language, frame: 4}), /data-image-kind="details"/);
    const migrated = render(players, steps, {language, frame: 5});
    assert.match(migrated, /data-image-kind="overview"/);
    assert.doesNotMatch(migrated, /class="sym-focus"/);
    assert.match(render(players, steps, {language}), /class="sym-focus" data-focus-color="green"/);
    assert.match(render(players, steps, {language, view: "P01"}), /data-board-id="P01-PRIVATE-blue"/);
  });
  test(`${language}: the explicit migration color applies to its exact start window and later window events replace it`, () => {
    const players = ["P01", "P02", "P03"];
    const prefix = [event("sym_setup", {...setupData(players), version: 3}), event("sym_puzzles", detailedPuzzles),
      window(players, 2), drawing("P01"), event("sym_tools", focusTools)];
    const first = render(players, prefix, {language});
    assert.match(first, /class="sym-focus" data-focus-color="blue"/);
    assert.match(render(players, prefix, {language, view: "P01"}), /data-board-id="P01-PRIVATE-blue"/);
    assert.doesNotMatch(first, /P01-PRIVATE-/);
    const later = render(players, [...prefix, event("sym_window", {window: 3, active: players, focus_color: "red"})], {language});
    assert.match(later, /class="sym-focus" data-focus-color="red"/);
    assert.doesNotMatch(later, /class="sym-focus" data-focus-color="blue"/);
    const past = [event("sym_setup", {...setupData(players), version: 3}), event("sym_puzzles", detailedPuzzles),
      event("sym_window", {window: 3, active: players, focus_color: "green"}), event("sym_tools", focusTools)];
    assert.match(render(players, past, {language}), /class="sym-focus" data-focus-color="green"/);
  });
  test(`${language}: focus badges require known mode, version, window and color instead of inferred correctness`, () => {
    const players = ["P01", "P02", "P03"];
    for (const config of [{version: 3, focus_mode: "one_color", color: "blue"}, {version: 4, color: "blue"},
      {version: 4, focus_mode: "unknown", color: "blue"}, {version: 4, focus_mode: "one_color", color: "violet"}]) {
      const steps = [event("sym_setup", {...setupData(players), ...config}), event("sym_puzzles", focusPuzzles),
        event("sym_window", {window: 1, active: players, focus_color: config.color})];
      assert.doesNotMatch(render(players, steps, {language}), /class="sym-focus"/);
    }
  });
  test(`${language}: the public practice example appears only after its event and exposes no current private assembly`, () => {
    const players = ["P01", "P02", "P03"];
    const steps = [event("sym_setup", {...setupData(players), version: 3}), event("sym_puzzles", detailedPuzzles),
      window(players), drawing("P01"), drawing("P02"), event("sym_tutorial", tutorialData)];
    const before = render(players, steps, {language, frame: steps.length - 1});
    assert.doesNotMatch(before, /PUBLIC-TUTORIAL|sym-tutorial-preview|data-image-kind="tutorial"/);
    const publicView = render(players, steps, {language, selected: "P02"});
    assert.match(publicView, /data-tutorial-image-id="PUBLIC-TUTORIAL"/);
    assert.match(publicView, /width="1800" height="1150"[^>]+data-image-kind="tutorial" data-image-id="PUBLIC-TUTORIAL"/);
    assert.match(publicView, language === "ko" ? /별도의 연습용 조각/ : /a separate practice set/);
    assert.match(publicView, language === "ko" ? /EX1과 EX2의 변 일부를 붙이고 EX3/ : /Join part of the edges of EX1 and EX2, then add EX3/);
    assert.doesNotMatch(publicView, language === "ko" ? /Join part of the edges of EX1/ : /EX1과 EX2의 변 일부/);
    assert.match(publicView, language === "ko" ? /연습 예시 확대/ : /Enlarge worked example/);
    assert.match(publicView, language === "ko" ? /원본 크기 · 100%/ : /Original size · 100%/);
    assert.match(render(players, steps, {language}), language === "ko" ? /별도 연습 조각의 조립 예시 공개/ : /Worked example using a separate practice set revealed/);
    assert.match(publicView, /data-board-id="PUBLIC-blue"/);
    assert.doesNotMatch(publicView, /P0\d-PRIVATE-|PRIVATE-STRATEGY|data-axis=/);
    for (const player of ["P01", "P02"]) assert.equal(publicView.includes(image(`${player}-PRIVATE-blue`).image), false);
    const ownView = render(players, steps, {language, view: "P01", selected: "P02"});
    assert.match(ownView, /data-tutorial-image-id="PUBLIC-TUTORIAL"/);
    assert.match(ownView, /data-board-id="P01-PRIVATE-blue"/);
    assert.doesNotMatch(ownView, /P02-PRIVATE-/);
  });
  test(`${language}: enlarged public piece details preserve aspect and privacy while own workspace remains available`, () => {
    const players = ["P01", "P02", "P03"];
    const steps = [event("sym_setup", {...setupData(players), version: 3}), event("sym_puzzles", detailedPuzzles), window(players), ...players.map((player) => drawing(player)), ...players.map(privateNote)];
    const publicView = render(players, steps, {language, selected: "P02"});
    assert.match(publicView, /data-board-id="PUBLIC-blue"/);
    assert.match(publicView, /width="2048" height="1792"[^>]+data-image-kind="details" data-image-id="DETAILS-blue"/);
    assert.match(publicView, language === "ko" ? />조각 세부</ : />Piece details</);
    assert.match(publicView, language === "ko" ? />작업판</ : />Workspace</);
    assert.match(publicView, language === "ko" ? /원본 크기 · 100%/ : /Original size · 100%/);
    assert.match(publicView, language === "ko" ? /가로·세로로 스크롤/ : /Scroll horizontally and vertically/);
    assert.match(publicView, language === "ko" ? /길이가 다른 변이나 변의 일부끼리/ : /Edges may have different lengths and touch along only part of an edge/);
    assert.match(publicView, language === "ko" ? /꼭짓점만 닿으면 연결로 인정하지 않습니다/ : /Point-only contact does not connect pieces/);
    assert.match(publicView, language === "ko" ? /자신의 메모와 최근 실패 기록/ : /Your own memo and recent failed attempts/);
    assert.match(publicView, language === "ko" ? /최대 3번/ : /up to 3 private strategy passes/);
    assert.match(publicView, language === "ko" ? /그 전에 배치를 확정/ : /finalize the arrangement earlier/);
    assert.match(publicView, language === "ko" ? /색별 정답 여부나 정답 대칭축은 알려주지 않습니다/ : /without color-specific feedback or solution axes/);
    assert.doesNotMatch(publicView, /P0\d-PRIVATE-|PRIVATE-STRATEGY|data-axis=/);
    for (const player of players) assert.equal(publicView.includes(image(`${player}-PRIVATE-blue`).image), false);
    const ownView = render(players, steps, {language, view: "P01", selected: "P02"});
    assert.match(ownView, /data-board-id="P01-PRIVATE-blue"/);
    assert.match(ownView, /data-image-id="DETAILS-blue"/);
    assert.match(render(players, steps, {language, view: "P01", selected: "P01"}), /PRIVATE-STRATEGY-P01/);
    assert.doesNotMatch(ownView, /P02-PRIVATE-|PRIVATE-STRATEGY-P02/);
    assert.equal(ownView.includes(image("P02-PRIVATE-blue").image), false);
  });
  test(`${language}: old v2 records enlarge their workspace without a missing details tab or new review claims`, () => {
    const players = ["P01", "P02", "P03"];
    const html = render(players, [event("sym_setup", setupData(players)), puzzles, window(players)], {language});
    assert.match(html, /data-image-kind="workspace" data-image-id="PUBLIC-blue"/);
    assert.doesNotMatch(html, /DETAILS-|data-image-kind="details"/);
    assert.doesNotMatch(html, language === "ko" ? /확대 이미지 종류|최대 3번/ : /Enlarged image type|up to 3 private strategy passes/);
  });
  test(`${language}: sym_tools adds public detail images to a resumed v2 match without exposing private work`, () => {
    const players = ["P01", "P02", "P03"];
    const steps = [event("sym_setup", setupData(players)), puzzles, window(players), drawing("P01"), event("sym_tools", toolsData)];
    const before = render(players, steps, {language, frame: steps.length - 1});
    assert.doesNotMatch(before, /DETAILS-|data-image-kind="details"/);
    const after = render(players, steps, {language});
    assert.match(after, /data-image-id="DETAILS-blue"/);
    assert.match(after, language === "ko" ? /조각 세부 이미지와 비공개 전략 검토 적용/ : /Piece detail images and private strategy reviews enabled/);
    assert.match(after, language === "ko" ? /최대 3번/ : /up to 3 private strategy passes/);
    assert.doesNotMatch(after, /P01-PRIVATE-|PRIVATE-STRATEGY|data-axis=/);
    assert.match(render(players, steps, {language, view: "P01"}), /data-board-id="P01-PRIVATE-blue"/);
  });
  for (const count of [3, 4]) {
    const players = Array.from({length: count}, (_, i) => `P0${i + 1}`);
    test(`${language}, ${count} players: three color tabs, native enlargement and N−1 finish places share the existing corner platforms`, () => {
      const {steps} = race(players);
      const html = render(players, steps, {language, frame: 3});
      assert.match(html, /data-board-id="PUBLIC-blue"/);
      assert.match(html, /data-board-owner="public"/);
      assert.equal((html.match(/class="exile-lift"/g) ?? []).length, count);
      assert.equal((html.match(/data-filled="false"/g) ?? []).length, count - 1);
      for (const color of colors) {
        assert.match(html, new RegExp(`id="sym-color-${color}"`));
        assert.match(html, new RegExp(`data-progress-color="${color}"`));
      }
      assert.match(html, /<dialog[^>]*aria-labelledby=/);
      assert.match(html, /aria-haspopup="dialog"/);
      assert.match(html, /match-strategy/);
      assert.match(html, /class="match-details"/);
      assert.match(html, /sym-attempts/);
      assert.match(html, /sym-assemblies/);
      assert.match(html, /sym-finishes/);
      assert.match(html, language === "ko" ? /세 퍼즐을 모두 완성한 뒤 버저/ : /Complete the blue, red and green puzzles before pressing the buzzer/);
      assert.match(html, language === "ko" ? /뒤집을 수 없습니다/ : /pieces cannot be flipped/);
      assert.match(html, language === "ko" ? /고정된 게임판이나 정답 윤곽 없이/ : /without a fixed game board or target outline/);
      assert.match(html, language === "ko" ? /소수와 음수도 사용할 수 있습니다/ : /may be decimal or negative/);
      assert.match(html, language === "ko" ? /원하는 각도/ : /any angle in degrees/);
      assert.match(html, /edge·vertex·to_piece·to_edge·to_vertex|edge, vertex, to_piece, to_edge and to_vertex/);
      assert.match(html, language === "ko" ? /같은 색의 전체 배치 목록에서 앞에/ : /earlier in the same color&#x27;s full replacement list/);
      assert.match(html, language === "ko" ? /선택한 변의 끝점이 아니어도/ : /need not be edge endpoints/);
      assert.match(html, language === "ko" ? /정답을 찾거나 선택을 고쳐주지 않습니다/ : /does not search for solutions or correct choices/);
      assert.match(html, /preserveAspectRatio="xMidYMid meet"/);
      for (const color of colors) assert.match(html, new RegExp(`data-progress-color="${color}"><span>[^<]+</span><strong>– / ${pieces[color].length}</strong>`));
      assert.doesNotMatch(html, /match-talk|10초|10s|라운드|Round |10×10|10x10|0°·90°·180°·270°/);
    });
    test(`${language}, ${count} players: public never receives private PNGs or placement counts; own and operator views keep correct ownership`, () => {
      const {start} = race(players);
      const frame = 3 + count * 2;
      const publicView = render(players, start, {language, selected: "P02", frame});
      assert.match(publicView, /data-board-id="PUBLIC-blue"/);
      assert.doesNotMatch(publicView, /P0\d-PRIVATE-|PRIVATE-STRATEGY/);
      assert.match(publicView, language === "ko" ? /배치 비공개/ : /Placements private/);
      const ownView = render(players, start, {language, view: "P01", selected: "P02", frame});
      assert.match(ownView, /data-board-id="P01-PRIVATE-blue"/);
      assert.match(ownView, /data-board-owner="P01"/);
      assert.doesNotMatch(ownView, /P02-PRIVATE-|PRIVATE-STRATEGY-P02/);
      assert.match(ownView, language === "ko" ? /배치 수는 정답 판정이 아닙니다/ : /Placement counts do not judge symmetry/);
      const operator = render(players, start, {language, view: "operator", selected: "P02", frame});
      assert.match(operator, /data-board-id="P02-PRIVATE-blue"/);
      assert.match(operator, /PRIVATE-STRATEGY-P02/);
      assert.match(render(players, start, {language, view: "P01", selected: "P01", frame}), /PRIVATE-STRATEGY-P01/);
    });
    test(`${language}, ${count} players: one finished player's three assemblies stay private through all finishes until the actual reveal`, () => {
      const {start, done, steps} = race(players);
      const before = render(players, steps, {language, frame: start.length});
      assert.doesNotMatch(before, /data-status="safe"|data-filled="true"|P0\d-FINISHED-/);
      const firstSafe = render(players, steps, {language, frame: start.length + 3, selected: "P01"});
      assert.equal((firstSafe.match(/data-status="safe"/g) ?? []).length, 1);
      assert.match(firstSafe, /data-board-id="PUBLIC-blue"/);
      assert.doesNotMatch(firstSafe, /P0\d-FINISHED-|PRIVATE-STRATEGY|data-status="eliminated"/);
      const beforeReveal = render(players, steps, {language, frame: start.length + done.length});
      assert.equal((beforeReveal.match(/data-status="safe"/g) ?? []).length, count - 1);
      assert.match(beforeReveal, /data-board-id="PUBLIC-blue"/);
      const revealed = render(players, steps, {language, frame: start.length + done.length + 1, selected: "P02"});
      assert.match(revealed, /data-board-id="P02-FINISHED-blue"/);
      assert.doesNotMatch(revealed, /PRIVATE-STRATEGY/);
      const other = render(players, steps, {language, view: "P01", selected: "P02"});
      assert.match(other, /data-board-id="P02-FINISHED-blue"/);
      assert.doesNotMatch(other, /PRIVATE-STRATEGY-P02/);
    });
    test(`${language}, ${count} players: wrong global verdict reveals no color oracle; final results lower exactly one platform even if every final score is three`, () => {
      const {start, steps} = race(players);
      const wrong = render(players, [...start, buzz("P01"), verdict("P01", false)], {language, view: "P01"});
      assert.match(wrong, language === "ko" ? /세 색을 검토하고 재제출/ : /Review all three colors and resubmit/);
      assert.equal((wrong.match(/data-status="assembling"/g) ?? []).length, count);
      assert.doesNotMatch(wrong, /data-status="safe"|data-progress-correct=|data-axis=/);
      const html = render(players, steps, {language});
      assert.equal((html.match(/data-status="safe"/g) ?? []).length, count - 1);
      assert.equal((html.match(/data-status="eliminated"/g) ?? []).length, 1);
      assert.equal((html.match(/class="exile-lift"/g) ?? []).length, count);
      assert.match(html, language === "ko" ? /최종 결과/ : /Final results/);
      assert.doesNotMatch(render(players, steps, {language, frame: steps.length - 1}), /data-status="eliminated"/);
    });
  }
}

test("all three current PNGs resolve per owner and color; public remains on the three empty workspaces until actual end reveal", () => {
  const players = ["P01", "P02", "P03"];
  const state = {exilePerspective: "operator"};
  api.en.applySymmetryEvent(state, "sym_setup", setupData(players));
  assert.equal(state.symSetup.version, 2);
  assert.equal(state.symSetup.mode, "polygons");
  assert.equal(Object.hasOwn(state.symSetup, "grid_size"), false);
  const publicData = {puzzles: puzzlesData.puzzles.map((puzzle) => ({...puzzle, cells: ["SECRET-CELLS"], solution: "SECRET-ASSEMBLY"}))};
  api.en.applySymmetryEvent(state, "sym_puzzles", publicData, {step: 2});
  const data = {...workingData("P01"), color_correct: {blue: "SECRET-ORACLE"}};
  const original = structuredClone(data);
  api.en.applySymmetryEvent(state, "sym_board", data, {step: 4});
  assert.doesNotMatch(JSON.stringify(state), /SECRET-/);
  assert.deepEqual(state.symBoards.P01.placements.blue, data.placements.blue);
  assert.equal(state.symBoards.P01.placements.blue[0].x, -2.5);
  assert.equal(state.symBoards.P01.placements.blue[1].rotation, 137.25);
  for (const color of colors) {
    assert.equal(api.en.symmetryBoardFor(state, players, "P01", color, "public").board.id, `PUBLIC-${color}`);
    assert.equal(api.en.symmetryBoardFor(state, players, "P02", color, "P01").board.id, `P01-PRIVATE-${color}`);
    assert.equal(api.en.symmetryBoardFor(state, players, "P01", color).board.image, data.boards[color].image);
  }
  api.en.applySymmetryEvent(state, "sym_finish", {...finishData("P01", 1), placements: {blue: "SECRET-FINISH"}}, {step: 5});
  assert.doesNotMatch(JSON.stringify(state), /SECRET-/);
  api.en.applySymmetryEvent(state, "sym_reveal", revealData(players), {step: 6});
  assert.equal(state.symRevealed, false);
  api.en.applySymmetryEvent(state, "sym_finish", finishData("P02", 2), {step: 7});
  for (const color of colors) assert.equal(api.en.symmetryBoardFor(state, players, "P01", color, "public").board.id, `PUBLIC-${color}`);
  const finalData = revealData(players), originalFinal = structuredClone(finalData);
  api.en.applySymmetryEvent(state, "sym_reveal", finalData, {step: 8});
  for (const color of colors) assert.equal(api.en.symmetryBoardFor(state, players, "P02", color, "public").board.id, `P02-FINISHED-${color}`);
  state.symOperations[0].placements.blue[0].x = 9;
  state.symBoards.P02.placements.green[0].rotation = 270;
  assert.deepEqual(data, original);
  assert.deepEqual(finalData, originalFinal);
  assert.equal(state.symOperations[0].step, 4);
  assert.equal(state.symFinishes[0].step, 5);
  assert.equal(state.symRevealStep, 8);
});

test("full replacement action summary covers every color and never turns malformed text into a solution", () => {
  assert.equal(api.en.symmetryActionText(JSON.stringify({type: "arrange", placements: workingData("P01").placements, submit: true})), "Replace all three assemblies · Blue 2 · Red 1 · Green 0 · Submit with buzzer");
  assert.equal(api.en.symmetryActionText('{"type":"wait"}'), "Wait · Keep all three assemblies");
  assert.equal(api.en.symmetryActionText('not JSON'), "Invalid arrangement action");
});

test("one-color action labels preserve the other colors and retain whole-set submission semantics", () => {
  const action = {type: "arrange_color", color: "red", placements: [{piece: "R1"}, {piece: "R2"}], submit: true};
  assert.equal(api.en.symmetryActionText(JSON.stringify(action)), "Replace Red assembly · 2 pieces · Keep the other two colors · Submit with buzzer");
  assert.equal(api.ko.symmetryActionText(action), "빨강 작업판 교체 · 조각 2개 · 나머지 두 색 유지 · 버저 제출");
  assert.equal(api.en.symmetryActionText({...action, color: "unknown"}), "Invalid arrangement action");
  assert.equal(api.en.symmetryActionText({...action, placements: {red: []}}), "Invalid arrangement action");
  const actionEvent = event("action", {phase: "symmetry_arrange", action: JSON.stringify(action)}, ["P01"], "P01");
  const html = render(["P01", "P02", "P03"], [actionEvent], {language: "en", view: "operator"});
  assert.match(html, /Arrange pieces/);
  assert.match(html, /Replace Red assembly · 2 pieces · Keep the other two colors · Submit with buzzer/);
});

test("v5 copies only known finite axes and workbench image fields, with owner privacy and reveal intact", () => {
  const players = ["P01", "P02", "P03"], state = {};
  api.en.applySymmetryEvent(state, "sym_setup", {...setupData(players), version: 5});
  api.en.applySymmetryEvent(state, "sym_puzzles", focusPuzzles);
  const data = workbenchData("P01");
  data.axes = {blue: 20.25, red: NaN, green: "SECRET-AXIS", violet: 35};
  Object.assign(data.workbenches.blue, {solution: "SECRET-SOLUTION", axis_correct: "SECRET-ORACLE"});
  data.workbenches.violet = image("SECRET-EXTRA-COLOR");
  api.en.applySymmetryEvent(state, "sym_board", data, {step: 4});
  assert.deepEqual(state.symBoards.P01.axes, {blue: 20.25, red: null, green: null});
  assert.deepEqual(state.symBoards.P01.workbenches.blue, workbenchData("P01").workbenches.blue);
  data.axes.blue = 99;
  data.workbenches.blue.image = "MUTATED";
  assert.equal(state.symBoards.P01.axes.blue, 20.25);
  assert.doesNotMatch(JSON.stringify(state), /SECRET-|MUTATED/);
  for (const color of colors) {
    assert.equal(api.en.symmetryBoardFor(state, players, "P01", color, "public").workbench, null);
    assert.equal(api.en.symmetryBoardFor(state, players, "P02", color, "P01").workbench.id, `P01-WORKBENCH-${color}`);
    assert.equal(api.en.symmetryBoardFor(state, players, "P01", color, "operator").workbench.id, `P01-WORKBENCH-${color}`);
  }
  const before = structuredClone(state.symBoards);
  api.en.applySymmetryEvent(state, "sym_tools", {...focusTools, version: 5});
  assert.deepEqual(state.symBoards, before);
  api.en.applySymmetryEvent(state, "sym_finish", finishData("P01", 1));
  api.en.applySymmetryEvent(state, "sym_reveal", {boards: {P01: workbenchData("P01", true)}});
  assert.equal(api.en.symmetryBoardFor(state, players, "P01", "blue", "public").workbench, null);
  api.en.applySymmetryEvent(state, "sym_finish", finishData("P02", 2));
  const finalData = {boards: Object.fromEntries(players.map((player) => [player, workbenchData(player, true)]))};
  api.en.applySymmetryEvent(state, "sym_reveal", finalData, {step: 8});
  assert.equal(api.en.symmetryBoardFor(state, players, "P02", "blue", "public").workbench.id, "P02-WORKBENCH-blue");
  state.symBoards.P02.axes.blue = 30;
  state.symBoards.P02.workbenches.blue.image = "CHANGED";
  assert.equal(finalData.boards.P02.axes.blue, 20.25);
  assert.notEqual(finalData.boards.P02.workbenches.blue.image, "CHANGED");
});

test("v4 public overview and focus migration copy only observed fields without touching private assemblies", () => {
  const players = ["P01", "P02", "P03"], state = {};
  api.en.applySymmetryEvent(state, "sym_setup", {...setupData(players), version: 3});
  api.en.applySymmetryEvent(state, "sym_puzzles", detailedPuzzles);
  api.en.applySymmetryEvent(state, "sym_board", workingData("P01"));
  const before = structuredClone(state.symBoards), tools = structuredClone(focusTools);
  tools.puzzles[0].overview.solution = "SECRET-SOLUTION";
  tools.color_correct = "SECRET-VERDICT";
  api.en.applySymmetryEvent(state, "sym_tools", tools);
  assert.equal(state.symSetup.version, 4);
  assert.equal(state.symSetup.focus_mode, "one_color");
  assert.equal(state.symSetup.focus_start_window, 2);
  assert.deepEqual(state.symPuzzles[0].overview, overviewImage("blue"));
  assert.deepEqual(state.symPuzzles[0].details, detailImage("blue"));
  tools.puzzles[0].overview.image = "MUTATED";
  assert.equal(state.symPuzzles[0].overview.image, overviewImage("blue").image);
  api.en.applySymmetryEvent(state, "sym_window", {window: 2, active: players, focus_color: "red", color_correct: "SECRET-VERDICT"});
  assert.equal(state.symWindow.focus_color, "red");
  assert.deepEqual(state.symBoards, before);
  api.en.applySymmetryEvent(state, "sym_tools", focusTools);
  assert.equal(state.symWindow.focus_color, "blue");
  assert.deepEqual(state.symBoards, before);
  assert.doesNotMatch(JSON.stringify(state), /SECRET-|MUTATED/);
  api.en.applySymmetryEvent(state, "sym_setup", {...setupData(players), version: 4, focus_mode: "one_color", focus_start_window: 1});
  api.en.applySymmetryEvent(state, "sym_puzzles", focusPuzzles);
  assert.deepEqual(state.symPuzzles[2].overview, overviewImage("green"));
});

test("public piece atlases are copied without private or answer fields, and migration preserves existing boards and history", () => {
  const players = ["P01", "P02", "P03"], state = {};
  api.en.applySymmetryEvent(state, "sym_setup", setupData(players));
  const data = structuredClone(detailedPuzzles);
  for (const puzzle of data.puzzles) Object.assign(puzzle.details, {placements: "SECRET-WORKSPACE", axes: "SECRET-AXES", solution: "SECRET-SOLUTION"});
  api.en.applySymmetryEvent(state, "sym_puzzles", data, {step: 2});
  for (const color of colors) assert.deepEqual(state.symPuzzles.find(({id}) => id === color).details, detailImage(color));
  data.puzzles[0].details.image = "MUTATED";
  assert.equal(state.symPuzzles[0].details.image, detailImage("blue").image);
  api.en.applySymmetryEvent(state, "sym_board", workingData("P01"), {step: 4});
  api.en.applySymmetryEvent(state, "sym_verdict", {player: "P01", window: 1, attempt: 1, correct: false}, {step: 5});
  const beforeBoards = structuredClone(state.symBoards), beforeAttempts = structuredClone(state.symAttempts);
  const migration = structuredClone(toolsData);
  migration.puzzles[0].details.image = "NEW-ATLAS";
  migration.puzzles[0].details.solution = "SECRET-SOLUTION";
  migration.puzzles.push({id: "SECRET-EXTRA-PUZZLE", details: image("SECRET-EXTRA")});
  api.en.applySymmetryEvent(state, "sym_tools", migration, {step: 6});
  assert.equal(state.symSetup.version, 3);
  assert.equal(state.symSetup.thinking_passes, 3);
  assert.equal(state.symPuzzles[0].details.image, "NEW-ATLAS");
  assert.equal(state.symPuzzles[0].step, 2);
  assert.equal(state.symPuzzles.length, 3);
  assert.deepEqual(state.symPuzzles[0].piece_ids, pieces.blue);
  assert.deepEqual(state.symPuzzles[0].board, image("PUBLIC-blue"));
  assert.deepEqual(state.symBoards, beforeBoards);
  assert.deepEqual(state.symAttempts, beforeAttempts);
  migration.puzzles[0].details.image = "MUTATED";
  assert.equal(state.symPuzzles[0].details.image, "NEW-ATLAS");
  assert.doesNotMatch(JSON.stringify(state), /SECRET-|MUTATED/);
});

test("tutorial state copies only the observed public example, persists through windows, and resets for a new setup", () => {
  const players = ["P01", "P02", "P03"], state = {};
  api.en.applySymmetryEvent(state, "sym_setup", {...setupData(players), version: 3});
  assert.equal(state.symTutorial, null);
  const data = structuredClone(tutorialData);
  Object.assign(data, {placements: "SECRET-CURRENT-ASSEMBLY", axes: "SECRET-CURRENT-AXES"});
  data.board.solution = "SECRET-CURRENT-SOLUTION";
  data.explanations.private = "SECRET-MEMO";
  api.en.applySymmetryEvent(state, "sym_tutorial", data, {step: 4});
  assert.deepEqual(state.symTutorial, {...tutorialData, step: 4});
  data.board.image = "MUTATED";
  data.explanations.en = "MUTATED";
  assert.deepEqual(state.symTutorial.board, tutorialData.board);
  assert.equal(state.symTutorial.explanations.en, tutorialData.explanations.en);
  api.en.applySymmetryEvent(state, "sym_window", {window: 2, active: players});
  assert.equal(state.symTutorial.step, 4);
  assert.doesNotMatch(JSON.stringify(state), /SECRET-|MUTATED/);
  api.en.applySymmetryEvent(state, "sym_setup", setupData(players));
  assert.equal(state.symTutorial, null);
});

test("English rules describe the recovered polygon sets and continuous placement without a fixed grid", () => {
  const summary = api.en.rulesSummary("대칭 퍼즐 · 게임 규칙", "");
  assert.match(summary, /two, three and three polygon pieces respectively/);
  assert.match(summary, /without a fixed game board or target outline/);
  assert.match(summary, /any angle in degrees, wrapping every 360°/);
  assert.match(summary, /Decimal and negative coordinates are valid/);
  assert.match(summary, /including its empty spaces/);
  assert.match(summary, /Optional exact alignment uses piece, edge, vertex, to_piece, to_edge and to_vertex/);
  assert.match(summary, /earlier in the same color's full replacement list/);
  assert.match(summary, /labels start at zero/);
  assert.match(summary, /need not be edge endpoints/);
  assert.match(summary, /does not search for solutions or correct choices/);
  assert.match(summary, /Edges may have different lengths and touch along only part of an edge/);
  assert.match(summary, /point-only contact does not connect pieces/);
  assert.match(summary, /without color-specific feedback or solution axes/);
  assert.doesNotMatch(summary, /three private strategy passes|Public piece detail images/);
  const modern = api.en.rulesSummary("대칭 퍼즐 · 게임 규칙", "고정 조각 상세도와 최대 세 번의 판단");
  assert.match(modern, /Public piece detail images enlarge the vertex v and edge e labels/);
  assert.match(modern, /Your own memo and recent failed attempts carry into the next thinking window/);
  assert.match(modern, /up to three private strategy passes/);
  assert.match(modern, /finalize the arrangement earlier/);
  const focused = api.en.rulesSummary("대칭 퍼즐 · 게임 규칙", "arrange_color와 공통 배율 상세도");
  assert.match(focused, /arrange_color replaces the focused color only and preserves the other two assemblies/);
  assert.match(focused, /Common scale overview uses one scale for every piece/);
  assert.match(focused, /changing focus is not a correct\/incorrect verdict/);
  assert.doesNotMatch(focused, /An arrangement action replaces all three current workspaces/);
  assert.match(api.en.rulesSummary("대칭 퍼즐 · 게임 규칙", "G1의 가장 긴 변과 45도를 이루는 반사축"),
    /45° to G1’s longest edge/);
  assert.doesNotMatch(focused, /45° to G1/);
  assert.doesNotMatch(summary, /10×10|10x10|0°, 90°, 180° and 270°/);
});
