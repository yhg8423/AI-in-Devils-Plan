"""The exile returnee and both Day 5 sources survive the Day 6 export."""

import json
import unittest

from games.match import DAY_SIX_MAIN, encode

from .export_replays import encode_rows, export_replays
from .spectator import case_catalog, find_matches, next_match
from . import test_equation_tower_integration as tower


class HitStayCampaignTest(unittest.TestCase):
    def setUp(self):
        fixture = tower.EquationTowerCampaignTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.source, self.output = fixture.source, fixture.output
        self.campaign, self.main, self.prison = fixture.campaign, fixture.main, fixture.prison
        self.log = self.campaign / "day6-main/events.jsonl"
        self.log.parent.mkdir()
        players = ["P01", "P11", "P12", "P09"]
        self.header = {"type": "match", "game": DAY_SIX_MAIN, "seed": 3, "players": players,
                       "pieces": dict(zip(players, (8, 9, 5, 1))), "from_main": str(self.main),
                       "from_prison": str(self.prison), "returnee": "P09", "returnee_pieces": 1}
        self.rows = [self.header,
                     {"type": "event", "turn": 0, "msg_type": "hit_hand", "agent_name": "System",
                      "content": encode({"player": "P11", "cards": [-1, 7, 3]}), "visible_to": ["P11"]},
                     {"type": "result", "ranking": players, "eliminated": ["P09"], "living": ["P01"],
                      "prison": ["P11", "P12"], "finalists": ["P01"], "pieces": dict.fromkeys(players, 0),
                      "pieces_spent": self.header["pieces"], "chips": dict(zip(players, (183, 0, 0, 0))),
                      "interest": dict.fromkeys(players, "personal"), "prize_token": False}]
        self.log.write_text(encode_rows(self.rows))
        self.log.with_name("events.en.jsonl").write_text("")

    def test_export_keeps_returnee_private_cards_resources_and_both_sources(self):
        before = {p: p.read_bytes() for p in self.campaign.rglob("*.jsonl")}
        export_replays([self.campaign], self.source, self.output)
        self.assertEqual({p: p.read_bytes() for p in before}, before)
        case, = case_catalog(self.output)
        self.assertEqual(len(case["matches"]), 11)
        self.assertEqual(len(case["exile_matches"]), 5)
        runs = find_matches(self.output)
        self.assertEqual(next_match(self.output, runs, "matches/example/day5-prison")["id"],
                         "matches/example/day6-main")
        rows = [json.loads(line) for line in runs["matches/example/day6-main"].read_text().splitlines()]
        self.assertEqual(rows[0]["from_main"], "matches/example/day5-main/events.jsonl")
        self.assertEqual(rows[0]["from_prison"], "matches/example/day5-prison/events.jsonl")
        self.assertEqual((rows[0]["returnee"], rows[0]["returnee_pieces"]), ("P09", 1))
        self.assertEqual(rows[1], self.rows[1])
        for key in ("chips", "pieces_spent", "finalists", "prison", "interest"):
            self.assertEqual(rows[-1][key], self.rows[-1][key])

    def test_wrong_prison_source_is_rejected_before_export_creates_files(self):
        self.rows[0]["from_prison"] = str(self.main)
        self.log.write_text(encode_rows(self.rows))
        with self.assertRaisesRegex(ValueError, "from_prison"):
            export_replays([self.campaign], self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_in_progress_day_six_remains_navigable(self):
        self.log.write_text(encode_rows(self.rows[:-1]))
        case, = case_catalog(self.source)
        self.assertEqual(case["matches"][-1]["game"], DAY_SIX_MAIN)
        self.assertEqual(case["matches"][-1]["status"], "in_progress")
        with self.assertRaisesRegex(ValueError, "completed full match"):
            export_replays([self.campaign], self.source, self.output)
        self.assertFalse(self.output.exists())
