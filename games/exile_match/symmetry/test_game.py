"""Three-color private work, strict full replacements, race privacy, and resume."""

from base64 import b64decode, b64encode
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from copy import deepcopy
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from ...match import FIFTH_EXILE, Match, encode, run_cli
from ...models import OpenAILanguageModel, StrategyNote
from . import game
from .puzzles import COLORS, judge, make_puzzles


PLAYERS = ("P01", "P02", "P03", "P04")
PUZZLES = make_puzzles(19)
SOLUTION = {puzzle["id"]: puzzle["solution"] for puzzle in PUZZLES}


def arrange(placements=SOLUTION, submit=True):
    return encode({"type": "arrange", "placements": placements, "submit": submit})


def rows(match, kind):
    return [json.loads(event.content) for event in match.events if event.msg_type == kind]


def render(puzzle, placements=()):
    image = b"\x89PNG\r\n\x1a\nEXACT-OWN-PNG" + encode({"color": puzzle["id"], "placements": placements}).encode()
    return {"id": sha256(image).hexdigest()[:16], "width": 960, "height": 640,
            "image": "data:image/png;base64," + b64encode(image).decode("ascii")}


@contextmanager
def puzzles():
    with (patch.object(game, "make_puzzles", return_value=[{**puzzle, "internal": "NEVER-PUBLISH"} for puzzle in PUZZLES]),
          patch.object(game, "board", side_effect=render)):
        yield


class LiveMatch(Match):
    def __init__(self, players=PLAYERS, seed=19, *, reply=None, times=None, live_turns=200):
        super().__init__(players, seed, model=OpenAILanguageModel("test", Mock()), live_players=players,
                         live_turns=live_turns)
        self.reply = reply or (lambda name, window: arrange())
        self.times = times or {name: index for index, name in enumerate(PLAYERS)}
        self.requests = []

    def decide_together(self, phase, decisions, **kwargs):
        self.window = rows(self, "sym_window")[-1]["window"]
        answers = super().decide_together(phase, decisions, **kwargs)
        kwargs["response_times"].update({name: self.times[name] for name in decisions})
        return answers

    def _query(self, name, prompt, *args, **kwargs):
        self.requests.append((name, self.window, prompt,
                              self.model_observations(name, self.observations(name)), kwargs["images"]))
        return self.reply(name, self.window), StrategyNote(text=f"PRIVATE-{name}")


class SymmetryTest(unittest.TestCase):
    def test_visible_edge_and_vertex_choices_build_actual_puzzles_without_measuring_pixels(self):
        commands = {
            "blue": [{"piece": "B2", "edge": 7, "vertex": 5, "to_piece": "B1", "to_edge": 2, "to_vertex": 4}],
            "red": [{"piece": "R2", "edge": 1, "vertex": 2, "to_piece": "R1", "to_edge": 2, "to_vertex": 2},
                    {"piece": "R3", "edge": 4, "vertex": 4, "to_piece": "R1", "to_edge": 0, "to_vertex": 1}],
            "green": [{"piece": "G2", "edge": 0, "vertex": 0, "to_piece": "G1", "to_edge": 2, "to_vertex": 3},
                      {"piece": "G3", "edge": 2, "vertex": 2, "to_piece": "G2", "to_edge": 2, "to_vertex": 3}],
        }
        for angle in (0, 17.3, 149.75):
            selected = {puzzle["id"]: [{**puzzle["solution"][0], "x": -2.125, "y": 3.75, "rotation": angle},
                                       *commands[puzzle["id"]]] for puzzle in PUZZLES}
            result = game.parse_action(arrange(selected), PUZZLES)
            for puzzle in PUZZLES:
                with self.subTest(color=puzzle["id"], angle=angle):
                    placements = result["placements"][puzzle["id"]]
                    self.assertTrue(judge(puzzle, placements))
                    self.assertTrue(all(set(row) == {"piece", "x", "y", "rotation"} for row in placements))
        before_target = {"blue": [commands["blue"][0]], "red": [], "green": []}
        with self.assertRaises(ValueError):
            game.parse_action(arrange(before_target), PUZZLES)

    def test_full_replacement_parser_requires_three_colors_and_rejects_unsafe_placement_forms(self):
        self.assertEqual(game.parse_action(game.WAIT, PUZZLES), {"type": "wait"})
        partial = {"blue": SOLUTION["blue"][:1], "red": [], "green": []}
        self.assertEqual(game.parse_action(arrange(partial, False), PUZZLES)["placements"], partial)
        invalid = [None, [], {"type": "wait", "extra": 1},
                   {"type": "arrange", "placements": partial, "submit": 1},
                   {"type": "arrange", "placements": {"blue": [], "red": []}, "submit": True},
                   {"type": "arrange", "placements": {**partial, "yellow": []}, "submit": True},
                   {"type": "arrange", "placements": partial, "submit": True, "flip": True}]
        placement = {"piece": "B1", "x": 0, "y": 0, "rotation": 0}
        for changes in ({"piece": "R1"}, {"x": True}, {"rotation": True}, {"rotation": float("nan")},
                        {"x": float("inf")}, {"y": -1_000_001}, {"flip": True}, {"piece": []}):
            invalid.append({"type": "arrange", "placements": {**partial, "blue": [{**placement, **changes}]}, "submit": True})
        invalid.append({"type": "arrange", "placements": {**partial, "blue": [placement, placement]}, "submit": True})
        invalid.append({"type": "arrange", "placements": {**partial, "green": None}, "submit": True})
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                game.parse_action(encode(value), PUZZLES)
        with self.assertRaises(ValueError):
            game.parse_action(" " * (game.MAX_ACTION_SIZE + 1), PUZZLES)
        overlap = [dict(placement, piece="B1"), dict(placement, piece="B2")]
        self.assertEqual(len(game.parse_action(arrange({**partial, "blue": overlap}), PUZZLES)["placements"]["blue"]), 2)
        continuous = {**placement, "x": -2.125, "y": 19.75, "rotation": 32.5}
        parsed = game.parse_action(arrange({**partial, "blue": [continuous]}), PUZZLES)
        self.assertEqual(parsed["placements"]["blue"], [continuous])

    def test_three_or_four_players_race_one_pack_until_first_n_minus_one_finish(self):
        for players in (PLAYERS[:3], PLAYERS):
            with self.subTest(players=players), puzzles():
                match = LiveMatch(players, times={"P01": 90, "P02": 60, "P03": 30, "P04": 120})
                result = game.play(match)
                expected = ["P03", "P02", "P01"] + (["P04"] if len(players) == 4 else [])
                self.assertEqual(result["ranking"], expected)
                self.assertEqual(result["survivors"], expected[:-1])
                self.assertEqual(result["eliminated"], expected[-1:])
                self.assertEqual(result["turns"], 1)
                self.assertEqual(result["scores"], dict.fromkeys(players, 3))
                self.assertEqual(result["attempts"][expected[-1]], 0)
                self.assertEqual(rows(match, "sym_setup")[0]["survivors"], len(players) - 1)
                self.assertEqual(rows(match, "sym_setup")[0]["mode"], "polygons")
                self.assertNotIn("grid_size", rows(match, "sym_setup")[0])
                self.assertEqual(len(rows(match, "sym_puzzles")), 1)
                self.assertEqual([row["player"] for row in rows(match, "sym_buzz")], expected[:-1])
                self.assertFalse(match.relationship_reviews_enabled)

    def test_equal_slow_responses_follow_disclosed_priority_without_a_timer(self):
        with puzzles():
            match = LiveMatch(times=dict.fromkeys(PLAYERS, 900_000_000_000))
            result = game.play(match)
        self.assertEqual(result["ranking"], rows(match, "sym_setup")[0]["priority"])
        self.assertTrue(all(row["correct"] for row in rows(match, "sym_verdict")))

    def test_partial_overlap_wait_and_format_failure_keep_own_work_then_allow_retries(self):
        incomplete = deepcopy(SOLUTION)
        incomplete["green"] = incomplete["green"][:-1]
        work = {"blue": SOLUTION["blue"], "red": [{"piece": "R1", "x": 0, "y": 0, "rotation": 0},
                                                     {"piece": "R2", "x": 0, "y": 0, "rotation": 0}], "green": []}

        def reply(name, window):
            if window == 1:
                return {"P01": arrange(submit=False), "P02": arrange(incomplete),
                        "P03": arrange(work, False), "P04": game.WAIT}[name]
            if window == 2:
                return arrange() if name == "P01" else "broken JSON" if name == "P02" else game.WAIT
            return arrange() if name in {"P02", "P04"} else arrange({**work, "green": [{"piece": "G1", "x": True, "y": 0, "rotation": 0}]})

        with puzzles():
            match = LiveMatch(reply=reply)
            result = game.play(match)
        self.assertEqual(result["ranking"], ["P01", "P02", "P04", "P03"])
        self.assertEqual(result["turns"], 3)
        self.assertEqual(result["scores"], {"P01": 3, "P02": 3, "P03": 1, "P04": 3})
        self.assertEqual(result["attempts"], {"P01": 1, "P02": 2, "P03": 0, "P04": 1})
        self.assertEqual([row["correct"] for row in rows(match, "sym_verdict")], [False, True, True, True])
        self.assertEqual(rows(match, "sym_window")[2]["active"], ["P02", "P03", "P04"])
        self.assertEqual(len(rows(match, "invalid_action")), 2)
        self.assertEqual(len(rows(match, "sym_board")), 6)
        self.assertEqual(rows(match, "sym_reveal")[0]["boards"]["P03"]["placements"], work)
        initial = {puzzle["id"]: puzzle["board"] for puzzle in rows(match, "sym_puzzles")[0]["puzzles"]}
        for name, window, prompt, history, images in match.requests:
            previous = [row for row in rows(match, "sym_board") if row["player"] == name and row["window"] < window]
            expected = previous[-1]["boards"] if previous else initial
            self.assertEqual(images, tuple(b64decode(expected[color]["image"].partition(",")[2]) for color in COLORS))
            self.assertEqual([event.msg_type for event in history], ["rules"])
            self.assertNotIn("NEVER-PUBLISH", prompt)
            self.assertNotIn("PRIVATE-", prompt)
            self.assertNotIn('"cells"', prompt)
            for other in PLAYERS:
                if other != name:
                    self.assertNotIn(f"PRIVATE-{other}", prompt)

    def test_replacing_with_empty_color_lists_erases_previous_work(self):
        empty = {color: [] for color in COLORS}

        def reply(name, window):
            return arrange(submit=False) if window == 1 else arrange(empty, False) if window == 2 else arrange()

        with puzzles():
            match = LiveMatch(reply=reply)
            game.play(match)
        self.assertTrue(all(row["placements"] == empty for row in rows(match, "sym_board") if row["window"] == 2))

    def test_malformed_live_replies_do_not_get_solved_defaults_and_wait_uses_normal_call_budget(self):
        for reply in ("invalid JSON", game.WAIT):
            with self.subTest(reply=reply), puzzles():
                match = LiveMatch(reply=lambda *args: reply, live_turns=8)
                result = game.play(match)
                self.assertEqual(result["turns"], 3)
                self.assertEqual(len(rows(match, "sym_puzzles")), 1)
                self.assertTrue(all(row["window"] == 3 for row in rows(match, "sym_board")))
                self.assertTrue(all(row["window"] == 3 for row in rows(match, "sym_verdict")))
                self.assertEqual(len(rows(match, "invalid_action")), 8 if reply != game.WAIT else 0)

    def test_no_work_completed_color_hints_or_fixtures_are_public_before_final_reveal(self):
        with puzzles():
            match = LiveMatch()
            game.play(match)
        reveal = next(index for index, event in enumerate(match.events) if event.msg_type == "sym_reveal")
        finishes = [index for index, event in enumerate(match.events) if event.msg_type == "sym_finish"]
        self.assertEqual(len(finishes), 3)
        self.assertGreater(reveal, max(finishes))
        for index, event in enumerate(match.events):
            if event.msg_type in {"action", "decision_note", "sym_board"}:
                self.assertEqual(event.visible_to, [event.agent_name])
            if event.msg_type in {"sym_buzz", "sym_verdict", "sym_finish"}:
                self.assertEqual(event.visible_to, "all")
                self.assertFalse({"placements", "boards", "axes", "colors", "scores"} & set(json.loads(event.content)))
            if index < reveal and event.visible_to == "all" and event.msg_type != "rules":
                self.assertNotIn("solution", event.content)
                self.assertNotIn('"cells"', event.content)
        for puzzle in rows(match, "sym_puzzles")[0]["puzzles"]:
            self.assertEqual(set(puzzle), {"id", "label", "piece_ids", "board"})
        self.assertEqual(set(rows(match, "sym_reveal")[0]["boards"]), set(PLAYERS))

    def test_initial_model_requests_never_contain_scripted_fixture_placements(self):
        with puzzles():
            match = LiveMatch()
            game.play(match)
        for name, window, prompt, history, images in match.requests:
            self.assertEqual(len(images), 3)
            self.assertNotIn(encode(SOLUTION), prompt)
            self.assertIn(encode({color: [] for color in COLORS}), prompt)
            self.assertIn("시계 방향", prompt)
            self.assertIn("왼쪽 위", prompt)

    def test_scripted_game_is_deterministic_preserves_pieces_and_requires_three_or_four_unique_players(self):
        with puzzles():
            first, second = Match(PLAYERS, 19, pieces=[0, 1, 2, 3]), Match(PLAYERS, 19, pieces=[0, 1, 2, 3])
            self.assertEqual(game.play(first), game.play(second))
        self.assertEqual(first.pieces, dict(zip(PLAYERS, [0, 1, 2, 3], strict=True)))
        self.assertEqual([(event.msg_type, event.content) for event in first.events],
                         [(event.msg_type, event.content) for event in second.events])
        for players in (PLAYERS[:2], (*PLAYERS, "P05"), ("P01",) * 3):
            with self.subTest(players=players), self.assertRaises(ValueError):
                game.play(Match(players, 1))

    def test_actual_interruptions_restore_three_images_and_saved_race_without_duplicate_queries(self):
        original_event = Match.event
        with (TemporaryDirectory() as directory, puzzles(), redirect_stdout(StringIO()), redirect_stderr(StringIO()),
              patch.object(Match, "_query", return_value=(arrange(), StrategyNote(text="private"))),
              patch("games.match.monotonic_ns", return_value=70_000_000_000)):
            root = Path(directory)
            full = root / "full.jsonl"
            arguments = ["--players", *PLAYERS, "--seed", "19", "--model", "test", "--model-turns", "4"]
            run_cli(game.play, title=FIFTH_EXILE, seats=(3, 4), argv=[*arguments, "--output", str(full)])
            expected = [json.loads(line) for line in full.read_text().splitlines()]
            saved = json.loads(full.with_name("full.decisions.jsonl").read_text().splitlines()[0])["value"]["value"]
            self.assertTrue(all(reply[2] == 0 for reply in saved.values()))
            for checkpoint in ("sym_board", "sym_buzz", "sym_verdict", "sym_finish", "sym_reveal"):
                with self.subTest(checkpoint=checkpoint):
                    output = root / f"{checkpoint}.jsonl"

                    def interrupt(match, kind, value, **kwargs):
                        original_event(match, kind, value, **kwargs)
                        if kind == checkpoint:
                            raise RuntimeError("interrupted after committed event")

                    with patch.object(Match, "event", interrupt), self.assertRaisesRegex(RuntimeError, "committed event"):
                        run_cli(game.play, title=FIFTH_EXILE, seats=(3, 4), argv=[*arguments, "--output", str(output)])
                    prefix = [json.loads(line) for line in output.read_text().splitlines()]
                    with (patch.object(Match, "_query", side_effect=AssertionError("committed response queried twice")),
                          patch("games.match.monotonic_ns", return_value=999_000_000_000)):
                        run_cli(game.play, title=FIFTH_EXILE, seats=(3, 4), argv=["--resume", "--output", str(output)])
                    actual = [json.loads(line) for line in output.read_text().splitlines()]
                    self.assertEqual(actual, expected)
                    self.assertEqual(actual[:len(prefix) - 1], prefix[:-1])


if __name__ == "__main__":
    unittest.main()
