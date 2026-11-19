import React, {useEffect, useLayoutEffect, useRef, useState} from "react";
import {caseTitle} from "./cases.js";
import {drawSet, setHeight, setPoint, setWidth} from "./floor.js";
import {fetchCases} from "./replay.js";
import {Sprite} from "./scene.jsx";
import {InfoNav} from "./info-pages.jsx";
import {LoadingStatus} from "./loading-status.jsx";
import {gameTitle, href, language, siteTitle, tr} from "./locale.js";

const games = [
  {session: "1일차 메인 매치", name: "양자택일", description: tr("아홉 번의 선택으로 승점과 생존이 갈린다.", "Nine choices determine who scores and who survives.")},
  {session: "1일차 감옥 매치", name: "무거운 13", description: tr("큐브가 쌓일수록 벌점을 피하기 어려워진다.", "As the cubes stack up, penalty points get harder to avoid.")},
  {session: "2일차 메인 매치", name: "미스터리 거래소", description: tr("단서로 시세를 읽고, 거래로 자산을 불린다.", "Read the clues, anticipate prices, and trade to grow your portfolio.")},
  {session: "2일차 감옥 매치", name: "러시안 룰렛", description: tr("공개된 단서와 각자 확인한 정보로 다음 칸을 추리한다.", "Use public clues and private observations to work out what comes next.")},
  {session: "3일차 메인 매치", name: "보석 암시장", description: tr("카드를 교환해 구매자의 보석을 맞추고, 마니또와의 점수 곱으로 승부한다.", "Swap hidden cards, match the buyers’ gems, and multiply scores with your manito.")},
  {session: "3일차 감옥 매치", name: "돼지 저금통", description: tr("오가는 저금통의 동전을 기억하고, 의심과 리셋 도전으로 승점을 얻는다.", "Remember the coins in circulating banks and score through doubts and reset challenges.")},
  {session: "4일차 메인 매치", name: "경매 빙고", description: tr("낙찰 결과가 숨겨진 경매에서 도형을 모아 빙고를 완성한다.", "Collect shapes through auctions with hidden outcomes to complete your bingo card.")},
];

export function runHref(id = "", caseId) {
  const params = new URLSearchParams({run: id});
  if (caseId) params.set("case", caseId);
  return href(`/?${params}`);
}

// Season 3 Piece, based on the close-up at 0:18 in the Netflix Korea trailer.
const piecePixels = [
  "................",
  "....hh..........",
  "...htthh........",
  "..httttthh......",
  "..hggttttthh....",
  "..gflggttttthh..",
  "..glflfggtttss..",
  "..glflflfggsss..",
  ".gflflflffgsss..",
  ".gflffllflgsss..",
  ".gfflfflflgss...",
  ".glfllfflfgss...",
  ".gglfffflfgss...",
  "...ggllfflgs....",
  ".....ggllfg.....",
  ".......gggg.....",
];
const pieceColors = {h: "#f4d29b", g: "#bf945c", t: "#56504a", f: "#181d23", s: "#80603f", l: "#8b7e68"};

function PieceMark() {
  const canvas = useRef(null);
  useLayoutEffect(() => {
    const context = canvas.current.getContext("2d");
    piecePixels.forEach((row, y) => {
      [...row].forEach((pixel, x) => {
        if (pixel === ".") return;
        context.fillStyle = pieceColors[pixel];
        context.fillRect(x, y, 1, 1);
      });
    });
  }, []);
  return <canvas className="brand-mark" ref={canvas} width={16} height={16} aria-hidden="true" />;
}

function BrandLink() {
  return <a href={href("/")} className="brand"><PieceMark /><span>{siteTitle}</span></a>;
}

export function Mast({currentPage, replayPosition, children}) {
  const {pathname, search} = window.location;
  const [hash, setHash] = useState(() => window.location.hash);
  useEffect(() => {
    const updateHash = () => setHash(window.location.hash);
    window.addEventListener("hashchange", updateHash);
    return () => window.removeEventListener("hashchange", updateHash);
  }, []);
  const params = new URLSearchParams(search);
  if (replayPosition) {
    params.set("run", replayPosition.id);
    if (replayPosition.frame) params.set("at", replayPosition.frame);
    else params.delete("at");
    if (replayPosition.view !== "operator") params.set("view", replayPosition.view);
    else params.delete("view");
    if (replayPosition.selected) params.set("player", replayPosition.selected);
    else params.delete("player");
  }
  const page = pathname + (params.size ? `?${params}` : "") + hash;
  return <header className="mast">
    <div className={children ? "shell mast-inner mast-with-picker" : "shell mast-inner"}>
      <BrandLink />
      {children && <div className="mast-picker">{children}</div>}
      <div className="mast-links">
        <InfoNav currentPage={currentPage} />
        <nav className="language-switch" aria-label={tr("언어 선택", "Language")}>
          <a href={href(page, "ko")} hrefLang="ko" lang="ko" aria-label="한국어" aria-current={language === "ko" ? "true" : undefined}>KO</a>
          <span aria-hidden="true">/</span>
          <a href={href(page, "en")} hrefLang="en" lang="en" aria-label="English" aria-current={language === "en" ? "true" : undefined}>EN</a>
        </nav>
        <a className="github-link" href="https://github.com/yhg8423/AI-in-Devils-Plan"
          target="_blank" rel="noopener"
          aria-label={tr("GitHub 저장소", "GitHub repository")}>
          {/* GitHub mark from Primer Octicons. */}
          <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" fill="currentColor">
            <path d="M6.766 11.328c-2.063-.25-3.516-1.734-3.516-3.656 0-.781.281-1.625.75-2.188-.203-.515-.172-1.609.063-2.062.625-.078 1.468.25 1.968.703.594-.187 1.219-.281 1.985-.281.765 0 1.39.094 1.953.265.484-.437 1.344-.765 1.969-.687.218.422.25 1.515.046 2.047.5.593.766 1.39.766 2.203 0 1.922-1.453 3.375-3.547 3.64.531.344.89 1.094.89 1.954v1.625c0 .468.391.734.86.547C13.781 14.359 16 11.53 16 8.03 16 3.61 12.406 0 7.984 0 3.563 0 0 3.61 0 8.031a7.88 7.88 0 0 0 5.172 7.422c.422.156.828-.125.828-.547v-1.25c-.219.094-.5.156-.75.156-1.031 0-1.64-.562-2.078-1.609-.172-.422-.36-.672-.719-.719-.187-.015-.25-.093-.25-.187 0-.188.313-.328.625-.328.453 0 .844.281 1.25.86.313.452.64.655 1.031.655s.641-.14 1-.5c.266-.265.47-.5.657-.656" />
          </svg>
          <span>GitHub</span>
        </a>
      </div>
    </div>
  </header>;
}

export function SiteFooter({currentPage}) {
  return <footer className="site-footer">
    <div className="shell site-footer-inner">
      <div>
        <BrandLink />
        <p>{tr("데블스 플랜 시즌 3의 게임을 AI의 시뮬레이션으로 재현한 비공식 팬 프로젝트입니다. 광고, 후원, 유료 결제 없이 무료로 운영합니다.",
          "An unofficial fan project that recreates the games from Season 3 of The Devil’s Plan with AI. Free to use, with no ads, donations, or paid features.")}</p>
        <p>Made by <a href="https://www.hyeonggeun.com/">Hyeonggeun Yun</a></p>
      </div>
      <InfoNav currentPage={currentPage} className="footer-nav" label={tr("하단 메뉴", "Footer navigation")} />
    </div>
  </footer>;
}

function PreviewArena() {
  const map = useRef(null);
  useLayoutEffect(() => drawSet(map.current), []);
  return <figure className="home-set stage-window pixel-frame">
    <div className="home-set-art" role="img" aria-label={tr("16명의 참가자가 모인 픽셀 아트 메인홀", "Pixel art of the main hall with 16 players")}>
      <canvas ref={map} className="set-map" width={setWidth * 2} height={setHeight * 2} aria-hidden="true" />
      {Array.from({length: 16}, (_, index) => {
        const player = "P" + String(index + 1).padStart(2, "0");
        const [x, y] = setPoint(0, index);
        return <span key={player} style={{left: x / setWidth * 100 + "%", top: y / setHeight * 100 + "%"}}>
          <Sprite player={player} />
        </span>;
      })}
    </div>
    <figcaption><span>{tr("메인홀", "Main Hall")}</span><span>{tr("참가자 16명", "16 players")}</span></figcaption>
  </figure>;
}

export function CasePicker({game, onClose}) {
  const open = game !== null;
  const [cases, setCases] = useState(null);
  const [failed, setFailed] = useState(false);
  const dialog = useRef(null);
  useLayoutEffect(() => {
    if (open && !dialog.current.open) dialog.current.showModal();
    if (!open && dialog.current.open) dialog.current.close();
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    const {signal} = controller;
    setFailed(false);
    fetchCases(signal).then(setCases, () => { if (!signal.aborted) setFailed(true); });
    return () => controller.abort();
  }, [open]);

  const available = cases?.flatMap((record) => {
    const match = game ? record.matches.find((item) => item.game === game) : record.matches[0];
    return match ? [{record, match}] : [];
  });

  return <dialog ref={dialog} className="case-dialog" id="case-picker" aria-labelledby="case-picker-title"
    aria-describedby={game ? "case-picker-game" : undefined} onClose={onClose}>
    <div className="case-dialog-heading">
      <div>
        <h2 id="case-picker-title">{tr("플레이 기록 선택", "Choose a replay")}</h2>
        {game && <p id="case-picker-game" className="muted">{gameTitle(game)}</p>}
      </div>
      <form method="dialog"><button className="case-dialog-close" aria-label={tr("닫기", "Close")}>✕</button></form>
    </div>
    {!failed && !cases ? <LoadingStatus /> :
    !available?.length ? <p role="status" className="muted">{failed ?
      tr("플레이 기록을 불러오지 못했어요. 다시 열어 주세요.", "Couldn’t load the replays. Close and try again.") :
      game ? tr("이 매치의 기록이 아직 없어요.", "No replays are available for this match yet.") :
        tr("아직 볼 수 있는 플레이 기록이 없어요.", "No replays are available yet.")}</p> :
      <ol className="home-grid home-case-grid">
        {available.map(({record, match}) => (
          <li key={record.id}>
            <a className="home-card" href={runHref(match.id, record.id)}>
              <h3>{caseTitle(record)}</h3>
              {(match.model_counts?.length > 0 || match.image_model) && <div className="case-card-models">
                <p>{tr("모델 정보", "Model information")}</p>
                <ul>
                  {match.model_counts?.map(({provider, model, effort, count, image_model: imageModel}) => (
                    <li key={`${provider}-${model}-${effort}-${imageModel}`}>
                      {provider && `${provider} · `}{model ?? tr("스크립트", "Scripted")}{effort && ` ${effort}`}
                      {count !== null && tr(` (${count}명)`, ` (${count} ${count === 1 ? "player" : "players"})`)}
                      {imageModel && <ul><li>↳ {tr("이미지 모델", "Image model")}: {imageModel}</li></ul>}
                    </li>
                  ))}
                  {match.image_model && <li>{tr("이미지 모델", "Image model")}: {match.image_model}</li>}
                </ul>
              </div>}
              <span className="home-card-state">{tr("플레이 확인하기", "Watch the replay")} <span aria-hidden="true">→</span></span>
            </a>
          </li>
        ))}
      </ol>}
  </dialog>;
}

export function Home({onChooseCase}) {
  return <>
    <Mast />
    <main className="shell home">
      <section className="home-hero" aria-labelledby="home-title">
        <div className="home-intro">
          <h1 id="home-title">{tr(<>AI가 데블스 플랜 3에 참가한다면 <span>어떻게 될까?</span></>,
            "What if AI played The Devil’s Plan Season 3?")}</h1>
          <p>{tr('서로 다른 성향의 AI 에이전트 16명이 데블스 플랜에 초대되었습니다. 그들은 누구와 손을 잡고, 어떠한 전략을 보여주고, 언제 각자의 길을 갈까요? "AI in 데블스 플랜: 데드 어게인" 프로젝트에서 AI 에이전트의 선택과 대화, 협상, 개인 전략을 살펴보고, 누가 최종 우승자가 될지 살펴보세요.',
            "Sixteen AI agents with distinct personalities have been invited to play The Devil’s Plan. Who will they team up with, what strategies will they try, and when will they go their separate ways? Follow their choices, conversations, negotiations, and private strategies to see who wins.")}</p>
          <div className="home-actions">
            <button type="button" id="watch-from-day-one" className="home-primary" aria-haspopup="dialog" aria-controls="case-picker"
              onClick={() => onChooseCase()}>{tr("1일차부터 보기", "Watch from Day 1")} <span aria-hidden="true">▶</span></button>
            <a href="#game-overview">{tr("게임 목록", "Games")} <span aria-hidden="true">↓</span></a>
          </div>
        </div>
        <PreviewArena />
      </section>
      <section id="game-overview" className="home-matches" aria-labelledby="games-title">
        <div className="home-section-head">
          <h2 id="games-title">{tr("게임 목록", "Games")}</h2>
        </div>
        <ol className="home-grid">
          {games.map(({session, name, description}) => <li key={session}>
            <button className="home-card home-game-card" type="button" aria-haspopup="dialog" aria-controls="case-picker"
              onClick={() => onChooseCase(`${session} · ${name}`)}>
              <small>{gameTitle(session)}</small>
              <strong>{gameTitle(name)}</strong>
              <span className="home-game-description">{description}</span>
              <span className="home-card-state">{tr("플레이 기록 선택", "Choose a replay")} <span aria-hidden="true">→</span></span>
            </button>
          </li>)}
        </ol>
      </section>
    </main>
  </>;
}
