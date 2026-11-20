"""Generated art must hide its alternate and change only the five scored regions."""

from base64 import b64decode
from io import BytesIO
import json
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pygame

from . import scenes
from .scenes import HEIGHT, PNG_PREFIX, THEMES, WIDTH, judge_marks, make_scene, picture, render_picture


class SceneTest(unittest.TestCase):
    def test_fixed_bank_views_are_fresh_and_contain_only_current_png(self):
        for round_number, theme in enumerate(THEMES, 1):
            with self.subTest(theme=theme):
                scene = make_scene(42, round_number)
                self.assertEqual(scene, make_scene(43, round_number))
                view = picture(scene)
                self.assertEqual(set(view), {"id", "theme", "width", "height", "image"})
                self.assertEqual(view["theme"], theme)
                self.assertNotEqual(view["image"], scene["changed"])
                self.assertEqual(render_picture(view), b64decode(view["image"][len(PNG_PREFIX):]))
                scene["targets"][0]["x"] = -1
                self.assertGreaterEqual(make_scene(42, round_number)["targets"][0]["x"], 0)

    def test_five_visible_nonoverlapping_regions_and_identical_pixels_elsewhere(self):
        for round_number, theme in enumerate(THEMES, 1):
            with self.subTest(theme=theme):
                scene = make_scene(42, round_number)
                self.assertEqual(len(scene["targets"]), 5)
                before = pygame.image.load(BytesIO(render_picture(picture(scene))))
                after = pygame.image.load(BytesIO(render_picture(picture(scene, changed=True))))
                changed = (pygame.surfarray.array3d(before) != pygame.surfarray.array3d(after)).any(axis=2)
                covered = changed.copy()
                for index, target in enumerate(scene["targets"]):
                    x, y, w, h = (target[key] for key in ("x", "y", "w", "h"))
                    self.assertTrue(changed[x:x+w, y:y+h].any())
                    covered[x:x+w, y:y+h] = False
                    for other in scene["targets"][index + 1:]:
                        self.assertFalse(x < other["x"] + other["w"] and other["x"] < x + w
                                         and y < other["y"] + other["h"] and other["y"] < y + h)
                self.assertFalse(covered.any())

    def test_png_dimensions_unique_region_scoring_and_invalid_marks(self):
        scene = make_scene(19)
        encoded = render_picture(picture(scene))
        self.assertEqual(encoded[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", encoded[16:24]), (WIDTH, HEIGHT))
        centers = [{"x": target["x"] + target["w"] // 2,
                    "y": target["y"] + target["h"] // 2} for target in scene["targets"]]
        judged = judge_marks(scene, centers)
        self.assertEqual(judged["score"], 5)
        self.assertTrue(all(mark["correct"] for mark in judged["marks"]))
        duplicate = judge_marks(scene, [centers[0], centers[0], {"x": 0, "y": 0}])
        self.assertEqual(duplicate["score"], 1)
        self.assertEqual([mark["correct"] for mark in duplicate["marks"]], [True, False, False])
        self.assertEqual(judge_marks(scene, [])["score"], 0)
        for marks in (None, {}, [None], [{"x": True, "y": 2}], [{"x": 1.0, "y": 2}],
                      [{"x": -1, "y": 2}], [{"x": WIDTH, "y": 2}], [{"x": 2, "y": HEIGHT}],
                      [{"x": 1, "y": 2, "target": "D1"}], [{"x": 1, "y": 2}] * 6):
            with self.subTest(marks=marks), self.assertRaises(ValueError):
                judge_marks(scene, marks)

    def test_missing_or_malformed_asset_bank_fails_without_pixel_fallback(self):
        with TemporaryDirectory() as directory, patch.object(scenes, "ASSET_ROOT", Path(directory)):
            scenes._asset_scene.cache_clear()
            try:
                with self.assertRaisesRegex(ValueError, "manifest.json"):
                    make_scene(1)
                (Path(directory) / "manifest.json").write_text(json.dumps({"version": 1, "scenes": {
                    "fishing": {"original": "missing.png", "edited": "missing.png", "targets": []}}}))
                with self.assertRaisesRegex(ValueError, "5개"):
                    make_scene(1)
            finally:
                scenes._asset_scene.cache_clear()

    def test_legacy_vector_views_still_render_and_bad_raster_data_does_not(self):
        view = {"width": 40, "height": 30, "shapes": [
            {"kind": "rect", "x": 0, "y": 0, "w": 40, "h": 30, "fill": "#abcdef"},
            {"kind": "ellipse", "x": 3, "y": 3, "w": 8, "h": 6, "fill": "#112233"},
            {"kind": "polygon", "points": [[20, 5], [28, 5], [24, 12]], "fill": "#445566"},
            {"kind": "line", "points": [[5, 20], [30, 20]], "stroke": "#778899", "width": 2},
        ]}
        rendered = pygame.image.load(BytesIO(render_picture(view)))
        self.assertEqual(rendered.get_size(), (40, 30))
        self.assertEqual(rendered.get_at((0, 0))[:3], (171, 205, 239))
        for image in ("https://example.com/hidden.png", PNG_PREFIX + "not a png!"):
            with self.assertRaises(ValueError):
                render_picture({"width": WIDTH, "height": HEIGHT, "image": image})


if __name__ == "__main__":
    unittest.main()
