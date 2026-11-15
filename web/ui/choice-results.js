import {scoreText} from "./replay.js";
import {en, tr} from "./locale.js";

const choiceTitles = [
  "성과금 / 보험금", "팀 / 개인", "네모 세기 정산", "공공의 이익 / 개인의 이익", "점수 / 정보",
  "공격 / 방어", "상생 / 견제", "가로수 / 맨홀", "피스 모금", "기억 포커 방식",
];
const englishTitles = ["Bonus / Insurance", "Team / Solo", "Rectangle Counting settlement", "Public / Personal benefit",
  "Points / Information", "Attack / Defense", "Cooperate / Compete", "Tree / Manhole", "Piece pledges", "Memory Poker format"];
export const optionsByChoice = [
  ["성과금", "보험금"], ["3인 팀", "개인"], ["독식", "헌신", "희생", "질책", "도전", "안전"],
  ["공공의 이익", "개인의 이익"], ["점수", "정보"], ["공격", "방어"], ["상생", "견제"],
  ["가로수", "맨홀"], [], ["지목", "계단"],
];

const englishOptions = {
  성과금: "Bonus", 보험금: "Insurance", "3인 팀": "Team of three", 개인: "Solo",
  독식: "Keep all", 헌신: "Devotion", 희생: "Sacrifice", 질책: "Rebuke", 도전: "Challenge", 안전: "Play safe",
  "공공의 이익": "Public benefit", "개인의 이익": "Personal benefit", 점수: "Points", 정보: "Information",
  공격: "Attack", 방어: "Defense", 상생: "Cooperate", 견제: "Compete", 가로수: "Tree", 맨홀: "Manhole",
  지목: "Nomination", 계단: "Ladder", 공공: "Public", "없음": "None",
};

export function choiceOptionLabel(option) {
  if (!en || typeof option !== "string") return option;
  const partner = option.match(/^상생 (.+)$/)?.[1];
  if (partner) return `Cooperate with ${partner}`;
  const pieces = option.match(/^(\d+)피스$/)?.[1];
  if (pieces !== undefined) return `${pieces} ${Number(pieces) === 1 ? "Piece" : "Pieces"}`;
  return Object.hasOwn(englishOptions, option) ? englishOptions[option] : option;
}

export function choiceCountLabel(count, unit) {
  if (!en) return `${count}${unit}`;
  const label = {명: "player", 표: "vote", 팀: "team"}[unit];
  return label ? `${count} ${label}${count === 1 ? "" : "s"}` : String(count);
}

function rankContext(scores, name) {
  if (!Object.hasOwn(scores ?? {}, name)) return "";
  const points = scores[name];
  const totals = Object.values(scores);
  const rank = 1 + totals.filter((total) => total > points).length;
  const tied = totals.filter((total) => total === points).length > 1;
  return tr(`${tied ? "공동 " : ""}${rank}위 · ${scoreText(points)}점`,
    `${tied ? "Tied for rank" : "Rank"} ${rank} · ${scoreText(points)} VP`);
}

function tallyChoices(entries, options, unit, totals) {
  const groups = new Map(options.map((option) => [option, []]));
  for (const [name, option] of entries) {
    if (!groups.has(option)) groups.set(option, []);
    groups.get(option).push(name);
  }
  return Array.from(groups, ([option, names]) => ({option, names, count: totals?.[option] ?? names.length, unit: unit(option)}));
}

export function choiceResults({feed, teams, scene, result}, players, perspective) {
  const submissions = choiceTitles.map(() => Object.create(null));
  const latest = (kind) => feed.findLast((event) => event.msg_type === kind)?.data;
  const teamVotes = [];
  let scores;
  let beforeChoiceFour;
  for (const event of feed) {
    if (event.msg_type === "action") {
      const choice = event.data.phase?.match(/^choice_(10|[1-9])(?:_(?:team|solo))?$/)?.[1];
      if (choice) submissions[Number(choice) - 1][event.agent_name] = event.data.action;
      if (choice === "4") beforeChoiceFour ??= scores;
    } else if (event.msg_type === "scoreboard") {
      scores = event.data;
    } else if (event.msg_type === "choice_4_result") {
      beforeChoiceFour ??= scores;
    } else if (event.msg_type === "team_vote") {
      teamVotes.push(event.data);
    }
  }

  // Choice 5 records the point award and private preview rather than a submission event.
  const choiceFive = feed.findIndex((event) => event.msg_type === "choice_request");
  let beforeChoiceFive;
  if (choiceFive >= 0) {
    beforeChoiceFive = feed.slice(0, choiceFive).findLast((event) => event.msg_type === "scoreboard")?.data;
    const following = feed.slice(choiceFive + 1);
    const settlement = following.find((event) => ["scoreboard", "grass_phase"].includes(event.msg_type));
    if (beforeChoiceFive && settlement?.msg_type === "scoreboard") {
      for (const name of players) {
        if ((perspective === "operator" || perspective === name) && settlement.data[name] > beforeChoiceFive[name]) {
          submissions[4][name] ??= "점수";
        }
      }
    }
    for (const event of following) {
      if (event.msg_type === "preview" && Array.isArray(event.visible_to)) {
        for (const name of event.visible_to) submissions[4][name] ??= "정보";
      }
    }
  }

  const publicVote = latest("choice_4_result");
  const challenge = latest("challenge_result");
  const pledges = latest("choice_9_result");
  const poker = latest("poker_mode");
  const priority = latest("priority")?.order ?? [];
  const representatives = latest("representatives") ?? {};
  const prePoker = latest("pre_poker_ranking");
  const teamByPlayer = new Map((teams ?? []).flatMap((team) => team.map((name) => [name, team])));
  const publicChoices = {...scene.choices, 4: publicVote?.choices};
  const partners = publicChoices[7];
  const nominatedPartner = (name) => partners?.[name]?.match(/^상생 (.+)$/)?.[1];
  const pairs = partners && players.flatMap((name) => {
    const partner = nominatedPartner(name);
    return partner && name < partner && nominatedPartner(partner) === name ? [`${name}·${partner}`] : [];
  });
  const tile = (name) => scene.tiles?.[name] ? tr(`${scene.tiles[name]}번 타일`, `Tile ${scene.tiles[name]}`) : "";
  const contexts = [
    (name) => result?.living?.includes(name) ? tr("생활동", "Living Quarters") : result?.prison?.includes(name) ? tr("감옥동", "Prison Wing") :
      result?.eliminated?.includes(name) ? tr("탈락", "Eliminated") : "",
    (name) => priority.includes(name) ? tr(`우선권 ${priority.indexOf(name) + 1}위`, `Priority ${priority.indexOf(name) + 1}`) : "",
    (name) => Object.hasOwn(representatives, name) ? tr("대표", "Representative") :
      teamByPlayer.get(name)?.length === 3 ? tr("팀원", "Team member") : tr("개인", "Solo"),
    (name) => rankContext(beforeChoiceFour, name),
    (name) => rankContext(beforeChoiceFive, name),
    tile,
    (name) => {
      const partner = nominatedPartner(name);
      if (!partner) return tile(name);
      return nominatedPartner(partner) === name ? tr(`${partner}와 상생 확정`, `Paired with ${partner}`)
        : tr(`${partner} 지목 · 미성립`, `Nominated ${partner} · no pair`);
    },
    (name) => [tile(name), choiceOptionLabel(publicChoices[6]?.[name])].filter(Boolean).join(" · "),
    (name) => [prePoker?.ranking?.includes(name) && tr(`${prePoker.ranking.indexOf(name) + 1}위`, `Rank ${prePoker.ranking.indexOf(name) + 1}`),
      Object.hasOwn(prePoker?.pieces ?? {}, name) && tr(`보유 ${prePoker.pieces[name]}피스`,
        `${choiceOptionLabel(`${prePoker.pieces[name]}피스`)} held`)].filter(Boolean).join(" · "),
    (name) => prePoker?.ranking?.includes(name) ? tr(`시작 ${prePoker.ranking.indexOf(name) + 1}위`, `Starting rank ${prePoker.ranking.indexOf(name) + 1}`) : "",
  ];
  const participant = (number, name) => {
    const context = contexts[number - 1](name);
    return context ? `${name} (${context})` : name;
  };
  const teamRows = teamVotes.map(({team, decision}) => [team.map((name) => participant(3, name)).join(" · "), decision]);
  const summaries = {
    3: challenge && tr(`추가 대결 우승 ${challenge.winner} · 도전 ${challenge.challengers.join(", ")}`,
      `Extra challenge winner: ${challenge.winner} · Challengers: ${challenge.challengers.join(", ")}`),
    4: publicVote && (publicVote.prize_token ? tr("상금의 징표 획득", "Prize Token earned") : tr("상금의 징표 미획득", "Prize Token not earned")),
    7: pairs && (pairs.length ? tr(`확정 상생 팀 ${pairs.join(", ")}`, `Confirmed pairs: ${pairs.join(", ")}`)
      : tr("성립한 상생 팀 없음", "No pairs formed")),
    9: pledges && tr(`총 약정 ${pledges.pledged}피스 · 최하위 ${pledges.eliminations}명 탈락`,
      `${choiceOptionLabel(`${pledges.pledged}피스`)} pledged · ${choiceCountLabel(pledges.eliminations, "명")} eliminated from the bottom`),
    10: poker && tr(`${poker.mode} 방식 확정`, `${choiceOptionLabel(poker.mode)} format confirmed`),
  };
  const groupResults = {
    2: teams?.length && {kind: "group", caption: tr("확정 팀 구성", "Confirmed teams"), headers: tr(["참가자", "참가 방식"], ["Player", "Entry format"]),
      rows: teams.map((team) => [team.map((name) => participant(2, name)).join(" · "), choiceOptionLabel(team.length === 3 ? "3인 팀" : "개인")])},
    3: teamRows.length && {kind: "group", caption: tr("팀 정산", "Team settlement"), headers: tr(["팀원", "팀 결정"], ["Team members", "Team decision"]),
      rows: teamRows.map(([name, decision]) => [name, choiceOptionLabel(decision)])},
  };

  return choiceTitles.flatMap((title, index) => {
    const number = index + 1;
    const published = publicChoices[number];
    const picks = published ?? submissions[index];
    const bonusSettled = number === 1 && result?.living && result?.prison;
    const rows = Object.entries(picks).map(([name, value]) => {
      const player = participant(number, name);
      if (bonusSettled) {
        const reward = value === "성과금" && result.living.includes(name) ? 1 :
          value === "보험금" && result.prison.includes(name) ? 2 : 0;
        return [player, value, `${reward}피스`];
      }
      if (number === 4 && ["공공", "개인"].includes(value)) return [player, `${value}의 이익`];
      if (number === 9) return [player, `${value}피스`];
      return [player, value];
    });
    const tables = [groupResults[number]].filter(Boolean);
    if (rows.length) {
      const headers = [tr("참가자", "Player"), number === 9 ? tr("약정", "Pledge") : tr("선택", "Choice")];
      if (bonusSettled) headers.push(tr("보상", "Reward"));
      tables.push({kind: published ? "published" : "submitted",
        caption: published ? tr("공개 선택", "Public choices") : tr("참가자 제출", "Player submissions"), headers,
        rows: rows.map(([name, value, ...rest]) => [name, choiceOptionLabel(value), ...rest.map(choiceOptionLabel)])});
    }
    const summary = summaries[number];
    const tallies = [];
    if (number === 2 && teams?.length && (perspective !== "operator" || !rows.length)) {
      const entries = teams.flatMap((team) => team.map((name) => [participant(2, name), team.length === 3 ? "3인 팀" : "개인"]));
      tallies.push({title: tr("확정 참가 방식", "Confirmed entry formats"), groups: tallyChoices(entries, optionsByChoice[index], () => "명")});
    } else if (rows.length || (number === 10 && poker)) {
      const entries = rows.map(([name, value]) => {
        if (number === 2 && value !== "개인") return [name, "3인 팀"];
        if (number === 7 && value.startsWith("상생 ")) return [name, "상생"];
        return [name, value];
      });
      const totals = number === 10 && Number.isInteger(poker?.nomination_votes)
        ? {지목: poker.nomination_votes, 계단: players.length - poker.nomination_votes} : undefined;
      const complete = published || rows.length === players.length || totals;
      const unit = (option) => number === 4 || number === 10 ||
        (number === 3 && ["독식", "헌신", "희생", "질책"].includes(option)) ? "표" : "명";
      const groups = tallyChoices(entries, complete ? optionsByChoice[index] : [], unit, totals);
      if (number === 9) groups.sort((left, right) => parseInt(left.option, 10) - parseInt(right.option, 10));
      const title = totals && rows.length < players.length ? tr("공개 득표수", "Public vote totals")
        : complete ? tr("선택지별 집계", "Choice totals") : tr("열람 가능한 제출 집계", "Visible submissions");
      tallies.push({title, groups});
    }
    if (number === 3 && teamRows.length && rows.length < players.length) {
      tallies.push({title: tr("팀 정산 집계", "Team settlement totals"), groups: tallyChoices(teamRows, [], () => "팀")});
    }
    return summary || tables.length ? [{value: String(number), label: tr(`선택 ${number}`, `Choice ${number}`),
      title: tr(title, englishTitles[index]), summary, tallies, tables}] : [];
  });
}
