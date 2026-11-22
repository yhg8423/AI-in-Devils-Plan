"""Private participant axes, review previews, and safe v4 log migration."""

from base64 import b64encode
from contextlib import redirect_stderr, redirect_stdout
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from shapely.affinity import rotate

from ...match import FIFTH_EXILE, Match, encode, run_cli
from ...models import StrategyNote
from . import game
from .puzzles import COLORS, placement_polygon
from .test_game import LiveMatch, PLAYERS, PUZZLES, SOLUTION, puzzles, rows


MISSING = object()


def action(color, placements, *, axis=MISSING, submit=False):
    value = {"type": "arrange_color", "color": color, "placements": placements, "submit": submit}
    if axis is not MISSING:
        value["axis"] = axis
    return encode(value)


def workbench(puzzle, placements, *, axis=None):
    image = b"\x89PNG\r\n\x1a\nPRIVATE-WORKBENCH-" + encode(
        {"color": puzzle["id"], "placements": placements, "axis": axis}).encode()
    return {"id": sha256(image).hexdigest()[:16], "width": 1440, "height": 900,
            "image": "data:image/png;base64," + b64encode(image).decode("ascii")}


class WorkbenchGameTest(unittest.TestCase):
    def test_original_geometry_is_reused_when_interrupted_before_setup(self):
        original_event = Match.event

        def stop_after_rules(match, kind, value, **kwargs):
            original_event(match, kind, value, **kwargs)
            if kind == "rules":
                raise RuntimeError("new rules saved")

        with TemporaryDirectory() as directory, redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            full = Path(directory) / "full.jsonl"
            interrupted = Path(directory) / "resumed.jsonl"
            args = ["--players", *PLAYERS, "--seed", "1", "--model-turns", "0"]
            run_cli(game.play, title=FIFTH_EXILE, seats=(3, 4), argv=[*args, "--output", str(full)])
            with patch.object(Match, "event", stop_after_rules), self.assertRaisesRegex(RuntimeError, "new rules saved"):
                run_cli(game.play, title=FIFTH_EXILE, seats=(3, 4), argv=[*args, "--output", str(interrupted)])
            run_cli(game.play, title=FIFTH_EXILE, seats=(3, 4), argv=["--resume", "--output", str(interrupted)])
            setup = next(json.loads(row["content"]) for row in map(json.loads, full.read_text().splitlines())
                         if row.get("msg_type") == "sym_setup")
            self.assertEqual(setup["puzzle_pack"], "original")
            self.assertEqual(interrupted.read_bytes(), full.read_bytes())

    def test_pair_history_counts_relative_poses_without_grading_or_proposing_geometry(self):
        puzzle = PUZZLES[1]
        first = [{"piece": f"R{index + 1}", "x": index * 5, "y": 0, "rotation": 0} for index in range(3)]
        shifted = []
        for placement in first:
            polygon = rotate(placement_polygon(puzzle, placement), 17.3, origin=(0, 0))
            shifted.append({**placement, "x": polygon.bounds[0] + 19, "y": polygon.bounds[1] - 7,
                            "rotation": 17.3})
        changed = [{**placement, "x": placement["x"] + (1 if placement["piece"] == "R2" else 0)}
                   for placement in first]
        visits = [{"placements": placements, "count": count, "last_window": window}
                  for placements, count, window in ((first, 3, 1), (shifted, 2, 4), (changed, 4, 7))]
        with (patch.object(game, "judge", side_effect=AssertionError("history must not grade")),
              patch.object(game, "accepted_axes", side_effect=AssertionError("history must not grade"))):
            history = game.pair_history(puzzle, visits)
        self.assertEqual(history, [
            {"pieces": ("R1", "R2"), "relative_poses": 2, "most_repeated": 5},
            {"pieces": ("R1", "R3"), "relative_poses": 1, "most_repeated": 9},
            {"pieces": ("R2", "R3"), "relative_poses": 2, "most_repeated": 5},
        ])
        self.assertEqual(game.pair_history(PUZZLES[0], visits), [])

    def test_axis_parser_normalizes_finite_angles_without_conflating_missing_and_clear(self):
        for supplied, expected in ((0, 0), (90, 90), (-45, 135), (540.25, .25), (1_000_000, 100), (None, None)):
            with self.subTest(axis=supplied):
                parsed = game.parse_action(action("blue", [], axis=supplied), PUZZLES)
                self.assertEqual(parsed["axis"], expected)
                self.assertTrue(game._accepts(action("blue", [], axis=supplied), PUZZLES, "blue"))
        self.assertNotIn("axis", game.parse_action(action("blue", []), PUZZLES))
        for invalid in (True, False, float("nan"), float("inf"), -float("inf"), 1_000_001,
                        -1_000_001, 10 ** 400, "90", [], {}, {"angle": 90}):
            with self.subTest(axis=invalid), self.assertRaises(ValueError):
                game.parse_action(action("blue", [], axis=invalid), PUZZLES)
        for invalid in ({"type": "wait", "axis": 90},
                        {"type": "arrange", "placements": {color: [] for color in COLORS},
                         "submit": False, "axis": 90},
                        {**json.loads(action("blue", [], axis=90)), "offset": 1}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                game.parse_action(encode(invalid), PUZZLES)

    def test_axes_preserve_clear_and_remain_private_per_owner_and_color(self):
        def reply(name, window):
            color = tuple(COLORS)[(window - 1) % 3]
            offset = PLAYERS.index(name)
            if window == 1:
                return action(color, SOLUTION[color], axis=11 + offset)
            if window == 2:
                return action(color, SOLUTION[color], axis=41 + offset)
            if window == 3:
                return action(color, SOLUTION[color], axis=81 + offset)
            if window == 5:
                return action(color, SOLUTION[color], axis=None)
            if window == 6:
                return game.WAIT
            return action(color, SOLUTION[color])

        with puzzles(5), patch.object(game, "workbench_image", side_effect=workbench):
            match = LiveMatch(reply=reply, live_turns=28)
            result = game.play(match)
        self.assertEqual(result["turns"], 8)
        states = {(row["player"], row["window"]): row for row in rows(match, "sym_board")}
        for name in PLAYERS:
            offset = PLAYERS.index(name)
            self.assertEqual(states[name, 3]["axes"], {"blue": 11 + offset, "red": 41 + offset, "green": 81 + offset})
            self.assertEqual(states[name, 4]["axes"], states[name, 3]["axes"])
            self.assertEqual(states[name, 5]["axes"], {"blue": 11 + offset, "red": None, "green": 81 + offset})
            self.assertNotIn((name, 6), states)  # A wait does not replace private work.
            self.assertEqual(states[name, 7]["axes"], states[name, 5]["axes"])
            self.assertEqual(states[name, 7]["placements"], SOLUTION)
        for name, window, prompt, history, images in match.requests:
            self.assertEqual(len(images), 5)
            color = tuple(COLORS)[(window - 1) % 3]
            previous = next((states[name, prior] for prior in range(window - 1, 0, -1)
                             if (name, prior) in states), None)
            placements = previous["placements"][color] if previous else []
            axis = previous["axes"][color] if previous else None
            puzzle = next(puzzle for puzzle in PUZZLES if puzzle["id"] == color)
            self.assertEqual(images[3], game._image_bytes([workbench(puzzle, placements, axis=axis)])[0])
            self.assertIn(f"내 현재 반사축 각도: {encode(axis)}", prompt)
            self.assertEqual([event.msg_type for event in history], ["rules"])
        reveal = next(index for index, event in enumerate(match.events) if event.msg_type == "sym_reveal")
        for event in match.events[:reveal]:
            if event.msg_type == "sym_board":
                self.assertEqual(event.visible_to, [event.agent_name])
            if event.visible_to == "all" and event.msg_type not in {"rules", "sym_tutorial"}:
                self.assertFalse({"axes", "workbenches", "placements"} & set(json.loads(event.content)))

    def test_changed_axis_gets_another_review_but_identical_and_rigid_equivalent_views_stop(self):
        players = PLAYERS[:3]
        passes = dict.fromkeys(players, 0)
        drafts = {}

        def reply(name, window):
            passes[name] += 1
            step = passes[name]
            placement = {"piece": "B1", "x": PLAYERS.index(name) * 100, "y": 0, "rotation": 0}
            axis = 10
            if name == players[0] and step > 1:
                axis = 20
            elif name == players[1] and step > 1:
                axis = 190  # The same unoriented line as 10 degrees.
            elif name == players[2] and step > 1:
                placement = {**placement, "x": 37, "y": -19, "rotation": 17.3}
                axis = 27.3  # A rigidly moved copy of the same comparison.
            drafts[name, step] = ([placement], axis % 180)
            return action("blue", [placement], axis=axis), StrategyNote(
                text=f"OWN-{name}-{step}", review_requested=True)

        with puzzles(5), patch.object(game, "workbench_image", side_effect=workbench):
            match = LiveMatch(players, reply=reply, live_turns=7)
            game.play(match)
        self.assertEqual(passes, {players[0]: 3, players[1]: 2, players[2]: 2})
        self.assertEqual(match.live_turns, 0)
        for name in players:
            requests = [request for request in match.requests if request[0] == name]
            for step, request in enumerate(requests[1:], 1):
                placements, axis = drafts[name, step]
                self.assertEqual(request[4][3], game._image_bytes([
                    workbench(PUZZLES[0], placements, axis=axis)])[0])
            notes = [event for event in match.events if event.msg_type == "decision_note" and event.agent_name == name]
            self.assertTrue(all(event.visible_to == [name] for event in notes))
        boards = [row for row in rows(match, "sym_board") if row["window"] == 1]
        self.assertEqual({row["player"]: row["axes"]["blue"] for row in boards},
                         {players[0]: 20, players[1]: 10, players[2]: 27.3})

    def test_malformed_final_axis_preserves_last_valid_draft_and_its_axis(self):
        players = PLAYERS[:3]
        passes = dict.fromkeys(players, 0)

        def reply(name, window):
            passes[name] += 1
            step = passes[name]
            placement = {"piece": "B1", "x": step, "y": 0, "rotation": 0}
            return action("blue", [placement], axis=(37, 83, True)[step - 1]), StrategyNote(
                text=f"OWN-{name}-{step}", review_requested=True)

        with puzzles(5), patch.object(game, "workbench_image", side_effect=workbench):
            match = LiveMatch(players, reply=reply, live_turns=9)
            game.play(match)
        self.assertEqual(passes, dict.fromkeys(players, 3))
        self.assertEqual(len(rows(match, "invalid_action")), 3)
        boards = [row for row in rows(match, "sym_board") if row["window"] == 1]
        self.assertEqual(len(boards), 3)
        for row in boards:
            self.assertEqual(row["axes"]["blue"], 83)
            self.assertEqual(row["placements"]["blue"], [{"piece": "B1", "x": 2, "y": 0, "rotation": 0}])
            self.assertEqual(row["workbenches"]["blue"], workbench(
                PUZZLES[0], row["placements"]["blue"], axis=83))

    def test_review_axis_carries_across_omissions_and_explicit_null_clears_it(self):
        players = PLAYERS[:3]
        for clear, full_action in ((False, False), (True, False), (False, True)):
            with self.subTest(explicit_null=clear, full_action=full_action):
                passes = dict.fromkeys(players, 0)
                drafts = {}

                def reply(name, window):
                    passes[name] += 1
                    step = passes[name]
                    placements = [{"piece": "B1", "x": 0, "y": 0, "rotation": 0},
                                  {"piece": "B2", "x": step * 10.125, "y": -2.75, "rotation": 0}]
                    drafts[name, step] = placements
                    axis = 37 if step == 1 else None if clear and step == 2 else MISSING
                    raw = (encode({"type": "arrange", "placements": {"blue": placements, "red": [], "green": []},
                                   "submit": False}) if full_action and step == 3 else action("blue", placements, axis=axis))
                    return raw, StrategyNote(
                        text=f"OWN-{name}-{step}", review_requested=step < 3)

                with puzzles(5), patch.object(game, "workbench_image", side_effect=workbench):
                    match = LiveMatch(players, reply=reply, live_turns=9)
                    game.play(match)
                self.assertEqual(passes, dict.fromkeys(players, 3))
                expected_axis = None if clear else 37
                for name in players:
                    requests = [request for request in match.requests if request[0] == name]
                    self.assertEqual(len(requests), 3)
                    for previous_step, request in enumerate(requests[1:], 1):
                        axis = None if clear and previous_step == 2 else 37
                        self.assertEqual(request[4][3], game._image_bytes([
                            workbench(PUZZLES[0], drafts[name, previous_step], axis=axis)])[0])
                    saved = next(row for row in rows(match, "sym_board")
                                 if row["player"] == name and row["window"] == 1)
                    self.assertEqual(saved["axes"], {"blue": expected_axis, "red": None, "green": None})
                    self.assertEqual(saved["workbenches"]["blue"], workbench(
                        PUZZLES[0], drafts[name, 3], axis=expected_axis))

    def test_v4_prefix_migrates_once_and_replays_v5_private_state_without_requery(self):
        original_event = Match.event
        with (TemporaryDirectory() as directory, redirect_stdout(StringIO()), redirect_stderr(StringIO()),
              patch.object(game, "workbench_image", side_effect=workbench),
              patch("games.match.monotonic_ns", return_value=70_000_000_000)):
            root = Path(directory)
            old = root / "v4.jsonl"
            arguments = ["--players", *PLAYERS, "--seed", "19", "--model", "test", "--model-turns", "40"]

            def stop_old(match, kind, value, **kwargs):
                original_event(match, kind, value, **kwargs)
                if kind == "sym_window" and value["window"] == 3:
                    raise RuntimeError("old v4 checkpoint")

            def old_query(match, name, prompt, *args, **kwargs):
                window = rows(match, "sym_window")[-1]["window"]
                color = tuple(COLORS)[window - 1]
                return action(color, SOLUTION[color]), StrategyNote(text=f"OLD-{name}-{window}")

            with (puzzles(4), patch.object(Match, "_query", old_query), patch.object(Match, "event", stop_old),
                  self.assertRaisesRegex(RuntimeError, "old v4 checkpoint")):
                run_cli(game.play, title=FIFTH_EXILE, seats=(3, 4), argv=[*arguments, "--output", str(old)])
            old_bytes = old.read_bytes()
            old_journal = old.with_name("v4.decisions.jsonl").read_bytes()
            prefix = [json.loads(line) for line in old_bytes.splitlines()][:-1]
            self.assertEqual(json.loads(next(row["content"] for row in prefix if row.get("msg_type") == "sym_setup"))["version"], 4)
            calls = []

            def query(match, name, prompt, *args, **kwargs):
                window = rows(match, "sym_window")[-1]["window"]
                color = tuple(COLORS)[(window - 1) % 3]
                calls.append((name, window, color))
                self.assertEqual(len(kwargs["images"]), 5)
                self.assertIn(f"OLD-{name}-2", prompt)
                return action(color, SOLUTION[color], axis=17 + window, submit=window == 5), StrategyNote(text=f"NEW-{name}")

            def fork(name):
                output = root / f"{name}.jsonl"
                output.write_bytes(old_bytes)
                output.with_name(f"{name}.decisions.jsonl").write_bytes(old_journal)
                return output

            with puzzles(5), patch.object(Match, "_query", query):
                full = fork("full")
                run_cli(game.play, title=FIFTH_EXILE, seats=(3, 4), argv=["--resume", "--output", str(full)])
                expected = [json.loads(line) for line in full.read_text().splitlines()]
                self.assertEqual(expected[:len(prefix)], prefix)
                tools = [json.loads(row["content"]) for row in expected if row.get("msg_type") == "sym_tools"]
                self.assertEqual(len(tools), 1)
                self.assertEqual((tools[0]["version"], tools[0]["focus_start_window"], tools[0]["focus_color"]), (5, 1, "green"))
                self.assertEqual(sorted(set((window, color) for _, window, color in calls)),
                                 [(3, "green"), (4, "blue"), (5, "red")])
                self.assertEqual(len(calls), 12)
                for checkpoint in ("sym_tools", "sym_board"):
                    with self.subTest(checkpoint=checkpoint):
                        output = fork(checkpoint)
                        calls.clear()

                        def interrupt(match, kind, value, **kwargs):
                            original_event(match, kind, value, **kwargs)
                            if kind == checkpoint and any(event.msg_type == "sym_tools" for event in match.events):
                                raise RuntimeError("v5 checkpoint")

                        with patch.object(Match, "event", interrupt), self.assertRaisesRegex(RuntimeError, "v5 checkpoint"):
                            run_cli(game.play, title=FIFTH_EXILE, seats=(3, 4), argv=["--resume", "--output", str(output)])
                        committed = [json.loads(line) for line in output.read_text().splitlines()][:-1]
                        run_cli(game.play, title=FIFTH_EXILE, seats=(3, 4), argv=["--resume", "--output", str(output)])
                        actual = [json.loads(line) for line in output.read_text().splitlines()]
                        self.assertEqual(actual, expected)
                        self.assertEqual(actual[:len(committed)], committed)
                        self.assertEqual(len(calls), 12)
                        self.assertEqual(len(set(calls)), 12)


if __name__ == "__main__":
    unittest.main()
