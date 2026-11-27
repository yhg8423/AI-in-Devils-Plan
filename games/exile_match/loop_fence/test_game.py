"""Editable private boards, submission races, retries, image isolation, and resume."""

from base64 import b64decode, b64encode
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from ...match import FOURTH_EXILE, Match, encode, run_cli
from ...models import OpenAILanguageModel, StrategyNote
from . import game
from .puzzles import all_edges, make_puzzle


PLAYERS = ("P01", "P02", "P03", "P04")
PUZZLE = make_puzzle(19)
SOLUTION = [list(edge) for edge in PUZZLE["solution"]]
CROSS = list(next(edge for edge in all_edges(7, 7) if list(edge) not in SOLUTION))


def draw(edges=SOLUTION, crosses=(), submit=True):
    return encode({"type": "draw", "edges": edges, "crosses": list(crosses), "submit": submit})


def rows(match, kind):
    return [json.loads(event.content) for event in match.events if event.msg_type == kind]


def render(puzzle, edges=(), crosses=()):
    image = b"\x89PNG\r\n\x1a\nEXACT-OWN-PNG" + encode({"edges": edges, "crosses": crosses}).encode()
    return {"id": sha256(image).hexdigest()[:16], "width": 960, "height": 640,
            "image": "data:image/png;base64," + b64encode(image).decode("ascii")}


@contextmanager
def puzzles():
    with (patch.object(game, "make_puzzle", return_value={**PUZZLE, "internal": "NEVER-PUBLISH"}),
          patch.object(game, "board", side_effect=render)):
        yield


class LiveMatch(Match):
    def __init__(self, seed=19, *, reply=None, times=None, live_turns=200):
        super().__init__(PLAYERS, seed, model=OpenAILanguageModel("test", Mock()), live_players=PLAYERS,
                         live_turns=live_turns)
        self.reply = reply or (lambda name, window: draw())
        self.times = times or {name: index for index, name in enumerate(PLAYERS)}
        self.requests = []

    def decide_together(self, phase, decisions, **kwargs):
        self.window = rows(self, "fence_window")[-1]["window"]
        answers = super().decide_together(phase, decisions, **kwargs)
        kwargs["response_times"].update({name: self.times[name] for name in decisions})
        return answers

    def _query(self, name, prompt, *args, **kwargs):
        self.requests.append((name, self.window, prompt,
                              self.model_observations(name, self.observations(name)), kwargs["images"]))
        return self.reply(name, self.window), StrategyNote(text=f"PRIVATE-{name}")


class LoopFenceTest(unittest.TestCase):
    def test_parser_enforces_unit_edges_types_bounds_duplicates_and_cross_conflicts(self):
        action = game.parse_action(encode({"type": "draw", "edges": [["V", 6, 7], ["H", 7, 6]], "submit": False}))
        self.assertEqual(action, {"type": "draw", "edges": [["H", 7, 6], ["V", 6, 7]],
                                  "crosses": [], "submit": False})
        self.assertEqual(game.parse_action(game.WAIT), {"type": "wait"})
        invalid = [None, [], {"type": "wait", "extra": 1}, {"type": "draw", "edges": []},
                   {"type": "draw", "edges": [], "submit": 1},
                   {"type": "draw", "edges": [], "submit": True, "extra": 1}]
        for edge in (["H", True, 0], ["V", 0, False], ["H", 0.0, 0], ["H", 7, 7],
                     ["V", 7, 7], ["H", -1, 0], ["V", 0, 8], ["D", 0, 0],
                     ["h", 0, 0], ["H", 0, 0, 1], ["H", 0], None):
            invalid.append({"type": "draw", "edges": [edge], "submit": True})
        invalid.extend([{"type": "draw", "edges": [["H", 0, 0]] * 2, "submit": True},
                        {"type": "draw", "edges": [["H", 0, 0]], "crosses": [["H", 0, 0]], "submit": True},
                        {"type": "draw", "edges": [], "crosses": None, "submit": True}])
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                game.parse_action(encode(value))

    def test_same_single_puzzle_race_uses_saved_response_time_then_stops_after_two(self):
        with puzzles():
            match = LiveMatch(times={"P01": 90, "P02": 60, "P03": 30, "P04": 120})
            result = game.play(match)
        self.assertEqual(result["ranking"], ["P03", "P02", "P01", "P04"])
        self.assertEqual(result["survivors"], result["ranking"][:2])
        self.assertEqual(result["eliminated"], ["P01", "P04"])
        self.assertEqual(result["ranking_groups"], [["P03"], ["P02"], ["P01", "P04"]])
        self.assertEqual(result["scores"], {"P01": 0, "P02": 1, "P03": 1, "P04": 0})
        self.assertEqual(result["attempts"], {"P01": 0, "P02": 1, "P03": 1, "P04": 0})
        self.assertEqual(rows(match, "fence_setup")[0]["survivors"], 2)
        self.assertEqual(result["finish_turns"], dict.fromkeys(result["survivors"], 1))
        self.assertEqual(result["turns"], 1)
        self.assertEqual(len(rows(match, "fence_puzzle")), 1)
        self.assertEqual([row["player"] for row in rows(match, "fence_buzz")], result["survivors"])
        self.assertFalse(match.relationship_reviews_enabled)

    def test_equal_and_slow_response_times_have_public_priority_without_any_answer_timeout(self):
        with puzzles():
            match = LiveMatch(times=dict.fromkeys(PLAYERS, 900_000_000_000))
            result = game.play(match)
        self.assertEqual(result["survivors"], rows(match, "fence_setup")[0]["priority"][:2])
        self.assertTrue(all(row["correct"] for row in rows(match, "fence_verdict")))
        self.assertTrue(all(row["elapsed_ns"] == 900_000_000_000 for row in result["finishes"]))

    def test_partial_edits_wait_and_malformed_actions_keep_private_boards_then_allow_retry(self):
        def reply(name, window):
            if window == 1:
                return {"P01": draw(submit=False), "P02": draw(SOLUTION[:-1]),
                        "P03": draw(SOLUTION[:1], [CROSS], submit=False), "P04": game.WAIT}[name]
            if window == 2:
                return draw() if name == "P01" else "broken JSON" if name == "P02" else game.WAIT
            return draw() if name in {"P02", "P04"} else draw([["H", True, 0]])

        with puzzles():
            match = LiveMatch(reply=reply)
            result = game.play(match)
        self.assertEqual(result["ranking"], ["P01", "P02", "P03", "P04"])
        self.assertEqual(result["turns"], 3)
        self.assertEqual(result["attempts"], {"P01": 1, "P02": 2, "P03": 0, "P04": 0})
        self.assertEqual([row["correct"] for row in rows(match, "fence_verdict")], [False, True, True])
        self.assertEqual(rows(match, "fence_window")[2]["active"], ["P02", "P03", "P04"])
        self.assertEqual(len(rows(match, "invalid_action")), 2)
        self.assertEqual(len(rows(match, "fence_board")), 6)
        final = rows(match, "fence_reveal")[0]["boards"]
        self.assertEqual(final["P03"]["edges"], SOLUTION[:1])
        self.assertEqual(final["P03"]["crosses"], [CROSS])
        # Each request gets exactly its own most recent public/private flattened PNG.
        public = rows(match, "fence_puzzle")[0]["puzzle"]["board"]
        for name, window, prompt, history, images in match.requests:
            previous = [row for row in rows(match, "fence_board") if row["player"] == name and row["window"] < window]
            expected = previous[-1]["board"] if previous else public
            self.assertEqual(images, (b64decode(expected["image"].partition(",")[2]),))
            self.assertEqual([event.msg_type for event in history], ["rules"])
            self.assertNotIn("NEVER-PUBLISH", prompt)
            self.assertNotIn("PRIVATE-", prompt)
            self.assertNotIn(encode(SOLUTION), prompt)
            self.assertNotIn("solution", prompt)

    def test_full_replacement_erases_omitted_marks(self):
        def reply(name, window):
            if window == 1:
                return draw(SOLUTION[:2], [CROSS], submit=False)
            return draw()

        with puzzles():
            match = LiveMatch(reply=reply)
            game.play(match)
        for state in rows(match, "fence_reveal")[0]["boards"].values():
            self.assertEqual(state["crosses"], [])
            self.assertEqual(state["edges"], SOLUTION)

    def test_invalid_live_output_retains_prior_board_and_never_becomes_solved_default(self):
        with puzzles():
            match = LiveMatch(reply=lambda *args: "invalid JSON", live_turns=4)
            result = game.play(match)
        self.assertEqual(result["turns"], 2)
        self.assertEqual(len(rows(match, "invalid_action")), 4)
        self.assertTrue(all(row["window"] == 2 for row in rows(match, "fence_board")))
        self.assertTrue(all(row["window"] == 2 for row in rows(match, "fence_buzz")))

    def test_wait_has_no_arbitrary_question_reset_or_winner_lottery(self):
        with puzzles():
            match = LiveMatch(reply=lambda *args: game.WAIT, live_turns=8)
            result = game.play(match)
        self.assertEqual(result["turns"], 3)
        self.assertEqual(len(rows(match, "fence_puzzle")), 1)
        self.assertTrue(all(row["window"] == 3 for row in rows(match, "fence_verdict")))

    def test_work_and_finished_answers_stay_private_until_both_survivors_are_safe(self):
        with puzzles():
            match = LiveMatch()
            game.play(match)
        reveal = next(index for index, event in enumerate(match.events) if event.msg_type == "fence_reveal")
        finish_indices = [index for index, event in enumerate(match.events) if event.msg_type == "fence_finish"]
        self.assertEqual(len(finish_indices), 2)
        self.assertGreater(reveal, max(finish_indices))
        for index, event in enumerate(match.events):
            if event.msg_type in {"action", "decision_note", "fence_board"}:
                self.assertEqual(event.visible_to, [event.agent_name])
            if event.msg_type in {"fence_buzz", "fence_verdict", "fence_finish"}:
                self.assertEqual(event.visible_to, "all")
                self.assertFalse({"edges", "crosses", "board", "solution"} & set(json.loads(event.content)))
            if index < reveal and event.visible_to == "all" and event.msg_type != "rules":
                self.assertNotIn("solution", event.content)
        self.assertEqual(set(rows(match, "fence_puzzle")[0]["puzzle"]), {"id", "size", "board"})
        self.assertEqual(set(rows(match, "fence_reveal")[0]["boards"]), set(PLAYERS))

    def test_scripted_result_is_deterministic_preserves_pieces_and_requires_four_distinct_players(self):
        with puzzles():
            first, second = Match(PLAYERS, 19, pieces=[0, 1, 2, 3]), Match(PLAYERS, 19, pieces=[0, 1, 2, 3])
            self.assertEqual(game.play(first), game.play(second))
        self.assertEqual(first.pieces, dict(zip(PLAYERS, [0, 1, 2, 3], strict=True)))
        self.assertEqual([(event.msg_type, event.content) for event in first.events],
                         [(event.msg_type, event.content) for event in second.events])
        for players in (PLAYERS[:3], ("P01",) * 4):
            with self.subTest(players=players), self.assertRaises(ValueError):
                game.play(Match(players, 1))

    def test_actual_interruptions_replay_private_boards_and_persisted_race_without_repeat_queries(self):
        original_event = Match.event
        with (TemporaryDirectory() as directory, puzzles(), redirect_stdout(StringIO()), redirect_stderr(StringIO()),
              patch.object(Match, "_query", return_value=(draw(), StrategyNote(text="private"))),
              patch("games.match.monotonic_ns", return_value=70_000_000_000)):
            root = Path(directory)
            full = root / "full.jsonl"
            arguments = ["--players", *PLAYERS, "--seed", "19", "--model", "test", "--model-turns", "4"]
            run_cli(game.play, title=FOURTH_EXILE, seats=4, argv=[*arguments, "--output", str(full)])
            expected = [json.loads(line) for line in full.read_text().splitlines()]
            saved = json.loads(full.with_name("full.decisions.jsonl").read_text().splitlines()[0])["value"]["value"]
            self.assertTrue(all(reply[2] == 0 for reply in saved.values()))
            for checkpoint in ("fence_board", "fence_buzz", "fence_verdict", "fence_finish", "fence_reveal"):
                with self.subTest(checkpoint=checkpoint):
                    output = root / f"{checkpoint}.jsonl"

                    def interrupt(match, kind, value, **kwargs):
                        original_event(match, kind, value, **kwargs)
                        if kind == checkpoint:
                            raise RuntimeError("interrupted after committed event")

                    with patch.object(Match, "event", interrupt), self.assertRaisesRegex(RuntimeError, "committed event"):
                        run_cli(game.play, title=FOURTH_EXILE, seats=4, argv=[*arguments, "--output", str(output)])
                    prefix = [json.loads(line) for line in output.read_text().splitlines()]
                    with (patch.object(Match, "_query", side_effect=AssertionError("committed response queried twice")),
                          patch("games.match.monotonic_ns", return_value=999_000_000_000)):
                        run_cli(game.play, title=FOURTH_EXILE, seats=4, argv=["--resume", "--output", str(output)])
                    actual = [json.loads(line) for line in output.read_text().splitlines()]
                    self.assertEqual(actual, expected)
                    self.assertEqual(actual[:len(prefix) - 1], prefix[:-1])

    def test_historical_three_survivor_setup_replays_without_changing_the_prefix(self):
        def interrupt(match):
            record = match.on_event

            def stop(event):
                record(event)
                if event.msg_type == "fence_finish" and json.loads(event.content)["rank"] == 2:
                    raise RuntimeError("two historical finishers saved")

            match.on_event = stop
            return game.play(match)

        with TemporaryDirectory() as directory, puzzles(), redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            full, partial = Path(directory) / "full.jsonl", Path(directory) / "partial.jsonl"
            arguments = ["--players", *PLAYERS, "--model-turns", "0", "--seed", "19"]
            with patch.object(game, "_survivor_count", return_value=3):
                run_cli(game.play, title=FOURTH_EXILE, seats=4, argv=[*arguments, "--output", str(full)])
                with self.assertRaisesRegex(RuntimeError, "historical finishers"):
                    run_cli(interrupt, title=FOURTH_EXILE, seats=4, argv=[*arguments, "--output", str(partial)])
            before = partial.read_text().splitlines()
            setup = next(json.loads(row["content"]) for row in map(json.loads, before)
                         if row.get("msg_type") == "fence_setup")
            self.assertEqual(setup["survivors"], 3)
            run_cli(game.play, title=FOURTH_EXILE, seats=4, argv=["--resume", "--output", str(partial)])
            self.assertEqual(partial.read_bytes(), full.read_bytes())
            self.assertEqual(partial.read_text().splitlines()[:len(before) - 1], before[:-1])
            self.assertEqual(len(json.loads(partial.read_text().splitlines()[-1])["survivors"]), 3)


if __name__ == "__main__":
    unittest.main()
