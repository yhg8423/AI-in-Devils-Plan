"""Source selection and resume must preserve the exile roster and starting state."""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ..match import (
    DAY_ONE_MAIN, DAY_ONE_PRISON, DAY_TWO_MAIN, DAY_TWO_PRISON, DAY_THREE_MAIN, DAY_THREE_PRISON,
    FIRST_EXILE, SECOND_EXILE, THIRD_EXILE, FOURTH_EXILE, FIFTH_EXILE, run_cli,
)


class ExileCliTest(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.main = self.root / "main.jsonl"
        self.prison = self.root / "prison.jsonl"
        self.output = self.root / "exile1/events.jsonl"
        roster = [f"P{number:02}" for number in range(1, 17)]
        for path, header, eliminated in (
            (self.main, {"type": "match", "game": DAY_ONE_MAIN, "players": roster}, ["P13", "P14"]),
            (self.prison, {"type": "match", "game": DAY_ONE_PRISON, "players": roster[:12],
                           "from_main": str(self.main)}, ["P09", "P10"]),
        ):
            path.write_text(json.dumps(header) + "\n" + json.dumps({"type": "result", "eliminated": eliminated}) + "\n")

    def run_cli(self, play, *args):
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            run_cli(play, title=FIRST_EXILE, seats=4, exile_roster=True, argv=list(args))

    @staticmethod
    def play(match):
        match.event("rules", "피스 퍼즐")
        ranking = list(match.players)
        return {"ranking": ranking, "survivors": ranking[:3], "eliminated": ranking[3:], "pieces": match.pieces}

    def test_imported_roster_has_no_remaining_main_match_currency_and_sources_stay_unchanged(self):
        originals = [self.main.read_bytes(), self.prison.read_bytes()]
        self.run_cli(self.play, "--from-matches", str(self.main), str(self.prison), "--output", str(self.output))
        rows = [json.loads(line) for line in self.output.read_text().splitlines()]
        self.assertEqual(rows[0]["players"], ["P13", "P14", "P09", "P10"])
        self.assertEqual(rows[0]["pieces"], dict.fromkeys(rows[0]["players"], 0))
        self.assertEqual(rows[0]["from_matches"], [str(self.main), str(self.prison)])
        self.assertEqual(rows[-1]["survivors"], ["P13", "P14", "P09"])
        self.assertEqual([self.main.read_bytes(), self.prison.read_bytes()], originals)

    def test_sources_and_manual_players_cannot_be_combined(self):
        with self.assertRaises(SystemExit) as error:
            self.run_cli(self.play, "--from-matches", str(self.main), str(self.prison),
                         "--players", "P01", "P02", "P03", "P04", "--output", str(self.output))
        self.assertEqual(error.exception.code, 2)
        self.assertFalse(self.output.exists())

    def test_resume_restores_sources_and_rejects_changed_sources(self):
        def interrupted(match):
            match.event("rules", "피스 퍼즐")
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            self.run_cli(interrupted, "--from-matches", str(self.main), str(self.prison), "--output", str(self.output))
        before = self.output.read_bytes()
        with self.assertRaises(SystemExit):
            self.run_cli(self.play, "--resume", "--output", str(self.output), "--from-matches", str(self.main))
        self.assertEqual(self.output.read_bytes(), before)
        self.run_cli(self.play, "--resume", "--output", str(self.output))
        rows = [json.loads(line) for line in self.output.read_text().splitlines()]
        self.assertEqual(rows[0]["from_matches"], [str(self.main), str(self.prison)])
        self.assertEqual(rows[-1]["type"], "result")
        self.assertEqual(sum(row.get("msg_type") == "rules" for row in rows), 1)

    def second_cli(self, play, *args):
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            run_cli(play, title=SECOND_EXILE, seats=4, exile_roster=True,
                    previous_exile=FIRST_EXILE, argv=list(args))

    def prepare_second(self):
        self.run_cli(self.play, "--from-matches", str(self.main), str(self.prison), "--output", str(self.output))
        market = self.root / "market.jsonl"
        header = {"type": "match", "game": DAY_TWO_MAIN, "players": [f"P{i:02}" for i in range(1, 9)],
                  "from_main": str(self.main), "from_prison": str(self.prison)}
        market.write_text(json.dumps(header) + '\n' + json.dumps({"type": "result", "eliminated": ["P08"]}) + '\n')
        return market, self.root / "exile2/events.jsonl"

    def test_second_imports_survivors_and_saves_previous_exile_link(self):
        market, target = self.prepare_second()
        self.second_cli(self.play, "--from-exile", str(self.output), "--from-matches", str(self.main),
                        str(self.prison), str(market), "--output", str(target))
        header = json.loads(target.read_text().splitlines()[0])
        self.assertEqual(header["players"], ["P13", "P14", "P09", "P08"])
        self.assertEqual(header["from_exile"], str(self.output))
        self.assertEqual(header["pieces"], dict.fromkeys(header["players"], 0))

    def test_second_requires_both_import_flags_and_rejects_changes_on_resume(self):
        market, target = self.prepare_second()
        with self.assertRaises(SystemExit):
            self.second_cli(self.play, "--from-exile", str(self.output), "--output", str(target))
        self.assertFalse(target.exists())

        def interrupted(match):
            match.event("rules", "피스 퍼즐")
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            self.second_cli(interrupted, "--from-exile", str(self.output), "--from-matches", str(self.main),
                            str(self.prison), str(market), "--output", str(target))
        before = target.read_bytes()
        with self.assertRaises(SystemExit):
            self.second_cli(self.play, "--resume", "--output", str(target), "--from-exile", str(market))
        self.assertEqual(target.read_bytes(), before)
        self.second_cli(self.play, "--resume", "--output", str(target))
        rows = [json.loads(line) for line in target.read_text().splitlines()]
        self.assertEqual(rows[0]["from_exile"], str(self.output))
        self.assertEqual(rows[-1]["type"], "result")

    def third_cli(self, play, *args):
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            run_cli(play, title=THIRD_EXILE, seats=4, exile_roster=True,
                    previous_exile=SECOND_EXILE, argv=list(args))

    def prepare_third(self):
        market, second = self.prepare_second()

        def second_play(match):
            players = list(match.players)
            ranking = [players[3], players[1], players[0], players[2]]
            return {"ranking": ranking, "survivors": ranking[:2], "eliminated": ranking[2:]}

        self.second_cli(second_play, "--from-exile", str(self.output), "--from-matches", str(self.main),
                        str(self.prison), str(market), "--output", str(second))
        prison = self.root / "day2-prison.jsonl"
        header = {"type": "match", "game": DAY_TWO_PRISON, "players": [f"P{i:02}" for i in range(1, 8)],
                  "from_main": str(market)}
        prison.write_text(json.dumps(header) + '\n' + json.dumps({"type": "result", "eliminated": ["P07", "P06"]}) + '\n')
        return second, [self.main, self.prison, market, prison], self.root / "exile3/events.jsonl"

    def test_third_imports_two_survivors_and_two_arrivals_with_zero_pieces(self):
        second, sources, target = self.prepare_third()
        originals = {path: path.read_bytes() for path in [self.output, second, *sources]}
        self.third_cli(self.play, "--from-exile", str(second), "--from-matches", *map(str, sources),
                       "--output", str(target))
        rows = [json.loads(line) for line in target.read_text().splitlines()]
        self.assertEqual(rows[0]["players"], ["P08", "P14", "P07", "P06"])
        self.assertEqual(rows[0]["pieces"], dict.fromkeys(rows[0]["players"], 0))
        self.assertEqual(rows[0]["from_exile"], str(second))
        self.assertEqual(rows[0]["from_matches"], list(map(str, sources)))
        self.assertEqual(rows[-1]["survivors"], ["P08", "P14", "P07"])
        self.assertEqual({path: path.read_bytes() for path in originals}, originals)

    def test_third_requires_both_flags_and_resumes_with_unchanged_sources(self):
        second, sources, target = self.prepare_third()
        for flags in (("--from-exile", str(second)), ("--from-matches", *map(str, sources))):
            with self.subTest(flags=flags), self.assertRaises(SystemExit):
                self.third_cli(self.play, *flags, "--output", str(target))
        self.assertFalse(target.exists())

        def interrupted(match):
            match.event("rules", "비밀 코드")
            raise KeyboardInterrupt

        flags = ["--from-exile", str(second), "--from-matches", *map(str, sources)]
        with self.assertRaises(KeyboardInterrupt):
            self.third_cli(interrupted, *flags, "--output", str(target))
        before = target.read_bytes()
        for flags in (("--from-exile", str(self.output)), ("--from-matches", *map(str, sources[:-1]))):
            with self.subTest(flags=flags), self.assertRaises(SystemExit):
                self.third_cli(self.play, "--resume", "--output", str(target), *flags)
            self.assertEqual(target.read_bytes(), before)

        def resumed(match):
            match.event("rules", "비밀 코드")
            return {"survivors": list(match.players[:3]), "eliminated": list(match.players[3:])}

        self.third_cli(resumed, "--resume", "--output", str(target))
        rows = [json.loads(line) for line in target.read_text().splitlines()]
        self.assertEqual(rows[0]["from_exile"], str(second))
        self.assertEqual(rows[0]["from_matches"], list(map(str, sources)))
        self.assertEqual(rows[-1]["type"], "result")
        self.assertEqual(sum(row.get("msg_type") == "rules" for row in rows), 1)

    def fourth_cli(self, play, *args):
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            run_cli(play, title=FOURTH_EXILE, seats=4, exile_roster=True,
                    previous_exile=THIRD_EXILE, argv=list(args))

    def prepare_fourth(self, *, queued=False):
        second, sources, third = self.prepare_third()
        if queued:
            rows = [json.loads(line) for line in sources[-1].read_text().splitlines()]
            rows[-1]["eliminated"].append("P05")
            sources[-1].write_text("".join(json.dumps(row) + '\n' for row in rows))
        self.third_cli(self.play, "--from-exile", str(second), "--from-matches", *map(str, sources),
                       "--output", str(third))
        if not queued:
            market = self.root / "day3-main.jsonl"
            header = {"type": "match", "game": DAY_THREE_MAIN, "players": [f"P{i:02}" for i in range(1, 6)],
                      "from_main": str(sources[2]), "from_prison": str(sources[3])}
            market.write_text(json.dumps(header) + '\n' + json.dumps({"type": "result", "eliminated": ["P05"]}) + '\n')
            sources.append(market)
        return third, sources, self.root / "exile4/events.jsonl"

    def test_fourth_imports_three_survivors_and_one_arrival_with_zero_pieces(self):
        third, sources, target = self.prepare_fourth()
        originals = {path: path.read_bytes() for path in [third, *sources]}
        self.fourth_cli(self.play, "--from-exile", str(third), "--from-matches", *map(str, sources),
                        "--output", str(target))
        rows = [json.loads(line) for line in target.read_text().splitlines()]
        self.assertEqual(rows[0]["players"], ["P08", "P14", "P07", "P05"])
        self.assertEqual(rows[0]["pieces"], dict.fromkeys(rows[0]["players"], 0))
        self.assertEqual(rows[0]["from_exile"], str(third))
        self.assertEqual(rows[0]["from_matches"], list(map(str, sources)))
        self.assertEqual({path: path.read_bytes() for path in originals}, originals)

    def test_fourth_imports_an_already_queued_arrival_with_the_same_prefix(self):
        third, sources, target = self.prepare_fourth(queued=True)
        self.fourth_cli(self.play, "--from-exile", str(third), "--from-matches", *map(str, sources),
                        "--output", str(target))
        header = json.loads(target.read_text().splitlines()[0])
        self.assertEqual(header["players"], ["P08", "P14", "P07", "P05"])
        self.assertEqual(header["from_matches"], json.loads(third.read_text().splitlines()[0])["from_matches"])

    def test_fourth_requires_both_flags_and_restores_sources_on_resume(self):
        third, sources, target = self.prepare_fourth()
        for flags in (("--from-exile", str(third)), ("--from-matches", *map(str, sources))):
            with self.subTest(flags=flags), self.assertRaises(SystemExit):
                self.fourth_cli(self.play, *flags, "--output", str(target))
        self.assertFalse(target.exists())

        def interrupted(match):
            match.event("rules", "울타리 치기")
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            self.fourth_cli(interrupted, "--from-exile", str(third), "--from-matches", *map(str, sources),
                            "--output", str(target))
        before = target.read_bytes()
        for flags in (("--from-exile", str(self.output)), ("--from-matches", *map(str, sources[:-1]))):
            with self.subTest(flags=flags), self.assertRaises(SystemExit):
                self.fourth_cli(self.play, "--resume", "--output", str(target), *flags)
            self.assertEqual(target.read_bytes(), before)

        def resumed(match):
            match.event("rules", "울타리 치기")
            return {"survivors": list(match.players[:3]), "eliminated": list(match.players[3:])}

        self.fourth_cli(resumed, "--resume", "--output", str(target))
        rows = [json.loads(line) for line in target.read_text().splitlines()]
        self.assertEqual(rows[0]["from_exile"], str(third))
        self.assertEqual(rows[0]["from_matches"], list(map(str, sources)))
        self.assertEqual(rows[-1]["type"], "result")
        self.assertEqual(sum(row.get("msg_type") == "rules" for row in rows), 1)

    def fifth_cli(self, play, *args):
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            run_cli(play, title=FIFTH_EXILE, seats=(3, 4), exile_roster=True,
                    previous_exile=FOURTH_EXILE, argv=list(args))

    def prepare_fifth(self, *, queued=False):
        third, sources, fourth = self.prepare_fourth()
        if queued:
            rows = [json.loads(line) for line in sources[-1].read_text().splitlines()]
            rows[-1]["eliminated"].append("P04")
            sources[-1].write_text("".join(json.dumps(row) + '\n' for row in rows))
        self.fourth_cli(self.play, "--from-exile", str(third), "--from-matches", *map(str, sources),
                        "--output", str(fourth))
        if not queued:
            prison = self.root / "day3-prison.jsonl"
            header = {"type": "match", "game": DAY_THREE_PRISON, "players": [f"P{i:02}" for i in range(1, 5)],
                      "from_main": str(sources[-1])}
            prison.write_text(json.dumps(header) + '\n' + json.dumps({"type": "result", "eliminated": ["P04"]}) + '\n')
            sources.append(prison)
        return fourth, sources, self.root / "exile5/events.jsonl"

    def test_fifth_import_preserves_all_three_survivors_in_a_four_player_roster(self):
        fourth, sources, target = self.prepare_fifth()
        originals = {path: path.read_bytes() for path in [fourth, *sources]}
        self.fifth_cli(self.play, "--from-exile", str(fourth), "--from-matches", *map(str, sources),
                       "--output", str(target))
        rows = [json.loads(line) for line in target.read_text().splitlines()]
        self.assertEqual(rows[0]["players"], ["P08", "P14", "P07", "P04"])
        self.assertEqual(rows[0]["pieces"], dict.fromkeys(rows[0]["players"], 0))
        self.assertEqual(rows[0]["from_exile"], str(fourth))
        self.assertEqual(rows[0]["from_matches"], list(map(str, sources)))
        self.assertEqual({path: path.read_bytes() for path in originals}, originals)

    def test_fifth_can_import_a_queued_arrival_with_the_same_prefix(self):
        fourth, sources, target = self.prepare_fifth(queued=True)
        self.fifth_cli(self.play, "--from-exile", str(fourth), "--from-matches", *map(str, sources),
                       "--output", str(target))
        header = json.loads(target.read_text().splitlines()[0])
        self.assertEqual(header["players"], ["P08", "P14", "P07", "P04"])
        self.assertEqual(header["from_matches"], json.loads(fourth.read_text().splitlines()[0])["from_matches"])

    def test_fifth_standalone_accepts_three_or_four_players(self):
        def play(match):
            ranking = list(match.players)
            return {"ranking": ranking, "survivors": ranking[:-1], "eliminated": ranking[-1:]}

        for count in (3, 4):
            with self.subTest(count=count):
                players = [f"P{i:02}" for i in range(1, count + 1)]
                target = self.root / f"standalone-{count}.jsonl"
                self.fifth_cli(play, "--players", *players, "--output", str(target))
                rows = [json.loads(line) for line in target.read_text().splitlines()]
                self.assertEqual(rows[0]["players"], players)
                self.assertEqual(rows[-1]["survivors"], players[:-1])

    def test_fifth_requires_both_flags_and_restores_unchanged_sources_on_resume(self):
        fourth, sources, target = self.prepare_fifth()
        for flags in (("--from-exile", str(fourth)), ("--from-matches", *map(str, sources))):
            with self.subTest(flags=flags), self.assertRaises(SystemExit):
                self.fifth_cli(self.play, *flags, "--output", str(target))
        self.assertFalse(target.exists())

        def interrupted(match):
            match.event("rules", "대칭 퍼즐")
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            self.fifth_cli(interrupted, "--from-exile", str(fourth), "--from-matches", *map(str, sources),
                           "--output", str(target))
        before = target.read_bytes()
        for flags in (("--from-exile", str(self.output)), ("--from-matches", *map(str, sources[:-1]))):
            with self.subTest(flags=flags), self.assertRaises(SystemExit):
                self.fifth_cli(self.play, "--resume", "--output", str(target), *flags)
            self.assertEqual(target.read_bytes(), before)

        def resumed(match):
            match.event("rules", "대칭 퍼즐")
            return {"survivors": list(match.players[:3]), "eliminated": list(match.players[3:])}

        self.fifth_cli(resumed, "--resume", "--output", str(target))
        rows = [json.loads(line) for line in target.read_text().splitlines()]
        self.assertEqual(rows[0]["from_exile"], str(fourth))
        self.assertEqual(rows[0]["from_matches"], list(map(str, sources)))
        self.assertEqual(rows[-1]["type"], "result")
        self.assertEqual(sum(row.get("msg_type") == "rules" for row in rows), 1)


if __name__ == "__main__":
    unittest.main()
