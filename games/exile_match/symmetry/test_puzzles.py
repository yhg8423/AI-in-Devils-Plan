"""Continuous placement, arbitrary-axis symmetry, contact tolerance, and PNG privacy."""

from base64 import b64decode
from hashlib import sha256
from io import BytesIO
import unittest
from unittest.mock import patch

import pygame
from shapely.affinity import rotate, scale, translate
from shapely.geometry import Polygon, box

from . import puzzles as graphics
from .puzzles import NUMERIC_LIMIT, _label_layout, align_placement, assembled_shape, board, judge, make_puzzles, piece_atlas, placement_polygon, reflection_axes


def puzzle(vertices, count=1):
    return {"id": "blue", "label": "파랑", "pieces": [
        {"id": f"B{index}", "vertices": vertices} for index in range(1, count + 1)], "solution": []}


def placement(piece="B1", x=0, y=0, rotation=0):
    return {"piece": piece, "x": x, "y": y, "rotation": rotation}


def positions(points):
    return [placement(f"B{index}", x, y) for index, (x, y) in enumerate(points, 1)]


SQUARE = [(0, 0), (1, 0), (1, 1), (0, 1)]
TRIANGLE = [(0, 0), (2, 0), (0, 1)]


class PolygonTest(unittest.TestCase):
    def assertAngles(self, actual, expected):
        self.assertEqual(len(actual), len(expected), actual)
        for angle in expected:
            self.assertTrue(any(min(abs(angle - value), 180 - abs(angle - value)) < 1e-7 for value in actual), actual)

    def test_arbitrary_axis_angles_survive_rotation_translation_and_scaling(self):
        shapes = [(box(0, 0, 4, 1), [0, 90]), (box(0, 0, 2, 2), [0, 45, 90, 135]),
                  (Polygon([(0, 0), (2, 0), (0, 2)]), [45])]
        for original, axes in shapes:
            for angle in (0, 17.3, 63.125, 149.75):
                for factor in (.001, 1, 1000):
                    with self.subTest(angle=angle, factor=factor, axes=axes):
                        transformed = translate(rotate(scale(original, factor, factor), angle), 13.125, -8.5)
                        self.assertAngles(reflection_axes(transformed), [(axis + angle) % 180 for axis in axes])

    def test_concave_and_holed_shapes_are_compared_as_whole_areas(self):
        asymmetric = Polygon([(0, 0), (3, 0), (3, 1), (1, 1), (1, 2), (0, 2)])
        self.assertEqual(reflection_axes(asymmetric), [])
        ring = Polygon([(0, 0), (4, 0), (4, 4), (0, 4)], [[(1, 1), (3, 1), (3, 3), (1, 3)]])
        self.assertAngles(reflection_axes(ring), [0, 45, 90, 135])
        self.assertAngles(reflection_axes(rotate(ring, 22.75)), [22.75, 67.75, 112.75, 157.75])
        off_center_hole = Polygon(ring.exterior, [[(.5, 1.5), (1.5, 1.5), (1.5, 2.5), (.5, 2.5)]])
        self.assertAngles(reflection_axes(off_center_hole), [0])
        self.assertEqual(reflection_axes(None), [])
        self.assertEqual(reflection_axes(Polygon()), [])

    def test_arbitrary_clockwise_rotation_normalizes_bbox_then_applies_decimal_anchor(self):
        source = puzzle(TRIANGLE)
        for angle in (17.3, 63.125, -296.875, 360, 725.5):
            with self.subTest(angle=angle):
                result = placement_polygon(source, placement(x=-3.125, y=7.75, rotation=angle))
                expected = rotate(Polygon(TRIANGLE), angle % 360, origin=(0, 0))
                expected = translate(expected, -3.125 - expected.bounds[0], 7.75 - expected.bounds[1])
                self.assertLess(result.symmetric_difference(expected).area, 1e-12)
                self.assertAlmostEqual(result.bounds[0], -3.125)
                self.assertAlmostEqual(result.bounds[1], 7.75)
                self.assertAlmostEqual(result.area, Polygon(TRIANGLE).area)
        clockwise = placement_polygon(source, placement(rotation=90))
        self.assertTrue(clockwise.equals(Polygon([(1, 0), (1, 2), (0, 0)])))

    def test_all_pieces_assemble_after_a_shared_nonorthogonal_rotation(self):
        source = puzzle(TRIANGLE, count=2)
        original = [placement("B1"), placement("B2", rotation=180)]
        self.assertTrue(judge(source, original))
        for angle in (17.3, 63.125, 149.75):
            moved = []
            for previous in original:
                shape = translate(rotate(placement_polygon(source, previous), angle, origin=(0, 0)), 4.125, -7.75)
                moved.append(placement(previous["piece"], shape.bounds[0], shape.bounds[1], previous["rotation"] + angle))
            with self.subTest(angle=angle):
                self.assertTrue(judge(source, moved))
                self.assertAngles(reflection_axes(assembled_shape(source, moved)), [angle, (angle + 90) % 180])

    def test_different_valid_silhouettes_and_symmetric_enclosed_holes_are_accepted(self):
        source = puzzle(SQUARE, count=3)
        for points in ([(0, 0), (1, 0), (2, 0)], [(0, 0), (1, 0), (0, 1)], [(0, 0), (1, 0), (1, 1)]):
            with self.subTest(points=points):
                self.assertTrue(judge(source, positions(points)))
        ring = [(x, y) for y in range(3) for x in range(3) if (x, y) != (1, 1)]
        shape = assembled_shape(puzzle(SQUARE, count=8), positions(ring))
        self.assertEqual(len(shape.interiors), 1)
        self.assertTrue(reflection_axes(shape))

    def test_shared_partial_edge_counts_but_corner_contact_gap_and_overlap_do_not(self):
        source = puzzle(SQUARE, count=2)
        self.assertIsNotNone(assembled_shape(source, positions([(0, 0), (1, .25)])))
        for point in ((1, 1), (1.00001, 0), (.99999, 0), (2, 0)):
            with self.subTest(point=point):
                self.assertIsNone(assembled_shape(source, positions([(0, 0), point])))
        # Much smaller than 1e-6 of a piece: tolerate arithmetic roundoff, not visible geometry errors.
        self.assertIsNotNone(assembled_shape(source, positions([(0, 0), (1 + 1e-10, 0)])))
        self.assertIsNotNone(assembled_shape(source, positions([(0, 0), (1 - 1e-10, 0)])))

    def test_missing_duplicate_unknown_piece_or_disconnected_assemblies_fail(self):
        source = puzzle(SQUARE, count=3)
        good = positions([(0, 0), (1, 0), (2, 0)])
        for placements in (good[:-1], [good[0]] * 3, positions([(0, 0), (2, 0), (4, 0)]),
                           [*good[:-1], placement("R3", 2, 0)], [True, good[1], good[2]]):
            with self.subTest(placements=placements):
                self.assertFalse(judge(source, placements))

    def test_recovered_source_counts_and_reference_assemblies_survive_all_seed_rotations(self):
        counts = {"blue": [9, 8], "red": [3, 4, 5], "green": [5, 5, 3]}
        for seed in range(101):
            for source in make_puzzles(seed):
                with self.subTest(seed=seed, color=source["id"]):
                    self.assertEqual([len(piece["vertices"]) for piece in source["pieces"]], counts[source["id"]])
                    self.assertTrue(judge(source, source["solution"]))
                    for angle in (17.3, 63.125, 149.75):
                        moved = []
                        for previous in source["solution"]:
                            shape = translate(rotate(placement_polygon(source, previous), angle, origin=(0, 0)), 13.125, -8.5)
                            moved.append(placement(previous["piece"], shape.bounds[0], shape.bounds[1], previous["rotation"] + angle))
                        self.assertTrue(judge(source, moved), angle)

    def test_actual_banks_align_only_the_commanded_edges_and_vertices(self):
        commands = {
            "blue": [("B2", 0, 5, "B1", 5, 4)],
            "red": [("R2", 0, 2, "R1", 1, 2), ("R3", 1, 4, "R1", 2, 1)],
            "green": [("G2", 0, 0, "G1", 2, 3), ("G3", 2, 2, "G2", 2, 3)],
        }
        keys = ("piece", "edge", "vertex", "to_piece", "to_edge", "to_vertex")
        for source in make_puzzles(19):
            for angle in (0, 37.25):
                first = source["solution"][0]
                original = translate(rotate(placement_polygon(source, first), angle, origin=(0, 0)), 1.125, -3.25)
                previous = [placement(first["piece"], original.bounds[0], original.bounds[1], first["rotation"] + angle)]
                for values in commands[source["id"]]:
                    command = dict(zip(keys, values, strict=True))
                    aligned = align_placement(source, command, previous)
                    self.assertEqual(set(aligned), {"piece", "x", "y", "rotation"})
                    actual = placement_polygon(source, aligned)
                    reference = next(value for value in source["solution"] if value["piece"] == aligned["piece"])
                    expected = translate(rotate(placement_polygon(source, reference), angle, origin=(0, 0)), 1.125, -3.25)
                    self.assertLess(actual.symmetric_difference(expected).area, 1e-9)
                    previous.append(aligned)
                self.assertTrue(judge(source, previous))

    def test_alignment_never_chooses_a_different_edge_or_searches_for_a_solution(self):
        source = puzzle(SQUARE, count=2)
        target = placement()
        good = {"piece": "B2", "edge": 3, "vertex": 0, "to_piece": "B1", "to_edge": 1, "to_vertex": 1}
        self.assertTrue(judge(source, [target, align_placement(source, good, [target])]))
        wrong = {**good, "edge": 0, "to_edge": 0, "to_vertex": 0}
        aligned = align_placement(source, wrong, [target])
        self.assertEqual(aligned, placement("B2", -1, -1, 180))
        self.assertFalse(judge(source, [target, aligned]))
        for changes in ({"piece": "R1"}, {"to_piece": "R1"}, {"to_piece": "B2"}, {"edge": True},
                        {"vertex": -1}, {"to_edge": 4}, {"to_vertex": 1.0}, {"flip": True}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                align_placement(source, {**good, **changes}, [target])
        for previous in ([], [target, target], [target, placement("B2")]):
            with self.subTest(previous=previous), self.assertRaises(ValueError):
                align_placement(source, good, previous)

    def test_no_flip_matrix_or_nonfinite_and_oversized_numbers_are_accepted(self):
        source = puzzle(TRIANGLE)
        good = placement(x=NUMERIC_LIMIT, y=-NUMERIC_LIMIT, rotation=17.3)
        self.assertGreater(placement_polygon(source, good).area, 0)
        for changes in ({"x": True}, {"y": False}, {"rotation": True}, {"x": float("nan")},
                        {"y": float("inf")}, {"rotation": -float("inf")}, {"x": 1_000_001},
                        {"rotation": 10 ** 1000}, {"flip": True}, {"matrix": [1, 0, 0, -1]},
                        {"piece": "R1"}, {"piece": []}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                placement_polygon(source, {**placement(), **changes})
        chiral = puzzle([(0, 0), (3, 0), (3, 1), (1, 1), (1, 2), (0, 2)])
        original = Polygon(chiral["pieces"][0]["vertices"])
        reflected = scale(original, xfact=-1, yfact=1, origin=(0, 0))
        for angle in (0, 17.3, 90, 180, 270):
            shape = placement_polygon(chiral, placement(rotation=angle))
            self.assertAlmostEqual(shape.area, original.area)
            self.assertFalse(shape.equals(translate(reflected, -reflected.bounds[0], -reflected.bounds[1])))

    def test_invalid_source_polygons_are_rejected_without_silent_repair(self):
        for vertices in ([], [(0, 0), (1, 0), (2, 0)], [(0, 0), (1, 1), (0, 1), (1, 0)],
                         [(0, 0), (float("nan"), 1), (1, 0)], [(0, 0), (1, 1, 1), (1, 0)]):
            with self.subTest(vertices=vertices), self.assertRaises(ValueError):
                placement_polygon(puzzle(vertices), placement())

    def test_pngs_show_only_explicit_work_and_keep_polygon_proportions(self):
        source = puzzle(TRIANGLE, count=2)
        source["pieces"][1]["vertices"] = [(0, 0), (1, 0), (0, .5)]
        initial = board(source)
        self.assertEqual(set(initial), {"id", "width", "height", "image"})
        encoded = b64decode(initial["image"].partition(",")[2], validate=True)
        self.assertTrue(encoded.startswith(b"\x89PNG\r\n\x1a\n"))
        image = pygame.image.load(BytesIO(encoded))
        self.assertEqual(image.get_size(), (960, 640))
        pixels = pygame.surfarray.array3d(image)
        widths = []
        for top, bottom in ((90, 330), (340, 583)):
            mask = (pixels[22:382, top:bottom] == (38, 113, 188)).all(axis=2)
            columns = mask.any(axis=1).nonzero()[0]
            widths.append(int(columns[-1] - columns[0] + 1))
        self.assertAlmostEqual(widths[0] / widths[1], 2, delta=.08)
        moved = board(source, [placement(rotation=17.3)])
        overlapping = board(source, [placement("B1", rotation=63.125), placement("B2", rotation=17.3)])
        self.assertEqual(len({initial["id"], moved["id"], overlapping["id"]}), 3)
        source["solution"] = [placement(), placement("B2")]
        self.assertEqual(board(source), initial)

    def test_dense_vertex_and_edge_labels_keep_distinct_boxes_and_exact_leader_anchors(self):
        bounds = pygame.Rect(0, 0, 180, 100)
        labels = [(f"{'v' if index % 2 else 'e'}{index}", (80 + index % 2, 40 + index % 3),
                   (80, 40), (18, 12)) for index in range(10)]
        routed = _label_layout(labels, bounds)
        self.assertEqual([(value, anchor) for value, anchor, _ in routed],
                         [(value, anchor) for value, anchor, _, _ in labels])
        for index, (_, _, rectangle) in enumerate(routed):
            self.assertTrue(bounds.contains(rectangle))
            self.assertFalse(any(rectangle.inflate(2, 2).colliderect(previous[2]) for previous in routed[:index]))
            self.assertFalse(any(rectangle.collidepoint(anchor) for _, anchor, _, _ in labels))

    def test_legacy_png_hashes_match_the_active_sol_record_exactly(self):
        # Initial PNGs and P16's first green draft from the real seed-1 Sol v2 log.
        expected = {"blue": "8a75931b07a8b723784fad20aebf8454daba9f409a206f49d053e19c82f4c9c4",
                    "red": "e446e47e73f8dd08677ddb36465cf72b6b1e1c111c25e54903996a51701be993",
                    "green": "26b479bdf836122194b3843967f9c95a24098d44b2939216e64abc92f3f9bdc0"}
        banks = make_puzzles(506456969)
        for source in banks:
            view = board(source)
            encoded = b64decode(view["image"].partition(",")[2])
            self.assertEqual(sha256(encoded).hexdigest(), expected[source["id"]])
            self.assertEqual(view, board(source, detailed=False))
        draft = [placement("G1"), placement("G2", -1.1279366747967152, .7958788920871428, 27.99999999999999),
                 placement("G3", .22341747916778587, -2.888353008585108, 126.68038349181982)]
        encoded = b64decode(board(banks[2], draft)["image"].partition(",")[2])
        self.assertEqual(sha256(encoded).hexdigest(), "dbce93c90b00a8ceeea3b1a5b824fe06a2aaba17214349065cf2a3a65be8f2b6")

    def test_public_atlases_enlarge_each_piece_without_changing_order_or_chirality(self):
        draw_polygon = graphics._graphics_polygon
        draw_annotations = graphics._draw_annotations
        for seed in (19, 31):
            for source in make_puzzles(seed):
                outlines, annotations = [], []

                def capture_polygon(surface, shape, transform, *args, **kwargs):
                    projected = Polygon([transform(x, y) for x, y in shape.exterior.coords])
                    outlines.append((shape, projected))
                    return draw_polygon(surface, shape, transform, *args, **kwargs)

                def capture_annotations(surface, labels, font, bounds):
                    routed = draw_annotations(surface, labels, font, bounds)
                    annotations.append((labels, routed, pygame.Rect(bounds), font.size("v0")[1]))
                    return routed

                with (self.subTest(seed=seed, color=source["id"]),
                      patch.object(graphics, "_graphics_polygon", side_effect=capture_polygon),
                      patch.object(graphics, "_draw_annotations", side_effect=capture_annotations),
                      patch.object(graphics, "judge", side_effect=AssertionError("A public atlas must not judge a solution"))):
                    view = piece_atlas(source)
                self.assertEqual((view["width"], view["height"]), (1440, 1100))
                self.assertEqual(set(view), {"id", "width", "height", "image"})
                self.assertEqual(len(outlines), len(source["pieces"]))
                for index, ((original, projected), (labels, routed, bounds, font_height)) in enumerate(zip(outlines, annotations, strict=True)):
                    self.assertGreaterEqual(max(projected.bounds[2] - projected.bounds[0], projected.bounds[3] - projected.bounds[1]), 300)
                    self.assertGreaterEqual(font_height, 20)
                    self.assertEqual(original.exterior.is_ccw, projected.exterior.is_ccw)
                    vertices = list(projected.exterior.coords)[:-1]
                    self.assertEqual(len(labels), len(vertices) * 2)
                    for number, vertex in enumerate(vertices):
                        self.assertEqual(labels[number * 2][0:2], (f"v{number}", vertex))
                        next_vertex = vertices[(number + 1) % len(vertices)]
                        self.assertEqual(labels[number * 2 + 1][0], f"e{number}")
                        self.assertAlmostEqual(labels[number * 2 + 1][1][0], (vertex[0] + next_vertex[0]) / 2)
                        self.assertAlmostEqual(labels[number * 2 + 1][1][1], (vertex[1] + next_vertex[1]) / 2)
                    for number, (_, _, rectangle) in enumerate(routed):
                        self.assertTrue(bounds.contains(rectangle))
                        self.assertFalse(any(rectangle.inflate(2, 2).colliderect(previous[2]) for previous in routed[:number]))
                encoded = b64decode(view["image"].partition(",")[2], validate=True)
                self.assertEqual(pygame.image.load(BytesIO(encoded)).get_size(), (1440, 1100))
                source["solution"] = [{"private": "MUST-NOT-APPEAR"}]
                source["placements"] = {"private": "OTHER-PLAYER"}
                self.assertEqual(piece_atlas(source), view)

    def test_detailed_drafts_show_owned_indices_and_overlap_hatching_without_judging(self):
        source = puzzle(SQUARE, count=2)
        legacy = board(source)
        received = []
        draw_annotations = graphics._draw_annotations

        def capture(surface, labels, font, bounds):
            received.extend(value for value, _, _ in labels)
            return draw_annotations(surface, labels, font, bounds)

        with (patch.object(graphics, "_draw_annotations", side_effect=capture),
              patch.object(graphics, "judge", side_effect=AssertionError("Draft rendering must not judge")),
              patch.object(graphics, "assembled_shape", side_effect=AssertionError("Drafts may overlap or be incomplete"))):
            clear = board(source, positions([(0, 0), (1, 0)]), detailed=True)
            overlap = board(source, positions([(0, 0), (.5, .5)]), detailed=True)
            empty = board(source, detailed=True)
        self.assertEqual(set(received), {f"B{piece}.{kind}{number}" for piece in (1, 2) for kind in ("e", "v") for number in range(4)})
        for view in (clear, overlap, empty):
            self.assertEqual((view["width"], view["height"]), (960, 640))
        pixels = [pygame.surfarray.array3d(pygame.image.load(BytesIO(b64decode(view["image"].partition(",")[2]))))
                  for view in (clear, overlap)]
        self.assertEqual(int((pixels[0] == (243, 107, 186)).all(axis=2).sum()), 0)
        self.assertGreater(int((pixels[1] == (243, 107, 186)).all(axis=2).sum()), 100)
        for outline in ((18, 61, 88), (104, 44, 89)):
            self.assertGreater(int((pixels[1] == outline).all(axis=2).sum()), 100)
        source["solution"] = [{"secret": "not-an-outline"}]
        self.assertEqual(board(source, detailed=True), empty)
        self.assertEqual(board(source), legacy)

    def test_korean_diagram_captions_have_bundled_glyphs_and_fit_without_changing_piece_geometry(self):
        for source in make_puzzles(31):
            for atlas in (True, False):
                with self.subTest(color=source["id"], atlas=atlas):
                    render = (lambda language: piece_atlas(source, language=language)) if atlas else (
                        lambda language: board(source, source["solution"], detailed=True, language=language))
                    with patch.object(graphics, "_graphics_polygon", wraps=graphics._graphics_polygon) as english_shapes:
                        english = render("en")
                    with (patch.object(graphics, "_graphics_polygon", wraps=graphics._graphics_polygon) as korean_shapes,
                          patch.object(graphics, "_graphics_text", wraps=graphics._graphics_text) as text):
                        korean = render("ko")
                    self.assertNotEqual(korean["id"], english["id"])
                    self.assertEqual((korean["width"], korean["height"]), (english["width"], english["height"]))
                    for english_call, korean_call in zip(english_shapes.call_args_list, korean_shapes.call_args_list, strict=True):
                        self.assertEqual(english_call.args[1], korean_call.args[1])
                        self.assertEqual([english_call.args[2](*point) for point in english_call.args[1].exterior.coords],
                                         [korean_call.args[2](*point) for point in korean_call.args[1].exterior.coords])
                    captions = [call.args[1] for call in text.call_args_list]
                    self.assertTrue(any("조각 확대도" in caption if atlas else "현재 작업판" in caption for caption in captions))
                    self.assertFalse(any(word in caption for caption in captions for word in ("ATLAS", "ASSEMBLY", "width", "units", "PLACED")))
                    for call in text.call_args_list:
                        surface, value, font, color, position = call.args
                        for character in value:
                            if "가" <= character <= "힣":
                                self.assertIsNotNone(font.metrics(character)[0], character)
                        bounds = font.render(value, True, color).get_rect()
                        if call.kwargs.get("center"):
                            bounds.center = tuple(round(coordinate) for coordinate in position)
                        else:
                            bounds.topleft = tuple(round(coordinate) for coordinate in position)
                        self.assertTrue(surface.get_rect().contains(bounds), value)


if __name__ == "__main__":
    unittest.main()
