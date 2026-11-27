"""Exact fives, private resource accounting, deadlines, images, and resume."""

from base64 import b64decode
from dataclasses import asdict
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from ...match import EIGHTH_EXILE, Match, encode
from ...models import StrategyNote
from ...resume import MatchLog
from . import game
from .puzzles import board, empty_board, five_lines, legal_triples


PLAYERS = ("P01", "P02")


def rows(match, kind):
    return [json.loads(event.content) for event in match.events if event.msg_type == kind]


class LiveMatch(Match):
    def __init__(self, *, duration=0, **kwargs):
        super().__init__(PLAYERS, 9, live_turns=5000, count_calls=lambda: 0, **kwargs)
        self.backends = dict.fromkeys(PLAYERS, object())
        self.calls, self.duration = [], duration

    def decide_together(self, phase, decisions, **kwargs):
        self.phase, self.defaults = phase, {name: decision.default for name, decision in decisions.items()}
        answers = super().decide_together(phase, decisions, **kwargs)
        kwargs["response_times"].update({name: self.duration for name in decisions})
        return answers

    def _query(self, name, prompt, *args, **kwargs):
        history = game._observations(name, self.observations(name))
        self.calls.append((name, self.phase, prompt, history, kwargs["images"]))
        return self.defaults[name], StrategyNote(text=f"PRIVATE-{name}")


class PointGomokuTest(unittest.TestCase):
    def test_selection_enforces_empty_consecutive_integer_coordinates_but_retains_order(self):
        grid = empty_board()
        valid = [[3, 3], [2, 2], [1, 1]]
        self.assertEqual(game.parse_selection(encode({"points": valid}), grid), valid)
        for points in ([[[1, 1], [1, 2], [1, 3]]],):
            self.assertTrue(game.parse_selection(encode({"points": points[0]}), grid))
        invalid = [None, [], {"points": []}, {"points": [[1, 1]] * 3},
                   {"points": [[1, 1], [2, 1], [2, 2]]}, {"points": [[1, 1], [3, 1], [5, 1]]},
                   {"points": [[True, 1], [2, 1], [3, 1]]}, {"points": [[1.0, 1], [2, 1], [3, 1]]},
                   {"points": [[0, 1], [1, 1], [2, 1]]}, {"points": [[14, 1], [15, 1], [16, 1]]},
                   {"points": [[1, 1], [2, 1], [3, 1]], "extra": 0}]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                game.parse_selection(encode(value), grid)
        grid[0][1] = PLAYERS[0]
        with self.assertRaises(ValueError):
            game.parse_selection(encode({"points": [[1, 1], [2, 1], [3, 1]]}), grid)

    def test_bids_and_tie_priority_charge_both_players_and_floor_carry(self):
        self.assertEqual(game.parse_bid('{"bids":[1,1,1]}', 10), [1, 1, 1])
        for value in ([0, 1, 1], [True, 1, 1], [1.0, 1, 1], [9, 1, 1], [1, 1], [1, -1, 1]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                game.parse_bid(encode({"bids": value}), 10)
        points = [[1, 1], [2, 1], [3, 1]]
        bids = {"P01": [7, 1, 1], "P02": [6, 3, 1]}
        grid, owners, _, winner, reason, carry = game.settle(empty_board(), points, bids,
            dict.fromkeys(PLAYERS, 13), PLAYERS, "P01")
        self.assertEqual(owners, ["P01", "P02", "P02"])
        self.assertEqual(carry, {"P01": 2, "P02": 1})
        self.assertEqual(grid[0][:3], owners)
        self.assertIsNone(winner)
        self.assertIsNone(reason)
        _, owners, *_ = game.settle(empty_board(), points, dict.fromkeys(PLAYERS, [1, 1, 1]),
                                    dict.fromkeys(PLAYERS, 10), PLAYERS, "P02")
        self.assertEqual(owners, ["P01"] * 3)

    def test_exact_maximal_fives_and_three_stone_resolution_prevent_overline_win(self):
        grid = empty_board()
        for x in range(4):
            grid[0][x] = "P01"
        after, *_ = game.settle(grid, [[5, 1], [6, 1], [7, 1]],
            {"P01": [4, 4, 1], "P02": [1, 1, 2]}, dict.fromkeys(PLAYERS, 10), PLAYERS, "P01")
        self.assertEqual(five_lines(after, "P01"), [])
        after[0][5] = None
        self.assertEqual(five_lines(after, "P01"), [[[x, 1] for x in range(1, 6)]])
        for y in range(5):
            after[y][2] = "P01"
        self.assertEqual(len(five_lines(after, "P01")), 2)

    def test_simultaneous_fives_use_line_counts_and_equal_counts_draw(self):
        grid = empty_board()
        for x in range(4):
            grid[2][x] = "P01"
        for y in (0, 1, 3, 4):
            grid[y][4], grid[y][5] = "P01", "P02"
        bids = {"P01": [8, 1, 1], "P02": [1, 8, 1]}
        result = game.settle(grid, [[5, 3], [6, 3], [7, 3]], bids,
                             dict.fromkeys(PLAYERS, 10), PLAYERS, "P01")
        self.assertEqual({name: len(lines) for name, lines in result[2].items()}, {"P01": 2, "P02": 1})
        self.assertEqual(result[3:5], ("P01", "five"))
        for y in (0, 1, 3, 4):
            grid[y][4] = None
        result = game.settle(grid, [[5, 3], [6, 3], [7, 3]], bids,
                             dict.fromkeys(PLAYERS, 10), PLAYERS, "P01")
        self.assertEqual(result[3:5], (None, "equal_fives"))

    def test_png_public_board_is_deterministic_and_contains_no_wallet_metadata(self):
        grid = empty_board()
        image = board(grid, PLAYERS, selected=[[1, 1], [2, 1], [3, 1]])
        self.assertEqual(image, board(grid, PLAYERS, selected=[[1, 1], [2, 1], [3, 1]]))
        self.assertEqual(set(image), {"id", "width", "height", "image"})
        self.assertEqual((image["width"], image["height"]), (800, 800))
        self.assertTrue(b64decode(image["image"].partition(",")[2]).startswith(b"\x89PNG\r\n\x1a\n"))

    def test_real_match_is_finite_deterministic_and_private_bids_never_reach_other_player(self):
        match = LiveMatch()
        result = game.play(match)
        self.assertLess(result["rounds"], 76)
        self.assertFalse(match.relationship_reviews_enabled)
        self.assertEqual(result["pieces"], {result["winner"]: 5, result["eliminated"][0]: 0})
        self.assertEqual(result["returnee"], result["winner"])
        self.assertEqual(rows(match, "gomoku_setup")[0]["first_selector"], "P01")
        for name, _, _, history, images in match.calls:
            self.assertTrue(images[0].startswith(b"\x89PNG\r\n\x1a\n"))
            for event in history:
                self.assertTrue(event.visible_to == "all" or name in event.visible_to)
                if event.msg_type == "gomoku_bid":
                    self.assertEqual(json.loads(event.content)["player"], name)
                if event.msg_type == "gomoku_placement":
                    self.assertNotIn("board", json.loads(event.content))
        for event in match.events:
            if event.msg_type in {"gomoku_bid", "gomoku_wallet"}:
                self.assertEqual(event.visible_to, [event.agent_name])
            if event.visible_to == "all" and event.msg_type != "rules":
                self.assertFalse({"bids", "remaining", "available", "carry"} & set(json.loads(event.content)))
        self.assertEqual(game.play(Match(PLAYERS, 9)), game.play(Match(PLAYERS, 9)))

    def test_timeouts_are_strict_and_late_bids_use_one_each_without_public_amounts(self):
        for duration, late in ((90_000_000_000, False), (90_000_000_001, True)):
            match = LiveMatch(duration=duration)

            def stop(event):
                if event.msg_type == "gomoku_placement":
                    raise RuntimeError("first placement")

            match.on_event = stop
            with self.assertRaisesRegex(RuntimeError, "first placement"):
                game.play(match)
            bids = rows(match, "gomoku_bid")
            self.assertEqual(len(bids), 2)
            self.assertTrue(all(row["timeout"] is late for row in bids))
            self.assertEqual(bool(rows(match, "gomoku_selection_timeout")), late)
            if late:
                self.assertTrue(all(row["bids"] == [1, 1, 1] and row["carry"] == 3 for row in bids))

    def test_draw_restarts_fresh_with_opposite_selector_and_never_lotteries_a_winner(self):
        original = game.settle
        calls = 0

        def draw_once(*args):
            nonlocal calls
            calls += 1
            grid, owners, lines, winner, reason, carries = original(*args)
            return (grid, owners, lines, None, "no_triples", carries) if calls == 1 else (grid, owners, lines, winner, reason, carries)

        match = Match(PLAYERS, 4)
        with patch.object(game, "settle", side_effect=draw_once):
            result = game.play(match)
        games = rows(match, "gomoku_game")
        self.assertEqual(games[0]["first_selector"], "P01")
        self.assertEqual(games[1]["first_selector"], "P02")
        self.assertEqual(result["games"][0]["winner"], None)
        second_wallets = [row for row in rows(match, "gomoku_wallet") if row["game"] == 2 and row["round"] == 1]
        self.assertTrue(all(row["available"] == 10 and row["carry"] == 0 for row in second_wallets))

    def test_saved_sealed_bids_replay_exactly_without_fresh_model_queries(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            header = {"type": "match", "game": EIGHTH_EXILE, "players": list(PLAYERS), "seed": 9}

            def record(log):
                def write(event):
                    log.write({"type": "event", **asdict(event), "model_calls": 0})
                    if event.msg_type == "gomoku_bid":
                        raise RuntimeError("sealed bid saved")
                return write

            with MatchLog(path) as log:
                log.write(header)
                with self.assertRaisesRegex(RuntimeError, "sealed bid saved"):
                    game.play(LiveMatch(resume_log=log, on_event=record(log)))
                log.write({"type": "interrupted", "model_calls": 0})
            before = path.read_bytes()
            with MatchLog(path, resume=True) as log:
                log.write(header)
                match = LiveMatch(resume_log=log, on_event=record(log))
                with self.assertRaisesRegex(RuntimeError, "sealed bid saved"):
                    game.play(match)
                log.write({"type": "interrupted", "model_calls": 0})
            self.assertEqual(match.calls, [])
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
