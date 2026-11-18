"""Regression checks for the hidden-card match and deterministic resumption."""

from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from ..match import DAY_THREE_MAIN, Match, run_cli
from ..models import OpenAILanguageModel, STRATEGY_NOTE_LIMIT, StrategyNote
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
                elimination_count = count - 8
                self.assertEqual(result["eliminated"], ranking[-elimination_count:])
                self.assertEqual(result["living"][-1], result["alliance_saved"])
                self.assertIn(result["alliance_saved"], ranking[3:-elimination_count])
                self.assertEqual(set(result["prison"]), set(ranking[3:-elimination_count]) - {result["alliance_saved"]})
                self.assertEqual(len(result["prison"]), 4)
                rules = next(event.content for event in match.events if event.msg_type == "rules")
                self.assertIn(f"최하위 {'두' if count == 10 else '한'} 명은 탈락", rules)
                self.assertEqual(len(result["living"]) + len(result["prison"]) + len(result["eliminated"]), count)
                self.assertEqual(set(result["living"]) | set(result["prison"]) | set(result["eliminated"]), set(players))
                for player in players:
                    reward = (result["scores"][player] >= 1) + (result["scores"][player] >= 10)
                    self.assertEqual(result["pieces_awarded"][player], diamond_rewards[player] + reward)
                    spent = peeks[player] + (auction["bid"] if player == auction["leader"] else 0)
                    self.assertEqual(result["pieces_spent"][player], spent)
                    self.assertEqual(result["pieces"][player], initial[player] + diamond_rewards[player] + reward - spent)
                    self.assertGreaterEqual(result["pieces"][player], 0)

    def test_private_preparation_chains_and_remains_available_during_opening(self):
        testcase = self
        players = tuple(f"P{index:02}" for index in range(1, 10))
        preparation_prompts = {name: [] for name in players}
        opening_prompts = {name: [] for name in players}

        class OpeningComplete(Exception):
            pass

        class PreparationMatch(Match):
            def event(self, kind, data, **kwargs):
                super().event(kind, data, **kwargs)
                if kind == "gem_auction_round":
                    raise OpeningComplete

        def plan(name, turn):
            return f"PRIVATE_{name}_PREPARATION_{turn}_ONLY"

        def respond(name, **kwargs):
            prompt = kwargs["input"][0]["content"][0]["text"]
            if "비공개 관계 평가를 갱신하세요" in prompt:
                action = "{}"
            elif not any(event.msg_type == "gem_preparation_end" for event in match.events):
                turn = next(json.loads(event.content)["turn"] for event in reversed(match.events)
                            if event.msg_type == "gem_preparation")
                preparation_prompts[name].append(prompt)
                if turn > 1:
                    testcase.assertIn(plan(name, turn - 1), prompt)
                testcase.assertFalse(any(event.msg_type in {"gem_manito", "gem_card", "gem_round"}
                                         for event in match.observations(name)))
                action = plan(name, turn)
            else:
                opening_prompts[name].append(prompt)
                testcase.assertIn(plan(name, 3), prompt)
                action = json.dumps({"type": "speak", "channel": "public", "text": f"{name}의 공개 협력 제안"})
            for other in players:
                if other != name:
                    for turn in range(1, 4):
                        testcase.assertNotIn(plan(other, turn), prompt)
            output = json.dumps({"action": action, "note": ""})
            return SimpleNamespace(status="completed", output_text=output, usage=None)

        models = {}
        for name in players:
            client = Mock()
            client.responses.create.side_effect = lambda owner=name, **kwargs: respond(owner, **kwargs)
            models[name] = OpenAILanguageModel("test-model", client)
        match = PreparationMatch(players, 8, pieces=[3] * 9, models=models, live_turns=1000)
        with self.assertRaises(OpeningComplete):
            play(match)
        stages = [event for event in match.events if event.msg_type == "gem_preparation"]
        self.assertEqual([json.loads(event.content) for event in stages],
                         [{"turn": turn, "turns": 3} for turn in range(1, 4)])
        self.assertTrue(all(event.visible_to == "all" for event in stages))
        preparation_end = next(event for event in match.events if event.msg_type == "gem_preparation_end")
        opening = next(event for event in match.events if event.msg_type == "gem_discussion")
        self.assertLess(preparation_end.turn, opening.turn)
        self.assertFalse(any(event.msg_type in {"gem_manito", "gem_card", "gem_round"} for event in match.events))
        self.assertFalse(any(event.msg_type == "action" and json.loads(event.content)["phase"] == "gem_preparation"
                             for event in match.events))
        for name in players:
            notes = [event for event in match.events if event.msg_type == "decision_note" and event.agent_name == name
                     and json.loads(event.content).get("phase") == "gem_preparation"
                     and "turn" in json.loads(event.content)]
            self.assertEqual([json.loads(event.content)["note"] for event in notes], [plan(name, turn) for turn in range(1, 4)])
            self.assertTrue(all(event.visible_to == [name] for event in notes))
            self.assertTrue(all(len(json.loads(event.content)["note"]) <= STRATEGY_NOTE_LIMIT for event in notes))
            pinned = next(event for event in match.events if event.msg_type == "discussion_note" and event.agent_name == name)
            self.assertEqual(pinned.content, plan(name, 3))
            self.assertEqual(pinned.visible_to, [name])
            self.assertEqual(len(preparation_prompts[name]), 3)
            self.assertEqual(len(opening_prompts[name]), 12)
            self.assertIn(plan(name, 3), opening_prompts[name][0])
            self.assertIn(plan(name, 3), opening_prompts[name][-1])
            other = next(player for player in players if player != name)
            self.assertFalse(pinned in match.observations(other))

    def test_discussion_allows_replies_before_auction_and_every_swap(self):
        testcase = self
        plans = {}
        submitted_plans = []
        queries = []
        refreshed_choices = set()

        class NegotiatingMatch(Match):
            def request_action(self, name, phase, prompt, default, **kwargs):
                self.phase = phase
                self.defaults = {name: default}
                return super().request_action(name, phase, prompt, default, **kwargs)

            def decide_together(self, phase, decisions, **kwargs):
                self.phase = phase
                self.defaults = {name: decision.default for name, decision in decisions.items()}
                return super().decide_together(phase, decisions, **kwargs)

            def _query(self, name, prompt, *args, **kwargs):
                queries.append((self.phase, name))
                response = self.defaults[name]
                observations = self.observations(name)
                identities = [event for event in observations if event.msg_type == "gem_manito"]
                if self.phase == "gem_opening_talk":
                    testcase.assertEqual(identities, [])
                    testcase.assertNotIn("개인 마니또를 확인한 뒤", prompt)
                elif self.phase in {"gem_bid", "gem_after_auction_talk"}:
                    testcase.assertEqual(len(identities), 1)
                    testcase.assertEqual(identities[0].agent_name, name)
                    testcase.assertEqual(identities[0].visible_to, [name])
                if self.phase in {"gem_opening_talk", "gem_talk", "gem_auction_talk", "gem_after_auction_talk"}:
                    context = next(json.loads(event.content) for event in reversed(self.events)
                                   if event.msg_type == "gem_discussion_round")
                    offer = f"offer {context['stage']} {context['round']} {context['pass']} {context['player']}"
                    if name == "P01" and (context["turn"] == 1 or context["player"] == "P09"):
                        message = offer
                        if self.phase == "gem_after_auction_talk":
                            outcome = next(json.loads(event.content) for event in observations if event.msg_type == "gem_auction")
                            beneficiary = json.loads(identities[0].content)["beneficiary"]
                            message += f" · 내 마니또 {beneficiary} · 낙찰자 {outcome['leader']}"
                        response = json.dumps({"type": "speak", "channel": "public", "text": message})
                    elif context["turn"] == 2 and name == "P02":
                        heard = next((event.content for event in observations if event.content.startswith(offer)), None)
                        testcase.assertIsNotNone(heard)
                        response = json.dumps({"type": "speak", "channel": "whisper", "to": "P01", "text": "reply " + heard})
                elif self.phase in {"gem_strategy", "gem_swap"}:
                    context = next(json.loads(event.content) for event in reversed(self.events)
                                   if event.msg_type == "gem_turn")
                    key = (name, context["round"], context["pass"])
                    if name == "P01" and any(event.msg_type == "gem_swap" for event in self.events):
                        testcase.assertIs(self.backends[name].relationships, self.relationships[name])
                        testcase.assertEqual(self.backends[name].relationships["P02"]["trust"], 80)
                        refreshed_choices.add(self.phase)
                    if self.phase == "gem_strategy":
                        response = plans[key] = f"plan for {name} round {context['round']} pass {context['pass']}"
                    else:
                        testcase.assertIn(plans[key], prompt)
                        submitted_plans.append(key)
                return response, StrategyNote()

        players = tuple(f"P{index:02}" for index in range(1, 10))
        client = Mock()

        def relationship_response(**kwargs):
            prompt = kwargs["input"][0]["content"][0]["text"]
            ratings = {}
            if "Exercise: P01의" in prompt:
                if "[gem_swap]" in prompt:
                    ratings = {"P02": {"affinity": 61, "trust": 80, "reason": "공개 교환 결과를 확인함"}}
                elif "P02" not in match.relationships["P01"]:
                    ratings = {"P02": {"affinity": 55, "trust": 55, "reason": "협상에서 답변을 받음"}}
            response = json.dumps({"action": json.dumps(ratings, ensure_ascii=False)})
            return SimpleNamespace(status="completed", output_text=response, usage=None)

        client.responses.create.side_effect = relationship_response
        model = OpenAILanguageModel("test-model", client)
        match = NegotiatingMatch(players, 8, pieces=[3] * 9, model=model,
                                 live_players=("P01", "P02"), live_turns=1000)
        play(match)
        events = match.events
        opening = next(event for event in events if event.msg_type == "gem_discussion")
        auction = next(event for event in events if event.msg_type == "gem_auction_round")
        self.assertEqual(json.loads(opening.content)["stage"], "opening")
        self.assertLess(opening.turn, auction.turn)
        self.assertFalse(any(event.msg_type == "gem_card" for event in events[:auction.turn]))
        opening_speakers = [name for phase, name in queries if phase == "gem_opening_talk"]
        self.assertEqual(len(opening_speakers), 24)
        self.assertEqual(set(opening_speakers[:2]), {"P01", "P02"})
        self.assertEqual(opening_speakers, opening_speakers[:2] * 12)
        opening_end = next(event for event in events if event.msg_type == "gem_discussion_end")
        opening_rounds = [json.loads(event.content)["turn"] for event in events[:opening_end.turn]
                          if event.msg_type == "gem_discussion_round"]
        self.assertEqual(opening_rounds, list(range(1, 13)))
        self.assertLess(opening_end.turn, auction.turn)
        self.assertTrue(json.loads(auction.content)["manito_reveal"])
        identities = [event for event in events if event.msg_type == "gem_manito"]
        bids = [event for event in events if event.msg_type == "action" and json.loads(event.content)["phase"] == "gem_bid"]
        self.assertEqual(len(identities), 9)
        self.assertTrue(all(auction.turn < event.turn < bids[0].turn for event in identities))
        outcome = next(event for event in events if event.msg_type == "gem_auction")
        after_auction = next(event for event in events if event.msg_type == "gem_discussion"
                             and json.loads(event.content)["stage"] == "after_auction")
        after_end = next(event for event in events[after_auction.turn + 1:] if event.msg_type == "gem_discussion_end")
        deal = next(event for event in events if event.msg_type == "gem_round")
        self.assertLess(outcome.turn, after_auction.turn)
        self.assertLess(after_end.turn, deal.turn)
        self.assertFalse(any(event.msg_type == "gem_card" for event in events[:deal.turn]))
        self.assertEqual(json.loads(after_auction.content)["rounds"], 5)
        self.assertEqual(json.loads(after_end.content)["reason"], "all_passed")
        after_rounds = [json.loads(event.content)["turn"] for event in events[after_auction.turn:after_end.turn]
                        if event.msg_type == "gem_discussion_round"]
        self.assertEqual(after_rounds, [1, 2, 3])
        self.assertTrue(any(event.msg_type == "public" and "내 마니또" in event.content and "낙찰자" in event.content
                            for event in events[after_auction.turn:after_end.turn]))

        acting = None
        for event in events:
            if event.msg_type == "gem_round":
                acting = None
            elif event.msg_type == "gem_turn":
                acting = json.loads(event.content)["player"]
                swap = next(candidate for candidate in events[event.turn + 1:] if candidate.msg_type == "gem_swap")
                segment = events[event.turn:swap.turn]
                kinds = [candidate.msg_type for candidate in segment]
                self.assertLess(kinds.index("gem_card"), kinds.index("gem_discussion"))
                self.assertLess(kinds.index("gem_discussion_end"), kinds.index("gem_strategy"))
                rounds = [json.loads(candidate.content)["turn"] for candidate in segment
                          if candidate.msg_type == "gem_discussion_round"]
                ended = next(json.loads(candidate.content) for candidate in segment
                             if candidate.msg_type == "gem_discussion_end")
                if acting == "P09":
                    self.assertEqual(rounds, [1, 2, 3, 4])
                    self.assertEqual(ended["reason"], "limit")
                else:
                    self.assertEqual(rounds, [1, 2, 3])
                    self.assertEqual(ended["reason"], "all_passed")
            elif event.msg_type == "gem_card" and acting is not None:
                self.assertEqual(event.agent_name, acting)
            elif event.msg_type == "decision_note" and json.loads(event.content)["phase"] == "gem_strategy":
                self.assertEqual(event.visible_to, [event.agent_name])
                other = next(player for player in players if player != event.agent_name)
                self.assertFalse(event in match.observations(other))
            elif event.msg_type == "whisper":
                self.assertEqual(event.visible_to, ["P02", "P01"])
                self.assertNotIn(event, match.observations("P03"))
        self.assertEqual(len(plans), 12)
        self.assertEqual(set(submitted_plans), set(plans))
        self.assertEqual(refreshed_choices, {"gem_strategy", "gem_swap"})
        updates = [event for event in events if event.msg_type == "relationship_update" and event.agent_name == "P01"]
        initial_rating = next(event for event in updates if json.loads(event.content)["ratings"]["P02"]["trust"] == 55)
        result_rating = next(event for event in updates if json.loads(event.content)["ratings"]["P02"]["trust"] == 80)
        self.assertTrue(opening_end.turn < initial_rating.turn < auction.turn)
        first_swap = next(event for event in events if event.msg_type == "gem_swap")
        following_turn = next(event for event in events[first_swap.turn + 1:] if event.msg_type == "gem_turn")
        self.assertTrue(first_swap.turn < result_rating.turn < following_turn.turn)
        for event in updates:
            self.assertEqual(event.visible_to, ["P01"])
            self.assertFalse(event in match.observations("P02"))

    def test_only_acting_player_can_finish_swap_discussion(self):
        class FirstSwapComplete(Exception):
            pass

        class ReadyMatch(Match):
            def event(self, kind, data, **kwargs):
                super().event(kind, data, **kwargs)
                if kind == "gem_turn" and any(event.msg_type == "gem_swap" for event in self.events):
                    raise FirstSwapComplete

            def review_relationships(self, checkpoint):
                reviews.append((len(self.events), checkpoint))
                return super().review_relationships(checkpoint)

            def request_action(self, name, phase, prompt, default, **kwargs):
                self.phase = phase
                self.defaults = {name: default}
                return super().request_action(name, phase, prompt, default, **kwargs)

            def decide_together(self, phase, decisions, **kwargs):
                self.phase = phase
                self.defaults = {name: decision.default for name, decision in decisions.items()}
                if phase == "gem_bid":
                    self.defaults = {name: "1" if name == "P01" else "0" for name in decisions}
                return super().decide_together(phase, decisions, **kwargs)

            def _query(self, name, prompt, *args, **kwargs):
                response = self.defaults[name]
                if self.phase in {"gem_opening_talk", "gem_after_auction_talk", "gem_talk"}:
                    context = next(json.loads(event.content) for event in reversed(self.events)
                                   if event.msg_type == "gem_discussion_round")
                    if self.phase != "gem_talk":
                        if name == "P01" and context["turn"] == 1:
                            response = '{"type":"swap_now"}'
                    elif scenario == "valid" and name == "P01" and context["turn"] == finish_turn:
                        response = '{"type":"swap_now"}'
                    elif scenario == "unauthorized" and name == "P02":
                        response = '{"type":"swap_now"}'
                    elif scenario == "extra_fields" and name == "P01":
                        response = '{"type":"swap_now","target":"buyer1"}'
                    else:
                        response = '{"type":"speak","channel":"public","text":"협상을 계속하자"}'
                elif self.phase == "gem_peek":
                    response = "buyer1"
                elif self.phase == "gem_strategy":
                    response = "확인한 카드와 대화를 바탕으로 P02와 교환한다."
                elif self.phase == "gem_swap":
                    response = "P02"
                return response, StrategyNote()

        players = tuple(f"P{index:02}" for index in range(1, 10))
        for scenario, finish_turn in (("valid", 1), ("valid", 2), ("valid", 3), ("unauthorized", 1), ("extra_fields", 1)):
            with self.subTest(scenario=scenario, finish_turn=finish_turn):
                reviews = []
                client = Mock()
                client.responses.create.return_value = SimpleNamespace(status="completed", output_text='{"action":"{}"}', usage=None)
                match = ReadyMatch(players, 8, pieces=[3] * 9, model=OpenAILanguageModel("test-model", client),
                                   live_players=players, live_turns=1000)
                with self.assertRaises(FirstSwapComplete):
                    play(match)
                events = match.events
                beginning = next(event for event in events if event.msg_type == "gem_discussion"
                                 and json.loads(event.content)["stage"] == "before_swap")
                ending = next(event for event in events[beginning.turn + 1:] if event.msg_type == "gem_discussion_end")
                context = json.loads(ending.content)
                self.assertEqual(context["player"], "P01")
                self.assertEqual(context["rounds"], 4)
                turns = [json.loads(event.content)["turn"] for event in events[beginning.turn:ending.turn]
                         if event.msg_type == "gem_discussion_round"]
                actions = [event for event in events[beginning.turn:ending.turn] if event.msg_type == "action"
                           and json.loads(event.content)["phase"] == "gem_talk"]
                if scenario == "valid":
                    self.assertEqual(context["reason"], "player_ready")
                    self.assertEqual(turns, list(range(1, finish_turn + 1)))
                    self.assertEqual(len(actions), 9 * (finish_turn - 1) + 1)
                    self.assertEqual(actions[-1].agent_name, "P01")
                else:
                    self.assertEqual(context["reason"], "limit")
                    self.assertEqual(turns, [1, 2, 3, 4])
                    invalid = [event for event in events[beginning.turn:ending.turn] if event.msg_type == "invalid_action"]
                    self.assertEqual(len(invalid), 4)
                    self.assertTrue(all(event.visible_to == ["P02" if scenario == "unauthorized" else "P01"] for event in invalid))
                self.assertEqual(actions[0].agent_name, "P01")
                self.assertTrue(any(index == ending.turn + 1 and "교환 전 협상 종료" in checkpoint for index, checkpoint in reviews))
                peek = next(event for event in events[ending.turn + 1:] if event.msg_type == "gem_peek")
                strategy = next(event for event in events[peek.turn + 1:] if event.msg_type == "decision_note"
                                and json.loads(event.content)["phase"] == "gem_strategy")
                swap = next(event for event in events[strategy.turn + 1:] if event.msg_type == "gem_swap")
                self.assertLess(ending.turn, peek.turn)
                self.assertLess(peek.turn, strategy.turn)
                self.assertLess(strategy.turn, swap.turn)
                self.assertEqual(json.loads(swap.content)["target"], "P02")
                self.assertEqual(strategy.visible_to, ["P01"])
                invalid_phases = {json.loads(event.content)["phase"] for event in events if event.msg_type == "invalid_action"}
                self.assertTrue({"gem_opening_talk", "gem_after_auction_talk"} <= invalid_phases)

    def test_tied_auction_negotiates_before_rebid_or_agreement(self):
        testcase = self

        class AuctionComplete(Exception):
            pass

        class NegotiatedAuction(Match):
            bid_round = 0

            def event(self, kind, data, **kwargs):
                super().event(kind, data, **kwargs)
                if kind == "gem_auction":
                    raise AuctionComplete

            def request_action(self, name, phase, prompt, default, **kwargs):
                self.phase = phase
                self.defaults = {name: default}
                return super().request_action(name, phase, prompt, default, **kwargs)

            def decide_together(self, phase, decisions, **kwargs):
                self.phase = phase
                self.defaults = {name: decision.default for name, decision in decisions.items()}
                if phase == "gem_bid":
                    self.bid_round += 1
                    if self.bid_round == 1:
                        self.defaults = {name: "1" if name in {"P01", "P02"} else "0" for name in decisions}
                    else:
                        testcase.assertEqual(set(decisions), {"P01", "P02"})
                        self.defaults = {"P01": "2", "P02": "pass"}
                elif phase == "gem_auction_agreement":
                    testcase.assertEqual(set(decisions), {"P01", "P02"})
                    self.defaults = dict.fromkeys(decisions, "P02")
                return super().decide_together(phase, decisions, **kwargs)

            def _query(self, name, prompt, *args, **kwargs):
                response = self.defaults[name]
                if self.phase == "gem_auction_talk":
                    context = next(json.loads(event.content) for event in reversed(self.events)
                                   if event.msg_type == "gem_discussion_round")
                    if context["turn"] == 1 and name == "P01":
                        response = '{"type":"speak","channel":"public","text":"선은 P02에게 양보하자"}'
                    elif context["turn"] == 2 and name == "P02":
                        testcase.assertTrue(any(event.content == "선은 P02에게 양보하자" for event in self.observations(name)))
                        response = '{"type":"speak","channel":"public","text":"동의한다"}'
                return response, StrategyNote()

        players = tuple(f"P{index:02}" for index in range(1, 10))
        for pieces, winner, price in ((1, "P02", 1), (3, "P01", 2)):
            with self.subTest(pieces=pieces):
                client = Mock()
                client.responses.create.return_value = SimpleNamespace(status="completed", output_text='{"action":"{}"}', usage=None)
                match = NegotiatedAuction(players, 8, pieces=[pieces] * 9,
                                          model=OpenAILanguageModel("test-model", client),
                                          live_players=players, live_turns=1000)
                with self.assertRaises(AuctionComplete):
                    play(match)
                events = match.events
                final = json.loads(events[-1].content)
                self.assertEqual(final["leader"], winner)
                self.assertEqual(final["bid"], price)
                self.assertEqual(final["pieces"], {player: pieces - (price if player == winner else 0) for player in players})
                start = next(event for event in events if event.msg_type == "gem_discussion"
                             and json.loads(event.content)["stage"] == "auction_tie")
                context = json.loads(start.content)
                self.assertEqual(set(context["bidders"]), {"P01", "P02"})
                self.assertEqual(context["bid"], 1)
                self.assertEqual(context["rounds"], 5)
                ended = next(event for event in events[start.turn + 1:] if event.msg_type == "gem_discussion_end")
                self.assertEqual(json.loads(ended.content)["reason"], "all_passed")
                turns = [json.loads(event.content)["turn"] for event in events[start.turn:ended.turn]
                         if event.msg_type == "gem_discussion_round"]
                self.assertEqual(turns, [1, 2, 3])
                talkers = [event.agent_name for event in events[start.turn:ended.turn]
                           if event.msg_type == "action" and json.loads(event.content)["phase"] == "gem_auction_talk"]
                self.assertEqual(Counter(talkers), Counter(dict.fromkeys(players, 3)))
                next_phase = "gem_auction_agreement" if pieces == 1 else "gem_bid"
                next_action = next(event for event in events[ended.turn + 1:] if event.msg_type == "action")
                self.assertEqual(json.loads(next_action.content)["phase"], next_phase)

    def test_relationship_reviews_use_only_new_visible_evidence(self):
        prompts = []
        client = Mock()

        def respond(**kwargs):
            prompt = kwargs["input"][0]["content"][0]["text"]
            prompts.append(prompt)
            action = "대기"
            if "비공개 관계 평가를 갱신하세요" in prompt:
                ratings = {}
                if "Exercise: P01의" in prompt:
                    ratings = {"P02": {"affinity": 60, "trust": 80 if "[gem_card]" in prompt else 55,
                                       "reason": "직접 확인한 정보"}}
                action = json.dumps(ratings, ensure_ascii=False)
            return SimpleNamespace(status="completed", output_text=json.dumps({"action": action}), usage=None)

        client.responses.create.side_effect = respond
        model = OpenAILanguageModel("test-model", client)
        players = ("P01", "P02", "P03")
        match = Match(players, 1, model=model, live_players=players, live_turns=20)
        match.event("public", "공개 협력 제안", actor="P02")
        match.event("whisper", "P02와 P03만 아는 비밀", actor="P02", private=("P02", "P03"))
        match.review_relationships("협상 종료")
        self.assertEqual(model.calls, 3)
        first_prompt = next(prompt for prompt in prompts if "Exercise: P01의" in prompt)
        self.assertIn("공개 협력 제안", first_prompt)
        self.assertNotIn("P02와 P03만 아는 비밀", first_prompt)
        self.assertEqual(match.relationships["P01"]["P02"]["trust"], 55)
        self.assertFalse(any(event.msg_type == "invalid_action" for event in match.events))
        remaining = match.live_turns
        match.review_relationships("새 근거 없음")
        self.assertEqual(model.calls, 3)
        self.assertEqual(match.live_turns, remaining)
        match.event("gem_card", {"round": 1, "slot": "P01", "card": {"kind": "gold", "value": 5}},
                    actor="P01", private=("P01",))
        match.review_relationships("교환 결과 확인")
        self.assertEqual(model.calls, 4)
        self.assertIn("[gem_card]", prompts[-1])
        self.assertIn("공개 협력 제안", prompts[-1])
        self.assertNotIn("P02와 P03만 아는 비밀", prompts[-1])
        self.assertEqual(match.relationships["P01"]["P02"]["trust"], 80)
        self.assertIs(match.backends["P01"].relationships, match.relationships["P01"])
        match.decide("P01", "test", "갱신한 관계를 참고하세요.", "대기", options=("대기",))
        self.assertIn("신뢰도 80/100", prompts[-1])
        self.assertNotIn("P02와 P03만 아는 비밀", prompts[-1])

    def test_interrupted_decisions_resume_to_identical_game(self):
        original_event = Match.event

        def reply(prompt):
            action = "pass"
            if "비공개 관계 평가를 갱신하세요" in prompt:
                action = json.dumps({"P02": {"affinity": 55, "trust": 60, "reason": "공개 결과를 확인함"}}, ensure_ascii=False)
            elif "교환 전 대화입니다. 이번 교환자는 P01입니다." in prompt.rsplit("Exercise:", 1)[-1]:
                action = '{"type":"swap_now"}'
            return json.dumps({"action": action, "note": "test"})

        with (
            TemporaryDirectory() as directory,
            redirect_stdout(StringIO()),
            redirect_stderr(StringIO()),
            patch("games.models.CodexLanguageModel._complete", side_effect=reply) as completion,
        ):
            for count, budget in ((9, 20), (9, 300), (10, 300)):
                uninterrupted = Path(directory) / f"full-{count}-{budget}.jsonl"
                arguments = ["--seed", "41", "--players", *(f"P{seat:02}" for seat in range(1, count + 1)),
                             "--pieces", *(["3"] * count), "--model", "test-model",
                             "--model-player", "P01", "--model-turns", str(budget), "--no-allow-review"]
                run_cli(play, title=DAY_THREE_MAIN, seats=(9, 10),
                        argv=[*arguments, "--output", str(uninterrupted)])
                expected = [json.loads(line) for line in uninterrupted.read_bytes().splitlines()]
                self.assertEqual(len(expected[-1]["eliminated"]), count - 8)
                self.assertLessEqual(expected[-1]["model_calls"], budget)
                checkpoints = ("preparation_note", "gem_preparation_end", "auction_bid", "after_auction",
                               "relationship_update", "gem_swap", "gem_discussion_end", "gem_strategy_note")
                if budget == 300:
                    self.assertTrue(any(row.get("msg_type") == "gem_discussion_end" and
                                        json.loads(row["content"])["reason"] == "player_ready" for row in expected))
                    checkpoints += ("player_ready",)
                for checkpoint in checkpoints:
                    with self.subTest(players=count, budget=budget, checkpoint=checkpoint):
                        resumed = Path(directory) / f"resumed-{count}-{budget}-{checkpoint}.jsonl"

                        def interrupt(match, kind, data, **kwargs):
                            original_event(match, kind, data, **kwargs)
                            if checkpoint == "preparation_note":
                                reached = kind == "decision_note" and data.get("phase") == "gem_preparation" and data.get("turn") == 2
                            elif checkpoint == "gem_preparation_end":
                                reached = kind == "gem_preparation_end"
                            elif checkpoint == "auction_bid":
                                reached = kind == "action" and data.get("phase") == "gem_bid"
                            elif checkpoint == "after_auction":
                                reached = kind == "gem_discussion_end" and data["stage"] == "after_auction"
                            elif checkpoint == "relationship_update":
                                reached = kind == "relationship_update"
                            elif checkpoint == "player_ready":
                                reached = kind == "gem_discussion_end" and data["reason"] == "player_ready"
                            elif checkpoint == "gem_strategy_note":
                                reached = kind == "decision_note" and data.get("phase") == "gem_strategy"
                                if reached:
                                    context = next(json.loads(event.content) for event in reversed(match.events)
                                                   if event.msg_type == "gem_turn")
                                    reached = context["round"] == 2 and context["pass"] == 2
                            else:
                                reached = kind == checkpoint and data["round"] == 2 and data["pass"] == 2
                            if reached:
                                raise RuntimeError("test interruption after committed progress")

                        with patch.object(Match, "event", interrupt):
                            with self.assertRaisesRegex(RuntimeError, "committed progress"):
                                run_cli(play, title=DAY_THREE_MAIN, seats=(9, 10),
                                        argv=[*arguments, "--output", str(resumed)])
                        prefix = [json.loads(line) for line in resumed.read_bytes().splitlines()]
                        self.assertEqual(prefix[-1]["type"], "interrupted")
                        decisions = resumed.with_suffix(".decisions.jsonl")
                        self.assertTrue(decisions.read_bytes())
                        calls_before_resume = completion.call_count
                        run_cli(play, title=DAY_THREE_MAIN, seats=(9, 10),
                                argv=["--resume", "--output", str(resumed)])
                        actual = [json.loads(line) for line in resumed.read_bytes().splitlines()]
                        self.assertEqual(actual, expected)
                        self.assertEqual(actual[:len(prefix) - 1], prefix[:-1])
                        self.assertEqual(completion.call_count - calls_before_resume,
                                         expected[-1]["model_calls"] - prefix[-1]["model_calls"])

    def test_existing_rules_without_preparation_resume_without_new_stages(self):
        previous_rules = ("\n\n5. 협상과 전략 정리\n\n\n6. 동률 경매 협상\n"
                          "\n\n7. 시작 전 진행 순서\n\n\n8. 관계 평가 갱신\n")
        original_event = Match.event

        def previous_play(match):
            current_log = match.resume_log
            match.resume_log = SimpleNamespace(
                resume=True, events=[{"msg_type": "rules", "content": previous_rules}], journal=current_log.journal,
            )
            try:
                return play(match)
            finally:
                match.resume_log = current_log

        def interrupt(match, kind, data, **kwargs):
            original_event(match, kind, data, **kwargs)
            if kind == "gem_swap":
                raise RuntimeError("test interruption in an existing ruleset")

        def respond(prompt):
            action = "{}" if "비공개 관계 평가를 갱신하세요" in prompt else "pass"
            return json.dumps({"action": action, "note": ""})

        with (
            TemporaryDirectory() as directory,
            redirect_stdout(StringIO()),
            redirect_stderr(StringIO()),
            patch("games.models.CodexLanguageModel._complete", side_effect=respond) as completion,
        ):
            full = Path(directory) / "previous-full.jsonl"
            resumed = Path(directory) / "previous-resumed.jsonl"
            arguments = ["--seed", "41", "--players", *(f"P{seat:02}" for seat in range(1, 11)),
                         "--model", "test-model", "--model-player", "P01", "--model-turns", "60"]
            run_cli(previous_play, title=DAY_THREE_MAIN, seats=(9, 10), argv=[*arguments, "--output", str(full)])
            with patch.object(Match, "event", interrupt):
                with self.assertRaisesRegex(RuntimeError, "existing ruleset"):
                    run_cli(previous_play, title=DAY_THREE_MAIN, seats=(9, 10), argv=[*arguments, "--output", str(resumed)])
            prefix = [json.loads(line) for line in resumed.read_bytes().splitlines()]
            rules = next(row["content"] for row in prefix if row.get("msg_type") == "rules")
            self.assertIn("\n\n8. 관계 평가 갱신\n", rules)
            self.assertIn("최하위 한 명은 탈락", rules)
            self.assertNotIn("\n\n9. 시작 전 비공개 전략 준비\n", rules)
            calls_before_resume = completion.call_count
            run_cli(play, title=DAY_THREE_MAIN, seats=(9, 10), argv=["--resume", "--output", str(resumed)])
            expected = [json.loads(line) for line in full.read_bytes().splitlines()]
            self.assertEqual(expected[-1]["eliminated"], expected[-1]["ranking"][-1:])
            actual = [json.loads(line) for line in resumed.read_bytes().splitlines()]
            self.assertEqual(actual, expected)
            self.assertFalse(any(row.get("msg_type") in {"gem_preparation", "gem_preparation_end"} for row in actual))
            self.assertEqual(completion.call_count - calls_before_resume,
                             expected[-1]["model_calls"] - prefix[-1]["model_calls"])


if __name__ == "__main__":
    unittest.main()
