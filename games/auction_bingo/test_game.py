"""Auction, hidden-information and resumption checks for Auction Bingo."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from io import StringIO
from itertools import product
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from ..match import Match, run_cli
from ..models import OpenAILanguageModel, StrategyNote
from .game import BOARD, INITIAL_COINS, SHAPES, coin_value, optimal_board, parse_bid, play, settle_round


PLAYERS = tuple(f"P{seat:02}" for seat in range(1, 8)) + ("G01",)
PASS = '{"type":"pass","note":"확인한 정보에 따라 계획을 검토한다."}'


class DiscussionMatch(Match):
    """Exercise the normal validators and journal with deterministic model replies."""

    def __init__(self, reply):
        super().__init__(PLAYERS, 0, model=OpenAILanguageModel("test-model", Mock()),
                         live_players=PLAYERS, live_turns=2000)
        self.reply = reply
        self.batches = []

    def request_action(self, name, phase, prompt, default, **kwargs):
        self.phase, self.defaults = phase, {name: default}
        return super().request_action(name, phase, prompt, default, **kwargs)

    def decide_together(self, phase, decisions, **kwargs):
        self.phase, self.defaults = phase, {name: decision.default for name, decision in decisions.items()}
        self.batches.append((phase, tuple(decisions)))
        return super().decide_together(phase, decisions, **kwargs)

    def _query(self, name, prompt, *args, **kwargs):
        return self.reply(self, name, prompt), StrategyNote()

    def review_relationships(self, checkpoint):
        pass


class AuctionBingoTest(unittest.TestCase):
    def test_saved_rules_keep_the_old_discussion_and_submission_order(self):
        rules = "경매 빙고 · 저장된 규칙\n시작 전 12턴, 매 라운드 최대 4턴, 대화 후 동시 제출."
        match = Match(PLAYERS, 1)
        match.resume_log = SimpleNamespace(resume=True, events=[{"msg_type": "rules", "content": rules}])
        play(match)
        self.assertEqual(match.events[0].content, rules)
        discussions = [json.loads(event.content) for event in match.events if event.msg_type == "bingo_discussion"]
        self.assertEqual(discussions[0]["rounds"], 12)
        self.assertTrue(all(event["rounds"] == 4 for event in discussions[1:]))
        self.assertFalse(any(event.msg_type == "bingo_submission" for event in match.events))
        end = next(event.turn for event in match.events if event.msg_type == "bingo_discussion_end"
                   and json.loads(event.content)["stage"] == "before_bid")
        bid = next(event.turn for event in match.events if event.msg_type == "action"
                   and json.loads(event.content)["phase"] == "bingo_bid")
        self.assertLess(end, bid)

    def test_bid_parser_uses_real_denominations_and_piece_balance(self):
        coins = INITIAL_COINS.copy()
        used, pieces = parse_bid('{"coins":{"1":2,"3":1},"pieces":2}', coins, 3)
        self.assertEqual({value: used.get(value, 0) for value in INITIAL_COINS},
                         {1: 2, 2: 0, 3: 1, 5: 0, 10: 0})
        self.assertEqual(pieces, 2)
        self.assertEqual(coin_value(used), 5)
        self.assertEqual(coins, INITIAL_COINS)
        self.assertEqual(coin_value(INITIAL_COINS), 30)
        used, pieces = parse_bid('{"coins":{"1":1},"pieces":1}', coins, 1)
        self.assertEqual(coin_value(used), 1)
        self.assertEqual(pieces, 1)
        used, pieces = parse_bid('{"coins":{"1":5},"pieces":2}', coins, 2)
        self.assertEqual(used[1], 5)
        self.assertEqual(pieces, 2)

        invalid = [
            [], None, True, {"coins": [], "pieces": 1},
            {"coins": {"1": True}, "pieces": 0},
            {"coins": {"1": 1.5}, "pieces": 0},
            {"coins": {"1": -1}, "pieces": 2},
            {"coins": {"1": 4}, "pieces": 0},
            {"coins": {"4": 1}, "pieces": 0},
            {"coins": {}, "pieces": True},
            {"coins": {}, "pieces": 1.5},
            {"coins": {}, "pieces": -1},
            {"coins": {}, "pieces": 4},
            {"coins": {}, "pieces": 0},
            {"coins": {}, "pieces": 1},
            {"coins": {"1": 6}, "pieces": 2},
            {"coins": {"1": 1}, "pieces": 0, "other": 1},
        ]
        for action in invalid:
            with self.subTest(action=action), self.assertRaises(ValueError):
                parse_bid(json.dumps(action), coins, 3)
        with self.assertRaises(ValueError):
            parse_bid('{"coins":{"1":1},"pieces":0}', {1: 0, 2: 0, 3: 0, 5: 0, 10: 1}, 0)

    def test_full_match_keeps_bids_and_awards_hidden_then_rewards_the_guest(self):
        class GuestWinsMatch(Match):
            round_number = 0

            def event(self, kind, data, **kwargs):
                if kind == "bingo_round":
                    self.round_number = data["round"]
                super().event(kind, data, **kwargs)

            def decide_together(self, phase, decisions, **kwargs):
                if phase == "bingo_shape":
                    shape = ("circle", "triangle", "star")[(self.round_number - 1) % 3]
                    decisions = {name: replace(decision, default=shape) for name, decision in decisions.items()}
                elif phase == "bingo_bid":
                    rewritten = {}
                    for name, decision in decisions.items():
                        value = ((10, 5, 3, 1, 1, 1, 2) if name == "G01" else (1, 1, 1, 2, 2, 2, 3))[self.round_number - 1]
                        action = {"coins": {str(value): 1},
                                  "pieces": 2 if name == "P01" and self.round_number == 1 else 0}
                        rewritten[name] = replace(decision, default=json.dumps(action))
                    decisions = rewritten
                return super().decide_together(phase, decisions, **kwargs)

        initial_pieces = {name: 1 if name == "G01" else 3 for name in PLAYERS}
        match = GuestWinsMatch(PLAYERS, 0, pieces=list(initial_pieces.values()))
        result = play(match)
        reveal = next(event for event in match.events if event.msg_type == "bingo_reveal")
        data = json.loads(reveal.content)
        self.assertEqual(reveal.visible_to, "all")
        self.assertEqual(len(data["rounds"]), 7)
        private_bids = {round_number: {} for round_number in range(1, 8)}
        current_round = 0
        for event in match.events:
            if event.msg_type == "bingo_round":
                current_round = json.loads(event.content)["round"]
            elif event.msg_type == "action":
                action = json.loads(event.content)
                if action["phase"] == "bingo_bid":
                    self.assertEqual(event.visible_to, [event.agent_name])
                    private_bids[current_round][event.agent_name] = json.loads(action["action"])
        wallets = {name: INITIAL_COINS.copy() for name in PLAYERS}
        pieces = initial_pieces.copy()
        acquired = {name: dict.fromkeys(SHAPES, 0) for name in PLAYERS}
        for round_data in data["rounds"]:
            self.assertEqual(set(round_data), {"round", "choices", "counts", "prices", "secret"})
            details = private_bids[round_data["round"]]
            self.assertCountEqual(details, PLAYERS)
            bids = {name: coin_value(bid["coins"]) for name, bid in details.items()}
            settlement = settle_round(round_data["choices"], bids)
            self.assertEqual(round_data["prices"], settlement["prices"])
            self.assertEqual(round_data["secret"], settlement["secret"])
            self.assertEqual(round_data["counts"], settlement["counts"])
            self.assertEqual(sum(settlement["awards"].values()) + sum(settlement["discarded"].values()), 8)
            for name in PLAYERS:
                bid = details[name]
                exchanged = bid["pieces"]
                pieces[name] -= exchanged
                wallets[name][1] += exchanged
                for value, count in bid["coins"].items():
                    wallets[name][int(value)] -= count
                self.assertTrue(all(count >= 0 for count in wallets[name].values()))
                acquired[name][round_data["choices"][name]] += settlement["awards"][name]

        self.assertEqual(result["coins"], wallets)
        self.assertEqual(result["shapes"], acquired)
        self.assertEqual(result["remaining_value"], {name: coin_value(wallet) for name, wallet in wallets.items()})
        self.assertEqual(result["remaining_value"]["P01"], 20)
        self.assertEqual(wallets["P01"][1], 2, "Exchanged but unspent one-won coins remain in the wallet")
        self.assertEqual(result["pieces_spent"]["P01"], 2)
        self.assertEqual(result["ranking"][0], "P01")
        self.assertEqual(result["all_ranking"][0], "G01")
        self.assertEqual(result["guest_result"], {"player": "G01", "rank": 1, "first": True,
                                                 "full_board": True, "prize_won": 20_000_000})
        self.assertEqual(result["scores"]["G01"], 8)
        self.assertEqual(result["filled"]["G01"], 9)
        self.assertEqual(result["pieces_awarded"]["G01"], 4)
        self.assertEqual(result["pieces"], {name: amount + (4 if name == "G01" else 0)
                                            for name, amount in pieces.items()})
        self.assertCountEqual(result["ranking"], PLAYERS[:-1])
        self.assertEqual((len(result["living"]), len(result["prison"]), len(result["eliminated"])), (3, 3, 1))
        self.assertCountEqual(result["living"] + result["prison"] + result["eliminated"], PLAYERS[:-1])

        public_results = [event for event in match.events if event.msg_type == "bingo_result"]
        self.assertEqual(len(public_results), 7)
        for event in public_results:
            public = json.loads(event.content)
            self.assertEqual(set(public), {"round", "counts", "prices", "secret"})
            self.assertEqual(event.visible_to, "all")
            self.assertTrue(all(public["prices"][shape] is None for shape in public["secret"]))
            self.assertLess(event.turn, reveal.turn)
        for event in match.events[:reveal.turn]:
            if event.msg_type == "bingo_bank" or (event.msg_type == "action" and
                    json.loads(event.content)["phase"] in {"bingo_shape", "bingo_bid"}):
                self.assertEqual(event.visible_to, [event.agent_name])
                for other in PLAYERS:
                    if other != event.agent_name:
                        self.assertNotIn(event, match.observations(other))
            if event.msg_type.startswith("bingo_"):
                content = json.loads(event.content)
                self.assertTrue({"winners", "awards", "bid_details", "boards", "all_ranking"}.isdisjoint(content),
                                "No participant receives the actual allocation before the final reveal")

    def test_final_ties_use_coin_value_instead_of_the_number_of_coins(self):
        class SameValueMatch(Match):
            round_number = 0

            def event(self, kind, data, **kwargs):
                if kind == "bingo_round":
                    self.round_number = data["round"]
                super().event(kind, data, **kwargs)

            def decide_together(self, phase, decisions, **kwargs):
                if phase == "bingo_shape":
                    decisions = {name: replace(decision, default="triangle") for name, decision in decisions.items()}
                elif phase == "bingo_bid":
                    value = (3, 2, 2, 2, 3, 5, 10)[self.round_number - 1]
                    decisions = {
                        name: replace(decision, default=json.dumps({
                            "coins": {"1": 3} if self.round_number == 1 and name == "P01" else {str(value): 1},
                            "pieces": 0,
                        })) for name, decision in decisions.items()
                    }
                return super().decide_together(phase, decisions, **kwargs)

        match = SameValueMatch(PLAYERS, 0)
        result = play(match)
        order = next(json.loads(event.content)["base_order"] for event in match.events if event.msg_type == "bingo_setup")
        self.assertEqual(set(result["scores"].values()), {0})
        self.assertEqual(set(result["filled"].values()), {3})
        self.assertEqual(set(result["remaining_value"].values()), {3})
        self.assertEqual(sum(result["coins"]["P01"].values()), 1)
        self.assertEqual(sum(result["coins"]["P02"].values()), 3)
        self.assertEqual(result["all_ranking"], order)
        self.assertEqual(result["ranking"], [name for name in order if name != "G01"])

    def test_missing_a_later_minimum_bid_overrides_an_already_complete_board(self):
        class ExhaustedMatch(Match):
            round_number = 0

            def event(self, kind, data, **kwargs):
                if kind == "bingo_round":
                    self.round_number = data["round"]
                super().event(kind, data, **kwargs)

            def decide_together(self, phase, decisions, **kwargs):
                if phase == "bingo_shape":
                    shape = ("circle", "triangle", "star")[(self.round_number - 1) % 3]
                    decisions = {name: replace(decision, default=shape) for name, decision in decisions.items()}
                elif phase == "bingo_bid" and "P01" in decisions:
                    coins = ({"10": 1}, {"5": 1, "3": 1}, {"3": 1, "2": 3, "1": 3})[self.round_number - 1]
                    decisions = {**decisions, "P01": replace(decisions["P01"], default=json.dumps({"coins": coins, "pieces": 0}))}
                return super().decide_together(phase, decisions, **kwargs)

        match = ExhaustedMatch(PLAYERS, 0, pieces=[0, 1, 1, 1, 1, 1, 1, 1])
        result = play(match)
        self.assertEqual(result["scores"]["P01"], 8)
        self.assertEqual(result["filled"]["P01"], 9)
        self.assertEqual(result["remaining_value"]["P01"], 0)
        self.assertEqual(result["forced_last"], ["P01"])
        self.assertEqual(result["ranking"][-1], "P01")
        self.assertEqual(result["eliminated"], ["P01"])
        forfeits = [json.loads(event.content) for event in match.events if event.msg_type == "bingo_forfeit"]
        self.assertEqual(forfeits, [{"round": round_number, "player": "P01"} for round_number in range(4, 8)])

    def test_highest_bidders_split_the_pool_and_all_maximum_shapes_are_secret(self):
        choices = {name: "triangle" if index < 5 else "circle" if index < 7 else "star"
                   for index, name in enumerate(PLAYERS)}
        bids = dict(zip(PLAYERS, (5, 5, 1, 2, 3, 5, 5, 3), strict=True))
        result = settle_round(choices, bids)
        self.assertEqual(result["counts"], {"triangle": 5, "circle": 2, "star": 1})
        self.assertEqual(result["prices"], {"triangle": 5, "circle": 5, "star": 3})
        self.assertEqual(set(result["secret"]), {"triangle", "circle"})
        self.assertEqual(result["winners"]["triangle"], ["P01", "P02"])
        self.assertEqual(result["winners"]["circle"], ["P06", "P07"])
        self.assertEqual(result["winners"]["star"], ["G01"])
        self.assertEqual({name: result["awards"].get(name, 0) for name in PLAYERS},
                         dict(zip(PLAYERS, (2, 2, 0, 0, 0, 1, 1, 1), strict=True)))
        self.assertEqual(result["discarded"], {"triangle": 1, "circle": 0, "star": 0})

        result = settle_round({"P01": "triangle", "P02": "circle", "G01": "star"},
                              {"P01": 2, "P02": 2, "G01": 2})
        self.assertEqual(set(result["secret"]), set(SHAPES))
        result = settle_round({"P01": "triangle"}, {"P01": 1})
        self.assertIsNone(result["prices"]["circle"])
        self.assertIsNone(result["prices"]["star"])
        self.assertEqual(set(result["secret"]), {"triangle"})

    def test_optimal_placement_matches_every_possible_three_by_three_board(self):
        flat = tuple(shape for row in BOARD for shape in row)
        lines = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7),
                 (2, 5, 8), (0, 4, 8), (2, 4, 6)]
        oracle = {}
        for mask in range(1 << 9):
            counts = tuple(sum(bool(mask & (1 << index)) and shape == candidate
                               for index, shape in enumerate(flat)) for candidate in SHAPES)
            completed = sum(all(mask & (1 << index) for index in line) for line in lines)
            oracle[counts] = max(oracle.get(counts, 0), completed)
        capacities = tuple(flat.count(shape) for shape in SHAPES)
        for counts in product(*(range(capacity + 1) for capacity in capacities)):
            with self.subTest(counts=counts):
                result = optimal_board(dict(zip(SHAPES, counts, strict=True)))
                board = tuple(shape for row in result["board"] for shape in row)
                self.assertEqual(len(board), 9)
                self.assertTrue(all(shape is None or shape == flat[index]
                                    for index, shape in enumerate(board)))
                self.assertEqual(tuple(board.count(shape) for shape in SHAPES), counts)
                self.assertEqual(result["filled"], sum(counts))
                self.assertEqual(result["lines"], oracle[counts])
        full = optimal_board(dict.fromkeys(SHAPES, 100))
        self.assertEqual(full["filled"], 9)
        self.assertEqual(full["lines"], 8)

    def test_roster_requires_seven_regular_players_and_one_guest(self):
        for players in (PLAYERS[:-1], tuple(f"P{seat:02}" for seat in range(1, 9)),
                        (*PLAYERS, "P08")):
            with self.subTest(players=players), self.assertRaises(ValueError):
                play(Match(players, 11))

    def test_all_players_can_submit_during_first_talk_turn_without_another_batch(self):
        testcase = self

        def reply(match, name, prompt):
            if match.phase != "bingo_discussion":
                return match.defaults[name]
            context = next(json.loads(event.content) for event in reversed(match.events)
                           if event.msg_type == "bingo_discussion_round")
            if context["stage"] == "opening":
                return PASS
            for event in match.observations(name):
                if event.msg_type == "action" and json.loads(event.content)["phase"] in {"bingo_shape", "bingo_bid"}:
                    testcase.assertEqual(event.agent_name, name)
            if context["stage"] == "before_shape":
                testcase.assertFalse(any(event.msg_type == "bingo_shapes" and
                                          json.loads(event.content)["round"] == context["round"]
                                          for event in match.events))
                choice = "triangle"
            else:
                value = 1 if context["round"] <= 3 else 2 if context["round"] <= 6 else 3
                choice = json.dumps({"coins": {str(value): 1}, "pieces": 0})
            return json.dumps({"type": "submit", "choice": choice, "note": "확정한 선택을 유지한다."})

        match = DiscussionMatch(reply)
        result = play(match)
        rules = next(event.content for event in match.events if event.msg_type == "rules")
        self.assertIn("\n\n6. 자유 제출\n", rules)
        talks = [json.loads(event.content) for event in match.events if event.msg_type == "bingo_discussion_round"]
        self.assertEqual([talk["turn"] for talk in talks if talk["stage"] == "opening"], list(range(1, 11)))
        self.assertEqual(len([talk for talk in talks if talk["stage"] != "opening"]), 14)
        self.assertTrue(all(talk["turn"] == 1 and talk["rounds"] == 6 for talk in talks if talk["stage"] != "opening"))
        endings = [json.loads(event.content) for event in match.events if event.msg_type == "bingo_discussion_end"]
        self.assertTrue(all(ending["reason"] == "all_submitted" for ending in endings if ending["stage"] != "opening"))
        self.assertFalse(any(phase in {"bingo_shape", "bingo_bid"} and players for phase, players in match.batches))
        progress = [event for event in match.events if event.msg_type == "bingo_submission"]
        self.assertEqual(len(progress), 8 * 2 * 7)
        for round_number in range(1, 8):
            for phase in ("shape", "bid"):
                group = [json.loads(event.content) for event in progress
                         if json.loads(event.content)["round"] == round_number and json.loads(event.content)["phase"] == phase]
                self.assertEqual([len(item["submitted"]) for item in group], list(range(1, 9)))
                self.assertEqual(set(group[-1]["submitted"]), set(PLAYERS))
                self.assertTrue(all(set(item) == {"round", "phase", "player", "submitted", "total"} and item["total"] == 8
                                    for item in group))
        self.assertTrue(all(event.visible_to == "all" for event in progress))
        self.assertTrue(all(counts == {"triangle": 7, "circle": 0, "star": 0} for counts in result["shapes"].values()))

    def test_partial_submissions_are_irreversible_and_only_pending_players_finish_at_six_turns(self):
        testcase = self

        class FirstRoundComplete(Exception):
            pass

        class PartialMatch(DiscussionMatch):
            def event(self, kind, data, **kwargs):
                super().event(kind, data, **kwargs)
                if kind == "bingo_result":
                    raise FirstRoundComplete

        def reply(match, name, prompt):
            if match.phase != "bingo_discussion":
                return match.defaults[name]
            context = next(json.loads(event.content) for event in reversed(match.events)
                           if event.msg_type == "bingo_discussion_round")
            if context["stage"] == "opening":
                return PASS
            if name == "P01":
                if context["stage"] == "before_bid" and context["turn"] == 2:
                    bank = next(event for event in reversed(match.events)
                                if event.msg_type == "bingo_bank" and event.agent_name == name)
                    testcase.assertEqual(json.loads(bank.content)["coins"]["1"], 2)
                    testcase.assertIn('"1":2', prompt)
                if context["turn"] <= 2:
                    choice = ("triangle" if context["turn"] == 1 else "circle") if context["stage"] == "before_shape" else json.dumps({
                        "coins": {"1" if context["turn"] == 1 else "2": 1}, "pieces": 0,
                    })
                    return json.dumps({"type": "submit", "choice": choice, "note": "입장을 확정한다."})
                if context["turn"] == 3:
                    return json.dumps({"type": "speak", "channel": "public", "text": "제출 후에도 협상을 계속한다.",
                                       "note": "이미 확정한 선택을 유지하며 대화한다."})
                return PASS
            return json.dumps({"type": "speak", "channel": "public", "text": "아직 선택을 검토하고 있다.",
                               "note": "상대의 약속을 추가로 확인한 뒤 제출한다."})

        match = PartialMatch(reply)
        with self.assertRaises(FirstRoundComplete):
            play(match)
        for stage in ("before_shape", "before_bid"):
            turns = [json.loads(event.content)["turn"] for event in match.events
                     if event.msg_type == "bingo_discussion_round" and json.loads(event.content)["stage"] == stage]
            self.assertEqual(turns, list(range(1, 7)))
            ended = next(json.loads(event.content) for event in match.events
                         if event.msg_type == "bingo_discussion_end" and json.loads(event.content)["stage"] == stage)
            self.assertEqual(ended["reason"], "limit")
        batches = [(phase, players) for phase, players in match.batches if phase in {"bingo_shape", "bingo_bid"}]
        self.assertEqual([phase for phase, _ in batches], ["bingo_shape", "bingo_bid"])
        self.assertTrue(all(set(players) == set(PLAYERS) - {"P01"} for _, players in batches))
        actions = [json.loads(event.content) for event in match.events if event.msg_type == "action" and event.agent_name == "P01"]
        self.assertEqual([action["action"] for action in actions if action["phase"] == "bingo_shape"], ["triangle"])
        bids = [json.loads(action["action"]) for action in actions if action["phase"] == "bingo_bid"]
        self.assertEqual(bids, [{"coins": {"1": 1}, "pieces": 0}])
        banks = [json.loads(event.content) for event in match.events if event.msg_type == "bingo_bank" and event.agent_name == "P01"]
        self.assertEqual(len(banks), 1)
        self.assertEqual(banks[0]["coins"]["1"], 2)
        invalid = [event for event in match.events if event.msg_type == "invalid_action"]
        self.assertEqual(len(invalid), 2)
        self.assertTrue(all(event.visible_to == ["P01"] and json.loads(event.content)["phase"] == "bingo_discussion" for event in invalid))
        progress = [json.loads(event.content) for event in match.events if event.msg_type == "bingo_submission" and
                    json.loads(event.content)["player"] == "P01"]
        self.assertEqual([item["phase"] for item in progress], ["shape", "bid"])
        self.assertEqual(sum(event.msg_type == "public" and event.agent_name == "P01" and
                             event.content == "제출 후에도 협상을 계속한다." for event in match.events), 2)

    def test_bidder_returns_to_the_hall_before_progress_and_uses_hall_speech_permissions(self):
        class FirstRoundComplete(Exception):
            pass

        class HallExitMatch(DiscussionMatch):
            def event(self, kind, data, **kwargs):
                super().event(kind, data, **kwargs)
                if kind == "rules":
                    self.resume_log = None  # Only the game's recorded-rule selection needs this stub.
                elif kind == "bingo_result":
                    raise FirstRoundComplete

        probe = Match(PLAYERS, 0)
        play(probe)
        rules = next(event.content for event in probe.events if event.msg_type == "rules")
        heading = "\n\n7. 딜러룸 입찰\n"
        self.assertIn(heading, rules)
        old_rules = rules.split(heading)[0]
        self.assertIn("\n\n6. 자유 제출\n", old_rules)
        testcase = self

        for hall_exit in (True, False):
            with self.subTest(hall_exit=hall_exit):
                def reply(match, name, prompt):
                    if match.phase != "bingo_discussion":
                        return match.defaults[name]
                    context = next(json.loads(event.content) for event in reversed(match.events)
                                   if event.msg_type == "bingo_discussion_round")
                    if context["stage"] == "opening":
                        return json.dumps({"type": "move", "room": 1, "note": "논의실에서 대화를 준비한다."}) if (
                            context["turn"] == 1 and name in {"P01", "P03"}) else PASS
                    if context["stage"] != "before_bid":
                        return PASS
                    if name == "P01":
                        if context["turn"] == 1:
                            testcase.assertIn("현재 위치 1번 논의실", prompt)
                            return json.dumps({"type": "submit", "choice": '{"coins":{"1":1},"pieces":0}',
                                               "note": "입찰을 확정한다."})
                        testcase.assertIn("현재 위치 복도" if hall_exit else "현재 위치 1번 논의실", prompt)
                        if context["turn"] in {2, 3}:
                            target = "P02" if context["turn"] == 2 else "P03"
                            return json.dumps({"type": "speak", "channel": "whisper", "to": target,
                                               "text": "복도 귓속말" if target == "P02" else "논의실 귓속말",
                                               "note": "현재 같은 장소의 상대에게만 이야기한다."})
                        if context["turn"] == 4:
                            return json.dumps({"type": "speak", "channel": "room", "text": "논의실 발언",
                                               "note": "현재 논의실의 참가자와 이야기한다."})
                        return PASS
                    return json.dumps({"type": "speak", "channel": "public", "text": "협상을 계속한다.",
                                       "note": "남은 선택지를 검토한다."})

                match = HallExitMatch(reply)
                if not hall_exit:
                    match.resume_log = SimpleNamespace(resume=True, events=[{"msg_type": "rules", "content": old_rules}])
                with self.assertRaises(FirstRoundComplete):
                    play(match)
                actual_rules = next(event.content for event in match.events if event.msg_type == "rules")
                self.assertEqual(actual_rules, rules if hall_exit else old_rules)
                bank = [event for event in match.events if event.msg_type == "bingo_bank" and event.agent_name == "P01"]
                self.assertEqual(len(bank), 1)
                self.assertEqual(json.loads(bank[0].content)["coins"]["1"], 2)
                progress = next(event for event in match.events if event.msg_type == "bingo_submission" and
                                json.loads(event.content)["phase"] == "bid" and json.loads(event.content)["player"] == "P01")
                moves = [event for event in match.events if event.msg_type == "room_move" and event.agent_name == "P01"
                         and event.content == "P01 → 복도"]
                self.assertEqual(len(moves), int(hall_exit))
                if hall_exit:
                    self.assertEqual(moves[0].visible_to, "all")
                    self.assertLess(bank[0].turn, moves[0].turn)
                    self.assertLess(moves[0].turn, progress.turn)
                whispers = [event for event in match.events if event.msg_type == "whisper" and event.agent_name == "P01"]
                self.assertEqual([event.content for event in whispers], ["복도 귓속말" if hall_exit else "논의실 귓속말"])
                self.assertEqual(whispers[0].visible_to, ["P01", "P02" if hall_exit else "P03"])
                room_speech = [event for event in match.events if event.msg_type == "room" and event.agent_name == "P01"]
                self.assertEqual(len(room_speech), int(not hall_exit))
                invalid = [event for event in match.events if event.msg_type == "invalid_action"]
                self.assertEqual(len(invalid), 2 if hall_exit else 1)
                self.assertTrue(all(event.visible_to == ["P01"] for event in invalid))
                self.assertFalse(any("5번" in event.content for event in match.events if event.msg_type == "room_move"))

    def test_interrupted_private_bid_and_settlement_resume_to_identical_record(self):
        title = "4일차 메인 매치 · 경매 빙고"
        original_event = Match.event

        def reply(prompt):
            exercise = prompt.rsplit("Exercise:", 1)[-1]
            if "비공개 관계 평가를 갱신하세요" in prompt:
                action = "{}"
            elif "나는 아직 제출하지 않았습니다." in exercise:
                action = next(line.strip() for line in exercise.splitlines()
                              if line.strip().startswith('{"type":"submit"'))
            elif "경기 시작 전 협상입니다." in exercise and "대화 1/10턴" in exercise:
                action = '{"type":"move","room":1,"note":"논의실에서 협상을 준비한다."}'
            else:
                action = PASS
            return json.dumps({"action": action, "note": "비공개 테스트 전략"}, ensure_ascii=False)

        with (TemporaryDirectory() as directory, redirect_stdout(StringIO()), redirect_stderr(StringIO()),
              patch("games.models.CodexLanguageModel._complete", side_effect=reply) as completion):
            arguments = ["--players", *PLAYERS[:-1], "--pieces", *(["3"] * 7), "--seed", "19",
                         "--model", "test-model", "--model-player", "P01", "--model-turns", "300",
                         "--no-allow-review"]
            full = Path(directory) / "full.jsonl"
            run_cli(play, title=title, seats=7, guest="G01", argv=[*arguments, "--output", str(full)])
            expected = [json.loads(line) for line in full.read_bytes().splitlines()]
            self.assertEqual(expected[0]["players"], list(PLAYERS))
            self.assertNotIn("G01", expected[-1]["ranking"])
            for checkpoint in ("bingo_setup", "bid_action", "bingo_bank", "hall_exit", "bingo_result", "bingo_reveal"):
                with self.subTest(checkpoint=checkpoint):
                    resumed = Path(directory) / f"resumed-{checkpoint}.jsonl"

                    def interrupt(match, kind, data, **kwargs):
                        original_event(match, kind, data, **kwargs)
                        if checkpoint == "bid_action":
                            reached = kind == "action" and data.get("phase") == "bingo_bid"
                        elif checkpoint == "hall_exit":
                            reached = kind == "room_move" and data == "P01 → 복도"
                        else:
                            reached = kind == checkpoint
                        if checkpoint == "bingo_result":
                            reached = reached and data["round"] == 2
                        if reached:
                            raise RuntimeError("test interruption after committed event")

                    with patch.object(Match, "event", interrupt):
                        with self.assertRaisesRegex(RuntimeError, "committed event"):
                            run_cli(play, title=title, seats=7, guest="G01",
                                    argv=[*arguments, "--output", str(resumed)])
                    prefix = [json.loads(line) for line in resumed.read_bytes().splitlines()]
                    self.assertEqual(prefix[-1]["type"], "interrupted")
                    calls_before = completion.call_count
                    run_cli(play, title=title, seats=7, guest="G01",
                            argv=["--resume", "--output", str(resumed)])
                    actual = [json.loads(line) for line in resumed.read_bytes().splitlines()]
                    self.assertEqual(actual, expected)
                    self.assertEqual(actual[:len(prefix) - 1], prefix[:-1])
                    self.assertEqual(completion.call_count - calls_before,
                                     expected[-1]["model_calls"] - prefix[-1]["model_calls"])


if __name__ == "__main__":
    unittest.main()
