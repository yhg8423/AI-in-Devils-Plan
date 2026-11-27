"""The final exile sequence consumes every queued entrant and returns one winner."""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ..match import (
    DAY_SIX_MAIN, FIFTH_EXILE, SIXTH_EXILE, SEVENTH_EXILE, EIGHTH_EXILE, encode, run_cli,
)
from . import test_roster as fixtures
from .roster import (
    STAGES, collect_fifth_exile_players, collect_sixth_exile_players,
    collect_seventh_exile_players, collect_eighth_exile_players, read_exile_returnee,
)


class LateExileRosterTest(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.fixture = fixtures.ExileRosterTest()
        self.fixture.root = self.root
        *_, fourth, self.logs = self.fixture.fifth_sources()
        fourth_rows = self.rows(fourth)
        ranked = fourth_rows[-1]["survivors"] + fourth_rows[-1]["eliminated"]
        self.fixture.rewrite(fourth, result={"survivors": ranked[:2], "eliminated": ranked[2:]})
        self.fourth = fourth
        entered = [name for path in self.logs for name in self.rows(path)[-1]["eliminated"]]
        for index in range(6, 10):
            players = [name for name in fixtures.PLAYERS if name not in entered]
            links = {"from_main": str(self.logs[index - (1 if index % 2 else 2)])}
            if not index % 2:
                links["from_prison"] = str(self.logs[index - 1])
            path = self.fixture.write("a", f"day{index // 2 + 1}-{'prison' if index % 2 else 'main'}",
                                      STAGES[index], players, [players[0]], **links)
            self.logs.append(path)
            entered.append(players[0])
        players = collect_fifth_exile_players(fourth, self.logs[:7])
        self.fifth = self.exile("exile5", FIFTH_EXILE, players, players[:2], fourth, self.logs[:7])

    @staticmethod
    def rows(path):
        return [json.loads(line) for line in path.read_text().splitlines()]

    def exile(self, stage, title, players, survivors, previous, sources):
        path = self.fixture.write("a", stage, title, players, [name for name in players if name not in survivors],
                                  from_exile=str(previous), from_matches=[str(p) for p in sources])
        self.fixture.rewrite(path, header={"exile_schedule": "four_player_v1"}, result={"survivors": survivors})
        return path

    def final_chain(self):
        players = collect_sixth_exile_players(self.fifth, self.logs[:9])
        sixth = self.exile("exile6", SIXTH_EXILE, players, [players[-1], players[0], players[1]], self.fifth, self.logs[:9])
        players = collect_seventh_exile_players(sixth, self.logs)
        seventh = self.exile("exile7", SEVENTH_EXILE, players, [players[-1], players[1]], sixth, self.logs)
        players = collect_eighth_exile_players(seventh, self.logs)
        eighth = self.exile("exile8", EIGHTH_EXILE, players, players[:1], seventh, self.logs)
        self.fixture.rewrite(eighth, result={"returnee": players[0],
            "pieces": {players[0]: 5, players[1]: 0}, "pieces_awarded": {players[0]: 5, players[1]: 0}})
        return sixth, seventh, eighth

    def test_flags_has_four_players_and_waits_for_day_five_main(self):
        originals = {p: p.read_bytes() for p in [self.fifth, *self.logs]}
        fifth_survivors = self.rows(self.fifth)[-1]["survivors"]
        queued = [self.rows(p)[-1]["eliminated"][0] for p in self.logs[7:9]]
        self.assertEqual(collect_sixth_exile_players(self.fifth, self.logs[:9]), [*fifth_survivors, *queued])
        self.assertEqual(len(collect_sixth_exile_players(self.fifth, self.logs[:9])), 4)
        self.assertEqual({p: p.read_bytes() for p in originals}, originals)
        for logs in (self.logs[:8], self.logs):
            with self.assertRaisesRegex(ValueError, "5일차 메인"):
                collect_sixth_exile_players(self.fifth, logs)

    def test_symmetry_waits_for_day_four_main_and_keeps_both_new_arrivals(self):
        survivors = self.rows(self.fourth)[-1]["survivors"]
        arrivals = [self.rows(p)[-1]["eliminated"][0] for p in self.logs[5:7]]
        self.assertEqual(collect_fifth_exile_players(self.fourth, self.logs[:7]), [*survivors, *arrivals])
        for logs in (self.logs[:6], self.logs[:8]):
            with self.assertRaisesRegex(ValueError, "4일차 메인 이후"):
                collect_fifth_exile_players(self.fourth, logs)
        rows = self.rows(self.fourth)
        old_survivors = [*rows[-1]["survivors"], rows[-1]["eliminated"][0]]
        self.fixture.rewrite(self.fourth, result={"survivors": old_survivors, "eliminated": rows[-1]["eliminated"][1:]})
        with self.assertRaisesRegex(ValueError, "울타리 치기를 4인→2인으로 다시 실행"):
            collect_fifth_exile_players(self.fourth, self.logs[:7])

    def test_rectangle_adds_prison_arrival_and_gomoku_selects_oldest_survivor_first(self):
        sixth, seventh, eighth = self.final_chain()
        flags_survivors = self.rows(sixth)[-1]["survivors"]
        prison_arrival = self.rows(self.logs[-1])[-1]["eliminated"][0]
        self.assertEqual(collect_seventh_exile_players(sixth, self.logs), [*flags_survivors, prison_arrival])
        players = collect_eighth_exile_players(seventh, self.logs)
        self.assertEqual(players, [flags_survivors[1], prison_arrival])
        self.assertEqual(len(collect_seventh_exile_players(sixth, self.logs)), 4)
        self.assertEqual(read_exile_returnee(eighth, self.logs[-2], self.logs[-1]), (players[0], 5))
        with self.assertRaisesRegex(ValueError, "5일차 메인"):
            read_exile_returnee(eighth, self.logs[-3], self.logs[-1])

    def test_earlier_survivor_tampering_and_changed_reward_are_rejected(self):
        sixth, seventh, eighth = self.final_chain()
        winner = self.rows(eighth)[-1]["returnee"]
        for pieces in ({winner: 10}, None, [], {winner: 5.0}):
            self.fixture.rewrite(eighth, result={"pieces": pieces})
            with self.subTest(pieces=pieces), self.assertRaisesRegex(ValueError, "피스 5개"):
                read_exile_returnee(eighth)
        self.fixture.rewrite(sixth, result={"survivors": ["P99", "P98"]})
        with self.assertRaisesRegex(ValueError, "만국기의 생존자"):
            collect_eighth_exile_players(seventh, self.logs)

    def test_cli_restores_automatic_returnee_without_adding_twice_or_changing_sources(self):
        *_, eighth = self.final_chain()
        winner, _ = read_exile_returnee(eighth)
        output = self.root / "main6.jsonl"
        def play(match):
            match.event("rules", "returnee test")
            return {"ranking": list(match.players), "pieces": match.pieces.copy(), "eliminated": []}
        def stop(match):
            play(match)
            raise RuntimeError("test interruption")
        options = dict(title=DAY_SIX_MAIN, seats=(4, 5), returnee=True)
        args = ["--players", "Q01", "Q02", "Q03", "--from-returnee", str(eighth), "--output", str(output)]
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            with self.assertRaisesRegex(RuntimeError, "test interruption"):
                run_cli(stop, **options, argv=args)
            prefix = output.read_bytes().splitlines()[:-1]
            with self.assertRaises(SystemExit):
                run_cli(play, **options, argv=["--resume", "--output", str(output), "--from-returnee", str(self.fifth)])
            self.assertEqual(output.read_bytes().splitlines()[:-1], prefix)
            run_cli(play, **options, argv=["--resume", "--output", str(output)])
        rows = self.rows(output)
        self.assertEqual(rows[0]["players"], ["Q01", "Q02", "Q03", winner])
        self.assertEqual(rows[0]["from_returnee"], str(eighth))
        self.assertEqual(rows[-1]["pieces"][winner], 5)
        self.assertEqual(output.read_bytes().splitlines()[:len(prefix)], prefix)


if __name__ == "__main__":
    unittest.main()
