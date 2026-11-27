"""Day 5 prison replays extend the campaign without changing exile branches."""

import json
import unittest

from games.match import DAY_FIVE_MAIN, DAY_FIVE_PRISON, inherited_players

from . import test_hidden_word_integration as hidden_word
from .export_replays import encode_rows, export_replays
from .spectator import CASE_STAGES, case_catalog, find_matches, next_match, read_match


class EquationTowerCampaignTest(unittest.TestCase):
    def setUp(self):
        hidden_word.HiddenWordCampaignTest.setUp(self)
        self.main = self.logs[-1]
        self.main_header = json.loads(self.main.read_text().splitlines()[0])
        self.prison = self.campaign / "day5-prison/events.jsonl"
        self.prison.parent.mkdir()
        self.translations = [{"turn": 1, "fields": {"note": "Compare the expressions on the right."}}]
        self.write_sources(["P11", "P12", "P13"])

    def write_sources(self, prison_players):
        players = ["P01", "P11", "P12", "P13", "P14"]
        pieces = dict(zip(players, (8, 6, 5, 4, 0), strict=True))
        main_result = {
            "type": "result", "ranking": players, "pieces": pieces,
            "living": [name for name in players[:-1] if name not in prison_players],
            "prison": prison_players, "eliminated": ["P14"],
        }
        self.main.write_text(encode_rows([{**self.main_header, "players": players}, main_result]), encoding="utf-8")
        self.prison_header = {
            "type": "match", "game": DAY_FIVE_PRISON, "players": prison_players, "seed": 1,
            "pieces": {name: pieces[name] for name in prison_players}, "from_main": str(self.main),
        }
        self.events = [
            {"type": "event", "turn": 0, "msg_type": "tower_setup", "agent_name": "System",
             "content": json.dumps({"players": prison_players, "order": prison_players, "discussion": False}),
             "visible_to": "all"},
            {"type": "event", "turn": 1, "msg_type": "decision_note", "agent_name": "P11",
             "content": json.dumps({"phase": "tower_execute", "note": "오른쪽 수식을 비교한다"}, ensure_ascii=False),
             "visible_to": ["P11"]},
        ]
        self.prison_result = {
            "type": "result", "ranking": prison_players,
            "ranking_groups": [[name] for name in prison_players],
            "survivors": prison_players[:-1], "eliminated": prison_players[-1:],
            "pieces_awarded": {name: 3 if name == "P11" else 0 for name in prison_players},
            "pieces": {name: pieces[name] + (3 if name == "P11" else 0) for name in prison_players},
            "scores": {name: 5 if name == "P11" else 0 for name in prison_players}, "rounds": 3,
        }
        self.prison.write_text(encode_rows([self.prison_header, *self.events, self.prison_result]), encoding="utf-8")
        self.prison.with_name("events.en.jsonl").write_text(encode_rows(self.translations), encoding="utf-8")

    def test_exports_tenth_stage_with_exile_navigation_and_translation_fields(self):
        original = {path: path.read_bytes() for path in self.campaign.rglob("*.jsonl")}
        export_replays([self.campaign], self.source, self.output)
        self.assertEqual({path: path.read_bytes() for path in original}, original)

        self.assertEqual(len(CASE_STAGES), 10)
        case, = case_catalog(self.output)
        self.assertEqual([match["id"] for match in case["matches"]], [
            f"matches/example/{stage}" for stage in (
                "day1-main", "day1-prison", "day2-main", "day2-prison", "day3-main",
                "day3-prison", "day4-main", "day4-prison", "day5-main", "day5-prison",
            )
        ])
        self.assertEqual([match["after"] for match in case["exile_matches"]], [
            f"matches/example/{stage}" for stage in (
                "day1-prison", "day2-main", "day2-prison", "day3-main", "day3-prison",
            )
        ])
        self.assertEqual(case["matches"][-1]["game"], DAY_FIVE_PRISON)
        self.assertEqual(case["matches"][-1]["status"], "complete")
        runs = find_matches(self.output)
        self.assertEqual(len(runs), 15)
        for previous, following in (("day4-prison", "day5-main"), ("day5-main", "day5-prison")):
            self.assertEqual(next_match(self.output, runs, f"matches/example/{previous}")["id"],
                             f"matches/example/{following}")
        self.assertIsNone(next_match(self.output, runs, "matches/example/day5-prison"))

        exported = runs["matches/example/day5-prison"]
        rows = [json.loads(line) for line in exported.read_text().splitlines()]
        self.assertEqual(rows[0]["from_main"], "matches/example/day5-main/events.jsonl")
        self.assertEqual(rows[0]["pieces"], self.prison_header["pieces"])
        self.assertEqual(rows[1:-1], self.events)
        self.assertEqual(rows[-1], self.prison_result)
        self.assertEqual([json.loads(line) for line in exported.with_name("events.en.jsonl").read_text().splitlines()],
                         self.translations)
        replay = read_match(exported, language="en")
        note = replay["steps"][1]["events"][0]
        self.assertEqual(note["translation"], {"fields": self.translations[0]["fields"]})
        self.assertEqual(note["visible_to"], ["P11"])

    def test_in_progress_tower_is_visible_but_exports_no_files(self):
        self.prison.write_text(encode_rows([self.prison_header, *self.events]), encoding="utf-8")
        case, = case_catalog(self.source)
        self.assertEqual(case["matches"][-1]["game"], DAY_FIVE_PRISON)
        self.assertEqual(case["matches"][-1]["status"], "in_progress")
        self.assertEqual(len(case["exile_matches"]), 5)
        with self.assertRaisesRegex(ValueError, "completed full match"):
            export_replays([self.campaign], self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_unsupported_tower_stage_exports_no_files(self):
        self.prison_header["game"] = "6일차 감옥 매치 · 그라데이션"
        self.prison.write_text(encode_rows([self.prison_header, *self.events, self.prison_result]), encoding="utf-8")
        self.assertEqual(len(case_catalog(self.source)[0]["matches"]), 9)
        with self.assertRaisesRegex(ValueError, "unexpected match stage"):
            export_replays([self.campaign], self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_tower_must_link_to_its_day_five_main(self):
        self.prison_header["from_main"] = str(self.logs[-2])
        self.prison.write_text(encode_rows([self.prison_header, *self.events, self.prison_result]), encoding="utf-8")
        self.assertEqual(len(case_catalog(self.source)[0]["matches"]), 9)
        self.assertIsNone(next_match(self.source, find_matches(self.source), "matches/example/day5-main"))
        with self.assertRaisesRegex(ValueError, "from_main must point to this run's day5-main"):
            export_replays([self.campaign], self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_continuation_accepts_three_prisoners_and_legacy_two_prisoners(self):
        for prisoners, survivors, balances in (
            (["P11", "P12", "P13"], ["P01", "P11", "P12"], [8, 9, 5]),
            (["P11", "P12"], ["P01", "P11", "P13"], [8, 9, 4]),
        ):
            with self.subTest(prisoners=prisoners):
                self.write_sources(prisoners)
                players, pieces, _ = inherited_players(self.main, DAY_FIVE_MAIN, None)
                self.assertEqual(players, prisoners)
                self.assertEqual(pieces, [self.prison_header["pieces"][name] for name in prisoners])
                players, pieces, _ = inherited_players(self.main, DAY_FIVE_MAIN, self.prison)
                self.assertEqual(players, survivors)
                self.assertEqual(pieces, balances)

    def test_continuation_rejects_wrong_roster_starting_pieces_or_stage(self):
        for changes in (
            {"players": ["P11", "P12", "P99"]},
            {"pieces": {"P11": 7, "P12": 5, "P13": 4}},
            {"game": "4일차 감옥 매치 · 벽바둑 2"},
        ):
            with self.subTest(changes=changes):
                header = {**self.prison_header, **changes}
                self.prison.write_text(encode_rows([header, *self.events, self.prison_result]), encoding="utf-8")
                with self.assertRaises(ValueError):
                    inherited_players(self.main, DAY_FIVE_MAIN, self.prison)
