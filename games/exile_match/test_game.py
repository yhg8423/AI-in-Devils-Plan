"""Geometry, private simultaneous play, and interrupted-game continuation."""

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from io import BytesIO, StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import pygame

from ..match import Match, encode, run_cli
from ..models import OpenAILanguageModel, StrategyNote
from .diagram import piece_diagram
from .game import play
from .puzzle import Board, PIECES, compatible, pattern, piece_data, solution


PLAYERS = ("P01", "P02", "P03", "P04")
TITLE = "유배지 매치 1 · 피스 퍼즐"


def completed_board():
    board = Board()
    for placement in solution():
        board.apply({"type": "place", **placement})
    return board


class PiecePuzzleTest(unittest.TestCase):
    def test_eight_pieces_are_five_shapes_under_direction_changes(self):
        types = {min(pattern(piece, reverse, flip) for reverse in (False, True) for flip in (False, True))
                 for piece in PIECES}
        self.assertEqual(len(piece_data()), 8)
        self.assertEqual(len(types), 5)
        self.assertEqual(pattern("K1", True), ((1, 83), (1, 58), (0, 83), (0, 58)))
        self.assertEqual(pattern("K1", False, True), ((1, 58), (1, 83), (0, 58), (0, 83)))
        for piece in PIECES:
            for reverse in (False, True):
                first = pattern(piece, reverse, False)
                flipped = pattern(piece, reverse, True)
                self.assertEqual(tuple(depth for _, depth in first), tuple(depth for _, depth in flipped))
                self.assertTrue(all(a[0] != b[0] for a, b in zip(first, flipped, strict=True)))

    def test_crossings_require_opposite_openings_and_sufficient_depth(self):
        self.assertFalse(compatible((0, 83), (0, 83)))
        self.assertFalse(compatible((0, 33), (1, 58)))
        self.assertFalse(compatible((1, 33), (0, 33)))
        self.assertTrue(compatible((0, 33), (1, 83)))
        self.assertTrue(compatible((1, 58), (0, 58)))

    def test_search_uses_every_piece_once_and_all_crossings_fit(self):
        target = solution()
        self.assertEqual({pose["piece"] for pose in target}, set(PIECES))
        self.assertEqual({(pose["axis"], pose["slot"]) for pose in target},
                         {(axis, slot) for axis in ("row", "col") for slot in range(1, 5)})
        board = completed_board()
        self.assertTrue(board.solved())
        self.assertTrue(board.apply({"type": "submit"}))
        self.assertEqual(len(board.joints()), 16)
        self.assertEqual(board.snapshot()["errors"], 0)
        changed = target[0].copy()
        changed["flip"] = not changed["flip"]
        board.apply({"type": "place", **changed})
        self.assertEqual(board.snapshot()["errors"], 4)
        self.assertFalse(board.apply({"type": "submit"}))
        target[0]["flip"] = not target[0]["flip"]
        self.assertNotEqual(target, solution())

    def test_placing_a_strip_moves_it_and_returns_an_occupant_to_the_tray(self):
        board = Board()
        first, second = solution()[:2]
        board.apply({"type": "place", **first})
        board.apply({"type": "place", **second})
        board.apply({"type": "place", **first, "slot": second["slot"]})
        self.assertEqual(set(board.placements), {first["piece"]})
        self.assertEqual(board.placements[first["piece"]]["slot"], second["slot"])
        board.apply({"type": "remove", "piece": first["piece"]})
        self.assertEqual(board.snapshot(), {"placements": [], "joints": [], "errors": 0, "placed": 0})
        self.assertFalse(board.apply({"type": "submit"}))

    def test_invalid_actions_do_not_change_a_board(self):
        board = completed_board()
        placement = {"type": "place", **solution()[0]}
        invalid = [None, [], {**placement, "slot": True}, {**placement, "slot": "1"},
                   {**placement, "slot": 0}, {**placement, "reverse": 1}, {**placement, "flip": "false"},
                   {**placement, "axis": "diagonal"}, {**placement, "piece": "K9"},
                   {**placement, "extra": 1}, {"type": "submit", "board": []},
                   {"type": "remove", "piece": "unknown"}, {"type": []}]
        before = deepcopy(board.snapshot())
        for action in invalid:
            with self.subTest(action=action), self.assertRaises(ValueError):
                board.apply(action)
            self.assertEqual(board.snapshot(), before)
        for text in ("[]", "not JSON", '{"type":"place"}', '{"type":{}}'):
            self.assertFalse(board.accepts(text))

    def test_scripted_policy_repairs_any_full_board_in_at_most_eight_moves(self):
        target = solution()
        board = Board()
        for index, piece in enumerate(reversed(PIECES)):
            board.apply({"type": "place", "piece": piece, "axis": "row" if index < 4 else "col",
                         "slot": index % 4 + 1, "reverse": False, "flip": False})
        for _ in range(8):
            if board.solved():
                break
            before = board.snapshot()
            action = board.next_action(target)
            self.assertEqual(board.snapshot(), before)
            board.apply(action)
        self.assertTrue(board.solved())
        self.assertTrue(board.apply(board.next_action(target)))

    def test_piece_diagram_is_a_cached_png_with_an_empty_target(self):
        image = piece_diagram()
        self.assertTrue(image.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertIs(image, piece_diagram())
        surface = pygame.image.load(BytesIO(image))
        self.assertEqual(surface.get_size(), (1024, 960))

    def test_same_turn_finishers_use_the_announced_order_without_adding_pieces(self):
        match = Match(PLAYERS, 19, pieces=[0, 1, 2, 3])
        result = play(match)
        setup = json.loads(next(event.content for event in match.events if event.msg_type == "exile_setup"))
        self.assertEqual(result["ranking"], setup["turn_order"])
        self.assertEqual(result["survivors"], setup["turn_order"][:3])
        self.assertEqual(result["eliminated"], setup["turn_order"][3:])
        self.assertEqual(result["finish_turns"], dict.fromkeys(PLAYERS, 9))
        self.assertEqual(result["pieces"], dict(zip(PLAYERS, [0, 1, 2, 3], strict=True)))
        self.assertFalse(match.relationship_reviews_enabled)

    def test_queries_receive_only_their_own_board_and_shared_diagram(self):
        class ObservedMatch(Match):
            checks = []

            def decide_together(self, phase, decisions, **kwargs):
                self.decisions = decisions
                self.checks.append(kwargs["images"])
                for name in decisions:
                    self_test.assertIn("내 보드:", decisions[name].prompt)
                    for event in self.observations(name):
                        if event.msg_type == "exile_board":
                            self_test.assertEqual(json.loads(event.content)["player"], name)
                        self_test.assertNotEqual(event.msg_type, "exile_reveal")
                return super().decide_together(phase, decisions, **kwargs)

            def _query(self, name, prompt, *args, **kwargs):
                self_test.assertEqual(kwargs["images"], (piece_diagram(),))
                return self.decisions[name].default, StrategyNote()

        self_test = self
        match = ObservedMatch(PLAYERS, 19, model=OpenAILanguageModel("test", Mock()),
                              live_players=PLAYERS, live_turns=100)
        result = play(match)
        self.assertEqual(len(result["survivors"]), 3)
        reveal = next(index for index, event in enumerate(match.events) if event.msg_type == "exile_reveal")
        attempts = [index for index, event in enumerate(match.events) if event.msg_type == "exile_attempt"]
        self.assertGreater(reveal, max(attempts))
        self.assertNotIn("boards", result)
        for event in match.events[:reveal]:
            if event.msg_type in ("exile_board", "action"):
                self.assertEqual(event.visible_to, [event.agent_name])

    def test_malformed_model_actions_pass_then_the_budget_falls_back_to_scripted_play(self):
        class InvalidMatch(Match):
            def _query(self, *args, **kwargs):
                return '{"type":"place","piece":"K1","axis":"row","slot":true,"reverse":false,"flip":false}', StrategyNote()

        match = InvalidMatch(PLAYERS, 19, model=OpenAILanguageModel("test", Mock()),
                             live_players=PLAYERS, live_turns=8)
        result = play(match)
        self.assertEqual(result["turns"], 11)
        first_moves = [json.loads(e.content)["action"] for e in match.events if e.msg_type == "action"][:8]
        self.assertEqual([json.loads(action) for action in first_moves], [{"type": "pass"}] * 8)
        self.assertEqual(match.live_turns, 0)
        self.assertEqual(len(result["eliminated"]), 1)

    def test_wrong_buzzer_can_be_corrected_and_does_not_finish_the_player(self):
        class EarlyBuzzerMatch(Match):
            def decide_together(self, phase, decisions, **kwargs):
                self.decisions = decisions
                return super().decide_together(phase, decisions, **kwargs)

            def _query(self, name, prompt, *args, **kwargs):
                return ('{"type":"submit"}' if len(self.events) < 5 else self.decisions[name].default), StrategyNote()

        match = EarlyBuzzerMatch(PLAYERS, 19, model=OpenAILanguageModel("test", Mock()),
                                live_players=PLAYERS, live_turns=100)
        result = play(match)
        attempts = [json.loads(e.content) for e in match.events if e.msg_type == "exile_attempt"]
        self.assertFalse(attempts[0]["correct"])
        self.assertIsNone(attempts[0]["place"])
        self.assertEqual(result["turns"], 10)

    def test_completed_players_stop_receiving_actions(self):
        class SlowMatch(Match):
            def decide_together(self, phase, decisions, **kwargs):
                self.decisions = decisions
                return super().decide_together(phase, decisions, **kwargs)

            def _query(self, name, prompt, *args, **kwargs):
                current = next(e for e in reversed(self.events) if e.msg_type == "exile_turn")
                turn = json.loads(current.content)["turn"]
                delay = {"P01": 0, "P02": 1, "P03": 2, "P04": 3}[name]
                return (encode({"type": "pass"}) if turn <= delay else self.decisions[name].default), StrategyNote()

        match = SlowMatch(PLAYERS, 19, model=OpenAILanguageModel("test", Mock()),
                          live_players=PLAYERS, live_turns=100)
        result = play(match)
        self.assertEqual(result["ranking"], list(PLAYERS))
        self.assertEqual(result["eliminated"], ["P04"])
        self.assertEqual(set(result["finish_turns"]), set(PLAYERS) - {"P04"})
        self.assertEqual(result["turns"], 11)
        turns = {json.loads(e.content)["turn"]: json.loads(e.content)["active"]
                 for e in match.events if e.msg_type == "exile_turn"}
        self.assertNotIn("P01", turns[10])
        self.assertNotIn("P01", turns[11])
        self.assertNotIn("P02", turns[11])

    def test_game_rejects_a_wrong_or_duplicate_roster(self):
        for players in (PLAYERS[:3], ("P01",) * 4):
            with self.subTest(players=players), self.assertRaises(ValueError):
                play(Match(players, 1))

    def test_interruptions_resume_exactly_without_repeating_committed_calls(self):
        original_event = Match.event
        reply = json.dumps({"action": '{"type":"pass"}', "note": "내 보드의 교차점을 확인한다."})
        with (TemporaryDirectory() as directory, redirect_stdout(StringIO()), redirect_stderr(StringIO()),
              patch("games.models.CodexLanguageModel._complete", return_value=reply) as completion):
            root = Path(directory)
            arguments = ["--players", *PLAYERS, "--seed", "19", "--model", "test-model", "--model-turns", "4"]
            full = root / "full.jsonl"
            run_cli(play, title=TITLE, seats=4, argv=[*arguments, "--output", str(full)])
            expected = [json.loads(line) for line in full.read_text().splitlines()]
            for checkpoint in ("exile_setup", "exile_board", "exile_attempt", "exile_reveal"):
                with self.subTest(checkpoint=checkpoint):
                    output = root / f"{checkpoint}.jsonl"

                    def interrupt(match, kind, data, **kwargs):
                        original_event(match, kind, data, **kwargs)
                        if kind == checkpoint:
                            raise RuntimeError("interrupted after committed event")

                    with patch.object(Match, "event", interrupt), self.assertRaisesRegex(RuntimeError, "committed event"):
                        run_cli(play, title=TITLE, seats=4, argv=[*arguments, "--output", str(output)])
                    prefix = [json.loads(line) for line in output.read_text().splitlines()]
                    calls = completion.call_count
                    run_cli(play, title=TITLE, seats=4, argv=["--resume", "--output", str(output)])
                    actual = [json.loads(line) for line in output.read_text().splitlines()]
                    self.assertEqual(actual, expected)
                    self.assertEqual(actual[:len(prefix) - 1], prefix[:-1])
                    self.assertEqual(completion.call_count - calls, expected[-1]["model_calls"] - prefix[-1]["model_calls"])


if __name__ == "__main__":
    unittest.main()
