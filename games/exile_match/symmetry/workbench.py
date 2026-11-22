"""Show current geometry and a participant-requested centroid-axis reflection."""

from base64 import b64decode
from io import BytesIO
from math import atan2, cos, degrees, hypot, isfinite, radians, sin, sqrt

import pygame
from shapely import union_all
from shapely.affinity import affine_transform
from shapely.geometry import MultiPolygon

from .puzzles import (
    COLORS, _graphics_polygon, _graphics_text, _piece_polygon, _png_view, _prose_fonts,
    piece_atlas, placement_polygon,
)


def _parts(shape):
    if shape.geom_type == "Polygon":
        yield shape
    else:
        for part in getattr(shape, "geoms", ()):
            yield from _parts(part)


def _display_union(shapes):
    """Close subpixel arithmetic cracks only between extended near-contact edges."""
    raw = union_all(shapes)
    if raw.is_empty:
        return raw
    left, top, right, bottom = raw.bounds
    scale = max(right - left, bottom - top)
    epsilon = scale * 1e-8  # Under 0.00001 display pixel in the shared fitted view.
    minimum_contact = sqrt(epsilon * scale)
    pending, closed = list(_parts(raw)), []
    while pending:
        group, changed = [pending.pop()], True
        while changed:
            changed = False
            for index in range(len(pending) - 1, -1, -1):
                if any(pending[index].boundary.intersection(part.boundary.buffer(epsilon)).length > minimum_contact
                       for part in group):
                    group.append(pending.pop(index))
                    changed = True
        # Separate groups keep genuine gaps and point-only contacts separate.
        merged = union_all(group).buffer(epsilon, join_style=2).buffer(-epsilon, join_style=2)
        closed.extend(_parts(merged))
    return closed[0] if len(closed) == 1 else MultiPolygon(closed)


def _reflect(shape, angle):
    """Reflect through the supplied clockwise angle and the current area centroid."""
    center = shape.centroid
    c, s = cos(2 * radians(angle)), sin(2 * radians(angle))
    return affine_transform(shape, [c, s, s, -c,
        center.x * (1 - c) - center.y * s, center.y * (1 + c) - center.x * s])


def _outline(surface, shape, transform, color):
    for part in _parts(shape):
        for ring in (part.exterior, *part.interiors):
            points = [tuple(round(value) for value in transform(x, y)) for x, y in ring.coords]
            pygame.draw.lines(surface, color, True, points, 4)


def _overlay(surface, shape, transform, color):
    layer = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    for part in _parts(shape):
        _graphics_polygon(layer, part, transform, color, width=0, background=(0, 0, 0, 0))
    surface.blit(layer, (0, 0))


def measurement_atlas(puzzle, *, language="en"):
    """Append uniform ruler/protractor observations for every original piece edge."""
    if language not in ("ko", "en"):
        raise ValueError("측정표 언어는 ko 또는 en이어야 합니다.")
    original = piece_atlas(puzzle, language=language)
    image = pygame.image.load(BytesIO(b64decode(original["image"].partition(",")[2])))
    vertices = [list(_piece_polygon(piece).exterior.coords)[:-1] for piece in puzzle["pieces"]]
    base = original["height"]
    surface = pygame.Surface((original["width"], base + 152 + max(map(len, vertices), default=0) * 28))
    surface.fill("#111d2e")
    surface.blit(image, (0, 0))
    heading, body = _prose_fonts(language, (28, 24), (32, 24))
    numbers = pygame.font.Font(None, 28)
    korean = language == "ko"
    _graphics_text(surface, "원래 조각의 모든 변 측정표" if korean else "ALL ORIGINAL EDGES / LENGTH AND DIRECTION",
                   heading, "#f5dfb6", (36, base + 14))
    _graphics_text(surface, "eN: vN->다음 꼭짓점 / 방향: 오른쪽 x축에서 시계 방향 / y는 아래쪽" if korean else
                   "eN: vN to next vertex / directions clockwise from rightward x / y points down",
                   body, "#d7e5f3", (36, base + 52))
    gap, margin = 24, 36
    width = (surface.get_width() - 2 * margin - gap * (len(vertices) - 1)) / max(len(vertices), 1)
    for index, (piece, points) in enumerate(zip(puzzle["pieces"], vertices)):
        card = pygame.Rect(round(margin + index * (width + gap)), base + 88, round(width), surface.get_height() - base - 102)
        pygame.draw.rect(surface, "#e9edf0", card, border_radius=10)
        positions = (card.x + 16, card.x + round(width * .52), card.x + round(width * .76))
        for value, x in zip((f"{piece['id']} / 변" if korean else f"{piece['id']} / edge",
                             "길이" if korean else "Length", "각도" if korean else "CW deg"), positions):
            _graphics_text(surface, value, body, "#405a70", (x, base + 100))
        for edge, (start, end) in enumerate(zip(points, points[1:] + points[:1])):
            dx, dy = end[0] - start[0], end[1] - start[1]
            length = hypot(dx, dy)
            angle = round(degrees(atan2(dy, dx)) % 360, 2) % 360
            values = (f"e{edge} (v{edge}->v{(edge + 1) % len(points)})", f"{length:.5f}", f"{angle:.2f}°")
            for value, x in zip(values, positions):
                _graphics_text(surface, value, numbers, "#172d44", (x, base + 140 + edge * 28))
    return _png_view(surface, "symmetry-measurement-atlas.png")


def workbench_image(puzzle, placements, *, axis=None, language="en"):
    """Render only observed pieces; axis is an optional angle, never an axis search."""
    if language not in ("ko", "en"):
        raise ValueError("작업 보기 언어는 ko 또는 en이어야 합니다.")
    if axis is not None:
        if type(axis) not in (int, float):
            raise ValueError("반사축 각도에는 유한한 수를 지정하세요.")
        try:
            axis = float(axis)
        except OverflowError:
            raise ValueError("반사축 각도에는 유한한 수를 지정하세요.") from None
        if not isfinite(axis):
            raise ValueError("반사축 각도에는 유한한 수를 지정하세요.")
        axis %= 180
    shapes = [placement_polygon(puzzle, placement) for placement in placements]
    shape = _display_union(shapes)
    reflected = _reflect(shape, axis) if axis is not None and not shape.is_empty else None
    pygame.font.init()
    surface = pygame.Surface((1440, 900))
    surface.fill("#111d2e")
    title, heading, body = _prose_fonts(language, (36, 28, 24), (44, 32, 28))
    korean = language == "ko"

    def text(ko, en, font, position, color="#d7e5f3"):
        _graphics_text(surface, ko if korean else en, font, color, position)

    if axis == 0:
        text("0도 가로 반사축 · 위 <-> 아래", "0 deg horizontal mirror line / top <-> bottom", title, (30, 23), "#f5dfb6")
    elif axis == 90:
        text("90도 세로 반사축 · 왼쪽 <-> 오른쪽", "90 deg vertical mirror line / left <-> right", title, (30, 23), "#f5dfb6")
    elif axis is not None:
        text(f"{axis:g}도 · 점선을 가로질러 반사", f"{axis:g} deg / reflect across the dashed mirror line", title, (30, 23), "#f5dfb6")
    else:
        text("전체 윤곽과 요청한 반사상", "Silhouette and requested reflection", title, (30, 23), "#f5dfb6")
    text("각도는 반사축의 방향입니다. 도형을 회전하는 명령이 아닙니다.",
         "Reflect across the dashed line, without rotating the shape.",
         body, (30, 78))
    if axis is not None:
        center = (1320, 48)
        along = (cos(radians(axis)), sin(radians(axis)))
        across = (-along[1], along[0])
        for lo in (-38, -16, 6, 28):
            points = [tuple(round(center[i] + along[i] * t) for i in (0, 1)) for t in (lo, lo + 10)]
            pygame.draw.line(surface, "#b98727", *points, 4)
        tips = [tuple(round(center[i] + across[i] * t) for i in (0, 1)) for t in (-27, 27)]
        pygame.draw.line(surface, "#8bd0dc", *tips, 3)
        for sign, tip in zip((-1, 1), tips):
            points = [tuple(round(tip[i] - sign * across[i] * 9 + along[i] * t) for i in (0, 1)) for t in (-6, 6)]
            pygame.draw.lines(surface, "#8bd0dc", False, (points[0], tip, points[1]), 3)
        text("반사 방향", "Mirror direction", body, (1215, 80))
    panels = (pygame.Rect(30, 155, 675, 590), pygame.Rect(735, 155, 675, 590))
    text("현재 전체 윤곽", "Current silhouette", heading, (44, 117))
    text("현재 윤곽 + 요청한 반사상", "Current + requested reflection", heading, (749, 117))
    for panel in panels:
        pygame.draw.rect(surface, "#f6f4ea", panel, border_radius=10)
    if not shape.is_empty:
        bounds = [shape.bounds] + ([reflected.bounds] if reflected is not None else [])
        left, top = min(b[0] for b in bounds), min(b[1] for b in bounds)
        right, bottom = max(b[2] for b in bounds), max(b[3] for b in bounds)
        unit = min((panels[0].width - 100) / (right - left), (panels[0].height - 100) / (bottom - top))
        transforms = [lambda x, y, panel=panel: (
            panel.centerx + (x - (left + right) / 2) * unit,
            panel.centery + (y - (top + bottom) / 2) * unit) for panel in panels]
        for part in _parts(shape):
            _graphics_polygon(surface, part, transforms[0], COLORS[puzzle["id"]][1], outline="#225b72", width=3)
        _overlay(surface, shape, transforms[1], (36, 177, 202, 96))
        if reflected is not None:
            transform = transforms[1]
            _overlay(surface, reflected, transform, (200, 63, 159, 96))
            _outline(surface, shape, transform, "#225b72")
            _outline(surface, reflected, transform, "#b73186")
            center = shape.centroid
            span = hypot(right - left, bottom - top) * 2
            dx, dy = cos(radians(axis)) * span, sin(radians(axis)) * span
            segment = panels[1].inflate(-8, -8).clipline(
                transform(center.x - dx, center.y - dy), transform(center.x + dx, center.y + dy))
            if segment:
                start, end = segment
                length = hypot(end[0] - start[0], end[1] - start[1])
                for offset in range(0, int(length), 20):
                    points = [tuple(round(start[i] + (end[i] - start[i]) * t / length) for i in (0, 1))
                              for t in (offset, min(offset + 11, length))]
                    pygame.draw.line(surface, "#a77319", *points, 4)
        else:
            _outline(surface, shape, transforms[1], "#225b72")
        text(f"좌표 범위 x {left:.5g} .. {right:.5g} / y {top:.5g} .. {bottom:.5g}",
             f"Shared coordinates x {left:.5g} .. {right:.5g} / y {top:.5g} .. {bottom:.5g}", body, (30, 759))
    else:
        text("배치한 조각이 없습니다.", "No pieces placed.", heading, (65, 400), "#677b88")
    text("청록: 현재 도형    자주: 반사상    혼합색: 두 그림이 겹친 부분    점선: 반사축",
         "Cyan: current shape    Magenta: reflection    Mixed color: superimposed region    Dashed line: mirror",
         body, (30, 805))
    if axis is None:
        text("반사축을 요청하지 않았습니다. 각도를 지정하면 현재 도형의 면적 중심을 지나는 축을 사용합니다.",
             "No axis requested. An angle defines a line through the current shape's area centroid.", body, (30, 849))
    else:
        text(f"요청한 축 {axis:g}도: 현재 도형의 면적 중심 통과 / 오른쪽 x축에서 시계 방향 / y는 아래쪽",
             f"Requested axis {axis:g} deg through the area centroid / clockwise from rightward x / y points down",
             body, (30, 849))
    return _png_view(surface, "symmetry-workbench.png")
