"""Uniqueness, clue consistency, and the public flattened card atlas."""

from base64 import b64decode
from io import BytesIO
from string import ascii_uppercase
import unittest

import pygame

from .puzzles import COLORS, HEIGHT, SHAPES, WIDTH, board, make_puzzle, satisfies, solutions


class PuzzleTest(unittest.TestCase):
    def test_many_seeds_have_one_proven_four_card_solution_and_varied_clues(self):
        signatures, kinds = set(), set()
        for seed in range(40):
            with self.subTest(seed=seed):
                puzzle = make_puzzle(seed)
                cards, clues, answer = puzzle["cards"], puzzle["clues"], puzzle["solution"]
                self.assertEqual([card["letter"] for card in cards], list(ascii_uppercase))
                self.assertEqual(sorted(card["number"] for card in cards), list(range(1, 27)))
                self.assertEqual({card["color"] for card in cards}, set(COLORS))
                self.assertEqual({card["shape"] for card in cards}, set(SHAPES))
                self.assertEqual(solutions(cards, clues), [answer])
                self.assertEqual(len(answer), 4)
                self.assertEqual(len(set(answer)), 4)
                selected = [card for card in cards if card["letter"] in answer]
                self.assertTrue(all(satisfies(selected, clue) for clue in clues))
                self.assertTrue(all(clue["text"] and clue["en"] for clue in clues))
                self.assertLessEqual(len(clues), 7)
                signatures.add(tuple((clue["kind"], clue.get("attribute"), clue.get("rank")) for clue in clues))
                kinds.update(clue["kind"] for clue in clues)
        self.assertGreater(len(signatures), 10)
        self.assertTrue({"sum", "distinct", "gap", "rank"} <= kinds)

    def test_same_seed_has_identical_picture_and_no_solution_metadata(self):
        puzzle = make_puzzle(19)
        self.assertEqual(puzzle, make_puzzle(19))
        view = board(puzzle)
        self.assertEqual(view, board(puzzle))
        self.assertEqual(set(view), {"id", "width", "height", "image"})
        self.assertEqual((view["width"], view["height"]), (WIDTH, HEIGHT))
        encoded = b64decode(view["image"].partition(",")[2], validate=True)
        self.assertTrue(encoded.startswith(b"\x89PNG\r\n\x1a\n"))
        surface = pygame.image.load(BytesIO(encoded))
        self.assertEqual(surface.get_size(), (WIDTH, HEIGHT))
        self.assertNotEqual(view["id"], board(make_puzzle(20))["id"])
        for seed in (None, True, "19"):
            with self.subTest(seed=seed), self.assertRaises(ValueError):
                make_puzzle(seed)


if __name__ == "__main__":
    unittest.main()
