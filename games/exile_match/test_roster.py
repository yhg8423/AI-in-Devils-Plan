"""Initial exile rosters must retain actual results and verified campaign links."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ..match import (
    DAY_ONE_MAIN, DAY_ONE_PRISON, DAY_TWO_MAIN, DAY_TWO_PRISON, DAY_THREE_MAIN, DAY_THREE_PRISON,
    FIRST_EXILE, SECOND_EXILE, THIRD_EXILE, FOURTH_EXILE,
)
from .roster import (
    collect_exile_players, collect_second_exile_players, collect_third_exile_players, collect_fourth_exile_players,
    collect_fifth_exile_players,
)


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

    def third_sources(self, main_eliminated=None, prison_eliminated=None):
        first, logs = self.second_sources()
        main_eliminated = ["P08"] if main_eliminated is None else main_eliminated
        prison_eliminated = ["P07", "P06"] if prison_eliminated is None else prison_eliminated
        self.rewrite(logs[-1], result={"eliminated": main_eliminated})
        players = collect_second_exile_players(first, logs)
        second = self.write("a", "exile2", SECOND_EXILE, players, players[1:3],
                            from_matches=[str(path) for path in logs], from_exile=str(first))
        self.rewrite(second, result={"survivors": [players[3], players[0]]})
        if prison_eliminated:
            earlier = {*collect_exile_players(logs[:2]), *main_eliminated}
            prison = self.write("a", "day2-prison", DAY_TWO_PRISON,
                                [name for name in PLAYERS if name not in earlier], prison_eliminated,
                                from_main=str(logs[-1]))
            logs.append(prison)
        return first, second, logs

    def test_third_keeps_saved_survivor_order_and_adds_two_arrivals_without_writes(self):
        first, second, logs = self.third_sources()
        originals = {path: path.read_bytes() for path in [first, second, *logs]}
        self.assertEqual(collect_third_exile_players(second, logs), ["P08", "P13", "P07", "P06"])
        self.assertEqual({path: path.read_bytes() for path in originals}, originals)

    def test_third_includes_queued_arrival_and_leaves_excess_arrivals_waiting(self):
        _, second, logs = self.third_sources(["P08", "P07"], ["P06", "P05"])
        self.assertEqual(collect_third_exile_players(second, logs), ["P08", "P13", "P07", "P06"])

    def test_third_can_use_the_same_source_prefix_when_all_arrivals_were_in_one_batch(self):
        _, second, logs = self.third_sources(["P08", "P07", "P06"], [])
        self.assertEqual(collect_third_exile_players(second, logs), ["P08", "P13", "P07", "P06"])

    def test_third_requires_the_first_prefix_with_two_new_arrivals(self):
        _, second, logs = self.third_sources()
        with self.assertRaisesRegex(ValueError, "새 탈락자 2명"):
            collect_third_exile_players(second, logs[:3])
        _, second, logs = self.third_sources(["P08", "P07", "P06"], ["P05"])
        with self.assertRaisesRegex(ValueError, "첫 경기"):
            collect_third_exile_players(second, logs)

    def test_third_recursively_rejects_an_invalid_first_match_and_wrong_campaign(self):
        first, second, logs = self.third_sources()
        self.rewrite(first, result={"survivors": ["P13", "P13", "P09"]})
        with self.assertRaisesRegex(ValueError, "생존자 3명"):
            collect_third_exile_players(second, logs)
        first, second, logs = self.third_sources()
        other = self.first_day("b")
        self.rewrite(first, header={"from_matches": [str(path) for path in other]})
        with self.assertRaisesRegex(ValueError, "같은 캠페인"):
            collect_third_exile_players(second, logs)

    def test_third_rejects_wrong_previous_game_links_roster_and_result_partition(self):
        first, second, logs = self.third_sources()
        with self.assertRaisesRegex(ValueError, SECOND_EXILE):
            collect_third_exile_players(first, logs)
        self.rewrite(second, header={"from_exile": ""})
        with self.assertRaisesRegex(ValueError, "첫 유배지 매치"):
            collect_third_exile_players(second, logs)
        for updates in (
            {"header": {"players": ["P13", "P12", "P09", "P07"]}},
            {"result": {"survivors": ["P08", "P08"]}},
            {"result": {"survivors": ["P08", False]}},
            {"result": {"eliminated": ["P12", "P08"]}},
        ):
            with self.subTest(updates=updates):
                _, second, logs = self.third_sources()
                self.rewrite(second, **updates)
                with self.assertRaisesRegex(ValueError, "생존자 2명"):
                    collect_third_exile_players(second, logs)

    def test_third_resolves_portable_exported_previous_exile_and_campaign_links(self):
        first, second, logs = self.third_sources()
        self.rewrite(first, header={"from_matches": [str(path.relative_to(self.root)) for path in logs[:2]]})
        self.rewrite(second, header={"from_exile": str(first.relative_to(self.root)),
                                     "from_matches": [str(path.relative_to(self.root)) for path in logs[:3]]})
        self.assertEqual(collect_third_exile_players(second, logs), ["P08", "P13", "P07", "P06"])

    def fourth_sources(self, *, queued=False, new_eliminated=None):
        first, second, logs = (self.third_sources(["P08", "P07"], ["P06", "P05"]) if queued else
                               self.third_sources())
        players = collect_third_exile_players(second, logs)
        third = self.write("a", "exile3", THIRD_EXILE, players, [players[1]],
                           from_matches=[str(path) for path in logs], from_exile=str(second))
        self.rewrite(third, result={"survivors": [players[2], players[0], players[3]]})
        if not queued:
            eliminated = ["P05"] if new_eliminated is None else new_eliminated
            earlier = {*collect_exile_players(logs[:2]), "P08", "P07", "P06"}
            market = self.write("a", "day3-main", DAY_THREE_MAIN,
                                [name for name in PLAYERS if name not in earlier], eliminated,
                                from_main=str(logs[2]), from_prison=str(logs[3]))
            logs.append(market)
        return first, second, third, logs

    def test_fourth_keeps_three_saved_survivors_and_the_next_arrival_without_writes(self):
        first, second, third, logs = self.fourth_sources()
        originals = {path: path.read_bytes() for path in [first, second, third, *logs]}
        self.assertEqual(collect_fourth_exile_players(third, logs), ["P07", "P08", "P06", "P05"])
        self.assertEqual({path: path.read_bytes() for path in originals}, originals)

    def test_fourth_accepts_a_queued_arrival_without_extending_the_third_match_prefix(self):
        _, _, third, logs = self.fourth_sources(queued=True)
        self.assertEqual(len(json.loads(third.read_text().splitlines()[0])["from_matches"]), len(logs))
        self.assertEqual(collect_fourth_exile_players(third, logs), ["P07", "P08", "P06", "P05"])

    def test_fourth_uses_saved_batch_order_and_leaves_excess_arrivals_waiting(self):
        _, _, third, logs = self.fourth_sources(new_eliminated=["P05", "P04"])
        self.assertEqual(collect_fourth_exile_players(third, logs), ["P07", "P08", "P06", "P05"])

    def test_fourth_requires_the_shortest_source_prefix_with_eight_arrivals(self):
        _, _, third, logs = self.fourth_sources()
        with self.assertRaisesRegex(ValueError, "새 탈락자가 합류"):
            collect_fourth_exile_players(third, logs[:-1])
        _, _, third, logs = self.fourth_sources(queued=True)
        market = self.write("a", "day3-main", DAY_THREE_MAIN,
                            [name for name in PLAYERS if name not in {"P13", "P12", "P09", "P14", "P08", "P07", "P06", "P05"}],
                            ["P04"], from_main=str(logs[2]), from_prison=str(logs[3]))
        with self.assertRaisesRegex(ValueError, "첫 경기"):
            collect_fourth_exile_players(third, [*logs, market])

    def test_fourth_recursively_validates_earlier_results_and_campaign_sources(self):
        first, _, third, logs = self.fourth_sources()
        self.rewrite(first, result={"survivors": ["P13", "P13", "P09"]})
        with self.assertRaisesRegex(ValueError, "첫 유배지 매치의 생존자"):
            collect_fourth_exile_players(third, logs)
        _, second, third, logs = self.fourth_sources()
        self.rewrite(second, result={"survivors": ["P08", "P08"]})
        with self.assertRaisesRegex(ValueError, "두 번째 유배지 매치의 생존자"):
            collect_fourth_exile_players(third, logs)
        _, _, third, logs = self.fourth_sources()
        other = self.first_day("b")
        self.rewrite(third, header={"from_matches": [str(path) for path in [*other, *logs[2:4]]]})
        with self.assertRaisesRegex(ValueError, "같은 캠페인"):
            collect_fourth_exile_players(third, logs)

    def test_fourth_rejects_invalid_previous_game_links_roster_and_result(self):
        _, second, third, logs = self.fourth_sources()
        with self.assertRaisesRegex(ValueError, THIRD_EXILE):
            collect_fourth_exile_players(second, logs)
        self.rewrite(third, header={"from_exile": "missing-exile2.jsonl"})
        with self.assertRaisesRegex(ValueError, "두 번째 유배지 매치의 기록"):
            collect_fourth_exile_players(third, logs)
        for updates in (
            {"header": {"players": ["P08", "P13", "P07", "P05"]}},
            {"result": {"survivors": ["P07", "P08", "P08"]}},
            {"result": {"survivors": ["P07", "P08", False]}},
            {"result": {"eliminated": ["P06"]}},
        ):
            with self.subTest(updates=updates):
                _, _, third, logs = self.fourth_sources()
                self.rewrite(third, **updates)
                with self.assertRaisesRegex(ValueError, "세 번째 유배지 매치의 생존자"):
                    collect_fourth_exile_players(third, logs)

    def test_fourth_resolves_the_entire_portable_exported_exile_chain(self):
        first, second, third, logs = self.fourth_sources()
        for path in [first, second, third]:
            header = json.loads(path.read_text().splitlines()[0])
            updates = {"from_matches": [str(Path(source).relative_to(self.root)) for source in header["from_matches"]]}
            if "from_exile" in header:
                updates["from_exile"] = str(Path(header["from_exile"]).relative_to(self.root))
            self.rewrite(path, header=updates)
        self.assertEqual(collect_fourth_exile_players(third, logs), ["P07", "P08", "P06", "P05"])

    def fifth_sources(self, *, queued=False, new_eliminated=None):
        first, second, third, logs = self.fourth_sources(new_eliminated=["P05", "P04"] if queued else None)
        players = collect_fourth_exile_players(third, logs)
        fourth = self.write("a", "exile4", FOURTH_EXILE, players, [players[1]],
                            from_matches=[str(path) for path in logs], from_exile=str(third))
        self.rewrite(fourth, result={"survivors": [players[3], players[0], players[2]]})
        if not queued:
            eliminated = ["P04"] if new_eliminated is None else new_eliminated
            earlier = {*collect_exile_players(logs[:2]), "P08", "P07", "P06", "P05"}
            prison = self.write("a", "day3-prison", DAY_THREE_PRISON,
                                [name for name in PLAYERS if name not in earlier], eliminated,
                                from_main=str(logs[-1]))
            logs.append(prison)
        return first, second, third, fourth, logs

    def test_legacy_fifth_keeps_all_three_saved_survivors_and_next_arrival_without_writes(self):
        first, second, third, fourth, logs = self.fifth_sources()
        originals = {path: path.read_bytes() for path in [first, second, third, fourth, *logs]}
        self.assertEqual(collect_fifth_exile_players(fourth, logs, legacy=True), ["P05", "P07", "P06", "P04"])
        self.assertEqual({path: path.read_bytes() for path in originals}, originals)

    def test_legacy_fifth_accepts_queued_arrival_with_same_prefix_and_preserves_batch_order(self):
        _, _, _, fourth, logs = self.fifth_sources(queued=True)
        self.assertEqual(len(json.loads(fourth.read_text().splitlines()[0])["from_matches"]), len(logs))
        self.assertEqual(collect_fifth_exile_players(fourth, logs, legacy=True), ["P05", "P07", "P06", "P04"])
        _, _, _, fourth, logs = self.fifth_sources(new_eliminated=["P04", "P03"])
        self.assertEqual(collect_fifth_exile_players(fourth, logs, legacy=True), ["P05", "P07", "P06", "P04"])

    def test_legacy_fifth_requires_the_shortest_source_prefix_with_nine_arrivals(self):
        _, _, _, fourth, logs = self.fifth_sources()
        with self.assertRaisesRegex(ValueError, "새 탈락자 1명"):
            collect_fifth_exile_players(fourth, logs[:-1], legacy=True)
        _, _, _, fourth, logs = self.fifth_sources(queued=True)
        prison = self.write("a", "day3-prison", DAY_THREE_PRISON,
                            [name for name in PLAYERS if name not in {"P13", "P12", "P09", "P14", "P08", "P07", "P06", "P05", "P04"}],
                            ["P03"], from_main=str(logs[-1]))
        with self.assertRaisesRegex(ValueError, "첫 경기"):
            collect_fifth_exile_players(fourth, [*logs, prison], legacy=True)

    def test_legacy_fifth_recursively_validates_earlier_outcomes_and_campaign_sources(self):
        first, _, _, fourth, logs = self.fifth_sources()
        self.rewrite(first, result={"survivors": ["P13", "P13", "P09"]})
        with self.assertRaisesRegex(ValueError, "첫 유배지 매치의 생존자"):
            collect_fifth_exile_players(fourth, logs, legacy=True)
        _, second, _, fourth, logs = self.fifth_sources()
        self.rewrite(second, result={"survivors": ["P08", "P08"]})
        with self.assertRaisesRegex(ValueError, "두 번째 유배지 매치의 생존자"):
            collect_fifth_exile_players(fourth, logs, legacy=True)
        _, _, _, fourth, logs = self.fifth_sources()
        other = self.first_day("b")
        self.rewrite(fourth, header={"from_matches": [str(path) for path in [*other, *logs[2:5]]]})
        with self.assertRaisesRegex(ValueError, "같은 캠페인"):
            collect_fifth_exile_players(fourth, logs, legacy=True)

    def test_legacy_fifth_rejects_wrong_predecessor_and_missing_or_invalid_survivors(self):
        _, _, third, fourth, logs = self.fifth_sources()
        with self.assertRaisesRegex(ValueError, FOURTH_EXILE):
            collect_fifth_exile_players(third, logs, legacy=True)
        self.rewrite(fourth, header={"from_exile": "missing-exile3.jsonl"})
        with self.assertRaisesRegex(ValueError, "세 번째 유배지 매치의 기록"):
            collect_fifth_exile_players(fourth, logs, legacy=True)
        for updates in (
            {"header": {"players": ["P07", "P08", "P06", "P04"]}},
            {"result": {"survivors": ["P05", "P07"]}},
            {"result": {"survivors": ["P05", "P07", "P07"]}},
            {"result": {"survivors": ["P05", "P07", False]}},
            {"result": {"eliminated": ["P06"]}},
        ):
            with self.subTest(updates=updates):
                _, _, _, fourth, logs = self.fifth_sources()
                self.rewrite(fourth, **updates)
                with self.assertRaisesRegex(ValueError, "네 번째 유배지 매치의 생존자"):
                    collect_fifth_exile_players(fourth, logs, legacy=True)

    def test_legacy_fifth_resolves_the_entire_portable_exported_exile_chain(self):
        first, second, third, fourth, logs = self.fifth_sources()
        for path in [first, second, third, fourth]:
            header = json.loads(path.read_text().splitlines()[0])
            updates = {"from_matches": [str(Path(source).relative_to(self.root)) for source in header["from_matches"]]}
            if "from_exile" in header:
                updates["from_exile"] = str(Path(header["from_exile"]).relative_to(self.root))
            self.rewrite(path, header=updates)
        self.assertEqual(collect_fifth_exile_players(fourth, logs, legacy=True), ["P05", "P07", "P06", "P04"])


if __name__ == "__main__":
    unittest.main()
