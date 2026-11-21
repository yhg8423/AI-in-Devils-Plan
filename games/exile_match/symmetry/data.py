"""Rigid pieces reconstructed from the actual S03E10 Symmetrical Puzzle.

Source: https://www.netflix.com/watch/82133519 (22:33 blue, 23:32 red,
25:38 green); https://www.youtube.com/watch?v=qv075JztN2Q&t=1175s
also shows the physical pieces. No production drawing is publicly available:
these are normalized photographic reconstructions, not certified dimensions.
Blue's repeated diagonal units and red's sqrt(2) lengths fit the visible
corners. Green's metric proportions were fitted jointly to assembled and
separated views (about 2.5 source pixels RMS); its topology is directly visible.
The coordinates define rigid shapes, never a board grid or required outline.
"""

from math import sqrt
from random import Random

from shapely.affinity import rotate, translate
from shapely.geometry import Polygon


_Q = sqrt(2)
_L = 1 + _Q
_A = _Q / 2

# Each row is one physical piece in a verified reference assembly. The judge
# accepts every symmetric union, rather than comparing against these fixtures.
_BLUE = (
    ((1, 0), (2, 1), (4, 1), (2, 3), (3, 4), (2, 5), (0, 3), (1, 2), (0, 1)),
    ((5, 0), (6, 1), (5, 2), (6, 3), (4, 5), (3, 4), (4, 3), (3, 2)),
)
_RED = (
    ((0, 0), (_L, _L), (0, _L)),
    ((-1, 1), (0, 1), (0, _L), (-1, _L)),
    ((_A, _A), (_Q, 0), (_Q, 1), (_L, 1), (_L, _L)),
)
_GREEN = (
    ((0, 0), (1.0143026836165832, 2.25803097424168),
     (2.302500392609719, 2.878125490762149),
     (-0.07156784534820182, 4.0838972347966545), (-36 / 41, 160 / 41)),
    ((-0.07156784534820182, 4.0838972347966545),
     (2.302500392609719, 2.878125490762149),
     (1.9803052394419005, 1.4852289295814254), (4, 3), (4, 5)),
    ((0, 0), (4, 0), (4, 3)),
)


def make_puzzles(seed):
    """Keep the same three piece sets; vary only their initial orientations."""
    if type(seed) is not int:
        raise ValueError("대칭 퍼즐 시드는 정수여야 합니다.")
    from .puzzles import COLORS, judge

    rng = Random(seed)
    puzzles = []
    for color, shapes in (("blue", _BLUE), ("red", _RED), ("green", _GREEN)):
        pieces, solution = [], []
        for index, vertices in enumerate(shapes, 1):
            original = Polygon(vertices)
            left, top, _, _ = original.bounds
            angle = rng.randrange(360)
            spun = rotate(original, angle, origin=(0, 0))
            sx, sy, _, _ = spun.bounds
            normalized = translate(spun, -sx, -sy)
            piece_id = f"{color[0].upper()}{index}"
            pieces.append({"id": piece_id, "vertices": list(normalized.exterior.coords)[:-1]})
            solution.append({"piece": piece_id, "x": left, "y": top, "rotation": (-angle) % 360})
        puzzle = {"id": color, "label": COLORS[color][0], "pieces": pieces, "solution": solution}
        if not judge(puzzle, solution):
            raise ValueError(f"{color} 조각의 기준 배치가 선대칭을 이루지 않습니다.")
        puzzles.append(puzzle)
    return puzzles
