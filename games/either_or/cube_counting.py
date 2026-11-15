"""Cube-counting rules, puzzle views, and priority ranking."""

from base64 import b64encode
import heapq
from io import BytesIO
from math import cos, hypot, radians, sin

import pygame

from ..models import Review


CUBE_REVIEW_SECONDS = 5
CUBE_ELEVATION = 28
CUBE_AZIMUTHS = (32, 38, 49, 57)


def cube_height(row: int, col: int) -> int:
    """Two base layers, two opposing wedges, and four layers of diagonals above the base."""
    left, right = sorted((row, 9 - row))
    if col in (left, right):
        return 6
    return 4 if col < left or col > right else 2


def cube_image(heights: list[list[int]], *, azimuth: int) -> bytes:
    """Draw the exposed faces from an orthographic camera above a board corner."""
    board = pygame.Surface((700, 544))
    board.fill("#101820")
    image_width, image_height = board.get_size()
    rows, columns = len(heights), len(heights[0])
    angle, tilt = radians(azimuth), radians(CUBE_ELEVATION)
    row_x, col_x = -sin(angle), cos(angle)
    row_y, col_y = cos(angle) * sin(tilt), sin(angle) * sin(tilt)
    level_y = -cos(tilt)

    # Use one scale for all views, based on the widest possible board projection.
    min_x, max_x = rows * row_x, columns * col_x
    min_y = max(map(max, heights)) * level_y
    max_y = rows * row_y + columns * col_y
    board_span = hypot(rows, columns)
    margin = 32
    scale = min(
        (image_width - 2 * margin) / board_span,
        (image_height - 2 * margin) / (board_span * sin(tilt) - min_y),
    )
    origin_x = (image_width - scale * (min_x + max_x)) / 2
    origin_y = (image_height - scale * (min_y + max_y)) / 2

    def project(row, col, level):
        x = origin_x + scale * (row * row_x + col * col_x)
        y = origin_y + scale * (row * row_y + col * col_y + level * level_y)
        return round(x), round(y)

    def face(color, corners):
        points = [project(*corner) for corner in corners]
        pygame.draw.polygon(board, color, points)
        pygame.draw.polygon(board, "#362319", points, 1)

    for row, heights_row in enumerate(heights):
        for col, height in enumerate(heights_row):
            left_neighbor = heights[row + 1][col] if row + 1 < len(heights) else 0
            right_neighbor = heights_row[col + 1] if col + 1 < len(heights_row) else 0
            for level in range(height):
                top = level + 1
                left, front, right = (row + 1, col, top), (row + 1, col + 1, top), (row, col + 1, top)
                if level >= left_neighbor:
                    face("#db9039", (left, front, (row + 1, col + 1, level), (row + 1, col, level)))
                if level >= right_neighbor:
                    face("#ae632b", (front, right, (row, col + 1, level), (row + 1, col + 1, level)))
                if top == height:
                    face("#ffc97a", ((row, col, top), right, front, left))
    output = BytesIO()
    pygame.image.save(board, output, "cubes.png")
    return output.getvalue()


def cube_priority(match):
    match.event("rules", "미니게임 1 · 큐브 세기\n"
                "공개된 쌓기 문제에서 큐브의 전체 개수를 세고 개인 단말기로 답을 제출합니다. "
                "정답 여부는 제출자만 확인하며, 오답을 내면 20초가 지나야 다시 제출할 수 있습니다. "
                "정답을 맞힌 순서가 우선권 순위입니다. 15명이 맞히면 종료하고 남은 참가자는 우선권 16위입니다. "
                "우선권은 이후 승점 또는 타일 번호가 같은 참가자의 순서를 가르는 데 사용합니다.\n"
                "시뮬레이션은 참가자마다 첫 제출 시각을 가상 시간으로 정하고, 오답을 내면 20초 뒤에 다시 답을 받습니다.")
    heights = [[cube_height(row, col) for col in range(10)] for row in range(10)]
    answer = sum(map(sum, heights))
    images = []
    for azimuth in CUBE_AZIMUTHS:
        images.append(cube_image(heights, azimuth=azimuth))
        heights = [list(column) for column in zip(*reversed(heights), strict=True)]
    match.event("cube_puzzle", {"images": [b64encode(image).decode("ascii") for image in images]})
    timers = [(match.policy.randrange(5, 50), seat) for seat in range(len(match.players))]
    heapq.heapify(timers)
    wrong_guesses: dict[str, set[int]] = {name: set() for name in match.players}
    pending_reviews: dict[str, Review] = {}
    correct = []
    while len(correct) < len(match.players) - 1:
        ready, seat = heapq.heappop(timers)
        name = match.players[seat]
        wrong = wrong_guesses[name]
        review = pending_reviews.pop(name, None)
        estimate = int(review.draft) if review else answer
        if review is None and not wrong and match.policy.random() < 0.25:
            estimate += match.policy.choice((-2, -1, 1, 2))
        prompt = (
            "첨부된 네 그림은 같은 큐브 구조를 네 모서리에서 같은 높이로, 좌우 각도만 달리해 본 모습입니다. "
            "가려진 내부를 포함해 큐브 전체 개수를 세세요. note에는 개수를 어떻게 셌는지 짧게 남기세요. "
            "action에는 전체 개수만 정수 하나로 출력하세요."
        )
        if wrong:
            previous = ", ".join(map(str, sorted(wrong)))
            prompt += f"\n이전에 제출해 오답 판정을 받은 개수는 {previous}입니다."
        if review:
            prompt += "\n" + review.instructions()
        elif match.allow_review and match.live_turns > 1:
            prompt += f"\n추가 검토를 요청하면 가상 시간 {CUBE_REVIEW_SECONDS}초 뒤에 최종 답안을 제출합니다."
        action = match.decide(
            name, "cubes", prompt,
            str(max(0, estimate)), valid=lambda a: a.isascii() and a.isdecimal() and len(a) <= 4, images=images,
            offer_review=review is None,
        )
        if isinstance(action, Review):
            pending_reviews[name] = action
            heapq.heappush(timers, (ready + CUBE_REVIEW_SECONDS, seat))
            continue
        guess = int(action)
        hit = guess == answer
        match.event("cube_answer", {"player": name, "time": ready, "guess": guess, "correct": hit}, private=[name])
        if hit:
            correct.append(name)
        else:
            wrong.add(guess)
            heapq.heappush(timers, (ready + 20, seat))
    priority = correct + [name for name in match.players if name not in correct]
    match.event("priority", {"order": priority, "answer": answer})
    return priority
