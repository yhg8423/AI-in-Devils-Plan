"""The first exile replay is an optional branch of an unchanged main campaign."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from games.match import DAY_ONE_MAIN, DAY_ONE_PRISON, DAY_TWO_MAIN, DAY_TWO_PRISON, FIRST_EXILE, SECOND_EXILE, THIRD_EXILE

from .export_replays import STAGES, encode_rows, export_replays
from .spectator import CASE_STAGES, case_catalog, find_matches, next_match, read_match


def campaign(root, name="example", *, mixed=False, player_count=6):
    """A completed original prefix producing four distinct exile entrants."""
    directory = root / "matches" / name
    logs = []
    players = [f"P{number:02}" for number in range(1, player_count + 1)]
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


def second_campaign(root, *, player_count=6):
    directory, logs, first = campaign(root, player_count=player_count)
    main = directory / "day2-main/events.jsonl"
    main.parent.mkdir()
    players = ["P01", "P06", *[f"P{number:02}" for number in range(7, player_count + 1)]]
    header = {"type": "match", "game": DAY_TWO_MAIN, "players": players, "seed": 1,
              "from_main": str(logs[0]), "from_prison": str(logs[1])}
    main.write_text(encode_rows([header, {"type": "result", "eliminated": ["P06"]}]))
    main.with_name("events.en.jsonl").write_text("")
    logs.append(main)
    second = directory / "exile2/events.jsonl"
    second.parent.mkdir()
    players = ["P05", "P04", "P03", "P06"]
    header = {"type": "match", "game": SECOND_EXILE, "players": players, "seed": 1,
              "model": "gpt-6.1-sol", "effort": "low", "provider": "codex", "model_players": players,
              "from_matches": [str(path) for path in logs], "from_exile": str(first)}
    event = {"type": "event", "turn": 1, "msg_type": "picture_setup", "agent_name": "System",
             "content": "그림을 기억하세요.", "visible_to": "all"}
    result = {"type": "result", "ranking": players, "survivors": players[:2], "eliminated": players[2:],
              "scores": {player: 10 for player in players}, "ranking_groups": [players[:2], players[2:]]}
    second.write_text(encode_rows([header, event, result]))
    second.with_name("events.en.jsonl").write_text(encode_rows([{"turn": 1, "text": "Remember the picture."}]))
    return directory, logs, first, second


def third_campaign(root):
    directory, logs, first, second = second_campaign(root, player_count=8)
    prison = directory / "day2-prison/events.jsonl"
    prison.parent.mkdir()
    header = {"type": "match", "game": DAY_TWO_PRISON, "players": ["P01", "P07", "P08"], "seed": 1,
              "from_main": str(logs[-1])}
    prison.write_text(encode_rows([header, {"type": "result", "eliminated": ["P07", "P08"]}]))
    prison.with_name("events.en.jsonl").write_text("")
    logs.append(prison)
    third = directory / "exile3/events.jsonl"
    third.parent.mkdir()
    players = ["P05", "P04", "P07", "P08"]
    header = {"type": "match", "game": THIRD_EXILE, "players": players, "seed": 1,
              "from_matches": [str(path) for path in logs], "from_exile": str(second)}
    event = {"type": "event", "turn": 1, "msg_type": "code_round_result", "agent_name": "System",
             "content": json.dumps({"round": 1, "question": 1, "winner": "P05", "code": "ABCD", "rank": 1}),
             "visible_to": "all"}
    result = {"type": "result", "ranking": players, "ranking_groups": [[player] for player in players],
              "survivors": players[:3], "eliminated": players[3:], "rounds": 3, "questions": 4,
              "finish_rounds": dict(zip(players[:3], (1, 2, 3), strict=True)),
              "round_winners": [json.loads(event["content"])]}
    third.write_text(encode_rows([header, event, result]))
    third.with_name("events.en.jsonl").write_text("")
    return directory, logs, first, second, third


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

    def test_second_exile_is_ordered_and_only_follows_the_first_exile(self):
        _, _, _, second = second_campaign(self.root)
        case, = case_catalog(self.root)
        self.assertEqual([match["game"] for match in case["exile_matches"]], [FIRST_EXILE, SECOND_EXILE])
        runs = find_matches(self.root)
        self.assertEqual(next_match(self.root, runs, "matches/example/exile1")["id"], "matches/example/exile2")
        self.assertIsNone(next_match(self.root, runs, "matches/example/day2-main"))
        self.assertIsNone(next_match(self.root, runs, "matches/example/exile2"))
        update_header(second, players=["P05", "P04", "P03", "P02"])
        self.assertEqual(len(case_catalog(self.root)[0]["exile_matches"]), 1)
        self.assertIsNone(next_match(self.root, runs, "matches/example/exile1"))

    def test_third_exile_continues_second_without_changing_main_navigation(self):
        _, _, first, second, third = third_campaign(self.root)
        case, = case_catalog(self.root)
        self.assertEqual([match["game"] for match in case["exile_matches"]],
                         [FIRST_EXILE, SECOND_EXILE, THIRD_EXILE])
        runs = find_matches(self.root)
        self.assertEqual(next_match(self.root, runs, "matches/example/exile2")["id"], "matches/example/exile3")
        self.assertIsNone(next_match(self.root, runs, "matches/example/exile3"))
        self.assertEqual(next_match(self.root, runs, "matches/example/day2-main")["id"],
                         "matches/example/day2-prison")
        update_header(third, from_exile=str(first))
        self.assertEqual(len(case_catalog(self.root)[0]["exile_matches"]), 2)
        self.assertIsNone(next_match(self.root, runs, "matches/example/exile2"))
        update_header(third, from_exile=str(second))
        update_header(second, players=["P05", "P04", "P03", "P08"])
        self.assertEqual(len(case_catalog(self.root)[0]["exile_matches"]), 1)


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

    def test_exports_both_exile_stages_with_portable_links_and_tied_rankings(self):
        directory, logs, first, second = second_campaign(self.source)
        originals = {path: path.read_bytes() for path in [*logs, first, second]}
        export_replays([directory], self.source, self.output)
        target = self.output / "matches/example/exile2/events.jsonl"
        rows = [json.loads(line) for line in target.read_text().splitlines()]
        self.assertEqual(rows[0]["from_exile"], "matches/example/exile1/events.jsonl")
        self.assertEqual(rows[0]["from_matches"], [f"matches/example/{stage}/events.jsonl" for stage in STAGES[:3]])
        self.assertEqual(rows[-1]["ranking_groups"], [["P05", "P04"], ["P03", "P06"]])
        self.assertEqual(read_match(target, language="en")["steps"][0]["events"][0]["translation"]["text"],
                         "Remember the picture.")
        self.assertEqual({path: path.read_bytes() for path in originals}, originals)
        case, = case_catalog(self.output)
        self.assertEqual([match["game"] for match in case["exile_matches"]], [FIRST_EXILE, SECOND_EXILE])

    def test_second_exile_without_predecessor_cannot_be_exported(self):
        directory, _, first, _ = second_campaign(self.source)
        first.unlink()
        with self.assertRaisesRegex(ValueError, "requires the first"):
            export_replays([directory], self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_exports_all_three_exiles_with_relocatable_links_and_code_results(self):
        directory, logs, first, second, third = third_campaign(self.source)
        originals = {path: path.read_bytes() for path in [*logs, first, second, third]}
        export_replays([directory], self.source, self.output)
        target = self.output / "matches/example/exile3/events.jsonl"
        rows = [json.loads(line) for line in target.read_text().splitlines()]
        self.assertEqual(rows[0]["from_exile"], "matches/example/exile2/events.jsonl")
        self.assertEqual(rows[0]["from_matches"], [f"matches/example/{stage}/events.jsonl" for stage in STAGES[:4]])
        self.assertEqual(rows[-1]["finish_rounds"], {"P05": 1, "P04": 2, "P07": 3})
        self.assertEqual(rows[-1]["questions"], 4)
        self.assertEqual(rows[-1]["round_winners"][0]["code"], "ABCD")
        self.assertEqual({path: path.read_bytes() for path in originals}, originals)
        case, = case_catalog(self.output)
        self.assertEqual([match["game"] for match in case["exile_matches"]],
                         [FIRST_EXILE, SECOND_EXILE, THIRD_EXILE])
        runs = find_matches(self.output)
        self.assertEqual(next_match(self.output, runs, "matches/example/exile2")["id"], "matches/example/exile3")

    def test_third_exile_requires_its_predecessor_before_any_export_is_written(self):
        directory, _, _, second, _ = third_campaign(self.source)
        second.unlink()
        with self.assertRaisesRegex(ValueError, "exile3 requires exile2"):
            export_replays([directory], self.source, self.output)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
