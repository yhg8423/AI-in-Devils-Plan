"""Buzzer order, locks, question recovery, information boundaries, and resume."""

from base64 import b64encode
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from ...match import Match, THIRD_EXILE, encode, run_cli
from ...models import OpenAILanguageModel, StrategyNote
from . import game


PLAYERS = ("P01", "P02", "P03", "P04")
SOLUTION = "QRTX"
IMAGE = b"\x89PNG\r\n\x1a\nSAME-FLATTENED-PUBLIC-BOARD"
VIEW = {"id": "public-board", "width": 960, "height": 640,
        "image": "data:image/png;base64," + b64encode(IMAGE).decode("ascii")}


def buzz(code=SOLUTION):
    return encode({"type": "buzz", "code": code})


def rows(match, kind):
    return [json.loads(event.content) for event in match.events if event.msg_type == kind]


@contextmanager
def puzzles():
    with (patch.object(game, "make_puzzle", return_value={"solution": SOLUTION,
            "cards": [{"hidden": "INTERNAL-CARD-LIST"}],
            "clues": [{"id": "C1", "text": "공개 단서", "en": "Public clue"}]}),
          patch.object(game, "board", return_value=VIEW)):
        yield


class LiveMatch(Match):
    def __init__(self, seed=19, *, reply=None, times=None, live_turns=200):
        super().__init__(PLAYERS, seed, model=OpenAILanguageModel("test", Mock()), live_players=PLAYERS,
                         live_turns=live_turns)
        self.reply = reply or (lambda name, question, window: buzz())
        self.times = times or {name: index for index, name in enumerate(PLAYERS)}
        self.requests = []

    def decide_together(self, phase, decisions, **kwargs):
        self.question = rows(self, "code_question")[-1]
        self.window = rows(self, "code_window")[-1]["window"]
        answers = super().decide_together(phase, decisions, **kwargs)
        # Deterministic fixtures for ordering/deadline tests; journal behavior is tested separately.
        kwargs["response_times"].update({name: self.times[name] for name in decisions})
        return answers

    def _query(self, name, prompt, *args, **kwargs):
        self.requests.append((name, self.question["round"], self.question["question"], self.window,
                              prompt, self.model_observations(name, self.observations(name)), kwargs["images"]))
        return self.reply(name, self.question["question"], self.window), StrategyNote(text=f"PRIVATE-{name}")


class SecretCodeTest(unittest.TestCase):
    def test_parser_normalizes_case_but_never_sorts_or_repairs_codes(self):
        self.assertEqual(game.parse_action(buzz("qtrx"))["code"], "QTRX")
        self.assertEqual(game.parse_action('{"type":"wait"}'), {"type": "wait"})
        for code in ("AAAA", "DCBA", "AB1D", "ABC", "ABCDE", ""):
            self.assertFalse(game._valid_code(game.parse_action(buzz(code))["code"]))
        for value in (None, [], {"type": "wait", "code": "ABCD"}, {"type": "buzz"},
                      {"type": "buzz", "code": None}, {"type": "buzz", "code": "A" * 65},
                      {"type": "buzz", "code": "ABCD", "extra": True}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                game.parse_action(encode(value))

    def test_three_first_correct_players_are_safe_and_only_last_player_is_out(self):
        with puzzles():
            match = LiveMatch(times={"P01": 90, "P02": 60, "P03": 30, "P04": 120})
            result = game.play(match)
        self.assertEqual(result["ranking"], ["P03", "P02", "P01", "P04"])
        self.assertEqual(result["survivors"], result["ranking"][:3])
        self.assertEqual(result["eliminated"], ["P04"])
        self.assertEqual(result["ranking_groups"], [[name] for name in result["ranking"]])
        self.assertEqual(result["finish_rounds"], {"P03": 1, "P02": 2, "P01": 3})
        self.assertEqual(result["scores"], {"P01": 1, "P02": 1, "P03": 1, "P04": 0})
        self.assertEqual((result["rounds"], result["questions"]), (3, 3))
        self.assertEqual([row["player"] for row in rows(match, "code_buzz")], result["survivors"])
        self.assertEqual(len(match.requests), 9)
        self.assertFalse(match.relationship_reviews_enabled)
        for row in rows(match, "code_question"):
            self.assertEqual(len(row["players"]), 5 - row["round"])

    def test_equal_times_follow_disclosed_priority_and_long_thinking_is_not_answer_timeout(self):
        with puzzles():
            match = LiveMatch(times=dict.fromkeys(PLAYERS, 90_000_000_000))
            result = game.play(match)
        self.assertEqual(result["ranking"], rows(match, "code_setup")[0]["priority"])
        self.assertTrue(all(row["correct"] and row["answer_seconds"] == 0
                            and row["elapsed_ns"] == 90_000_000_000 for row in rows(match, "code_attempt")))

    def test_wrong_and_invalid_answers_lock_only_that_question_waiters_can_buzz_later(self):
        def reply(name, question, window):
            if question == 1:
                if name == "P01":
                    return buzz("XTRQ")
                if name == "P02":
                    return buzz("ABCD")
                if window == 1:
                    return '{"type":"wait"}'
            return buzz()

        with puzzles():
            match = LiveMatch(reply=reply)
            result = game.play(match)
        attempts = rows(match, "code_attempt")
        self.assertEqual([(row["player"], row["reason"]) for row in attempts[:3]],
                         [("P01", "invalid"), ("P02", "incorrect"), ("P03", None)])
        self.assertEqual(rows(match, "code_window")[1]["eligible"], ["P03", "P04"])
        self.assertEqual(rows(match, "code_question")[1]["players"], ["P01", "P02", "P04"])
        self.assertEqual(result["ranking"], ["P03", "P01", "P02", "P04"])

    def test_all_locked_and_three_all_wait_windows_replace_question_in_same_round(self):
        def reply(name, question, window):
            return buzz("ABCD") if question == 1 else '{"type":"wait"}' if question == 2 else buzz()

        with puzzles():
            match = LiveMatch(reply=reply)
            result = game.play(match)
        self.assertEqual([(row["round"], row["question"], row["reason"], row["code"])
                          for row in rows(match, "code_question_end")],
                         [(1, 1, "all_locked", SOLUTION), (1, 2, "no_buzz", SOLUTION)])
        self.assertEqual([(row["round"], row["question"]) for row in rows(match, "code_question")],
                         [(1, 1), (1, 2), (1, 3), (2, 4), (3, 5)])
        self.assertEqual([row["window"] for row in rows(match, "code_window") if row["question"] == 2], [1, 2, 3])
        self.assertEqual(result["questions"], 5)

    def test_invalid_model_output_never_gets_correct_default_and_budget_demo_finishes(self):
        with puzzles():
            match = LiveMatch(reply=lambda *args: "broken JSON", live_turns=4)
            result = game.play(match)
        self.assertEqual(len(rows(match, "invalid_action")), 4)
        first_attempts = [row for row in rows(match, "code_attempt") if row["question"] == 1]
        self.assertEqual(len(first_attempts), 4)
        self.assertTrue(all(row["code"] == "" and row["reason"] == "invalid" for row in first_attempts))
        self.assertEqual(result["questions"], 4)
        self.assertEqual(len(result["survivors"]), 3)

    def test_three_wait_windows_are_counted_even_if_a_wrong_buzz_occurs_between_them(self):
        def reply(name, question, window):
            if question != 1:
                return buzz()
            return buzz("ABCD") if name == "P01" and window == 2 else '{"type":"wait"}'

        with puzzles():
            match = LiveMatch(reply=reply)
            game.play(match)
        first_windows = [row for row in rows(match, "code_window") if row["question"] == 1]
        self.assertEqual([row["window"] for row in first_windows], [1, 2, 3, 4])
        self.assertEqual(rows(match, "code_question_end")[0]["reason"], "no_buzz")
        self.assertNotIn("P01", first_windows[-1]["eligible"])

    def test_models_get_exact_public_png_clues_and_state_without_solution_or_private_history(self):
        with puzzles():
            match = LiveMatch()
            game.play(match)
        for name, number, question, window, prompt, history, images in match.requests:
            with self.subTest(name=name, round=number):
                self.assertEqual(images, (IMAGE,))
                self.assertEqual([event.msg_type for event in history], ["rules"])
                self.assertIn("공개 단서", prompt)
                self.assertNotIn(SOLUTION, prompt)
                self.assertNotIn("INTERNAL-CARD-LIST", prompt)
                self.assertNotIn("PRIVATE-", prompt)
                self.assertNotIn("solution", prompt)
        for event in match.events:
            if event.msg_type in {"action", "decision_note"}:
                self.assertEqual(event.visible_to, [event.agent_name])
        for question in rows(match, "code_question"):
            self.assertEqual(set(question), {"round", "question", "players", "board", "clues", "answer_seconds"})
            self.assertNotIn(SOLUTION, encode(question))
        # Later proposals in a winning window are never turned into public attempts.
        self.assertEqual(len(rows(match, "code_attempt")), 3)

    def test_scripted_game_is_deterministic_preserves_pieces_and_rejects_wrong_rosters(self):
        with puzzles():
            first = Match(PLAYERS, 19, pieces=[0, 1, 2, 3])
            second = Match(PLAYERS, 19, pieces=[0, 1, 2, 3])
            self.assertEqual(game.play(first), game.play(second))
        self.assertEqual(first.pieces, dict(zip(PLAYERS, [0, 1, 2, 3], strict=True)))
        self.assertEqual([(event.msg_type, event.content) for event in first.events],
                         [(event.msg_type, event.content) for event in second.events])
        for players in (PLAYERS[:3], ("P01",) * 4):
            with self.subTest(players=players), self.assertRaises(ValueError):
                game.play(Match(players, 1))

    def test_saved_live_response_times_replay_exact_buzz_order_after_interrupted_events(self):
        original_event = Match.event
        with (TemporaryDirectory() as directory, puzzles(), redirect_stdout(StringIO()), redirect_stderr(StringIO()),
              patch.object(Match, "_query", return_value=(buzz(), StrategyNote(text="private"))),
              patch("games.match.monotonic_ns", return_value=70_000_000_000)):
            root = Path(directory)
            full = root / "full.jsonl"
            arguments = ["--players", *PLAYERS, "--seed", "19", "--model", "test", "--model-turns", "4"]
            run_cli(game.play, title=THIRD_EXILE, seats=4, argv=[*arguments, "--output", str(full)])
            expected = [json.loads(line) for line in full.read_text().splitlines()]
            journal = full.with_name("full.decisions.jsonl").read_text().splitlines()
            first_batch = json.loads(journal[0])["value"]["value"]
            self.assertTrue(all(value[2] == 0 for value in first_batch.values()))
            for checkpoint in ("action", "code_buzz", "code_attempt", "code_round_result"):
                with self.subTest(checkpoint=checkpoint):
                    output = root / f"{checkpoint}.jsonl"
                    def interrupt(match, kind, value, **kwargs):
                        original_event(match, kind, value, **kwargs)
                        if kind == checkpoint:
                            raise RuntimeError("interrupted after committed event")

                    with patch.object(Match, "event", interrupt), self.assertRaisesRegex(RuntimeError, "committed event"):
                        run_cli(game.play, title=THIRD_EXILE, seats=4, argv=[*arguments, "--output", str(output)])
                    prefix = [json.loads(line) for line in output.read_text().splitlines()]
                    with (patch.object(Match, "_query", side_effect=AssertionError("committed response queried twice")),
                          patch("games.match.monotonic_ns", return_value=999_000_000_000)):
                        run_cli(game.play, title=THIRD_EXILE, seats=4, argv=["--resume", "--output", str(output)])
                    actual = [json.loads(line) for line in output.read_text().splitlines()]
                    self.assertEqual(actual, expected)
                    self.assertEqual(actual[:len(prefix) - 1], prefix[:-1])


if __name__ == "__main__":
    unittest.main()
