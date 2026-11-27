"""Explicit exile returnees survive campaign loading and deterministic resume."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from .match import DAY_FIVE_MAIN, DAY_FIVE_PRISON, DAY_SIX_MAIN, encode, run_cli


def play(match):
    match.event("rules", "returnee test")
    return {"ranking": list(match.players), "pieces": match.pieces.copy(), "eliminated": []}


class ReturneeTest(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.output = self.root / "events.jsonl"
        self.options = dict(title=DAY_SIX_MAIN, seats=(5, 4), returnee=True,
                            previous_main=DAY_FIVE_MAIN, after_prison=True)

    def run_match(self, args, game=play):
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            run_cli(game, **self.options, argv=[*args, "--output", str(self.output)])
        return [json.loads(line) for line in self.output.read_text().splitlines()]

    def test_manual_returnee_joins_once_and_keeps_declared_pieces(self):
        rows = self.run_match(["--players", "P01", "P02", "P03", "--pieces", "2", "3", "4",
                               "--returnee", "P09", "--returnee-pieces", "7"])
        self.assertEqual(rows[0]["players"], ["P01", "P02", "P03", "P09"])
        self.assertEqual(rows[0]["pieces"], {"P01": 2, "P02": 3, "P03": 4, "P09": 7})
        self.assertEqual(rows[0]["returnee"], "P09")
        self.assertEqual(rows[-1]["pieces"], rows[0]["pieces"])

    def test_duplicate_negative_and_unidentified_returnees_leave_no_log(self):
        for extra in (["--returnee", "P01"], ["--returnee", "P09", "--returnee-pieces", "-1"],
                      ["--returnee-pieces", "7"]):
            with self.subTest(extra=extra), self.assertRaises(SystemExit):
                self.run_match(["--players", "P01", "P02", "P03", *extra])
            self.assertFalse(self.output.exists())

    def test_day_five_survivors_join_the_returnee_without_mutating_sources(self):
        sources = []
        for filename, title, players, result in (
            ("main.jsonl", DAY_FIVE_MAIN, ["P01", "P02", "P03", "P04", "P05"],
             {"ranking": ["P01", "P02", "P03", "P04", "P05"], "prison": ["P02", "P03", "P04"],
              "eliminated": ["P05"], "pieces": {"P01": 4, "P02": 2, "P03": 3, "P04": 1, "P05": 0}}),
            ("prison.jsonl", DAY_FIVE_PRISON, ["P02", "P03", "P04"],
             {"ranking": ["P02", "P03", "P04"], "eliminated": ["P04"],
              "pieces": {"P02": 5, "P03": 3, "P04": 1}}),
        ):
            path = self.root / filename
            initial = {p: n for p, n in zip(players, [4, 2, 3, 1, 0] if len(players) == 5 else [2, 3, 1])}
            path.write_text(encode({"type": "match", "game": title, "players": players, "pieces": initial})
                            + "\n" + encode({"type": "result", **result}) + "\n")
            sources.append(path)
        before = [p.read_bytes() for p in sources]
        rows = self.run_match(["--from-main", str(sources[0]), "--from-prison", str(sources[1]),
                               "--returnee", "P09"])
        self.assertEqual(rows[0]["players"], ["P01", "P02", "P03", "P09"])
        self.assertEqual(rows[0]["pieces"], {"P01": 4, "P02": 5, "P03": 3, "P09": 1})
        self.assertEqual([p.read_bytes() for p in sources], before)

    def test_resume_restores_returnee_without_double_insertion_or_changing_pieces(self):
        def stop(match):
            play(match)
            raise RuntimeError("test interruption")
        with self.assertRaisesRegex(RuntimeError, "interruption"):
            self.run_match(["--players", "P01", "P02", "P03", "--returnee", "P09",
                            "--returnee-pieces", "7"], game=stop)
        prefix = self.output.read_text().splitlines()[:-1]
        with self.assertRaises(SystemExit):
            self.run_match(["--resume", "--returnee", "P10"])
        self.assertEqual(self.output.read_text().splitlines()[:-1], prefix)
        rows = self.run_match(["--resume"])
        self.assertEqual(rows[0]["players"], ["P01", "P02", "P03", "P09"])
        self.assertEqual(rows[-1]["pieces"]["P09"], 7)
        self.assertEqual(self.output.read_text().splitlines()[:len(prefix)], prefix)
