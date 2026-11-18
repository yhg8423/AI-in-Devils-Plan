"""Checks for bank routing, scoring, visibility, and deterministic resumption."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from io import StringIO
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ..match import DAY_THREE_PRISON, Match, run_cli
from ..models import CodexLanguageModel
from .game import (
    NO_DISCUSSION_HEADING, NO_RELATIONSHIP_HEADING, SIMULTANEOUS_RESET_HEADING,
    parse_challenge, parse_deposit, play,
)
from .memory import DYNAMIC_MEMORY_HEADING, FREE_MEMORY_HEADING, MEMORY_HEADING, MEMORY_SUMMARY_LIMIT


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
        terminal = next(index for index, event in enumerate(match.events)
                        if event.msg_type in {"pig_doubt", "pig_challenge"}
                        and max(json.loads(event.content)["scores"].values()) >= 5)
        self.assertFalse(any(event.msg_type == "action" for event in match.events[terminal + 1:]),
                         "A winning verdict skips reset voting and further memory-update actions")
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
                elif phase == "pig_reset_vote":
                    decisions = {name: replace(decision, default="pass") for name, decision in decisions.items()}
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
                    default = "pass" if name == "P01" else "reset"
                elif phase == "pig_challenge":
                    guesses = json.loads(json.dumps(self.banks))
                    if not correct:
                        guesses[next(iter(guesses))]["black"] += 1
                    default = json.dumps(guesses)
                return super().decide(name, phase, prompt, default, **kwargs)

            def decide_together(self, phase, decisions, **kwargs):
                if phase == "pig_reset_vote":
                    decisions = {name: replace(decision, default="pass" if name == "P01" else "reset")
                                 for name, decision in decisions.items()}
                return super().decide_together(phase, decisions, **kwargs)

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
                elif phase == "pig_reset_vote":
                    decisions = {name: replace(decision, default="pass" if name == "P01" else "reset")
                                 for name, decision in decisions.items()}
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

    def test_simultaneous_reset_queries_share_prior_votes_and_publish_all_current_requests(self):
        class TurnsComplete(Exception):
            pass

        class ResetMatch(Match):
            current_turn = 0

            def event(self, kind, data, **kwargs):
                super().event(kind, data, **kwargs)
                if kind == "rules":
                    self.resume_log = None  # The stub selects saved rules; this prompt test does not replay a journal.
                elif kind == "pig_turn":
                    self.current_turn = data["turn"]
                    if self.current_turn > len(requests):
                        raise TurnsComplete

        scenarios = ((set(),), ({"P01"}, {"P02", "P03"}),
                     ({"P01", "P02"}, {"P03", "P04"}), (set(PLAYERS),))
        for requests in scenarios:
            with self.subTest(requests=requests), TemporaryDirectory() as directory:
                models = {name: CodexLanguageModel("test-model", Path(directory)) for name in PLAYERS}
                owners = {id(model): name for name, model in models.items()}
                match = ResetMatch(PLAYERS, 23, models=models, live_turns=500, allow_review=False)
                match.resume_log = SimpleNamespace(resume=True, events=[{
                    "msg_type": "rules", "content": DYNAMIC_MEMORY_HEADING + NO_DISCUSSION_HEADING
                    + NO_RELATIONSHIP_HEADING + SIMULTANEOUS_RESET_HEADING,
                }])
                queries = []

                def reply(model, prompt):
                    name = owners[id(model)]
                    if "현재 리셋 요청자 " in prompt:
                        queries.append((match.current_turn, name, prompt))
                        action = "reset" if name in requests[match.current_turn - 1] else "pass"
                    elif "다음 구간에 남길 기억 세 개를 갱신하세요" in prompt:
                        current = json.loads(prompt.rsplit("현재 저금통 번호: ", 1)[1].split(". 기존 기억:", 1)[0])
                        action = json.dumps({str(bank): {"black": 77, "white": None} for bank in current[::2]})
                    else:
                        action = "pass"
                    return json.dumps({"action": action, "note": ""})

                with patch("games.models.CodexLanguageModel._complete", autospec=True, side_effect=reply):
                    with self.assertRaises(TurnsComplete):
                        play(match)

                order = next(json.loads(event.content)["order"] for event in match.events if event.msg_type == "pig_setup")
                prior = []
                for turn, current_requests in enumerate(requests, 1):
                    inputs = [(name, prompt) for number, name, prompt in queries if number == turn]
                    eligible = set(PLAYERS) - set(prior)
                    self.assertCountEqual([name for name, _ in inputs], eligible)
                    for _, prompt in inputs:
                        shown = json.loads(prompt.rsplit("현재 리셋 요청자 ", 1)[1].split(".", 1)[0])
                        self.assertEqual(shown, prior, "A player must not see another current ballot before submitting")
                        self.assertEqual([json.loads(value) for value in re.findall(r'"voters":(\[[^\]]*\])', prompt)], [prior])
                    start = next(index for index, event in enumerate(match.events)
                                 if event.msg_type == "pig_turn" and json.loads(event.content)["turn"] == turn)
                    end = next(index for index, event in enumerate(match.events)
                               if event.msg_type == "pig_turn" and json.loads(event.content)["turn"] == turn + 1)
                    records = list(enumerate(match.events[start:end], start))
                    ballots = [(index, event) for index, event in records if event.msg_type == "action"
                               and json.loads(event.content)["phase"] == "pig_reset_vote"]
                    self.assertCountEqual([event.agent_name for _, event in ballots], eligible)
                    self.assertTrue(all(event.visible_to == [event.agent_name] for _, event in ballots))
                    claim = next(json.loads(event.content) for _, event in records if event.msg_type == "pig_claim")
                    if turn == 1:
                        self.assertIn(claim["player"], eligible, "The recipient also participates in the reset batch")
                    final = prior + [name for name in order if name in current_requests and name not in prior]
                    public = [(index, json.loads(event.content)) for index, event in records if event.msg_type == "pig_reset_vote"]
                    self.assertCountEqual([data["player"] for _, data in public], current_requests)
                    for index, data in public:
                        self.assertGreater(index, max(index for index, _ in ballots), "All answers must be recorded before any reset request is public")
                        self.assertTrue(data["simultaneous"])
                        self.assertEqual(data["voters"], final)
                    challenges = [event.agent_name for _, event in records if event.msg_type == "action"
                                  and json.loads(event.content)["phase"] == "pig_challenge"]
                    self.assertEqual(challenges, [next(name for name in order if name not in final)] if len(final) == 3 else [])
                    self.assertEqual(sum(event.msg_type == "pig_reset" for _, event in records), int(len(final) >= 3))
                    prior = [] if len(final) >= 3 else final

    def test_saved_dynamic_game_keeps_four_opening_and_two_pre_deposit_discussions(self):
        match = Match(PLAYERS, 23)
        match.resume_log = SimpleNamespace(resume=True, events=[{"msg_type": "rules", "content": DYNAMIC_MEMORY_HEADING}])
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

    def test_new_game_cli_never_requests_dialogue_or_relationship_assessments(self):
        prompts = []
        matches = []

        def capture_match(match):
            matches.append(match)
            return play(match)

        def reply(prompt):
            prompts.append(prompt)
            if "다음 구간에 남길 기억 세 개를 갱신하세요" in prompt:
                current = json.loads(prompt.rsplit("현재 저금통 번호: ", 1)[1].split(". 기존 기억:", 1)[0])
                action = json.dumps({str(bank): {"black": 77, "white": None} for bank in current[::2]})
            elif "현재 리셋 요청자 " in prompt:
                action = "reset"
            elif "전달받은 위칸 " in prompt:
                action = "0"
            elif "의심(doubt)하거나 통과(pass)하세요" in prompt:
                action = "doubt"
            elif "비공개 관계 평가를 갱신하세요" in prompt:
                action = "{}"
            elif any(f"비공개 전략 준비 {step}/2단계" in prompt for step in (1, 2)):
                action = "개인적으로 판단하고 확신이 있을 때 의심한다."
            else:
                action = json.dumps({"type": "speak", "channel": "public", "text": "WOULD_SPEAK94799"})
            return json.dumps({"action": action, "note": ""})

        with (TemporaryDirectory() as directory,
              patch("games.models.CodexLanguageModel._complete", side_effect=reply),
              redirect_stdout(StringIO()), redirect_stderr(StringIO())):
            output = Path(directory) / "events.jsonl"
            run_cli(capture_match, title=DAY_THREE_PRISON, seats=4,
                    argv=["--seed", "23", "--model", "test-model", "--model-turns", "5000",
                          "--no-allow-review", "--output", str(output)])
            result = json.loads(output.read_text().splitlines()[-1])
            keys = [json.loads(line)["key"] for line in output.with_name("events.decisions.jsonl").read_text().splitlines()]

        match, = matches
        self.assertFalse(match.relationship_reviews_enabled)
        self.assertFalse(any(key[0] == "relationships" for key in keys))
        self.assertTrue(all("비공개 관계 평가를 갱신하세요" not in prompt for prompt in prompts))

        kinds = {event.msg_type for event in match.events}
        self.assertFalse(kinds & {"pig_discussion", "pig_discussion_end", "public", "whisper", "relationship_update"})
        rules = next(event.content for event in match.events if event.msg_type == "rules")
        self.assertIn(NO_DISCUSSION_HEADING, rules)
        self.assertIn(NO_RELATIONSHIP_HEADING, rules)
        self.assertNotIn(SIMULTANEOUS_RESET_HEADING, rules)
        self.assertFalse(any(key[:2] == ["batch", "pig_reset_vote"] for key in keys))
        order = next(json.loads(event.content)["order"] for event in match.events if event.msg_type == "pig_setup")
        reset_inputs = [prompt for prompt in prompts if "현재 리셋 요청자 " in prompt]
        self.assertGreater(result["resets"], 0)
        self.assertEqual([json.loads(prompt.rsplit("현재 리셋 요청자 ", 1)[1].split(".", 1)[0]) for prompt in reset_inputs],
                         [order[:index] for _ in range(result["resets"]) for index in range(3)],
                         "Later seats must see earlier requests, and the third request must stop polling")
        reset_actions = [event for event in match.events if event.msg_type == "action"
                         and json.loads(event.content)["phase"] == "pig_reset_vote"]
        self.assertEqual([event.agent_name for event in reset_actions], order[:3] * result["resets"])
        self.assertTrue(all(event.visible_to == "all" for event in reset_actions))
        public_votes = [json.loads(event.content) for event in match.events if event.msg_type == "pig_reset_vote"]
        self.assertEqual([data["voters"] for data in public_votes],
                         [order[:index] for _ in range(result["resets"]) for index in range(1, 4)])
        self.assertTrue(all("simultaneous" not in data for data in public_votes))
        phases = [json.loads(event.content)["phase"] for event in match.events if event.msg_type == "action"]
        self.assertNotIn("pig_talk", phases)
        self.assertFalse(any(event.msg_type == "invalid_action" and json.loads(event.content)["phase"] == "relationship_review"
                             for event in match.events))
        self.assertEqual(phases.count("pig_memory_update"), len(PLAYERS) * result["turns"])
        self.assertTrue({"pig_deposit", "pig_count", "pig_doubt", "pig_reset_vote"} <= set(phases))
        preparations = [event for event in match.events if event.msg_type == "decision_note"
                        and json.loads(event.content)["phase"] == "pig_preparation"]
        self.assertCountEqual([(event.agent_name, json.loads(event.content)["step"]) for event in preparations],
                              [(name, step) for name in PLAYERS for step in (1, 2)])
        self.assertTrue(all(event.visible_to == [event.agent_name] for event in preparations))
        self.assertEqual(sum(any(f"비공개 전략 준비 {step}/2단계" in prompt for step in (1, 2)) for prompt in prompts), 8)
        self.assertEqual(sum("다음 구간에 남길 기억 세 개를 갱신하세요" in prompt for prompt in prompts),
                         len(PLAYERS) * result["turns"])
        self.assertTrue(all("모두 같은 테이블에 앉아 있습니다. 공개 발언이나" not in prompt for prompt in prompts))
        prep_end = next(index for index, event in enumerate(match.events) if event.msg_type == "pig_preparation_end")
        first_turn = next(index for index, event in enumerate(match.events) if event.msg_type == "pig_turn")
        initial = [json.loads(event.content) for event in match.events[prep_end + 1:first_turn] if event.msg_type == "action"]
        self.assertEqual([action["phase"] for action in initial], ["pig_memory_update"] * len(PLAYERS))
        self.assertTrue(all(set(json.loads(action["action"])) == {"1", "3", "5"} for action in initial))
        self.assertGreaterEqual(max(result["scores"].values()), 5)

    def test_legacy_memory_selections_are_private_fixed_per_reset_and_limit_exact_recalls(self):
        match = Match(PLAYERS, 23)
        match.resume_log = SimpleNamespace(resume=True, events=[{"msg_type": "rules", "content": MEMORY_HEADING}])
        result = play(match)
        slots = {}
        counts = {}
        choices = set()
        epoch = selections = recalls = 0
        for event in match.events:
            if event.msg_type == "action" and json.loads(event.content)["phase"] == "pig_memory_select":
                key = epoch, event.agent_name
                self.assertNotIn(key, choices, "Players may choose new slots only once per reset")
                choices.add(key)
            if not event.msg_type.startswith("pig_"):
                continue
            data = json.loads(event.content)
            if event.msg_type in {"pig_setup", "pig_reset"}:
                epoch = data.get("reset", 0)
                slots.clear()
            elif event.msg_type == "pig_contents":
                counts = data["banks"]
            elif event.msg_type == "pig_memory_selection":
                self.assertEqual(data["reset"], epoch)
                self.assertEqual(data["capacity"], 3)
                self.assertEqual(len(set(data["banks"])), 3)
                self.assertTrue(set(map(str, data["banks"])) <= set(counts))
                if event.agent_name in slots:
                    self.assertEqual(set(data["banks"]), slots[event.agent_name],
                                     "A slot update may only follow the known automatic bank replacement")
                else:
                    slots[event.agent_name] = set(data["banks"])
                    selections += 1
                self.assertEqual(event.visible_to, [event.agent_name])
                for player in PLAYERS:
                    if player != event.agent_name:
                        self.assertNotIn(event, match.observations(player))
            elif event.msg_type == "pig_turn":
                self.assertEqual(set(slots), set(PLAYERS), "Everyone must choose before a future pass target is known")
            elif event.msg_type == "pig_replace":
                for selected in slots.values():
                    if data["old_bank"] in selected:
                        selected.remove(data["old_bank"])
                        selected.add(data["bank"])
            elif event.msg_type == "pig_recall":
                self.assertEqual(event.visible_to, [event.agent_name])
                self.assertEqual(data["reset"], epoch)
                self.assertEqual(set(data["banks"]), set(map(str, slots[event.agent_name])))
                self.assertEqual(data["banks"], {bank: counts[bank] for bank in data["banks"]})
                self.assertEqual(len(data["banks"]), 3)
                recalls += 1
        self.assertEqual(selections, len(PLAYERS) * (result["resets"] + 1))
        self.assertEqual(len(choices), selections)
        self.assertGreater(recalls, selections)

    def test_free_summaries_follow_opening_and_every_nonterminal_turn(self):
        class SummaryMatch(Match):
            def decide_together(self, phase, decisions, **kwargs):
                if phase == "pig_memory_update":
                    turn = next((json.loads(event.content)["turn"] for event in reversed(self.events)
                                 if event.msg_type == "pig_turn"), 0)
                    decisions = {name: replace(decision, default=f"{name} {turn}턴 기억: 1번 흑77, 2번 백9, 3·4·5번 불명. 확신 없으면 의심하지 않는다.")
                                 for name, decision in decisions.items()}
                return super().decide_together(phase, decisions, **kwargs)

        match = SummaryMatch(PLAYERS, 23)
        match.resume_log = SimpleNamespace(resume=True, events=[{"msg_type": "rules", "content": FREE_MEMORY_HEADING}])
        self._assert_end_turn_memory(match, "summary", discussion=True)

    def test_dynamic_slot_updates_can_change_ids_at_every_end_of_turn(self):
        class DynamicMatch(Match):
            def event(self, kind, data, **kwargs):
                super().event(kind, data, **kwargs)
                if isinstance(data, dict) and "lower" in data and "upper" in data:
                    self.live_ids = sorted({bank for bank in (*data["lower"].values(), *data["upper"].values()) if bank is not None})

            def decide_together(self, phase, decisions, **kwargs):
                if phase == "pig_memory_update":
                    values = json.dumps({str(bank): {"black": 77, "white": None} for bank in self.live_ids[::2]})
                    decisions = {name: replace(decision, default=values) for name, decision in decisions.items()}
                return super().decide_together(phase, decisions, **kwargs)

        self._assert_end_turn_memory(DynamicMatch(PLAYERS, 23), "dynamic")

    def _assert_end_turn_memory(self, match, mode, *, discussion=False):
        result = play(match)
        updates = {}
        recalls = set()
        opening_done = False
        resolved_turn = 0
        turn = update_count = 0
        for event in match.events:
            self.assertNotEqual(event.msg_type, "pig_memory_selection")
            if event.msg_type not in {"pig_turn", "pig_deposit", "pig_preparation_end", "pig_discussion_end", "pig_doubt", "pig_pass", "action", "pig_recall"}:
                continue
            data = json.loads(event.content)
            if ((discussion and event.msg_type == "pig_discussion_end" and data["stage"] == "opening")
                    or (not discussion and event.msg_type == "pig_preparation_end")):
                opening_done = True
            elif event.msg_type == "pig_turn":
                self.assertEqual(set(updates), set(PLAYERS), "Everyone must compress opening/previous-turn observations before the next turn")
                self.assertEqual(recalls, set(PLAYERS))
                turn = data["turn"]
                updates, recalls = {}, set()
            elif event.msg_type in {"pig_doubt", "pig_pass"}:
                resolved_turn = data["turn"]
            elif event.msg_type == "pig_deposit":
                self.assertFalse(updates, "Memory is compressed after the whole turn, not immediately after its deposit")
            elif event.msg_type == "action" and data["phase"] == "pig_memory_update":
                self.assertTrue(opening_done)
                self.assertEqual(resolved_turn, turn, "Current outcomes must be available before compression")
                self.assertNotIn(event.agent_name, updates)
                self.assertEqual(event.visible_to, [event.agent_name])
                if mode == "summary":
                    self.assertLessEqual(len(data["action"]), MEMORY_SUMMARY_LIMIT)
                updates[event.agent_name] = data["action"]
                update_count += 1
            elif event.msg_type == "action" and data["phase"] == "pig_reset_vote":
                self.assertFalse(updates, "All reset decisions must precede end-of-turn compression")
            elif event.msg_type == "action":
                self.assertNotEqual(data["phase"], "pig_memory_select")
            elif event.msg_type == "pig_recall" and updates:
                self.assertEqual(set(updates), set(PLAYERS))
                self.assertEqual(data["mode"], mode)
                self.assertEqual(data["updated_turn"], turn)
                if mode == "summary":
                    self.assertEqual(set(data), {"reset", "mode", "updated_turn", "text", "limit"})
                    self.assertEqual(data["text"], updates[event.agent_name])
                    self.assertEqual(data["limit"], MEMORY_SUMMARY_LIMIT)
                else:
                    self.assertEqual(set(data), {"reset", "mode", "updated_turn", "banks"})
                    self.assertEqual(data["banks"], json.loads(updates[event.agent_name]))
                    self.assertEqual(len(data["banks"]), 3)
                recalls.add(event.agent_name)
        self.assertFalse(updates, "A terminal turn must end without another summary round")
        self.assertEqual(update_count, len(PLAYERS) * result["turns"])
        self.assertGreater(result["turns"], 1)

    def test_saved_pre_memory_discussions_resume_without_changing_the_record(self):
        def previous_play(match):
            current_log = match.resume_log
            match.resume_log = SimpleNamespace(
                resume=True, events=[{"msg_type": "rules", "content": old_rules}],
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

        for old_turns, mode in ((1, "none"), (2, "none"), (2, "exact"), (2, "summary"),
                                (2, "dynamic"), (2, "silent"), (2, "silent_noeval"), (2, "simultaneous")):
            old_rules = f"추가 행동 전에는 전원에게 {'한' if old_turns == 1 else '두'} 턴씩" + {
                "none": "", "exact": MEMORY_HEADING, "summary": FREE_MEMORY_HEADING,
                "dynamic": DYNAMIC_MEMORY_HEADING, "silent": DYNAMIC_MEMORY_HEADING + NO_DISCUSSION_HEADING,
                "silent_noeval": DYNAMIC_MEMORY_HEADING + NO_DISCUSSION_HEADING + NO_RELATIONSHIP_HEADING,
                "simultaneous": DYNAMIC_MEMORY_HEADING + NO_DISCUSSION_HEADING + NO_RELATIONSHIP_HEADING + SIMULTANEOUS_RESET_HEADING,
            }[mode]
            with (
                self.subTest(turns=old_turns, mode=mode),
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
                expected_keys = [json.loads(line)["key"] for line in full.with_suffix(".decisions.jsonl").read_text().splitlines()]
                actual_keys = [json.loads(line)["key"] for line in resumed.with_suffix(".decisions.jsonl").read_text().splitlines()]
                self.assertEqual(actual_keys, expected_keys)
                self.assertEqual(any(key[0] == "relationships" for key in expected_keys), mode not in {"silent_noeval", "simultaneous"},
                                 "Saved games must keep their recorded relationship assessment setting")
                self.assertEqual(actual[:len(prefix) - 1], prefix[:-1])
                self.assertEqual(completion.call_count - calls_before,
                                 expected[-1]["model_calls"] - prefix[-1]["model_calls"])
                rules = next(row["content"] for row in actual if row.get("msg_type") == "rules")
                if mode not in {"silent", "silent_noeval", "simultaneous"}:
                    self.assertIn(f"추가 행동 전에는 전원에게 {'한' if old_turns == 1 else '두'} 턴씩", rules)
                self.assertEqual(MEMORY_HEADING in rules, mode == "exact")
                windows = [json.loads(row["content"]) for row in actual if row.get("msg_type") == "pig_discussion"]
                if mode in {"silent", "silent_noeval", "simultaneous"}:
                    self.assertFalse(windows)
                else:
                    self.assertEqual(windows[0]["turns"], 4)
                    self.assertTrue(all(window["turns"] == old_turns for window in windows[1:]))
                self.assertEqual(FREE_MEMORY_HEADING in rules, mode == "summary")
                self.assertEqual(DYNAMIC_MEMORY_HEADING in rules, mode in {"dynamic", "silent", "silent_noeval", "simultaneous"})
                self.assertEqual(NO_DISCUSSION_HEADING in rules, mode in {"silent", "silent_noeval", "simultaneous"})
                self.assertEqual(NO_RELATIONSHIP_HEADING in rules, mode in {"silent_noeval", "simultaneous"})
                self.assertEqual(SIMULTANEOUS_RESET_HEADING in rules, mode == "simultaneous")
                self.assertTrue(all(("simultaneous" in json.loads(row["content"])) == (mode == "simultaneous") for row in actual
                                    if row.get("msg_type") == "pig_reset_vote"))
                self.assertEqual(any(row.get("msg_type") == "pig_memory_selection" for row in actual), mode == "exact")
                self.assertEqual(any(row.get("msg_type") == "action" and
                                     json.loads(row["content"])["phase"] == "pig_memory_update" for row in actual),
                                 mode in {"summary", "dynamic", "silent", "silent_noeval", "simultaneous"})
                for row in actual:
                    if row.get("msg_type") == "pig_recall":
                        self.assertEqual(set(json.loads(row["content"])), {"reset", "banks"} if mode == "exact" else
                                         {"reset", "mode", "updated_turn", "text", "limit"} if mode == "summary" else
                                         {"reset", "mode", "updated_turn", "banks"})

    def test_interrupted_model_decisions_resume_to_the_same_record(self):
        def reply(prompt):
            if "다음 구간에 남길 기억 세 개를 갱신하세요" in prompt:
                current = json.loads(prompt.rsplit("현재 저금통 번호: ", 1)[1].split(". 기존 기억:", 1)[0])
                action = json.dumps({str(bank): {"black": 77, "white": None} for bank in current[::2]})
            else:
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
            retained = next(json.loads(row["content"])["banks"] for row in expected
                            if row.get("msg_type") == "pig_recall" and row["agent_name"] == "P01"
                            and any(counts["black"] == 77 for counts in json.loads(row["content"])["banks"].values()))
            self.assertEqual(set(retained), {"1", "3", "5"})
            self.assertTrue(all(counts == {"black": 77, "white": None} for counts in retained.values()))
            for checkpoint in ("pig_memory_update_initial", "pig_recall_update", "pig_deposit", "pig_doubt",
                               "pig_reset_ballot", "pig_reset_fourth_ballot", "pig_reset_vote", "pig_memory_update_later",
                               "pig_reset", "pig_memory_update_after_reset"):
                with self.subTest(checkpoint=checkpoint):
                    resumed = Path(directory) / f"resumed-{checkpoint}.jsonl"

                    def interrupt(match, kind, data, **kwargs):
                        original_event(match, kind, data, **kwargs)
                        if checkpoint.startswith("pig_memory_update_"):
                            reached = kind == "action" and data["phase"] == "pig_memory_update"
                            if checkpoint.endswith("initial"):
                                reached = reached and not any(event.msg_type == "pig_turn" for event in match.events)
                            elif checkpoint.endswith("later"):
                                reached = reached and any(event.msg_type == "pig_deposit" for event in match.events)
                            else:
                                reached = reached and any(event.msg_type == "pig_reset" for event in match.events)
                        elif checkpoint == "pig_recall_update":
                            reached = kind == "pig_recall" and any(event.msg_type == "action" and
                                      json.loads(event.content)["phase"] == "pig_memory_update" for event in match.events)
                        elif checkpoint in {"pig_reset_ballot", "pig_reset_fourth_ballot"}:
                            reached = kind == "action" and data["phase"] == "pig_reset_vote"
                            if checkpoint.endswith("fourth_ballot"):
                                reached = reached and sum(event.msg_type == "action" and
                                          json.loads(event.content)["phase"] == "pig_reset_vote" for event in match.events) == len(PLAYERS)
                        else:
                            reached = kind == checkpoint
                        if reached:
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
