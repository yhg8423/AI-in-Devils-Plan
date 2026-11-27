"""Flag timing, memory isolation, boundary ties, and deterministic replay."""

from base64 import b64encode
from contextlib import contextmanager
from dataclasses import asdict
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from ...match import Match, SIXTH_EXILE, encode
from ...models import OpenAILanguageModel, StrategyNote
from ...resume import MatchLog
from . import game
from .puzzles import COUNTRIES, board, make_puzzle


PLAYERS = ("P01", "P02", "P03", "P04")


def data(match, kind):
    return [json.loads(event.content) for event in match.events if event.msg_type == kind]


def marks(count):
    return list(range(1, count + 1)) + list(range(6, 11 - count))


@contextmanager
def puzzles():
    def view(codes, *, study=False):
        raw = b"STUDY-IMAGE" if study else b"CHOICES-IMAGE"
        return {"id": "study" if study else "choices", "width": 1000, "height": 760,
                "image": "data:image/png;base64," + b64encode(raw).decode()}
    with (patch.object(game, "make_puzzle", return_value={"study": ["INTERNAL-COUNTRY"] * 10,
                   "choices": ["INTERNAL-COUNTRY"] * 25, "correct": [1, 2, 3, 4, 5]}),
          patch.object(game, "board", side_effect=view),
          patch.object(game, "frame", return_value=view([], study=True))):
        yield


class LiveMatch(Match):
    def __init__(self, players=PLAYERS, *, scores=None, durations=None, reply=None, **kwargs):
        super().__init__(players, 17, model=OpenAILanguageModel("test", Mock()),
                         live_players=players, live_turns=300, count_calls=lambda: 0, **kwargs)
        self.requests = []
        self.scores = scores or (lambda name, number: players.index(name) + 1)
        self.durations = durations or {}
        self.reply = reply

    def decide_together(self, phase, decisions, **kwargs):
        self.phase = phase
        self.stage = data(self, "flag_phase")[-1]
        result = super().decide_together(phase, decisions, **kwargs)
        kwargs["response_times"].update({name: self.durations.get((phase, name), 0) for name in decisions})
        return result

    def _query(self, name, prompt, *args, **kwargs):
        self.requests.append((name, self.phase, prompt, self.model_observations(name, self.observations(name)), kwargs["images"]))
        value = ({"memory": f"KEEP-{name}-{self.stage['round']}"} if self.phase == "flag_memorize" else
                 {"marks": marks(self.scores(name, self.stage["round"]))})
        if self.reply is not None:
            value = self.reply(name, self.phase, value)
        return encode(value), StrategyNote(text="UNBOUNDED-RECALL " * 30)


class FlagGameTest(unittest.TestCase):
    def test_generated_choices_have_exactly_five_seen_flags_and_no_country_metadata(self):
        self.assertGreaterEqual(len(COUNTRIES), 30)
        for seed in range(10):
            puzzle = make_puzzle(seed)
            self.assertEqual(puzzle, make_puzzle(seed))
            self.assertEqual(len(set(puzzle["study"])), 10)
            self.assertEqual(len(set(puzzle["choices"])), 25)
            self.assertEqual(len(set(puzzle["study"]) & set(puzzle["choices"])), 5)
            self.assertEqual(puzzle["correct"], [i for i, code in enumerate(puzzle["choices"], 1) if code in puzzle["study"]])
        picture = board(make_puzzle(1)["choices"])
        self.assertEqual((picture["width"], picture["height"]), (1000, 760))
        self.assertEqual(set(picture), {"id", "width", "height", "image", "alt", "grid"})
        self.assertEqual(picture["grid"]["rows"], 5)

    def test_marks_require_five_unique_integer_positions(self):
        self.assertEqual(game.parse_marks(encode({"marks": [1, 5, 9, 17, 25]})), [1, 5, 9, 17, 25])
        for value in ([], [1], [1, 2, 3, 4, 4], [True, 2, 3, 4, 5], [0, 2, 3, 4, 5], [1, 2, 3, 4, 26]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                game.parse_marks(encode({"marks": value}))

    def test_three_round_scores_and_only_bounded_own_memory_reaches_answer(self):
        with puzzles():
            match = LiveMatch()
            result = game.play(match)
        self.assertEqual(result["scores"], {"P01": 3, "P02": 6, "P03": 9, "P04": 12})
        self.assertEqual(result["survivors"], ["P04", "P03", "P02"])
        self.assertEqual(result["eliminated"], ["P01"])
        self.assertEqual(data(match, "flag_setup")[0]["survivor_count"], 3)
        self.assertEqual(len(data(match, "flag_frame")), 90)
        self.assertEqual([row["index"] for row in data(match, "flag_frame")[:30]], list(range(1, 31)))
        self.assertFalse(match.relationship_reviews_enabled)
        for name, phase, prompt, history, images in match.requests:
            self.assertTrue(all(event.msg_type == "rules" for event in history))
            self.assertNotIn("INTERNAL-COUNTRY", prompt)
            self.assertNotIn("UNBOUNDED-RECALL", prompt)
            if phase == "flag_answer":
                self.assertEqual(images, (b"CHOICES-IMAGE",))
                self.assertIn(f"KEEP-{name}-", prompt)
                for other in set(match.players) - {name}:
                    self.assertNotIn(f"KEEP-{other}-", prompt)
            else:
                self.assertEqual(images, (b"STUDY-IMAGE",))
        self.assertTrue(all(event.visible_to == [json.loads(event.content)["player"]]
                            for event in match.events if event.msg_type in {"flag_memory", "flag_marks"}))

    def test_deadlines_clear_memory_or_score_and_invalid_marks_do_not_receive_scripted_points(self):
        with puzzles():
            match = LiveMatch(durations={("flag_memorize", "P01"): 30_000_000_001,
                                         ("flag_answer", "P02"): 60_000_000_001},
                              reply=lambda name, phase, value: {"marks": [1, 1, 1, 1, 1]}
                              if name == "P01" and phase == "flag_answer" else value)
            result = game.play(match)
        self.assertEqual(result["scores"], {"P01": 0, "P02": 0, "P03": 9, "P04": 12})
        self.assertTrue(all(row["memory"] == "" for row in data(match, "flag_memory") if row["player"] == "P01"))
        self.assertTrue(all(row["marks"] == [] for row in data(match, "flag_marks")
                            if row["player"] in {"P01", "P02"} and row["round"] <= 3))
        self.assertEqual({row["phase"] for row in data(match, "flag_timeout")}, {"flag_memorize", "flag_answer"})

    def test_only_boundary_ties_play_overtime_and_normal_totals_remain(self):
        normal = {"P01": 5, "P02": 4, "P03": 2, "P04": 2}
        with puzzles():
            match = LiveMatch(PLAYERS, scores=lambda name, number: normal[name] if number <= 3 else {"P03": 1, "P04": 2}[name])
            result = game.play(match)
        self.assertEqual(result["survivors"], ["P01", "P02", "P04"])
        self.assertEqual(result["eliminated"], ["P03"])
        self.assertEqual(result["scores"], {"P01": 15, "P02": 12, "P03": 6, "P04": 6})
        self.assertEqual(data(match, "flag_tiebreak")[0]["players"], ["P03", "P04"])
        self.assertEqual(result["tiebreaks"][0]["slots"], 1)

    def test_four_player_demo_survives_three_and_other_new_rosters_are_rejected(self):
        with puzzles():
            match = Match(PLAYERS, 8)
            result = game.play(match)
            for size in (3, 5, 6):
                with self.assertRaisesRegex(ValueError, "4명"):
                    game.play(Match(tuple(f"P{i:02}" for i in range(size)), 8))
        self.assertEqual(len(result["survivors"]), 3)
        self.assertEqual(len(result["eliminated"]), 1)
        self.assertLessEqual(len(result["tiebreaks"]), 1)

    def test_saved_round_replays_identically_without_new_model_requests(self):
        class Stop(RuntimeError):
            pass
        with puzzles(), TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            header = {"type": "match", "game": SIXTH_EXILE}

            def record(log):
                def write(event):
                    log.write({"type": "event", **asdict(event), "model_calls": 0})
                    if event.msg_type == "flag_result":
                        raise Stop()
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
                with self.assertRaises(Stop):
                    game.play(resumed)
                log.write({"type": "interrupted", "model_calls": 0})
            self.assertEqual(resumed.requests, [])
            self.assertEqual(path.read_bytes(), before)

    def test_old_saved_six_player_roster_keeps_its_recorded_two_survivors(self):
        players = [f"P{i:02}" for i in range(1, 7)]
        match = Match(players, 8)
        match.resume_log = SimpleNamespace(resume=True, events=[
            {"msg_type": "flag_setup", "content": encode({"version": 1, "players": players, "survivor_count": 2})},
            {"msg_type": "rules", "content": game.LEGACY_RULES},
        ])
        with puzzles():
            result = game.play(match)
        self.assertEqual(len(result["survivors"]), 2)
        self.assertEqual(len(result["eliminated"]), 4)
        self.assertEqual(data(match, "flag_setup")[0]["version"], 1)
        self.assertEqual(data(match, "flag_setup")[0]["survivor_count"], 2)
        self.assertEqual(next(event.content for event in match.events if event.msg_type == "rules"), game.LEGACY_RULES)


if __name__ == "__main__":
    unittest.main()
