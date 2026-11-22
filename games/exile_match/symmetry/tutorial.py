"""A public partial-contact example whose unmatched edges remain exterior at completion."""

from math import cos, radians, sin

import pygame
from shapely.affinity import rotate, translate
from shapely.geometry import Polygon

from .puzzles import _graphics_polygon, _graphics_text, _png_view, _prose_fonts, placement_polygon


TUTORIAL_EXPLANATIONS = {
    "ko": (
        "예제 전용 EX1·EX2·EX3는 실제 퍼즐 조각과 다릅니다. EX1의 길이 6인 변에는 EX2와 EX3가 각각 길이 2만큼만 맞닿습니다. "
        "EX2와 EX3의 해당 변은 각각 길이 4이므로, 남은 2는 모든 조각을 놓은 뒤에도 외부에 드러납니다. "
        "EX1도 두 접합 사이의 중앙 길이 2가 끝까지 외곽 경계로 남습니다. 다른 조각으로 이 부분을 메울 필요는 없습니다. "
        "변 전체가 아니라 일부만 맞닿아도, 모든 조각을 겹침 없이 연결한 전체 도형이 선대칭이면 정답입니다. "
        "완성 예 전체를 20도 회전해도 대칭은 유지됩니다. 꼭짓점 한 점만 닿는 것은 연결로 인정하지 않습니다."
    ),
    "en": (
        "EX1, EX2 and EX3 are example-only pieces, different from the actual puzzle pack. "
        "EX1's length-6 edge shares only length 2 with each wing. Each wing edge has length 4, so its other 2 remains exposed "
        "even after all pieces are placed. The central length-2 gap on EX1 also remains on the final exterior boundary. "
        "No other piece fills these exposed portions. Full-edge matching is unnecessary: use every piece without overlap, "
        "connect them along positive-length segments, and make the complete shape reflection-symmetric. "
        "Rotating the entire example by 20 degrees preserves its symmetry. Touching at only one vertex does not connect pieces."
    ),
}
TUTORIAL_INSTRUCTIONS = TUTORIAL_EXPLANATIONS["ko"]

# Fixed teaching geometry only. EX3 is its own supplied rigid piece, not a flip action.
EXAMPLE_VERTICES = (
    ((0, -4), (1, -3), (1, 3), (0, 4), (-1, 3), (-1, -3)),
    ((-1, -5), (-3, -5), (-3, -4), (-5, -4), (-5, -2), (-4, -2), (-4, -1), (-1, -1)),
    ((-1, 1), (-4, 1), (-4, 2), (-5, 2), (-5, 4), (-3, 4), (-3, 5), (-1, 5)),
)
EXAMPLE_ANGLE = 20
POINT_ONLY_ANGLE = 90
EXAMPLE_PUZZLE = {"id": "example", "pieces": [
    {"id": f"EX{index}", "vertices": vertices} for index, vertices in enumerate(EXAMPLE_VERTICES, 1)]}
EXAMPLE_PLACEMENTS = []
POINT_ONLY_PLACEMENTS = []
for index, vertices in enumerate(EXAMPLE_VERTICES, 1):
    polygon = Polygon(vertices)
    rotated = rotate(polygon, EXAMPLE_ANGLE, origin=(0, 0))
    EXAMPLE_PLACEMENTS.append({"piece": f"EX{index}", "x": rotated.bounds[0], "y": rotated.bounds[1], "rotation": EXAMPLE_ANGLE})
    point_only = translate(polygon, yoff=2) if index == 3 else polygon
    point_only = rotate(point_only, POINT_ONLY_ANGLE, origin=(0, 0))
    POINT_ONLY_PLACEMENTS.append({"piece": f"EX{index}", "x": point_only.bounds[0], "y": point_only.bounds[1], "rotation": POINT_ONLY_ANGLE})

PALETTE = ("#d8a04b", "#9b8ac9", "#55a899")
LONG_EDGE = ((-1, -3), (-1, 3))
SHARED_UPPER = ((-1, -3), (-1, -1))
SHARED_LOWER = ((-1, 1), (-1, 3))
EXPOSED_CENTRAL = ((-1, -1), (-1, 1))
EXPOSED_UPPER = ((-1, -5), (-1, -3))
EXPOSED_LOWER = ((-1, 3), (-1, 5))


def tutorial_image(*, language="en"):
    """Return a fixed worked example, with no actual game pieces or game state."""
    if language not in ("ko", "en"):
        raise ValueError("예제 언어는 ko 또는 en이어야 합니다.")
    pygame.font.init()
    korean = language == "ko"
    title, heading, body, small = _prose_fonts(language, (38, 28, 24, 21), (50, 34, 28, 24))
    identifiers = pygame.font.Font(None, 32)
    surface = pygame.Surface((1800, 1150))
    surface.fill("#111d2e")

    def text(ko, en, font, position, color="#263f54", center=False):
        _graphics_text(surface, ko if korean else en, font, color, position, center=center)

    def segment(points, transform, color, width=7, dashed=False):
        start, end = (transform(*point) for point in points)
        if not dashed:
            pygame.draw.line(surface, color, start, end, width)
            return
        length = ((end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2) ** .5
        for offset in range(0, int(length), 20):
            a, b = offset / length, min(offset + 11, length) / length
            pygame.draw.line(surface, color,
                (start[0] + (end[0] - start[0]) * a, start[1] + (end[1] - start[1]) * a),
                (start[0] + (end[0] - start[0]) * b, start[1] + (end[1] - start[1]) * b), width)

    def label(value, position, color="#263f54"):
        rendered = body.render(value, True, color)
        rectangle = rendered.get_rect(center=position).inflate(12, 8)
        pygame.draw.rect(surface, "#fffef6", rectangle, border_radius=5)
        surface.blit(rendered, rendered.get_rect(center=rectangle.center))

    def draw_pieces(shapes, transform, indices=(0, 1, 2), font=identifiers):
        for index, shape in zip(indices, shapes, strict=True):
            _graphics_polygon(surface, shape, transform, PALETTE[index], width=3)
        for index, shape in zip(indices, shapes, strict=True):
            point = shape.representative_point()
            _graphics_text(surface, f"EX{index + 1}", font, "#233547", transform(point.x, point.y), center=True)

    def fit(shapes, bounds):
        boxes = [shape.bounds for shape in shapes]
        left, right = min(b[0] for b in boxes), max(b[2] for b in boxes)
        top, bottom = min(b[1] for b in boxes), max(b[3] for b in boxes)
        unit = min(bounds[2] / (right - left), bounds[3] / (bottom - top))
        return lambda x, y: (bounds[0] + bounds[2] / 2 + (x - (left + right) / 2) * unit,
                             bounds[1] + bounds[3] / 2 + (y - (top + bottom) / 2) * unit)

    def turn(point, angle=EXAMPLE_ANGLE):
        angle = radians(angle)
        x, y = point
        return x * cos(angle) - y * sin(angle), x * sin(angle) + y * cos(angle)

    contact, exposed = "#2367aa", "#bd562d"
    text("부분 접합 예제 · 드러난 부분이 끝까지 남는 경우", "PARTIAL CONTACT / EXPOSED PARTS REMAIN", title, (30, 22), "#f5dfb6")
    text("실제 퍼즐과 다른 조각 · 모두 놓은 뒤에도 변 전체를 메울 필요는 없습니다",
         "Different example pieces / exposed edge portions need not be filled, even in the completed shape", body, (32, 87), "#d7e5f3")
    for rectangle in ((30, 150, 420, 650), (480, 150, 590, 650), (1100, 150, 670, 650),
                      (30, 830, 1010, 290), (1070, 830, 700, 290)):
        pygame.draw.rect(surface, "#f6f4ea", rectangle, border_radius=12)
    text("1. 따로 놓인 조각", "1. Loose pieces", heading, (52, 174))
    for index, vertices in enumerate(EXAMPLE_VERTICES):
        shape = Polygon(vertices)
        left, top, right, bottom = shape.bounds
        cx, cy = 270, 300 + index * 185
        transform = lambda x, y: (cx + (x - (left + right) / 2) * 21, cy + (y - (top + bottom) / 2) * 21)
        _graphics_polygon(surface, shape, transform, PALETTE[index])
        _graphics_text(surface, f"EX{index + 1}", identifiers, "#263f54", (62, cy - 15))
        if index == 0:
            segment(LONG_EDGE, transform, "#4b5969", 5)
            segment(SHARED_UPPER, transform, contact, 7)
            segment(SHARED_LOWER, transform, contact, 7)
            segment(EXPOSED_CENTRAL, transform, exposed, 5, dashed=True)
            label("6", (210, cy))
        else:
            interval = ((-1, -5), (-1, -1)) if index == 1 else ((-1, 1), (-1, 5))
            segment(interval, transform, "#4b5969", 5)
            segment(SHARED_UPPER if index == 1 else SHARED_LOWER, transform, contact, 7)
            segment(EXPOSED_UPPER if index == 1 else EXPOSED_LOWER, transform, exposed, 5, dashed=True)
            label("4", (350, cy))
    text("파랑: 접합 / 주황: 계속 드러날 부분", "Blue: contact / orange: stays exposed", small, (52, 760))

    text("2. 두 변 모두 일부만 접합", "2. Both edges meet only partly", heading, (503, 174))
    partial = [Polygon(vertices) for vertices in EXAMPLE_VERTICES[:2]]
    partial_transform = fit(partial, (520, 255, 500, 380))
    draw_pieces(partial, partial_transform, (0, 1))
    segment(SHARED_UPPER, partial_transform, contact, 9)
    segment(EXPOSED_UPPER, partial_transform, exposed, 7, dashed=True)
    segment(EXPOSED_CENTRAL, partial_transform, exposed, 7, dashed=True)
    for value, source, position in (("공유 2" if korean else "shared 2", (-1, -2), (990, 390)),
                                    ("노출 2" if korean else "exposed 2", (-1, -4), (990, 285)),
                                    ("노출 2" if korean else "exposed 2", (-1, 0), (990, 555))):
        color = contact if source[1] == -2 else exposed
        label(value, position, color)
        pygame.draw.line(surface, color, partial_transform(*source), (position[0] - 55, position[1] + 10), 2)
    text("길이 4인 변 중 2만 맞닿습니다.", "Only 2 of the length-4 edge is shared.", body, (503, 692))
    text("주황색 2는 EX3를 놓아도 외곽입니다.", "Its orange 2 stays exposed after EX3 joins.", body, (503, 737))

    text("3. 모두 놓아도 노출이 남음", "3. Complete, with exposed portions", heading, (1124, 174))
    joined = [placement_polygon(EXAMPLE_PUZZLE, placement) for placement in EXAMPLE_PLACEMENTS]
    joined_transform = fit(joined, (1140, 250, 590, 420))
    draw_pieces(joined, joined_transform)
    rotated_transform = lambda x, y: joined_transform(*turn((x, y)))
    for interval in (SHARED_UPPER, SHARED_LOWER):
        segment(interval, rotated_transform, contact, 8)
    for interval in (EXPOSED_UPPER, EXPOSED_CENTRAL, EXPOSED_LOWER):
        segment(interval, rotated_transform, exposed, 7, dashed=True)
    segment(((-5.7, 0), (1.7, 0)), rotated_transform, "#233547", 3, dashed=True)
    point = rotated_transform(-1, 0)
    label("중앙 노출 2" if korean else "central exposed 2", (1260, 485), exposed)
    pygame.draw.line(surface, exposed, point, (1360, 485), 2)
    text("점선: 대칭축 / 전체를 20° 회전", "Dashed: axis / whole rotated 20 degrees", small, (1124, 233))
    text("모두 놓아도 주황색 부분은 외곽입니다.", "All three placed: exposed parts remain.", body, (1124, 692))
    text("중앙의 노출 2도 메우지 않습니다.", "No piece fills the central length-2 gap.", body, (1124, 737))

    text("완성 뒤에도 남는 부분 접합", "Partial contact in the finished shape", heading, (54, 850))
    lines = (
        ("긴 변 6에 EX2와 EX3가 각각 2씩만 맞닿습니다.", "The long edge 6 shares only 2 with EX2 and 2 with EX3."),
        ("EX1의 중앙 길이 2는 끝까지 외곽으로 드러납니다.", "EX1's central 2 stays exterior after every piece is placed."),
        ("각 날개 변 4 = 맞닿은 2 + 계속 드러난 2입니다.", "Each wing edge 4 = contact 2 + permanently exposed 2."),
        ("겹침 없이 연결한 전체 도형이 선대칭이면 됩니다.", "Judge the complete connected outline for reflection symmetry."),
    )
    for index, (ko, en) in enumerate(lines):
        text(ko, en, body, (54, 903 + index * 43))
    text("한 점만 닿으면 연결되지 않음", "One point does NOT connect", heading, (1094, 850))
    contrast = [placement_polygon(EXAMPLE_PUZZLE, placement) for placement in POINT_ONLY_PLACEMENTS]
    contrast_transform = fit(contrast, (1125, 900, 590, 170))
    draw_pieces(contrast, contrast_transform, font=pygame.font.Font(None, 20))
    point = contrast_transform(*turn((-1, 3), angle=POINT_ONLY_ANGLE))
    pygame.draw.circle(surface, "#d43858", tuple(round(value) for value in point), 7, 3)
    label("한 점" if korean else "point", (point[0] + 15, point[1] - 60), "#ae2447")
    pygame.draw.line(surface, "#ae2447", point, (point[0] + 15, point[1] - 45), 2)
    text("EX3는 한 점만 닿아 연결되지 않습니다.", "EX3 touches at one point, not along a segment", small, (1094, 1080))
    return _png_view(surface, "symmetry-partial-contact-example.png")
