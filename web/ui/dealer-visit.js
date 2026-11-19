import {setHeight, setWidth} from "./floor.js";

const door = [417, 244];
const inside = [450, 244];
const at = ([x, y], offset, opacity = 1) => ({left: `${x / setWidth * 100}%`, top: `${y / setHeight * 100}%`, offset, opacity});

export function dealerVisitFrames(route) {
  const approach = [...route, door];
  const distances = [0];
  for (let index = 1; index < approach.length; index++) {
    distances.push(distances[index - 1] + Math.hypot(approach[index][0] - approach[index - 1][0], approach[index][1] - approach[index - 1][1]));
  }
  const distance = distances.at(-1) || 1;
  return [
    ...approach.map((point, index) => at(point, distances[index] / distance * .3)),
    at(door, .3001, 0), at(inside, .38, 0), at(inside, .62, 0), at(door, .6999, 0),
    ...approach.toReversed().map((point, index) => at(point, .7 + (distance - distances[approach.length - index - 1]) / distance * .3)),
  ];
}

export function cancelDealerVisits(active) {
  for (const visit of [...active.values()]) visit.cancel();
}

export function syncDealerVisits(active, {cues = [], frame, previousFrame, phase, previousPhase, locations, tokens, routeFor, reducedMotion}) {
  if (frame < previousFrame || phase !== previousPhase || reducedMotion) cancelDealerVisits(active);
  for (const [player, visit] of active) {
    if (tokens.get(player) !== visit.token || (locations[player] ?? 0) !== visit.room) visit.cancel();
    else visit.token.classList.add("walking", "dealer-visiting");
  }
  if (reducedMotion || previousFrame < 0 || frame <= previousFrame) return;
  for (const cue of cues) {
    if (cue.step <= previousFrame || cue.step > frame || `${cue.round}:bid` !== phase) continue;
    const token = tokens.get(cue.player);
    if (!token) continue;
    active.get(cue.player)?.cancel();
    for (const animation of token.getAnimations()) animation.cancel();
    token.classList.add("walking", "dealer-visiting");
    token.dataset.dealerVisit = String(cue.step);
    const animation = token.animate(dealerVisitFrames(routeFor(cue.player)), {duration: 2600, easing: "linear"});
    const visit = {token, animation, room: locations[cue.player] ?? 0};
    const restore = () => {
      if (active.get(cue.player) !== visit) return;
      token.classList.remove("walking", "dealer-visiting");
      delete token.dataset.dealerVisit;
      active.delete(cue.player);
    };
    visit.cancel = () => { animation.cancel(); restore(); };
    animation.onfinish = restore;
    animation.oncancel = restore;
    active.set(cue.player, visit);
  }
}
