from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from . import spectator
from .test_symmetry_localization import (
    COLORS, HEADER, PUZZLE_SEED, event, fake_atlas, fake_board, fake_image,
    fake_puzzles, payloads, public_puzzles, setup, working,
)


def fake_workbench(puzzle, placements, *, axis=None, language="en"):
    return {**fake_image(f"workbench:{axis}", puzzle, placements, language=language), "width": 1440, "height": 900}


def workspace(player, offset=0):
    data = working(player, offset)
    data["axes"] = dict(zip(COLORS, (37.5 + offset, None, 0), strict=True))
    data["workbenches"] = {puzzle["id"]: fake_workbench(
        puzzle, data["placements"][puzzle["id"]], axis=data["axes"][puzzle["id"]])
        for puzzle in fake_puzzles(PUZZLE_SEED)}
    return data


def expected_korean(data):
    expected = deepcopy(data)
    for puzzle in fake_puzzles(PUZZLE_SEED):
        color = puzzle["id"]
        expected["boards"][color] = fake_board(puzzle, data["placements"][color], detailed=True, language="ko")
        if color in data.get("workbenches", {}):
            expected["workbenches"][color] = {**data["workbenches"][color], **fake_workbench(
                puzzle, data["placements"][color], axis=data.get("axes", {}).get(color), language="ko")}
    return expected


class SymmetryWorkbenchLocalizationTest(unittest.TestCase):
    def setUp(self):
        spectator._symmetry_puzzles.cache_clear()
        spectator._korean_symmetry_image.cache_clear()
        self.addCleanup(spectator._symmetry_puzzles.cache_clear)
        self.addCleanup(spectator._korean_symmetry_image.cache_clear)
        self.enterContext(patch("games.exile_match.symmetry.puzzles.make_puzzles", side_effect=fake_puzzles))
        self.enterContext(patch("games.exile_match.symmetry.puzzles.board", side_effect=fake_board))
        self.enterContext(patch("games.exile_match.symmetry.puzzles.piece_atlas", side_effect=fake_atlas))
        self.renderer = self.enterContext(patch(
            "games.exile_match.symmetry.workbench.workbench_image", side_effect=fake_workbench))
        self.log = Path(self.enterContext(TemporaryDirectory())) / "events.jsonl"

    def write(self, events):
        raw = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in [HEADER, *events]).encode()
        self.log.write_bytes(raw)
        return raw

    def test_private_workbenches_preserve_ownership_placements_axes_and_english_output(self):
        first, second = workspace("P01"), workspace("P02", 4)
        first["workbenches"]["blue"]["caption"] = "KEEP-IMAGE-METADATA"
        events = [setup(5), public_puzzles(4), event("sym_board", first, ["P01"], "P01"),
                  event("sym_board", second, ["P02"], "P02")]
        original = deepcopy(events)
        raw = self.write(events)
        korean = payloads(spectator.read_match(self.log))
        english = payloads(spectator.read_match(self.log, language="en"))
        for index, source in ((2, first), (3, second)):
            actual = json.loads(korean[index]["content"])
            self.assertEqual(actual, expected_korean(source))
            self.assertEqual(korean[index]["visible_to"], [source["player"]])
            self.assertEqual(korean[index]["agent_name"], source["player"])
            self.assertEqual(actual["placements"], source["placements"])
            self.assertEqual(actual["axes"], source["axes"])
        for record in korean:
            if record["visible_to"] == "all":
                self.assertNotIn("workbenches", json.loads(record["content"]))
        for source, shown in zip(events, english, strict=True):
            self.assertEqual(shown, {key: source[key] for key in spectator.EVENT_FIELDS})
        calls = self.renderer.call_count
        self.assertEqual(payloads(spectator.read_match(self.log)), korean)
        self.assertEqual(self.renderer.call_count, calls)
        self.assertEqual(events, original)
        self.assertEqual(self.log.read_bytes(), raw)

    def test_reveal_uses_each_owners_chosen_axes_without_substituting_the_final_grade_axes(self):
        first, second = workspace("P01"), workspace("P02", 20)
        source = {"boards": {"P01": first, "P02": second}, "axes": {"P01": {"blue": 123}, "P02": {"blue": 7}}}
        self.write([setup(5), event("sym_reveal", source)])
        shown = payloads(spectator.read_match(self.log))[1]
        data = json.loads(shown["content"])
        self.assertEqual(data, {**source, "boards": {"P01": expected_korean(first), "P02": expected_korean(second)}})
        self.assertEqual(shown["visible_to"], "all")
        self.assertEqual(data["axes"], source["axes"])

    def test_unknown_render_id_falls_back_without_changing_image_metadata_or_the_chosen_axis(self):
        data = workspace("P01")
        archived = {**data["workbenches"]["blue"], "id": "ARCHIVED-UNKNOWN-RENDERER", "caption": "KEEP"}
        data["workbenches"]["blue"] = archived
        self.write([setup(5), event("sym_board", data, ["P01"], "P01")])
        first = payloads(spectator.read_match(self.log))
        actual = json.loads(first[1]["content"])
        self.assertEqual(actual["workbenches"]["blue"], archived)
        self.assertEqual(actual["axes"], data["axes"])
        self.assertNotEqual(actual["workbenches"]["green"]["id"], data["workbenches"]["green"]["id"])
        calls = self.renderer.call_count
        self.assertEqual(payloads(spectator.read_match(self.log)), first)
        self.assertEqual(self.renderer.call_count, calls)

    def test_axis_is_part_of_the_cache_identity_and_missing_axes_mean_no_requested_axis(self):
        data = workspace("P01")
        self.write([setup(5), event("sym_board", data, ["P01"], "P01")])
        first = json.loads(payloads(spectator.read_match(self.log))[1]["content"])
        changed = deepcopy(data)
        changed["axes"]["blue"] = 42
        self.write([setup(5), event("sym_board", changed, ["P01"], "P01")])
        mismatched = json.loads(payloads(spectator.read_match(self.log))[1]["content"])
        self.assertEqual(mismatched["workbenches"]["blue"], data["workbenches"]["blue"])
        self.assertNotEqual(mismatched["workbenches"]["blue"], first["workbenches"]["blue"])
        changed["workbenches"]["blue"] = fake_workbench(
            fake_puzzles(PUZZLE_SEED)[0], changed["placements"]["blue"], axis=42)
        self.write([setup(5), event("sym_board", changed, ["P01"], "P01")])
        actual = json.loads(payloads(spectator.read_match(self.log))[1]["content"])
        self.assertEqual(actual, expected_korean(changed))
        absent = workspace("P01")
        absent.pop("axes")
        absent["workbenches"] = {puzzle["id"]: fake_workbench(puzzle, absent["placements"][puzzle["id"]])
                                  for puzzle in fake_puzzles(PUZZLE_SEED)}
        self.write([setup(5), event("sym_board", absent, ["P01"], "P01")])
        self.assertEqual(json.loads(payloads(spectator.read_match(self.log))[1]["content"]), expected_korean(absent))


class RealWorkbenchLocalizationTest(unittest.TestCase):
    def test_v5_public_measurement_details_localize_without_changing_private_state_or_english_events(self):
        from games.exile_match.symmetry.puzzles import board, make_puzzles, piece_atlas
        from games.exile_match.symmetry.workbench import measurement_atlas, workbench_image

        spectator._symmetry_puzzles.cache_clear()
        spectator._korean_symmetry_image.cache_clear()
        self.addCleanup(spectator._symmetry_puzzles.cache_clear)
        self.addCleanup(spectator._korean_symmetry_image.cache_clear)
        puzzle = make_puzzles(PUZZLE_SEED)[1]
        public = {"puzzles": [{"id": "red", "label": "빨강", "piece_ids": [piece["id"] for piece in puzzle["pieces"]],
                   "board": board(puzzle, detailed=True), "overview": piece_atlas(puzzle, common_scale=True),
                   "details": measurement_atlas(puzzle)}]}
        placements = [{"piece": "R1", "x": .25, "y": -1.5, "rotation": 17.3}]
        own = {"player": "P01", "window": 2, "submitted": False, "placements": {"red": placements},
               "axes": {"red": 57.5}, "boards": {"red": board(puzzle, placements, detailed=True)},
               "workbenches": {"red": workbench_image(puzzle, placements, axis=57.5)}}
        events = [setup(5), event("sym_puzzles", public), event("sym_board", own, ["P01"], "P01")]
        original = deepcopy(events)
        with TemporaryDirectory() as directory:
            log = Path(directory) / "events.jsonl"
            raw = "".join(json.dumps(row) + "\n" for row in [HEADER, *events]).encode()
            log.write_bytes(raw)
            korean = payloads(spectator.read_match(log))
            shown_public = json.loads(korean[1]["content"])
            expected_piece = {**public["puzzles"][0], "board": board(puzzle, detailed=True, language="ko"),
                              "overview": piece_atlas(puzzle, common_scale=True, language="ko"),
                              "details": measurement_atlas(puzzle, language="ko")}
            self.assertEqual(shown_public, {"puzzles": [expected_piece]})
            self.assertEqual(korean[1]["visible_to"], "all")
            self.assertNotIn("placements", shown_public)
            self.assertNotIn("axes", shown_public)
            self.assertEqual(json.loads(korean[2]["content"]), {**own,
                "boards": {"red": board(puzzle, placements, detailed=True, language="ko")},
                "workbenches": {"red": workbench_image(puzzle, placements, axis=57.5, language="ko")}})
            self.assertEqual(korean[2]["visible_to"], ["P01"])
            self.assertEqual(korean[2]["agent_name"], "P01")
            for source, english in zip(events, payloads(spectator.read_match(log, language="en")), strict=True):
                self.assertEqual(english, {key: source[key] for key in spectator.EVENT_FIELDS})
            self.assertEqual(events, original)
            self.assertEqual(log.read_bytes(), raw)

    def test_real_workbench_png_localizes_while_preserving_the_recorded_private_state(self):
        from games.exile_match.symmetry.puzzles import board, make_puzzles
        from games.exile_match.symmetry.workbench import workbench_image

        spectator._symmetry_puzzles.cache_clear()
        spectator._korean_symmetry_image.cache_clear()
        self.addCleanup(spectator._symmetry_puzzles.cache_clear)
        self.addCleanup(spectator._korean_symmetry_image.cache_clear)
        puzzle = make_puzzles(PUZZLE_SEED)[1]
        placements = [{"piece": "R1", "x": .25, "y": -1.5, "rotation": 17.3}]
        data = {"player": "P01", "placements": {"red": placements}, "axes": {"red": 57.5},
                "boards": {"red": board(puzzle, placements, detailed=True)},
                "workbenches": {"red": workbench_image(puzzle, placements, axis=57.5)}}
        source = event("sym_board", data, ["P01"], "P01")
        with TemporaryDirectory() as directory:
            log = Path(directory) / "events.jsonl"
            raw = "".join(json.dumps(row) + "\n" for row in [HEADER, setup(5), source]).encode()
            log.write_bytes(raw)
            actual = payloads(spectator.read_match(log))[1]
            self.assertEqual(json.loads(actual["content"]), {**data,
                "boards": {"red": board(puzzle, placements, detailed=True, language="ko")},
                "workbenches": {"red": workbench_image(puzzle, placements, axis=57.5, language="ko")}})
            self.assertEqual(actual["visible_to"], ["P01"])
            self.assertEqual(payloads(spectator.read_match(log, language="en"))[1]["content"], source["content"])
            self.assertEqual(log.read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
