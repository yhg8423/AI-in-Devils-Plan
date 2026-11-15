"""Grid and tile geometry for Lay the Grass."""

from dataclasses import dataclass
from functools import cache
from itertools import combinations


Cell = tuple[int, int]

# Coordinates follow the public diagram, top to bottom and left to right.
PARK_ROWS = (
    "..................###.....",
    "......###..##....####.....",
    "......#.#.###########.....",
    "##..###.###.########......",
    "#######.....#########.....",
    "#######......########.....",
    "######......##########....",
    "..###.......##########....",
    "............####.##.#.....",
    "....................#..###",
    "....................######",
    ".......................###",
)
PARK = frozenset(
    (row, col)
    for row, line in enumerate(PARK_ROWS)
    for col, cell in enumerate(line)
    if cell == "#"
)

# N is the numbered cell, o has a tree hole, # is solid, . is outside the tile.
TILE_ROWS = {
    3: ("###", "##N", "###", ".#."),
    4: ("##.", "oN.", "##o", "##."),
    6: (".#o", ".#N", "o#.", "o#."),
    7: (".o.", ".#N", "o#o", "o.."),
    9: (".o", "#N", "oo", ".o", ".o"),
    11: ("oo..", ".oN.", "..oo", "...o"),
    13: ("ooN", "ooo", "ooo"),
}


def neighbors(cell: Cell) -> tuple[Cell, ...]:
    row, col = cell
    return ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1))


def _reachable(start: Cell, allowed: set[Cell]) -> set[Cell]:
    reached = {start}
    pending = [start]
    while pending:
        for neighbor in neighbors(pending.pop()):
            if neighbor in allowed and neighbor not in reached:
                reached.add(neighbor)
                pending.append(neighbor)
    return reached


def _has_enclosed_empty_cell(cells: set[Cell]) -> bool:
    top = min(row for row, _ in cells) - 1
    left = min(col for _, col in cells) - 1
    bottom = max(row for row, _ in cells) + 1
    right = max(col for _, col in cells) + 1
    empty = {
        (row, col)
        for row in range(top, bottom + 1)
        for col in range(left, right + 1)
    } - cells
    return _reachable((top, left), empty) != empty


@dataclass(frozen=True)
class Shape:
    cells: frozenset[Cell]
    holes: frozenset[Cell]


@dataclass(frozen=True)
class Placement:
    row: int
    col: int
    rotation: int
    cut: tuple[Cell, ...] = ()

    def shape(self, number: int, *, defense: bool) -> Shape:
        if not defense and self.cut:
            raise ValueError("Only defense permits cutting a tile")
        shape = tile_shape(number, self.rotation, self.cut)
        return Shape(
            frozenset((self.row + r, self.col + c) for r, c in shape.cells),
            frozenset((self.row + r, self.col + c) for r, c in shape.holes),
        )


def _tile_cells(number: int) -> dict[Cell, str]:
    return {
        (row, col): cell
        for row, line in enumerate(TILE_ROWS[number])
        for col, cell in enumerate(line)
        if cell != "."
    }


@cache
def tile_shape(number: int, rotation: int, cut: tuple[Cell, ...] = ()) -> Shape:
    cells = _tile_cells(number)
    removed = set(cut)
    if (
        len(cut) > 2
        or len(removed) != len(cut)
        or any(cells.get(cell) not in {"#", "o"} for cell in cut)
        or (len(cut) == 2 and cut[1] not in neighbors(cut[0]))
    ):
        raise ValueError("Invalid cut")
    remaining = set(cells) - removed
    if cut and (
        _reachable(next(iter(remaining)), remaining) != remaining
        or _has_enclosed_empty_cell(remaining)
    ):
        raise ValueError("The cut disconnects the tile or creates an enclosed gap")
    if rotation not in (0, 90, 180, 270):
        raise ValueError("Tiles rotate in quarter turns")
    rotated = {}
    for row, col in remaining:
        target_row, target_col = row, col
        for _ in range(rotation // 90):
            target_row, target_col = target_col, -target_row
        rotated[target_row, target_col] = cells[row, col]
    top = min(row for row, _ in rotated)
    left = min(col for _, col in rotated)
    return Shape(
        frozenset((row - top, col - left) for row, col in rotated),
        frozenset((row - top, col - left) for (row, col), cell in rotated.items() if cell == "o"),
    )


@cache
def variants(number: int, defense: bool) -> tuple[tuple[Placement, Shape], ...]:
    removable = [cell for cell, marker in _tile_cells(number).items() if marker != "N"]
    cuts = [()]
    if defense:
        cuts.extend(combinations(removable, 1))
        cuts.extend(pair for pair in combinations(removable, 2) if pair[1] in neighbors(pair[0]))
    unique = {}
    for cut in cuts:
        for rotation in (0, 90, 180, 270):
            try:
                shape = tile_shape(number, rotation, cut)
            except ValueError:
                continue
            unique.setdefault(shape, Placement(0, 0, rotation, cut))
    return tuple((placement, shape) for shape, placement in unique.items())
