import React, {useState} from "react";
import {Selector} from "@astryxdesign/core/Selector";
import {Tab, TabList} from "@astryxdesign/core/TabList";
import {drawSet, setPoint, setWidth, setHeight} from "./floor.js";
import {tr} from "./locale.js";
import {Table} from "./records.jsx";
import {bingoBoard, bingoPhaseLabel, bingoShapes, coinValue, parseBingoBid, priceLabel, shapeGlyph, shapeLabel} from "./auction-bingo-state.js";
import "./auction-bingo.css";

export function bingoSetPoint(room, index, count) {
  return room ? setPoint(room, index) : [256 + (index - (count - 1) / 2) * 39, 252];
}

export function drawBingoSet(canvas, choices = {}) {
  drawSet(canvas);
  const c = canvas.getContext("2d");
  c.setTransform(canvas.width / setWidth, 0, 0, canvas.height / setHeight, 0, 0);
  const rect = (x, y, w, h, color) => { c.fillStyle = color; c.fillRect(x, y, w, h); };
  // The dealer booth occupies the central panel; the stairs and four rooms stay accessible.
  rect(209, 165, 94, 49, "#171825");
  rect(212, 168, 88, 42, "#43364f");
  rect(217, 172, 78, 31, "#1b2030");
  rect(209, 202, 94, 7, "#a58b62");
  rect(209, 209, 94, 3, "#584633");
  rect(244, 178, 24, 14, "#3f4654");
  rect(248, 181, 16, 9, "#b7a175");
  c.fillStyle = "#f1dca4";
  c.textAlign = "center";
  c.font = "bold 7px monospace";
  c.fillText(tr("비공개 딜러룸", "SEALED BID ROOM"), 256, 199);
  // Three freestanding ticket boxes sit on their own table in front of the cast.
  rect(153, 322, 207, 9, "#382e2c");
  rect(158, 329, 6, 12, "#92704c");
  rect(349, 329, 6, 12, "#92704c");
  rect(153, 319, 207, 3, "#b39365");
  const colors = {triangle: "#aa6750", circle: "#548d7b", star: "#bc9b50"};
  for (const [index, shape] of bingoShapes.entries()) {
    const x = 169 + index * 68;
    rect(x, 281, 40, 39, "#181d27");
    rect(x + 2, 283, 36, 35, colors[shape]);
    rect(x + 5, 285, 30, 3, "#e2cba2");
    rect(x + 10, 286, 20, 2, "#141925");
    c.fillStyle = "#fff0c9";
    c.font = "bold 19px monospace";
    c.fillText(shapeGlyph(shape), x + 20, 309);
    const count = Object.values(choices).filter((chosen) => chosen === shape).length;
    for (let ticket = 0; ticket < count; ticket++) rect(x + 7 + ticket * 4, 274 - ticket % 2 * 2, 3, 10, "#eee0bd");
  }
}

function BingoCard({board = bingoBoard, filled, label}) {
  return <div className="bingo-card" role="img" aria-label={label ?? tr("빙고판 · 세모 3개, 동그라미 4개, 별 2개", "Bingo card · Three triangles, four circles and two stars")}>
    {board.flatMap((row, y) => row.map((shape, x) => <span key={`${y}-${x}`} data-shape={shape}
      data-filled={filled ? Boolean(filled[y]?.[x]) : false}>{shapeGlyph(shape)}</span>))}
  </div>;
}

function statusText(state, player) {
  if (player === (state.bingoSetup?.guest ?? "G01")) return tr("게스트 · 생존 판정 제외", "Guest · Outside survival ranking");
  if (!state.result) return "";
  if (state.result.eliminated?.includes(player)) return tr("탈락", "Eliminated");
  if (state.result.living?.includes(player)) return tr("생활동", "Living Quarters");
  if (state.result.prison?.includes(player)) return tr("감옥동", "Prison Wing");
  return "";
}

export function BingoSubmission({progress, players, selected, onChoose}) {
  if (!progress) return null;
  const {phase, round, submitted, total} = progress;
  return <section className="bingo-submission" data-phase={phase} aria-label={tr("현재 단계 제출 현황", "Current phase submissions")}>
    <strong>{tr(`${round}라운드 ${phase === "shape" ? "도형 선택" : "입찰"} 제출`, `Round ${round} · ${phase === "shape" ? "Shape" : "Bid"} submissions`)} <span>{submitted.length} / {total}</span></strong>
    <div>{players.map((player) => <button type="button" key={player} onClick={() => onChoose(player)} aria-pressed={selected === player} data-submitted={submitted.includes(player)}>
      {player} <small>{submitted.includes(player) ? tr("완료", "Done") : tr("대기", "Pending")}</small>
    </button>)}</div>
    <p>{tr("제출은 확정되며 수정할 수 없습니다. 선택한 도형과 입찰 금액은 표시하지 않습니다.", "Submitted decisions are final. Chosen shapes and bid amounts are not shown here.")}</p>
  </section>;
}

export function BingoStage({state, replay}) {
  const {selected, choosePlayer, match: {players}, view} = replay;
  const round = state.bingoRound ?? 0;
  const reveal = state.bingoReveal;
  const guest = state.bingoSetup?.guest ?? "G01";
  const board = state.bingoSetup?.board ?? bingoBoard;
  const chosen = selected || (players.includes(view) ? view : reveal?.ranking[0]);
  const own = state.bingoBanks?.[chosen];
  const final = reveal?.players?.[chosen];
  const latest = state.bingoResults?.findLast((result) => result.round === round);
  return <div className="bingo-stage">
    <header className="bingo-heading"><div><h2>{round ? tr(`${round} / 7라운드`, `Round ${round} / 7`) : tr("경매 빙고", "Auction Bingo")}</h2>
      <p>{bingoPhaseLabel(state)}</p></div><span className="bingo-guest-tag">{guest} · {tr("게스트", "Guest")}</span></header>
    <div className="bingo-round-track" aria-label={tr("라운드 진행", "Round progress")}>
      {Array.from({length: 7}, (_, index) => <span key={index} data-current={index + 1 === round} data-done={Boolean(reveal) || index + 1 < round}>{index + 1}</span>)}
    </div>
    <BingoSubmission progress={state.bingoSubmission} players={players} selected={selected} onChoose={choosePlayer} />
    {!reveal ? <>
      <p className="bingo-secrecy">{tr("낙찰자와 획득 도형은 7라운드 종료 후 공개됩니다. 본인도 낙찰 여부를 알 수 없습니다.", "Winners and acquired shapes stay hidden until all seven rounds end, including from the winners themselves.")}</p>
      <div className="bingo-auctions">
        {bingoShapes.map((shape) => {
          const names = Object.entries(state.bingoChoices ?? {}).filter(([, choice]) => choice === shape).map(([player]) => player);
          const secret = latest?.secret.includes(shape);
          return <section className="bingo-box" data-shape={shape} key={shape}>
            <strong><span aria-hidden="true">{shapeGlyph(shape)}</span> {shapeLabel(shape)}</strong>
            <div className="bingo-tickets">{names.length ? names.map((player) => <button type="button" key={player} onClick={() => choosePlayer(player)} aria-pressed={selected === player}>{player}</button>) : <small>{Object.keys(state.bingoChoices ?? {}).length ? tr("선택자 없음", "No players") : tr("선택 공개 대기", "Awaiting choices")}</small>}</div>
            <span className="bingo-price" data-secret={secret}>{latest ? priceLabel(latest.prices[shape], secret) : tr("발표 전", "Not announced")}</span>
            <small>{tr("낙찰가", "Winning price")}</small>
          </section>;
        })}
      </div>
      <div className="bingo-template"><BingoCard board={board} /><p>{tr("세모 3개 · 동그라미 4개 · 별 2개", "3 triangles · 4 circles · 2 stars")}<br />{tr("마지막에 빙고 줄 수가 최대가 되도록 자동 배치합니다.", "Shapes are placed automatically to maximize completed lines at the end.")}</p></div>
      <p className="bingo-starting-coins">{tr("시작 코인 30원 · 1원×3, 2원×3, 3원×2, 5원×1, 10원×1", "Starting coins: 30 won · 1×3, 2×3, 3×2, 5×1, 10×1")}<br />{tr("매 라운드 최소 1원 입찰 · 낙찰 실패에도 사용한 코인은 소모", "Bid at least one won each round · Losing bids are also spent")}</p>
    </> : <>
      <p className="bingo-secrecy revealed">{tr("획득 도형과 빙고판이 모두 공개되었습니다.", "All acquired shapes and bingo cards have been revealed.")}</p>
      <div className="bingo-player-picker">{players.map((player) => <button type="button" key={player} onClick={() => choosePlayer(player)} aria-pressed={chosen === player} data-guest={player === guest}>{player}{player === guest && <small>{tr("게스트", "Guest")}</small>}</button>)}</div>
      {final && <section className="bingo-final-card"><div><h3>{chosen} <small>{statusText(state, chosen)}</small></h3><BingoCard board={board} filled={final.board} label={tr(`${chosen} · ${final.lines}줄, ${final.filled}칸 완성`, `${chosen} · ${final.lines} lines, ${final.filled} filled cells`)} /></div>
        <dl><div><dt>{tr("빙고", "Bingos")}</dt><dd>{final.lines}{tr("줄", " lines")}</dd></div><div><dt>{tr("완성", "Filled")}</dt><dd>{final.filled} / 9</dd></div><div><dt>{tr("잔여 코인", "Coins left")}</dt><dd>{priceLabel(final.remaining_value)}</dd></div>
          <div><dt>{tr("획득 도형", "Shapes won")}</dt><dd>{bingoShapes.map((shape) => `${shapeGlyph(shape)} ${final.shapes[shape]}`).join(" · ")}</dd></div></dl></section>}
    </>}
    {chosen && (own || final) && <section className="bingo-wallet"><h3>{chosen} · {final ? tr("최종 코인", "Final coins") : tr("비공개 코인 현황", "Private coin balance")}</h3>
      {!final && <p className="muted">{tr("본인과 운영자만 볼 수 있습니다.", "Visible only to this player and the operator.")}</p>}
      <div className="bingo-coins">{[1, 2, 3, 5, 10].map((value) => <span key={value}><i>{value}</i> × {(final?.coins ?? own.coins)[value] ?? 0}</span>)}</div>
      <p>{tr(`총 ${final?.remaining_value ?? coinValue(own.coins)}원 · 피스 ${state.result?.pieces?.[chosen] ?? final?.pieces ?? own.pieces}개`, `${final?.remaining_value ?? coinValue(own.coins)} won total · ${state.result?.pieces?.[chosen] ?? final?.pieces ?? own.pieces} Pieces`)}</p>
    </section>}
    <p className="bingo-rank-rule">{tr("순위: 빙고 줄 수 → 채운 칸 수 → 남은 코인 금액", "Ranking: Bingo lines → Filled cells → Remaining coin value")}</p>
  </div>;
}

export function BingoInformation({state, replay}) {
  const [tab, setTab] = useState("rounds");
  const [roundChoice, setRoundChoice] = useState("");
  const {selected, choosePlayer, seek, match: {players}} = replay;
  const round = Number(roundChoice) || state.bingoRound || 1;
  const reveal = state.bingoReveal;
  const shapeEvent = state.feed.findLast((event) => event.msg_type === "bingo_shapes" && event.data.round === round);
  const resultEvent = state.feed.findLast((event) => event.msg_type === "bingo_result" && event.data.round === round);
  const audit = reveal?.rounds.find((result) => result.round === round);
  const choices = audit?.choices ?? shapeEvent?.data.choices ?? {};
  const visiblePlayers = selected ? [selected] : players;
  const privateBids = new Map();
  let bidRound = 0;
  for (const event of state.feed) {
    if (event.msg_type === "bingo_round") bidRound = event.data.round;
    if (event.msg_type === "action" && event.data.phase === "bingo_bid" && bidRound === round) {
      const bid = parseBingoBid(event.data.action);
      if (bid) privateBids.set(event.agent_name, {amount: coinValue(bid.coins), pieces: bid.pieces, step: event.step});
    }
  }
  const bidRows = visiblePlayers.map((player) => {
    const bid = privateBids.get(player);
    const amount = bid?.amount;
    return [player, choices[player] ? `${shapeGlyph(choices[player])} ${shapeLabel(choices[player])}` : "–",
      amount == null ? tr("비공개", "Private") : <button type="button" className="result-link" onClick={() => seek(bid.step)}>{priceLabel(amount)}</button>];
  });
  const guest = state.bingoSetup?.guest ?? "G01";
  return <aside className="caption match-info bingo-info" aria-label={tr("경매 빙고 결과와 기록", "Auction Bingo results and records")}>
    <TabList role="tablist" aria-label={tr("경매 빙고 정보 종류", "Auction Bingo information tabs")} size="sm" value={tab} onChange={setTab} hasDivider>
      <Tab id="bingo-rounds" value="rounds" label={tr("라운드 기록", "Round history")} panelId="bingo-rounds-panel" />
      <Tab id="bingo-bids" value="bids" label={tr("입찰 기록", "Bid history")} panelId="bingo-bids-panel" />
      <Tab id="bingo-results" value="results" label={tr("최종 결과", "Final results")} panelId="bingo-results-panel" />
    </TabList>
    <div className="match-info-games">
      <Selector label={tr("기록을 볼 참가자", "Filter by player")} isLabelHidden value={selected} size="sm" onChange={choosePlayer}
        options={[{value: "", label: tr("전체 참가자", "All players")}, ...players.map((player) => ({value: player, label: `${player}${player === guest ? tr(" · 게스트", " · Guest") : ""}`}))]} />
      {tab !== "results" && state.bingoRound > 0 && <Selector label={tr("기록을 볼 라운드", "Filter by round")} isLabelHidden value={roundChoice} size="sm" onChange={setRoundChoice}
        options={[{value: "", label: tr("현재 라운드", "Current round")}, ...Array.from({length: state.bingoRound}, (_, index) => ({value: String(index + 1), label: tr(`${index + 1}라운드`, `Round ${index + 1}`)}))]} />}
    </div>
    {state.bingoSubmission?.round === round && tab !== "results" && <BingoSubmission progress={state.bingoSubmission} players={players} selected={selected} onChoose={choosePlayer} />}
    <div id="bingo-rounds-panel" className="match-info-scroll" role="tabpanel" aria-labelledby="bingo-rounds" hidden={tab !== "rounds"} tabIndex={0}>
      {!state.bingoRound ? <p className="empty">{tr("아직 시작한 라운드가 없어요.", "No rounds have started yet.")}</p> : <>
        <Table caption={tr(`${round}라운드 도형 선택·낙찰가`, `Round ${round} · Shape choices and winning prices`)} headers={tr(["도형", "선택한 참가자", audit ? "최종 공개 낙찰가" : "발표 낙찰가"], ["Shape", "Players", audit ? "Final revealed price" : "Announced price"])}
          rows={bingoShapes.map((shape) => [`${shapeGlyph(shape)} ${shapeLabel(shape)}`, Object.entries(choices).filter(([, chosen]) => chosen === shape).map(([player]) => player).join(" · ") || "–",
            audit ? priceLabel(audit.prices[shape]) : resultEvent ? priceLabel(resultEvent.data.prices[shape], resultEvent.data.secret.includes(shape)) : tr("발표 전", "Not announced")])} />
        {resultEvent && <button type="button" className="result-link" onClick={() => seek(resultEvent.step)}>{tr("낙찰가 발표 기록 보기", "View the price announcement")}</button>}
        <p className="muted">{audit ? tr("경기 종료 후 시크릿 낙찰가도 공개되었습니다. 개인별 비공개 입찰 내역은 공개하지 않습니다.", "Secret winning prices are revealed after the match. Individual sealed bids remain private.") : tr("각 라운드에서 발표된 금액입니다. 낙찰자·획득 도형은 최종 공개 전까지 숨깁니다.", "These are the prices announced in each round. Winners and acquired shapes remain hidden until the final reveal.")}</p>
      </>}
    </div>
    <div id="bingo-bids-panel" className="match-info-scroll" role="tabpanel" aria-labelledby="bingo-bids" hidden={tab !== "bids"} tabIndex={0}>
      <p className="muted">{tr("개인별 입찰은 경기 종료 후에도 해당 참가자 시점 또는 운영자 시점에서만 보입니다. 라운드별 개인 획득 수량은 공개하지 않습니다.", "Individual bids remain visible only to their owner and the operator, including after the match. Per-player awards for each round are not disclosed.")}</p>
      <Table caption={tr(`${round}라운드 입찰`, `Round ${round} bids`)} headers={tr(["참가자", "선택", "비공개 입찰액"], ["Player", "Shape", "Sealed bid"])} rows={bidRows} />
    </div>
    <div id="bingo-results-panel" className="match-info-scroll" role="tabpanel" aria-labelledby="bingo-results" hidden={tab !== "results"} tabIndex={0}>
      {!reveal ? <p className="empty">{tr("7라운드가 끝나면 빙고판과 최종 순위를 공개합니다.", "Bingo cards and final standings are revealed after Round 7.")}</p> : <>
        <Table caption={tr("본선 최종 순위 · 게스트 별도 표시", "Final standings · Guest listed separately")} headers={tr(["참가자", "순위", "빙고", "채운 칸", "잔여 금액", "결과"], ["Player", "Rank", "Lines", "Filled", "Coins left", "Result"])}
          rows={[...reveal.ranking, guest].filter((player) => !selected || selected === player).map((player) => {
            const final = reveal.players[player];
            return [player, player === guest ? tr("게스트", "Guest") : reveal.ranking.indexOf(player) + 1, final.lines, `${final.filled} / 9`, priceLabel(final.remaining_value), statusText(state, player)];
          })} />
        <p className="muted">{tr(`${guest}는 생존·탈락 순위에서 제외됩니다. 빙고판 완성 시 피스 4개를 얻습니다.`, `${guest} is excluded from survival and elimination. A full card earns four Pieces.`)}</p>
        {state.result?.guest_result && <section className="bingo-guest-result"><h3>{guest} · {tr("게스트 미션", "Guest missions")}</h3>
          <p>{tr(`전체 ${state.result.guest_result.rank}위 · 전체 1위 ${state.result.guest_result.first ? "성공" : "실패"} · 빙고판 완성 ${state.result.guest_result.full_board ? "성공" : "실패"}`, `Overall rank ${state.result.guest_result.rank} · First place: ${state.result.guest_result.first ? "Achieved" : "Not achieved"} · Full card: ${state.result.guest_result.full_board ? "Achieved" : "Not achieved"}`)}</p>
          <strong>{tr(`상금 ${state.result.guest_result.prize_won.toLocaleString("ko-KR")}원`, `Prize: ₩${state.result.guest_result.prize_won.toLocaleString("en")}`)}</strong>
        </section>}
      </>}
    </div>
  </aside>;
}
