import {tr} from "./locale.js";

export const bingoShapes = ["triangle", "circle", "star"];
export const bingoBoard = [["triangle", "circle", "triangle"], ["circle", "star", "circle"], ["star", "circle", "triangle"]];
export const shapeGlyph = (shape) => ({triangle: "△", circle: "○", star: "☆"})[shape] ?? "?";
export const shapeLabel = (shape) => ({triangle: tr("세모", "Triangle"), circle: tr("동그라미", "Circle"), star: tr("별", "Star")})[shape] ?? shape;
export const coinValue = (coins = {}) => Object.entries(coins).reduce((sum, [value, count]) => sum + Number(value) * count, 0);
export const priceLabel = (price, secret = false) => secret ? tr("시크릿", "Secret") : price == null ? tr("입찰 없음", "No bids") : tr(`${price}원`, `${price} won`);

export function bingoPhaseLabel(state) {
  if (state.result) return tr("매치 종료", "Match complete");
  if (state.bingoReveal) return tr("최종 빙고 공개", "Final bingo reveal");
  if (state.bingoDiscussion) {
    const {stage, turn, rounds} = state.bingoDiscussion;
    const label = stage === "opening" ? tr("게임 시작 전 대화", "Opening discussion") : stage === "before_bid" ? tr("입찰 전 대화", "Discussion before bidding") : tr("도형 선택 전 대화", "Discussion before shape selection");
    return label + (turn ? tr(` · ${turn} / ${rounds}턴`, ` · Turn ${turn} of ${rounds}`) : "");
  }
  return ({preparation: tr("비공개 전략 준비", "Private preparation"), shape: tr("도형 선택", "Shape selection"), bid: tr("비공개 입찰", "Sealed bidding"), strategy: tr("입찰 전 전략 정리", "Planning before bidding"), result: tr("낙찰가 발표", "Winning prices revealed")})[state.bingoPhase] ?? tr("게임 규칙", "Game rules");
}

export function applyBingoEvent(state, type, data, event = {}) {
  switch (type) {
    case "rules":
      if (typeof data === "string" && data.startsWith("경매 빙고")) state.bingoFreeSubmission = data.includes("\n\n6. 자유 제출\n");
      break;
    case "bingo_setup": state.bingoSetup = data; break;
    case "bingo_round":
      if (state.bingoRound !== data.round) state.bingoChoices = {};
      if (state.bingoRound !== data.round) state.bingoForfeits = [];
      state.bingoDealerVisits = [];
      state.bingoDealerPhase = `${data.round}:${data.phase}`;
      if (state.bingoFreeSubmission || state.bingoSubmission) state.bingoSubmission = {
        round: data.round, phase: data.phase, submitted: [], total: state.bingoSetup?.base_order.length ?? 8,
      };
      state.bingoRound = data.round;
      state.bingoPhase = data.phase;
      state.bingoDiscussion = null;
      break;
    case "bingo_submission":
      state.bingoSubmission = {round: data.round, phase: data.phase, submitted: data.submitted.slice(), total: data.total};
      if (data.phase === "bid" && event.visible_to === "all" && !state.bingoForfeits?.includes(data.player)) {
        state.bingoDealerVisits ??= [];
        state.bingoDealerVisits.push({player: data.player, round: data.round, step: event.step});
      }
      break;
    case "bingo_forfeit":
      state.bingoForfeits ??= [];
      state.bingoForfeits.push(data.player);
      break;
    case "bingo_preparation": state.bingoPhase = "preparation"; break;
    case "bingo_preparation_end": state.bingoPhase = null; break;
    case "bingo_discussion":
    case "bingo_discussion_round": state.bingoDiscussion = data; break;
    case "bingo_discussion_end": state.bingoDiscussion = null; break;
    case "bingo_strategy": state.bingoPhase = "strategy"; break;
    case "bingo_shapes":
      state.bingoRound = data.round;
      state.bingoChoices = {...data.choices};
      break;
    case "bingo_result":
      state.bingoPhase = "result";
      state.bingoDealerPhase = `${data.round}:result`;
      state.bingoDealerVisits = [];
      state.bingoSubmission = null;
      state.bingoResults ??= [];
      state.bingoResults.push(data);
      break;
    case "bingo_bank":
      state.bingoBanks ??= {};
      state.bingoBanks[event.agent_name] = data;
      break;
    case "bingo_reveal": state.bingoReveal = data; state.bingoDiscussion = null; state.bingoSubmission = null;
      state.bingoDealerVisits = []; state.bingoDealerPhase = "reveal"; break;
  }
}

export function parseBingoBid(action) {
  try {
    const bid = typeof action === "string" ? JSON.parse(action) : action;
    return bid && typeof bid === "object" && bid.coins && typeof bid.coins === "object" ? bid : null;
  } catch { return null; }
}

export function bingoEventText(type, data) {
  switch (type) {
    case "bingo_setup": return tr(`참가자 ${data.base_order.length}명 · 게스트 ${data.guest} · 7라운드`, `${data.base_order.length} players · Guest ${data.guest} · Seven rounds`);
    case "bingo_round": return tr(`${data.round}라운드 · ${data.phase === "shape" ? "도형 선택" : "비공개 입찰"}`, `Round ${data.round} · ${data.phase === "shape" ? "Shape selection" : "Sealed bidding"}`);
    case "bingo_submission": return tr(`${data.round}라운드 ${data.phase === "shape" ? "도형 선택" : "입찰"} 제출 · ${data.submitted.length} / ${data.total}명 · ${data.submitted.join(" · ")}`, `Round ${data.round} · ${data.phase === "shape" ? "Shape" : "Bid"} submissions: ${data.submitted.length} of ${data.total} · ${data.submitted.join(" · ")}`);
    case "bingo_shapes": return Object.entries(data.choices).map(([player, shape]) => `${player} ${shapeGlyph(shape)}`).join(" · ");
    case "bingo_result": return bingoShapes.map((shape) => `${shapeGlyph(shape)} ${priceLabel(data.prices[shape], data.secret.includes(shape))}`).join(" · ");
    case "bingo_bank": return tr(`비공개 · 잔여 코인 ${coinValue(data.coins)}원 · 피스 ${data.pieces}개`, `Private · ${coinValue(data.coins)} won in coins · ${data.pieces} Pieces`);
    case "bingo_forfeit": return tr(`${data.player} · 최소 1원 입찰 불가 · 자동 최하위`, `${data.player} · Unable to bid one won · Automatically last`);
    case "bingo_reveal": return tr(`획득 도형·빙고판 공개 · 본선 1위 ${data.ranking[0]}`, `Shapes and bingo cards revealed · Leading regular player: ${data.ranking[0]}`);
    case "bingo_preparation": return tr(`비공개 전략 준비 · ${data.turn} / ${data.turns}단계`, `Private preparation · Step ${data.turn} of ${data.turns}`);
    case "bingo_preparation_end": return tr("전략 준비 완료", "Preparation complete");
    case "bingo_strategy": return tr(`${data.round}라운드 입찰 전 전략 정리`, `Round ${data.round} · Private bidding plan`);
    case "bingo_discussion":
    case "bingo_discussion_round": return bingoPhaseLabel({bingoDiscussion: data});
    case "bingo_discussion_end": return tr("대화 종료", "Discussion complete");
  }
}

export function bingoActionText(phase, action) {
  if (phase === "bingo_shape") return `${shapeGlyph(action)} ${shapeLabel(action)}`;
  if (phase === "bingo_bid") {
    const bid = parseBingoBid(action);
    if (bid) return tr(`${coinValue(bid.coins)}원 입찰 · 피스 ${bid.pieces ?? 0}개 교환`, `Bid ${coinValue(bid.coins)} won · Exchange ${bid.pieces ?? 0} Pieces`);
  }
  return action;
}
