"""Continuous polygon placement, arbitrary reflection axes, and private PNGs."""

from base64 import b64encode
from hashlib import sha256
from io import BytesIO
from math import atan2, cos, degrees, floor, hypot, isfinite, log10, pi, sin, sqrt
from pathlib import Path

import pygame
from shapely import symmetric_difference, union_all
from shapely.affinity import affine_transform, rotate, translate
from shapely.errors import GEOSException
from shapely.geometry import Polygon


WIDTH, HEIGHT = 960, 640
NUMERIC_LIMIT = 1_000_000
RELATIVE_TOLERANCE = 1e-7
COLORS = {"blue": ("파랑", "#2671bc"), "red": ("빨강", "#c34450"), "green": ("초록", "#318755")}


def _number(value):
    return type(value) in (int, float) and abs(value) <= NUMERIC_LIMIT and isfinite(value)


def _piece_polygon(piece):
    vertices = piece["vertices"]
    if (not isinstance(vertices, (list, tuple)) or not 3 <= len(vertices) <= 256
            or any(not isinstance(point, (list, tuple)) or len(point) != 2
                   or not all(_number(value) for value in point) for point in vertices)):
        raise ValueError("조각에는 유한한 좌표의 다각형 꼭짓점이 필요합니다.")
    polygon = Polygon(vertices)
    if polygon.is_empty or not polygon.is_valid or polygon.area <= 0:
        raise ValueError("조각은 넓이가 있는 단순 다각형이어야 합니다.")
    return polygon


def placement_polygon(puzzle, placement):
    """Only an orientation-preserving rotation and translation can place a piece."""
    if (not isinstance(placement, dict) or set(placement) != {"piece", "x", "y", "rotation"}
            or not isinstance(placement["piece"], str)
            or not all(_number(placement[key]) for key in ("x", "y", "rotation"))):
        raise ValueError("조각 ID와 유한한 x/y/회전 각도만 지정하세요. 뒤집기는 허용하지 않습니다.")
    pieces = {piece["id"]: piece for piece in puzzle["pieces"]}
    if placement["piece"] not in pieces:
        raise ValueError("해당 색의 조각 ID를 지정하세요.")
    # Positive rotation is clockwise in the PNG's downward-positive y coordinates.
    polygon = rotate(_piece_polygon(pieces[placement["piece"]]), placement["rotation"] % 360, origin=(0, 0))
    left, top, _, _ = polygon.bounds
    return translate(polygon, placement["x"] - left, placement["y"] - top)


def align_placement(puzzle, command, previous_placements):
    """Apply exactly the participant's chosen edge direction and vertex coincidence."""
    keys = {"piece", "edge", "vertex", "to_piece", "to_edge", "to_vertex"}
    if (not isinstance(command, dict) or set(command) != keys
            or not isinstance(command["piece"], str) or not isinstance(command["to_piece"], str)
            or command["piece"] == command["to_piece"] or not isinstance(previous_placements, list)):
        raise ValueError("조각과 대상 조각의 변·꼭짓점을 정확히 지정하세요.")
    pieces = {piece["id"]: piece for piece in puzzle["pieces"]}
    if command["piece"] not in pieces or command["to_piece"] not in pieces:
        raise ValueError("같은 색에 있는 서로 다른 조각을 지정하세요.")
    for key, piece_id in (("edge", command["piece"]), ("vertex", command["piece"]),
                          ("to_edge", command["to_piece"]), ("to_vertex", command["to_piece"])):
        if type(command[key]) is not int or not 0 <= command[key] < len(pieces[piece_id]["vertices"]):
            raise ValueError("변과 꼭짓점 번호는 그림에 표시된 0부터 시작하는 정수여야 합니다.")
    targets = [placement for placement in previous_placements
               if isinstance(placement, dict) and placement.get("piece") == command["to_piece"]]
    if len(targets) != 1 or any(isinstance(placement, dict) and placement.get("piece") == command["piece"]
                               for placement in previous_placements):
        raise ValueError("대상 조각을 먼저 한 번 배치하고 새 조각을 연결하세요.")
    source = list(_piece_polygon(pieces[command["piece"]]).exterior.coords)[:-1]
    target = list(placement_polygon(puzzle, targets[0]).exterior.coords)[:-1]
    a, b = source[command["edge"]], source[(command["edge"] + 1) % len(source)]
    c, d = target[command["to_edge"]], target[(command["to_edge"] + 1) % len(target)]
    if a == b or c == d:
        raise ValueError("길이가 있는 변을 지정하세요.")
    angle = degrees(atan2(d[1] - c[1], d[0] - c[0]) - atan2(b[1] - a[1], b[0] - a[0]) + pi) % 360
    result = {"piece": command["piece"], "x": 0, "y": 0, "rotation": angle}
    normalized = list(placement_polygon(puzzle, result).exterior.coords)[:-1]
    vertex, destination = normalized[command["vertex"]], target[command["to_vertex"]]
    result["x"], result["y"] = destination[0] - vertex[0], destination[1] - vertex[1]
    placement_polygon(puzzle, result)  # Apply the same finite numeric limits as direct placement.
    return result


def _edge_contact(first, second, tolerance):
    """Recognize a shared segment despite rotation roundoff; a shared point is insufficient."""
    for ring_a in (first.exterior, *first.interiors):
        points_a = list(ring_a.coords)
        for a, b in zip(points_a, points_a[1:]):
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = hypot(dx, dy)
            if length <= tolerance:
                continue
            ux, uy = dx / length, dy / length
            for ring_b in (second.exterior, *second.interiors):
                points_b = list(ring_b.coords)
                for c, d in zip(points_b, points_b[1:]):
                    if (abs((c[0] - a[0]) * uy - (c[1] - a[1]) * ux) > tolerance
                            or abs((d[0] - a[0]) * uy - (d[1] - a[1]) * ux) > tolerance):
                        continue
                    positions = [(point[0] - a[0]) * ux + (point[1] - a[1]) * uy for point in (c, d)]
                    if min(length, max(positions)) - max(0, min(positions)) > tolerance:
                        return True
    return False


def assembled_shape(puzzle, placements):
    """Use every piece once, without area overlap, joined by positive-length contacts."""
    if not isinstance(placements, list) or not puzzle["pieces"] or len(placements) != len(puzzle["pieces"]):
        return None
    try:
        if len({placement["piece"] for placement in placements}) != len(placements):
            return None
        polygons = [placement_polygon(puzzle, placement) for placement in placements]
        scale = sqrt(sum(polygon.area for polygon in polygons) / len(polygons))
        tolerance = scale * RELATIVE_TOLERANCE
        neighbors = [set() for _ in polygons]
        for index, polygon in enumerate(polygons):
            for other in range(index):
                if polygon.intersection(polygons[other]).area > tolerance * scale:
                    return None
                if _edge_contact(polygon, polygons[other], tolerance):
                    neighbors[index].add(other)
                    neighbors[other].add(index)
        visited, pending = set(), [0]
        while pending:
            index = pending.pop()
            if index not in visited:
                visited.add(index)
                pending.extend(neighbors[index] - visited)
        # Overlay precision is far finer than the rule tolerance, but removes
        # roundoff-only cracks where independently rotated shared edges meet.
        return union_all(polygons, grid_size=tolerance * .001) if len(visited) == len(polygons) else None
    except (ValueError, TypeError, KeyError, GEOSException):
        return None


def reflection_axes(shape):
    """Return polygonal reflection-axis angles, clockwise from x, modulo 180 degrees."""
    if shape is None or shape.is_empty or not shape.is_valid or shape.area <= 0:
        return []
    center = shape.centroid
    tolerance = sqrt(shape.area) * RELATIVE_TOLERANCE
    hull = list(shape.convex_hull.simplify(tolerance * .001).exterior.coords)[:-1]
    # Independent rotations can leave roundoff-width inward slits or tiny holes.
    # Buffer only the boundary comparison; retain the original area comparison below.
    stable_boundary = shape.buffer(tolerance, join_style=2).boundary
    vx, vy = hull[0][0] - center.x, hull[0][1] - center.y
    candidates = []
    # Reflection preserves the convex hull, mapping its first vertex to another vertex.
    # Every reflection axis also passes through the shape's area centroid.
    for x, y in hull:
        dx, dy = vx + x - center.x, vy + y - center.y
        if hypot(dx, dy) <= tolerance:
            dx, dy = -vy, vx
        angle = atan2(dy, dx) % pi
        if not any(min(abs(angle - previous), pi - abs(angle - previous)) < 1e-9 for previous in candidates):
            candidates.append(angle)
    axes = []
    for angle in sorted(candidates):
        c, s = cos(2 * angle), sin(2 * angle)
        transform = [c, s, s, -c,
            center.x * (1 - c) - center.y * s, center.y * (1 + c) - center.x * s]
        reflected = affine_transform(shape, transform)
        if (symmetric_difference(shape, reflected, grid_size=tolerance * .001).area <= shape.area * RELATIVE_TOLERANCE
                and stable_boundary.hausdorff_distance(affine_transform(stable_boundary, transform)) <= tolerance * 4):
            axes.append(round(degrees(angle), 9) % 180)
    return axes


def judge(puzzle, placements):
    return bool(reflection_axes(assembled_shape(puzzle, placements)))


def make_puzzles(seed):
    # Recovered broadcast geometry has one separate source of truth.
    from .data import make_puzzles as load_puzzles
    return load_puzzles(seed)


def _label_layout(labels, bounds, *, radii=(0, 12, 24, 38, 54, 74)):
    """Separate nearby labels while preserving every exact geometry anchor."""
    bounds = pygame.Rect(bounds)
    placed = []
    for value, anchor, preferred, size in labels:
        candidates = []
        for radius in radii:
            for direction in range(8):
                angle = direction * pi / 4
                center = (preferred[0] + radius * cos(angle), preferred[1] + radius * sin(angle))
                rectangle = pygame.Rect(0, 0, *size)
                rectangle.center = tuple(round(coordinate) for coordinate in center)
                rectangle.clamp_ip(bounds)
                if any(rectangle.inflate(4, 4).colliderect(previous[2]) for previous in placed):
                    continue
                if any(rectangle.collidepoint(other[1]) for other in labels):
                    continue
                distance = hypot(rectangle.centerx - preferred[0], rectangle.centery - preferred[1])
                candidates.append((distance, rectangle))
            if candidates:
                break
        if not candidates:
            raise ValueError("조각 표시를 겹치지 않게 배치할 공간이 부족합니다.")
        rectangle = min(candidates, key=lambda candidate: candidate[0])[1]
        placed.append((value, anchor, rectangle))
    return placed


def board(puzzle, placements=(), *, detailed=False, language="en"):
    """Render polygons at a common tray scale and auto-fit the private workspace."""
    if detailed:
        return _detailed_board(puzzle, placements, language=language)
    pygame.font.init()
    factor = 2
    surface = pygame.Surface((WIDTH * factor, HEIGHT * factor))
    surface.fill("#111d2e")
    fonts = {size: pygame.font.Font(None, size * factor) for size in (14, 18, 20, 24, 30)}

    def text(value, size, color, position, *, center=False):
        label = fonts[size].render(value, True, color)
        position = tuple(round(value * factor) for value in position)
        surface.blit(label, label.get_rect(center=position) if center else position)

    def rectangle(color, bounds, radius=0):
        pygame.draw.rect(surface, color, tuple(round(value * factor) for value in bounds), border_radius=radius * factor)

    def index_labels(labels, bounds):
        sizes = {value: ((fonts[14].size(value)[0] + factor - 1) // factor + 4,
                         (fonts[14].size(value)[1] + factor - 1) // factor + 2) for value, _, _ in labels}
        routed = _label_layout([(value, anchor, preferred, sizes[value]) for value, anchor, preferred in labels], bounds)
        for value, anchor, rectangle in routed:
            endpoint = (min(max(anchor[0], rectangle.left), rectangle.right),
                        min(max(anchor[1], rectangle.top), rectangle.bottom))
            color = "#9a6672" if value.startswith("v") else "#557f96"
            pygame.draw.line(surface, color, tuple(round(coordinate * factor) for coordinate in anchor),
                             tuple(round(coordinate * factor) for coordinate in endpoint), factor)
            pygame.draw.circle(surface, color, tuple(round(coordinate * factor) for coordinate in anchor), factor)
        for value, anchor, rectangle in routed:
            label = fonts[14].render(value, True, "#633645" if value.startswith("v") else "#234d64")
            bounds = pygame.Rect(*(coordinate * factor for coordinate in rectangle))
            pygame.draw.rect(surface, "#faf9ee", bounds, border_radius=2 * factor)
            surface.blit(label, label.get_rect(center=bounds.center))

    def polygon(shape, transform, fill):
        points = [tuple(round(value * factor) for value in transform(x, y)) for x, y in shape.exterior.coords]
        pygame.draw.polygon(surface, fill, points)
        pygame.draw.lines(surface, "#253d50", True, points, factor * 2)
        for ring in shape.interiors:
            points = [tuple(round(value * factor) for value in transform(x, y)) for x, y in ring.coords]
            pygame.draw.polygon(surface, "#f6f4ea", points)
            pygame.draw.lines(surface, "#253d50", True, points, factor * 2)

    color = pygame.Color(COLORS[puzzle["id"]][1])
    pieces = [(piece, _piece_polygon(piece)) for piece in puzzle["pieces"]]
    placed = {placement["piece"] for placement in placements}
    text(f"{puzzle['id'].upper()} / SYMMETRICAL PUZZLE", 30, "#f5dfb6", (23, 18))
    text("ROTATE FREELY / NO FLIPS", 20, "#d7e5f3", (635, 25))
    text("PIECE TRAY / SAME SCALE", 24, "#d7e5f3", (24, 57))
    text("FREE PLACEMENT", 24, "#d7e5f3", (570, 57))
    columns = 1 if len(pieces) <= 3 else 2
    rows = (len(pieces) + columns - 1) // columns
    card_width = 360 / columns - (10 if columns > 1 else 0)
    card_height = 506 / max(rows, 1) - 10
    tray_scale = min((card_width - 58) / max(shape.bounds[2] - shape.bounds[0] for _, shape in pieces),
                     (card_height - 75) / max(shape.bounds[3] - shape.bounds[1] for _, shape in pieces))
    for index, (piece, shape) in enumerate(pieces):
        x, y = 22 + index % columns * 183, 87 + index // columns * (card_height + 10)
        rectangle("#e9edf0", (x, y, card_width, card_height), 8)
        text(piece["id"], 24, "#172d44", (x + 10, y + 8))
        text("PLACED" if piece["id"] in placed else "TRAY", 18, "#405a70", (x + card_width - 75, y + 12))
        left, top, right, bottom = shape.bounds
        ox = x + (card_width - (right - left) * tray_scale) / 2 - left * tray_scale
        oy = y + 39 + (card_height - 49 - (bottom - top) * tray_scale) / 2 - top * tray_scale
        polygon(shape, lambda px, py: (ox + px * tray_scale, oy + py * tray_scale), color)
        vertices = list(shape.exterior.coords)[:-1]
        center = shape.centroid
        labels = []
        for number, ((ax, ay), (bx, by)) in enumerate(zip(vertices, vertices[1:] + vertices[:1])):
            dx, dy = ax - center.x, ay - center.y
            length = hypot(dx, dy) or 1
            labels.append((f"v{number}", (ox + ax * tray_scale, oy + ay * tray_scale),
                           (ox + ax * tray_scale + dx / length * 12, oy + ay * tray_scale + dy / length * 12)))
            dx, dy = bx - ax, by - ay
            length = hypot(dx, dy) or 1
            sign = 1 if shape.exterior.is_ccw else -1
            labels.append((f"e{number}", (ox + (ax + bx) / 2 * tray_scale, oy + (ay + by) / 2 * tray_scale),
                           (ox + (ax + bx) / 2 * tray_scale + sign * dy / length * 11,
                            oy + (ay + by) / 2 * tray_scale - sign * dx / length * 11)))
        index_labels(labels, (x + 5, y + 33, card_width - 10, card_height - 38))
    workspace = (421, 86, 511, 501)
    rectangle("#f6f4ea", workspace, 10)
    working = [(placement, placement_polygon(puzzle, placement)) for placement in placements]
    if working:
        bounds = [shape.bounds for _, shape in working]
        left, top = min(value[0] for value in bounds), min(value[1] for value in bounds)
        right, bottom = max(value[2] for value in bounds), max(value[3] for value in bounds)
    else:
        left = top = 0
        right = max(shape.bounds[2] - shape.bounds[0] for _, shape in pieces) * 2
        bottom = max(shape.bounds[3] - shape.bounds[1] for _, shape in pieces) * 2
    width, height = max(right - left, 1e-12), max(bottom - top, 1e-12)
    unit = min((workspace[2] - 74) / width, (workspace[3] - 74) / height)
    ox = workspace[0] + (workspace[2] - width * unit) / 2 - left * unit
    oy = workspace[1] + (workspace[3] - height * unit) / 2 - top * unit
    transform = lambda x, y: (ox + x * unit, oy + y * unit)
    for index, (placement, shape) in enumerate(working):
        polygon(shape, transform, color.lerp(pygame.Color("#ffffff"), .08 * (index % 4)))
    for placement, shape in working:
        points = [tuple(round(value * factor) for value in transform(x, y)) for x, y in shape.exterior.coords]
        pygame.draw.lines(surface, "#253d50", True, points, factor * 2)
        point = shape.representative_point()
        text(placement["piece"], 20, "#ffffff", transform(point.x, point.y), center=True)
    text(f"x {left:.4g} .. {right:.4g}   y {top:.4g} .. {bottom:.4g}", 18, "#405a70", (438, 566))
    text(f"PLACED {len(placements)} / {len(puzzle['pieces'])}", 24, "#d7e5f3", (24, 612))
    text("x: right / y: down / anchor: rotated bounding-box top-left", 18, "#d7e5f3", (425, 612))
    output = BytesIO()
    pygame.image.save(pygame.transform.smoothscale(surface, (WIDTH, HEIGHT)), output, "symmetry.png")
    png = output.getvalue()
    return {"id": sha256(png).hexdigest()[:16], "width": WIDTH, "height": HEIGHT,
            "image": "data:image/png;base64," + b64encode(png).decode("ascii")}


def _png_view(surface, name):
    output = BytesIO()
    pygame.image.save(surface, output, name)
    png = output.getvalue()
    return {"id": sha256(png).hexdigest()[:16], "width": surface.get_width(), "height": surface.get_height(),
            "image": "data:image/png;base64," + b64encode(png).decode("ascii")}


def _graphics_text(surface, value, font, color, position, *, center=False):
    label = font.render(value, True, color)
    position = tuple(round(coordinate) for coordinate in position)
    surface.blit(label, label.get_rect(center=position) if center else position)


def _graphics_polygon(surface, shape, transform, fill, outline="#173a50", width=3, background="#f6f4ea"):
    points = [tuple(round(coordinate) for coordinate in transform(x, y)) for x, y in shape.exterior.coords]
    pygame.draw.polygon(surface, fill, points)
    if width:
        pygame.draw.lines(surface, outline, True, points, width)
    for ring in shape.interiors:
        points = [tuple(round(coordinate) for coordinate in transform(x, y)) for x, y in ring.coords]
        pygame.draw.polygon(surface, background, points)
        if width:
            pygame.draw.lines(surface, outline, True, points, width)


def _polygon_annotations(shape, transform, *, prefix="", distance=28):
    vertices = list(shape.exterior.coords)[:-1]
    center = shape.centroid
    labels = []
    for number, ((ax, ay), (bx, by)) in enumerate(zip(vertices, vertices[1:] + vertices[:1])):
        anchor = transform(ax, ay)
        dx, dy = ax - center.x, ay - center.y
        length = hypot(dx, dy) or 1
        labels.append((f"{prefix}v{number}", anchor,
                       (anchor[0] + dx / length * distance, anchor[1] + dy / length * distance)))
        anchor = transform((ax + bx) / 2, (ay + by) / 2)
        dx, dy = bx - ax, by - ay
        length = hypot(dx, dy) or 1
        sign = 1 if shape.exterior.is_ccw else -1
        labels.append((f"{prefix}e{number}", anchor,
                       (anchor[0] + sign * dy / length * distance, anchor[1] - sign * dx / length * distance)))
    return labels


def _draw_annotations(surface, labels, font, bounds):
    sized = [(value, anchor, preferred, (font.size(value)[0] + 10, font.size(value)[1] + 6))
             for value, anchor, preferred in labels]
    routed = _label_layout(sized, bounds, radii=(0, 20, 40, 70, 110, 160, 220, 300, 400, 550, 750))
    for value, anchor, rectangle in routed:
        endpoint = (min(max(anchor[0], rectangle.left), rectangle.right),
                    min(max(anchor[1], rectangle.top), rectangle.bottom))
        color = "#975867" if value.split(".")[-1].startswith("v") else "#376e8c"
        pygame.draw.line(surface, color, anchor, endpoint, 2)
        pygame.draw.circle(surface, color, tuple(round(coordinate) for coordinate in anchor), 3)
    for value, anchor, rectangle in routed:
        color = "#633645" if value.split(".")[-1].startswith("v") else "#234d64"
        pygame.draw.rect(surface, "#fffef5", rectangle, border_radius=3)
        _graphics_text(surface, value, font, color, rectangle.center, center=True)
    return routed


def _prose_fonts(language, korean_sizes, english_sizes):
    font = str(Path(__file__).resolve().parents[3] / "web/ui/assets/Galmuri11-Bold.ttf") if language == "ko" else None
    return tuple(pygame.font.Font(font, size) for size in (korean_sizes if language == "ko" else english_sizes))


def piece_atlas(puzzle, *, language="en"):
    """Public, independently enlarged pieces; no placements or solution data are read."""
    pygame.font.init()
    surface = pygame.Surface((1440, 1100))
    surface.fill("#111d2e")
    korean = language == "ko"
    title, body = _prose_fonts(language, (32, 22), (44, 30))
    label = pygame.font.Font(None, 32)
    _graphics_text(surface, f"{COLORS[puzzle['id']][0]} / 조각 확대도" if korean else f"{puzzle['id'].upper()} / PIECE ATLAS",
                   title, "#f5dfb6", (36, 25))
    _graphics_text(surface, "조각별 확대 · 배율이 서로 다름 · 뒤집기 금지" if korean else "INDIVIDUAL ZOOM / SCALES DIFFER / NO FLIPS",
                   body, "#d7e5f3", (36, 78))
    gap, margin = 24, 36
    card_width = (surface.get_width() - margin * 2 - gap * (len(puzzle["pieces"]) - 1)) / len(puzzle["pieces"])
    color = pygame.Color(COLORS[puzzle["id"]][1])
    for index, piece in enumerate(puzzle["pieces"]):
        card = pygame.Rect(round(margin + index * (card_width + gap)), 133, round(card_width), 870)
        pygame.draw.rect(surface, "#e9edf0", card, border_radius=12)
        _graphics_text(surface, piece["id"], title, "#172d44", (card.x + 22, card.y + 18))
        shape = _piece_polygon(piece)
        left, top, right, bottom = shape.bounds
        _graphics_text(surface, f"가로 {right-left:.4g} / 세로 {bottom-top:.4g}" if korean else f"width {right-left:.4g} / height {bottom-top:.4g}",
                       body, "#405a70", (card.x + 22, card.y + 66))
        unit = min((card.width - 120) / (right - left), (card.height - 270) / (bottom - top))
        ox = card.centerx - (left + right) / 2 * unit
        oy = card.y + 120 + (card.height - 270) / 2 - (top + bottom) / 2 * unit
        # A positive uniform scale preserves the original chirality, order, and orientation.
        transform = lambda x, y: (ox + x * unit, oy + y * unit)
        _graphics_polygon(surface, shape, transform, color)
        _draw_annotations(surface, _polygon_annotations(shape, transform, distance=38), label,
                          (card.x + 10, card.y + 103, card.width - 20, card.height - 208))
        target_units = (card.width - 90) / unit
        magnitude = 10 ** floor(log10(target_units))
        ruler_units = max(value * magnitude for value in (1, 2, 5) if value * magnitude <= target_units)
        length = ruler_units * unit
        x, y = card.centerx - length / 2, card.bottom - 68
        pygame.draw.line(surface, "#405a70", (x, y), (x + length, y), 3)
        for end in (x, x + length):
            pygame.draw.line(surface, "#405a70", (end, y - 8), (end, y + 8), 3)
        _graphics_text(surface, f"{ruler_units:g} 단위" if korean else f"{ruler_units:g} units", body, "#405a70", (card.centerx, y + 28), center=True)
    _graphics_text(surface, "vN: 꼭짓점 / eN: vN에서 다음 꼭짓점으로 가는 변 / 원래 번호 순서 유지" if korean else
                   "vN: vertex / eN: directed edge from vN to the next vertex / labels keep the original order",
                   body, "#d7e5f3", (36, 1045))
    return _png_view(surface, "symmetry-atlas.png")


def _detailed_board(puzzle, placements, *, language="en"):
    """A larger editing view with ownership and geometric overlaps, without symmetry hints."""
    pygame.font.init()
    surface = pygame.Surface((WIDTH, HEIGHT))
    surface.fill("#111d2e")
    korean = language == "ko"
    title, body = _prose_fonts(language, (26, 18), (34, 22))
    label = pygame.font.Font(None, 22)
    _graphics_text(surface, f"{COLORS[puzzle['id']][0]} / 현재 작업판" if korean else f"{puzzle['id'].upper()} / CURRENT ASSEMBLY",
                   title, "#f5dfb6", (28, 20))
    _graphics_text(surface, "조각 ID가 붙은 꼭짓점 v·변 e / 원래 조각 모양은 확대도 참고" if korean else
                   "Piece-prefixed v/e labels / separate atlas for larger original pieces", body, "#d7e5f3", (28, 62))
    workspace = pygame.Rect(28, 100, 904, 476)
    pygame.draw.rect(surface, "#f6f4ea", workspace, border_radius=10)
    working = [(value, placement_polygon(puzzle, value)) for value in placements]
    if not working:
        _graphics_text(surface, "배치한 조각 없음 · 조각 확대도를 참고하세요" if korean else
                       "No pieces placed / use the separate piece atlas", title, "#677b88", workspace.center, center=True)
    else:
        bounds = [shape.bounds for _, shape in working]
        left, top = min(value[0] for value in bounds), min(value[1] for value in bounds)
        right, bottom = max(value[2] for value in bounds), max(value[3] for value in bounds)
        unit = min((workspace.width - 150) / (right - left), (workspace.height - 110) / (bottom - top))
        ox = workspace.centerx - (left + right) / 2 * unit
        oy = workspace.centery - (top + bottom) / 2 * unit
        transform = lambda x, y: (ox + x * unit, oy + y * unit)
        color = pygame.Color(COLORS[puzzle["id"]][1])
        outlines = ("#123d58", "#682c59", "#725018")
        for index, (value, shape) in enumerate(working):
            _graphics_polygon(surface, shape, transform, color.lerp(pygame.Color("#ffffff"), .12 * (index % 3)))
        mask = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        for index, (_, first) in enumerate(working):
            for _, second in working[:index]:
                overlap = first.intersection(second)
                regions = [overlap] if overlap.geom_type == "Polygon" else getattr(overlap, "geoms", ())
                for region in regions:
                    if region.geom_type == "Polygon" and region.area * unit * unit > .5:
                        part = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
                        _graphics_polygon(part, region, transform, (255, 255, 255, 255), width=0, background=(0, 0, 0, 0))
                        mask.blit(part, (0, 0), special_flags=pygame.BLEND_RGBA_MAX)
        hatch = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        for x in range(workspace.left - workspace.height, workspace.right, 12):
            pygame.draw.line(hatch, "#f36bba", (x, workspace.top), (x + workspace.height, workspace.bottom), 2)
        hatch.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(hatch, (0, 0))
        annotations = []
        for index, (value, shape) in enumerate(working):
            points = [tuple(round(coordinate) for coordinate in transform(x, y)) for x, y in shape.exterior.coords]
            pygame.draw.lines(surface, outlines[index % len(outlines)], True, points, 4)
            annotations.extend(_polygon_annotations(shape, transform, prefix=value["piece"] + ".", distance=24))
        _draw_annotations(surface, annotations, label, workspace.inflate(-10, -10))
        for value, shape in working:
            point = shape.representative_point()
            _graphics_text(surface, value["piece"], title, "#ffffff", transform(point.x, point.y), center=True)
        _graphics_text(surface, f"x {left:.5g} .. {right:.5g} / y {top:.5g} .. {bottom:.5g}", body, "#d7e5f3", (28, 590))
    _graphics_text(surface, f"배치 {len(placements)} / {len(puzzle['pieces'])} · 빗금은 겹친 영역" if korean else
                   f"PLACED {len(placements)} / {len(puzzle['pieces'])} / hatching marks overlapping area",
                   body, "#d7e5f3", (28, 615))
    return _png_view(surface, "symmetry-edit.png")
