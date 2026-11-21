"""Authored clue families and a flattened, publicly shared 26-card board."""

from base64 import b64encode
from hashlib import sha256
from io import BytesIO
from itertools import combinations
from math import cos, pi, sin
from random import Random
from string import ascii_uppercase

import pygame


WIDTH, HEIGHT = 960, 640
COLORS = {"red": ("빨강", "#d32f46"), "blue": ("파랑", "#2468cc"),
          "green": ("초록", "#23854a"), "gold": ("금색", "#be8408"),
          "purple": ("보라", "#8748b9")}
SHAPES = {"circle": "원", "triangle": "삼각형", "square": "정사각형",
          "diamond": "마름모", "star": "별"}


def satisfies(cards, clue):
    """Evaluate only public card attributes, never the stored solution."""
    ordered = sorted(cards, key=lambda card: card["number"])
    numbers = [card["number"] for card in ordered]
    kind, value = clue["kind"], clue["value"]
    if kind == "sum":
        return sum(numbers) == value
    if kind == "distinct":
        return len({card[clue["attribute"]] for card in cards}) == value
    if kind == "odd":
        return sum(number % 2 for number in numbers) == value
    if kind == "gap":
        return numbers[clue["high"]] - numbers[clue["low"]] == value
    if kind == "rank":
        return ordered[clue["rank"]][clue["attribute"]] == value
    raise ValueError(f"Unknown clue: {kind}")


def solutions(cards, clues):
    return ["".join(card["letter"] for card in group)
            for group in combinations(sorted(cards, key=lambda card: card["letter"]), 4)
            if all(satisfies(group, clue) for clue in clues)]


def _clues(cards):
    ordered = sorted(cards, key=lambda card: card["number"])
    numbers = [card["number"] for card in ordered]
    total = sum(numbers)
    clues = [{"kind": "sum", "value": total,
              "text": f"네 카드의 숫자를 모두 더하면 {total}입니다.",
              "en": f"The four numbers add up to {total}."}]
    for attribute, ko, en in (("color", "색", "colors"), ("shape", "도형", "shapes")):
        count = len({card[attribute] for card in cards})
        clues.append({"kind": "distinct", "attribute": attribute, "value": count,
                      "text": f"서로 다른 {ko}은 정확히 {count}종류입니다.",
                      "en": f"There are exactly {count} different {en}."})
    odds = sum(number % 2 for number in numbers)
    clues.append({"kind": "odd", "value": odds,
                  "text": f"홀수 카드가 정확히 {odds}장입니다.",
                  "en": f"Exactly {odds} cards have odd numbers."})
    for low, high in ((0, 3), (0, 1), (1, 2), (2, 3)):
        gap = numbers[high] - numbers[low]
        clues.append({"kind": "gap", "low": low, "high": high, "value": gap,
                      "text": f"숫자가 작은 순서로 {high + 1}번째와 {low + 1}번째 카드의 차는 {gap}입니다.",
                      "en": f"In ascending number order, card {high + 1} minus card {low + 1} is {gap}."})
    for rank, card in enumerate(ordered):
        for attribute, labels, ko, en in (("color", COLORS, "색", "color"), ("shape", SHAPES, "도형", "shape")):
            value = card[attribute]
            label = labels[value][0] if attribute == "color" else labels[value]
            clues.append({"kind": "rank", "rank": rank, "attribute": attribute, "value": value,
                          "text": f"숫자가 작은 순서로 {rank + 1}번째 카드의 {ko}은 {label}입니다.",
                          "en": f"In ascending number order, card {rank + 1}'s {en} is {value}."})
    return clues


def make_puzzle(seed):
    """Choose useful clues, then exhaustively prove exactly one of 14,950 answers."""
    if type(seed) is not int:
        raise ValueError("비밀 코드 시드는 정수여야 합니다.")
    rng = Random(seed)
    numbers = rng.sample(range(1, 27), 26)
    colors = list(COLORS) * 6
    shapes = list(SHAPES) * 6
    rng.shuffle(colors)
    rng.shuffle(shapes)
    cards = [{"letter": letter, "number": number, "color": colors[index], "shape": shapes[index]}
             for index, (letter, number) in enumerate(zip(ascii_uppercase, numbers, strict=True))]
    answer = sorted(rng.sample(cards, 4), key=lambda card: card["letter"])
    candidates = _clues(answer)
    clues = candidates[:3]
    remaining = [group for group in combinations(cards, 4)
                 if all(satisfies(group, clue) for clue in clues)]
    extras = candidates[3:]
    rng.shuffle(extras)
    while len(remaining) > 1:
        clue = min(extras, key=lambda item: sum(satisfies(group, item) for group in remaining))
        extras.remove(clue)
        clues.append(clue)
        remaining = [group for group in remaining if satisfies(group, clue)]
    clues = [{"id": f"C{index}", **clue} for index, clue in enumerate(clues, 1)]
    solution = "".join(card["letter"] for card in answer)
    if solutions(cards, clues) != [solution]:
        raise ValueError("비밀 코드 문제는 정답이 정확히 하나여야 합니다.")
    return {"cards": cards, "clues": clues, "solution": solution}


def board(puzzle):
    """Draw one opaque PNG; models receive these exact bytes, with no answer layer."""
    pygame.font.init()
    surface = pygame.Surface((WIDTH, HEIGHT))
    surface.fill("#101b2b")
    fonts = {size: pygame.font.Font(None, size) for size in (18, 24, 38, 40)}

    def text(value, size, color, position, *, center=False):
        label = fonts[size].render(value, True, color)
        surface.blit(label, label.get_rect(center=position) if center else position)

    text("SECRET CODE", 38, "#f5dfb1", (30, 13))
    text("26 CARDS / 4 LETTERS / ALPHABETICAL ORDER", 24, "#d9e2ef", (450, 21))
    for index, card in enumerate(puzzle["cards"]):
        x, y = 30 + index % 7 * 130, 61 + index // 7 * 142
        rectangle = pygame.Rect(x, y, 120, 132)
        pygame.draw.rect(surface, "#f8f7f0", rectangle, border_radius=9)
        pygame.draw.rect(surface, "#b4c3d4", rectangle, width=2, border_radius=9)
        text(card["letter"], 40, "#162239", (x + 9, y + 6))
        number = fonts[38].render(str(card["number"]), True, "#162239")
        surface.blit(number, (x + 109 - number.get_width(), y + 8))
        color, shape = COLORS[card["color"]][1], card["shape"]
        cx, cy, radius = x + 60, y + 69, 25
        if shape == "circle":
            pygame.draw.circle(surface, color, (cx, cy), radius)
        elif shape == "square":
            pygame.draw.rect(surface, color, (cx - 23, cy - 23, 46, 46))
        else:
            count = 10 if shape == "star" else 3 if shape == "triangle" else 4
            points = [(cx + cos(-pi / 2 + step * 2 * pi / count) * (radius if shape != "star" or step % 2 == 0 else 11),
                       cy + sin(-pi / 2 + step * 2 * pi / count) * (radius if shape != "star" or step % 2 == 0 else 11))
                      for step in range(count)]
            pygame.draw.polygon(surface, color, points)
        text(card["color"].upper(), 18, "#26364d", (cx, y + 108), center=True)
        text(shape.upper(), 18, "#26364d", (cx, y + 123), center=True)
    text("A-Z", 40, "#f5dfb1", (810, 535))
    text("ALL CLUES MUST HOLD", 18, "#d9e2ef", (753, 583))
    output = BytesIO()
    pygame.image.save(surface, output, "code-board.png")
    png = output.getvalue()
    return {"id": sha256(png).hexdigest()[:16], "width": WIDTH, "height": HEIGHT,
            "image": "data:image/png;base64," + b64encode(png).decode("ascii")}
