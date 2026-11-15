import {tr} from "./locale.js";

export const chipColors = ["빨강", "초록", "파랑", "레인보우"];
const englishColors = ["Red", "Green", "Blue", "Rainbow"];

export function chipColorLabel(color) {
  return tr(color, englishColors[chipColors.indexOf(color)] ?? color);
}

export function heavy13Players(players, feed) {
  const accounts = new Map(players.map((player) => [player, {rounds: [], penalties: 0}]));
  let round = 0;
  const resetHands = () => {
    for (const account of accounts.values()) {
      account.cards = [0, 1, 2, 3, 4, 5, 6];
      account.chips = Object.fromEntries(chipColors.map((color) => [color, color === "레인보우" ? 1 : 2]));
    }
  };
  resetHands();

  function submit(player, {weight, chip}, step) {
    const account = accounts.get(player);
    const entry = account?.rounds[round - 1];
    if (!entry) return;
    if (chipColors.includes(chip) && entry.chip === undefined) {
      entry.chip = chip;
      entry.step = step;
      account.chips[chip]--;
    }
    if (Number.isInteger(weight) && entry.weight === undefined) {
      entry.weight = weight;
      entry.step = step;
      account.cards = account.cards.filter((card) => card !== weight);
    }
  }

  for (const {msg_type: type, data, step, agent_name: player} of feed) {
    if (type === "round") {
      round = data.round;
      if (round === 1 || round === 8) resetHands();
      for (const [name, account] of accounts) {
        account.penalties = data.penalties?.[name] ?? account.penalties;
        account.rounds[round - 1] = {round, step, total: account.penalties};
      }
    } else if (type === "action" && data.phase === "submit") {
      const [weight, chip] = data.action.split(/\s+/);
      submit(player, {weight: Number(weight), chip}, step);
    } else if (type === "colors" || type === "weights") {
      for (const [name, value] of Object.entries(data)) {
        submit(name, type === "colors" ? {chip: value} : {weight: value}, step);
      }
    } else if (type === "action" && data.phase === "place" && data.action === "패스") {
      const entry = accounts.get(player)?.rounds[round - 1];
      if (entry) Object.assign(entry, {passed: true, step});
    } else if (type === "placement") {
      const account = accounts.get(data.player);
      const entry = account?.rounds[round - 1];
      if (!entry) continue;
      account.penalties += data.penalty;
      Object.assign(entry, {placement: data.color, penalty: data.penalty, total: account.penalties, step});
    }
  }
  return accounts;
}
