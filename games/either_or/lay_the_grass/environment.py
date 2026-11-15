"""Run Either Or's third minigame from Choice 5 through final scoring."""

from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict
import json

from chatarena.environments import TimeStep
from chatarena.message import Message, SYSTEM_NAME

from .choice_five import INFORMATION, OBSTACLE_RULES, PARTNER_RULES, STANCE_RULES, ChoiceFive
from .board import PARK, PARK_ROWS, TILE_ROWS, Cell, Placement, Shape, neighbors, variants


ATTACK, DEFENSE = "공격", "방어"
COOPERATE, CHECK = "상생", "견제"
TREE, MANHOLE = "가로수", "맨홀"
FAIL = "실패"
MAX_PLAN_LENGTH = 600
PHASE_LABELS = {
    "plan": "선택 6~8 비공개 구상",
    "talk": "정보 공개 뒤 협상",
    "draft": "잔디 타일 선택",
    "stance": "선택 6 · 공격 또는 방어",
    "partner": "선택 7 · 상생 또는 견제",
    "obstacle": "선택 8 · 가로수 또는 맨홀",
    "manhole": "맨홀 설치",
    "tree": "가로수 설치",
    "place": "잔디 타일 배치",
    "split": "상생 승점 분배",
    "done": "잔디 깔기 종료",
}
PHASE_RULES = {"stance": STANCE_RULES, "partner": PARTNER_RULES, "obstacle": OBSTACLE_RULES}


def _cell(value: object) -> Cell:
    if not isinstance(value, list) or len(value) != 2 or any(type(n) is not int for n in value):
        raise ValueError("Expected [row, col] with integer coordinates")
    return value[0], value[1]


class LayTheGrass(ChoiceFive):
    discussion_notes = True

    def __init__(
        self,
        initial_scores: Mapping[str, int],
        priority: Sequence[str],
        *,
        discussion_rounds: int = 0,
    ):
        super().__init__(initial_scores, discussion_rounds=discussion_rounds)
        if len(priority) != self.num_players or set(priority) != set(initial_scores):
            raise ValueError("Priority must rank each participant exactly once")
        self.priority = {name: index for index, name in enumerate(priority)}
        self.park = PARK
        self.preview_planning = True
        self._post_discussion_order = self.player_names * discussion_rounds

    @property
    def max_steps(self) -> int:
        planning_steps = self.num_players if self.preview_planning else 0
        return super().max_steps + len(self._post_discussion_order) + 7 * self.num_players + planning_steps

    def reset(self) -> TimeStep:
        self.phase: str | None = None
        self.tiles: dict[str, int] = {}
        self.stances: dict[str, str] = {}
        self.manholes: dict[Cell, int] = {}
        self.trees: set[Cell] = set()
        self.placed: dict[str, Shape] = {}
        self.occupied: set[Cell] = set()
        self.pairs: dict[str, str] = {}
        self.checkers: set[str] = set()
        self.obstacles: dict[str, str] = {}
        self.shared_edges: dict[str, int] = {}
        self.placement_order: list[str] = []
        self._turn = self._choice_turn + 2
        self._queue: deque[str] = deque()
        self._decisions: dict[str, str] = {}
        super().reset()
        self._messages.insert(
            1,
            Message(
                SYSTEM_NAME,
                "‘선택 5’의 5는 양자택일의 진행 단계 번호입니다.\n"
                f"잔디 타일 번호는 {', '.join(map(str, TILE_ROWS))}입니다.\n"
                "누적 승점이 낮은 참가자부터 타일 하나를 공개적으로 고릅니다. 같은 번호를 여러 명이 고를 수 있으며, "
                "한 번 고른 타일은 변경할 수 없습니다.\n"
                "타일 배치는 각자 고른 타일의 번호가 작은 순으로 진행합니다. "
                "두 순서 모두 동률이면 우선권 순위를 따릅니다.\n"
                "타일은 90도 단위로 회전할 수 있습니다. 뒤집기, 판 밖 배치, 타일 겹침은 금지입니다.\n"
                "기본 배치 승점은 성공 시 타일 번호, 실패 시 0점입니다. 모든 참가자가 배치 차례를 마치면 최종 승점을 정산합니다.\n"
                f"우선권 순서 {' → '.join(self.priority)}\n"
                f"시작 공원판 {len(self.park)}칸 (# 판 안, . 판 밖)\n"
                + self.render_board()
                + "\n타일 도안 N 번호 칸, # 잔디, o 구멍 있는 칸, . 타일 밖\n"
                + "\n".join(f"{number}번 {' / '.join(rows)}" for number, rows in TILE_ROWS.items()),
                turn=0,
                msg_type="grass_rules",
            ),
        )
        return TimeStep(self.get_observation(), self.get_zero_rewards(), terminal=False)

    def render_board(self) -> str:
        markers = {cell: "+" if value > 0 else "-" for cell, value in self.manholes.items()}
        markers.update(dict.fromkeys(self.trees, "T"))
        for index, name in enumerate(self.player_names):
            shape = self.placed.get(name)
            if shape:
                markers.update(dict.fromkeys(shape.cells, chr(ord("A") + index)))
        return "\n".join(
            "".join(markers.get((row, col), "#" if (row, col) in self.park else ".")
                    for col in range(len(PARK_ROWS[0])))
            for row in range(len(PARK_ROWS))
        )

    def _event(
        self, kind: str, content: str, *, speaker: str = SYSTEM_NAME,
        visible_to: str | list[str] = "all",
    ) -> None:
        self._turn += 1
        self._messages.append(Message(speaker, content, turn=self._turn, msg_type=kind, visible_to=visible_to))

    def _publish_scores(self) -> None:
        self._turn += 1
        self._messages.append(self._scoreboard(self._turn))

    def _begin(self, phase: str, players: Iterable[str] = ()) -> None:
        self.phase = phase
        self._queue = deque(players)
        self._decisions = {}
        self._event("grass_phase", PHASE_LABELS[phase])
        if phase in PHASE_RULES:
            self._event("rules", f"{PHASE_LABELS[phase]}\n{PHASE_RULES[phase]}")
        if not self._queue and phase != "done":
            self._advance()

    def _advance(self) -> None:
        if self.phase == "plan":
            self._begin("talk", self._post_discussion_order)
        elif self.phase == "talk":
            self.discussion.clear()
            self._begin("draft", sorted(self.player_names, key=lambda name: (
                self._scores[name], self.priority[name]
            )))
        elif self.phase == "draft":
            self.placement_order = sorted(self.player_names, key=lambda name: (
                self.tiles[name], self.priority[name]
            ))
            self._begin("stance", self.player_names)
        elif self.phase == "stance":
            self.stances = self._decisions
            self._reveal_choices(6)
            self._begin("partner", self.player_names)
        elif self.phase == "partner":
            for name, selection in self._decisions.items():
                if selection == CHECK:
                    self.checkers.add(name)
                    continue
                partner = selection.removeprefix(f"{COOPERATE} ")
                if self._decisions.get(partner) == f"{COOPERATE} {name}":
                    self.pairs[name] = partner
            self._reveal_choices(7)
            self._begin("obstacle", self.player_names)
        elif self.phase == "obstacle":
            self.obstacles = self._decisions
            self._reveal_choices(8)
            self._begin("manhole", (
                name for name in self.placement_order if self.obstacles[name] == MANHOLE
            ))
        elif self.phase == "manhole":
            self._begin("tree", (
                name for name in self.placement_order if self.obstacles[name] == TREE
            ))
        elif self.phase == "tree":
            self._begin("place", self.placement_order)
        elif self.phase == "place":
            self._prepare_bonuses()
        elif self.phase == "split":
            self._award_shares()
            self._begin("done")

    def _reveal_choices(self, number: int) -> None:
        self._event("grass_choices", json.dumps(
            {"choice": number, "decisions": self._decisions}, ensure_ascii=False
        ))

    def _prepare_bonuses(self) -> None:
        check_bonus = self.checkers.intersection(self.placed) if len(self.placed) <= 9 else set()
        for name in check_bonus:
            self._scores[name] += 5
        if check_bonus:
            self._event("grass_bonus", f"견제 +5점 · {', '.join(sorted(check_bonus))}")
            self._publish_scores()
        for name, partner in self.pairs.items():
            if name in self.placed and partner in self.placed:
                other_cells = self.placed[partner].cells
                edges = sum(
                    neighbor in other_cells
                    for cell in self.placed[name].cells for neighbor in neighbors(cell)
                )
                if edges:
                    self.shared_edges[name] = edges
        self._begin("split", self.shared_edges)

    def _award_shares(self) -> None:
        resolved = set()
        points_changed = False
        for name, total in self.shared_edges.items():
            partner = self.pairs[name]
            if name in resolved:
                continue
            resolved.update((name, partner))
            share, other_share = int(self._decisions[name]), int(self._decisions[partner])
            if share + other_share == total:
                self._scores[name] += share
                self._scores[partner] += other_share
                self._event("grass_bonus", f"상생 · {name} +{share}, {partner} +{other_share}")
                points_changed = True
            else:
                self._event("grass_bonus", f"상생 분배 미합의 · {name}, {partner}")
        if points_changed:
            self._publish_scores()

    def is_terminal(self) -> bool:
        return super().is_terminal() if self.phase is None else self.phase == "done"

    def get_next_player(self) -> str:
        if self.phase is None:
            return super().get_next_player()
        if self.is_terminal():
            raise RuntimeError("Lay the Grass has already ended")
        return self._queue[0]

    def simultaneous_players(self) -> tuple[str, ...]:
        if self.phase is None:
            return super().simultaneous_players()
        if self.phase in {"plan", "stance", "partner", "obstacle", "split"}:
            return tuple(self._queue)
        return ()

    def get_observation(self, player_name: str | None = None) -> list[Message]:
        messages = super().get_observation(player_name)
        if self._queue and (player_name == self._queue[0] or player_name in self.simultaneous_players()):
            if self.phase == "talk":
                messages.append(self.discussion.request(
                    player_name, self._turn + 1,
                    "선택 5가 끝났습니다. 지금은 잔디 타일을 고르기 전 협상입니다. "
                    "공개 타일 목록과 본인이 받은 정보를 바탕으로 계획을 논의할 수 있습니다.",
                    action_index=len(self._post_discussion_order) - len(self._queue), notes=self.discussion_notes,
                ))
            else:
                messages.append(Message(
                    SYSTEM_NAME, self._prompt(player_name), turn=self._turn + 1,
                    visible_to=[player_name], msg_type="grass_request",
                ))
        return messages

    def _prompt(self, name: str) -> str:
        instructions = {
            "plan": "받은 미리보기를 바탕으로 협상 전에 볼 짧은 비공개 전략 메모를 작성하세요. "
                    "타일 후보, 선택 6~8의 잠정 선택과 바꿀 조건, 협상 상대와 공유할 정보를 정리하세요. "
                    "승점과 순위에 미칠 영향도 고려하세요. "
                    f"계획은 이후 판세에 따라 바꿀 수 있습니다. {MAX_PLAN_LENGTH}자 이내의 메모만 출력하세요.",
            "draft": f"타일 번호 하나를 출력하세요. 가능한 번호는 {', '.join(map(str, TILE_ROWS))}입니다.",
            "stance": f"{STANCE_RULES}\n공격 또는 방어만 출력하세요.",
            "partner": f"{PARTNER_RULES}\n"
                       "견제를 고르면 견제만 출력하세요. 상생을 고르면 상생 뒤에 다른 참가자의 ID를 붙이세요. "
                       "출력은 JSON이 아닌 한 줄의 문자열입니다. 예시는 견제 또는 상생 P03입니다.",
            "obstacle": f"{OBSTACLE_RULES}\n가로수 또는 맨홀만 출력하세요.",
            "manhole": "+1과 -1을 각각 빈 칸에 두세요. [[plus_row,plus_col],[minus_row,minus_col]] 형식.",
            "tree": "맨홀이 없는 빈 칸에 가로수 하나를 두세요. [행,열] 형식의 JSON 배열 하나만 출력하세요.",
            "place": "타일을 배치하세요. 좌표를 직접 제출할 때는 "
                     "{\"row\":0,\"col\":0,\"rotation\":90,\"cut\":[]} 형식을 사용하세요. "
                     "회전은 0/90/180/270도, cut은 원래 타일 좌표입니다. "
                     "방어의 두 칸은 붙어 있어야 하며 번호 칸을 자르거나 타일을 분리하거나 "
                     "새로 둘러싸인 빈 칸을 만들 수 없습니다. 배치를 마치지 못하면 실패를 출력하세요.",
            "split": "팀 추가 승점 중 본인이 받을 점수를 정수로 출력하세요. "
                     "두 참가자의 요청 합이 팀 점수와 같아야 합니다.",
        }[self.phase]
        if self.phase in {"manhole", "tree", "place"}:
            instructions += "\n좌표는 왼쪽 위 (0,0) 기준입니다. # 빈 칸, . 판 밖, T 가로수, "
            instructions += "+/- 맨홀, A~P 배치된 타일.\n" + self.render_board()
        if self.phase == "place":
            tile = self.tiles[name]
            instructions += f"\n내 타일 {tile}번, 선택 {self.stances[name]}.\n"
            instructions += "\n".join(TILE_ROWS[tile])
        if self.phase == "split":
            instructions += f"\n팀원 {self.pairs[name]}, 팀 추가 승점 {self.shared_edges[name]}점."
        if self.simultaneous_players():
            instructions = "다른 참가자의 이번 답안을 보기 전에 내 순위와 생존을 고려해 제출하세요.\n" + instructions
        return f"잔디 깔기 {PHASE_LABELS[self.phase]}\n{instructions}"

    def _fits(self, shape: Shape) -> bool:
        return (
            shape.cells <= self.park
            and not shape.cells & self.occupied
            and (shape.cells & self.trees) <= shape.holes
        )

    def legal_placements(self, name: str) -> Iterable[tuple[Placement, Shape]]:
        for template, shape in variants(self.tiles[name], self.stances[name] == DEFENSE):
            rows = len(PARK_ROWS) - max(r for r, _ in shape.cells)
            cols = len(PARK_ROWS[0]) - max(c for _, c in shape.cells)
            for row in range(rows):
                for col in range(cols):
                    cells = frozenset((row + r, col + c) for r, c in shape.cells)
                    if not cells <= self.park or cells & self.occupied:
                        continue
                    candidate = Shape(cells, frozenset((row + r, col + c) for r, c in shape.holes))
                    if self._fits(candidate):
                        yield Placement(row, col, template.rotation, template.cut), candidate

    def _validate(self, name: str, action: str, *, simultaneous=False):
        if self.is_terminal() or (
            name not in self.simultaneous_players() if simultaneous else name != self.get_next_player()
        ):
            raise ValueError(f"It is not {name}'s turn")
        action = action.strip()
        if self.phase == "plan" and 0 < len(action) <= MAX_PLAN_LENGTH:
            return action
        if self.phase == "talk":
            return self.discussion.parse(name, action, self._turn + 1, notes=self.discussion_notes)
        if self.phase == "draft" and action in tuple(map(str, TILE_ROWS)):
            return int(action)
        if self.phase == "stance" and action in (ATTACK, DEFENSE):
            return action
        if self.phase == "partner":
            if action == CHECK or (
                action.startswith(f"{COOPERATE} ")
                and action.removeprefix(f"{COOPERATE} ") in self.player_names
                and action != f"{COOPERATE} {name}"
            ):
                return action
        if self.phase == "obstacle" and action in (TREE, MANHOLE):
            return action
        if self.phase in {"tree", "manhole"}:
            data = json.loads(action)
            if self.phase == "tree":
                cells = (_cell(data),)
            else:
                if not isinstance(data, list) or len(data) != 2:
                    raise ValueError("Expected two manhole cells")
                cells = tuple(_cell(cell) for cell in data)
            if len(set(cells)) != len(cells) or any(
                cell not in self.park or cell in self.manholes or cell in self.trees for cell in cells
            ):
                raise ValueError("An obstacle must use an empty park cell")
            return cells
        if self.phase == "place":
            if action == FAIL:
                return None
            data = json.loads(action)
            if not isinstance(data, dict) or data.keys() != {"row", "col", "rotation", "cut"}:
                raise ValueError("Expected a placement")
            if any(type(data[key]) is not int for key in ("row", "col", "rotation")):
                raise ValueError("Placement coordinates and rotation must be integers")
            if not isinstance(data["cut"], list) or len(data["cut"]) > 2:
                raise ValueError("Expected zero to two cut cells")
            placement = Placement(data["row"], data["col"], data["rotation"],
                                  tuple(_cell(cell) for cell in data["cut"]))
            shape = placement.shape(self.tiles[name], defense=self.stances[name] == DEFENSE)
            if not self._fits(shape):
                raise ValueError("The tile overlaps a tile, a tree without a hole, or the board edge")
            return placement, shape
        if self.phase == "split" and action in tuple(map(str, range(self.shared_edges[name] + 1))):
            return action
        raise ValueError(f"Invalid action in {self.phase}")

    def check_action(self, action: str, player_name: str, *, simultaneous=False) -> bool:
        if self.phase is None:
            return super().check_action(action, player_name, simultaneous=simultaneous)
        try:
            self._validate(player_name, action, simultaneous=simultaneous)
        except (ValueError, RecursionError):
            return False
        return True

    def _place(self, name: str, action: tuple[Placement, Shape] | None) -> None:
        number = self.tiles[name]
        attacking = self.stances[name] == ATTACK
        if action is None:
            points = -4 if attacking else 0
        else:
            placement, shape = action
            self.placed[name] = shape
            self.occupied.update(shape.cells)
            points = number * (2 if attacking else 1) + sum(
                self.manholes.get(cell, 0) for cell in shape.cells
            )
        self._scores[name] += points
        self._event("grass_placement", json.dumps({
            "tile": number,
            "placement": None if action is None else asdict(placement),
            "cells": [] if action is None else sorted(shape.cells),
            "points": points,
        }), speaker=name)
        if points:
            self._publish_scores()

    def step(self, player_name: str, action: str, *, note: str = "") -> TimeStep:
        if self.phase is None:
            result = super().step(player_name, action, note=note)
            if result.terminal:
                informed = [name for name, choice in self._submissions.items() if choice == INFORMATION]
                if self.preview_planning and informed:
                    self._begin("plan", informed)
                else:
                    self._begin("talk", self._post_discussion_order)
                return TimeStep(self.get_observation(), result.reward, terminal=False)
            return result
        decision = self._validate(player_name, action)
        if note:
            self._turn += 1
            self._record_decision_note(player_name, self.phase, note, self._turn)
        before = self.scores
        if self.phase == "plan":
            self._event("grass_plan", decision, speaker=player_name, visible_to=[player_name])
        elif self.phase == "talk":
            if decision is not None:
                self._turn += 1
                self._messages.extend(self.discussion.record(player_name, decision, self._turn))
        elif self.phase == "draft":
            self.tiles[player_name] = decision
            self._event("grass_tile", str(decision), speaker=player_name)
        elif self.phase == "manhole":
            self.manholes[decision[0]] = 1
            self.manholes[decision[1]] = -1
            self._event("grass_obstacle", json.dumps({"+": decision[0], "-": decision[1]}),
                        speaker=player_name)
        elif self.phase == "tree":
            self.trees.add(decision[0])
            self._event("grass_obstacle", json.dumps({"tree": decision[0]}), speaker=player_name)
        elif self.phase == "place":
            self._place(player_name, decision)
        else:
            self._decisions[player_name] = decision
        self._queue.popleft()
        if not self._queue:
            self._advance()
        rewards = {name: score - before[name] for name, score in self._scores.items()}
        return TimeStep(self.get_observation(), rewards, terminal=self.is_terminal())
