"""The ninth campaign stage coexists with all five optional exile replays."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from games.match import DAY_FIVE_MAIN, DAY_FOUR_MAIN, DAY_FOUR_PRISON

from .export_replays import encode_rows, export_replays
from .spectator import case_catalog, find_matches, next_match
from .test_exile_catalog import fifth_campaign


class HiddenWordCampaignTest(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.source = self.root / "runs"
        self.output = self.root / "play_results"
        self.campaign, self.logs, *_ = fifth_campaign(self.source)
        for stage, title, links in (
            ("day4-main", DAY_FOUR_MAIN, {"from_main": 4, "from_prison": 5}),
            ("day4-prison", DAY_FOUR_PRISON, {"from_main": 6}),
            ("day5-main", DAY_FIVE_MAIN, {"from_main": 6, "from_prison": 7}),
        ):
            log = self.campaign / stage / "events.jsonl"
            log.parent.mkdir()
            header = {"type": "match", "game": title, "players": ["P01"], "seed": 1,
                      **{key: str(self.logs[index]) for key, index in links.items()}}
            result = {"type": "result", "ranking": ["P01"], "eliminated": []}
            log.write_text(encode_rows([header, result]), encoding="utf-8")
            log.with_name("events.en.jsonl").write_text("", encoding="utf-8")
            self.logs.append(log)

    def test_exports_day_five_without_losing_exile_branches_or_adding_a_prison_stage(self):
        original = {path: path.read_bytes() for path in self.campaign.rglob("*.jsonl")}
        export_replays([self.campaign], self.source, self.output)
        self.assertEqual({path: path.read_bytes() for path in original}, original)

        case, = case_catalog(self.output)
        self.assertEqual([match["id"] for match in case["matches"]], [
            f"matches/example/{stage}" for stage in (
                "day1-main", "day1-prison", "day2-main", "day2-prison", "day3-main",
                "day3-prison", "day4-main", "day4-prison", "day5-main",
            )
        ])
        self.assertEqual([match["after"] for match in case["exile_matches"]], [
            f"matches/example/{stage}" for stage in (
                "day1-prison", "day2-main", "day2-prison", "day3-main", "day3-prison",
            )
        ])
        runs = find_matches(self.output)
        self.assertEqual(len(runs), 14)
        self.assertEqual(next_match(self.output, runs, "matches/example/day4-prison")["id"],
                         "matches/example/day5-main")
        self.assertIsNone(next_match(self.output, runs, "matches/example/day5-main"))
        header = json.loads(runs["matches/example/day5-main"].read_text().splitlines()[0])
        self.assertEqual(header["from_main"], "matches/example/day4-main/events.jsonl")
        self.assertEqual(header["from_prison"], "matches/example/day4-prison/events.jsonl")

    def test_in_progress_day_five_is_visible_but_cannot_be_exported(self):
        log = self.logs[-1]
        header = json.loads(log.read_text().splitlines()[0])
        log.write_text(encode_rows([header]), encoding="utf-8")
        case, = case_catalog(self.source)
        self.assertEqual(case["matches"][-1]["game"], DAY_FIVE_MAIN)
        self.assertEqual(case["matches"][-1]["status"], "in_progress")
        self.assertEqual(len(case["exile_matches"]), 5)
        with self.assertRaisesRegex(ValueError, "completed full match"):
            export_replays([self.campaign], self.source, self.output)
        self.assertFalse(self.output.exists())
