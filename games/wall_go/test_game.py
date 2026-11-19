"""Wall Go II movement, scoring, continuation, and journal regressions."""

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from ..match import DAY_FOUR_MAIN, Match, run_cli
from ..models import OpenAILanguageModel, StrategyNote
from .game import Board, play


PLAYERS = ("P01", "P02", "P03")
TITLE = "4일차 감옥 매치 · 벽바둑 2"


def edge(a, b):
    return tuple(sorted((tuple(a), tuple(b))))


def all_edges():
    return {edge((r, c), (r + dr, c + dc))
            for r in range(1, 8) for c in range(1, 8)
            for dr, dc in ((1, 0), (0, 1)) if r + dr <= 7 and c + dc <= 7}


def open_board(kind="square"):
    board = Board(PLAYERS, PLAYERS, 1)
    positions = ((4, 4), (1, 4), (1, 1), (1, 7), (7, 1), (7, 7))
    for piece, position in zip(board.pieces.values(), positions, strict=True):
        piece["position"] = position
    if kind == "round":
        board.pieces["P01:square:1"]["position"] = (1, 4)
        board.pieces["P01:round:1"]["position"] = (4, 4)
    return board


def blocked_mixed_board(board=None):
    board = board or Board(PLAYERS, PLAYERS, 1)
    board.walls = all_edges()
    # Two P01 counters and one P02 counter cannot move inside this shared component.
    for row, start, end in ((1, 1, 3), (5, 1, 4), (7, 6, 7)):
        for col in range(start, end):
            board.walls.remove(edge((row, col), (row, col + 1)))
    positions = {"P01:square:1": (1, 1), "P01:round:1": (1, 3),
                 "P02:square:1": (1, 2), "P02:round:1": (7, 7),
                 "P03:square:1": (5, 1), "P03:round:1": (5, 4)}
    for name, position in positions.items():
        board.pieces[name]["position"] = position
    board.breakers = dict.fromkeys(PLAYERS, 0)
    return board


class WallGoTest(unittest.TestCase):
    def test_shapes_have_distinct_paths_and_cannot_stay_or_return(self):
        expected_square = {(2, 4), (3, 4), (5, 4), (6, 4), (4, 2), (4, 3), (4, 5), (4, 6)}
        square = [a for a in open_board().legal_actions("P01") if a["piece"] == "P01:square:1"]
        self.assertEqual({tuple(a["path"][-1]) for a in square}, expected_square)
        for action in square:
            path = [(4, 4), *map(tuple, action["path"])]
            self.assertIn(len(path), (2, 3))
            self.assertTrue(len({r for r, _ in path}) == 1 or len({c for _, c in path}) == 1)
        rounded = [a for a in open_board("round").legal_actions("P01") if a["piece"] == "P01:round:1"]
        self.assertEqual({tuple(a["path"][-1]) for a in rounded},
                         {(3, 4), (5, 4), (4, 3), (4, 5), (3, 3), (3, 5), (5, 3), (5, 5)})
        for action in rounded:
            path = [(4, 4), *map(tuple, action["path"])]
            if len(path) == 3:
                first = (path[1][0] - 4, path[1][1] - 4)
                second = (path[2][0] - path[1][0], path[2][1] - path[1][1])
                self.assertEqual(first[0] * second[0] + first[1] * second[1], 0)
            self.assertNotEqual(path[-1], (4, 4))

    def test_both_shapes_cannot_jump_over_a_counter(self):
        for kind in ("square", "round"):
            with self.subTest(kind=kind):
                board = open_board(kind)
                board.pieces["P02:square:1"]["position"] = (4, 5)
                actions = [a for a in board.legal_actions("P01") if a["piece"] == f"P01:{kind}:1"]
                self.assertFalse(any(a["path"][0] == [4, 5] for a in actions))
                if kind == "square":
                    self.assertNotIn((4, 6), {tuple(a["path"][-1]) for a in actions})
                else:
                    self.assertTrue(any(a["path"] == [[5, 4], [5, 5]] for a in actions))

    def test_wall_breaker_crosses_only_one_path_wall_and_is_consumed_atomically(self):
        board = open_board("round")
        first = edge((4, 4), (4, 5))
        second = edge((4, 5), (5, 5))
        board.walls.update((first, second))
        actions = board.legal_actions("P01")
        self.assertFalse(any(a["piece"] == "P01:round:1" and a["path"] == [[4, 5], [5, 5]] for a in actions))
        action = next(a for a in actions if a["piece"] == "P01:round:1" and a["path"] == [[4, 5]]
                      and edge(*a["wall"]) != first)
        result = board.apply("P01", action)
        self.assertEqual(edge(*result["broken"]), first)
        self.assertEqual(board.breakers["P01"], 0)
        self.assertNotIn(first, board.walls)
        self.assertIn(edge(*action["wall"]), board.walls)
        self.assertEqual(board.pieces[action["piece"]]["position"], (4, 5))

        blocked = open_board("round")
        blocked.walls.add(first)
        blocked.breakers["P01"] = 0
        self.assertFalse(any(a["piece"] == "P01:round:1" and a["path"][0] == [4, 5]
                             for a in blocked.legal_actions("P01")))

    def test_invalid_moves_never_change_board_or_piece_balance(self):
        board = open_board()
        valid = next(a for a in board.legal_actions("P01") if a["piece"] == "P01:square:1")
        bad = [
            {**valid, "wall": [[1, 1], [1, 2]]},
            {**valid, "wall": [[1, 1], [0, 1]]},
            {**valid, "path": []},
            {**valid, "path": [[3, 4], [4, 4]]},
            {**valid, "piece": "P02:square:1"},
            {**valid, "broken": [[4, 4], [4, 5]]},
        ]
        for action in bad:
            with self.subTest(action=action):
                before = deepcopy(board.snapshot())
                with self.assertRaises((ValueError, TypeError)):
                    board.apply("P01", action)
                self.assertEqual(board.snapshot(), before)

    def test_connected_territories_are_counted_once_and_largest_breaks_equal_totals(self):
        board = Board(PLAYERS, PLAYERS, 1)
        board.walls = all_edges()
        for a, b in (((1, 1), (1, 2)), ((3, 1), (3, 2)),
                     ((1, 4), (1, 5)), ((1, 4), (2, 4)), ((2, 4), (2, 5)), ((1, 5), (2, 5))):
            board.walls.remove(edge(a, b))
        for name, position in zip(board.pieces, ((1, 1), (3, 1), (1, 4), (2, 5), (7, 1), (7, 7)), strict=True):
            board.pieces[name]["position"] = position
        scores, largest = board.scores()
        self.assertEqual(scores, {"P01": 4, "P02": 4, "P03": 2})
        self.assertEqual(largest, {"P01": 2, "P02": 4, "P03": 1})
        self.assertEqual(board.ranking(), [["P02"], ["P01"], ["P03"]])
        self.assertTrue(board.separated())
        self.assertTrue(all(value == 1 for value in board.breakers.values()))

    def test_stalemate_scores_occupied_shared_cells_without_changing_exclusive_areas(self):
        board = blocked_mixed_board()
        before = deepcopy(board.snapshot())
        self.assertFalse(board.separated())
        self.assertTrue(all(not board.legal_actions(player) for player in PLAYERS))
        self.assertEqual(board.scores(), ({"P01": 0, "P02": 2, "P03": 4}, {"P01": 0, "P02": 2, "P03": 4}))
        self.assertEqual(board.scores(stalemate=True),
                         ({"P01": 2, "P02": 3, "P03": 4}, {"P01": 1, "P02": 2, "P03": 4}))
        self.assertEqual(board.ranking(stalemate=True), [["P03"], ["P02"], ["P01"]])
        territories = board.territories(stalemate=True)
        owned = {owner: [region["cells"] for region in territories if region["owner"] == owner] for owner in PLAYERS}
        self.assertCountEqual(owned["P01"], [[[1, 1]], [[1, 3]]])
        self.assertCountEqual(owned["P02"], [[[1, 2]], [[7, 6], [7, 7]]])
        self.assertEqual(owned["P03"], [[[5, 1], [5, 2], [5, 3], [5, 4]]])
        cells = [tuple(position) for region in territories for position in region["cells"]]
        self.assertEqual((len(cells), len(set(cells))), (49, 49))
        self.assertEqual(board.snapshot(), before)

    def test_stalemate_counts_a_two_cell_shared_component_as_one_point_each(self):
        board = blocked_mixed_board()
        board.walls.add(edge((1, 2), (1, 3)))
        self.assertFalse(board.separated())
        self.assertTrue(all(not board.legal_actions(player) for player in PLAYERS))
        scores, largest = board.scores(stalemate=True)
        self.assertEqual(scores, {"P01": 2, "P02": 3, "P03": 4})
        self.assertEqual(largest, {"P01": 1, "P02": 2, "P03": 4})
        self.assertIn({"owner": "P01", "cells": [[1, 1]]}, board.territories(stalemate=True))
        self.assertIn({"owner": "P02", "cells": [[1, 2]]}, board.territories(stalemate=True))

    def test_game_uses_stalemate_points_and_territories_for_the_final_ranking(self):
        class StalemateBoard(Board):
            def place(self, player, action):
                super().place(player, action)
                if self.round_number == 1 and all(piece["position"] is not None for piece in self.pieces.values()):
                    blocked_mixed_board(self)

        match = Match(PLAYERS, 19)
        with patch("games.wall_go.game.Board", StalemateBoard):
            result = play(match)
        end = next(event for event in match.events if event.msg_type == "wall_end")
        summary = json.loads(end.content)
        self.assertEqual(summary["reason"], "stalemate")
        self.assertEqual(summary["scores"], {"P01": 2, "P02": 3, "P03": 4})
        self.assertEqual(summary["largest"], {"P01": 1, "P02": 2, "P03": 4})
        self.assertEqual(summary["ranking"], [["P03"], ["P02"], ["P01"]])
        self.assertEqual(summary["winner"], "P03")
        self.assertEqual(summary["territories"], blocked_mixed_board().territories(stalemate=True))
        self.assertEqual(result["scores"], summary["scores"])
        self.assertEqual(result["games"][0], summary)
        self.assertEqual(result["ranking"][0], "P03")
        self.assertFalse(any(event.msg_type == "wall_move" for event in match.events[:end.turn]))

    def test_round_two_circles_start_on_opposite_diagonals_and_only_squares_are_placed(self):
        board = Board(("P02", "P01"), ("P02", "P01"), 2)
        self.assertEqual(board.pieces["P02:round:1"]["position"], (2, 2))
        self.assertEqual(board.pieces["P02:round:2"]["position"], (6, 6))
        self.assertEqual(board.pieces["P01:round:1"]["position"], (2, 6))
        self.assertEqual(board.pieces["P01:round:2"]["position"], (6, 2))
        self.assertEqual(board.breakers, {"P02": 0, "P01": 0})
        options = board.placement_options("P02")
        self.assertTrue(options)
        self.assertTrue(all(":square:" in action["piece"] for action in options))
        self.assertFalse(any(action["position"] in ([2, 2], [6, 6], [2, 6], [6, 2]) for action in options))
        first = options[0]
        board.place("P02", first)
        self.assertEqual(board.pieces[first["piece"]]["position"], tuple(first["position"]))
        before = deepcopy(board.snapshot())
        with self.assertRaises(ValueError):
            board.place("P02", first)
        self.assertEqual(board.snapshot(), before)

    def test_isolated_regions_skip_without_breakers_but_allow_preparing_an_escape(self):
        board = open_board()
        board.walls = {edge((r, 3), (r, 4)) for r in range(1, 8)}
        board.pieces["P01:square:1"]["position"] = (4, 1)
        board.pieces["P01:round:1"]["position"] = (5, 1)
        board.pieces["P02:square:1"]["position"] = (1, 7)
        board.pieces["P02:round:1"]["position"] = (2, 7)
        board.pieces["P03:square:1"]["position"] = (7, 7)
        board.pieces["P03:round:1"]["position"] = (6, 7)
        self.assertFalse(board.separated())
        self.assertTrue(board.legal_actions("P01"), "a pawn may approach a wall before using its remaining breaker")
        board.breakers["P01"] = 0
        self.assertEqual(board.legal_actions("P01"), [])

    def test_tied_players_only_replay_in_reversed_order_before_round_two(self):
        scenarios = [
            ([["P01"], ["P02", "P03"]], [["P03"], ["P02"]], ["P01", "P03", "P02"]),
            ([["P01", "P02"], ["P03"]], [["P02"], ["P01"]], ["P02", "P01", "P03"]),
        ]
        for first, replay, resolved in scenarios:
            with self.subTest(first=first), patch.object(Board, "ranking", side_effect=[first, replay, [[resolved[1]], [resolved[2]]]]):
                match = Match(PLAYERS, 19)
                result = play(match)
            setups = [json.loads(e.content) for e in match.events if e.msg_type == "wall_setup"]
            tied = next(group for group in first if len(group) > 1)
            self.assertEqual(set(setups[1]["players"]), set(tied))
            self.assertEqual(setups[1]["order"], [p for p in reversed(setups[0]["order"]) if p in tied])
            self.assertEqual(setups[1]["round"], 1)
            self.assertEqual(setups[2]["round"], 2)
            self.assertEqual(setups[2]["order"], resolved[1:])
            self.assertEqual(result["ranking"], resolved)

    def test_two_player_draw_swaps_first_player_and_fixed_circle_diagonals(self):
        with patch.object(Board, "ranking", side_effect=[[["P01"], ["P02"], ["P03"]],
                                                        [["P02", "P03"]], [["P03"], ["P02"]]]):
            match = Match(PLAYERS, 19)
            result = play(match)
        setups = [json.loads(e.content) for e in match.events if e.msg_type == "wall_setup"]
        self.assertEqual(setups[2]["order"], ["P03", "P02"])
        self.assertEqual(setups[2]["pieces"]["P03:round:1"]["position"], [2, 2])
        self.assertEqual(setups[2]["pieces"]["P02:round:1"]["position"], [2, 6])
        self.assertEqual(result["ranking"], ["P01", "P03", "P02"])

    def test_json_spacing_and_key_order_are_valid_model_actions(self):
        class PrettyJsonMatch(Match):
            def decide_together(self, phase, decisions, **kwargs):
                self.decisions = decisions
                return super().decide_together(phase, decisions, **kwargs)

            def _query(self, name, prompt, *args, **kwargs):
                return json.dumps(json.loads(self.decisions[name].default), indent=2, sort_keys=True), StrategyNote()

        match = PrettyJsonMatch(PLAYERS, 19, model=OpenAILanguageModel("test", Mock()),
                                live_players=PLAYERS, live_turns=1000)
        play(match)
        self.assertFalse(any(e.msg_type == "invalid_action" for e in match.events))

    def test_late_move_keeps_its_path_and_chooses_a_legal_wall(self):
        class LateMatch(Match):
            late_action = None

            def decide_together(self, phase, decisions, **kwargs):
                answers = super().decide_together(phase, decisions, **kwargs)
                if phase == "wall_move" and self.late_action is None:
                    name = next(iter(decisions))
                    self.late_action = json.loads(answers[name])
                    kwargs["response_times"][name] = 90_000_000_001
                return answers

        match = LateMatch(PLAYERS, 19)
        play(match)
        timeouts = [e for e in match.events if e.msg_type == "wall_timeout"]
        self.assertEqual(len(timeouts), 1)
        move = next(json.loads(e.content) for e in match.events if e.turn > timeouts[0].turn and e.msg_type == "wall_move")
        self.assertEqual(move["piece"], match.late_action["piece"])
        self.assertEqual(move["path"], match.late_action["path"])

    def test_scripted_match_finishes_silently_and_rewards_only_two_survivors(self):
        match = Match(PLAYERS, 19, pieces=(2, 3, 4))
        result = play(match)
        self.assertCountEqual(result["ranking"], PLAYERS)
        self.assertEqual(len(result["eliminated"]), 1)
        self.assertEqual(len(result["survivors"]), 2)
        self.assertEqual(result["ranking"][-1], result["eliminated"][0])
        for player, balance in zip(PLAYERS, (2, 3, 4), strict=True):
            self.assertEqual(result["pieces"][player], balance + int(player in result["survivors"]))
        self.assertFalse(match.relationship_reviews_enabled)
        self.assertFalse(any(event.msg_type in {"discussion_request", "public", "whisper", "relationship_update"}
                             for event in match.events))
        for event in match.events:
            if event.msg_type.startswith("wall_"):
                self.assertEqual(event.visible_to, "all")

    def test_cli_continuation_uses_only_main_match_prisoners_and_balances(self):
        roster = [f"P{seat:02}" for seat in range(1, 8)] + ["G01"]
        prisoners = ["P03", "P07", "P01"]
        balances = {name: index for index, name in enumerate(roster)}
        with TemporaryDirectory() as directory, redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            source = Path(directory) / "main.jsonl"
            output = Path(directory) / "prison.jsonl"
            source.write_text("\n".join(map(json.dumps, [
                {"type": "match", "game": DAY_FOUR_MAIN, "players": roster},
                {"type": "result", "ranking": roster[:-1], "prison": prisoners, "eliminated": ["P06"], "pieces": balances},
            ])) + "\n", encoding="utf-8")

            def verify(match):
                self.assertEqual(match.players, tuple(prisoners))
                self.assertEqual(match.pieces, {name: balances[name] for name in prisoners})
                self.assertNotIn("G01", match.players)
                return {"ranking": prisoners, "pieces": match.pieces}

            run_cli(verify, title=TITLE, seats=3, previous_main=DAY_FOUR_MAIN,
                    argv=["--from-main", str(source), "--output", str(output)])
            self.assertEqual(json.loads(output.read_text().splitlines()[0])["players"], prisoners)

    def test_interruptions_resume_without_repeating_committed_model_calls(self):
        original_event = Match.event
        fake_reply = json.dumps({"action": "invalid", "note": "공개 판과 합법 수를 비교한다."}, ensure_ascii=False)
        with (TemporaryDirectory() as directory, redirect_stdout(StringIO()), redirect_stderr(StringIO()),
              patch("games.models.CodexLanguageModel._complete", return_value=fake_reply) as completion):
            root = Path(directory)
            arguments = ["--players", *PLAYERS, "--seed", "19", "--model", "test-model", "--model-player", "P01",
                         "--model-turns", "1000", "--no-allow-review"]
            full = root / "full.jsonl"
            run_cli(play, title=TITLE, seats=3, previous_main=DAY_FOUR_MAIN,
                    argv=[*arguments, "--output", str(full)])
            expected = [json.loads(line) for line in full.read_text().splitlines()]
            for checkpoint in ("wall_setup", "wall_place", "wall_move", "wall_end"):
                with self.subTest(checkpoint=checkpoint):
                    output = root / f"{checkpoint}.jsonl"

                    def interrupt(match, kind, data, **kwargs):
                        original_event(match, kind, data, **kwargs)
                        if kind == checkpoint:
                            raise RuntimeError("interrupted after committed event")

                    with patch.object(Match, "event", interrupt), self.assertRaisesRegex(RuntimeError, "committed event"):
                        run_cli(play, title=TITLE, seats=3, previous_main=DAY_FOUR_MAIN,
                                argv=[*arguments, "--output", str(output)])
                    prefix = [json.loads(line) for line in output.read_text().splitlines()]
                    self.assertEqual(prefix[-1]["type"], "interrupted")
                    calls = completion.call_count
                    run_cli(play, title=TITLE, seats=3, previous_main=DAY_FOUR_MAIN,
                            argv=["--resume", "--output", str(output)])
                    actual = [json.loads(line) for line in output.read_text().splitlines()]
                    self.assertEqual(actual, expected)
                    self.assertEqual(actual[:len(prefix) - 1], prefix[:-1])
                    self.assertEqual(completion.call_count - calls, expected[-1]["model_calls"] - prefix[-1]["model_calls"])


if __name__ == "__main__":
    unittest.main()
