"""Day 6 prison keeps concealed data, export links, and the two finalists."""

import json
import unittest

from games.match import DAY_SIX_MAIN, DAY_SIX_PRISON, encode, inherited_players

from . import test_hit_stay_integration as hit_stay
from .export_replays import encode_rows, export_replays
from .spectator import case_catalog, find_matches, next_match


class GradationCampaignTest(unittest.TestCase):
    def setUp(self):
        fixture = hit_stay.HitStayCampaignTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.source, self.output, self.campaign = fixture.source, fixture.output, fixture.campaign
        self.main = fixture.log
        self.log = self.campaign / "day6-prison/events.jsonl"
        self.log.parent.mkdir()
        self.header = {"type": "match", "game": DAY_SIX_PRISON, "players": ["P11", "P12"],
                       "pieces": {"P11": 0, "P12": 0}, "seed": 2, "from_main": str(self.main)}
        self.rows = [self.header,
                     {"type": "event", "turn": 0, "msg_type": "grad_layout", "agent_name": "P11",
                      "visible_to": ["P11"], "content": encode({"match": 1, "player": "P11", "numbers": [0, 1, 2, 3, 4, 5, 6]})},
                     {"type": "event", "turn": 1, "msg_type": "grad_offer", "agent_name": "P11",
                      "visible_to": "all", "content": encode({"match": 1, "round": 1, "player": "P11", "color": "black"})},
                     {"type": "result", "ranking": ["P11", "P12"], "survivors": ["P11"], "finalists": ["P11"],
                      "eliminated": ["P12"], "pieces": {"P11": 0, "P12": 0}, "pieces_awarded": {"P11": 0, "P12": 0},
                      "scores": {"P11": 4, "P12": 2}, "games": [{"match": 1, "winner": "P11"}], "matches": 1}]
        self.log.write_text(encode_rows(self.rows))
        self.log.with_name("events.en.jsonl").write_text("")

    def test_exports_twelve_stages_without_losing_exile_branches_or_privacy(self):
        before = {p: p.read_bytes() for p in self.campaign.rglob("*.jsonl")}
        export_replays([self.campaign], self.source, self.output)
        self.assertEqual({p: p.read_bytes() for p in before}, before)
        case, = case_catalog(self.output)
        self.assertEqual(len(case["matches"]), 12)
        self.assertEqual(len(case["exile_matches"]), 5)
        self.assertEqual(case["matches"][-1]["game"], DAY_SIX_PRISON)
        runs = find_matches(self.output)
        self.assertEqual(next_match(self.output, runs, "matches/example/day6-main")["id"],
                         "matches/example/day6-prison")
        self.assertIsNone(next_match(self.output, runs, "matches/example/day6-prison"))
        rows = [json.loads(line) for line in runs["matches/example/day6-prison"].read_text().splitlines()]
        self.assertEqual(rows[0]["from_main"], "matches/example/day6-main/events.jsonl")
        self.assertEqual(rows[1:3], self.rows[1:3])
        self.assertNotIn("slot", json.loads(rows[2]["content"]))
        self.assertEqual(rows[-1]["matches"], 1)
        self.assertEqual(rows[-1]["finalists"], ["P11"])

    def test_main_and_prison_survivors_combine_into_two_finalists(self):
        players, pieces, _ = inherited_players(self.main, DAY_SIX_MAIN, self.log)
        self.assertEqual(players, ["P01", "P11"])
        self.assertEqual(pieces, [0, 0])

    def test_wrong_main_source_or_incomplete_prison_cannot_be_exported(self):
        original = self.log.read_text()
        self.rows[0]["from_main"] = "missing.jsonl"
        self.log.write_text(encode_rows(self.rows))
        with self.assertRaisesRegex(ValueError, "from_main"):
            export_replays([self.campaign], self.source, self.output)
        self.assertFalse(self.output.exists())
        self.log.write_text(encode_rows([json.loads(line) for line in original.splitlines()][:-1]))
        case, = case_catalog(self.source)
        self.assertEqual(case["matches"][-1]["status"], "in_progress")
        with self.assertRaisesRegex(ValueError, "completed full match"):
            export_replays([self.campaign], self.source, self.output)
        self.assertFalse(self.output.exists())
