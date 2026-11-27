"""Exact arithmetic, legal stack operations, bid timing, overtime, and replay."""

from contextlib import redirect_stderr, redirect_stdout
from fractions import Fraction
from io import StringIO
import json
from pathlib import Path
from random import Random
import struct
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from ..match import DAY_FIVE_PRISON, Match, encode, run_cli
from ..models import StrategyNote
from .game import BLOCKS, Board, board_image, constructive_problem, execute, make_problem, parse_bid, play


def board_with(stack):
    return Board([[], list(stack), [], [key for key in BLOCKS if key not in stack]])


MOVE = {"from": 2, "to": 1, "count": 3, "flip": False}


class TowerBoardTests(unittest.TestCase):
    def test_inventory_and_ordinary_precedence_with_exact_fractions(self):
        self.assertEqual(len(BLOCKS), 20)
        self.assertEqual({block["value"] for block in BLOCKS.values()}, {2, 3, 5, 7})
        self.assertEqual(sum(b["operator"] is None for b in BLOCKS.values()), 4)
        board = board_with(["mul2", "add3", "n5"])
        self.assertEqual(board.expression(1), ("5+3×2", Fraction(11)))
        self.assertEqual(board_with(["mul3", "div3", "n2"]).expression(1)[1], 2)
        self.assertEqual(board_with(["div2", "sub3", "n2"]).expression(1)[1], Fraction(1, 2))
        self.assertEqual(board_with(["div3", "n2"]).expression(1)[1], Fraction(2, 3))
        self.assertEqual(board_with(["n3", "n2"]).expression(1), (None, None))
        self.assertEqual(board_with(["add3", "mul2"]).expression(1), (None, None))

    def test_exact_height_and_number_first(self):
        board = board_with(["mul5", "add3", "n2"])
        self.assertIsNotNone(board.solution(17, 3)[0])
        self.assertEqual(board.solution(17, 2), (None, None))
        self.assertEqual(board.solution(25, 3), (None, None))

    def test_top_bundle_moves_flip_and_fresh_snapshots(self):
        board = board_with(["mul5", "add3", "n2"])
        saved = board.snapshot()
        board.move({"from": 2, "to": 2, "count": 2, "flip": True})
        self.assertEqual(board.stacks[1], ["mul5", "n2", "add3"])
        board.move({"from": 2, "to": 1, "count": 2, "flip": True})
        self.assertEqual(board.stacks[0], ["add3", "n2"])
        self.assertEqual(board.stacks[1], ["mul5"])
        self.assertEqual(saved[1], ["mul5", "add3", "n2"])
        for invalid in ({**MOVE, "from": True}, {**MOVE, "to": 5}, {**MOVE, "count": 99},
                        {**MOVE, "count": 0}, {**MOVE, "flip": 1},
                        {"from": 1, "to": 1, "count": 1, "flip": True},
                        {"from": 1, "to": 1, "count": 2, "flip": False}):
            before = board.snapshot()
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                board.move(invalid)
            self.assertEqual(board.snapshot(), before)
        self.assertEqual(sorted(key for stack in board.stacks for key in stack), sorted(BLOCKS))

    def test_execution_time_and_valid_prefix_persist_on_failure(self):
        board = board_with(["mul5", "add3", "n2"])
        before = board.snapshot()
        verdict = execute(board, encode({"moves": [MOVE]}), 17, 3, 1, late=True)
        self.assertEqual((verdict["reason"], verdict["used"]), ("timeout", 0))
        self.assertEqual(board.snapshot(), before)
        events = []
        verdict = execute(board, encode({"moves": [MOVE, {**MOVE, "from": 3}]}), 17, 3, 2,
                          on_move=lambda index, action: events.append((index, action)))
        self.assertEqual((verdict["success"], verdict["reason"], verdict["used"]), (False, "invalid_move", 1))
        self.assertEqual(board.stacks[0], before[1])
        self.assertEqual(events, [(1, MOVE)])
        board = Board(before)
        verdict = execute(board, encode({"moves": [MOVE, {**MOVE, "from": 1, "to": 2}]}), 17, 3, 1)
        self.assertEqual((verdict["reason"], verdict["used"]), ("move_limit", 1))
        self.assertEqual(board.stacks[0], before[1])
        self.assertFalse(execute(Board(before), "not json", 17, 3, 1)["success"])
        verdict = execute(Board(before), encode({"moves": [MOVE]}), 17, 3, 4)
        self.assertTrue(verdict["success"])
        self.assertEqual((verdict["value"], verdict["used"]), ("17", 1))

    def test_generated_questions_have_legal_private_witnesses_and_public_png(self):
        rng = Random(27)
        board = Board([list(BLOCKS)[i:i + 5] for i in range(0, 20, 5)])
        for _ in range(35):
            before = board.snapshot()
            target, height, moves = make_problem(board, rng)
            self.assertEqual(board.snapshot(), before)
            verdict = execute(board, encode({"moves": moves}), target, height, len(moves))
            self.assertTrue(verdict["success"])
            self.assertIn(height, range(3, 7))
            self.assertEqual(sum(map(len, board.stacks)), 20)
        image = board_image(board, target, height)
        self.assertTrue(image.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(struct.unpack(">II", image[16:24]), (1024, 900))

    def test_constructive_problem_fallback_is_solvable(self):
        class FixedRandom:
            def choice(self, actions):
                return actions[0]
        board = Board([list(BLOCKS)[i:i + 5] for i in range(0, 20, 5)])
        target, height, witness = make_problem(board, FixedRandom())
        self.assertTrue(execute(board, encode({"moves": witness}), target, height, len(witness))["success"])
        for board in (Board([list(BLOCKS), [], [], []]), board_with(["mul5", "add3", "n2"])):
            before = board.snapshot()
            target, height, witness = constructive_problem(board)
            self.assertIsNone(board.solution(target, height)[0])
            self.assertEqual(board.snapshot(), before)
            self.assertTrue(execute(board, encode({"moves": witness}), target, height, len(witness))["success"])

    def test_bid_parser_rejects_booleans_zero_and_extra_fields(self):
        self.assertEqual(parse_bid('{"type":"bid","moves":5}')["moves"], 5)
        self.assertEqual(parse_bid('{"type":"wait"}'), {"type": "wait"})
        for value in (True, 0, -1, 1.5, "3"):
            with self.assertRaises(ValueError):
                parse_bid(encode({"type": "bid", "moves": value}))
        with self.assertRaises(ValueError):
            parse_bid('{"type":"wait","moves":2}')


class TowerMatchTests(unittest.TestCase):
    def test_scripted_two_and_three_player_games_finish_deterministically(self):
        for size in (2, 3):
            players = [f"P{i}" for i in range(size)]
            first = Match(players, 12)
            result = play(first)
            second = Match(players, 12)
            self.assertEqual(play(second), result)
            self.assertEqual([e.content for e in first.events], [e.content for e in second.events])
            self.assertCountEqual(result["ranking"], players)
            self.assertEqual(result["survivors"], result["ranking"][:-1])
            self.assertEqual(len(result["eliminated"]), 1)
            self.assertEqual(sum(result["pieces_awarded"].values()), 3)
            self.assertEqual(result["pieces"][result["ranking"][0]], 4)
            self.assertLess(result["rounds"], 150)
            self.assertFalse(first.relationship_reviews_enabled)
            setup = json.loads(next(e.content for e in first.events if e.msg_type == "tower_setup"))
            self.assertEqual(list(map(len, setup["stacks"])), [5] * 4)
            self.assertEqual(setup["blocks"], BLOCKS)
            self.assertEqual(setup["goal"], 7)
            self.assertFalse(any(e.msg_type.startswith("relationship") or e.msg_type == "speech" for e in first.events))

    def run_controlled(self, choose):
        match = Match(["A", "B", "C"], 51)
        original = match.decide_together
        calls = []
        def decide(phase, decisions, **kwargs):
            self.assertTrue(kwargs["images"][0].startswith(b"\x89PNG"))
            self.assertNotIn("witness", " ".join(d.prompt for d in decisions.values()))
            self.assertEqual(kwargs.get("max_reviews"), 0)
            calls.append((phase, tuple(decisions)))
            overrides, times = choose(match, phase, decisions)
            kwargs["response_times"].update(times)
            answers = original(phase, decisions, **{key: value for key, value in kwargs.items() if key != "response_times"})
            answers.update(overrides)
            return answers
        match.decide_together = decide
        result = play(match)
        return match, result, calls

    def test_counter_stake_and_time_window_early_equal_bids_do_not_steal(self):
        def choose(match, phase, decisions):
            name = next(iter(decisions))
            if phase == "tower_opening_bid":
                bid = json.loads(decisions[name].default)["moves"] + 1
                return {p: encode({"type": "bid", "moves": bid}) for p in decisions}, {p: 0 if p == "A" else 100 for p in decisions}
            if phase == "tower_counter_bid":
                first = json.loads(next(e.content for e in reversed(match.events) if e.msg_type == "tower_bid"))
                return {p: encode({"type": "bid", "moves": first["moves"] - 1}) for p in decisions}, {"B": 1, "C": 2}
            return {}, {name: 120_000_000_000}
        match, result, calls = self.run_controlled(choose)
        challenges = [json.loads(e.content) for e in match.events if e.msg_type == "tower_challenge"]
        first_advance = json.loads(next(e.content for e in match.events if e.msg_type == "tower_advance"))
        self.assertTrue(all(row["player"] == "B" and row["stake"] == 2
                            for row in challenges if row["round"] <= first_advance["round"]))
        verdicts = [json.loads(e.content) for e in match.events if e.msg_type == "tower_verdict"]
        self.assertTrue(all(row["success"] and row["change"] == 2 for row in verdicts))
        self.assertEqual(result["ranking"][0], "B")
        self.assertIn(("tower_counter_bid", ("B", "C")), calls)
        self.assertTrue(any(json.loads(e.content)["reset_scores"] for e in match.events if e.msg_type == "tower_advance"))

    def test_no_bid_late_execution_and_tied_lowest_overtime(self):
        def choose(match, phase, decisions):
            problem = json.loads(next(e.content for e in reversed(match.events) if e.msg_type == "tower_problem"))
            number, active = problem["round"], problem["players"]
            if phase == "tower_opening_bid":
                if number == 1:
                    return {}, {p: 300_000_000_001 for p in decisions}
                winner = "A" if "A" in active else "B"
                return {}, {p: 0 if p == winner else 10 for p in decisions}
            if phase == "tower_execute" and number == 2:
                return {}, {next(iter(decisions)): 120_000_000_001}
            return {}, {}
        match, result, calls = self.run_controlled(choose)
        self.assertEqual(result["ranking"], ["A", "B", "C"])
        self.assertTrue(any(e.msg_type == "tower_skip" for e in match.events))
        verdicts = [json.loads(e.content) for e in match.events if e.msg_type == "tower_verdict"]
        self.assertEqual((verdicts[0]["reason"], verdicts[0]["used"]), ("timeout", 0))
        advances = [json.loads(e.content) for e in match.events if e.msg_type == "tower_advance"]
        self.assertCountEqual(advances[0]["tied"], ["B", "C"])
        self.assertEqual(advances[0]["safe"], ["A"])
        after = next(json.loads(e.content) for e in match.events if e.msg_type == "tower_problem"
                     and json.loads(e.content)["round"] > advances[0]["round"])
        self.assertEqual((after["scores"]["B"], after["scores"]["C"]), (0, 0))
        self.assertNotIn("A", after["players"])
        self.assertEqual(result["pieces_awarded"], {"A": 3, "B": 0, "C": 0})
        self.assertFalse(advances[-1]["reset_scores"])
        observed = match.model_observations("A", match.events)
        self.assertTrue(any(e.msg_type == "action" for e in observed))
        self.assertFalse(any(e.msg_type == "action" and e.agent_name != "A" for e in observed))

    def test_seeded_order_breaks_identical_opening_nanoseconds(self):
        def choose(match, phase, decisions):
            return {}, dict.fromkeys(decisions, 0)
        match, result, _ = self.run_controlled(choose)
        setup = json.loads(next(e.content for e in match.events if e.msg_type == "tower_setup"))
        self.assertEqual(result["ranking"][0], setup["order"][0])

    def test_invalid_live_actions_exhaust_budget_then_scripted_game_finishes(self):
        match = Match(["A", "B"], 23, models={"A": object(), "B": object()}, live_turns=3)
        requests = []
        def query(name, prompt, **kwargs):
            requests.append((name, prompt, kwargs))
            self.assertNotIn('"moves":[', prompt.split("해법은")[0])
            return "malformed", StrategyNote(text=f"private-{name}")
        with patch.object(match, "_query", side_effect=query):
            result = play(match)
        self.assertEqual(len(requests), 3)
        self.assertEqual(match.live_turns, 0)
        self.assertEqual(len(result["eliminated"]), 1)
        self.assertTrue(all(kwargs["images"][0].startswith(b"\x89PNG") for _, _, kwargs in requests))
        self.assertTrue(any(event.msg_type == "invalid_action" for event in match.events))
        for name in match.players:
            own = match.model_observations(name, match.observations(name))
            self.assertFalse(any(event.msg_type == "decision_note" and event.agent_name != name for event in own))
            self.assertTrue(any(event.msg_type == "invalid_action" for event in own))

    def test_timed_decisions_resume_after_committed_move_without_model_requery(self):
        event = Match.event
        def query(name, prompt, **kwargs):
            action = '{"moves":[]}' if "실연자" in prompt else '{"type":"wait"}' if "추가 입찰:" in prompt else '{"type":"bid","moves":3}'
            return action, StrategyNote(text="private")
        with (TemporaryDirectory() as directory, redirect_stdout(StringIO()), redirect_stderr(StringIO()),
              patch.object(Match, "_query", side_effect=query),
              patch("games.match.monotonic_ns", return_value=70_000_000_000)):
            arguments = ["--players", "A", "B", "C", "--seed", "19", "--model", "test", "--model-turns", "6"]
            root = Path(directory)
            complete, interrupted = root / "complete.jsonl", root / "interrupted.jsonl"
            run_cli(play, title=DAY_FIVE_PRISON, seats=(3, 2), argv=[*arguments, "--output", str(complete)])
            def stop(match, kind, value, **kwargs):
                event(match, kind, value, **kwargs)
                if kind == "tower_move":
                    raise RuntimeError("committed move")
            with patch.object(Match, "event", stop), self.assertRaisesRegex(RuntimeError, "committed move"):
                run_cli(play, title=DAY_FIVE_PRISON, seats=(3, 2), argv=[*arguments, "--output", str(interrupted)])
            with patch.object(Match, "_query", side_effect=AssertionError("model called twice")):
                run_cli(play, title=DAY_FIVE_PRISON, seats=(3, 2), argv=["--resume", "--output", str(interrupted)])
            self.assertEqual([json.loads(line) for line in complete.read_text().splitlines()],
                             [json.loads(line) for line in interrupted.read_text().splitlines()])


if __name__ == "__main__":
    unittest.main()
