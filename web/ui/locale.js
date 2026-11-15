const location = globalThis.location;
export const en = new URLSearchParams(location?.search).get("lang") === "en";
export const language = en ? "en" : "ko";

export function tr(korean, english) {
  return en ? english : korean;
}

export const siteTitle = tr("AI in 데블스 플랜: 데드 어게인", "AI in The Devil’s Plan: Dead Again");

const gameNames = new Map([
  ["1일차", "Day 1"], ["2일차", "Day 2"],
  ["1일차 메인 매치", "Day 1 Main Match"], ["1일차 감옥 매치", "Day 1 Prison Match"],
  ["2일차 메인 매치", "Day 2 Main Match"], ["2일차 감옥 매치", "Day 2 Prison Match"],
  ["양자택일", "Either/Or"], ["무거운 13", "Heavy 13"],
  ["미스터리 거래소", "Mystery Stock Exchange"], ["러시안 룰렛", "Russian Roulette"],
  ["큐브 세기", "Cube Counting"], ["네모 세기", "Rectangle Counting"],
  ["잔디 깔기", "Lay the Grass"], ["기억 포커", "Memory Poker"],
]);

export function gameTitle(title) {
  return en ? title.split(" · ").map((part) => gameNames.get(part) ?? part).join(" · ") : title;
}

export function href(path, lang = language) {
  const url = new URL(path, "https://devils-plan.local");
  if (lang === "en") url.searchParams.set("lang", "en");
  else url.searchParams.delete("lang");
  return url.pathname + url.search + url.hash;
}
