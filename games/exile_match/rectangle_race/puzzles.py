"""Signed-number rectangle puzzles and their shared public raster boards."""

from base64 import b64encode
from hashlib import sha256
from io import BytesIO
from random import Random

import pygame

from ...either_or.rectangle_counting import count_rectangles


WIDTH, HEIGHT = 960, 640


def make_puzzle(seed, number=1, *, pack="full_grid_v2"):
    if pack not in ("authored_v1", "full_grid_v2"):
        raise ValueError("지원하지 않는 네모 세기 문제 구성입니다.")
    rng = Random(seed)
    if number == 1:
        # An authored alternating-sign puzzle; the correct count is 24.
        values = [[(-1) ** (row * 5 + col) * (row * 5 + col + 1) for col in range(5)] for row in range(4)]
        target = 0
    elif number == 2:
        # 41 + 51 + 3*37 reaches 203, but no rectangle has that arrangement.
        # The whole board exceeds the target, so its total cannot reveal zero.
        values = ([[41, 51, 37]] if pack == "authored_v1" else
                  [[41, 0, 37, 51, 0], [0, 51, 0, 41, 37], [37, 0, 41, 0, 51],
                   [51, 41, 0, 37, 0], [0, 37, 51, 0, 41]])
        target = 203
    else:
        rows, columns = rng.randrange(4, 7), rng.randrange(4, 7)
        values = [[rng.choice((0, 0, *range(-9, 21))) for _ in range(columns)] for _ in range(rows)]
        top, bottom = sorted(rng.sample(range(rows + 1), 2))
        left, right = sorted(rng.sample(range(columns + 1), 2))
        target = sum(values[row][col] for row in range(top, bottom) for col in range(left, right))
    if rng.randrange(2):
        values = list(reversed(values))
    if rng.randrange(2):
        values = [list(reversed(row)) for row in values]
    return {"values": values, "target": target, "answer": count_rectangles(values, target)}


def board(puzzle):
    pygame.font.init()
    surface = pygame.Surface((WIDTH, HEIGHT))
    surface.fill("#111c2c")
    title = pygame.font.Font(None, 34).render("COUNT THE RECTANGLES", True, "#f2deb0")
    surface.blit(title, (30, 20))
    target = pygame.font.Font(None, 38).render(f"TARGET SUM: {puzzle['target']}", True, "#f2deb0")
    surface.blit(target, (WIDTH - target.get_width() - 30, 17))
    values = puzzle["values"]
    rows, columns = len(values), len(values[0])
    cell = min(110, 830 // columns, 460 // rows)
    left, top = (WIDTH - columns * cell) // 2, 96 + (460 - rows * cell) // 2
    font = pygame.font.Font(None, max(28, cell // 2))
    for row, line in enumerate(values):
        for col, value in enumerate(line):
            rect = pygame.Rect(left + col * cell, top + row * cell, cell, cell)
            pygame.draw.rect(surface, "#f7f4ec", rect)
            pygame.draw.rect(surface, "#8b9aac", rect, width=2)
            if value:
                label = font.render(str(value), True, "#a42f48" if value < 0 else "#172239")
                surface.blit(label, label.get_rect(center=rect.center))
    note = pygame.font.Font(None, 25).render("EMPTY CELLS = 0 / ONE CELL ALSO COUNTS", True, "#c8d3e1")
    surface.blit(note, note.get_rect(center=(WIDTH // 2, 603)))
    stream = BytesIO()
    pygame.image.save(surface, stream, "rectangle-board.png")
    png = stream.getvalue()
    return {"id": sha256(png).hexdigest()[:16], "width": WIDTH, "height": HEIGHT,
            "image": "data:image/png;base64," + b64encode(png).decode("ascii"), "alt": "숫자가 표시된 네모 세기 문제판"}
