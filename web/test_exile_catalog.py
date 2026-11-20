"""The first exile replay is an optional branch of an unchanged main campaign."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from games.match import DAY_ONE_MAIN, DAY_ONE_PRISON, DAY_TWO_MAIN, FIRST_EXILE

from .export_replays import STAGES, encode_rows, export_replays
from .spectator import CASE_STAGES, case_catalog, find_matches, next_match, read_match


def campaign(root, name="example", *, mixed=False):
    """A completed original prefix producing four distinct exile entrants."""
    directory = root / "matches" / name
    logs = []
    players = [f"P{number:02}" for number in range(1, 7)]
    entrants = []
    titles = [DAY_ONE_MAIN, DAY_ONE_PRISON, DAY_TWO_MAIN] if mixed else [DAY_ONE_MAIN, DAY_ONE_PRISON]
    eliminations = [["P05"], ["P04", "P03"], ["P02"]] if mixed else [["P05", "P04"], ["P03", "P02"]]
    for index, (title, eliminated) in enumerate(zip(titles, eliminations, strict=True)):
        path = directory / STAGES[index] / "events.jsonl"
        path.parent.mkdir(parents=True)
        header = {"type": "match", "game": title, "players": players.copy(), "seed": 1,
                  "model": "gpt-6-luna", "effort": "medium", "provider": "codex", "model_players": players.copy()}
        if index:
            header["from_main"] = str(logs[0])
        if index == 2:
            header["from_prison"] = str(logs[1])
        result = {"type": "result", "ranking": players.copy(), "eliminated": eliminated}
        event = {"type": "event", "turn": 1, "msg_type": "decision_note", "agent_name": players[0],
                 "content": "계획", "visible_to": [players[0]]}
        path.write_text(encode_rows([header, event, result]), encoding="utf-8")
        path.with_name("events.en.jsonl").write_text(encode_rows([{"turn": 1, "text": "Plan"}]), encoding="utf-8")
        logs.append(path)
        entrants.extend(eliminated)
        players = [name for name in players if name not in eliminated]

    exile = directory / "exile1" / "events.jsonl"
    exile.parent.mkdir()
    header = {"type": "match", "game": FIRST_EXILE, "players": entrants, "seed": 1,
              "model": "gpt-6-luna", "effort": "medium", "provider": "codex", "model_players": entrants,
              "model_overrides": {"P02": {"model": "gpt-6.1-sol", "effort": "low"}},
              "from_matches": [str(path) for path in logs], "local_settings": "/private/config"}
    event = {"type": "event", "turn": 1, "msg_type": "exile_setup", "agent_name": "System",
             "content": "퍼즐을 완성하세요.", "visible_to": "all"}
    result = {"type": "result", "ranking": entrants, "survivors": entrants[:3], "eliminated": entrants[3:],
              "turns": 12, "finish_turns": dict(zip(entrants, (3, 6, 9, 12), strict=True))}
    exile.write_text(encode_rows([header, event, result]), encoding="utf-8")
    exile.with_name("events.en.jsonl").write_text(
        encode_rows([{"turn": 1, "text": "Complete the puzzle."}]), encoding="utf-8")
    return directory, logs, exile


def update_header(path, **changes):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    rows[0].update(changes)
    path.write_text(encode_rows(rows), encoding="utf-8")


class ExileCatalogTest(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name) / "runs"

    def test_attaches_first_exile_without_inserting_it_in_the_main_chain(self):
        _, logs, exile = campaign(self.root)
        snapshots = {path: path.read_bytes() for path in [*logs, exile]}
        case, = case_catalog(self.root)
        self.assertEqual([match["id"] for match in case["matches"]],
                         [f"matches/example/{stage}" for stage in STAGES[:2]])
        match, = case["exile_matches"]
        self.assertEqual((match["id"], match["game"], match["status"]),
                         ("matches/example/exile1", FIRST_EXILE, "complete"))
        self.assertEqual(match["model_counts"], [
            {"model": "gpt-6-luna", "effort": "medium", "count": 3},
            {"model": "gpt-6.1-sol", "effort": "low", "count": 1},
        ])
        self.assertEqual({path: path.read_bytes() for path in snapshots}, snapshots)
        self.assertEqual(len(CASE_STAGES), 8)
        runs = find_matches(self.root)
        self.assertEqual(next_match(self.root, runs, "matches/example/day1-main")["id"],
                         "matches/example/day1-prison")
        self.assertIsNone(next_match(self.root, runs, "matches/example/day1-prison"))

    def test_mixed_campaign_waits_for_the_fourth_actual_elimination(self):
        _, _, exile = campaign(self.root, mixed=True)
        case, = case_catalog(self.root)
        self.assertEqual(len(case["matches"]), 3)
        self.assertEqual(len(case["exile_matches"]), 1)
        update_header(exile, from_matches=json.loads(exile.read_text().splitlines()[0])["from_matches"][:2])
        case, = case_catalog(self.root)
        self.assertNotIn("exile_matches", case)

    def test_standalone_game_still_has_a_direct_replay_without_campaign_membership(self):
        _, _, exile = campaign(self.root)
        rows = [json.loads(line) for line in exile.read_text().splitlines()]
        rows[0].pop("from_matches")
        exile.write_text(encode_rows(rows), encoding="utf-8")
        case, = case_catalog(self.root)
        self.assertNotIn("exile_matches", case)
        self.assertEqual(read_match(exile)["game"], FIRST_EXILE)
        self.assertTrue(read_match(exile)["complete"])

    def test_does_not_join_mismatched_campaign_sources_or_rosters(self):
        _, first, exile = campaign(self.root, "a")
        _, other, _ = campaign(self.root, "b")
        update_header(exile, from_matches=[str(first[0]), str(other[1])])
        cases = {case["id"]: case for case in case_catalog(self.root)}
        self.assertNotIn("exile_matches", cases["matches/a/day1-main"])
        update_header(exile, from_matches=[str(path) for path in first], players=["P02", "P03", "P04", "P05"])
        cases = {case["id"]: case for case in case_catalog(self.root)}
        self.assertNotIn("exile_matches", cases["matches/a/day1-main"])
        self.assertEqual(len(cases["matches/b/day1-main"]["exile_matches"]), 1)

    def test_sources_must_be_complete_and_in_their_original_order(self):
        _, logs, exile = campaign(self.root)
        update_header(exile, from_matches=[str(path) for path in reversed(logs)])
        self.assertNotIn("exile_matches", case_catalog(self.root)[0])
        update_header(exile, from_matches=[str(path) for path in logs])
        logs[-1].write_bytes(logs[-1].read_bytes().rstrip(b"\n"))
        self.assertNotIn("exile_matches", case_catalog(self.root)[0])

    def test_unfinished_exile_is_visible_but_never_redirects_main_navigation(self):
        _, _, exile = campaign(self.root)
        rows = [json.loads(line) for line in exile.read_text().splitlines()]
        exile.write_text(encode_rows(rows[:-1]), encoding="utf-8")
        self.assertEqual(case_catalog(self.root)[0]["exile_matches"][0]["status"], "in_progress")
        update_header(exile, from_main="matches/example/day1-prison/events.jsonl")
        self.assertNotIn("exile_matches", case_catalog(self.root)[0])
        runs = find_matches(self.root)
        self.assertIsNone(next_match(self.root, runs, "matches/example/day1-prison"))


class ExileExportTest(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.source = self.root / "runs"
        self.output = self.root / "play_results"

    def test_exports_optional_exile_and_portable_sources_after_two_or_three_original_matches(self):
        for mixed in (False, True):
            with self.subTest(mixed=mixed):
                name = "mixed" if mixed else "a"
                directory, logs, exile = campaign(self.source, name, mixed=mixed)
                sources = [*logs, exile, *(path.with_name("events.en.jsonl") for path in [*logs, exile])]
                snapshots = {path: path.read_bytes() for path in sources}
                export_replays([directory], self.source, self.output)
                self.assertEqual({path: path.read_bytes() for path in snapshots}, snapshots)
                exported = self.output / "matches" / name / "exile1" / "events.jsonl"
                header, *_, result = [json.loads(line) for line in exported.read_text().splitlines()]
                self.assertEqual(header["from_matches"],
                                 [f"matches/{name}/{stage}/events.jsonl" for stage in STAGES[:len(logs)]])
                self.assertNotIn("local_settings", header)
                self.assertEqual(result["finish_turns"], {"P05": 3, "P04": 6, "P03": 9, "P02": 12})
                english = read_match(exported, language="en")["steps"][0]["events"][0]
                self.assertEqual(english["translation"], {"text": "Complete the puzzle."})
                case = next(case for case in case_catalog(self.output) if case["id"] == f"matches/{name}/day1-main")
                self.assertEqual(len(case["matches"]), len(logs))
                self.assertEqual(case["exile_matches"][0]["id"], f"matches/{name}/exile1")
                with self.assertRaises(FileExistsError):
                    export_replays([directory], self.source, self.output)

    def test_rejects_missing_exile_translations_without_writing_a_campaign(self):
        directory, _, exile = campaign(self.source)
        exile.with_name("events.en.jsonl").write_text("", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "missing translations"):
            export_replays([directory], self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_rejects_other_campaign_sources_without_writing_a_campaign(self):
        directory, _, exile = campaign(self.source, "a")
        _, other, _ = campaign(self.source, "b")
        update_header(exile, from_matches=[str(path) for path in other])
        with self.assertRaisesRegex(ValueError, "this campaign"):
            export_replays([directory], self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_rejects_reordered_roster_and_incomplete_exile(self):
        directory, _, exile = campaign(self.source)
        update_header(exile, players=["P02", "P03", "P04", "P05"])
        with self.assertRaisesRegex(ValueError, "source order"):
            export_replays([directory], self.source, self.output)
        update_header(exile, players=["P05", "P04", "P03", "P02"])
        rows = [json.loads(line) for line in exile.read_text().splitlines()]
        exile.write_text(encode_rows(rows[:-1]), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "completed full match"):
            export_replays([directory], self.source, self.output)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
