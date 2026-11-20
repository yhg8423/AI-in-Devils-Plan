"""Shared piece side views and an empty target for the visual puzzle prompt."""

from functools import lru_cache
from io import BytesIO

import pygame

from .puzzle import piece_data


@lru_cache(maxsize=1)
def piece_diagram():
    pygame.font.init()
    image = pygame.Surface((1024, 960))
    image.fill("#101820")
    title = pygame.font.Font(None, 34)
    small = pygame.font.Font(None, 25)

    def text(value, position, font=small, color="#e9e6d8"):
        image.blit(font.render(value, True, color), position)

    text("PIECE PUZZLE / 8 STRIPS", (28, 22), title)
    text("Notches are shown in their original order. Numbers = side / depth.", (28, 62))
    for index, piece in enumerate(piece_data()):
        x, y = 28 + index % 2 * 500, 110 + index // 2 * 130
        text(piece["id"], (x, y + 26), title, "#efc674")
        left = x + 66
        pygame.draw.rect(image, "#d7b774", (left, y, 360, 80))
        for notch, (side, depth) in enumerate(zip(piece["sides"], piece["depths"], strict=True)):
            center = left + 54 + notch * 84
            height = round(depth * .8)
            pygame.draw.rect(image, "#101820", (center - 9, y if side == 0 else y + 80 - height, 18, height))
            text(f"{side}/{depth}", (center - 21, y + 88))
    text("TARGET: 4 ROWS x 4 COLUMNS / 16 FITTING CROSSINGS", (28, 651), title)
    for number in range(4):
        y, x = 713 + number * 48, 630 + number * 76
        pygame.draw.rect(image, "#8b7957", (580, y, 330, 9))
        pygame.draw.rect(image, "#b69b65", (x, 692, 9, 205))
        text(f"row {number + 1}", (503, y - 5))
        text(f"col {number + 1}", (x - 12, 903))
    text("0 = top notch   1 = bottom notch", (28, 725))
    text("REVERSE: read the strip backward", (28, 771))
    text("FLIP: swap every top/bottom side", (28, 817))
    text("Opposite sides; combined depth >= 100", (28, 863))
    output = BytesIO()
    pygame.image.save(image, output, "pieces.png")
    return output.getvalue()
