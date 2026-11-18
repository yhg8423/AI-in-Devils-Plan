"""Checks for bank routing, scoring, visibility, and deterministic resumption."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ..match import DAY_THREE_PRISON, Match, run_cli
from .game import parse_challenge, parse_deposit, play


PLAYERS = ("P01", "P02", "P03", "P04")


class PiggyBankTest(unittest.TestCase):
    def test_deposits_require_one_to_five_coins_and_another_recipient(self):
        for black, white in ((0, 1), (5, 0), (2, 3)):
            action = {"black": black, "white": white, "to": "P02"}
            self.assertEqual(parse_deposit(json.dumps(action), PLAYERS, "P01"), action)
        invalid = [
            {"black": 0, "white": 0, "to": "P02"},
            {"black": 3, "white": 3, "to": "P02"},
            {"black": -1, "white": 2, "to": "P02"},
            {"black": True, "white": 1, "to": "P02"},
            {"black": 1.5, "white": 1, "to": "P02"},
            {"black": 1, "white": 1, "to": "P01"},
            {"black": 1, "white": 1, "to": "outsider"},
            {"black": 1, "white": 1, "to": "P02", "extra": 1},
            [],
        ]
        for action in invalid:
            with self.subTest(action=action), self.assertRaises(ValueError):
                parse_deposit(json.dumps(action), PLAYERS, "P01")

    def test_reset_challenge_requires_every_live_bank_and_both_colors(self):
        guesses = {str(bank): {"black": bank, "white": bank + 1} for bank in range(1, 6)}
        self.assertIsNone(parse_challenge("pass", range(1, 6)))
        self.assertEqual(parse_challenge(json.dumps(guesses), range(1, 6)), guesses)
        invalid = [
            {bank: coins for bank, coins in guesses.items() if bank != "5"},
            {**guesses, "6": {"black": 1, "white": 1}},
            {**guesses, "1": {"black": 1}},
            {**guesses, "1": {"black": -1, "white": 1}},
            {**guesses, "1": {"black": True, "white": 1}},
            {**guesses, "1": {"black": 1, "white": 1.5}},
            [],
        ]
        for action in invalid:
            with self.subTest(action=action), self.assertRaises(ValueError):
                parse_challenge(json.dumps(action), range(1, 6))

    def test_complete_match_preserves_bank_routing_counts_and_scores(self):
        match = Match(PLAYERS, 23, pieces=[1, 2, 3, 4])
        result = play(match)
        banks = {str(bank): {"black": 1, "white": 1} for bank in range(1, 6)}
        scores = dict.fromkeys(PLAYERS, 0)
        lower = upper = None
        deposits = doubts = 0

        for event in match.events:
            if not event.msg_type.startswith("pig_"):
                continue
            data = json.loads(event.content)
            if event.msg_type == "pig_setup":
                lower, upper = data["lower"], data["upper"]
                self.assertCountEqual(data["order"], PLAYERS)
            elif event.msg_type == "pig_turn":
                self.assertEqual(data["color"], "black" if data["turn"] % 2 else "white")
                self.assertEqual(data["scores"], scores)
                self.assertIsNotNone(data["upper"][data["player"]])
                self.assertEqual(sum(bank is not None for bank in data["upper"].values()), 1)
                lower, upper = data["lower"], data["upper"]
            elif event.msg_type == "pig_deposit":
                deposits += 1
                name, recipient, bank = data["player"], data["to"], data["bank"]
                self.assertNotEqual(name, recipient)
                self.assertEqual(bank, lower[name])
                self.assertLessEqual(1, data["black"] + data["white"])
                self.assertLessEqual(data["black"] + data["white"], 5)
                banks[str(bank)]["black"] += data["black"]
                banks[str(bank)]["white"] += data["white"]
                expected_lower = {**lower, name: upper[name]}
                expected_upper = {**upper, name: None, recipient: bank}
                self.assertEqual(data["lower"], expected_lower)
                self.assertEqual(data["upper"], expected_upper)
                lower, upper = expected_lower, expected_upper
            elif event.msg_type == "pig_doubt":
                doubts += 1
                self.assertEqual(data["actual"], banks[str(data["bank"])])
                self.assertEqual(data["correct"], data["claimed"] != data["actual"][data["color"]])
                penalized = data["player"] if data["correct"] else data["challenger"]
                scores[penalized] -= 1
                if data["correct"]:
                    scores[data["challenger"]] += 1
                self.assertEqual(data["scores"], scores)
            elif event.msg_type == "pig_replace":
                banks.pop(str(data["old_bank"]))
                self.assertNotIn(str(data["bank"]), banks)
                banks[str(data["bank"])] = {"black": 1, "white": 1}
                self.assertEqual(data["next_player"], data["player"])
                self.assertEqual(data["upper"][data["player"]], data["bank"])
                lower, upper = data["lower"], data["upper"]
            elif event.msg_type == "pig_challenge":
                self.assertEqual(data["actual"], banks)
                self.assertEqual(data["correct"], data["guesses"] == banks)
                scores[data["player"]] += 3 if data["correct"] else -2
                self.assertEqual(data["scores"], scores)
            elif event.msg_type == "pig_reset":
                banks = {str(bank): {"black": 1, "white": 1} for bank in range(1, 6)}
                self.assertEqual(data["scores"], scores)
                lower, upper = data["lower"], data["upper"]
            elif event.msg_type == "pig_contents":
                self.assertEqual(data["banks"], banks)
                self.assertEqual(event.visible_to, ["__operator__"])
                for player in PLAYERS:
                    self.assertNotIn(event, match.observations(player))
                in_play = [*lower.values(), *(bank for bank in upper.values() if bank is not None)]
                self.assertEqual(len(in_play), 5)
                self.assertEqual(set(map(str, in_play)), set(banks))

        self.assertGreater(deposits, 0)
        self.assertGreater(doubts, 0)
        self.assertEqual(result["scores"], scores)
        self.assertGreaterEqual(max(scores.values()), 5)
        self.assertCountEqual(result["ranking"], PLAYERS)
        self.assertEqual([scores[name] for name in result["ranking"]], sorted(scores.values(), reverse=True))
        self.assertEqual(result["eliminated"], result["ranking"][-1:])
        winners = [name for name in PLAYERS if scores[name] == max(scores.values())]
        for name in PLAYERS:
            reward = 3 // len(winners) if name in winners else 0
            self.assertEqual(result["pieces_awarded"].get(name, 0), reward)
            self.assertEqual(result["pieces"][name], match.pieces[name] + reward)

    def test_suspicion_replaces_the_opened_bank_and_penalized_player_acts_next(self):
        class FirstTurnComplete(Exception):
            pass

        class SuspicionMatch(Match):
            def decide(self, name, phase, prompt, default, **kwargs):
                if phase == "pig_deposit":
                    default = json.dumps({"black": 0, "white": 1,
                                          "to": next(player for player in PLAYERS if player != name)})
                elif phase == "pig_count":
                    default = "0" if wrong else "1"
                elif phase == "pig_reset_vote":
                    default = "pass"
                return super().decide(name, phase, prompt, default, **kwargs)

            def decide_together(self, phase, decisions, **kwargs):
                if phase == "pig_doubt":
                    first = next(iter(decisions))
                    decisions = {name: replace(decision, default="doubt" if doubt and name == first else "pass")
                                 for name, decision in decisions.items()}
                return super().decide_together(phase, decisions, **kwargs)

            def event(self, kind, data, **kwargs):
                super().event(kind, data, **kwargs)
                if kind == "pig_turn" and data["turn"] == 2:
                    raise FirstTurnComplete

        for doubt, wrong in ((True, True), (True, False), (False, False)):
            with self.subTest(doubt=doubt, wrong=wrong):
                match = SuspicionMatch(PLAYERS, 23)
                with self.assertRaises(FirstTurnComplete):
                    play(match)
                events = [(event.msg_type, json.loads(event.content)) for event in match.events
                          if event.msg_type.startswith("pig_")]
                claim = next(data for kind, data in events if kind == "pig_claim")
                next_turn = next(data for kind, data in events if kind == "pig_turn" and data["turn"] == 2)
                if doubt:
                    result = next(data for kind, data in events if kind == "pig_doubt")
                    replacement = next(data for kind, data in events if kind == "pig_replace")
                    penalized = result["player"] if wrong else result["challenger"]
                    self.assertEqual(result["correct"], wrong)
                    self.assertEqual(result["scores"][penalized], -1)
                    self.assertEqual(result["scores"][result["challenger"]], 1 if wrong else -1)
                    self.assertEqual(replacement["player"], penalized)
                    self.assertEqual(replacement["old_bank"], claim["bank"])
                    self.assertEqual(replacement["bank"], 6)
                    self.assertEqual(replacement["initial"], {"black": 1, "white": 1})
                    self.assertEqual(next_turn["player"], penalized)
                    self.assertEqual(next_turn["upper"][penalized], 6)
                    self.assertNotIn(claim["bank"], next_turn["lower"].values())
                    self.assertNotIn(claim["bank"], next_turn["upper"].values())
                else:
                    self.assertEqual(next_turn["player"], claim["player"])
                    self.assertEqual(next_turn["upper"][claim["player"]], claim["bank"])
                    self.assertFalse(any(kind == "pig_replace" for kind, _ in events))

    def test_reset_challenge_scores_before_fresh_banks_are_distributed(self):
        class ResetComplete(Exception):
            pass

        class ResetMatch(Match):
            def __init__(self):
                super().__init__(PLAYERS, 23)
                self.banks = {}

            def event(self, kind, data, **kwargs):
                super().event(kind, data, **kwargs)
                if kind == "pig_contents":
                    self.banks = json.loads(json.dumps(data["banks"]))
                elif kind == "pig_reset":
                    raise ResetComplete

            def decide(self, name, phase, prompt, default, **kwargs):
                if phase == "pig_reset_vote":
                    default = "reset"
                elif phase == "pig_challenge":
                    guesses = json.loads(json.dumps(self.banks))
                    if not correct:
                        guesses[next(iter(guesses))]["black"] += 1
                    default = json.dumps(guesses)
                return super().decide(name, phase, prompt, default, **kwargs)

        for correct in (True, False):
            with self.subTest(correct=correct):
                match = ResetMatch()
                with self.assertRaises(ResetComplete):
                    play(match)
                records = [(event.msg_type, json.loads(event.content)) for event in match.events
                           if event.msg_type.startswith("pig_")]
                votes = [data["player"] for kind, data in records if kind == "pig_reset_vote"]
                challenge = next(data for kind, data in records if kind == "pig_challenge")
                reset = next(data for kind, data in records if kind == "pig_reset")
                self.assertEqual(len(votes), 3)
                self.assertEqual(len(set(votes)), 3)
                self.assertNotIn(challenge["player"], votes)
                self.assertEqual(challenge["correct"], correct)
                before = next((data["scores"] for kind, data in records if kind == "pig_doubt"),
                              dict.fromkeys(PLAYERS, 0))
                self.assertEqual(challenge["scores"][challenge["player"]] - before[challenge["player"]],
                                 3 if correct else -2)
                self.assertEqual(reset["scores"], challenge["scores"])
                self.assertEqual(reset["reset"], 1)
                self.assertEqual(set(reset["lower"].values()) |
                                 {bank for bank in reset["upper"].values() if bank is not None}, set(range(1, 6)))

    def test_a_challenge_passing_five_points_ends_before_another_reset(self):
        class ChallengeMatch(Match):
            def event(self, kind, data, **kwargs):
                super().event(kind, data, **kwargs)
                if kind == "pig_contents":
                    self.banks = json.loads(json.dumps(data["banks"]))

            def decide(self, name, phase, prompt, default, **kwargs):
                if phase == "pig_reset_vote":
                    default = "pass" if name == "P01" else "reset"
                elif phase == "pig_challenge":
                    default = json.dumps(self.banks)
                return super().decide(name, phase, prompt, default, **kwargs)

            def decide_together(self, phase, decisions, **kwargs):
                if phase == "pig_doubt":
                    decisions = {name: replace(decision, default="pass") for name, decision in decisions.items()}
                return super().decide_together(phase, decisions, **kwargs)

        match = ChallengeMatch(PLAYERS, 23)
        result = play(match)
        self.assertEqual(result["scores"], {"P01": 6, "P02": 0, "P03": 0, "P04": 0})
        self.assertEqual(result["turns"], 2)
        self.assertEqual(result["resets"], 1)
        self.assertEqual(match.events[-1].msg_type, "pig_challenge")
        self.assertEqual(result["winners"], ["P01"])
        self.assertEqual(result["pieces_awarded"]["P01"], 3)
        order = next(json.loads(event.content)["order"] for event in match.events if event.msg_type == "pig_setup")
        self.assertEqual(result["eliminated"], [next(player for player in reversed(order) if player != "P01")])

    def test_opening_has_four_discussion_rounds_and_each_deposit_has_two(self):
        match = Match(PLAYERS, 23)
        result = play(match)
        order = next(json.loads(event.content)["order"] for event in match.events if event.msg_type == "pig_setup")
        window = completed = None
        speakers = []
        deposits = 0
        for event in match.events:
            if event.msg_type not in {"pig_discussion", "pig_discussion_end", "action", "pig_deposit"}:
                continue
            data = json.loads(event.content)
            if event.msg_type == "pig_discussion":
                self.assertIsNone(window)
                window = data
                speakers = []
                self.assertEqual(data["turns"], 4 if data["stage"] == "opening" else 2)
            elif event.msg_type == "action" and data["phase"] == "pig_talk":
                self.assertIsNotNone(window)
                speakers.append(event.agent_name)
            elif event.msg_type == "pig_discussion_end":
                self.assertEqual(speakers, order * window["turns"])
                self.assertEqual((data["stage"], data["turn"]), (window["stage"], window["turn"]))
                completed, window = window, None
            elif event.msg_type == "pig_deposit":
                self.assertEqual((completed["stage"], completed["turn"]), ("before_turn", data["turn"]))
                deposits += 1
        self.assertEqual(deposits, result["turns"])
        self.assertIsNone(window)

    def test_saved_one_round_discussions_resume_without_changing_the_record(self):
        def previous_play(match):
            current_log = match.resume_log
            match.resume_log = SimpleNamespace(
                resume=True, events=[{"msg_type": "rules", "content": "추가 행동 전에는 전원에게 한 턴씩"}],
                journal=current_log.journal,
            )
            try:
                return play(match)
            finally:
                match.resume_log = current_log

        def reply(prompt):
            action = "{}" if "비공개 관계 평가를 갱신하세요" in prompt else "pass"
            return json.dumps({"action": action, "note": ""})

        original_event = Match.event

        def interrupt(match, kind, data, **kwargs):
            original_event(match, kind, data, **kwargs)
            if kind == "pig_deposit":
                raise RuntimeError("test interruption after legacy discussion")

        with (
            TemporaryDirectory() as directory,
            redirect_stdout(StringIO()),
            redirect_stderr(StringIO()),
            patch("games.models.CodexLanguageModel._complete", side_effect=reply) as completion,
        ):
            full = Path(directory) / "old-full.jsonl"
            resumed = Path(directory) / "old-resumed.jsonl"
            arguments = ["--seed", "23", "--model", "test-model", "--model-player", "P01",
                         "--model-turns", "30", "--no-allow-review"]
            run_cli(previous_play, title=DAY_THREE_PRISON, seats=4, argv=[*arguments, "--output", str(full)])
            with patch.object(Match, "event", interrupt), self.assertRaisesRegex(RuntimeError, "legacy discussion"):
                run_cli(previous_play, title=DAY_THREE_PRISON, seats=4, argv=[*arguments, "--output", str(resumed)])
            prefix = [json.loads(line) for line in resumed.read_bytes().splitlines()]
            calls_before = completion.call_count
            run_cli(play, title=DAY_THREE_PRISON, seats=4, argv=["--resume", "--output", str(resumed)])
            expected = [json.loads(line) for line in full.read_bytes().splitlines()]
            actual = [json.loads(line) for line in resumed.read_bytes().splitlines()]
            self.assertEqual(actual, expected)
            self.assertEqual(actual[:len(prefix) - 1], prefix[:-1])
            self.assertEqual(completion.call_count - calls_before,
                             expected[-1]["model_calls"] - prefix[-1]["model_calls"])
            rules = next(row["content"] for row in actual if row.get("msg_type") == "rules")
            self.assertIn("추가 행동 전에는 전원에게 한 턴씩", rules)
            windows = [json.loads(row["content"]) for row in actual if row.get("msg_type") == "pig_discussion"]
            self.assertEqual(windows[0]["turns"], 4)
            self.assertTrue(all(window["turns"] == 1 for window in windows[1:]))

    def test_interrupted_model_decisions_resume_to_the_same_record(self):
        def reply(prompt):
            action = "{}" if "비공개 관계 평가를 갱신하세요" in prompt else "pass"
            return json.dumps({"action": action, "note": ""})

        original_event = Match.event
        with (
            TemporaryDirectory() as directory,
            redirect_stdout(StringIO()),
            redirect_stderr(StringIO()),
            patch("games.models.CodexLanguageModel._complete", side_effect=reply) as completion,
        ):
            full = Path(directory) / "full.jsonl"
            arguments = ["--seed", "23", "--model", "test-model", "--model-player", "P01",
                         "--model-turns", "30", "--no-allow-review"]
            run_cli(play, title=DAY_THREE_PRISON, seats=4, argv=[*arguments, "--output", str(full)])
            expected = [json.loads(line) for line in full.read_bytes().splitlines()]
            for checkpoint in ("pig_deposit", "pig_doubt"):
                with self.subTest(checkpoint=checkpoint):
                    resumed = Path(directory) / f"resumed-{checkpoint}.jsonl"

                    def interrupt(match, kind, data, **kwargs):
                        original_event(match, kind, data, **kwargs)
                        if kind == checkpoint:
                            raise RuntimeError("test interruption after committed event")

                    with patch.object(Match, "event", interrupt):
                        with self.assertRaisesRegex(RuntimeError, "committed event"):
                            run_cli(play, title=DAY_THREE_PRISON, seats=4,
                                    argv=[*arguments, "--output", str(resumed)])
                    prefix = [json.loads(line) for line in resumed.read_bytes().splitlines()]
                    self.assertEqual(prefix[-1]["type"], "interrupted")
                    calls_before = completion.call_count
                    run_cli(play, title=DAY_THREE_PRISON, seats=4,
                            argv=["--resume", "--output", str(resumed)])
                    actual = [json.loads(line) for line in resumed.read_bytes().splitlines()]
                    self.assertEqual(actual, expected)
                    self.assertEqual(actual[:len(prefix) - 1], prefix[:-1])
                    self.assertEqual(completion.call_count - calls_before,
                                     expected[-1]["model_calls"] - prefix[-1]["model_calls"])


if __name__ == "__main__":
    unittest.main()
