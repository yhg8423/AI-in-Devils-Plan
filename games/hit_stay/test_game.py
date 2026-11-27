"""Card, betting, privacy, tournament and deterministic resumption checks."""

from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ..match import Match, run_cli
from .game import (
    DECK, DECK_COUNTS, Round, ante_for, effective_cap, first_bust_loser,
    parse_bet, play, settle_round,
)


PLAYERS = ("P01", "P02", "P03", "P04")
TITLE = "6일차 메인 매치 · HIT, STAY"


class ScriptMatch(Match):
    def __init__(self, actions=None, choices=None):
        super().__init__(PLAYERS, 23, pieces=[0, 1, 2, 3])
        self.actions = actions or (lambda name, phase, default: default)
        self.choices = choices or {}

    def decide(self, name, phase, prompt, default, **kwargs):
        return super().decide(name, phase, prompt, self.actions(name, phase, default), **kwargs)

    def decide_together(self, phase, decisions, **kwargs):
        decisions = {name: replace(decision, default=self.choices.get((phase, name), decision.default))
                     for name, decision in decisions.items()}
        return super().decide_together(phase, decisions, **kwargs)


class HitStayTest(unittest.TestCase):
    def test_inventory_fresh_decks_and_ten_round_ante(self):
        self.assertEqual(len(DECK), 35)
        self.assertEqual(Counter(DECK), {7: 1, 6: 2, 5: 3, 4: 4, 3: 5, 2: 6, 1: 7, -1: 7})
        self.assertEqual([ante_for(round_number) for round_number in (1, 10, 11, 20, 21)], [1, 1, 2, 2, 3])
        match = Match(PLAYERS, 23)
        for number in (1, 2):
            table = Round(match, PLAYERS, dict.fromkeys(PLAYERS, 30), PLAYERS[0], number)
            self.assertEqual(Counter([*table.deck, *(card for hand in table.hands.values() for card in hand)]),
                             Counter(DECK_COUNTS))
            self.assertEqual(len(table.deck), 23)

    def test_bet_validation_rejects_partial_all_in_and_invalid_targets(self):
        self.assertEqual(parse_bet('{"type":"raise","total":8}', 3, 8), {"type": "raise", "total": 8})
        for action in ([], {}, {"type": "raise", "total": True}, {"type": "raise", "total": 3},
                       {"type": "raise", "total": 9}, {"type": "raise", "total": 4.5},
                       {"type": "call", "total": 5}, {"type": "all_in"}):
            with self.subTest(action=action), self.assertRaises(ValueError):
                parse_bet(json.dumps(action), 3, 8)

    def test_folded_short_stack_stops_capping_and_remaining_all_ins_are_equal(self):
        def action(name, phase, default):
            if phase == "hit_bet1":
                if name == "P01":
                    return '{"type":"fold"}'
                if name == "P02":
                    return '{"type":"raise","total":5}'
            return default
        match = ScriptMatch(action)
        chips = {"P01": 2, "P02": 5, "P03": 5, "P04": 5}
        table = Round(match, PLAYERS, chips, "P01", 1)
        self.assertEqual(effective_cap(chips, table.contributions, table.remaining), 2)
        table.betting("bet1")
        self.assertEqual(table.folded, {"P01"})
        self.assertEqual(table.contributions, {"P01": 1, "P02": 5, "P03": 5, "P04": 5})
        self.assertEqual(chips, {"P01": 1, "P02": 0, "P03": 0, "P04": 0})
        self.assertEqual(table.pot + sum(chips.values()), 17)
        before = len(match.events)
        table.betting("bet2")
        self.assertEqual(len(match.events), before, "An unfolded all-in fixes the cap, so no side pot is possible")

    def test_second_bet_uses_cumulative_contributions_and_only_charges_the_difference(self):
        def action(name, phase, default):
            if phase == "hit_bet1":
                return '{"type":"raise","total":3}' if name == "P01" else '{"type":"call"}'
            if phase == "hit_bet2":
                return '{"type":"raise","total":5}' if name == "P01" else '{"type":"call"}'
            return default
        match = ScriptMatch(action)
        chips = dict.fromkeys(PLAYERS, 5)
        table = Round(match, PLAYERS, chips, "P01", 1)
        table.betting("bet1")
        self.assertEqual(list(chips.values()), [2] * 4)
        table.betting("bet2")
        self.assertEqual(list(chips.values()), [0] * 4)
        self.assertEqual(table.pot, 20)
        self.assertTrue(all(value == 5 for value in table.contributions.values()))

    def test_second_bet_reopens_prior_callers_after_rear_seat_raise_and_reraise(self):
        steps = iter(("call", "call", "call", "raise3", "call", "raise6", "call", "call", "call"))
        turns = []
        def action(name, phase, default):
            if phase != "hit_bet2":
                return default
            turns.append(name)
            step = next(steps)
            return json.dumps({"type": "raise", "total": int(step[5:])} if step.startswith("raise")
                              else {"type": step})
        match = ScriptMatch(action)
        chips = dict.fromkeys(PLAYERS, 10)
        table = Round(match, PLAYERS, chips, "P01", 1)
        table.betting("bet1")
        table.betting("bet2")
        self.assertEqual(turns, ["P01", "P02", "P03", "P04", "P01", "P02", "P03", "P04", "P01"])
        self.assertEqual(table.contributions, dict.fromkeys(PLAYERS, 6))
        self.assertEqual(chips, dict.fromkeys(PLAYERS, 4))
        self.assertEqual(table.pot, 24)
        self.assertEqual(table.pot + sum(chips.values()), 40)

    def test_negative_hits_can_recover_and_stayed_players_are_skipped(self):
        match = ScriptMatch(lambda name, phase, default: (
            "HIT" if name == "P01" else "STAY") if phase == "hit_draw" else default)
        table = Round(match, PLAYERS, dict.fromkeys(PLAYERS, 30), "P01", 1)
        table.limit = table.context["limit"] = 11
        table.hands.update(P01=[5, 5, 3], P02=[5, 5, 1])
        table.folded.update(("P03", "P04"))
        table.deck = [-1, -1]
        table.draw_cards()
        self.assertEqual(sum(table.hands["P01"]), 11)
        cards = [json.loads(event.content) for event in match.events if event.msg_type == "hit_card"]
        self.assertEqual([(card["player"], card["type"]) for card in cards],
                         [("P01", "HIT"), ("P02", "STAY"), ("P01", "HIT")])
        self.assertEqual(len(table.deck), 0)

    def test_valid_sums_card_counts_all_bust_and_remainder_order(self):
        result = settle_round({"P01": [7, 1], "P02": [3, 3, 1, 1], "P03": [7, 3]}, 8, 15, PLAYERS)
        self.assertEqual(result["winners"], ["P02"])
        self.assertEqual(result["payouts"], {"P02": 15})
        result = settle_round({"P01": [7, 4], "P02": [7, 2]}, 8, 5, ["P02", "P01"])
        self.assertEqual(result["reason"], "all_bust")
        self.assertEqual(result["payouts"], {"P02": 3, "P01": 2})
        result = settle_round({name: [3, 3, 2] for name in PLAYERS[:3]}, 8, 11,
                              ["P03", "P01", "P02", "P04"])
        self.assertEqual(result["payouts"], {"P03": 4, "P01": 4, "P02": 3})

    def test_only_the_last_unfolded_player_wins_without_showing_private_cards(self):
        match = ScriptMatch(lambda name, phase, default: '{"type":"fold"}' if (
            phase == "hit_bet1" and name != "P04") else default)
        chips = dict.fromkeys(PLAYERS, 30)
        table = Round(match, PLAYERS, chips, "P01", 1)
        table.play()
        self.assertFalse(any(event.msg_type == "hit_card" for event in match.events))
        showdown = json.loads(match.events[-1].content)
        self.assertEqual(showdown["reason"], "uncontested")
        self.assertEqual(showdown["hands"], {})
        self.assertEqual(chips["P04"], 33)

        match = ScriptMatch(lambda name, phase, default: '{"type":"fold"}' if (
            phase == "hit_bet1" and name == "P01") else default)
        table = Round(match, PLAYERS, dict.fromkeys(PLAYERS, 30), "P01", 1)
        table.play()
        showdown = json.loads(match.events[-1].content)
        self.assertEqual(set(showdown["hands"]), set(PLAYERS[1:]))
        self.assertNotIn("P01", showdown["sums"])

    def test_tied_first_bust_uses_only_tied_lowest_without_moving_any_chips(self):
        match = Match(PLAYERS, 23)
        chips = dict.fromkeys(PLAYERS, 0)
        contests = []
        def contest(match, players, chips, first, number, *, tiebreak):
            contests.append(players)
            hands = ({"P01": [7, 7], "P02": [7, 6], "P03": [5, 5]} if tiebreak == 1
                     else {"P01": [5, 5], "P02": [7, 7]})
            return SimpleNamespace(order=list(players), limit=10, play=lambda: hands)
        with patch(__package__ + ".game.Round", side_effect=contest):
            loser = first_bust_loser(match, list(PLAYERS[:3]), chips, list(PLAYERS), "P01", 1)
        self.assertEqual(loser, "P02")
        self.assertEqual(contests, [["P01", "P02", "P03"], ["P01", "P02"]])
        self.assertEqual(chips, dict.fromkeys(PLAYERS, 0))

    def test_full_match_conserves_chips_and_keeps_first_elimination_separate_from_prison(self):
        for count in (4, 5):
            with self.subTest(count=count):
                players = tuple(f"P{index:02}" for index in range(1, count + 1))
                match = Match(players, 23, pieces=list(range(count)))
                result = play(match)
                self.assertEqual(sum(result["chips"].values()), 40 * count + sum(range(count)))
                self.assertEqual(len(result["eliminated"]), 1)
                self.assertEqual(len(result["prison"]), count - 2)
                self.assertEqual(result["finalists"], result["living"])
                self.assertCountEqual(result["ranking"], players)
                self.assertEqual(result["pieces"], dict.fromkeys(players, 0))
                self.assertEqual(result["pieces_spent"], dict(zip(players, range(count), strict=True)))
                busts = [json.loads(event.content) for event in match.events if event.msg_type == "hit_bust"]
                self.assertTrue(busts)
                self.assertTrue(all(bust["eliminated"] == result["eliminated"] for bust in busts))
                self.assertTrue(all(value == 0 for name, value in result["chips"].items() if name != result["living"][0]))

    def test_simultaneous_first_bust_keeps_prison_ranking_and_skips_zero_seats(self):
        match = Match(PLAYERS, 23)
        starts = []
        def table(match, players, chips, first, number):
            starts.append((first, tuple(players)))
            start = players.index(first)
            def settle():
                total = sum(chips.values())
                if number == 1:
                    chips.update(P01=0, P02=0, P03=total // 4, P04=total - total // 4)
                elif number == 2:
                    chips.update(P03=0, P04=total)
                else:
                    self.fail("The last chip holder should end the match after round two")
                return {}
            return SimpleNamespace(order=players[start:] + players[:start], play=settle)
        with (patch.object(match.rng, "sample", return_value=list(PLAYERS)),
              patch(__package__ + ".game.Round", side_effect=table),
              patch(__package__ + ".game.first_bust_loser", return_value="P02") as overtime):
            result = play(match)
        overtime.assert_called_once()
        self.assertEqual(overtime.call_args.args[1], ["P01", "P02"])
        self.assertEqual(starts, [("P01", PLAYERS), ("P03", PLAYERS[2:])])
        self.assertEqual(result["ranking_groups"], [["P04"], ["P03"], ["P01"], ["P02"]])
        self.assertEqual(result["ranking"], ["P04", "P03", "P01", "P02"])
        self.assertEqual(result["living"], ["P04"])
        self.assertEqual(result["prison"], ["P03", "P01"])
        self.assertEqual(result["eliminated"], ["P02"])
        busts = [json.loads(event.content) for event in match.events if event.msg_type == "hit_bust"]
        self.assertEqual([bust["zero"] for bust in busts], [["P01", "P02"], ["P03"]])
        self.assertEqual(sum(result["chips"].values()), 164)

    def test_interest_is_simultaneous_majority_and_personal_bonus_is_independent(self):
        for public_count, earned in ((2, False), (3, True)):
            choices = {("hit_interest", name): "public" if index < public_count else "personal"
                       for index, name in enumerate(PLAYERS)}
            match = ScriptMatch(choices=choices)
            result = play(match)
            self.assertEqual(result["prize_token"], earned)
            interest = next(json.loads(event.content) for event in match.events if event.msg_type == "hit_interest")
            self.assertEqual(interest["threshold"], 3)
            self.assertEqual(sum(interest["bonuses"].values()), 10 * (4 - public_count))
            self.assertEqual(sum(result["chips"].values()), 126 + 10 * (4 - public_count))

    def test_private_hands_and_reveal_commitments_never_leak_to_other_players(self):
        match = Match(PLAYERS, 23)
        play(match)
        for event in match.events:
            if event.msg_type == "hit_hand":
                data = json.loads(event.content)
                self.assertEqual(event.visible_to, [data["player"]])
                self.assertEqual(len(data["cards"]), 3)
            elif event.msg_type == "action" and json.loads(event.content)["phase"] in {"hit_reveal", "hit_interest"}:
                self.assertEqual(event.visible_to, [event.agent_name])
            elif event.msg_type.startswith("hit_") and event.visible_to == "all":
                data = json.loads(event.content)
                if "hands" in data:
                    self.assertEqual(event.msg_type, "hit_showdown")
        for player in PLAYERS:
            self.assertFalse(any(event.msg_type == "hit_hand" and json.loads(event.content)["player"] != player
                                 for event in match.observations(player)))
        reveals = [event for event in match.events if event.msg_type == "hit_reveal"]
        for reveal in reveals:
            data = json.loads(reveal.content)
            preceding = [event for event in match.events[:reveal.turn] if event.msg_type == "action"
                         and json.loads(event.content)["phase"] == "hit_reveal"]
            self.assertGreaterEqual(len(preceding), len(data["players"]))
            self.assertTrue(all(count == 2 for count in data["hidden_counts"].values()))

    def test_model_decisions_resume_to_identical_private_and_public_events(self):
        original_event = Match.event
        with (TemporaryDirectory() as directory, redirect_stdout(StringIO()), redirect_stderr(StringIO()),
              patch("games.models.CodexLanguageModel._complete", return_value='{"action":"{}","note":""}')):
            full = Path(directory) / "full.jsonl"
            args = ["--seed", "23", "--model", "test-model", "--model-player", "P01",
                    "--model-turns", "25", "--no-allow-review"]
            run_cli(play, title=TITLE, seats=4, argv=[*args, "--output", str(full)])
            expected = [json.loads(line) for line in full.read_bytes().splitlines()]
            for checkpoint in ("hit_hand", "hit_bet", "hit_card"):
                with self.subTest(checkpoint=checkpoint):
                    resumed = Path(directory) / f"{checkpoint}.jsonl"
                    def interrupt(match, kind, data, **kwargs):
                        original_event(match, kind, data, **kwargs)
                        if kind == checkpoint:
                            raise RuntimeError("committed HIT, STAY interruption")
                    with patch.object(Match, "event", interrupt), self.assertRaisesRegex(RuntimeError, "committed HIT"):
                        run_cli(play, title=TITLE, seats=4, argv=[*args, "--output", str(resumed)])
                    run_cli(play, title=TITLE, seats=4, argv=["--resume", "--output", str(resumed)])
                    self.assertEqual([json.loads(line) for line in resumed.read_bytes().splitlines()], expected)


if __name__ == "__main__":
    unittest.main()
