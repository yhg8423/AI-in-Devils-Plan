"""Public board geometry, exact fives, and the PNG shown to both models."""

from base64 import b64encode
from hashlib import sha256
from io import BytesIO

import pygame


SIZE = 15
DIRECTIONS = ((1, 0), (0, 1), (1, 1), (1, -1))
WIDTH = HEIGHT = 800


def empty_board():
    return [[None] * SIZE for _ in range(SIZE)]


def legal_triples(grid):
    """All three consecutive empty intersections, without jumping a stone."""
    return [[[x + step * dx + 1, y + step * dy + 1] for step in range(3)]
            for y in range(SIZE) for x in range(SIZE) for dx, dy in DIRECTIONS
            if all(0 <= x + step * dx < SIZE and 0 <= y + step * dy < SIZE
                   and grid[y + step * dy][x + step * dx] is None for step in range(3))]


def five_lines(grid, player):
    """Count maximal runs of exactly five; crossing fives count separately."""
    lines = []
    for y in range(SIZE):
        for x in range(SIZE):
            if grid[y][x] != player:
                continue
            for dx, dy in DIRECTIONS:
                previous_x, previous_y = x - dx, y - dy
                if (0 <= previous_x < SIZE and 0 <= previous_y < SIZE
                        and grid[previous_y][previous_x] == player):
                    continue
                points, xx, yy = [], x, y
                while 0 <= xx < SIZE and 0 <= yy < SIZE and grid[yy][xx] == player:
                    points.append([xx + 1, yy + 1])
                    xx, yy = xx + dx, yy + dy
                if len(points) == 5:
                    lines.append(points)
    return lines


def stone_list(grid):
    return [{"x": x + 1, "y": y + 1, "player": player}
            for y, row in enumerate(grid) for x, player in enumerate(row) if player is not None]


def board(grid, players, *, selected=(), winning_lines=None):
    """No budgets or bids enter this public image or its metadata."""
    pygame.font.init()
    image = pygame.Surface((WIDTH, HEIGHT))
    image.fill("#111b28")
    font = pygame.font.Font(None, 25)
    small = pygame.font.Font(None, 20)
    title = pygame.font.Font(None, 34)

    def label(text, position, color="#26333c", face=font):
        rendered = face.render(str(text), True, color)
        image.blit(rendered, rendered.get_rect(center=position))

    label("POINT GOMOKU", (172, 27), "#f2d29a", title)
    label(f"BLACK {players[0]} / WHITE {players[1]}", (573, 27), "#f0e6d2", font)
    pygame.draw.rect(image, "#c6ac78", (35, 58, 730, 720), border_radius=7)
    origin_x, origin_y, step = 78, 100, 46
    point = lambda x, y: (origin_x + (x - 1) * step, origin_y + (y - 1) * step)
    for index in range(SIZE):
        pygame.draw.line(image, "#594830", point(index + 1, 1), point(index + 1, SIZE), 1)
        pygame.draw.line(image, "#594830", point(1, index + 1), point(SIZE, index + 1), 1)
        label(index + 1, (origin_x + index * step, 77), face=small)
        label(index + 1, (53, origin_y + index * step), face=small)
    for x, y in ((4, 4), (12, 4), (8, 8), (4, 12), (12, 12)):
        pygame.draw.circle(image, "#594830", point(x, y), 4)
    for stone in stone_list(grid):
        black = stone["player"] == players[0]
        center = point(stone["x"], stone["y"])
        pygame.draw.circle(image, "#e3b45c" if black else "#37647a", center, 19)
        pygame.draw.circle(image, "#172330" if black else "#fff8e8", center, 16)
    for lines in (winning_lines or {}).values():
        for line in lines:
            pygame.draw.line(image, "#db3549", point(*line[0]), point(*line[-1]), 4)
    for index, coordinates in enumerate(selected):
        center = point(*coordinates)
        pygame.draw.circle(image, "#d33352", center, 21, 4)
        label(chr(65 + index), center, "#a91637", font)
    stream = BytesIO()
    pygame.image.save(image, stream, "PNG")
    png = stream.getvalue()
    return {"id": sha256(png).hexdigest()[:16], "width": WIDTH, "height": HEIGHT,
            "image": "data:image/png;base64," + b64encode(png).decode("ascii")}
