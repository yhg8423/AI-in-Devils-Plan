"""Notched strips and discrete placement rules for the first exile puzzle."""

from functools import lru_cache
import json


SIZE = 4
SOURCE_URL = "https://puzzle-3d-phi.vercel.app/games/key/index.html"
# Notch directions and approximate depths from the public recreation's second puzzle.
_SHAPES = (
    ((0, 0, 1, 1), (58, 83, 58, 83)),
    ((0, 1, 0, 1), (58, 58, 83, 83)),
    ((0, 1, 0, 1), (83, 83, 58, 58)),
    ((0, 0, 0, 1), (83, 33, 58, 33)),
    ((0, 0, 1, 1), (83, 58, 83, 58)),
    ((1, 0, 0, 0), (83, 58, 58, 58)),
    ((0, 0, 0, 1), (58, 58, 83, 83)),
    ((0, 1, 1, 1), (83, 58, 58, 58)),
)
PIECES = tuple(f"K{number}" for number in range(1, 9))


def piece_data():
    return [{"id": name, "sides": list(sides), "depths": list(depths)}
            for name, (sides, depths) in zip(PIECES, _SHAPES, strict=True)]


def pattern(piece, reverse=False, flip=False):
    """Read the four notches in board order after reversal and vertical flipping."""
    if piece not in PIECES or type(reverse) is not bool or type(flip) is not bool:
        raise ValueError("피스 ID와 두 방향 값은 올바른 ID 및 불리언이어야 합니다.")
    sides, depths = _SHAPES[PIECES.index(piece)]
    notches = tuple((side ^ flip, depth) for side, depth in zip(sides, depths, strict=True))
    return notches[::-1] if reverse else notches


def compatible(first, second):
    return first[0] != second[0] and first[1] + second[1] >= 100


@lru_cache(maxsize=1)
def _solution():
    # Search the most constrained unfilled row/column, pruning each existing crossing.
    choices = tuple((piece, reverse, flip, pattern(piece, reverse, flip))
                    for piece in PIECES for reverse in (False, True) for flip in (False, True))
    slots = [None] * 8

    def fits(slot, candidate):
        notches = candidate[3]
        if slot < SIZE:
            return all(other is None or compatible(notches[col], other[3][slot])
                       for col, other in enumerate(slots[SIZE:]))
        return all(other is None or compatible(other[3][slot - SIZE], notches[row])
                   for row, other in enumerate(slots[:SIZE]))

    def search(used):
        if len(used) == len(PIECES):
            return tuple(slots)
        candidates = []
        for slot, current in enumerate(slots):
            if current is None:
                available = [choice for choice in choices if choice[0] not in used and fits(slot, choice)]
                if not available:
                    return None
                candidates.append((len(available), slot, available))
        _, slot, available = min(candidates, key=lambda item: (item[0], item[1]))
        for candidate in available:
            slots[slot] = candidate
            found = search(used | {candidate[0]})
            if found is not None:
                return found
        slots[slot] = None
        return None

    found = search(set())
    if found is None:
        raise ValueError("피스 퍼즐의 완성 배치를 찾을 수 없습니다.")
    return tuple((candidate[0], "row" if index < SIZE else "col", index % SIZE + 1,
                  candidate[1], candidate[2]) for index, candidate in enumerate(found))


def solution():
    """Return a fresh placement list; never expose it in a participant's setup."""
    return [dict(zip(("piece", "axis", "slot", "reverse", "flip"), item, strict=True))
            for item in _solution()]


def parse_action(text):
    action = json.loads(text)
    if not isinstance(action, dict):
        raise ValueError("JSON 행동 객체를 지정하세요.")
    kind = action.get("type")
    fields = {"place": {"type", "piece", "axis", "slot", "reverse", "flip"},
              "remove": {"type", "piece"}, "submit": {"type"}, "pass": {"type"}}
    if not isinstance(kind, str) or kind not in fields or set(action) != fields[kind]:
        raise ValueError("배치·회수·제출·패스 중 하나의 정해진 형식만 사용하세요.")
    if kind in {"place", "remove"} and action["piece"] not in PIECES:
        raise ValueError("피스 ID는 K1~K8입니다.")
    if kind == "place" and (
        action["axis"] not in ("row", "col") or type(action["slot"]) is not int
        or not 1 <= action["slot"] <= SIZE
        or type(action["reverse"]) is not bool or type(action["flip"]) is not bool
    ):
        raise ValueError("행·열, 1~4의 자리 번호, 불리언 reverse·flip을 지정하세요.")
    return action


class Board:
    def __init__(self):
        self.placements = {}

    def accepts(self, text):
        try:
            action = parse_action(text)
            return action["type"] != "remove" or action["piece"] in self.placements
        except (ValueError, TypeError, RecursionError):
            return False

    def apply(self, action):
        # Validate before changing either the moved strip or an occupied target slot.
        encoded = json.dumps(action)
        if not self.accepts(encoded):
            raise ValueError("올바른 행동과 현재 배치된 피스를 지정하세요.")
        action = parse_action(encoded)
        kind = action["type"]
        if kind == "place":
            placement = {key: value for key, value in action.items() if key != "type"}
            self.placements = {piece: existing for piece, existing in self.placements.items()
                               if piece != action["piece"] and
                               (existing["axis"], existing["slot"]) != (action["axis"], action["slot"])}
            self.placements[action["piece"]] = placement
        elif kind == "remove":
            del self.placements[action["piece"]]
        return kind == "submit" and self.solved()

    def joints(self):
        rows = {p["slot"]: p for p in self.placements.values() if p["axis"] == "row"}
        cols = {p["slot"]: p for p in self.placements.values() if p["axis"] == "col"}
        return [{"row": row, "col": col,
                 "ok": compatible(pattern(r["piece"], r["reverse"], r["flip"])[col - 1],
                                  pattern(c["piece"], c["reverse"], c["flip"])[row - 1])}
                for row, r in sorted(rows.items()) for col, c in sorted(cols.items())]

    def solved(self):
        return len(self.placements) == 8 and all(joint["ok"] for joint in self.joints())

    def snapshot(self):
        joints = self.joints()
        return {"placements": [self.placements[piece].copy() for piece in PIECES if piece in self.placements],
                "joints": joints, "errors": sum(not joint["ok"] for joint in joints),
                "placed": len(self.placements)}

    def next_action(self, target):
        if self.solved():
            return {"type": "submit"}
        return {"type": "place", **next(placement for placement in target
                                        if self.placements.get(placement["piece"]) != placement)}
