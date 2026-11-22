from base64 import b64decode
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import unittest
from unittest.mock import patch

import pygame
from shapely import union_all
from shapely.affinity import translate
from shapely.geometry import Polygon

from . import workbench


PUZZLE = {"id": "red", "pieces": [{"id": "A", "vertices": [(0, 0), (3, 0), (0, 2)]}],
          "solution": "NEVER-READ-OR-DISPLAY"}
PLACEMENTS = [{"piece": "A", "x": 0, "y": 0, "rotation": 0}]


class WorkbenchTest(unittest.TestCase):
    def test_explicit_horizontal_and_diagonal_reflection_use_the_area_centroid(self):
        shape = Polygon([(0, 0), (3, 0), (0, 2)])
        center = shape.centroid
        horizontal = Polygon([(x, 2 * center.y - y) for x, y in shape.exterior.coords])
        diagonal = Polygon([(center.x + y - center.y, center.y + x - center.x)
                            for x, y in shape.exterior.coords])
        self.assertLess(workbench._reflect(shape, 0).symmetric_difference(horizontal).area, 1e-12)
        self.assertLess(workbench._reflect(shape, 45).symmetric_difference(diagonal).area, 1e-12)

    def test_standard_png_is_deterministic_and_never_requests_a_judgment_or_fixture(self):
        with (patch("games.exile_match.symmetry.puzzles.judge", side_effect=AssertionError("judge")),
              patch("games.exile_match.symmetry.puzzles.reflection_axes", side_effect=AssertionError("axis search"))):
            image = workbench.workbench_image(PUZZLE, PLACEMENTS, axis=37)
            self.assertEqual(image, workbench.workbench_image(PUZZLE, PLACEMENTS, axis=217))
        png = b64decode(image["image"].partition(",")[2])
        self.assertEqual(image["id"], sha256(png).hexdigest()[:16])
        self.assertEqual(pygame.image.load(BytesIO(png)).get_size(), (1440, 900))
        self.assertNotIn("NEVER-READ", str(image))

    def test_invalid_angles_reject_bools_nonfinite_and_non_numeric_values(self):
        for axis in (True, False, float("inf"), float("nan"), "45", {}, 10 ** 400):
            with self.subTest(axis=str(axis)[:40]), self.assertRaises(ValueError):
                workbench.workbench_image(PUZZLE, PLACEMENTS, axis=axis)
        with self.assertRaises(ValueError):
            workbench.workbench_image(PUZZLE, PLACEMENTS, language="fr")

    def test_clean_union_preserves_holes_and_panels_share_the_same_coordinate_transform(self):
        polygons = [[(0, 0), (3, 0), (3, 1), (0, 1)], [(0, 2), (3, 2), (3, 3), (0, 3)],
                    [(0, 1), (1, 1), (1, 2), (0, 2)], [(2, 1), (3, 1), (3, 2), (2, 2)]]
        puzzle = {"id": "green", "pieces": [{"id": str(i), "vertices": vertices} for i, vertices in enumerate(polygons)]}
        placements = [{"piece": str(i), "x": min(x for x, y in vertices), "y": min(y for x, y in vertices), "rotation": 0}
                      for i, vertices in enumerate(polygons)]
        calls = []
        paint = workbench._graphics_polygon

        def capture(surface, shape, transform, *args, **kwargs):
            calls.append((shape, transform(0, 0), transform(3, 3)))
            return paint(surface, shape, transform, *args, **kwargs)

        with patch.object(workbench, "_graphics_polygon", side_effect=capture):
            image = workbench.workbench_image(puzzle, placements, axis=19)
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(len(shape.interiors) == 1 for shape, _, _ in calls))
        first, second = calls[:2]
        for i in (0, 1):
            self.assertAlmostEqual(first[2][i] - first[1][i], second[2][i] - second[1][i])
        self.assertEqual(first[1][1], second[1][1])

        with patch.object(workbench, "_graphics_polygon", side_effect=capture):
            image = workbench.workbench_image(puzzle, placements, axis=0)
        png = pygame.image.load(BytesIO(b64decode(image["image"].partition(",")[2])))
        _, second = calls[-3:-1]
        hole_x = round(second[1][0] + (second[2][0] - second[1][0]) / 2)
        # Stay inside the hole and away from the horizontal axis itself.
        hole_y = round(second[1][1] + (second[2][1] - second[1][1]) * .4)
        self.assertEqual(tuple(png.get_at((hole_x, hole_y)))[:3], (246, 244, 234))

    def test_cardinal_headers_describe_the_mirror_direction_and_never_call_it_rotation(self):
        for language, expected in (("ko", ("가로 반사축", "위 <-> 아래", "세로 반사축", "왼쪽 <-> 오른쪽")),
                                   ("en", ("horizontal mirror line", "top <-> bottom", "vertical mirror line", "left <-> right"))):
            for axis, phrases in ((0, expected[:2]), (90, expected[2:])):
                with self.subTest(language=language, axis=axis), patch.object(workbench, "_graphics_text") as draw:
                    workbench.workbench_image(PUZZLE, PLACEMENTS, axis=axis, language=language)
                captions = "\n".join(call.args[1] for call in draw.call_args_list)
                self.assertTrue(all(phrase in captions for phrase in phrases))
                self.assertIn("회전하는 명령이 아닙니다" if language == "ko" else "without rotating the shape", captions)
                self.assertIn("혼합색" if language == "ko" else "Mixed color", captions)
        with patch.object(workbench, "_graphics_text") as draw:
            workbench.workbench_image(PUZZLE, PLACEMENTS, axis=37, language="ko")
        self.assertTrue(any("점선을 가로질러 반사" in call.args[1] for call in draw.call_args_list))

    def test_no_axis_and_empty_geometry_are_explicit_and_bilingual(self):
        reflect = workbench._reflect
        for language in ("ko", "en"):
            with patch.object(workbench, "_reflect", wraps=reflect) as reflection:
                no_axis = workbench.workbench_image(PUZZLE, PLACEMENTS, language=language)
                empty = workbench.workbench_image(PUZZLE, [], axis=0, language=language)
                reflection.assert_not_called()
                self.assertNotEqual(no_axis["id"], empty["id"])
        self.assertNotEqual(workbench.workbench_image(PUZZLE, PLACEMENTS, language="ko")["id"],
                            workbench.workbench_image(PUZZLE, PLACEMENTS, language="en")["id"])

    def test_actual_green_trial_has_no_internal_outline_from_roundoff_cracks(self):
        from .puzzles import make_puzzles, placement_polygon

        puzzle = next(puzzle for puzzle in make_puzzles(506456969) if puzzle["id"] == "green")
        # P14, mirror pilot attempt 2, final green work; no reference-solution data.
        placements = [
            {"piece": "G1", "x": -2.733283384891571, "y": 1.4630188713637373, "rotation": 25.13010235415597},
            {"piece": "G2", "x": 0, "y": 0, "rotation": 0},
            {"piece": "G3", "x": -2.137053979719743, "y": -0.8076075050741567, "rotation": 151.8104858459758},
        ]
        shapes = [placement_polygon(puzzle, placement) for placement in placements]
        raw = union_all(shapes, grid_size=1e-9)
        self.assertEqual(raw.geom_type, "MultiPolygon")
        display = workbench._display_union(shapes)
        self.assertEqual(display.geom_type, "Polygon")
        self.assertEqual(len(display.interiors), 0)
        self.assertLess(display.symmetric_difference(raw).area, 1e-6)
        with patch.object(workbench, "_graphics_polygon", wraps=workbench._graphics_polygon) as paint:
            workbench.workbench_image(puzzle, placements, axis=90)
        self.assertEqual(len(paint.call_args_list), 3)
        self.assertTrue(all(call.args[1].geom_type == "Polygon" for call in paint.call_args_list))

    def test_display_closing_preserves_real_holes_visible_gaps_and_point_only_components(self):
        square = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
        for other in (translate(square, xoff=1, yoff=1), translate(square, xoff=1.02)):
            with self.subTest(bounds=other.bounds):
                display = workbench._display_union([square, other])
                self.assertEqual(display.geom_type, "MultiPolygon")
                self.assertEqual(len(display.geoms), 2)
                self.assertAlmostEqual(display.area, 2)
                self.assertLess(display.symmetric_difference(union_all([square, other])).area, 1e-12)
        holed = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)],
                        holes=[[(.4, .4), (.6, .4), (.6, .6), (.4, .6)]])
        display = workbench._display_union([holed])
        self.assertEqual(len(display.interiors), 1)
        self.assertAlmostEqual(Polygon(display.interiors[0]).area, .04)

    def test_measurement_atlas_preserves_the_original_pixels_and_source_vertices_in_both_languages(self):
        from .puzzles import make_puzzles, piece_atlas

        for language in ("ko", "en"):
            for puzzle in make_puzzles(506456969):
                with self.subTest(language=language, color=puzzle["id"]):
                    before = deepcopy(puzzle)
                    original = piece_atlas(puzzle, language=language)
                    measured = workbench.measurement_atlas(puzzle, language=language)
                    top = pygame.image.load(BytesIO(b64decode(original["image"].partition(",")[2])))
                    whole = pygame.image.load(BytesIO(b64decode(measured["image"].partition(",")[2])))
                    self.assertEqual(measured["width"], original["width"])
                    self.assertGreater(measured["height"], original["height"])
                    self.assertEqual(pygame.image.tobytes(whole.subsurface(top.get_rect()), "RGBA"),
                                     pygame.image.tobytes(top, "RGBA"))
                    self.assertEqual(puzzle, before)

    def test_measurement_table_includes_every_directed_edge_and_no_join_or_solution_information(self):
        puzzle = {"id": "red", "pieces": [{"id": "A", "vertices": [(0, 0), (3, 0), (3, 4)]}],
                  "solution": "NEVER-READ-OR-DISPLAY"}
        with (patch.object(workbench, "_graphics_text") as draw,
              patch("games.exile_match.symmetry.puzzles.judge", side_effect=AssertionError("judge")),
              patch("games.exile_match.symmetry.puzzles.reflection_axes", side_effect=AssertionError("axis search"))):
            workbench.measurement_atlas(puzzle)
        captions = [call.args[1] for call in draw.call_args_list]
        for expected in ("e0 (v0->v1)", "e1 (v1->v2)", "e2 (v2->v0)", "3.00000", "4.00000", "5.00000",
                         "0.00°", "90.00°", "233.13°"):
            self.assertIn(expected, captions)
        self.assertNotIn("NEVER-READ", "\n".join(captions))
        self.assertTrue(any("clockwise from rightward x" in caption for caption in captions))
        with self.assertRaises(ValueError):
            workbench.measurement_atlas(puzzle, language="fr")


if __name__ == "__main__":
    unittest.main()
