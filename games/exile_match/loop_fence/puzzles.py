"""Unique Slitherlink boards, geometric verification, and shared raster views."""

from base64 import b64encode
from hashlib import sha256
from io import BytesIO
from random import Random

import pygame


WIDTH, HEIGHT = 960, 640


def all_edges(rows, cols):
    return tuple(("H", row, col) for row in range(rows + 1) for col in range(cols)) + tuple(
        ("V", row, col) for row in range(rows) for col in range(cols + 1))


def endpoints(edge):
    kind, row, col = edge
    return ((row, col), (row, col + 1)) if kind == "H" else ((row, col), (row + 1, col))


def cell_edges(row, col):
    return (("H", row, col), ("H", row + 1, col), ("V", row, col), ("V", row, col + 1))


def _one_loop(edges):
    if not edges:
        return False
    adjacent = {}
    for edge in edges:
        a, b = endpoints(edge)
        adjacent.setdefault(a, set()).add(b)
        adjacent.setdefault(b, set()).add(a)
    if any(len(neighbors) != 2 for neighbors in adjacent.values()):
        return False
    seen, pending = set(), [next(iter(adjacent))]
    while pending:
        point = pending.pop()
        if point not in seen:
            seen.add(point)
            pending.extend(adjacent[point] - seen)
    return len(seen) == len(adjacent)


def judge(puzzle, edges):
    """Check rules from public clues rather than comparing a secret answer array."""
    rows = cols = puzzle["size"]
    clues = puzzle["clues"]
    try:
        marked = set(map(tuple, edges))
    except TypeError:
        return False
    if len(marked) != len(edges) or not marked <= set(all_edges(rows, cols)) or not _one_loop(marked):
        return False
    return all(value is None or sum(edge in marked for edge in cell_edges(row, col)) == value
               for row, line in enumerate(clues) for col, value in enumerate(line))


def solve(clues, limit=2):
    """Enumerate up to limit loops using cell and vertex constraint propagation."""
    if (not isinstance(clues, list) or not clues or not isinstance(clues[0], list) or not clues[0]
            or any(not isinstance(line, list) or len(line) != len(clues[0])
                   or any(value is not None and (type(value) is not int or not 0 <= value <= 3)
                          for value in line) for line in clues)):
        raise ValueError("울타리 단서는 직사각형의 0~3 또는 빈칸이어야 합니다.")
    rows, cols = len(clues), len(clues[0])
    edges = all_edges(rows, cols)
    indices = {edge: index for index, edge in enumerate(edges)}
    cells = [(tuple(indices[edge] for edge in cell_edges(row, col)), value)
             for row, line in enumerate(clues) for col, value in enumerate(line) if value is not None]
    vertices = {}
    for index, edge in enumerate(edges):
        for point in endpoints(edge):
            vertices.setdefault(point, []).append(index)
    constraints = [(group, (value,)) for group, value in cells] + [
        (tuple(group), (0, 2)) for group in vertices.values()]
    answers = []

    def search(values):
        while True:
            changed = False
            for group, allowed in constraints:
                total = sum(values[index] == 1 for index in group)
                unknown = [index for index in group if values[index] == -1]
                possible = [value for value in allowed if total <= value <= total + len(unknown)]
                if not possible:
                    return
                if unknown and (max(possible) == total or min(possible) == total + len(unknown)):
                    value = int(min(possible) == total + len(unknown))
                    for index in unknown:
                        values[index] = value
                    changed = True
            # A completed component must be the only loop: every other edge is off.
            on = [index for index, value in enumerate(values) if value == 1]
            adjacent = {}
            for index in on:
                for point in endpoints(edges[index]):
                    adjacent.setdefault(point, []).append(index)
            visited = set()
            for first in adjacent:
                if first in visited:
                    continue
                component, pending = set(), [first]
                while pending:
                    point = pending.pop()
                    if point in component:
                        continue
                    component.add(point)
                    for index in adjacent[point]:
                        pending.extend(endpoints(edges[index]))
                visited.update(component)
                if all(len(adjacent[point]) == 2 for point in component):
                    if len(component) != len(adjacent):
                        return
                    for index, value in enumerate(values):
                        if value == -1:
                            values[index] = 0
                            changed = True
                    break
            if not changed:
                break
        unknown = [index for index, value in enumerate(values) if value == -1]
        if not unknown:
            answer = [edges[index] for index in on]
            if _one_loop(answer):
                answers.append(answer)
            return
        # Prefer an edge in a nearly determined numbered cell or used vertex.
        weights = dict.fromkeys(unknown, 0)
        for group, allowed in constraints:
            unsettled = [index for index in group if values[index] == -1]
            weight = 8 - len(unsettled) + int(any(values[index] == 1 for index in group))
            for index in unsettled:
                weights[index] += weight
        index = max(unknown, key=weights.get)
        for value in (1, 0):
            branch = values.copy()
            branch[index] = value
            search(branch)
            if len(answers) >= limit:
                return

    if type(limit) is not int or limit < 1:
        raise ValueError("해답 검색 상한은 1 이상의 정수여야 합니다.")
    search([-1] * len(edges))
    return answers


def _boundary(cells):
    result = set()
    for row, col in cells:
        for neighbor, edge in (((row - 1, col), ("H", row, col)),
                               ((row + 1, col), ("H", row + 1, col)),
                               ((row, col - 1), ("V", row, col)),
                               ((row, col + 1), ("V", row, col + 1))):
            if neighbor not in cells:
                result.add(edge)
    return result


def make_puzzle(seed, size=7):
    """Grow a simple boundary and retain blanks only after proving uniqueness."""
    if type(seed) is not int or type(size) is not int or not 3 <= size <= 8:
        raise ValueError("정수 시드와 3~8칸의 크기가 필요합니다.")
    rows = cols = size
    rng = Random(seed)
    for _ in range(40):
        inside = {(rows // 2, cols // 2)}
        target = rng.randrange(rows * cols // 3, rows * cols * 2 // 3 + 1)
        while len(inside) < target:
            frontier = sorted({(row + dr, col + dc) for row, col in inside
                               for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1))
                               if 0 <= row + dr < rows and 0 <= col + dc < cols} - inside)
            rng.shuffle(frontier)
            addition = next((cell for cell in frontier if _one_loop(_boundary(inside | {cell}))), None)
            if addition is None:
                break
            inside.add(addition)
        solution = sorted(_boundary(inside))
        clues = [[sum(edge in solution for edge in cell_edges(row, col))
                  for col in range(cols)] for row in range(rows)]
        if any(value > 3 for line in clues for value in line) or len(solve(clues)) != 1:
            continue
        positions = [(row, col) for row in range(rows) for col in range(cols)]
        rng.shuffle(positions)
        blanks = 0
        # ponytail: leave most clues for an image-only model; remove more if real runs prove too easy.
        for row, col in positions:
            value, clues[row][col] = clues[row][col], None
            if len(solve(clues)) == 1:
                blanks += 1
                if blanks >= max(3, rows * cols // 5):
                    break
            else:
                clues[row][col] = value
        if blanks:
            return {"size": size, "clues": clues, "solution": solution}
    raise ValueError("유일한 울타리 문제를 생성하지 못했습니다.")


def board(puzzle, edges=(), crosses=()):
    """Flatten the shared puzzle and this player's marks into one opaque PNG."""
    pygame.font.init()
    surface = pygame.Surface((WIDTH, HEIGHT))
    surface.fill("#111d2e")
    fonts = {size: pygame.font.Font(None, size) for size in (20, 25, 38, 40)}

    def text(value, size, color, position, *, center=False):
        label = fonts[size].render(value, True, color)
        surface.blit(label, label.get_rect(center=position) if center else position)

    rows = cols = puzzle["size"]
    cell = min(76, 448 // rows, 680 // cols)
    left, top = (WIDTH - cols * cell) // 2, 94
    pygame.draw.rect(surface, "#f6f4ea", (left - 29, top - 29, cols * cell + 58, rows * cell + 58), border_radius=12)
    text("LOOP FENCE", 40, "#f3d5a2", (30, 19))
    text("ONE CLOSED LOOP", 25, "#dce6f3", (700, 29))
    for col in range(cols + 1):
        text(str(col), 20, "#40546c", (left + col * cell, top - 17), center=True)
    for row in range(rows + 1):
        text(str(row), 20, "#40546c", (left - 17, top + row * cell), center=True)
    for row, line in enumerate(puzzle["clues"]):
        for col, value in enumerate(line):
            if value is not None:
                text(str(value), 38, "#172c43", (left + (col + .5) * cell, top + (row + .5) * cell), center=True)
    for edge in all_edges(rows, cols):
        a, b = endpoints(edge)
        pygame.draw.line(surface, "#d1d5cf", (left + a[1] * cell, top + a[0] * cell),
                         (left + b[1] * cell, top + b[0] * cell), 1)
    for edge in edges:
        a, b = endpoints(edge)
        pygame.draw.line(surface, "#b76a19", (left + a[1] * cell, top + a[0] * cell),
                         (left + b[1] * cell, top + b[0] * cell), 6)
    for edge in crosses:
        a, b = endpoints(edge)
        x, y = left + (a[1] + b[1]) * cell / 2, top + (a[0] + b[0]) * cell / 2
        pygame.draw.line(surface, "#b45160", (x - 6, y - 6), (x + 6, y + 6), 3)
        pygame.draw.line(surface, "#b45160", (x - 6, y + 6), (x + 6, y - 6), 3)
    for row in range(rows + 1):
        for col in range(cols + 1):
            pygame.draw.circle(surface, "#263f54", (left + col * cell, top + row * cell), 4)
    text(f"EDGES {len(edges)}   /   CROSSES {len(crosses)}", 25, "#dce6f3", (30, 588))
    text("H r c: (r,c)-(r,c+1)    V r c: (r,c)-(r+1,c)", 20, "#dce6f3", (450, 592))
    output = BytesIO()
    pygame.image.save(surface, output, "loop-fence.png")
    png = output.getvalue()
    return {"id": sha256(png).hexdigest()[:16], "width": WIDTH, "height": HEIGHT,
            "image": "data:image/png;base64," + b64encode(png).decode("ascii")}
