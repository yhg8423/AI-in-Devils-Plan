"""Image-only rectangle judging, buzzer deadlines, locks, and replay."""

from base64 import b64encode
from contextlib import contextmanager
from dataclasses import asdict
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from ...match import Match, SEVENTH_EXILE, encode
from ...models import OpenAILanguageModel, StrategyNote
from ...resume import MatchLog
from . import game
from .puzzles import board, make_puzzle


PLAYERS = ("P01", "P02", "P03", "P04")
ANSWER = 37
IMAGE = b"RECTANGLE-PUBLIC-IMAGE"
VIEW = {"id": "public-board", "width": 960, "height": 640,
        "image": "data:image/png;base64," + b64encode(IMAGE).decode()}
NANO = 1_000_000_000


def buzz(count=ANSWER):
    return encode({"type": "buzz", "count": count})


def data(match, kind):
    return [json.loads(event.content) for event in match.events if event.msg_type == kind]


@contextmanager
def puzzles():
    with (patch.object(game, "make_puzzle", return_value={"values": [["INTERNAL-NUMBERS"]], "target": 203, "answer": ANSWER}),
          patch.object(game, "board", return_value=VIEW)):
        yield


class LiveMatch(Match):
    def __init__(self, *, reply=None, times=None, **kwargs):
        super().__init__(PLAYERS, 31, model=OpenAILanguageModel("test", Mock()), live_players=PLAYERS,
                         live_turns=300, count_calls=lambda: 0, **kwargs)
        self.reply = reply or (lambda name, question, window: buzz())
        self.times = times or (lambda name, question, window: (len(PLAYERS) - PLAYERS.index(name)) * NANO)
        self.requests = []

    def decide_together(self, phase, decisions, **kwargs):
        self.question = data(self, "rect_question")[-1]["question"]
        self.window = data(self, "rect_window")[-1]["window"]
        replies = super().decide_together(phase, decisions, **kwargs)
        kwargs["response_times"].update({name: self.times(name, self.question, self.window) for name in decisions})
        return replies

    def _query(self, name, prompt, *args, **kwargs):
        self.requests.append((name, self.question, self.window, prompt,
                              self.model_observations(name, self.observations(name)), kwargs["images"]))
        return self.reply(name, self.question, self.window), StrategyNote(text=f"PRIVATE-{name}")


class RectangleRaceTest(unittest.TestCase):
    def test_authored_signed_and_impossible_boards_include_zero_answer(self):
        first, second = make_puzzle(1, 1), make_puzzle(2, 2)
        self.assertEqual(first["answer"], 24)
        self.assertEqual(second["answer"], 0)
        self.assertEqual([len(row) for row in second["values"]], [5] * 5)
        self.assertGreater(sum(map(sum, second["values"])), second["target"])
        self.assertEqual(41 + 51 + 3 * 37, second["target"])
        legacy = make_puzzle(2, 2, pack="authored_v1")
        self.assertEqual(sorted(legacy["values"][0]), [37, 41, 51])
        self.assertEqual(legacy["answer"], 0)
        self.assertTrue(any(value < 0 for row in first["values"] for value in row))
        for number in range(1, 8):
            self.assertEqual(make_puzzle(77, number), make_puzzle(77, number))
        picture = board(first)
        self.assertEqual((picture["width"], picture["height"]), (960, 640))
        self.assertEqual(set(picture), {"id", "width", "height", "image", "alt"})
        self.assertEqual(game.parse_action(buzz(0))["count"], 0)
        for action in ({"type": "buzz", "count": True}, {"type": "buzz", "count": "0"},
                       {"type": "wait", "count": 0}, {"type": "buzz"}):
            with self.assertRaises(ValueError):
                game.parse_action(encode(action))

    def test_first_correct_player_is_safe_and_only_public_image_reaches_models(self):
        with puzzles():
            match = LiveMatch()
            result = game.play(match)
        self.assertEqual(result["ranking"], ["P04", "P03", "P01", "P02"])
        self.assertEqual(result["survivors"], ["P04", "P03"])
        self.assertEqual(result["eliminated"], ["P01", "P02"])
        self.assertEqual(result["ranking_groups"][-1], ["P01", "P02"])
        self.assertEqual(len(match.requests), 7)
        self.assertEqual([row["player"] for row in data(match, "rect_attempt")], ["P04", "P03"])
        self.assertFalse(match.relationship_reviews_enabled)
        for name, question, window, prompt, history, images in match.requests:
            self.assertNotIn("INTERNAL-NUMBERS", prompt)
            self.assertNotIn(str(ANSWER), prompt)
            self.assertEqual(images, (IMAGE,))
            self.assertTrue(all(event.msg_type == "rules" for event in history))
        self.assertNotIn("P04", data(match, "rect_question")[1]["players"])

    def test_invalid_and_wrong_answers_lock_only_one_problem_and_waiter_can_answer_later(self):
        def reply(name, question, window):
            if question == 1:
                if name == "P01": return "not JSON"
                if name == "P02": return buzz(1)
                if window == 1: return encode({"type": "wait"})
            return buzz()
        with puzzles():
            match = LiveMatch(reply=reply, times=lambda name, question, window: PLAYERS.index(name) + 1)
            result = game.play(match)
        attempts = data(match, "rect_attempt")
        self.assertEqual([(row["player"], row["reason"]) for row in attempts[:3]],
                         [("P01", "invalid"), ("P02", "incorrect"), ("P03", None)])
        self.assertEqual(data(match, "rect_window")[1]["eligible"], ["P03", "P04"])
        self.assertEqual(result["survivors"], ["P03", "P01"])

    def test_three_wait_windows_replace_problem_without_selecting_a_winner(self):
        with puzzles():
            match = LiveMatch(reply=lambda name, question, window: encode({"type": "wait"}) if question == 1 else buzz())
            result = game.play(match)
        self.assertEqual(result["questions"], 3)
        ended = data(match, "rect_question_end")
        self.assertEqual((ended[0]["question"], ended[0]["reason"]), (1, "no_buzz"))
        self.assertFalse(any(row["question"] == 1 for row in data(match, "rect_attempt")))

    def test_question_deadline_accumulates_across_windows_and_accepts_exact_boundary(self):
        def reply(name, question, window):
            return encode({"type": "wait"}) if question == 1 and window == 1 else buzz()
        def times(name, question, window):
            if question == 1: return (150 if window == 1 else 151) * NANO
            if question == 2: return (300 if name == "P01" else 301) * NANO
            return PLAYERS.index(name) + 1
        with puzzles():
            match = LiveMatch(reply=reply, times=times)
            result = game.play(match)
        self.assertEqual(data(match, "rect_question_end")[0]["reason"], "timeout")
        attempts = data(match, "rect_attempt")
        self.assertFalse(any(row["question"] == 1 for row in attempts))
        self.assertEqual((attempts[0]["player"], attempts[0]["elapsed_ns"]), ("P01", 300 * NANO))
        self.assertEqual(result["survivors"], ["P01", "P02"])

    def test_equal_response_times_use_public_priority_and_zero_budget_demo_finishes(self):
        with puzzles():
            match = LiveMatch(times=lambda *args: NANO)
            result = game.play(match)
            self.assertEqual(result["survivors"], data(match, "rect_setup")[0]["priority"][:2])
            demo = Match(PLAYERS, 4)
            result = game.play(demo)
        self.assertEqual(len(result["survivors"]), 2)
        self.assertEqual(len(result["eliminated"]), 2)
        self.assertEqual(result["questions"], 2)
        with self.assertRaisesRegex(ValueError, "4명"):
            game.play(Match(PLAYERS[:3], 4))

    def test_saved_problem_replays_without_fresh_queries_or_changing_the_prefix(self):
        class Stop(RuntimeError):
            pass
        with puzzles(), TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            header = {"type": "match", "game": SEVENTH_EXILE}

            def record(log):
                def write(event):
                    log.write({"type": "event", **asdict(event), "model_calls": 0})
                    if event.msg_type == "rect_round_result": raise Stop()
                return write

            with MatchLog(path) as log:
                log.write(header)
                with self.assertRaises(Stop):
                    game.play(LiveMatch(resume_log=log, on_event=record(log)))
                log.write({"type": "interrupted", "model_calls": 0})
            before = path.read_bytes()
            with MatchLog(path, resume=True) as log:
                log.write(header)
                resumed = LiveMatch(resume_log=log, on_event=record(log))
                with self.assertRaises(Stop): game.play(resumed)
                log.write({"type": "interrupted", "model_calls": 0})
            self.assertEqual(resumed.requests, [])
            self.assertEqual(path.read_bytes(), before)

    def test_old_saved_four_player_match_retains_three_survivors(self):
        match = Match(PLAYERS, 4)
        match.resume_log = SimpleNamespace(resume=True, events=[
            {"msg_type": "rect_setup", "content": encode({"version": 1, "players": list(PLAYERS), "survivor_count": 3})},
            {"msg_type": "rules", "content": game.LEGACY_RULES},
        ])
        with puzzles():
            result = game.play(match)
            self.assertTrue(all(call.kwargs["pack"] == "authored_v1"
                                for call in game.make_puzzle.call_args_list))
        self.assertEqual(len(result["survivors"]), 3)
        self.assertEqual(len(result["eliminated"]), 1)
        self.assertEqual(result["rounds"], 3)
        self.assertEqual(data(match, "rect_setup")[0]["version"], 1)
        self.assertEqual(data(match, "rect_setup")[0]["survivor_count"], 3)
        self.assertNotIn("puzzle_pack", data(match, "rect_setup")[0])
        self.assertEqual(next(event.content for event in match.events if event.msg_type == "rules"), game.LEGACY_RULES)


if __name__ == "__main__":
    unittest.main()
