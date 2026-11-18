import React, {useCallback, useEffect, useMemo, useState} from "react";
import {Button} from "@astryxdesign/core/Button";
import {Selector} from "@astryxdesign/core/Selector";
import {Tab, TabList} from "@astryxdesign/core/TabList";
import {choiceCountLabel, choiceOptionLabel, choiceResults, optionsByChoice} from "./choice-results.js";
import {RouletteInspection, RouletteInspectionLegend, RouletteScene} from "./day-two-scenes.jsx";
import {applyGemEvent, gemActionText, gemDiscussionLabel, gemEventText, gemSlotLabel, GemStage} from "./gem-exchange.jsx";
import {drawGemSet, gemSetPoint} from "./gem-floor.js";
import {GemInformation} from "./gem-info.jsx";
import {Heavy13Information} from "./heavy-13-info.jsx";
import {chipColorLabel} from "./heavy-13.js";
import {runHref} from "./home.jsx";
import {cardPositions, CommunityCards, duelWinner, formatPokerCards, GrassResults, handNames, PokerCard, PokerResults} from "./minigame-results.jsx";
import {PrisonScene} from "./prison-scene.jsx";
import {applyPigEvent, pigActionText, pigEventText, PiggyScene, PiggyStage, PiggyInformation} from "./piggy-bank.jsx";
import {isStrategy, MatchFeed, Participant, Standings, Table} from "./records.jsx";
import {BoardScene, RoomScene} from "./scene.jsx";
import {checkpointLabel, decisionNoteLabel, eventFields, eventText, grassBonusText, phaseNames, roomRecordText, scoreText, snapshot} from "./replay.js";
import {en, gameTitle, tr} from "./locale.js";
import {rulesSummary} from "./rule-summaries.js";

const labels = {
  rules: tr("게임 규칙", "Game rules"), action: tr("행동", "Action"), invalid_action: tr("반려된 행동", "Rejected action"), scoreboard: tr("승점", "Victory Points"), round: tr("라운드", "Round"),
  cube_puzzle: tr("큐브 세기", "Cube Counting"), cube_answer: tr("큐브 답안", "Cube answer"), priority: tr("큐브 세기 결과", "Cube Counting results"), teams: tr("네모 세기 팀", "Rectangle Counting teams"),
  representatives: tr("팀 대표", "Team representative"), rectangle_puzzle: tr("네모 세기", "Rectangle Counting"), buzz: tr("버저", "Buzzer"), rectangle_answer: tr("네모 세기 정답", "Rectangle Counting answer"),
  rectangle_standings: tr("네모 세기 정답 수", "Rectangle Counting scores"), rectangle_result: tr("네모 세기 결과", "Rectangle Counting results"),
  team_vote: tr("팀 선택 결과", "Team choice results"), challenge_result: tr("추가 대결 결과", "Tiebreaker results"), choice_progress: tr("선택 제출 현황", "Submission progress"),
  choice_4_result: tr("선택 4 결과", "Choice 4 results"), choice_request: tr("선택 5", "Choice 5"), preview: tr("비공개 미리보기", "Private preview"), discussion: tr("선택 5 전 협상", "Pre–Choice 5 negotiation"),
  grass_rules: tr("잔디 깔기 시작", "Lay the Grass begins"), grass_phase: tr("잔디 깔기", "Lay the Grass"), grass_plan: tr("미리보기 전략", "Preview strategy"), discussion_note: tr("협상 전략", "Negotiation strategy"),
  room_move: tr("이동", "Move"), public: tr("전체 발언", "Public message"), room: tr("룸 발언", "Room message"), whisper: tr("귓속말", "Whisper"), room_invite: tr("룸 초대", "Room invitation"),
  room_invite_response: tr("초대 응답", "Invitation response"), grass_tile: tr("타일 선택", "Tile selection"), grass_choices: tr("선택 결과", "Choice results"), grass_obstacle: tr("장애물", "Obstacle"),
  negotiation_start: tr("협상 시작", "Negotiation begins"), negotiation_round: tr("협상 턴", "Negotiation turn"), negotiation_end: tr("협상 종료", "Negotiation ends"),
  relationship_update: tr("관계 평가", "Relationship review"),
  grass_placement: tr("타일 배치", "Tile placement"), grass_bonus: tr("잔디 깔기 정산", "Lay the Grass scoring"), pre_poker_ranking: tr("기억 포커 전 순위", "Standings before Memory Poker"),
  choice_9_result: tr("선택 9 결과", "Choice 9 results"), poker_mode: tr("기억 포커 방식", "Memory Poker format"), poker_cards: tr("기억 포커 카드 공개", "Memory Poker card reveal"),
  poker_result: tr("기억 포커 대결", "Memory Poker duel"), poker_ranking: tr("기억 포커 순위", "Memory Poker rankings"),
  colors: tr("색 칩 공개", "Color chips revealed"), weights: tr("무게 공개", "Weights revealed"), placement: tr("큐브 배치", "Cube placement"), market: tr("시세", "Stock prices"), hints: tr("공개 단서", "Public clues"),
  market_tick: tr("거래 시간", "Trading time"), trade_fill: tr("주문 체결", "Trade filled"), seats: tr("자리 배정", "Seating"), inspection: tr("조사", "Inspection"), shift: tr("회전", "Rotation"), swap: tr("조작 · 두 칸 교환", "Manipulation · Two slots swapped"),
  gem_setup: tr("게임 준비", "Game setup"), gem_manito: tr("비공개 마니또", "Private manito"),
  gem_preparation: tr("비공개 전략 준비", "Private strategy preparation"), gem_preparation_end: tr("전략 준비 완료", "Preparation complete"),
  gem_discussion: tr("대화 시작", "Discussion begins"), gem_discussion_round: tr("대화 턴", "Discussion turn"),
  gem_discussion_end: tr("대화 종료", "Discussion ends"), gem_strategy: tr("비공개 전략 정리", "Private planning"),
  gem_auction_round: tr("선 플레이어 경매", "Lead auction"), gem_auction: tr("경매 결과", "Auction results"),
  gem_round: tr("라운드 시작", "Round begins"), gem_turn: tr("카드 교환 차례", "Swap turn"),
  gem_card: tr("내 카드 확인", "Inspect own card"), gem_swap: tr("카드 교환", "Card swap"),
  gem_peek: tr("피스 카드 확인", "Piece inspection"), gem_bonus: tr("폭탄 보너스", "Bomb bonus"),
  gem_piece: tr("피스 변동", "Piece balance"), gem_reveal: tr("카드·점수 공개", "Cards and scores revealed"),
  gem_final: tr("마니또 최종 정산", "Final manito scoring"),
  pig_setup: tr("저금통 배분", "Banks dealt"), pig_turn: tr("입금 차례", "Deposit turn"),
  pig_contents: tr("운영자 동전 현황", "Operator coin counts"), pig_deposit: tr("입금과 전달", "Deposit and pass"),
  pig_claim: tr("동전 개수 선언", "Coin count declaration"), pig_doubt: tr("의심 판정", "Doubt resolved"),
  pig_replace: tr("새 저금통 지급", "Replacement bank"), pig_reset_vote: tr("리셋 요청", "Reset request"),
  pig_challenge: tr("전체 저금통 도전", "All-bank challenge"), pig_reset: tr("저금통 리셋", "Banks reset"),
  pig_pass: tr("의심 없이 통과", "Declaration accepted"), pig_discussion: tr("대화 시작", "Discussion begins"),
  pig_discussion_end: tr("대화 종료", "Discussion ends"), pig_preparation: tr("비공개 전략 준비", "Private preparation"),
  pig_preparation_end: tr("전략 준비 완료", "Preparation complete"),
  pass: tr("자동 패스", "Automatic pass"), private_action: tr("비공개 행동", "Private action"), match_result: tr("최종 결과", "Final results"), match_interrupted: tr("플레이 중단", "Run interrupted"),
};
const legacyRelationshipCheckpoints = new Map([
  ["이전 경기에서 이어받음", "이전 매치에서 이어받음"],
  ["경기 종료", "매치 종료"],
]);
const actions = {
  choice_1: tr("선택 1", "Choice 1"), choice_2: tr("선택 2", "Choice 2"), choice_3_team: tr("선택 3 · 팀", "Choice 3 · Team"), choice_3_solo: tr("선택 3 · 개인", "Choice 3 · Solo"),
  choice_4: tr("선택 4", "Choice 4"), choice_9: tr("선택 9", "Choice 9"), choice_10: tr("선택 10", "Choice 10"), cubes: tr("큐브 답안 제출", "Submit cube count"), rectangles: tr("네모 답안 제출", "Submit rectangle count"),
  rectangle_challenge: tr("추가 대결 답안", "Tiebreaker answer"), memorize: tr("암기 위치", "Memorized positions"), memory_poker: tr("포커 카드 선택", "Poker card selection"), nominate: tr("대결 상대 지목", "Choose an opponent"),
  representative: tr("대표 투표", "Representative vote"), alliance: tr("연맹의 징표", "Alliance Token"), submit: tr("카드와 칩 제출", "Submit card and chip"), place: tr("배치 또는 패스", "Place or pass"),
  piece: tr("피스 사용", "Spend a Piece"), secret: tr("시크릿", "Secret"), trade: tr("주문", "Order"),
  market_turn: tr("거래소 행동", "Stock exchange action"), credit: tr("크레딧 사용", "Spend credits"),
  gem_bid: tr("선 플레이어 입찰", "Bid for the lead"), gem_auction_agreement: tr("경매 합의", "Auction agreement"),
  gem_peek: tr("피스 카드 확인", "Piece inspection"), gem_swap: tr("교환 상대 선택", "Choose a swap target"),
  gem_opening_talk: tr("게임 시작 전 대화", "Opening discussion"),
  gem_auction_talk: tr("경매 동률 협상", "Auction tie discussion"),
  gem_after_auction_talk: tr("경매 후 대화", "Post-auction discussion"),
  gem_talk: tr("교환 전 대화", "Pre-swap discussion"), gem_strategy: tr("교환 전 판단", "Pre-swap decision"),
  swap: tr("조작 위치 선택", "Select slots to swap"),
  pig_preparation: tr("비공개 전략 준비", "Private preparation"), pig_talk: tr("저금통 대화", "Piggy Bank discussion"),
  pig_deposit: tr("입금과 전달", "Deposit and pass"), pig_count: tr("동전 개수 선언", "Coin count declaration"),
  pig_doubt: tr("의심 선언", "Call doubt"), pig_reset_vote: tr("리셋 버튼", "Reset button"),
  pig_challenge: tr("전체 저금통 도전", "All-bank challenge"),
};
const grassPhases = {
  "선택 6~8 비공개 구상": "plan", "정보 공개 뒤 협상": "talk", "잔디 타일 선택": "draft",
  "선택 6 · 공격 또는 방어": "stance", "선택 7 · 상생 또는 견제": "partner", "선택 8 · 가로수 또는 맨홀": "obstacle",
  "맨홀 설치": "manhole", "가로수 설치": "tree", "잔디 타일 배치": "place", "상생 승점 분배": "split",
  "잔디 깔기 종료": "done",
};
const chapters = {
  cube_puzzle: tr("큐브 세기 판", "Cube Counting puzzle"), teams: tr("네모 세기 팀", "Rectangle Counting teams"), rectangle_result: tr("네모 세기 결과", "Rectangle Counting results"),
  grass_rules: tr("잔디 깔기", "Lay the Grass"), pre_poker_ranking: tr("기억 포커 전 순위", "Standings before Memory Poker"),
  match_result: tr("최종 결과", "Final results"),
};
const number = new Intl.NumberFormat(en ? "en" : "ko-KR");
const dialogueTypes = new Set(["public", "room", "whisper", "room_invite", "room_invite_response", "room_move"]);
const rouletteObservations = new Set(["inspection", "shift", "swap"]);
const rouletteStartingCredits = 16;
const pokerPhases = {nominate: tr("대결 상대 지목", "Choose an opponent"), memorize: tr("카드 암기 중", "Memorizing cards"), memory_poker: tr("카드 선택 중", "Selecting cards")};
const matchVenues = {"무거운 13": PrisonScene, "러시안 룰렛": RouletteScene, "돼지 저금통": PiggyScene};
const marketActions = {trade: tr("주문", "Order"), speak: tr("발언", "Speak"), move: tr("이동", "Move"), move_room: tr("이동", "Move"), pass: tr("패스", "Pass"),
  respond_invite: tr("초대 응답", "Invitation response"), piece: tr("피스 사용", "Spend a Piece"), secret: tr("시크릿 예약", "Schedule Secret")};
const marketStartingCash = 100_000;
const marketPieceCash = 10_000;
const roundLabel = (round) => tr(`${round}라운드`, `Round ${round}`);
const leaderLabel = (round, leader) => tr(`${round}라운드 · 선 ${leader}`, `Round ${round} · Leader ${leader}`);
const won = (amount) => tr(`${number.format(amount)}원`, `₩${number.format(amount)}`);
const shares = (quantity) => tr(`${number.format(quantity)}주`, `${number.format(quantity)} ${quantity === 1 ? "share" : "shares"}`);
const stockLabel = (stock) => en ? {
  맛소금융: "Matso Finance", 무조건설: "Mujo Construction", 방어제철: "Bangeo Steel",
  알트엔터: "Alt Entertainment", 열림보안: "Yeollim Security", 코요테크: "Koyo Tech", 후자전자: "Huja Electronics",
}[stock] ?? stock : stock;

function parse(content) {
  try { return JSON.parse(content); } catch { return content; }
}

function exchangedPieceForCash({phase, action}) {
  if (phase === "piece") return action === "현금";
  if (phase !== "market_turn") return false;
  const order = parse(action);
  return order?.type === "piece" && order.choice === "현금";
}

function readable(value) {
  if (Array.isArray(value)) return value.map(readable).join(" / ");
  if (value !== null && typeof value === "object") {
    return Object.entries(value).map(([key, item]) => `${key} ${readable(item)}`).join(" · ");
  }
  return value === null ? tr("비공개", "Private") : String(value);
}

function rouletteCreditAction(action) {
  const [kind, amount] = action.replace(" 조사 ", " ").split(" ");
  switch (kind) {
    case "공개": return {text: tr(`공개 조사 ${amount}`, `Public inspection ${amount}`), cost: 1};
    case "비공개": return {text: tr(`비공개 조사 ${amount}`, `Private inspection ${amount}`), cost: 2};
    case "이동":
    case "회전": return {text: tr(`${amount}칸 회전`, `Rotate ${amount} ${amount === "1" ? "slot" : "slots"}`), cost: Number(amount) + 2};
    case "기금":
    case "조작": return {text: tr(`조작 ${amount}크레딧`, `Manipulate · ${amount} credits`), cost: Number(amount)};
    default: return {text: action};
  }
}

function ruleText(content) {
  if (content.startsWith("보석 암시장")) content = content.replaceAll("회전", "턴");
  return content.replaceAll("경기 규칙", "게임 규칙")
    .replace(/(선택 5 전후로 각각 \d+)라운드 협상/g, "$1턴 협상")
    .replace(/(\d+)인 경기/g, "참가자 $1명")
    .replaceAll("경기 중", "게임 도중")
    .replaceAll("경기가 끝나고", "게임이 끝나고")
    .replaceAll("경기를 끝냅니다", "게임을 끝냅니다")
    .replaceAll("이 경기에서는", "이 게임에서는");
}

const ruleHeadings = {
  "양자택일 · 게임 규칙": "Either/Or · Game rules",
  "선택 1 · 성과금 / 보험금": "Choice 1 · Bonus or insurance",
  "미니게임 1 · 큐브 세기": "Minigame 1 · Cube Counting",
  "선택 2 · 팀 / 개인": "Choice 2 · Team or solo",
  "미니게임 2 · 네모 세기": "Minigame 2 · Rectangle Counting",
  "네모 세기 · 팀 대표 선출": "Rectangle Counting · Electing a team representative",
  "선택 3 · 네모 세기 정산과 추가 대결": "Choice 3 · Rectangle Counting scoring and tiebreaker",
  "선택 4 · 공공의 이익 / 개인의 이익": "Choice 4 · Public or personal benefit",
  "선택 5 · 점수 / 정보": "Choice 5 · Points or information",
  "선택 6~8 미리보기": "Preview of Choices 6–8",
  "선택 6 · 공격 / 방어": "Choice 6 · Attack or defense",
  "선택 7 · 상생 / 견제": "Choice 7 · Cooperation or competition",
  "선택 8 · 가로수 / 맨홀": "Choice 8 · Tree or manhole",
  "선택 9 · 탈락 인원 1명 / 2명": "Choice 9 · One or two eliminations",
  "미니게임 4 · 기억 포커와 선택 10": "Minigame 4 · Memory Poker and Choice 10",
  "최종 배정 · 연맹의 징표와 피스 정산": "Final assignments · Alliance Token and Piece rewards",
  "잔디 깔기 종료": "Lay the Grass ends",
};

function ruleHeading(title) {
  if (!en) return title;
  if (title.startsWith("‘선택 5’의 5는")) return "Minigame 3 · Lay the Grass";
  if (Object.hasOwn(ruleHeadings, title)) return ruleHeadings[title];
  if (phaseNames[grassPhases[title]]) return phaseNames[grassPhases[title]];
  const [name, details, rounds] = title.split(" · ");
  const count = details?.match(/^(?:참가자 )?(\d+)(?:명|인 경기), 총 (\d+)라운드$/);
  if (count) return `${gameTitle(name)} · ${count[1]} players, ${count[2]} rounds`;
  if (name === "보석 암시장") {
    const players = details?.match(/^참가자 (\d+)명$/)?.[1];
    const total = rounds?.match(/^(\d+)라운드$/)?.[1];
    if (players && total) return `${gameTitle(name)} · ${players} players, ${total} rounds`;
  }
  if (name === "러시안 룰렛") return "Russian Roulette · A deduction game for six players";
  if (name === "돼지 저금통") return "Piggy Bank · A memory game for four players";
  return gameTitle(title);
}

function negotiationTopic({choice, topic, translatedTopic}) {
  if (!en) return topic;
  const topics = {
    2: "Discuss who should play in a team of three and who should go solo. All three teammates must submit the same team.",
    4: "Discuss whether nine players will vote for the public benefit. Compare that with the five Victory Points a vote for personal benefit gives you.",
    9: "Discuss whether the group can contribute eight Pieces, how much each player can afford, and who benefits if only one player is eliminated.",
  };
  return translatedTopic ?? topics[choice] ?? topic;
}

function localizedRules(content) {
  const [heading, ...lines] = ruleText(content).split("\n");
  const title = ruleHeading(heading);
  if (!lines.length) return title;
  const summary = rulesSummary(heading, lines.join("\n"));
  return summary ? [title, summary, "Original rules (Korean)", lines.join("\n")].join("\n\n") :
    [title, "Original rules (Korean)", lines.join("\n")].join("\n\n");
}

function record(event, step) {
  const {msg_type: type, content, data} = event;
  const displayData = eventFields(event, data);
  const credit = type === "action" && data.phase === "credit" ? rouletteCreditAction(data.action) : null;
  const label = type === "decision_note" ? (data.phase === "gem_preparation" && data.turn && data.turns ?
    `${phaseNames.gem_preparation} · ${tr(`${data.turn} / ${data.turns}단계`, `Step ${data.turn} of ${data.turns}`)}` : decisionNoteLabel(data.phase)) :
    type === "inspection" ? (event.visible_to === "all" ? tr("공개 조사", "Public inspection") : tr("비공개 조사", "Private inspection")) :
      (type === "action" && actions[data.phase]) || labels[type] || type;
  const text = {
    rules: () => en ? localizedRules(content) : content.startsWith("러시안 룰렛 ·") ? ruleText(content)
      .replace("조사와 이동", "조사와 회전").replace(/([12])칸 이동/g, "$1칸 회전")
      .replace("공동 기금과 교환", "조작").replace("공동 기금에 비공개로 낼", "조작에 비공개로 쓸")
      .replace("기금을 6 이상으로 만든", "조작에 쓴 크레딧을 6개 이상으로 만든")
      .replace("기금은 초과분까지", "조작에 쓴 크레딧은 초과분까지").replace("납부 금액", "사용한 크레딧 수") : ruleText(content),
    action: () => {
      if (credit) return credit.text;
      if (data.phase.startsWith("pig_")) return pigActionText(data.phase, data.action);
      if (["gem_bid", "gem_auction_agreement", "gem_peek", "gem_swap"].includes(data.phase)) return gemActionText(data.phase, data.action);
      if (["gem_talk", "gem_opening_talk", "gem_auction_talk", "gem_after_auction_talk"].includes(data.phase)) {
        const action = parse(data.action);
        if (action?.type === "pass") return tr("패스", "Pass");
        if (data.phase === "gem_talk" && action?.type === "swap_now") return tr("대화 종료 · 교환 진행", "End discussion and proceed to swap");
        if (action?.type === "peek") return tr(`${gemSlotLabel(action.slot)} 카드 확인`, `Inspect ${gemSlotLabel(action.slot)}`);
      }
      if (data.phase === "market_turn") {
        const action = parse(data.action);
        const label = marketActions[action.type];
        const choice = action.choice;
        const choiceLabel = !en || !choice ? choice :
          choice === "현금" ? "Cash" : choice.startsWith("단서 ") ? `Clue: ${stockLabel(choice.slice(3))}` :
          action.type === "secret" ? stockLabel(choice) : choiceOptionLabel(choice);
        return [label, choiceLabel, action.type !== "trade" && action.orders?.length ? tr("주문 동시 제출", "Order also submitted") : null].filter(Boolean).join(" · ");
      }
      if (["rectangles", "rectangle_challenge"].includes(data.phase) && data.action !== "패스") {
        const [first, count] = data.action.trim().split(/\s+/);
        return count === undefined ? tr(`${first}개`, `${first} rectangles`) :
          tr(`${first}초 · ${count}개`, `${first}s · ${count} rectangles`);
      }
      if (en && data.action === "패스") return "Pass";
      if (en && data.action === "현금") return "Cash";
      if (en && data.phase === "submit") {
        const [weight, color] = data.action.split(" ");
        return `Weight ${weight} · ${chipColorLabel(color)}`;
      }
      if (data.phase !== "cubes") {
        const actionLabel = chipColorLabel(choiceOptionLabel(data.action));
        return actionLabel === data.action ? displayData.action : actionLabel;
      }
      const [first, count] = data.action.trim().split(/\s+/);
      return count === undefined ? tr(`${first}개`, `${first} cubes`) :
        tr(`${count}개 · 추가 대기 ${first}초`, `${count} cubes · ${first}s extra wait`);
    },
    invalid_action: () => displayData.action,
    decision_note: () => displayData.note,
    room_move: () => roomRecordText(content, type),
    room_invite: () => roomRecordText(content, type),
    room_invite_response: () => roomRecordText(content, type),
    grass_rules: () => en ? localizedRules(content) : content,
    grass_phase: () => ruleHeading(data),
    grass_tile: () => tr(content, `Tile ${content}`),
    grass_bonus: () => grassBonusText(content),
    choice_request: () => en ? localizedRules(content) : content,
    preview: () => en ? localizedRules(content) : content,
    relationship_update: () => [checkpointLabel(data.checkpoint, displayData.checkpoint), ...Object.entries(displayData.ratings).map(([name, rating]) =>
      tr(`${name} · 친밀도 ${rating.affinity} · 신뢰도 ${rating.trust} · ${rating.reason}`,
        `${name} · Affinity ${rating.affinity} · Trust ${rating.trust} · ${rating.reason}`))].join("\n"),
    cube_puzzle: () => tr("큐브 세기 문제 공개", "Cube Counting puzzle revealed"),
    cube_answer: () => [data.guess == null ? "" : tr(`${data.guess}개`, `${data.guess} cubes`),
      data.correct ? tr("정답", "Correct") : tr("오답", "Incorrect"),
      tr(`가상 시각 ${data.time}초`, `Simulated time ${data.time}s`)].filter(Boolean).join(" · "),
    buzz: () => {
      const clock = data.clock === "response" ? tr("응답 ", "Response ") : data.clock === "scripted" ? tr("가상 ", "Simulated ") : "";
      const result = data.correct ? tr("정답", "Correct") : tr("오답", "Incorrect");
      const time = number.format(data.time);
      return tr(`${data.player} · ${clock}${time}초 · ${data.answer}개 · ${result}`,
        `${data.player} · ${clock}${time}s · ${data.answer} rectangles · ${result}`);
    },
    hints: () => Object.entries(displayData).map(([stock, hint]) =>
      `${stockLabel(stock)} · ${Array.isArray(hint) ? hint.join(" · ") : hint}`).join("\n"),
    negotiation_start: () => negotiationTopic({...data, translatedTopic: event.translation?.fields?.topic}),
    negotiation_round: () => tr(`선택 ${data.choice} · ${data.round}턴`, `Choice ${data.choice} · Turn ${data.round}`),
    negotiation_end: () => data.reason === "all_submitted" ?
      tr(`선택 ${data.choice} 전원 제출 완료`, `Choice ${data.choice} · All players submitted`) :
      data.reason === "limit" ? tr(`선택 ${data.choice} 미제출 참가자 제출 시작`, `Choice ${data.choice} · Remaining players may submit`) :
        tr(`선택 ${data.choice} 제출 시작`, `Choice ${data.choice} · Submissions open`),
    choice_progress: () => tr(`선택 ${data.choice} · ${data.submitted} / ${data.total}명 제출`,
      `Choice ${data.choice} · ${data.submitted} of ${data.total} submitted`),
    rectangle_result: () => tr(`승리 ${data.winners.length}팀 · 패배 ${data.losers.length}팀`,
      `Teams that won: ${data.winners.length} · Teams that lost: ${data.losers.length}`),
    poker_mode: () => en ? `${choiceOptionLabel(data.mode)} · ${data.nomination_votes} nomination votes` : readable(data),
    poker_cards: () => data.phase === "memorize" ?
      tr(`암기 카드 ${data.display.length}장 · ${data.players.join(" vs ")}`, `Memorize ${data.display.length} cards · ${data.players.join(" vs ")}`) :
      tr(`공유 카드 ${formatPokerCards(data.community)}`, `Community cards ${formatPokerCards(data.community)}`),
    poker_result: () => formatPokerCards(readable(data)),
    round: () => leaderLabel(data.round, data.leader),
    market: () => tr(`${data.round}라운드 시세 갱신`, `Stock prices updated for round ${data.round}`),
    market_tick: () => tr(`${data.round}라운드 · ${data.minute} / ${data.minutes}분 차`,
      `Round ${data.round} · Minute ${data.minute} of ${data.minutes}`),
    trade_fill: () => [...data.orders.map(([stock, quantity]) => quantity > 0
      ? tr(`${stock}번 ${quantity}주 매수`, `Bought ${shares(quantity)} of stock ${stock}`)
      : tr(`${stock}번 ${Math.abs(quantity)}주 매도`, `Sold ${shares(Math.abs(quantity))} of stock ${stock}`)),
    tr(`잔액 ${won(data.cash)}`, `Balance ${won(data.cash)}`)].join(" · "),
    placement: () => tr(`${data.player} · ${data.color} · 무게 ${data.weight} · 벌점 ${data.penalty}`,
      `${data.player} · ${chipColorLabel(data.color)} · Weight ${data.weight} · Penalty ${data.penalty}`),
    colors: () => Object.entries(data).map(([player, color]) => `${player} ${chipColorLabel(color)}`).join(" · "),
    grass_placement: () => tr(
      `${data.tile}번 · ${data.placement ? "배치 성공" : "배치 실패"} · ${scoreText(data.points)}점`,
      `Tile ${data.tile} · ${data.placement ? "Placed" : "Not placed"} · ${scoreText(data.points)} points`),
    inspection: () => `${data.player} · ` + Object.entries(data.slots).map(([slot, marked]) =>
      tr(`${slot}번 ${marked ? "표식" : "빈 칸"}`, `Slot ${slot} ${marked ? "marked" : "empty"}`)).join(" · "),
    shift: () => tr(`${data.player} · ${data.amount}칸 회전 · 1번 칸 ${data.slot_1}`,
      `${data.player} · Rotated ${data.amount} ${data.amount === 1 ? "slot" : "slots"} · Slot 1 ${data.slot_1}`),
    swap: () => tr(`${data.slots.join("번 ↔ ")}번`, `Slot ${data.slots.join(" ↔ Slot ")}`),
    private_action: () => tr(content, "A private action was taken."),
    match_result: () => tr(`탈락 ${data.eliminated.join(", ")}`, `Eliminated: ${data.eliminated.join(", ")}`),
    match_interrupted: () => tr(content, "The replay shows events up to the interruption."),
  }[type];
  const actor = ["inspection", "shift", "swap", "pass"].includes(type) ? data.player :
    type === "trade_fill" ? event.visible_to[0] : event.agent_name;
  const fallback = text ? text() : pigEventText(type, data) ?? gemEventText(type, data) ?? (typeof data === "string" ? content : readable(displayData));
  return {...event, agent_name: actor, step, label, creditCost: credit?.cost,
    text: type === "grass_phase" && fallback !== content ? fallback : eventText(event, fallback)};
}

function matchState(events, match, frame, perspective, isMarket, isGemExchange) {
  const state = {feed: [], stacks: {}, penalties: {}, rounds: 0};
  const sceneSteps = [];
  let grassNotes = 0;
  for (let index = 0; index < frame; index++) {
    const event = events[index];
    const {msg_type: type, data} = event;
    if (match.board) {
      if (type === "negotiation_start") state.negotiation = {
        ...data, round: 1, translatedTopic: event.translation?.fields?.topic,
      };
      if (type === "negotiation_round") state.negotiation.round = data.round;
      if (type === "negotiation_end") state.negotiation = null;
      if (type === "grass_rules") state.grassPhase = "before_choice";
      if (type === "choice_request") state.grassPhase = "choice_five";
      if (type === "grass_phase" && grassPhases[data]) {
        state.grassPhase = grassPhases[data];
        grassNotes = 0;
      }
      if (type === "pre_poker_ranking") state.grassPhase = null;
      const phase = state.negotiation ? `choice_${state.negotiation.choice}_negotiation` : state.grassPhase;
      sceneSteps.push({phase, step: index + 1, events: [event],
        round: state.negotiation?.round ?? Math.floor(grassNotes / match.players.length) + 1});
      if (type === "discussion_note" && !state.negotiation) grassNotes++;
    } else if (isMarket || isGemExchange) {
      sceneSteps.push({phase: isGemExchange ? "gem_talk" : "market_turn", step: index + 1, events: [event]});
    }
    // Older logs saved the boards with the result. Rebuild each public reveal at its first recorded phase marker.
    if (state.pokerMode && (type === "action" || type === "decision_note") &&
        ["memorize", "memory_poker"].includes(data.phase) && state.pokerPhase !== data.phase) {
      state.choice = null;
      state.pokerPhase = data.phase;
      const next = events.slice(index + 1).find((row) => ["poker_cards", "poker_result"].includes(row.msg_type));
      state.pokerCards = null;
      if (next?.msg_type === "poker_result" && next.visible_to === "all") {
        state.pokerCards = data.phase === "memorize" ? {display: next.data.display} : {community: next.data.community};
        state.pokerPair ??= Object.keys(next.data.picks);
      }
    }
    if (perspective !== "operator" && event.visible_to !== "all" && !event.visible_to.includes(perspective)) continue;
    state.feed.push({...record(event, index + 1), round: state.rounds});
    if (isGemExchange) applyGemEvent(state, type, data, event);
    if (type.startsWith("pig_") || (type === "action" && ["pig_doubt", "pig_challenge"].includes(data.phase))) {
      applyPigEvent(state, type, data, state.feed.at(-1));
    }
    if (type === "match_result") {
      state.pigDoubtCue = null;
      state.pigChallengeCue = null;
    }
    switch (type) {
      case "rules": {
        if (!match.board) break;
        const [title, ...lines] = ruleText(data).split("\n");
        const choice = title.match(/^선택 (\d+) ·/)?.[1] ?? (title.startsWith("미니게임 4 ·") ? "10" : null);
        if (choice === "3" && !state.rectangleResult && state.teams && state.rectangleStandings) {
          const winners = state.teams.filter((team) => state.rectangleStandings[team.join(" / ")] === 2);
          state.rectangleResult = {winners, losers: state.teams.filter((team) => !winners.includes(team))};
        }
        if (choice || /^(양자택일 ·|미니게임 1 ·|최종 배정 ·)/.test(title)) {
          state.choice = {number: choice, title, rules: lines.join("\n"),
            translatedRules: event.translation?.text?.split("\n").slice(1).join("\n")};
          state.choiceProgress = null;
          state.showRectangleResult = false;
        }
        break;
      }
      case "round":
        state.rounds = data.round;
        state.leader = data.leader;
        if (data.stacks) {
          state.stacks = {...data.stacks};
          state.penalties = {...data.penalties};
          state.placement = null;
        }
        break;
      case "placement":
        state.stacks[data.color] = data.stack;
        state.penalties[data.player] += data.penalty;
        state.placement = data;
        break;
      case "hints": state.marketHints = eventFields(event, data); break;
      case "market": {
        state.market = data;
        state.marketTick = null;
        state.marketFills = new Map();
        state.marketAccounts ??= new Map(match.players
          .filter((player) => perspective === "operator" || perspective === player)
          .map((player) => [player, {cash: marketStartingCash, holdings: Object.keys(data.stocks).map(() => 0)}]));
        break;
      }
      case "market_tick": state.marketTick = data; break;
      case "trade_fill": {
        const player = state.feed.at(-1).agent_name;
        const orders = state.marketFills.get(player)?.orders ?? [];
        state.marketFills.set(player, {...data, orders: orders.concat(data.orders)});
        const account = state.marketAccounts.get(player);
        if (account) {
          account.cash = data.cash;
          if (data.holdings) {
            account.holdings = data.holdings.slice();
          } else {
            for (const [stock, quantity] of data.orders) account.holdings[stock - 1] += quantity;
          }
        }
        break;
      }
      case "seats": state.seats = data.clockwise; state.first = data.slot_1; break;
      case "shift": state.first = data.slot_1; state.shift = state.feed.at(-1); break;
      case "inspection":
        state.inspection = {...data, round: state.rounds, first: state.first, public: event.visible_to === "all"};
        break;
      case "scoreboard": state.scores = data; break;
      case "priority": state.priority = data.order; state.cubeAnswer = data.answer; break;
      case "cube_puzzle":
        state.choice = null;
        state.puzzle = {kind: "cubes", images: data.images ?? (data.image ? [data.image] : []), board: data.heights};
        state.cubeSolvers = new Set();
        state.lastCubeAnswer = null;
        break;
      case "cube_answer":
        if (data.correct) state.cubeSolvers?.add(data.player);
        state.lastCubeAnswer = state.feed.at(-1);
        break;
      case "rectangle_puzzle": {
        const kind = data.phase === "rectangle_challenge" ? "challenge" : "rectangles";
        const round = state.puzzle?.kind === kind ? state.puzzle.round + 1 : 1;
        state.choice = null;
        state.puzzle = {kind, round, board: data.board, target: data.target};
        break;
      }
      case "buzz": if (state.puzzle) state.puzzle.buzz = state.feed.at(-1); break;
      case "rectangle_answer": if (state.puzzle) state.puzzle.answer = data; break;
      case "challenge_result":
        if (state.puzzle?.kind === "challenge") state.puzzle.challenge = data;
        break;
      case "choice_progress": state.choiceProgress = data; break;
      case "teams": state.teams = data.teams; break;
      case "rectangle_standings": state.rectangleStandings = data; break;
      case "rectangle_result": state.puzzle = null; state.rectangleResult = data; state.showRectangleResult = true; break;
      case "representatives": state.representatives = Object.keys(data); break;
      case "choice_request": {
        const [title, ...lines] = data.split("\n");
        state.choice = {number: "5", title, rules: lines.join("\n"),
          translatedRules: event.translation?.text && (lines.length ? event.translation.text.split("\n").slice(1).join("\n") : event.translation.text)};
        break;
      }
      case "grass_phase": {
        const choice = data.match(/^선택 ([678]) ·/)?.[1];
        if (choice) state.choice = {number: choice, title: data, rules: ""};
        if (state.grassPhase === "draft") state.grassStart = state.scores;
        if (state.grassPhase === "done" && state.grassStart) {
          state.grassScores = Object.fromEntries(match.players.map((name) => [name, state.scores[name] - state.grassStart[name]]));
        }
        if (["draft", "manhole", "tree", "place", "split", "done"].includes(state.grassPhase)) state.choice = null;
        break;
      }
      case "pre_poker_ranking": state.choice = null; state.puzzle = null; state.ranking = data.ranking; break;
      case "poker_mode": state.pokerMode = data.mode; break;
      case "poker_cards":
        state.choice = null;
        state.pokerPhase = data.phase;
        state.pokerCards = data;
        if (data.players) state.pokerPair = data.players;
        break;
      case "action":
      case "decision_note":
        if (type === "action" && state.marketAccounts?.has(event.agent_name) && exchangedPieceForCash(data)) {
          state.marketAccounts.get(event.agent_name).cash += marketPieceCash;
        }
        if (state.pokerMode && data.phase === "nominate") {
          state.choice = null;
          state.pokerPhase = "nominate";
          if (type === "action") state.pokerPair = [event.agent_name, data.action];
        }
        if (type === "action" && data.phase === "memory_poker") {
          state.pokerPicks ??= new Map();
          state.pokerPicks.set(event.agent_name, data.action);
        }
        break;
      case "poker_result":
        state.choice = null;
        state.poker = data;
        state.pokerRound = (state.pokerRound ?? 0) + 1;
        state.pokerPhase = null;
        state.pokerPair = null;
        state.pokerCards = null;
        state.pokerPicks = null;
        break;
      case "poker_ranking": state.ranking = data.ranking; break;
      case "match_result": state.result = data; break;
    }
  }
  if (match.board || isMarket || isGemExchange) {
    const scores = match.board ? Object.fromEntries(match.players.map((name) => [name, 0])) : {};
    state.scene = snapshot({scores, steps: sceneSteps}, sceneSteps.length, perspective);
    if (isGemExchange) state.scene.scores = state.gemScores ?? {};
    const roomLabels = new Map(state.scene.feed.filter((event) => event.msg_type === "room")
      .map(({step, label}) => [step, label]));
    for (const event of state.feed) {
      if (event.msg_type === "room" && roomLabels.has(event.step)) event.label = roomLabels.get(event.step);
    }
  }
  return state;
}

function ChoiceScreen({choice, state, result}) {
  const options = optionsByChoice[Number(choice.number) - 1];
  const progress = state.choiceProgress?.choice === Number(choice.number) ? state.choiceProgress : null;
  const translatedRules = en && choice.translatedRules;
  const summary = en && !translatedRules && rulesSummary(choice.title, choice.rules);
  const {negotiation} = state;
  const submissionTurn = choice.number === "2" && negotiation?.choice === 2 ? negotiation.submission_opens_on : null;
  return <div className="choice-screen">
    <h2>{ruleHeading(choice.title)}</h2>
    {negotiation && <div className="negotiation-topic">
      <strong>{tr(`협상 ${negotiation.round} / ${negotiation.rounds}턴`,
        `Negotiation · Turn ${negotiation.round} of ${negotiation.rounds}`)}</strong>
      <p>{negotiationTopic(negotiation)}</p>
      {submissionTurn && <p>{negotiation.round < submissionTurn ?
        tr(`협상만 진행합니다. ${submissionTurn}턴부터 선택을 제출할 수 있어요.`,
          `Negotiation only. Submissions open on turn ${submissionTurn}.`) :
        tr("이제 개인·팀 선택을 제출할 수 있어요.", "Players can now submit their solo or team choices.")}</p>}
    </div>}
    {progress && <p className="choice-result">{tr(`${progress.submitted} / ${progress.total}명 제출`, `${progress.submitted} of ${progress.total} submitted`)}</p>}
    {result ? <ChoiceDetails result={result} options={options} /> : options && <>
      {!state.negotiation && !progress && <p className="choice-result">
        {choice.number === "5" && state.grassPhase === "before_choice" ? tr("선택 전 협상", "Negotiation before the choice") : tr("선택 결과 대기 중", "Waiting for the choice results")}
      </p>}
      <ChoiceColumns options={options} />
    </>}
    {(translatedRules || summary) && <p className="choice-rules">{translatedRules || summary}</p>}
    {choice.rules && (en || (choice.number && result) ? <details className="stage-details">
      <summary>{tr("게임 규칙", "Original rules (Korean)")}</summary><p className="choice-rules" lang="ko">{choice.rules}</p>
    </details> : <p className="choice-rules">{choice.rules}</p>)}
  </div>;
}

function PokerScreen({state, view}) {
  const {pokerMode, pokerRound, pokerPhase, pokerPair, pokerPicks, ranking} = state;
  const poker = pokerPhase ? null : state.poker;
  const {display, community} = poker ?? state.pokerCards ?? {};
  const contestants = Object.keys(poker?.picks ?? {});
  const winner = poker && duelWinner(poker, ...contestants);
  const picked = new Set(Object.values(poker?.picks ?? {}).flatMap((pair) => pair.split(/\s+/)));
  const selectingPlayers = pokerPair ?? Array.from(pokerPicks?.keys() ?? []);
  return <div className="poker-screen">
    <h2>{gameTitle("기억 포커")}{pokerMode && tr(` · ${pokerMode} 방식`, ` · ${choiceOptionLabel(pokerMode)} format`)}</h2>
    {!poker && <p className="choice-result">{pokerPhase ? tr(`${(pokerRound ?? 0) + 1}번째 대결 · ${pokerPhases[pokerPhase]}`,
      `Duel ${(pokerRound ?? 0) + 1} · ${pokerPhases[pokerPhase]}`) : tr("대결 준비 중", "Preparing the duel")}
      {pokerPair && ` · ${pokerPair.join(" vs ")}`}</p>}
    {poker && <p className="choice-result">{tr(`${pokerRound}번째 대결`, `Duel ${pokerRound}`)} · {contestants.join(" vs ")}
      {winner === null ? tr(" · 무승부", " · Draw") : winner && tr(` · ${winner} 승리`, ` · ${winner} wins`)}</p>}
    {display && <div className="poker-cards" aria-label={tr("카드 위치", "Card positions")}>{display.map((card, index) => {
      const position = cardPositions[index];
      return <PokerCard key={position} card={card} position={position} picked={picked.has(position)} />;
    })}</div>}
    <CommunityCards community={community} />
    {pokerPhase === "memory_poker" && selectingPlayers.length > 0 && <Table caption={tr("카드 선택 현황", "Card selections")}
      headers={[tr("참가자", "Player"), tr("선택 위치", "Selected positions")]} rows={selectingPlayers.map((name) => {
        const positions = pokerPicks?.get(name);
        const pending = view === "operator" || view === name ? tr("제출 대기", "Awaiting submission") : tr("공개 대기", "Awaiting reveal");
        return [name, positions ? positions.split(/\s+/).join(" · ") : pending];
      })} />}
    {poker && <Table caption={tr("대결 결과", "Duel results")} headers={[tr("참가자", "Player"), tr("선택 위치", "Selected positions"), tr("족보", "Poker hand"), tr("결과", "Result"), tr("현재 순위", "Current rankings")]}
      rows={contestants.map((name) => {
        const outcome = winner === undefined ? "–" : winner === null ? tr("무승부", "Draw") :
          name === winner ? <strong className="poker-winner">{tr("승리", "Win")}</strong> : tr("패배", "Loss");
        return [name, poker.picks[name], handNames[poker.hands?.[name]?.[0]] ?? "–", outcome,
          ranking?.includes(name) ? tr(`${ranking.indexOf(name) + 1}위`, `#${ranking.indexOf(name) + 1}`) : "–"];
      })} />}
    {ranking && <details className="stage-details">
      <summary>{tr("기억 포커 현재 순위", "Memory Poker rankings")}</summary><RankTable caption={tr("기억 포커 현재 순위", "Memory Poker rankings")} order={ranking} />
    </details>}
  </div>;
}

function RankTable({caption, order}) {
  return <Table caption={caption} headers={[tr("순위", "Rank"), tr("참가자", "Player")]} rows={order.map((name, index) => [index + 1, name])} />;
}

function RectangleResults({state}) {
  const {winners, losers} = state.rectangleResult;
  const rows = (teams, result) => teams.map((team) => [team.join(" · "), result,
    state.rectangleStandings?.[team.join(" / ")] ?? "–",
    state.representatives?.find((name) => team.includes(name)) ?? "–"]);
  return <Table caption={tr("네모 세기 결과", "Rectangle Counting results")} headers={[tr("참가자", "Player"), tr("결과", "Result"), tr("정답", "Correct"), tr("팀 대표", "Team representative")]}
    rows={[...rows(winners, tr("승리", "Win")), ...rows(losers, tr("패배", "Loss"))]} />;
}

function ChoiceColumns({options = [], tally}) {
  const unit = tally?.groups[0]?.unit;
  const groups = new Map(options.map((option) => [option, {option, count: 0, unit, names: []}]));
  for (const group of tally?.groups ?? []) groups.set(group.option, group);
  if (!groups.size) return null;
  return <div className="stage-choice-tally">
    {tally && <h3>{tally.title}</h3>}
    <div className="stage-choice-columns">{Array.from(groups.values(), ({option, count, unit, names}) =>
      <section className="stage-choice-column" key={option} aria-label={choiceOptionLabel(option)}>
        <h4>{choiceOptionLabel(option)}{unit && <> <span>{choiceCountLabel(count, unit)}</span></>}</h4>
        {names.length > 0 && <ul>{names.map((name) => <li key={name}>{name}</li>)}</ul>}
        {count > names.length && <p>{tr("비공개", "Private")} {choiceCountLabel(count - names.length, unit)}</p>}
      </section>)}</div>
  </div>;
}

function ChoiceDetails({result, options}) {
  const compact = options !== undefined;
  const {label, title, summary, tallies, tables} = result;
  const ballots = compact && tables.find(({kind}) => kind === "published" || kind === "submitted");
  return <>
    {!compact && <h3>{label} · {title}</h3>}
    {summary && <p className={compact ? "choice-result" : "muted"}>{summary}</p>}
    {compact && !tallies.length && <ChoiceColumns options={options} />}
    {tallies.map((tally, index) => compact ? <ChoiceColumns key={tally.title} tally={tally}
      options={index === 0 && tally.groups[0]?.unit !== "팀" ? options : undefined} /> : <div className="choice-tally" key={tally.title}>
      <h4>{tally.title}</h4>
      <ul>{tally.groups.map(({option, count, unit, names}) => <li key={option}>
        <strong>{choiceOptionLabel(option)}</strong> <span>{choiceCountLabel(count, unit)}</span>
        {names.length > 0 && <p>{names.join(", ")}</p>}
      </li>)}</ul>
    </div>)}
    {tables.filter((table) => table !== ballots).map((table) => <Table key={table.caption} {...table} />)}
  </>;
}

function ResultPicker({results, label, emptyText}) {
  const [selection, setSelection] = useState("");
  const current = results.find((result) => result.value === selection) ?? results.at(-1);
  if (!current) return <p className="empty">{emptyText}</p>;
  return <>
    <div className="match-info-games" role="group" aria-label={label}>
      {results.map(({value, label}) => <Button key={value} label={label} size="sm"
        variant={value === current.value ? "secondary" : "ghost"} aria-pressed={value === current.value}
        onClick={() => setSelection(value)} />)}
    </div>
    <div className="match-info-scroll" tabIndex={0} role="region" aria-label={tr(`${current.label} 결과`, `${current.label} results`)}>{current.content}</div>
  </>;
}

function MatchInformation({state, replay, choices}) {
  const [tab, setTab] = useState("scores");
  const {match: {players}, selected, choosePlayer, seek} = replay;
  const priority = Object.fromEntries((state.priority ?? []).map((name, index) => [name, index]));
  const standings = (scores) => <Standings scores={scores} priority={priority} players={players} selected={selected} onPlayer={choosePlayer} />;
  const pokerRanking = state.result?.ranking ?? ((state.pokerMode || state.poker) && state.ranking);
  const grassStarted = state.grassScores || Object.keys(state.scene.tiles).length > 0 || state.scene.attempts > 0;
  const results = [
    state.priority && {value: "cubes", label: tr("큐브 세기", "Cube Counting"), content: <RankTable caption={tr("큐브 세기 우선권", "Cube Counting priority")} order={state.priority} />},
    state.rectangleResult && {value: "rectangles", label: tr("네모 세기", "Rectangle Counting"), content: <RectangleResults state={state} />},
    grassStarted && {value: "grass", label: tr("잔디 깔기", "Lay the Grass"),
      content: <GrassResults state={state} priority={priority} players={players} onSeek={seek} />},
    pokerRanking && {value: "poker", label: gameTitle("기억 포커"),
      content: <PokerResults state={state} order={pokerRanking} onSeek={seek} />},
  ].filter(Boolean);
  return <aside className="caption match-info" aria-label={tr("게임 정보", "Game information")}>
    <TabList role="tablist" aria-label={tr("게임 정보 종류", "Game information tabs")} size="sm" value={tab} onChange={setTab} hasDivider>
      <Tab id="info-scores" value="scores" label={tr("승점 순위", "Victory Point standings")} panelId="info-scores-panel" />
      <Tab id="info-results" value="results" label={tr("미니게임 결과", "Minigame results")} panelId="info-results-panel" />
      <Tab id="info-choices" value="choices" label={tr("선택 결과", "Choice results")} panelId="info-choices-panel" />
    </TabList>
    <div id="info-scores-panel" role="tabpanel" aria-labelledby="info-scores" hidden={tab !== "scores"}>
      {state.pokerMode && <p className="muted">{tr("기억 포커 전 누적 승점", "Victory Points before Memory Poker")}</p>}
      <div className="match-info-scroll" tabIndex={0} role="region" aria-label={tr("승점 순위 목록", "Victory Point standings")}>{standings(state.scene.scores)}</div>
    </div>
    <div id="info-results-panel" role="tabpanel" aria-labelledby="info-results" hidden={tab !== "results"}>
      <ResultPicker results={results} label={tr("미니게임 선택", "Select a minigame")} emptyText={tr("이 시점에 공개된 미니게임 결과가 없어요.", "No minigame results have been revealed yet.")} />
    </div>
    <div id="info-choices-panel" role="tabpanel" aria-labelledby="info-choices" hidden={tab !== "choices"}>
      <ResultPicker results={choices.map((result) => ({...result, content: <ChoiceDetails result={result} />}))}
        label={tr("선택 번호", "Choice number")} emptyText={tr("이 시점에 볼 수 있는 선택 결과가 없어요.", "No choice results are visible at this point.")} />
    </div>
  </aside>;
}

function canSeeCredits(view, player) {
  return view === "operator" || (view !== "public" && view === player);
}

function Result({result, players, view}) {
  const showCredits = (value, name) => canSeeCredits(view, name) ? value : tr("비공개", "Private");
  const metric = result.assets ? [tr("최종 자산", "Final assets"), result.assets, won] :
    result.penalties ? [tr("벌점", "Penalty points"), result.penalties, String] : result.scores ? [tr("승점", "Victory Points"), result.scores, scoreText] :
      [tr("남은 크레딧", "Credits remaining"), result.credits, showCredits];
  const names = result.ranking ?? result.seats ?? players;
  return <Table caption={tr("최종 결과", "Final results")} headers={[tr("참가자", "Player"), metric[0], tr("피스", "Pieces"), tr("결과", "Result")]}
    rows={names.map((name, index) => [result.ranking ? `${index + 1}. ${name}` : name, metric[2](metric[1][name], name),
      result.pieces?.[name] ?? "–", result.eliminated.includes(name) ? tr("탈락", "Eliminated") : result.living?.includes(name) ? tr("생활동", "Living Quarters") :
        result.prison?.includes(name) ? tr("감옥동", "Prison Wing") : tr("생존", "Survived")])} />;
}

function CubeViews({images}) {
  const [view, setView] = useState(0);
  const [rotating, setRotating] = useState(() => !window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  const count = images.length;

  useEffect(() => {
    if (!rotating || count < 2) return;
    const timer = window.setInterval(() => setView((current) => (current + 1) % count), 1800);
    return () => window.clearInterval(timer);
  }, [rotating, count]);

  const turn = (step) => {
    setRotating(false);
    setView((current) => (current + step + count) % count);
  };

  return <>
    {images.map((image, index) => <img key={index} hidden={index !== view}
      src={`data:image/png;base64,${image}`} width="700" height="544" alt={tr(`쌓인 큐브 · 시점 ${index + 1}`, `Stacked cubes · View ${index + 1}`)} />)}
    {count > 1 && <div className="cube-view-controls" role="group" aria-label={tr("큐브 시점 조작", "Cube view controls")}>
      <Button size="sm" variant="ghost" label={tr("이전 시점", "Previous view")} onClick={() => turn(-1)} />
      <span>{tr("시점", "View")} {view + 1} / {count}</span>
      <Button size="sm" variant="ghost" label={tr("다음 시점", "Next view")} onClick={() => turn(1)} />
      <Button size="sm" variant="secondary" label={rotating ? tr("회전 멈춤", "Stop rotation") : tr("자동 회전", "Auto-rotate")}
        onClick={() => setRotating(!rotating)} />
    </div>}
  </>;
}

function PuzzleBoard({board, label}) {
  return <table className="puzzle-board" aria-label={label}><tbody>{board.map((row, index) => <tr key={index}>
    {row.map((value, col) => <td key={col}>{value || "·"}</td>)}
  </tr>)}</tbody></table>;
}

function CubeStage({state, replay}) {
  const {puzzle, priority, cubeAnswer, cubeSolvers, lastCubeAnswer} = state;
  const status = priority ? (cubeAnswer == null ? tr("우선권 확정", "Priority finalized") : tr(`정답 ${cubeAnswer}개 · 우선권 확정`, `Answer: ${cubeAnswer} cubes · Priority finalized`)) :
    replay.view === "operator" ? tr(`정답자 ${cubeSolvers.size} / ${replay.match.players.length - 1}명`,
      `Correct answers: ${cubeSolvers.size} / ${replay.match.players.length - 1}`) : tr("정답 집계 중", "Collecting answers");
  return <div className="match-puzzle">
    <h2>{tr("큐브 세기", "Cube Counting")}</h2>
    <p className="choice-result">{status}</p>
    {!priority && lastCubeAnswer && <p className="choice-result">
      {tr("최근 제출", "Latest submission")} {lastCubeAnswer.data.player} · {lastCubeAnswer.text}
    </p>}
    <div className="puzzle-columns">
      <div>{puzzle.images.length ? <CubeViews key={replay.id} images={puzzle.images} /> :
        <PuzzleBoard board={puzzle.board} label={tr("큐브 세기", "Cube Counting")} />}</div>
      {priority && <RankTable caption={tr("큐브 세기 우선권", "Cube Counting priority")} order={priority} />}
    </div>
  </div>;
}

function RectangleStage({state}) {
  const {puzzle, teams, rectangleStandings} = state;
  const {kind, round, target, board, buzz, answer, challenge} = puzzle;
  const label = kind === "challenge" ? tr("네모 세기 추가 대결", "Rectangle Counting tiebreaker") : tr("네모 세기", "Rectangle Counting");
  const rows = kind === "rectangles" ? (teams ?? []).map((team) => {
    const correct = rectangleStandings?.[team.join(" / ")] ?? 0;
    return [team.join(" · "), correct, correct >= 2 ? tr("승리 확정", "Won") : "–"];
  }).sort((left, right) => right[1] - left[1]) : [];
  return <div className="match-puzzle">
    <h2>{label} · {tr(`${round}번째 문제`, `Puzzle ${round}`)}</h2>
    <p className="choice-result">{tr("목표 합", "Target sum")} {target}{!buzz && !answer && tr(" · 버저 대기 중", " · Waiting for the buzzer")}</p>
    {buzz && <p className="choice-result">{tr("최근 버저", "Latest buzzer")} {buzz.text}</p>}
    {answer && <p className="choice-result">{tr(`정답 ${answer.answer}개`, `Answer: ${answer.answer} rectangles`)} · {answer.winner ? tr(`정답 팀 ${answer.winner.join(" · ")}`, `Correct team: ${answer.winner.join(" · ")}`) : tr("정답자 없음", "No correct answers")}</p>}
    {challenge && <p className="choice-result">{tr(`추가 대결 우승 ${challenge.winner} · 피스 3개 획득`, `Tiebreaker winner: ${challenge.winner} · 3 Pieces awarded`)}</p>}
    <div className="puzzle-columns">
      <PuzzleBoard board={board} label={label} />
      {rows.length > 0 && <Table caption={tr("누적 정답", "Total correct answers")} headers={[tr("참가자", "Player"), tr("정답 수", "Correct answers"), tr("결과", "Result")]} rows={rows} />}
    </div>
  </div>;
}

function MarketStage({state, view}) {
  const {stocks, round} = state.market;
  const symbols = Object.keys(stocks);
  const tick = state.marketTick;
  const live = view === "operator" && tick;
  const volume = symbols.map(() => ({bought: 0, sold: 0}));
  if (live) {
    for (const {orders} of state.marketFills.values()) {
      for (const [stock, quantity] of orders) volume[stock - 1][quantity > 0 ? "bought" : "sold"] += Math.abs(quantity);
    }
  }
  return <>
    {tick && <p className="choice-result">{tr(`가상 거래 시간 ${tick.minute} / ${tick.minutes}분 차`, `Simulated trading time · Minute ${tick.minute} of ${tick.minutes}`)}</p>}
    <Table caption={`${tr(`${round}라운드 시세`, `Round ${round} prices`)} · ${live ? tr("이번 체결", "Current fills") : tr("직전 거래량", "Previous volume")}`} headers={[tr("종목", "Stock"), tr("가격", "Price"), tr("보유", "Holdings"), tr("매수", "Buy"), tr("매도", "Sell")]}
      rows={symbols.map((name, index) => {
        const stock = stocks[name];
        if (!stock) return [stockLabel(name), tr("시크릿", "Secret"), "–", "–", "–"];
        const {bought, sold} = live ? volume[index] : stock;
        return [stockLabel(name), won(stock.price), live ? stock.held + bought - sold : stock.held, bought, sold];
      })} />
  </>;
}

function MarketTrades({state, selected}) {
  const {market, marketFills} = state;
  const fill = marketFills?.get(selected);
  if (fill) {
    const symbols = Object.keys(market.stocks);
    const holdings = fill.holdings?.flatMap((quantity, index) => quantity ? [`${stockLabel(symbols[index])} ${en ? shares(quantity) : quantity + "주"}`] : []);
    return <div className="market-account">
      <Table caption={`${selected} · ${tr(`${market.round}라운드 체결 · 잔액`, `Round ${market.round} fills · Balance`)} ${won(fill.cash)}`}
        headers={[tr("종목", "Stock"), tr("구분", "Side"), tr("수량", "Quantity")]} rows={fill.orders.map(([stock, quantity], index) => [
          `${index + 1}. ${stockLabel(symbols[stock - 1])}`, quantity > 0 ? tr("매수", "Buy") : tr("매도", "Sell"), Math.abs(quantity),
        ])} />
      {holdings && <p className="choice-result">{tr("보유 주식", "Shares held")} · {holdings.join(" · ") || tr("없음", "None")}</p>}
    </div>;
  }
  if (selected || !marketFills?.size) return <p className="empty">{tr("이 시점에 볼 수 있는 체결 내역이 없어요.", "No trade fills are visible at this point.")}</p>;
  return <Table caption={tr(`${market.round}라운드 체결 현황`, `Round ${market.round} fills`)} headers={[tr("참가자", "Player"), tr("매수", "Buy"), tr("매도", "Sell")]}
    rows={Array.from(marketFills, ([player, {orders}]) => {
      let bought = 0;
      let sold = 0;
      for (const [, quantity] of orders) {
        if (quantity > 0) bought += quantity;
        else sold -= quantity;
      }
      return [player, shares(bought), shares(sold)];
    })}
  />;
}

function MarketAccounts({state, selected}) {
  const {market, result, marketAccounts} = state;
  const entries = Array.from(marketAccounts ?? []).filter(([player]) => !selected || selected === player);
  if (!entries.length) return <p className="empty">{tr("이 시점에 볼 수 있는 보유 자산이 없어요.", "No holdings are visible at this point.")}</p>;

  const symbols = Object.keys(market.stocks);
  return <Table caption={result ? tr("최종 보유 자산", "Final holdings") : tr(`${market.round}라운드 보유 자산`, `Round ${market.round} holdings`)}
    headers={[tr("참가자", "Player"), tr("현금", "Cash"), tr("보유 주식", "Shares held"), tr("평가 자산", "Portfolio value")]}
    rows={entries.map(([player, {cash, holdings}]) => {
      const positions = symbols.flatMap((stock, index) => holdings[index] ? [{stock, quantity: holdings[index]}] : []);
      const hasSecretPrice = positions.some(({stock}) => market.stocks[stock] == null);
      const assets = result?.assets?.[player] ?? (hasSecretPrice ? null :
        positions.reduce((total, {stock, quantity}) => total + market.stocks[stock].price * quantity, cash));
      return [player, won(cash), positions.length ? <ul className="market-holdings">
        {positions.map(({stock, quantity}) => <li key={stock}>{stockLabel(stock)} {shares(quantity)}</li>)}
      </ul> : tr("없음", "None"), assets == null ? tr("시크릿", "Secret") : won(assets)];
    })} />;
}

function MarketInformation({state, replay}) {
  const [tab, setTab] = useState("ranking");
  const {selected, choosePlayer} = replay;
  const {market, result, marketHints} = state;
  const ranking = result?.ranking ?? market?.ranking;
  const assets = result?.assets ?? market?.assets;
  return <aside className="caption match-info" aria-label={tr("거래소 게임 정보", "Stock exchange information")}>
    <TabList role="tablist" aria-label={tr("거래소 정보 종류", "Stock exchange information tabs")} size="sm" value={tab} onChange={setTab} hasDivider>
      <Tab id="market-ranking" value="ranking" label={tr("자산 순위", "Asset rankings")} panelId="market-ranking-panel" />
      <Tab id="market-accounts" value="accounts" label={tr("보유 자산", "Holdings")} panelId="market-accounts-panel" />
      <Tab id="market-trades" value="trades" label={tr("체결 내역", "Trade fills")} panelId="market-trades-panel" />
      <Tab id="market-hints" value="hints" label={tr("공개 단서", "Public clues")} panelId="market-hints-panel" />
    </TabList>
    <div id="market-ranking-panel" className="match-info-scroll" role="tabpanel" aria-labelledby="market-ranking"
      hidden={tab !== "ranking"} tabIndex={0}>
      {ranking ? <Table caption={result ? tr("최종 자산 순위", "Final asset rankings") : tr(`${market.round}라운드 개장 순위`, `Round ${market.round} opening rankings`)}
        headers={[tr("순위", "Rank"), tr("참가자", "Player"), tr("자산", "Assets")]} rows={ranking.map((player, index) => [index + 1,
          <button type="button" className="result-link" aria-pressed={player === selected}
            onClick={() => choosePlayer(player)}>{player}</button>,
          assets ? won(assets[player]) : tr("비공개", "Private"),
        ])} /> : <p className="empty">{tr("이 시점에 공개된 순위가 없어요.", "No rankings have been revealed yet.")}</p>}
    </div>
    <div id="market-accounts-panel" className="match-info-scroll" role="tabpanel" aria-labelledby="market-accounts"
      hidden={tab !== "accounts"} tabIndex={0}>
      <MarketAccounts state={state} selected={selected} />
    </div>
    <div id="market-trades-panel" className="match-info-scroll" role="tabpanel" aria-labelledby="market-trades"
      hidden={tab !== "trades"} tabIndex={0}>
      <MarketTrades state={state} selected={selected} />
    </div>
    <div id="market-hints-panel" className="match-info-scroll" role="tabpanel" aria-labelledby="market-hints"
      hidden={tab !== "hints"} tabIndex={0}>
      {marketHints ? <>
        {Object.values(marketHints).some((hint) => typeof hint === "string" && hint.includes("▧")) &&
          <p className="muted"><span className="market-hint-next">▧</span> {tr("다음 공개 글자 · □ 가려진 글자", "Next character to be revealed · □ Hidden character")}</p>}
        <dl className="market-hints">{Object.entries(marketHints).map(([stock, hint]) => <div key={stock}>
          <dt>{stockLabel(stock)}</dt><dd lang={/[가-힣]/.test(hint) ? "ko" : undefined}>{typeof hint === "string" ? hint.split(/(▧+)/).map((part, index) =>
            part.startsWith("▧") ? <span key={index} className="market-hint-next">{part}</span> : part) : hint.join(" · ")}</dd>
        </div>)}</dl>
      </> : <p className="empty">{tr("이 시점에 공개된 단서가 없어요.", "No clues have been revealed yet.")}</p>}
    </div>
  </aside>;
}

function RoulettePlayers({state, replay}) {
  const [chosenRound, chooseRound] = useState("");
  const {seats, rounds, feed, result} = state;
  const {selected, view, seek} = replay;
  if (!seats) return <p className="empty">{tr("자리 배정 후 참가자 기록을 볼 수 있어요.", "Player records will appear after seats are assigned.")}</p>;
  const roundChoice = Number(chosenRound) <= rounds ? chosenRound : "";
  const round = Number(roundChoice) || rounds;
  const accounts = new Map(seats.filter((player) => !selected || player === selected).map((player) =>
    [player, {credits: canSeeCredits(view, player) ? rouletteStartingCredits : null, actions: new Map()}]));

  for (const event of feed) {
    const {agent_name: player, msg_type: type, data, step, creditCost} = event;
    const account = accounts.get(player);
    if (!account) continue;
    if (account.credits != null && creditCost != null) account.credits -= creditCost;
    if (!selected && event.round !== round) continue;

    let action;
    if (type === "action" && data.phase === "credit") action = event.text;
    else if (type === "pass") action = event.label;
    else if (type === "swap") action = tr(`칸 교환 · ${event.text}`, `Slots swapped · ${event.text}`);
    else if (account.credits == null) {
      if (type === "private_action") action = event.label;
      if (type === "shift") action = rouletteCreditAction(`회전 ${data.amount}`).text;
      if (type === "inspection" && event.visible_to === "all") {
        const slots = Object.keys(data.slots);
        const first = slots.includes("1") && slots.includes(String(seats.length)) ? seats.length : slots[0];
        action = rouletteCreditAction(`공개 ${first}`).text;
      }
    }
    if (action) {
      const actions = account.actions.get(event.round) ?? [];
      actions.push({step, action, credits: account.credits});
      account.actions.set(event.round, actions);
    }
  }

  const remaining = (player, credits) =>
    credits == null ? tr("비공개", "Private") : (result?.credits?.[player] ?? credits);
  const actionLinks = (actions = []) => actions.length ? actions.map(({step, action}) => <div key={step}>
    <button type="button" className="result-link" onClick={() => seek(step)}>{action}</button>
  </div>) : "–";

  const selectedAccount = accounts.get(selected);
  if (selectedAccount) {
    let balance = selectedAccount.credits == null ? null : rouletteStartingCredits;
    const rows = Array.from({length: rounds}, (_, index) => {
      const roundNumber = index + 1;
      const actions = selectedAccount.actions.get(roundNumber);
      balance = actions?.at(-1)?.credits ?? balance;
      const roundBalance = roundNumber === rounds ? remaining(selected, balance) : (balance ?? tr("비공개", "Private"));
      return [roundLabel(roundNumber), actionLinks(actions), roundBalance];
    });
    return <>
      <p className="choice-result">{tr("현재 남은 크레딧", "Current credits")} · {remaining(selected, selectedAccount.credits)}</p>
      {rounds > 0 && <Table caption={tr(`${selected} 라운드별 기록`, `${selected} · Round-by-round record`)} headers={[tr("라운드", "Round"), tr("행동", "Action"), tr("남은 크레딧", "Credits remaining")]} rows={rows} />}
    </>;
  }

  return <>
    {rounds > 0 && <Selector label={tr("행동을 볼 라운드", "Select a round")} isLabelHidden size="sm"
      value={roundChoice} onChange={chooseRound}
      options={[{value: "", label: tr(`현재 라운드 · ${rounds}라운드`, `Current round · Round ${rounds}`)},
        ...Array.from({length: rounds}, (_, index) => ({value: String(index + 1), label: roundLabel(index + 1)}))]} />}
    <Table caption={round ? tr(`${round}라운드 참가자 기록`, `Round ${round} player records`) : tr("시작 크레딧", "Starting credits")}
      headers={[tr("참가자", "Player"), tr("남은 크레딧", "Credits remaining"), tr("행동", "Action")]}
      rows={Array.from(accounts, ([player, {credits, actions}]) => [
        player,
        remaining(player, credits),
        actionLinks(actions.get(round)),
      ])} />
  </>;
}

function RouletteInformation({state, replay}) {
  const [tab, setTab] = useState("actions");
  const {selected, choosePlayer, seek, match} = replay;
  const events = state.feed.filter((event) => {
    if (tab === "observations") {
      return rouletteObservations.has(event.msg_type) &&
        (!selected || event.visible_to === "all" || event.visible_to.includes(selected));
    }
    if (selected && event.agent_name !== selected) return false;
    if (event.msg_type === "action") return event.data.phase === "credit";
    if (event.msg_type === "private_action") return replay.view !== "operator" && event.agent_name !== replay.view;
    return rouletteObservations.has(event.msg_type) || event.msg_type === "pass";
  }).map((event) => ({...event, label: event.round ? `${roundLabel(event.round)} · ${event.label}` : event.label}));

  return <aside className="caption match-info" aria-label={tr("러시안 룰렛 게임 정보", "Russian Roulette information")}>
    <TabList role="tablist" aria-label={tr("러시안 룰렛 정보 종류", "Russian Roulette information tabs")} size="sm" value={tab} onChange={setTab} hasDivider>
      <Tab id="roulette-actions" value="actions" label={tr("행동 기록", "Action log")} panelId="roulette-info-panel" />
      <Tab id="roulette-observations" value="observations" label={tr("확인한 정보", "Observations")} panelId="roulette-info-panel" />
      <Tab id="roulette-players" value="players" label={tr("참가자별 기록", "Player records")} panelId="roulette-info-panel" />
    </TabList>
    <Selector label={tr("기록을 볼 참가자", "Select a player")} isLabelHidden value={selected} size="sm" onChange={choosePlayer}
      options={[{value: "", label: tr("전체 참가자", "All players")}, ...(state.seats ?? match.players).map((player) => ({value: player, label: player}))]} />
    <div id="roulette-info-panel" className="match-info-scroll" role="tabpanel" aria-labelledby={`roulette-${tab}`} tabIndex={0}>
      {tab === "players" ? <RoulettePlayers state={state} replay={replay} /> :
        <MatchFeed events={events} onSeek={seek} unit="번째 기록"
          emptyText={tab === "observations" ? tr("이 시점에 확인한 정보가 없어요.", "No observations are available at this point.") : tr("이 시점에 볼 수 있는 행동이 없어요.", "No actions are visible at this point.")} />}
    </div>
  </aside>;
}

function Stage({state, replay, choiceResult, gemExchange}) {
  const {match} = replay;
  if (match.game.endsWith(" · 돼지 저금통")) return <PiggyStage state={state} players={match.players} selected={replay.selected} onChoose={replay.choosePlayer} />;
  if (gemExchange) return <GemStage state={state} players={match.players} selected={replay.selected} onChoose={replay.choosePlayer} />;
  if (state.result) return <Result result={state.result} players={match.players} view={replay.view} />;
  if (state.market) return <MarketStage state={state} view={replay.view} />;
  if (Object.keys(state.stacks).length) {
    const {placement} = state;
    return <>
      {placement && <p className="choice-result">{tr(
        `${placement.player} · ${placement.color}에 ${placement.weight} 배치`,
        `${placement.player} · Placed weight ${placement.weight} on ${chipColorLabel(placement.color).toLowerCase()}`)}
        {placement.penalty > 0 && tr(` · 벌점 +${placement.penalty}`, ` · Penalty +${placement.penalty}`)}</p>}
      <div className="match-columns">
        <Table caption={leaderLabel(state.rounds, state.leader)} headers={[tr("받침대", "Platform"), tr("무게 (아래부터)", "Weights (bottom first)"), tr("합계", "Total")]}
          rows={Object.entries(state.stacks).map(([color, stack]) => [chipColorLabel(color), stack.join(" · ") || tr("빈 받침대", "Empty platform"),
            stack.reduce((sum, weight) => sum + weight, 0)])} />
        <Table caption={tr("누적 벌점", "Total penalties")} headers={[tr("참가자", "Player"), tr("벌점", "Penalty points")]} rows={Object.entries(state.penalties)} />
      </div>
    </>;
  }
  if (state.seats) {
    const offset = state.seats.indexOf(state.first);
    const {inspection} = state;
    const inspectionOffset = state.seats.indexOf(inspection?.first ?? state.first);
    return <>
      <div className="roulette-stage-columns">
        <section aria-label={tr("최근 조사 결과", "Latest inspection results")}>
          <h2>{tr("최근 조사", "Latest inspection")}</h2>
          <p className="muted inspection-caption">{inspection ? <>
            {roundLabel(inspection.round)} · {inspection.player} · {inspection.public ? tr("공개", "Public") : tr("비공개", "Private")}
            <br />{tr("조사 당시 1번 칸", "Slot 1 at the time")} · {inspection.first}
          </> : tr("볼 수 있는 조사 기록이 없어요.", "No inspection records are visible.")}</p>
          <RouletteInspection slots={inspection?.slots} offset={inspectionOffset} />
          <RouletteInspectionLegend />
        </section>
        <Table caption={state.rounds ? leaderLabel(state.rounds, state.leader) : tr("자리 배정", "Seating")}
          headers={[tr("현재 칸", "Current slot"), tr("참가자", "Player")]} rows={state.seats.map((_, index) => [
            tr(`${index + 1}번`, `Slot ${index + 1}`), state.seats[(offset + index) % state.seats.length],
          ])} />
      </div>
      {state.shift && <p className="choice-result">{tr("최근 회전", "Latest rotation")} · {state.shift.text}</p>}
    </>;
  }
  if (state.choice) return <ChoiceScreen key={state.choice.number ?? state.choice.title} choice={state.choice} state={state} result={choiceResult} />;
  if (state.grassPhase) return <div className="grass-stage">
    <h2>{phaseNames[state.grassPhase] ?? tr("잔디 깔기", "Lay the Grass")}</h2>
    <BoardScene board={match.board} state={state.scene} players={match.players} selected={replay.selected} />
    {state.grassPhase === "draft" && <p className="choice-result">{tr("선택 완료", "Tiles selected")} {Object.keys(state.scene.tiles).length} / {match.players.length}{tr("명", "")}</p>}
  </div>;
  if (state.pokerMode || state.poker) return <PokerScreen state={state} view={replay.view} />;
  if (state.showRectangleResult) return <RectangleResults state={state} />;
  if (state.puzzle?.kind === "cubes") return <CubeStage state={state} replay={replay} />;
  if (state.puzzle) return <RectangleStage state={state} />;
  if (state.ranking) return <RankTable caption={tr("현재 순위", "Current rankings")} order={state.ranking} />;
  return <p className="match-roster">{match.players.join(" · ")}</p>;
}

function modelSettings(model, effort, provider) {
  const settings = effort ? `${model} ${effort} effort` : model;
  return provider ? `${provider} · ${settings}` : settings;
}

function modelLabel({provider, model, effort, model_players: modelPlayers, model_overrides: modelOverrides, players}) {
  const prefix = tr("사용 모델:", "Model:");
  if (!model || modelPlayers?.length === 0) return `${prefix} ${tr("스크립트", "Scripted")}`;
  const overrides = modelOverrides ?? {};
  const defaultProvider = Object.values(overrides).some((config) => config.provider) ? provider : undefined;
  const defaults = modelSettings(model, effort, defaultProvider);
  if (!modelPlayers) return `${prefix} ${defaults}`;

  const enabled = new Set(modelPlayers);
  const groups = new Map();
  const scripted = [];
  for (const player of players) {
    if (!enabled.has(player)) {
      scripted.push(player);
      continue;
    }
    const override = Object.hasOwn(overrides, player) ? overrides[player] : undefined;
    const settings = override ? modelSettings(override.model, override.effort, override.provider ?? defaultProvider) : defaults;
    if (!groups.has(settings)) groups.set(settings, []);
    groups.get(settings).push(player);
  }

  const playerCount = (count) => tr(`${count}명`, `${count} ${count === 1 ? "player" : "players"}`);
  const label = (settings, members) => {
    const scope = members.length === players.length ? tr("모든 참가자", "all players") : playerCount(members.length);
    return `${settings} (${scope} · ${members.join(", ")})`;
  };
  const lines = [...groups].map(([settings, members]) => label(settings, members));
  if (scripted.length) lines.push(label(tr("스크립트", "Scripted"), scripted));
  return `${prefix} ${lines.join("\n")}`;
}

export function MatchReplay({replay, transport, caseName}) {
  const {caseRecord, match, frame, view, selected} = replay;
  const indexInCase = caseRecord?.matches.findIndex(({id}) => id === replay.id) ?? -1;
  const nextMatch = indexInCase >= 0 ? caseRecord.matches[indexInCase + 1] : match.next_match;
  const [subtitle, name] = match.game.split(" · ");
  const isMarket = name === "미스터리 거래소";
  const isRoulette = name === "러시안 룰렛";
  const isHeavy13 = name === "무거운 13";
  const isGemExchange = name === "보석 암시장";
  const isPiggyBank = name === "돼지 저금통";
  const [tab, setTab] = useState("all");
  const events = useMemo(() => match.steps.map(({events: [event]}) => {
    const data = parse(event.content);
    if (event.msg_type === "relationship_update") {
      data.checkpoint = legacyRelationshipCheckpoints.get(data.checkpoint) ?? data.checkpoint;
    }
    return {...event, data};
  }), [match]);
  const state = useMemo(() => matchState(events, match, frame, view, isMarket, isGemExchange), [events, match, frame, view, isMarket, isGemExchange]);
  const {gemCards} = state;
  const drawGemMap = useCallback((canvas) => drawGemSet(canvas, gemCards), [gemCards]);
  const choices = useMemo(() => match.board ? choiceResults(state, match.players, view) : [], [state, match, view]);
  const choiceResult = choices.find(({value}) => value === state.choice?.number);
  const chapterOptions = events.flatMap(({msg_type: type, data}, index) => {
    const label = (type === "rules" ? (index === 0 ? tr("게임 규칙", "Game rules") : ruleHeading(ruleText(data.split("\n", 1)[0]))) : chapters[type]) ??
      (["round", "market", "gem_round"].includes(type) ? roundLabel(data.round) : null) ??
      (type === "gem_preparation" ? gemEventText(type, data) : null) ??
      (type === "gem_discussion" ? gemDiscussionLabel(data) : null) ??
      (type === "gem_auction_round" && data.manito_reveal ? tr("마니또 확인 · 피스 경매", "Manito reveal and Piece auction") : null) ??
      (type === "gem_strategy" ? gemEventText(type, data) : null) ??
      (["pig_setup", "pig_turn", "pig_doubt", "pig_challenge", "pig_reset"].includes(type) ? pigEventText(type, data) : null) ??
      (type === "negotiation_start" ? (data.choice === 2 ? tr("선택 2 팀 구성 협상", "Choice 2 team negotiations") : tr(`선택 ${data.choice} 전 협상`, `Negotiation before Choice ${data.choice}`)) : null) ??
      (type === "grass_phase" && grassPhases[data] === "place" ? tr("잔디 타일 배치", "Grass tile placement") : null);
    return label ? [{value: String(index + 1), label}] : [];
  });
  const views = [{value: "operator", label: tr("운영자 · 전체 기록", "Operator · Full log")}, {value: "public", label: tr("공개 시점", "Public view")},
    ...match.players.map((name) => ({value: name, label: tr(`${name} 시점`, `${name}’s view`)}))];
  const Venue = matchVenues[name];
  const dialogueTabs = state.scene || isRoulette || isPiggyBank;
  const ranking = isMarket || isGemExchange ? state.result?.ranking ?? state.market?.ranking : null;
  const playerDetails = ranking && new Map(ranking.map((player, index) => [player, {
    rank: tr(`${index + 1}위`, `Rank ${index + 1}`), status: state.result?.eliminated.includes(player) ? "탈락" :
      state.result?.living.includes(player) ? "생활동" : state.result?.prison.includes(player) ? "감옥동" : null,
  }]));
  const participantState = state.scene ? {
    ...state.scene, feed: state.feed,
    participantRecords: state.scene.participantRecords.filter((event) => event.msg_type === "grass_choices"),
  } : state;
  const dialogue = state.feed.filter((event) => dialogueTypes.has(event.msg_type));
  const strategies = state.feed.filter(isStrategy);
  const visible = tab === "talk" ? dialogue : tab === "strategy" ? strategies : state.feed;
  const latest = state.feed.at(-1);
  const records = selected ? <Participant key={selected} state={participantState} player={selected} players={match.players}
    onSeek={replay.seek} onClose={() => { replay.choosePlayer(""); setTab(dialogueTabs ? "talk" : "all"); }} unit="번째 기록" /> :
    <section className="caption match-log" aria-label={tr("플레이 기록", "Play log")}>
      {dialogueTabs && <TabList role="tablist" aria-label={tr("기록 종류", "Log categories")} size="sm" value={tab} onChange={setTab} hasDivider>
        <Tab id="match-all" value="all" label={tr("플레이 기록", "Play log")} panelId="match-log-panel" />
        <Tab id="match-talk" value="talk" label={tr("대화", "Conversation")} panelId="match-log-panel" />
        <Tab id="match-strategy" value="strategy" label={tr("전략 메모", "Strategy notes")} panelId="match-log-panel" />
      </TabList>}
      <div id="match-log-panel" role={dialogueTabs ? "tabpanel" : undefined} aria-labelledby={dialogueTabs ? `match-${tab}` : undefined}>
        <MatchFeed events={visible.slice(tab === "all" ? -25 : -160)} onSeek={replay.seek} unit="번째 기록"
          emptyText={tab === "strategy" ? tr("이 시점에 볼 수 있는 전략 메모가 없어요.", "No strategy notes are visible at this point.") : undefined} />
      </div>
    </section>;
  return <main className={match.board ? "shell replay full-match either-or" : "shell replay full-match"}>
    <div className="heading"><div className="match-heading-title">
      {caseName && <p className="match-case-name">{caseName}</p>}
      <div className="match-title"><h1>{gameTitle(name || subtitle)}</h1>{name && <span>{gameTitle(subtitle)}</span>}</div>
    </div>
      <div className="match-heading-details">
        {nextMatch ?
          <Button label={`${tr("다음 매치 보기", "Watch next match")} · ${gameTitle(nextMatch.game)}`}
            href={runHref(nextMatch.id, caseRecord?.id)} variant="primary" size="sm" /> :
          state.result && caseRecord && <p className="muted">{isPiggyBank ?
            tr("3일차까지 마쳤어요.", "End of Day 3.") : isGemExchange ?
            tr("3일차 메인 매치를 마쳤어요.", "End of Day 3 Main Match.") : caseRecord.matches.length === 4 ?
              tr("2일차까지 마쳤어요.", "End of Day 2.") : tr("이어지는 매치 기록이 아직 없어요.", "No follow-up match has been recorded yet.")}</p>}
        <p className="muted match-models">{modelLabel(match)}</p>
      </div>
    </div>
    <div className={match.board ? "either-or-stage" : isMarket || isGemExchange || Venue ? "venue-stage" : undefined}>
      {state.scene && <RoomScene state={state.scene} players={match.players} frame={frame} following={replay.mode === "follow"}
          row={latest?.step === frame ? {player: latest.agent_name} : undefined} selected={selected}
          onChoose={replay.choosePlayer} playerDetails={playerDetails} drawMap={isGemExchange ? drawGemMap : undefined}
          getPoint={isGemExchange ? gemSetPoint : undefined}
          label={isGemExchange ? tr("보석 암시장 메인홀", "Gem Black Market main hall") :
            isMarket ? tr("미스터리 거래소 메인홀", "Mystery Stock Exchange main hall") : tr("전체 세트장", "Full set")} />}
      {Venue && <Venue players={match.players} state={state} frame={frame} selected={selected} onChoose={replay.choosePlayer} />}
      <section className="match-state" aria-label={tr("현재 판세", "Current game state")}><Stage state={state} replay={replay} choiceResult={choiceResult} gemExchange={isGemExchange} /></section>
    </div>
    {transport}
    <div className="context">
      <div className="context-start">
        <strong>{frame ? state.feed.at(-1)?.label || tr("플레이 기록", "Play log") : tr("플레이 시작", "Match starts")}</strong>
        <Selector label={tr("구간 이동", "Jump to section")} isLabelHidden value="" size="sm"
          options={[{value: "", label: tr("구간 이동", "Jump to section")}, ...chapterOptions]} onChange={(value) => { if (value) replay.seek(Number(value)); }} />
      </div>
      <div className="context-end">
        {!state.scene && !isRoulette && !isPiggyBank && <Selector label={tr("참가자 기록", "Player records")} isLabelHidden value={selected} size="sm"
          options={[{value: "", label: tr("참가자 기록", "Player records")}, ...match.players.map((player) => ({value: player, label: player}))]}
          onChange={replay.choosePlayer} />}
        <Selector label={tr("관전 시점", "Viewpoint")} isLabelHidden value={view} size="sm" options={views} onChange={replay.chooseView} />
      </div>
    </div>
    {match.board || isMarket || isRoulette || isHeavy13 || isGemExchange || isPiggyBank ? <div className="match-details">
      {records}
      {isMarket && <MarketInformation key={replay.id} state={state} replay={replay} />}
      {isRoulette && <RouletteInformation key={replay.id} state={state} replay={replay} />}
      {isHeavy13 && <Heavy13Information key={replay.id} state={state} replay={replay} />}
      {isGemExchange && <GemInformation key={replay.id} state={state} replay={replay} />}
      {isPiggyBank && <PiggyInformation key={replay.id} state={state} replay={replay} />}
      {match.board && <MatchInformation key={replay.id} state={state} replay={replay} choices={choices} />}
    </div> : records}
  </main>;
}
