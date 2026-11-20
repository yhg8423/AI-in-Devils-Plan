"""Initial exile rosters must retain actual results and verified campaign links."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ..match import DAY_ONE_MAIN, DAY_ONE_PRISON, DAY_TWO_MAIN, DAY_TWO_PRISON, FIRST_EXILE
from .roster import collect_exile_players, collect_second_exile_players


PLAYERS = [f"P{number:02}" for number in range(1, 17)]


class ExileRosterTest(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def write(self, campaign, stage, title, players, eliminated, **links):
        path = self.root / "matches" / campaign / stage / "events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        header = {"type": "match", "game": title, "players": players, **links}
        result = {"type": "result", "eliminated": eliminated}
        path.write_text(json.dumps(header) + "\n" + json.dumps(result) + "\n", encoding="utf-8")
        return path

    def first_day(self, campaign="a", main_eliminated=None, prison_eliminated=None):
        main_eliminated = ["P13", "P12"] if main_eliminated is None else main_eliminated
        prison_eliminated = ["P09", "P14"] if prison_eliminated is None else prison_eliminated
        main = self.write(campaign, "day1-main", DAY_ONE_MAIN, PLAYERS, main_eliminated)
        prison = self.write(campaign, "day1-prison", DAY_ONE_PRISON,
                            [p for p in PLAYERS if p not in main_eliminated], prison_eliminated,
                            from_main=str(main))
        return [main, prison]

    def rewrite(self, path, *, header=None, result=None):
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        if header:
            rows[0].update(header)
        if result:
            rows[-1].update(result)
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    def test_first_four_follow_elimination_order_without_modifying_sources(self):
        logs = self.first_day()
        snapshots = [path.read_bytes() for path in logs]
        self.assertEqual(collect_exile_players(logs), ["P13", "P12", "P09", "P14"])
        self.assertEqual([path.read_bytes() for path in logs], snapshots)

    def test_one_day_one_elimination_waits_for_the_next_main_result(self):
        logs = self.first_day(main_eliminated=["P10"], prison_eliminated=["P09", "P15"])
        market = self.write("a", "day2-main", DAY_TWO_MAIN,
                            [p for p in PLAYERS if p not in {"P10", "P09", "P15"}], ["P07"],
                            from_main=str(logs[0]), from_prison=str(logs[1]))
        self.assertEqual(collect_exile_players([*logs, market]), ["P10", "P09", "P15", "P07"])
        with self.assertRaisesRegex(ValueError, "현재 수집된 참가자는 3명"):
            collect_exile_players(logs)

    def test_portable_export_links_resolve_relative_to_the_record_root(self):
        logs = self.first_day()
        self.rewrite(logs[1], header={"from_main": "matches/a/day1-main/events.jsonl"})
        self.assertEqual(collect_exile_players(logs), ["P13", "P12", "P09", "P14"])

    def test_rejects_a_different_campaign_and_mismatched_second_main_links(self):
        one = self.first_day("a", ["P10"], ["P09", "P15"])
        other = self.first_day("b", ["P10"], ["P09", "P15"])
        with self.assertRaisesRegex(ValueError, "같은 캠페인"):
            collect_exile_players([one[0], other[1]])
        market = self.write("a", "day2-main", DAY_TWO_MAIN,
                            [p for p in PLAYERS if p not in {"P10", "P09", "P15"}], ["P07"],
                            from_main=str(other[0]), from_prison=str(one[1]))
        with self.assertRaisesRegex(ValueError, "같은 캠페인"):
            collect_exile_players([*one, market])

    def test_rejects_duplicate_entry_in_a_later_roster(self):
        logs = self.first_day()
        self.rewrite(logs[1], header={"players": [*PLAYERS]}, result={"eliminated": ["P13", "P09"]})
        with self.assertRaisesRegex(ValueError, "다시 출전"):
            collect_exile_players(logs)

    def test_rejects_duplicate_or_unknown_eliminated_ids_and_invalid_types(self):
        logs = self.first_day()
        for eliminated in (["P09", "P09"], ["P99", "P14"], "P09", [False, "P14"]):
            with self.subTest(eliminated=eliminated):
                self.rewrite(logs[1], result={"eliminated": eliminated})
                with self.assertRaisesRegex(ValueError, "탈락 명단"):
                    collect_exile_players(logs)

    def test_rejects_incomplete_reordered_repeated_and_missing_sources(self):
        logs = self.first_day()
        for paths in ([], [logs[1], logs[0]], [logs[0], logs[0]]):
            with self.subTest(paths=paths), self.assertRaises(ValueError):
                collect_exile_players(paths)
        self.rewrite(logs[1], result={"type": "interrupted"})
        with self.assertRaisesRegex(ValueError, "완료된 매치 결과"):
            collect_exile_players(logs)

    def test_rejects_excess_entrants_instead_of_choosing_arbitrary_four(self):
        logs = self.first_day(prison_eliminated=["P09", "P14", "P15"])
        with self.assertRaisesRegex(ValueError, "4명을 초과"):
            collect_exile_players(logs)

    def test_rejects_unexpected_source_links_and_invalid_player_rosters(self):
        logs = self.first_day()
        self.rewrite(logs[0], header={"from_main": str(logs[0])})
        with self.assertRaisesRegex(ValueError, "진행 순서"):
            collect_exile_players(logs)
        logs = self.first_day()
        for players in ([], ["P09", "P09"], ["P09", 3], ["P 09", "P14"]):
            with self.subTest(players=players):
                self.rewrite(logs[1], header={"players": players})
                with self.assertRaisesRegex(ValueError, "참가자 명단"):
                    collect_exile_players(logs)

    def second_sources(self):
        logs = self.first_day()
        first = collect_exile_players(logs)
        previous = self.write("a", "exile1", FIRST_EXILE, first, first[3:],
                              from_matches=[str(path) for path in logs])
        self.rewrite(previous, result={"survivors": first[:3], "ranking": first})
        market = self.write("a", "day2-main", DAY_TWO_MAIN,
                            [name for name in PLAYERS if name not in first], ["P08"],
                            from_main=str(logs[0]), from_prison=str(logs[1]))
        return previous, [*logs, market]

    def test_second_exile_keeps_three_survivors_and_adds_next_arrival(self):
        previous, logs = self.second_sources()
        originals = {path: path.read_bytes() for path in [previous, *logs]}
        self.assertEqual(collect_second_exile_players(previous, logs), ["P13", "P12", "P09", "P08"])
        self.assertEqual({path: path.read_bytes() for path in originals}, originals)

    def test_second_exile_rejects_wrong_prefix_and_invalid_survivors(self):
        previous, logs = self.second_sources()
        self.rewrite(previous, header={"from_matches": [str(logs[1]), str(logs[0])]})
        with self.assertRaisesRegex(ValueError, "같은 캠페인"):
            collect_second_exile_players(previous, logs)
        self.rewrite(previous, header={"from_matches": [str(path) for path in logs[:2]]})
        for survivors in (["P13", "P13", "P09"], ["P13", "P12", "P14"], ["P13", "P12", False]):
            with self.subTest(survivors=survivors):
                self.rewrite(previous, result={"survivors": survivors})
                with self.assertRaisesRegex(ValueError, "생존자 3명"):
                    collect_second_exile_players(previous, logs)

    def test_second_exile_requires_new_arrival_and_rejects_extra_stages(self):
        previous, logs = self.second_sources()
        with self.assertRaises(ValueError):
            collect_second_exile_players(previous, logs[:2])
        prison = self.write("a", "day2-prison", DAY_TWO_PRISON,
                            [name for name in PLAYERS if name not in {"P13", "P12", "P09", "P14", "P08"}],
                            ["P07"], from_main=str(logs[-1]))
        with self.assertRaisesRegex(ValueError, "첫 경기"):
            collect_second_exile_players(previous, [*logs, prison])

    def test_simultaneous_new_eliminations_arrive_in_the_saved_order(self):
        previous, logs = self.second_sources()
        self.rewrite(logs[-1], result={"eliminated": ["P08", "P07"]})
        self.assertEqual(collect_second_exile_players(previous, logs), ["P13", "P12", "P09", "P08"])


if __name__ == "__main__":
    unittest.main()
