from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from random import Random
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from games.match import FIFTH_EXILE
from . import spectator


PLAYERS = ["P01", "P02", "P03"]
COLORS = ("blue", "red", "green")
HEADER = {"type": "match", "game": FIFTH_EXILE, "players": PLAYERS, "seed": 19}
rng = Random(HEADER["seed"])
rng.sample(PLAYERS, len(PLAYERS))
PUZZLE_SEED = rng.randrange(2 ** 32)


def fake_puzzles(seed):
    return [{"id": color, "seed": seed, "solution": "NEVER-PUBLISH"} for color in COLORS]


def fake_image(kind, puzzle, placements=(), *, language="en"):
    text = json.dumps([kind, puzzle["seed"], puzzle["id"], placements, language], sort_keys=True)
    return {"id": sha256(text.encode()).hexdigest()[:16], "width": 1440 if kind == "atlas" else 960,
            "height": 1100 if kind == "atlas" else 640, "image": f"PNG:{text}"}


def fake_board(puzzle, placements=(), *, detailed=False, language="en"):
    return fake_image("board" if detailed else "legacy", puzzle, placements, language=language)


def fake_atlas(puzzle, *, language="en"):
    return fake_image("atlas", puzzle, language=language)


def event(kind, data, visible_to="all", agent_name="System"):
    return {"type": "event", "msg_type": kind, "agent_name": agent_name, "visible_to": visible_to,
            "content": json.dumps(data, ensure_ascii=False)}


def setup(version=3):
    return event("sym_setup", {"version": version, "players": PLAYERS, "priority": PLAYERS[::-1],
                               "mode": "polygons", "survivors": 2})


def public_puzzles(version=3):
    return event("sym_puzzles", {"puzzles": [
        {"id": puzzle["id"], "label": puzzle["id"], "piece_ids": [puzzle["id"][0].upper() + "1"],
         "board": fake_board(puzzle, detailed=version >= 3),
         **({"details": fake_atlas(puzzle)} if version >= 3 else {})}
        for puzzle in fake_puzzles(PUZZLE_SEED)]})


def working(player, offset=0, *, modern=True):
    placements = {color: [{"piece": color[0].upper() + "1", "x": offset + index + .25,
                          "y": -2.5, "rotation": 17.3 + offset}]
                  for index, color in enumerate(COLORS)}
    return {"player": player, "window": 2, "submitted": False, "placements": placements,
            "boards": {puzzle["id"]: fake_board(puzzle, placements[puzzle["id"]], detailed=modern)
                       for puzzle in fake_puzzles(PUZZLE_SEED)}}


def payloads(match):
    return [step["events"][0] for step in match["steps"]]


class SymmetryLocalizationTest(unittest.TestCase):
    def setUp(self):
        spectator._symmetry_puzzles.cache_clear()
        spectator._korean_symmetry_image.cache_clear()
        self.addCleanup(spectator._symmetry_puzzles.cache_clear)
        self.addCleanup(spectator._korean_symmetry_image.cache_clear)
        self.make_puzzles = self.enterContext(patch("games.exile_match.symmetry.puzzles.make_puzzles", side_effect=fake_puzzles))
        self.board = self.enterContext(patch("games.exile_match.symmetry.puzzles.board", side_effect=fake_board))
        self.atlas = self.enterContext(patch("games.exile_match.symmetry.puzzles.piece_atlas", side_effect=fake_atlas))
        directory = self.enterContext(TemporaryDirectory())
        self.log = Path(directory) / "events.jsonl"

    def write(self, events, header=HEADER):
        content = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in [header, *events])
        self.log.write_text(content, encoding="utf-8")
        return content.encode()

    def test_korean_localizes_only_images_using_each_owners_recorded_placements(self):
        own, other = working("P01"), working("P02", 4)
        events = [setup(), public_puzzles(), event("sym_board", own, ["P01"], "P01"),
                  event("sym_board", other, ["P02"], "P02"),
                  event("decision_note", {"note": "PRIVATE-MEMO"}, ["P01"], "P01"),
                  event("sym_reveal", {"boards": {"P01": own, "P02": other}, "axes": {"P01": "FINAL-AXES"}})]
        original = deepcopy(events)
        disk = self.write(events)
        korean = payloads(spectator.read_match(self.log))
        english = payloads(spectator.read_match(self.log, language="en"))
        self.make_puzzles.assert_called_once_with(PUZZLE_SEED)
        for row, shown in zip(events, english, strict=True):
            self.assertEqual(shown, {key: row[key] for key in spectator.EVENT_FIELDS})
        for row, shown in zip(events, korean, strict=True):
            self.assertEqual(shown["visible_to"], row["visible_to"])
            self.assertEqual(shown["agent_name"], row["agent_name"])
            expected = json.loads(row["content"])
            kind = row["msg_type"]
            if kind == "sym_puzzles":
                for puzzle in expected["puzzles"]:
                    source = next(value for value in fake_puzzles(PUZZLE_SEED) if value["id"] == puzzle["id"])
                    puzzle["board"] = fake_board(source, detailed=True, language="ko")
                    puzzle["details"] = fake_atlas(source, language="ko")
            elif kind in ("sym_board", "sym_reveal"):
                boards = [expected] if kind == "sym_board" else expected["boards"].values()
                for owner in boards:
                    for puzzle in fake_puzzles(PUZZLE_SEED):
                        owner["boards"][puzzle["id"]] = fake_board(
                            puzzle, owner["placements"][puzzle["id"]], detailed=True, language="ko")
            self.assertEqual(json.loads(shown["content"]), expected)
        public = json.dumps([row for row in korean[:-1] if row["visible_to"] == "all"])
        self.assertNotIn("PRIVATE-MEMO", public)
        self.assertNotIn('"placements"', public)
        self.assertNotIn("NEVER-PUBLISH", json.dumps(korean))
        self.assertEqual(self.log.read_bytes(), disk)
        self.assertEqual(events, original)

    def test_migration_localizes_only_the_modern_suffix_and_public_tool_atlases(self):
        legacy = event("sym_board", working("P01", modern=False), ["P01"], "P01")
        tools = event("sym_tools", {"version": 3, "thinking_passes": 3,
                                   "puzzles": [{"id": puzzle["id"], "details": fake_atlas(puzzle)}
                                               for puzzle in fake_puzzles(PUZZLE_SEED)]})
        events = [setup(2), public_puzzles(2), legacy, tools,
                  event("sym_board", working("P01", 3), ["P01"], "P01")]
        self.write(events)
        shown = payloads(spectator.read_match(self.log))
        for index in range(3):
            self.assertEqual(shown[index]["content"], events[index]["content"])
        migrated = json.loads(shown[3]["content"])
        self.assertEqual(migrated["thinking_passes"], 3)
        for puzzle, source in zip(migrated["puzzles"], fake_puzzles(PUZZLE_SEED), strict=True):
            self.assertEqual(puzzle, {"id": source["id"], "details": fake_atlas(source, language="ko")})
        self.assertEqual(shown[4]["visible_to"], ["P01"])
        self.assertIn('"ko"', json.loads(shown[4]["content"])["boards"]["blue"]["image"])

    def test_archived_image_id_mismatch_keeps_original_image_and_metadata(self):
        data = working("P01")
        archived = {**data["boards"]["blue"], "id": "ARCHIVED-OTHER-GEOMETRY", "extra": "KEEP-ME"}
        data["boards"]["blue"] = archived
        self.write([setup(), event("sym_board", data, ["P01"], "P01")])
        first = spectator.read_match(self.log)
        self.assertEqual(json.loads(payloads(first)[1]["content"])["boards"]["blue"], archived)
        self.assertNotEqual(json.loads(payloads(first)[1]["content"])["boards"]["red"], data["boards"]["red"])
        rendered = self.board.call_count
        self.assertEqual(spectator.read_match(self.log), first)
        self.assertEqual(self.board.call_count, rendered)

    def test_polls_reuse_bounded_artifact_cache_and_render_only_a_new_board(self):
        own = working("P01")
        events = [setup(), public_puzzles(), event("sym_board", own, ["P01"], "P01")]
        self.write(events)
        first = spectator.read_match(self.log)
        rendered = (self.board.call_count, self.atlas.call_count)
        self.assertEqual(spectator.read_match(self.log), first)
        self.assertEqual((self.board.call_count, self.atlas.call_count), rendered)
        updated = deepcopy(own)
        updated["placements"]["blue"][0]["x"] += 1
        updated["boards"]["blue"] = fake_board(fake_puzzles(PUZZLE_SEED)[0], updated["placements"]["blue"], detailed=True)
        self.write([*events, event("sym_board", updated, ["P01"], "P01")])
        spectator.read_match(self.log)
        self.assertEqual(self.board.call_count, rendered[0] + 2)
        self.assertEqual(self.atlas.call_count, rendered[1])
        self.assertIsNotNone(spectator._korean_symmetry_image.cache_info().maxsize)

    def test_english_other_games_and_legacy_only_logs_do_not_render_images(self):
        events = [setup(), public_puzzles()]
        self.write(events)
        spectator.read_match(self.log, language="en")
        self.write(events, {**HEADER, "game": "유배지 매치 4 · 울타리 치기"})
        spectator.read_match(self.log)
        self.write([setup(2), public_puzzles(2)])
        spectator.read_match(self.log)
        self.make_puzzles.assert_not_called()
        self.board.assert_not_called()
        self.atlas.assert_not_called()


class SymmetryRasterLocalizationTest(unittest.TestCase):
    def test_existing_v3_pngs_resolve_to_the_real_korean_renderer_without_log_changes(self):
        from games.exile_match.symmetry.puzzles import board, make_puzzles, piece_atlas

        spectator._symmetry_puzzles.cache_clear()
        spectator._korean_symmetry_image.cache_clear()
        self.addCleanup(spectator._symmetry_puzzles.cache_clear)
        self.addCleanup(spectator._korean_symmetry_image.cache_clear)
        puzzle = make_puzzles(PUZZLE_SEED)[0]
        placement = [{"piece": "B1", "x": .25, "y": -1.5, "rotation": 17.3}]
        events = [setup(), event("sym_puzzles", {"puzzles": [{"id": "blue", "label": "파랑", "piece_ids": ["B1", "B2"],
                   "board": board(puzzle, detailed=True), "details": piece_atlas(puzzle)}]}),
                  event("sym_board", {"player": "P01", "placements": {"blue": placement},
                                       "boards": {"blue": board(puzzle, placement, detailed=True)}}, ["P01"], "P01")]
        with TemporaryDirectory() as directory:
            log = Path(directory) / "events.jsonl"
            raw = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in [HEADER, *events]).encode()
            log.write_bytes(raw)
            korean = payloads(spectator.read_match(log))
            english = payloads(spectator.read_match(log, language="en"))
            actual = json.loads(korean[1]["content"])["puzzles"][0]
            self.assertEqual(actual["board"], board(puzzle, detailed=True, language="ko"))
            self.assertEqual(actual["details"], piece_atlas(puzzle, language="ko"))
            self.assertEqual(json.loads(korean[2]["content"])["boards"]["blue"], board(puzzle, placement, detailed=True, language="ko"))
            self.assertNotEqual(korean[1]["content"], english[1]["content"])
            self.assertEqual(english[1]["content"], events[1]["content"])
            self.assertEqual(log.read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
