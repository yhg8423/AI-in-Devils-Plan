"""The public partial-edge example is valid, explanatory, and independent of the real pack."""

from base64 import b64decode
from io import BytesIO
import unittest
from unittest.mock import patch

import pygame
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

from . import tutorial
from .puzzles import assembled_shape, judge, placement_polygon, reflection_axes


class TutorialTest(unittest.TestCase):
    def test_three_irregular_pieces_form_a_concave_symmetric_whole_without_overlaps(self):
        puzzle = tutorial.EXAMPLE_PUZZLE
        self.assertEqual([piece["id"] for piece in puzzle["pieces"]], ["EX1", "EX2", "EX3"])
        self.assertEqual([len(piece["vertices"]) for piece in puzzle["pieces"]], [6, 8, 8])
        self.assertTrue(judge(puzzle, tutorial.EXAMPLE_PLACEMENTS))
        shape = assembled_shape(puzzle, tutorial.EXAMPLE_PLACEMENTS)
        self.assertAlmostEqual(shape.area, 40)
        self.assertGreater(shape.convex_hull.area - shape.area, 7)
        self.assertEqual(len(reflection_axes(shape)), 1)
        self.assertTrue(any(abs(angle - 20) < 1e-6 for angle in reflection_axes(shape)))
        pieces = [placement_polygon(puzzle, value) for value in tutorial.EXAMPLE_PLACEMENTS]
        for index, first in enumerate(pieces):
            self.assertEqual(first.exterior.is_ccw, Polygon(tutorial.EXAMPLE_VERTICES[index]).exterior.is_ccw)
            for second in pieces[:index]:
                self.assertLess(first.intersection(second).area, 1e-12)

    def test_final_exterior_keeps_unshared_parts_of_both_unequal_contacting_edges(self):
        pieces = [Polygon(vertices) for vertices in tutorial.EXAMPLE_VERTICES]
        complete = unary_union(pieces)
        long_edge = LineString(tutorial.LONG_EDGE)
        upper_edge = LineString([tutorial.EXAMPLE_VERTICES[1][-1], tutorial.EXAMPLE_VERTICES[1][0]])
        lower_edge = LineString([tutorial.EXAMPLE_VERTICES[2][-1], tutorial.EXAMPLE_VERTICES[2][0]])
        upper = pieces[0].boundary.intersection(pieces[1].boundary)
        lower = pieces[0].boundary.intersection(pieces[2].boundary)
        self.assertAlmostEqual(long_edge.length, 6)
        self.assertAlmostEqual(upper_edge.length, 4)
        self.assertAlmostEqual(lower_edge.length, 4)
        for shared, wing_edge in ((upper, upper_edge), (lower, lower_edge)):
            self.assertAlmostEqual(shared.length, 2)
            self.assertLess(shared.length, long_edge.length)
            self.assertLess(shared.length, wing_edge.length)
            remainder = wing_edge.difference(shared)
            self.assertAlmostEqual(remainder.length, 2)
            self.assertAlmostEqual(remainder.intersection(complete.boundary).length, 2)
        central = long_edge.difference(unary_union([upper, lower]))
        self.assertAlmostEqual(central.length, 2)
        self.assertTrue(central.equals(LineString(tutorial.EXPOSED_CENTRAL)))
        self.assertAlmostEqual(central.intersection(complete.boundary).length, 2)
        self.assertGreater(upper.distance(lower), 1.9)

    def test_point_only_contrast_uses_every_piece_without_overlap_but_is_not_connected(self):
        pieces = [placement_polygon(tutorial.EXAMPLE_PUZZLE, value) for value in tutorial.POINT_ONLY_PLACEMENTS]
        self.assertEqual(len(pieces), 3)
        for index, first in enumerate(pieces):
            for second in pieces[:index]:
                self.assertLess(first.intersection(second).area, 1e-12)
        self.assertLess(pieces[0].distance(pieces[2]), 1e-10)
        self.assertLess(pieces[0].boundary.intersection(pieces[2].boundary).length, 1e-10)
        self.assertIsNone(assembled_shape(tutorial.EXAMPLE_PUZZLE, tutorial.POINT_ONLY_PLACEMENTS))
        self.assertFalse(judge(tutorial.EXAMPLE_PUZZLE, tutorial.POINT_ONLY_PLACEMENTS))

    def test_bilingual_png_and_explanation_are_deterministic_and_do_not_load_actual_puzzles(self):
        self.assertEqual(set(tutorial.TUTORIAL_EXPLANATIONS), {"ko", "en"})
        self.assertEqual(tutorial.TUTORIAL_INSTRUCTIONS, tutorial.TUTORIAL_EXPLANATIONS["ko"])
        views = []
        with (patch("games.exile_match.symmetry.puzzles.make_puzzles", side_effect=AssertionError("No actual pack")),
              patch("games.exile_match.symmetry.puzzles.judge", side_effect=AssertionError("No game judgement"))):
            for language in ("ko", "en"):
                with self.subTest(language=language):
                    view = tutorial.tutorial_image(language=language)
                    self.assertEqual(set(view), {"id", "width", "height", "image"})
                    self.assertEqual((view["width"], view["height"]), (1800, 1150))
                    encoded = b64decode(view["image"].partition(",")[2], validate=True)
                    self.assertTrue(encoded.startswith(b"\x89PNG\r\n\x1a\n"))
                    self.assertEqual(pygame.image.load(BytesIO(encoded)).get_size(), (1800, 1150))
                    self.assertEqual(view, tutorial.tutorial_image(language=language))
                    for expected in ("EX1", "EX2", "EX3", "6", "4", "2", "20"):
                        self.assertIn(expected, tutorial.TUTORIAL_EXPLANATIONS[language])
                    for forbidden in ("B1", "R1", "G1", "blue", "red", "green"):
                        self.assertNotIn(forbidden, tutorial.TUTORIAL_EXPLANATIONS[language])
                    for obsolete in ("3.4", "2.6", "T junction", "T자", "asymmetric", "비대칭"):
                        self.assertNotIn(obsolete, tutorial.TUTORIAL_EXPLANATIONS[language])
                    views.append(view)
        self.assertNotEqual(views[0]["id"], views[1]["id"])
        with self.assertRaises(ValueError):
            tutorial.tutorial_image(language="fr")


if __name__ == "__main__":
    unittest.main()
