import React from "react";
import {tr} from "./locale.js";
import {scoreText} from "./replay.js";
import {Table} from "./records.jsx";

const gemNames = {
  diamond: tr("다이아몬드", "Diamond"), gold: tr("금", "Gold"),
  silver: tr("은", "Silver"), copper: tr("동", "Copper"), bomb: tr("폭탄", "Bomb"),
};
const marketSlots = ["buyer1", "buyer2", "buyer3", "trash"];

export function gemSlotLabel(slot) {
  if (slot === "trash") return tr("휴지통", "Trash");
  if (slot?.startsWith("buyer")) return tr(`구매자 ${slot.slice(5)}`, `Buyer ${slot.slice(5)}`);
  return slot;
}

export function gemCardLabel(card) {
  return card ? `${gemNames[card.kind]} ${card.value}` : tr("비공개", "Face down");
}

export function gemActionText(phase, action) {
  if (phase === "gem_bid") return action === "pass" ? tr("기존 입찰 유지", "Keep previous bid") : tr(`피스 ${action}개 입찰`, `Bid ${action} Pieces`);
  if (phase === "gem_auction_agreement") return tr(`선 플레이어로 ${action} 지명`, `Nominate ${action} to lead`);
  if (phase === "gem_peek") return action === "pass" ? tr("확인 보류", "Skip inspection") : gemSlotLabel(action);
  if (phase === "gem_swap") return tr(`${gemSlotLabel(action)} 카드와 교환`, `Swap with ${gemSlotLabel(action)}`);
}

export function gemEventText(type, data) {
  switch (type) {
    case "gem_setup": return tr(`참가자 ${data.base_order.length}명 · 카드 ${data.card_count}장 · ${data.rounds}라운드`,
      `${data.base_order.length} players · ${data.card_count} cards · ${data.rounds} rounds`);
    case "gem_manito": return tr(`내 점수가 곱해지는 상대 · ${data.beneficiary}`, `My points multiply ${data.beneficiary}’s score`);
    case "gem_auction_round": return tr(`경매 ${data.round}차 · ${data.bidders.join(" · ")}`, `Auction ${data.round} · ${data.bidders.join(" · ")}`);
    case "gem_auction": return tr(`선 ${data.leader} · 피스 ${data.bid}개`, `Leader ${data.leader} · ${data.bid} Pieces`);
    case "gem_round": return tr(`${data.round}라운드 · 선 ${data.leader}`, `Round ${data.round} · Leader ${data.leader}`);
    case "gem_turn": return tr(`${data.player} · ${data.pass === 1 ? "정순" : "역순"} 교환`,
      `${data.player} · ${data.pass === 1 ? "Forward" : "Reverse"} swap`);
    case "gem_card":
    case "gem_peek": return `${gemSlotLabel(data.slot)} · ${gemCardLabel(data.card)}`;
    case "gem_swap": return `${data.player} ↔ ${gemSlotLabel(data.target)}`;
    case "gem_bonus": return tr(`${data.player} · 폭탄 넘기기 ${scoreText(data.points)}점`, `${data.player} · Bomb passed ${scoreText(data.points)} VP`);
    case "gem_piece": return tr(`${data.player} · 피스 ${data.pieces}개`, `${data.player} · ${data.pieces} Pieces`);
    case "gem_reveal": return tr(`${data.round}라운드 카드·점수 공개 · 다음 선 ${data.next_leader}`,
      `Round ${data.round} cards and scores revealed · Next leader ${data.next_leader}`);
    case "gem_final": return tr("마니또 공개 · 누적 승점 × 마니또 승점", "Manitos revealed · Cumulative VP × manito VP");
  }
}

export function applyGemEvent(state, type, data, event) {
  switch (type) {
    case "gem_setup":
      state.gemSetup = data;
      state.gemPieces = {...data.pieces};
      state.gemScores = Object.fromEntries(data.base_order.map((name) => [name, 0]));
      state.gemCards = {};
      state.gemManitos = {};
      break;
    case "gem_manito": state.gemManitos[event.agent_name] = data.beneficiary; break;
    case "gem_auction_round": state.gemAuctionRound = data; break;
    case "gem_auction":
      state.gemAuction = data;
      state.gemPieces = {...data.pieces};
      break;
    case "gem_round":
      state.rounds = data.round;
      state.leader = data.leader;
      state.gemRound = data;
      state.gemCards = {};
      state.gemTurn = null;
      state.gemReveal = null;
      state.gemLastSwap = null;
      break;
    case "gem_turn": state.gemTurn = data; break;
    case "gem_card":
    case "gem_peek": state.gemCards[data.slot] = data.card; break;
    case "gem_swap": {
      const cards = state.gemCards;
      [cards[data.player], cards[data.target]] = [cards[data.target], cards[data.player]];
      state.gemLastSwap = data;
      break;
    }
    case "gem_bonus": state.gemScores = data.scores; break;
    case "gem_piece": state.gemPieces[data.player] = data.pieces; break;
    case "gem_reveal":
      state.gemCards = {...data.cards};
      state.gemScores = data.scores;
      state.gemPieces = {...data.pieces};
      state.gemReveal = data;
      break;
    case "gem_final":
      state.gemFinal = data;
      state.gemScores = data.scores;
      state.gemManitos = {...data.manitos};
      break;
  }
}

function GemCard({slot, card, active, selected, onChoose}) {
  const player = !marketSlots.includes(slot);
  const content = <>
    <span className="gem-card-owner">{gemSlotLabel(slot)}</span>
    <span className="gem-card-face" data-gem={card?.kind ?? "hidden"}>
      <span aria-hidden="true" className="gem-card-mark">{card?.kind === "bomb" ? "●" : card ? "◆" : "?"}</span>
      <strong>{card ? card.value : "–"}</strong>
      <span>{card ? gemNames[card.kind] : tr("비공개", "Face down")}</span>
    </span>
  </>;
  return player ? <button type="button" className={`gem-card${active ? " acting" : ""}`}
    aria-pressed={slot === selected} aria-label={`${slot} · ${gemCardLabel(card)}`} onClick={() => onChoose(slot)}>{content}</button> :
    <div className={`gem-card${slot === "trash" ? " gem-trash" : ""}`} aria-label={`${gemSlotLabel(slot)} · ${gemCardLabel(card)}`}>{content}</div>;
}

export function GemStage({state, players, selected, onChoose}) {
  const {gemSetup: setup, gemAuction: auction, gemRound: round, gemTurn: turn, gemReveal: reveal,
    gemCards: cards = {}, gemScores: scores = {}, gemPieces: pieces = {}, gemManitos: manitos = {}, gemFinal: final, result} = state;
  const order = round?.order ?? auction?.order ?? setup?.base_order ?? players;
  const incoming = Object.fromEntries(Object.entries(manitos).map(([source, beneficiary]) => [beneficiary, source]));
  if (result) {
    return <div className="gem-stage">
      <h2>{tr("최종 결과", "Final results")}</h2>
      <Table caption={tr("누적 승점 × 마니또 승점", "Cumulative VP × manito VP")}
        headers={tr(["참가자", "승점 계산", "최종 승점", "피스", "결과"], ["Player", "Score calculation", "Final VP", "Pieces", "Result"])}
        rows={result.ranking.map((name, index) => [
          `${index + 1}. ${name}`, incoming[name] ? `${scores[name]} × ${scores[incoming[name]]} (${incoming[name]})` : "–",
          result.final_scores?.[name] ?? final?.final_scores[name] ?? result.scores[name], result.pieces[name],
          result.eliminated.includes(name) ? tr("탈락", "Eliminated") : result.living.includes(name) ? tr("생활동", "Living Quarters") : tr("감옥동", "Prison Wing"),
        ])} />
    </div>;
  }
  return <div className="gem-stage">
    <h2>{round ? tr(`${round.round} / ${setup?.rounds ?? 3}라운드`, `Round ${round.round} of ${setup?.rounds ?? 3}`) : tr("선 플레이어 경매", "Auction for the lead")}</h2>
    <p className="muted gem-status">{reveal ? tr(`카드 공개 · 다음 선 ${reveal.next_leader}`, `Cards revealed · Next leader ${reveal.next_leader}`) :
      turn ? gemEventText("gem_turn", turn) : auction ? tr(`선 ${auction.leader}`, `Leader ${auction.leader}`) :
        state.gemAuctionRound ? gemEventText("gem_auction_round", state.gemAuctionRound) :
          tr("피스로 비공개 입찰", "Sealed bids using Pieces")}</p>
    {round && <>
      <div className="gem-market-cards" aria-label={tr("구매자와 휴지통 카드", "Buyer and trash cards")}>
        {marketSlots.map((slot) => <GemCard key={slot} slot={slot} card={cards[slot]} />)}
      </div>
      <div className="gem-player-cards" aria-label={tr("플레이 순서와 보유 카드", "Play order and player cards")}>
        {order.map((slot) => <GemCard key={slot} slot={slot} card={cards[slot]} active={!reveal && turn?.player === slot}
          selected={selected} onChoose={onChoose} />)}
      </div>
      {state.gemLastSwap && <p className="choice-result">{tr("최근 교환", "Last swap")} · {gemEventText("gem_swap", state.gemLastSwap)}</p>}
      <p className="choice-result">{tr("정순", "Forward")} {order.join(" → ")}<br />
        {tr("역순", "Reverse")} {order.toReversed().join(" → ")}</p>
    </>}
    {setup && <Table caption={tr("누적 승점과 피스", "Cumulative VP and Pieces")}
      headers={tr(["참가자", "카드 승점", "누적 승점", "피스"], ["Player", "Card VP", "Cumulative VP", "Pieces"])}
      rows={players.map((name) => [name, reveal ? scoreText(reveal.points[name]) : "–", scoreText(scores[name] ?? 0), pieces[name] ?? "–"])} />}
    {Object.keys(manitos).length > 0 && <details className="stage-details">
      <summary>{tr("볼 수 있는 마니또 관계", "Visible manito relationships")}</summary>
      <Table caption={tr("내 점수가 곱해지는 상대", "Whose score my points multiply")}
        headers={tr(["점수를 주는 참가자", "영향받는 참가자"], ["Score source", "Beneficiary"])}
        rows={Object.entries(manitos)} />
    </details>}
  </div>;
}
