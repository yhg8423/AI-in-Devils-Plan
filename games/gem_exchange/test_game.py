"""Regression checks for the hidden-card match and deterministic resumption."""

from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from ..match import DAY_THREE_MAIN, Match, run_cli
from .game import BUYERS, CARDS, TABLE, play, round_points


class GemBlackMarketTest(unittest.TestCase):
    def test_round_scoring_counts_buyers_and_penalizes_bombs(self):
        cards = {
            "buyer1": {"kind": "silver", "value": 2},
            "buyer2": {"kind": "silver", "value": 3},
            "buyer3": {"kind": "diamond", "value": 5},
            "trash": {"kind": "gold", "value": 5},
            "A": {"kind": "silver", "value": 4},
            "B": {"kind": "diamond", "value": 6},
            "C": {"kind": "gold", "value": 4},
            "D": {"kind": "copper", "value": 1},
            "E": {"kind": "bomb", "value": -6},
            "F": {"kind": "bomb", "value": -4},
        }
        self.assertEqual(round_points(cards), {"A": 8, "B": 6, "C": 0, "D": 0, "E": -6, "F": -4})

    def test_complete_match_preserves_cards_private_information_and_rewards(self):
        class PeekingMatch(Match):
            def decide(self, name, phase, prompt, default, **kwargs):
                if phase == "gem_peek":
                    default = "buyer1"
                return super().decide(name, phase, prompt, default, **kwargs)

        for count, seed in ((9, 17), (10, 29)):
            with self.subTest(players=count):
                players = tuple(f"P{index:02}" for index in range(1, count + 1))
                initial = dict.fromkeys(players, 3)
                match = PeekingMatch(players, seed, pieces=list(initial.values()))
                result = play(match)
                scores = dict.fromkeys(players, 0)
                known = {}
                expected_bonuses = []
                actual_bonuses = []
                round_orders = {}
                swap_orders = {}
                peeks = Counter()
                diamond_rewards = Counter()
                expected_diamond_rewards = Counter()
                private_manitos = {}
                last_leader = None
                reveals = 0
                auction = None
                expected_deck = Counter((card["kind"], card["value"]) for card in CARDS)
                if count == 10:
                    expected_deck[("copper", 1)] += 1

                for event in match.events:
                    if not event.msg_type.startswith("gem_"):
                        continue
                    data = json.loads(event.content)
                    if event.msg_type in {"gem_manito", "gem_card", "gem_peek"}:
                        self.assertEqual(event.visible_to, [event.agent_name])
                        other = next(player for player in players if player != event.agent_name)
                        self.assertNotIn(event, match.observations(other))
                    if event.msg_type == "gem_manito":
                        private_manitos[event.agent_name] = data["beneficiary"]
                    elif event.msg_type == "gem_auction":
                        auction = data
                        last_leader = data["leader"]
                        for player in players:
                            self.assertEqual(data["pieces"][player], initial[player] -
                                             (data["bid"] if player == data["leader"] else 0))
                    elif event.msg_type == "gem_round":
                        known.clear()
                        round_orders[data["round"]] = data["order"]
                        self.assertEqual(data["leader"], last_leader)
                        self.assertEqual(data["order"][0], last_leader)
                    elif event.msg_type == "gem_card":
                        if known.get(data["slot"]) is not None:
                            self.assertEqual(data["card"], known[data["slot"]])
                        known[data["slot"]] = data["card"]
                    elif event.msg_type == "gem_peek":
                        self.assertIn(data["slot"], TABLE)
                        peeks[event.agent_name] += 1
                        self.assertEqual(peeks[event.agent_name], 1)
                        if known.get(data["slot"]) is not None:
                            self.assertEqual(data["card"], known[data["slot"]])
                        known[data["slot"]] = data["card"]
                    elif event.msg_type == "gem_swap":
                        self.assertEqual(event.visible_to, "all")
                        self.assertNotIn("card", data)
                        player, target = data["player"], data["target"]
                        self.assertNotEqual(player, target)
                        self.assertIn(target, (*players, *TABLE))
                        if known[player]["kind"] == "bomb":
                            self.assertIn(target, players)
                        if target in players and known[target]["kind"] == "bomb":
                            expected_bonuses.append(target)
                        known[player], known[target] = known.get(target), known[player]
                        swap_orders.setdefault((data["round"], data["pass"]), []).append(player)
                    elif event.msg_type == "gem_bonus":
                        self.assertEqual(data["points"], 3)
                        actual_bonuses.append(data["player"])
                        scores[data["player"]] += 3
                        self.assertEqual(data["scores"], scores)
                    elif event.msg_type == "gem_piece" and data["reason"] == "diamond":
                        diamond_rewards[data["player"]] += 1
                    elif event.msg_type == "gem_reveal":
                        reveals += 1
                        self.assertEqual(event.visible_to, "all")
                        cards = data["cards"]
                        self.assertEqual(set(cards), set(players) | set(TABLE))
                        self.assertEqual(Counter((card["kind"], card["value"]) for card in cards.values()), expected_deck)
                        for slot, card in known.items():
                            if card is not None:
                                self.assertEqual(cards[slot], card)
                        demand = Counter(cards[slot]["kind"] for slot in BUYERS)
                        points = {
                            player: cards[player]["value"] *
                            (1 if cards[player]["kind"] == "bomb" else demand[cards[player]["kind"]])
                            for player in players
                        }
                        self.assertEqual(data["points"], points)
                        for player in players:
                            scores[player] += points[player]
                            if cards[player]["kind"] == "diamond" and points[player] > 0:
                                expected_diamond_rewards[player] += 1
                        self.assertEqual(data["scores"], scores)
                        bombs = [player for player in players if cards[player]["kind"] == "bomb"]
                        if bombs:
                            last_leader = min(bombs, key=lambda player: cards[player]["value"])
                        self.assertEqual(data["next_leader"], last_leader)

                self.assertEqual(reveals, 3)
                self.assertEqual(actual_bonuses, expected_bonuses)
                self.assertEqual(diamond_rewards, expected_diamond_rewards)
                self.assertGreater(len(expected_bonuses), 0)
                self.assertGreaterEqual(len(peeks), count - 1)
                for round_number, order in round_orders.items():
                    self.assertEqual(swap_orders[(round_number, 1)], order)
                    self.assertEqual(swap_orders[(round_number, 2)], list(reversed(order)))
                self.assertEqual(result["raw_scores"], scores)
                self.assertEqual(result["manitos"], private_manitos)
                self.assertEqual(set(result["manitos"]), set(players))
                self.assertEqual(set(result["manitos"].values()), set(players))
                for source, beneficiary in result["manitos"].items():
                    self.assertNotEqual(source, beneficiary)
                    self.assertEqual(result["scores"][beneficiary], scores[source] * scores[beneficiary])
                ranking = result["ranking"]
                self.assertEqual(sorted(ranking), sorted(players))
                self.assertEqual([result["scores"][player] for player in ranking],
                                 sorted(result["scores"].values(), reverse=True))
                self.assertEqual(result["living"][:3], ranking[:3])
                self.assertEqual(len(result["living"]), 4)
                self.assertEqual(result["eliminated"], ranking[-1:])
                self.assertEqual(result["living"][-1], result["alliance_saved"])
                self.assertEqual(len(result["living"]) + len(result["prison"]) + len(result["eliminated"]), count)
                self.assertEqual(set(result["living"]) | set(result["prison"]) | set(result["eliminated"]), set(players))
                for player in players:
                    reward = (result["scores"][player] >= 1) + (result["scores"][player] >= 10)
                    self.assertEqual(result["pieces_awarded"][player], diamond_rewards[player] + reward)
                    spent = peeks[player] + (auction["bid"] if player == auction["leader"] else 0)
                    self.assertEqual(result["pieces_spent"][player], spent)
                    self.assertEqual(result["pieces"][player], initial[player] + diamond_rewards[player] + reward - spent)
                    self.assertGreaterEqual(result["pieces"][player], 0)

    def test_interrupted_swap_resumes_to_identical_game(self):
        original_event = Match.event

        def interrupt_after_swap(match, kind, data, **kwargs):
            original_event(match, kind, data, **kwargs)
            if kind == "gem_swap" and data["round"] == 2 and data["pass"] == 2:
                raise RuntimeError("test interruption after a committed swap")

        with (
            TemporaryDirectory() as directory,
            redirect_stdout(StringIO()),
            redirect_stderr(StringIO()),
            patch("games.models.CodexLanguageModel._complete", return_value='{"action":"pass","note":"test"}'),
        ):
            uninterrupted = Path(directory) / "full.jsonl"
            resumed = Path(directory) / "resumed.jsonl"
            arguments = ["--seed", "41", "--pieces", *(["3"] * 9), "--model", "test-model",
                         "--model-player", "P01", "--model-turns", "300", "--no-allow-review"]
            run_cli(play, title=DAY_THREE_MAIN, seats=(9, 10),
                    argv=[*arguments, "--output", str(uninterrupted)])
            with patch.object(Match, "event", interrupt_after_swap):
                with self.assertRaisesRegex(RuntimeError, "committed swap"):
                    run_cli(play, title=DAY_THREE_MAIN, seats=(9, 10),
                            argv=[*arguments, "--output", str(resumed)])
            prefix = [json.loads(line) for line in resumed.read_bytes().splitlines()]
            self.assertEqual(prefix[-1]["type"], "interrupted")
            decisions = resumed.with_suffix(".decisions.jsonl")
            self.assertTrue(decisions.read_bytes())
            run_cli(play, title=DAY_THREE_MAIN, seats=(9, 10),
                    argv=["--resume", "--output", str(resumed)])
            expected = [json.loads(line) for line in uninterrupted.read_bytes().splitlines()]
            actual = [json.loads(line) for line in resumed.read_bytes().splitlines()]
            self.assertEqual(actual[:-1], expected[:-1])
            self.assertEqual(actual[-1], expected[-1])
            self.assertEqual(actual[:len(prefix) - 1], prefix[:-1])


if __name__ == "__main__":
    unittest.main()
