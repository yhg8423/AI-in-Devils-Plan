"""Source selection and resume must preserve the exile roster and starting state."""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ..match import DAY_ONE_MAIN, DAY_ONE_PRISON, DAY_TWO_MAIN, FIRST_EXILE, SECOND_EXILE, run_cli


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


if __name__ == "__main__":
    unittest.main()
