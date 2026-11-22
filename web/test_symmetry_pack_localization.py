"""Pack-aware Korean views preserve recorded geometry, privacy, and archive IDs."""

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from . import spectator
from .test_symmetry_localization import HEADER, PUZZLE_SEED, event, payloads, setup


def pack_artifacts(pack, *, language="en"):
    from games.exile_match.symmetry.puzzles import board, make_puzzles, piece_atlas
    from games.exile_match.symmetry.workbench import measurement_atlas, workbench_image

    puzzles = make_puzzles(PUZZLE_SEED, pack=pack)
    placements = {puzzle["id"]: [{"piece": piece["id"], "x": index * 9 + .25, "y": -1.5,
                                 "rotation": 17.3 + index * 11.25}
                                for index, piece in enumerate(puzzle["pieces"])] for puzzle in puzzles}
    axes = {puzzle["id"]: 37.5 + index * 10 for index, puzzle in enumerate(puzzles)}
    public = {"puzzles": [{"id": puzzle["id"], "label": puzzle["label"],
                           "piece_ids": [piece["id"] for piece in puzzle["pieces"]],
                           "board": board(puzzle, detailed=True, language=language),
                           "details": measurement_atlas(puzzle, language=language),
                           "overview": piece_atlas(puzzle, common_scale=True, language=language)}
                          for puzzle in puzzles]}
    private = {"player": "P01", "window": 1, "submitted": False, "placements": placements, "axes": axes,
               "boards": {puzzle["id"]: board(puzzle, placements[puzzle["id"]], detailed=True, language=language)
                          for puzzle in puzzles},
               "workbenches": {puzzle["id"]: workbench_image(puzzle, placements[puzzle["id"]],
                                                            axis=axes[puzzle["id"]], language=language)
                               for puzzle in puzzles}}
    return public, private


class SymmetryPackLocalizationTest(unittest.TestCase):
    def setUp(self):
        spectator._symmetry_puzzles.cache_clear()
        spectator._korean_symmetry_image.cache_clear()
        self.addCleanup(spectator._symmetry_puzzles.cache_clear)
        self.addCleanup(spectator._korean_symmetry_image.cache_clear)
        self.log = Path(self.enterContext(TemporaryDirectory())) / "events.jsonl"

    def write(self, events):
        raw = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in [HEADER, *events]).encode()
        self.log.write_bytes(raw)
        return raw

    def test_real_original_and_implicit_broadcast_packs_localize_with_independent_warm_caches(self):
        for pack in ("broadcast", "original", "broadcast"):
            with self.subTest(pack=pack):
                public, private = pack_artifacts(pack)
                korean_public, korean_private = pack_artifacts(pack, language="ko")
                start = setup(5)
                if pack == "original":
                    start = event("sym_setup", {**json.loads(start["content"]), "puzzle_pack": pack})
                events = [start, event("sym_puzzles", public), event("sym_board", private, ["P01"], "P01")]
                original = deepcopy(events)
                raw = self.write(events)
                korean = payloads(spectator.read_match(self.log))
                self.assertEqual(json.loads(korean[1]["content"]), korean_public)
                self.assertEqual(json.loads(korean[2]["content"]), korean_private)
                self.assertEqual(korean[2]["visible_to"], ["P01"])
                self.assertEqual(korean[2]["agent_name"], "P01")
                self.assertNotIn("placements", json.loads(korean[1]["content"]))
                self.assertNotIn("axes", json.loads(korean[1]["content"]))
                for source, shown in zip(events, payloads(spectator.read_match(self.log, language="en")), strict=True):
                    self.assertEqual(shown, {key: source[key] for key in spectator.EVENT_FIELDS})
                self.assertEqual(payloads(spectator.read_match(self.log)), korean)
                self.assertEqual(self.log.read_bytes(), raw)
                self.assertEqual(events, original)
        self.assertEqual(spectator._symmetry_puzzles.cache_info().currsize, 2)

    def test_setup_pack_is_not_changed_by_later_tools_metadata(self):
        public, private = pack_artifacts("broadcast")
        korean_public, korean_private = pack_artifacts("broadcast", language="ko")
        tools = {"version": 6, "puzzle_pack": "original", "thinking_passes": 3,
                 "focus_mode": "one_color", "focus_start_window": 1,
                 "puzzles": [{"id": puzzle["id"], "details": puzzle["details"], "overview": puzzle["overview"]}
                             for puzzle in public["puzzles"]]}
        events = [setup(5), event("sym_puzzles", public), event("sym_tools", tools),
                  event("sym_board", private, ["P01"], "P01")]
        raw = self.write(events)
        korean = payloads(spectator.read_match(self.log))
        expected_tools = {**tools, "puzzles": [{"id": puzzle["id"], "details": puzzle["details"], "overview": puzzle["overview"]}
                                               for puzzle in korean_public["puzzles"]]}
        self.assertEqual(json.loads(korean[2]["content"]), expected_tools)
        self.assertEqual(json.loads(korean[3]["content"]), korean_private)
        self.assertEqual(spectator._symmetry_puzzles.cache_info().currsize, 1)
        self.assertEqual(self.log.read_bytes(), raw)

    def test_pack_selection_retains_exact_id_guard_for_images_from_different_geometry(self):
        public, private = pack_artifacts("broadcast")
        original_public, original_private = pack_artifacts("original")
        start = event("sym_setup", {**json.loads(setup(5)["content"]), "puzzle_pack": "original"})
        events = [start, event("sym_puzzles", public), event("sym_board", private, ["P01"], "P01")]
        raw = self.write(events)
        shown = payloads(spectator.read_match(self.log))
        actual_public, actual_private = json.loads(shown[1]["content"]), json.loads(shown[2]["content"])
        checked = 0
        for source, other, actual in zip(public["puzzles"], original_public["puzzles"], actual_public["puzzles"], strict=True):
            for kind in ("board", "details", "overview"):
                if source[kind]["id"] != other[kind]["id"]:
                    self.assertEqual(actual[kind], source[kind])
                    checked += 1
        for kind in ("boards", "workbenches"):
            for color, source in private[kind].items():
                if source["id"] != original_private[kind][color]["id"]:
                    self.assertEqual(actual_private[kind][color], source)
                    checked += 1
        self.assertGreater(checked, 0)
        self.assertEqual(actual_private["placements"], private["placements"])
        self.assertEqual(actual_private["axes"], private["axes"])
        self.assertEqual(shown[2]["visible_to"], ["P01"])
        self.assertEqual(self.log.read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
