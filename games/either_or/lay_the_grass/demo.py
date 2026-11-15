"""Run a complete 16-player Lay the Grass match without a model API."""

import argparse
from collections.abc import Sequence
from dataclasses import asdict
import json
import random

from chatarena.agent import Player
from chatarena.arena import Arena
from concordia.components.agent.observation import OBSERVATION_TAG
from concordia.language_model.language_model import LanguageModel
from concordia.language_model.no_language_model import NoLanguageModel

from .choice_five_demo import DEMO_DISCUSSION_ROUNDS, demo_models, demo_room_speech
from .choice_five import CHANNEL_NAMES, PLAYER_COUNT, format_speech
from .board import Placement, Shape, neighbors
from .environment import ATTACK, CHECK, COOPERATE, DEFENSE, FAIL, MANHOLE, TREE, LayTheGrass
from .simulation import DISCUSSION_PROMPT, ConcordiaBackend, DiscussionAction, ScriptedLanguageModel, play_arena


class GrassDemoModel(NoLanguageModel):
    def __init__(self, game: LayTheGrass, name: str, model: LanguageModel):
        self.game = game
        self.name = name
        self.seat = game.player_names.index(name)
        self.model = model

    def sample_choice(self, prompt: str, responses: Sequence[str], *, seed: int | None = None):
        return self.model.sample_choice(prompt, responses, seed=seed)

    def sample_text(self, prompt: str, **kwargs) -> str:
        if "Exercise: 잔디 깔기 " in prompt:
            return self._move()
        if f"Exercise: {DISCUSSION_PROMPT}" in prompt:
            action = (self._preview_speech(prompt) if self.game.phase == "talk"
                      else json.loads(self.model.sample_text(prompt, **kwargs)))
            if action.get("channel") == "whisper":
                discussion = self.game.discussion
                destination = discussion.location(action["to"])
                if discussion.location(self.name) != destination:
                    action["room"] = destination
            if self.game.discussion_notes:
                action["note"] = {
                    "move": "논의실로 이동한다. 합류한 사람과 다음 차례에 계획을 맞춘다.",
                    "speak": "제안을 전했다. 상대의 답을 보고 계획을 확정한다.",
                    "pass": "현재 계획을 유지한다. 새로운 제안을 받으면 다시 검토한다.",
                }[action["type"]]
            return json.dumps(action, ensure_ascii=False)
        return self.model.sample_text(prompt, **kwargs)

    def _preview_speech(self, prompt: str) -> DiscussionAction:
        fourth, fifth, sixth, seventh = self.game.player_names[3:7]
        proposal = f"가로수는 타일 구멍에 맞춰야 해. {fourth}와 상생으로 붙여보자."
        question = "좋아. 내 타일을 먼저 놓고 네가 옆에 붙일래?"
        answer = "응. 내 타일이 긴 변을 맞댈 수 있게 옆자리를 남겨줘."
        if self.name == fourth:
            return demo_room_speech(prompt, 1, (proposal, question), (answer, "그렇게 하자."))
        if self.name == fifth:
            return demo_room_speech(
                prompt, 1, (f"{OBSERVATION_TAG} 선택 6~8 미리보기", proposal), (question, answer)
            )
        if self.name == sixth:
            return demo_room_speech(prompt, 2 if proposal in prompt else 1)
        if self.name == seventh:
            return demo_room_speech(prompt, 1 if f"{sixth} → 2번 논의실" in prompt else 2)
        return {"type": "pass"}

    def _move(self) -> str:
        game, name = self.game, self.name
        if game.phase == "plan":
            return (
                "작은 타일로 먼저 배치하는 방안을 검토한다. 방어로 배치 선택지를 확보하고, "
                "붙일 타일을 고를 상대와 합의하면 상생을 선택한다. 구멍 모양을 보고 가로수와 맨홀을 비교한다."
            )
        if game.phase == "draft":
            preferred = (6, 9, 7, 3, 4, 6, 7, 9, 11, 6, 7, 4, 13, 9, 9, 11)
            return str(preferred[self.seat])
        if game.phase == "stance":
            return ATTACK if self.seat % 3 == 0 else DEFENSE
        if game.phase == "partner":
            first, second = game.player_names[3:5]
            partner = {first: second, second: first}.get(name)
            return f"{COOPERATE} {partner}" if partner else CHECK
        if game.phase == "obstacle":
            return MANHOLE if self.seat % 4 == 0 else TREE
        if game.phase in {"manhole", "tree"}:
            available = sorted(game.park - game.manholes.keys() - game.trees)
            rng = random.Random(self.seat)
            cells = rng.sample(available, 2 if game.phase == "manhole" else 1)
            return json.dumps(cells if game.phase == "manhole" else cells[0])
        if game.phase == "place":
            best = max(game.legal_placements(name), key=lambda move: placement_rank(game, name, move),
                       default=None)
            return json.dumps(asdict(best[0])) if best else FAIL
        if game.phase == "split":
            total = game.shared_edges[name]
            return str(total // 2 if name < game.pairs[name] else (total + 1) // 2)
        raise RuntimeError(f"Unexpected phase {game.phase}")


def placement_rank(
    game: LayTheGrass, name: str, candidate: tuple[Placement, Shape]
) -> tuple[int, int, int, int]:
    placement, shape = candidate
    partner = game.placed.get(game.pairs.get(name, ""))
    touches_partner = 0 if partner is None else sum(
        neighbor in partner.cells for cell in shape.cells for neighbor in neighbors(cell)
    )
    manhole_points = sum(game.manholes.get(cell, 0) for cell in shape.cells)
    outer_edges = sum(
        neighbor not in game.park or neighbor in game.occupied
        for cell in shape.cells for neighbor in neighbors(cell)
    )
    return touches_partner, manhole_points, -len(placement.cut), outer_edges


def make_grass_game() -> LayTheGrass:
    scores = {f"P{seat:02}": seat - 9 for seat in range(1, PLAYER_COUNT + 1)}
    return LayTheGrass(scores, tuple(reversed(scores)), discussion_rounds=DEMO_DISCUSSION_ROUNDS)


def make_grass_demo() -> Arena:
    return make_grass_arena(make_grass_game())


def make_grass_arena(game: LayTheGrass, *, wrap_backend=None) -> Arena:
    players = []
    models = demo_models(game.player_names)
    for name in game.player_names:
        model = models[name]
        if isinstance(model, str):
            model = ScriptedLanguageModel(model)
        backend = ConcordiaBackend(name, GrassDemoModel(game, name, model))
        if wrap_backend:
            backend = wrap_backend(name, backend)
        players.append(Player(name=name, role_desc="잔디 깔기 참가자", backend=backend))
    return Arena(players, game)


def main() -> None:
    arena = make_grass_demo()
    game = arena.environment
    starting_scores = game.scores
    parser = argparse.ArgumentParser(description="양자택일 미니게임 3 · 잔디 깔기")
    parser.add_argument("--player", choices=starting_scores, help="이 참가자가 볼 수 있는 대화 표시")
    args = parser.parse_args()

    play_arena(arena)
    if not game.is_terminal():
        raise RuntimeError("Lay the Grass did not reach its final scoring phase")

    print(f"양자택일 · 잔디 깔기 · 참가자 {arena.num_players}명 · 공원판 {len(game.park)}칸")
    for message in game.get_observation(args.player):
        if message.msg_type in CHANNEL_NAMES:
            print(format_speech(message))
        elif message.msg_type == "room_move":
            print(f"[이동] {message.content}")
        elif message.msg_type == "grass_plan":
            print(f"[개인 계획] {message.content}")
        elif message.msg_type == "discussion_note":
            print(f"[협상 전략] {message.content}")
    print("\n타일 배치 순서와 배치 승점")
    for message in game.get_observation():
        if message.msg_type == "grass_placement":
            move = json.loads(message.content)
            placement = move["placement"]
            detail = "실패" if placement is None else (
                f"({placement['row']},{placement['col']}) "
                f"{placement['rotation']}° 절단 {len(placement['cut'])}칸"
            )
            print(f"{message.agent_name} · {move['tile']}번 · {detail} · {move['points']:+}점")
        elif message.msg_type == "grass_bonus":
            print(message.content)

    print(f"\n최종 공원판 · 배치 성공 {len(game.placed)}/{arena.num_players}")
    print("A~P는 P01~P16 타일, # 빈 칸, T 가로수, +/- 맨홀, . 판 밖")
    print(game.render_board())
    print("\n참가자 | 시작 → 최종 승점")
    final_scores = game.scores
    for name in sorted(game.player_names, key=lambda n: (-final_scores[n], game.priority[n])):
        print(f"{name}    | {starting_scores[name]:3} → {final_scores[name]:3}")


if __name__ == "__main__":
    main()
