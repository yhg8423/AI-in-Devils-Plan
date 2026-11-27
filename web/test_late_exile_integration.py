"""The final three exile matches export and reconnect to the Day 6 main match."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from games.exile_match import test_late_rosters as fixtures
from games.exile_match.roster import read_exile_returnee
from games.match import DAY_SIX_MAIN
from .export_replays import encode_rows, export_replays
from .spectator import case_catalog, find_matches, next_match, read_match


class LateExileExportTest(unittest.TestCase):
    def test_all_eight_exiles_and_the_automatic_returnee_survive_bilingual_export(self):
        fixture = fixtures.LateExileRosterTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        *_, final = fixture.final_chain()
        winner, _ = read_exile_returnee(final)
        campaign = fixture.root / "matches/a"
        main = campaign / "day6-main/events.jsonl"
        main.parent.mkdir()
        main.write_text(encode_rows([
            {"type": "match", "game": DAY_SIX_MAIN, "seed": 1, "players": ["Q01", "Q02", "Q03", winner],
             "from_main": str(fixture.logs[-2]), "from_prison": str(fixture.logs[-1]),
             "from_returnee": str(final), "returnee": winner, "returnee_pieces": 5},
            {"type": "result", "eliminated": [], "pieces": {winner: 5}},
        ]))
        for path in campaign.glob("*/events.jsonl"):
            rows = fixture.rows(path)
            rows[0]["seed"] = 1
            path.write_text(encode_rows(rows))
            path.with_name("events.en.jsonl").write_text("")
        originals = {p: p.read_bytes() for p in campaign.glob("*/*.jsonl")}
        with TemporaryDirectory() as directory:
            output = Path(directory) / "published"
            export_replays([campaign], fixture.root, output)
            case, = case_catalog(output)
            self.assertEqual(len(case["matches"]), 11)
            self.assertEqual(len(case["exile_matches"]), 8)
            self.assertEqual([match["after"] for match in case["exile_matches"][4:]],
                             ["matches/a/day4-main", "matches/a/day5-main",
                              "matches/a/day5-prison", "matches/a/day5-prison"])
            self.assertEqual(case["exile_matches"][-1]["after"], "matches/a/day5-prison")
            logs = find_matches(output)
            self.assertEqual(next_match(output, logs, "matches/a/exile8")["id"], "matches/a/day6-main")
            header = fixture.rows(logs["matches/a/day6-main"])[0]
            self.assertEqual(header["from_returnee"], "matches/a/exile8/events.jsonl")
            fifth = fixture.rows(logs["matches/a/exile5"])[0]
            self.assertEqual(fifth["exile_schedule"], "four_player_v1")
            self.assertEqual(read_exile_returnee(logs["matches/a/exile8"],
                                               logs["matches/a/day5-main"], logs["matches/a/day5-prison"]), (winner, 5))
            for name in ("exile6", "exile7", "exile8", "day6-main"):
                for language in ("ko", "en"):
                    self.assertTrue(read_match(logs[f"matches/a/{name}"], language=language)["complete"])
        self.assertEqual({p: p.read_bytes() for p in originals}, originals)


if __name__ == "__main__":
    unittest.main()
