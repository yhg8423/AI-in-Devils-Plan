import assert from "node:assert/strict";
import {mkdtempSync, rmSync} from "node:fs";
import {createRequire} from "node:module";
import {tmpdir} from "node:os";
import {dirname, join} from "node:path";
import {fileURLToPath} from "node:url";
import {after, test} from "node:test";
import {build} from "esbuild";

const directory = mkdtempSync(join(tmpdir(), "wall-go-ui-"));
after(() => rmSync(directory, {recursive:true, force:true}));
const require = createRequire(import.meta.url), api = {};
for (const language of ["ko", "en"]) {
  const bundle = join(directory, `${language}.cjs`);
  await build({stdin:{contents:`import React from 'react'; import {renderToStaticMarkup} from 'react-dom/server'; import {MatchReplay} from './match-replay.jsx'; export {applyWallEvent} from './wall-go.jsx'; export const render = replay => renderToStaticMarkup(<MatchReplay replay={replay} transport={null}/>);`, loader:"jsx",resolveDir:dirname(fileURLToPath(import.meta.url))},outfile:bundle,bundle:true,platform:"node",format:"cjs",logLevel:"silent",loader:{".css":"empty",".woff2":"empty",".md":"text"},define:{STATIC_REPLAY_BUILD:"false","process.env.NODE_ENV":'"production"',"globalThis.location":JSON.stringify({search:language === "en" ? "?lang=en" : ""})}});
  api[language] = require(bundle);
}
const players = ["P01", "P02", "P03"], noop = () => {};
const event = (msg_type, data, visible_to="all", agent_name="System") => ({events:[{msg_type,content:typeof data === "string" ? data : JSON.stringify(data),visible_to,agent_name}]});
const board = {game:1,round:1,replay:0,players,order:players,size:7,breakers:{P01:1,P02:1,P03:1},walls:[[[2,2],[2,3]]],pieces:{"P01:S1":{player:"P01",kind:"square",position:[2,2]},"P01:C1":{player:"P01",kind:"round",position:[3,2]},"P02:S1":{player:"P02",kind:"square",position:[6,2]},"P02:C1":{player:"P02",kind:"round",position:[6,6]},"P03:S1":{player:"P03",kind:"square",position:[2,6]},"P03:C1":{player:"P03",kind:"round",position:[4,6]}}};
const setup = event("wall_setup",board);
const turn = event("wall_turn",{game:1,round:1,turn:1,player:"P01"});
const move = event("wall_move",{game:1,round:1,turn:1,player:"P01",piece:"P01:S1",from:[2,2],to:[2,3],path:[[2,3]],wall:[[2,3],[3,3]],broken:[[2,2],[2,3]],breakers:{P01:0,P02:1,P03:1}});
const end = event("wall_end",{game:1,round:1,replay:0,players,scores:{P01:20,P02:15,P03:14},largest:{P01:12,P02:10,P03:9},territories:[{owner:"P01",cells:[[2,2],[2,3]]}],ranking:[["P01"],["P02"],["P03"]],winner:"P01"});
function render(steps,{language="ko",view="public",frame=steps.length}={}) {
  return api[language].render({id:"wall-demo",match:{game:"4일차 감옥 매치 · 벽바둑 2",players,steps},frame,view,selected:"",choosePlayer:noop,chooseView:noop,seek:noop,mode:"paused"});
}
for (const language of ["ko","en"]) {
  test(`${language}: board uses 49 labeled cells, both counter shapes and no conversation panel`,() => {
    const html=render([setup,turn],{language});
    assert.equal((html.match(/data-cell=/g)??[]).length,49);
    assert.equal((html.match(/data-kind="square"/g)??[]).length,3);
    assert.equal((html.match(/data-kind="round"/g)??[]).length,3);
    assert.match(html,language === "ko" ? /벽바둑 결과와 기록/ : /Wall Go results and records/);
    assert.match(html,language === "ko" ? /대화 없이 진행/ : /No discussion/);
    assert.doesNotMatch(html,/arena-speech|match-talk/);
  });
  test(`${language}: moves display a path, new wall and separately marked broken wall`,() => {
    const html=render([setup,turn,move],{language});
    assert.match(html,/wall-move-path/);
    assert.match(html,/recent-wall/);
    assert.match(html,/broken-wall/);
    assert.match(html,/data-piece="P01:S1"/);
    assert.match(html,language === "ko" ? /벽 부수기/ : /Break wall/);
    assert.doesNotMatch(render([setup,turn,move],{language,frame:1}),/wall-move-path|broken-wall/);
  });
  test(`${language}: scoring reveals territories and history only at the end event`,() => {
    const steps=[setup,turn,move,end];
    assert.doesNotMatch(render(steps,{language,frame:3}),/data-owner=/);
    const html=render(steps,{language});
    assert.match(html,/data-owner="P01"/);
    assert.match(html,language === "ko" ? /영역 1위 · P01/ : /Territory winner · P01/);
    assert.match(html,/P01 &gt; P02 &gt; P03/);
  });
  test(`${language}: replay clears the old board and fixed circles reset on the new game`,() => {
    const replay=event("wall_replay",{round:1,players:["P02","P03"],order:["P03","P02"]});
    const pending=render([setup,end,replay],{language});
    assert.doesNotMatch(pending,/data-piece=/);
    assert.match(pending,language === "ko" ? /동률 재경기 준비/ : /Preparing a tied-player replay/);
    const second={...board,game:2,round:2,players:["P02","P03"],order:["P02","P03"],walls:[],breakers:{P02:0,P03:0},pieces:{"P02:C1":{player:"P02",kind:"round",position:[2,2]},"P02:C2":{player:"P02",kind:"round",position:[6,6]},"P03:C1":{player:"P03",kind:"round",position:[2,6]},"P03:C2":{player:"P03",kind:"round",position:[6,2]},"P02:S1":{player:"P02",kind:"square",position:null}}};
    const html=render([setup,end,replay,event("wall_setup",second)],{language});
    assert.equal((html.match(/data-kind="round"/g)??[]).length,4);
    assert.doesNotMatch(html,/broken-wall|recent-wall/);
    assert.match(html,language === "ko" ? /벽 부수기 없음/ : /No wall breakers/);
  });
}
test("private strategy notes stay private across all public board events",()=> {
  const note=event("decision_note",{phase:"wall_move",note:"PRIVATE-WALL-PLAN"},["P01"],"P01");
  const steps=[setup,note,turn,move];
  assert.doesNotMatch(render(steps),/PRIVATE-WALL-PLAN/);
  assert.doesNotMatch(render(steps,{view:"P02"}),/PRIVATE-WALL-PLAN/);
  assert.match(render(steps,{view:"P01"}),/PRIVATE-WALL-PLAN/);
  assert.match(render(steps,{view:"operator"}),/PRIVATE-WALL-PLAN/);
});
test("timeout, pass and final standings are readable without leaking future results",()=> {
  const timeout=event("wall_timeout",{game:1,round:1,turn:1,player:"P01",seconds:90,phase:"move"});
  const pass=event("wall_pass",{game:1,round:1,turn:2,player:"P03",reason:"isolated"});
  const result=event("match_result",{ranking:["P01","P02","P03"],scores:{P01:20,P02:30,P03:19},eliminated:["P03"],pieces:{P01:2,P02:3,P03:1}});
  const html=render([setup,turn,timeout,move,pass,end,result],{language:"en"});
  assert.match(render([setup,turn,timeout,move],{language:"en"}),/Random wall after timeout/);
  assert.match(html,/Automatic pass/);
  assert.match(html,/Final standings/);
  assert.match(html,/Eliminated/);
  assert.doesNotMatch(render([setup,turn,timeout,move,pass,end,result],{frame:4,language:"en"}),/Final standings|Eliminated/);
});

test("live territory totals update without revealing a future end state", () => {
  const state = {};
  api.ko.applyWallEvent(state, "wall_setup", {...board, scores:{P01:0,P02:0,P03:0}, largest:{P01:0,P02:0,P03:0}});
  const data = JSON.parse(move.events[0].content);
  api.ko.applyWallEvent(state, "wall_move", {...data, scores:{P01:5,P02:0,P03:0}, largest:{P01:5,P02:0,P03:0}});
  assert.equal(state.wallGame.scores.P01, 5);
  assert.equal(state.wallGame.largest.P01, 5);
  assert.equal(state.wallEnd, null);
  api.ko.applyWallEvent(state, "wall_setup", {...board, scores:{P01:0,P02:0,P03:0}, largest:{P01:0,P02:0,P03:0}});
  assert.equal(state.wallGame.scores.P01, 0);
});

test("stalemate results show occupied-square scoring and preserve the scored cells", () => {
  const scored = {...JSON.parse(end.events[0].content), reason:"stalemate", scores:{P01:2,P02:2,P03:2}, largest:{P01:1,P02:1,P03:1},
    winner:null, ranking:[players], territories:Object.values(board.pieces).map((piece) => ({owner:piece.player,cells:[piece.position]}))};
  const steps = [setup,event("wall_end",scored)];
  assert.equal((render(steps).match(/data-owner=/g) ?? []).length, 6);
  assert.match(render(steps), /공동 영역은 각 말이 선 칸만 1점씩 인정/);
  assert.match(render(steps,{language:"en"}), /Only occupied squares in shared territory score one point per counter/);
  assert.doesNotMatch(render(steps,{frame:1}), /교착 종료/);
});

test("high-contrast player colors remain stable in a reordered two-player round", () => {
  const initial = render([setup]);
  for (const color of ["#ff765e", "#55b9ff", "#ffe066"]) assert.match(initial, new RegExp(`fill="${color}"`));
  assert.match(initial, /P01 · 빨강/);
  assert.match(initial, /P02 · 파랑/);
  assert.match(initial, /P03 · 노랑/);
  const second = {...board, game:2, round:2, players:["P03","P02"], order:["P03","P02"],
    pieces:Object.fromEntries(Object.entries(board.pieces).filter(([,piece]) => piece.player !== "P01"))};
  const html = render([setup,event("wall_setup",second)]);
  assert.match(html, /P02 · 파랑/);
  assert.match(html, /P03 · 노랑/);
  assert.doesNotMatch(html, /fill="#ff765e"/);
  assert.match(render([setup],{language:"en"}), /P01 · Red/);
});
