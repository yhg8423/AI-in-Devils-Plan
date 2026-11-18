const attack = "Attack uses the uncut tile. A successful placement earns twice its number in Victory Points, while a failed placement costs 4. Defense may remove up to two edge-adjacent squares, but cannot remove the numbered square, split the tile, or create a hole. Defense earns the tile number on success and 0 on failure.";
const partner = "Two players who select each other cooperate. If both tiles are placed, the pair earns 1 bonus point per shared edge. Their submitted shares must add up to the full bonus. A player who chooses to compete earns 5 extra points if their tile is placed and no more than nine players place tiles in total.";
const obstacle = "Choose one tree or two manholes worth +1 and −1. A tile may cover a tree only with a hole. Covering a manhole adds or subtracts one point. Place manholes first, then trees, then tiles. Obstacles go on empty board cells in tile placement order.";
const points = "Choose Points for 5 Victory Points or Information for a private preview of Choices 6–8 before picking a tile.";

// Replay logs retain the original rules. Summaries cover known headings without changing archived data.
const summaries = [
  ["돼지 저금통", "Four players circulate five numbered banks, each starting with one black and one white coin. Deposit one to five coins into your lower bank, announce the added colors and amounts truthfully, and pass it to another player. Move your upper bank down. The receiver declares the black or white total, alternating each turn. Only the first doubt is judged: a successful doubter gains one point and the declarer loses one; a failed doubter loses one. The opened bank is replaced, and the player who lost a point acts next. Three reset requests trigger a reset. Before it, the remaining player may recall both colors in all five banks for +3 points or −2 on failure. End immediately when anyone reaches five points. Last place is eliminated; first place shares three Pieces, discarding any remainder. Coin counting aids are prohibited. In the simulation, drawn order resolves simultaneous doubts and final score ties; discussion and decision windows replace the timers."],
  ["보석 암시장", "Play three rounds with hidden gem and bomb cards. Nine players use 13 cards. A ten-player continuation adds one Copper 1. Secretly bid Pieces for the lead. Ties trigger another auction, then agreement, with base order resolving failed agreement. Swap once in forward order and once in reverse. The three-minute turn becomes one discussion action per player. Bomb holders must swap with another player. Losing your bomb to someone else’s swap earns 3 points. Once per game, a Piece inspects one buyer or trash card. At reveal, each matching buyer earns your card’s value. A scoring diamond also earns one Piece. Bombs score their printed negative value. The −6 holder leads next, then −4, then the previous leader. Final VP equals your cumulative VP times your incoming manito’s VP. Base order breaks final ties. The top three enter the Living Quarters, the bottom player is eliminated, and the winner saves one prisoner with the Alliance Token. Final VP of at least 1 earns one Piece, or two at 10 or more."],
  ["양자택일 ·", "Sixteen players face ten choices and four minigames. Everyone starts at 0 Victory Points and normally holds one Piece. Scores are public. By default, the top six are assigned to the Living Quarters, the next eight to the Prison Wing, and the bottom two are eliminated. First place may move one player from the Prison Wing to the Living Quarters."],
  ["선택 1 ·", "Performance Pay awards one Piece if you end up in the Living Quarters. Insurance awards two Pieces if you end up in the Prison Wing. The final assignments after the alliance token decide the payout."],
  ["미니게임 1 ·", "Count all the cubes and submit the total privately. Wrong answers have a 20-second virtual cooldown. Correct answers establish priority in submission order. The game ends after 15 correct answers, and the remaining player ranks 16th. Priority breaks later ties on scores and tile numbers."],
  ["미니게임 2 ·", "Count grid-aligned rectangles whose cells sum to the target. Blank cells count as zero. A single cell and the entire board can qualify. Answers are processed in the order they arrive. A wrong answer locks that team out of the current puzzle. Two correct answers earn a win. Play ends once half the entries win. A solo win earns 7 Victory Points and a solo loss costs 3. Teams settle their scores in Choice 3."],
  ["네모 세기 · 팀 대표", "Each team of three selects the member who contributed most in Rectangle Counting as its representative."],
  ["선택 3 ·", "Teams settle scores by majority vote. A winning team gives its representative and teammates either +5/+1/+1 or +1/+3/+3. A losing team chooses −3/0/0 or 0/−2/−2. Solo players may accept a one-point loss or enter another puzzle. The extra contest winner earns three Pieces, and each loser loses three Victory Points."],
  ["선택 4 ·", "If at least nine players choose the public interest, the group earns a prize token worth ₩100 million toward the season prize. A player who chooses self-interest gains 5 Victory Points regardless of the vote."],
  ["선택 6 ·", attack], ["선택 7 ·", partner], ["선택 8 ·", obstacle],
  ["선택 9 ·", "Players privately pledge up to eight Pieces, limited by their balances. If pledges reach eight, the highest-ranked contributors pay up to their pledges until eight Pieces are collected, and only last place is eliminated. Otherwise no one pays and the bottom two are eliminated. Seven players enter the Prison Wing after the alliance token is used."],
  ["미니게임 4 ·", "Victory Points and Cube Counting priority determine starting ranks. Each duel shows 16 cards for 20 seconds. Players choose 8–10 positions to memorize in the simulation, then privately select two positions after three shared cards are revealed. Unmemorized positions may be guessed. Compare five-card poker hands using both selected cards and all shared cards. Ties are replayed. Choice 10 sets the format: nomination requires eight votes, and the ladder requires nine. The two lowest-ranked players begin streaks. In nomination, challengers choose a higher-ranked opponent they have not faced. A win moves them up and the opponent down. A successful defender earns one Piece. In the ladder, a win swaps places with the player immediately above. Play continues until no new player is eligible to challenge."],
  ["최종 배정 ·", "Final standings determine who goes to the Living Quarters or Prison Wing and who is eliminated. The winner moves one player from the Prison Wing to the Living Quarters. Choice 1 payouts use those final assignments, and eliminated players receive no payout."],
  ["‘선택 5’의 5는", "Available tiles are 3, 4, 6, 7, 9, 11, and 13. Choose tiles from lowest to highest score, then place them from smallest to largest tile number. Cube Counting priority breaks ties. Rotate in quarter turns. Flipping, overlapping, and off-board placements are invalid. A successful placement normally earns the tile number. Scores are settled after everyone has a turn."],
  ["무거운 13 ·", "Seven players play 14 rounds. Each starts with rock cards numbered 0–6, two chips of each color, and one rainbow chip. Submit one card and one chip privately each round. Rainbow goes first, then higher weights, with ties resolved clockwise from the lead player. Rainbow can use any base. A player may pass once per round. Players who pass place last, in reverse pass order. When a base reaches 13 or more, remove its old cubes and give the player one penalty point per cube removed, including zeroes. The new cube stays. The last player to receive a penalty leads the next round. Refill cards and chips at Round 8. Fewest penalties wins, with recent penalties breaking ties against the player. The bottom two are eliminated. The winners split four Pieces, discarding any remainder."],
  ["미스터리 거래소 ·", "Everyone starts with ₩100,000 in virtual cash. Seven stocks start at ₩10,000, with a ₩100 floor. There are 24 rounds of five virtual minutes, with one turn per player per minute. Players can trade at fixed prices while moving or talking. Prices, volumes, total holdings, and rankings update between rounds. Clues reveal more characters in Rounds 5, 10, and 15 and become fully visible in Round 20. Once per game, a player may hide a stock’s public trading information for the next two rounds. Through Round 20, a Piece buys an early private clue or converts to ₩10,000. Cash plus stock value determines final rank. The last-place player is eliminated, and first place can save one player from the Prison Wing. Assets of ₩1.5M, ₩3M, or ₩6M earn one, two, or three Pieces respectively. ₩10M earns a prize token."],
  ["러시안 룰렛 ·", "Six players start with 16 credits each. Two of the six board positions contain hidden elimination markers. The lead seat shifts clockwise each round. Players may speak publicly or whisper to adjacent seats for free, including between actions. Inspect a position and its neighbor publicly for 1 credit or privately for 2. Rotate the assignment by one or two positions for 3 or 4 credits. Players may also secretly contribute 1–3 credits toward a swap. At six or more pooled credits, the last contributor swaps two adjacent positions and the pool resets. The game ends when three players have zero credits. Players assigned to the two marked positions are eliminated. Each survivor earns one Piece."],
];

export function rulesSummary(heading, body) {
  if (heading.startsWith("돼지 저금통")) {
    const turns = body.includes("전원에게 두 턴씩") ? "two discussion turns" : "one discussion turn";
    const silent = body.includes("\n\n6. 대화 없는 진행\n");
    const memory = body.includes("\n\n5. 변경 가능한 기억 슬롯\n") ?
      " Each player keeps black and white estimates for three banks and may choose any three current banks at each memory update. Estimates can be wrong or unknown and are never corrected from hidden totals. Each update replaces the previous three-bank memory, so dropping a bank forgets its old totals; selecting it again does not recover that memory. Resets begin with fresh banks. A retired remembered bank is replaced by its fresh replacement with one coin of each color." : body.includes("\n\n5. 비공개 기억 요약\n") ?
        " Each player maintains a private summary of at most 300 characters, choosing which facts, doubts, or plans to retain. There are no fixed banks or slots. The summary is rewritten after opening discussions and completed turns; it can omit facts, contain mistakes, or be cleared. Resets retain the previous summary until the player rewrites it. The engine supplies no hidden totals, automatic correction, or earlier transcript beyond the retained summary." : body.includes("\n\n6. 기억 직접 갱신\n") ?
        " Each player maintains their own black and white estimates for three chosen banks, updating those memories after each deposit. Estimates can be wrong, and uncertain counts may be left unknown; the engine never corrects them with hidden totals. Players choose banks at the start and after each reset, keeping those slots until the next reset. A retired selected bank is replaced by the fresh bank with one coin of each color. Earlier bank-count records are unavailable outside these memories." : body.includes("\n\n5. 기억 슬롯\n") ?
        " The simulation privately retains exact black and white counts for three chosen banks. Players choose at the start and after each reset; slots stay fixed between resets and follow fresh replacements, which start with one coin of each color. Earlier bank-count records are unavailable outside these slots." : "";
    let summary = summaries.find(([prefix]) => prefix === "돼지 저금통")[1];
    if (body.includes("\n\n8. 리셋 동시 판단\n")) summary = summary.replace(
      "Three reset requests trigger a reset. Before it, the remaining player may recall both colors in all five banks for +3 points or −2 on failure.",
      "A reset occurs when at least three players have requested it. Players who have not already requested one decide simultaneously in private, and all responses are collected before any new requests are announced. At exactly three cumulative requests, the sole non-requester may recall both colors in all five banks for +3 points or −2 on failure. If all four request a reset, reset directly without a challenge.",
    );
    const relationships = body.includes("\n\n7. 관계 평가 없음\n") ?
      " Relationship assessments are disabled during and at the end of this match." : "";
    const initialMemory = body.includes("\n\n초기 기억 선택\n") ?
      " Memory slots start empty. At the start and after each reset, each player independently chooses three current banks in private." : "";
    return (silent ? summary.replace("discussion and decision windows replace the timers", "decision windows replace the timers") : summary) +
      (silent ? " There are no discussion or whisper phases. Players privately prepare and update their initial memory before the first deposit. Coin deposits, count declarations, and verdicts remain public." :
        ` Each player has four opening discussion turns and ${turns} before each deposit.`) + memory + initialMemory + relationships;
  }
  if (heading.startsWith("보석 암시장")) {
    const relationships = body.includes("\n\n8. 관계 평가 갱신\n") ?
      " Players review affinity and trust after discussions, auction results, swaps, card reveals, final scoring, and the Alliance Token decision. Updates require new evidence visible to that player." : "";
    const preparation = body.includes("\n\n9. 시작 전 비공개 전략 준비\n") ?
      " Each player privately plans, reviews, and finalizes a strategy in three steps before the 12 opening discussion turns. Each step retains the player's own previous summary. Manitos and cards remain unrevealed throughout preparation." : "";
    const swapDiscussion = body.includes("\n\n10. 교환 전 대화 단축과 조기 종료\n") ?
      "Pre-swap discussions allow up to four turns. The active player speaks first each turn and may immediately end the discussion to proceed to the swap. Tied-auction discussions allow up to five turns. Both windows also end when everyone passes in a turn." :
      "Pre-swap and tied-auction discussions also allow up to five turns, ending early when everyone passes in one turn.";
    let summary = summaries.find(([prefix]) => prefix === "보석 암시장")[1] + relationships + preparation;
    if (body.includes("최하위 두 명은 탈락")) {
      summary = summary.replace("the bottom player is eliminated", "the bottom two players are eliminated");
    }
    if (body.includes("\n\n7. 시작 전 진행 순서\n")) return summary.replace(
      "The three-minute turn becomes one discussion action per player.",
      "The opening discussion allows 12 turns per player before manitos are revealed. Players then privately learn whose score their points affect and submit simultaneous sealed Piece bids, with no discussion between revelation and the initial bids. After the auction winner is announced, players may discuss for up to five turns before cards are dealt. " + swapDiscussion + " All players may discuss auction ties before re-bidding or the final agreement vote. Tied bidders alone submit further bids or nominate the leader. After pre-swap discussion and any paid inspection, the acting player privately plans the swap.",
    );
    if (body.includes("\n\n6. 동률 경매 협상\n")) return summary.replace(
      "The three-minute turn becomes one discussion action per player.",
      "The simulation gives each player 12 opening discussion turns before bidding. Each swap and tied auction allows up to five discussion turns, ending early when everyone passes in one turn. All players may discuss auction ties before re-bidding or the final agreement vote. Tied bidders alone submit further bids or nominate the leader. After discussion and any paid inspection, the acting player privately plans the swap.",
    );
    return /2(?:회전|턴)/.test(body) ? summary.replace(
      "The three-minute turn becomes one discussion action per player.",
      "The simulation provides two opening discussion turns before bidding and two before each swap. After discussion and any paid inspection, the acting player privately plans the swap.",
    ) : summary;
  }
  if (heading.startsWith("선택 2 ·")) {
    const teams = "Enter Rectangle Counting alone or form a team of three. All three players must privately submit the same lineup.";
    const submissionTurn = body.match(/(\d+)턴부터 자기 차례에 비공개로 제출/)?.[1];
    const timing = submissionTurn ? `The first ${Number(submissionTurn) - 1} turns are for negotiation only. Players can submit privately on their own turn starting on turn ${submissionTurn}.` :
      body.includes("협상 중 언제든") ? "Players can submit privately on their own turn at any point during negotiations." : "";
    const ending = timing ? "When everyone has submitted, teams are revealed and the game begins. Anyone who has not submitted chooses at the deadline." :
      "Once a team is formed, its lineup cannot change until the game ends.";
    return [teams, timing, ending].filter(Boolean).join(" ");
  }
  if (heading.startsWith("선택 5 ·")) {
    const turns = body.match(/각각 (\d+)(?:턴|라운드) 협상/)?.[1];
    return turns ? `${points} The simulation allows ${turns} negotiation turns before and after this choice. Players who choose Information write a private plan before the second negotiation.` : points;
  }
  if (heading.startsWith("선택 6~8 미리보기")) {
    return `Choice 6: ${attack}\n\nChoice 7: ${partner}\n\nChoice 8: ${obstacle}`;
  }
  return summaries.find(([prefix]) => heading.startsWith(prefix))?.[1];
}
