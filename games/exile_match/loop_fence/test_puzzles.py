"""Solver completeness, unique generated boards, and flattened private marks."""

from base64 import b64decode
from io import BytesIO
from itertools import product
import unittest

import pygame

from .puzzles import all_edges, board, cell_edges, judge, make_puzzle, solve


def unit_loop(row, col):
    return list(cell_edges(row, col))


class PuzzleTest(unittest.TestCase):
    def test_small_board_solver_matches_exhaustive_edge_subsets(self):
        edges = all_edges(2, 2)
        blank = [[None, None], [None, None]]
        loops = []
        for bits in product((False, True), repeat=len(edges)):
            chosen = [edge for edge, marked in zip(edges, bits, strict=True) if marked]
            if judge({"size": 2, "clues": blank}, chosen):
                loops.append(frozenset(chosen))
        self.assertEqual(len(loops), 13)
        for clues in (blank, [[3, None], [None, None]], [[0, 0], [0, 0]],
                      [[2, 2], [2, 2]], [[1, 2], [2, 1]], [[3, 3], [3, 3]]):
            with self.subTest(clues=clues):
                expected = {loop for loop in loops if all(
                    value is None or sum(edge in loop for edge in cell_edges(row, col)) == value
                    for row, line in enumerate(clues) for col, value in enumerate(line))}
                actual = [frozenset(answer) for answer in solve(clues, limit=100)]
                self.assertEqual(set(actual), expected)
                self.assertEqual(len(actual), len(set(actual)))

    def test_judge_accepts_unused_dots_and_blanks_but_rejects_multiple_loops_and_deadends(self):
        puzzle = {"size": 3, "clues": [[None] * 3 for _ in range(3)], "solution": []}
        loop = unit_loop(0, 0)
        self.assertTrue(judge(puzzle, loop))  # The secret solution field is not the judge.
        for edges in ([], loop[:-1], loop + unit_loop(2, 2), loop + unit_loop(1, 1),
                      loop + [loop[0]], loop + [("H", 3, 3)], [("D", 0, 0)]):
            with self.subTest(edges=edges):
                self.assertFalse(judge(puzzle, edges))
        puzzle["clues"][0][0] = 0
        self.assertFalse(judge(puzzle, loop))

    def test_generated_seven_by_seven_boards_are_varied_and_exhaustively_unique(self):
        signatures, values = set(), set()
        for seed in range(40):
            with self.subTest(seed=seed):
                puzzle = make_puzzle(seed)
                self.assertEqual(puzzle["size"], 7)
                self.assertTrue(all(len(line) == 7 for line in puzzle["clues"]))
                self.assertEqual(len(puzzle["clues"]), 7)
                self.assertGreaterEqual(sum(value is None for line in puzzle["clues"] for value in line), 3)
                answers = solve(puzzle["clues"])
                self.assertEqual(answers, [puzzle["solution"]])
                self.assertTrue(judge(puzzle, puzzle["solution"]))
                self.assertGreaterEqual(len(puzzle["solution"]), 20)
                signatures.add(tuple(tuple(line) for line in puzzle["clues"]))
                values.update(value for line in puzzle["clues"] for value in line)
        self.assertEqual(len(signatures), 40)
        self.assertEqual(values, {None, 0, 1, 2, 3})
        self.assertEqual(make_puzzle(19), make_puzzle(19))

    def test_pngs_are_exact_size_and_only_explicit_marks_change_the_public_picture(self):
        puzzle = make_puzzle(19)
        view = board(puzzle)
        self.assertEqual(set(view), {"id", "width", "height", "image"})
        encoded = b64decode(view["image"].partition(",")[2], validate=True)
        self.assertTrue(encoded.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(pygame.image.load(BytesIO(encoded)).get_size(), (960, 640))
        marked = board(puzzle, puzzle["solution"][:3])
        crossed = board(puzzle, crosses=puzzle["solution"][:1])
        self.assertEqual(len({view["id"], marked["id"], crossed["id"]}), 3)
        puzzle["solution"] = []
        self.assertEqual(board(puzzle), view)

    def test_solver_and_generator_reject_malformed_inputs(self):
        for clues in ([], [[]], [[True]], [[4]], [[-1]], [["1"]], [[0], [0, 1]], None):
            with self.subTest(clues=clues), self.assertRaises(ValueError):
                solve(clues)
        for seed, size in ((None, 7), (True, 7), (1, True), (1, 2), (1, 9)):
            with self.subTest(seed=seed, size=size), self.assertRaises(ValueError):
                make_puzzle(seed, size)
        with self.assertRaises(ValueError):
            solve([[None]], limit=0)


if __name__ == "__main__":
    unittest.main()
