const location = globalThis.location;
export const en = new URLSearchParams(location?.search).get("lang") === "en";
export const language = en ? "en" : "ko";

export function tr(korean, english) {
  return en ? english : korean;
}

export const siteTitle = tr("AI in 데블스 플랜: 데드 어게인", "AI in The Devil’s Plan: Dead Again");

const gameNames = new Map([
  ["1일차", "Day 1"], ["2일차", "Day 2"], ["3일차", "Day 3"], ["4일차", "Day 4"],
  ["1일차 메인 매치", "Day 1 Main Match"], ["1일차 감옥 매치", "Day 1 Prison Match"],
  ["2일차 메인 매치", "Day 2 Main Match"], ["2일차 감옥 매치", "Day 2 Prison Match"],
  ["3일차 메인 매치", "Day 3 Main Match"], ["보석 암시장", "Gem Black Market"],
  ["3일차 감옥 매치", "Day 3 Prison Match"], ["돼지 저금통", "Piggy Bank"],
  ["4일차 메인 매치", "Day 4 Main Match"], ["경매 빙고", "Auction Bingo"],
  ["4일차 감옥 매치", "Day 4 Prison Match"], ["벽바둑 2", "Wall Go II"],
  ["5일차", "Day 5"], ["5일차 메인 매치", "Day 5 Main Match"], ["히든 워드", "Hidden Word"],
  ["5일차 감옥 매치", "Day 5 Prison Match"], ["수식의 탑", "Tower of Equations"],
  ["6일차", "Day 6"], ["6일차 메인 매치", "Day 6 Main Match"],
  ["6일차 감옥 매치", "Day 6 Prison Match"], ["그라데이션", "Gradation"],
  ["유배지 매치 1", "Exile Match 1"], ["피스 퍼즐", "Piece Puzzle"],
  ["유배지 매치 2", "Exile Match 2"], ["달라진 그림 찾기", "Spot the Difference"],
  ["유배지 매치 3", "Exile Match 3"], ["비밀 코드", "Secret Code"],
  ["유배지 매치 4", "Exile Match 4"], ["울타리 치기", "Loop Fence Puzzle"],
  ["유배지 매치 5", "Exile Match 5"], ["대칭 퍼즐", "Symmetrical Puzzle"],
  ["유배지 매치 6", "Exile Match 6"], ["만국기", "Flags"], ["유배지 매치 7", "Exile Match 7"], ["유배지 매치 8", "Exile Match 8"], ["포인트 오목", "Point Gomoku"],
  ["양자택일", "Either/Or"], ["무거운 13", "Heavy 13"],
  ["미스터리 거래소", "Mystery Stock Exchange"], ["러시안 룰렛", "Russian Roulette"],
  ["큐브 세기", "Cube Counting"], ["네모 세기", "Rectangle Counting"],
  ["잔디 깔기", "Lay the Grass"], ["기억 포커", "Memory Poker"],
]);

export function canonicalGameTitle(title) {
  return title.replaceAll("틀린 그림 찾기", "달라진 그림 찾기");
}

export function gameTitle(title) {
  title = canonicalGameTitle(title);
  return en ? title.split(" · ").map((part) => gameNames.get(part) ?? part).join(" · ") : title;
}

export function href(path, lang = language) {
  const url = new URL(path, "https://devils-plan.local");
  if (lang === "en") url.searchParams.set("lang", "en");
  else url.searchParams.delete("lang");
  return url.pathname + url.search + url.hash;
}
