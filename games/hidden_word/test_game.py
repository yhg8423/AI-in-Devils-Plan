from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict, replace
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from ..match import DAY_FIVE_MAIN, Match, encode, run_cli
from ..resume import MatchLog
from . import game
from .words import ENVELOPES


PLAYERS = tuple(f"P{number:02}" for number in range(1, 7))


def events(match, kind):
    return [json.loads(event.content) for event in match.events if event.msg_type == kind]


class WrongGuesses(Match):
    def decide_together(self, phase, decisions, **kwargs):
        if phase == "word_guess":
            decisions = {name: replace(decision, default=encode({"answers": ["우주선"], "spend": False}))
                         for name, decision in decisions.items()}
        return super().decide_together(phase, decisions, **kwargs)


class HiddenWordTest(unittest.TestCase):
    def test_extra_answer_cost_is_limited_to_one_per_secret(self):
        two = encode({"answers": ["바다", "강"], "spend": True})
        self.assertEqual(game.parse_guesses(two, 1, False), (["바다", "강"], True))
        for pieces, spent in ((0, False), (1, True)):
            with self.assertRaises(ValueError):
                game.parse_guesses(two, pieces, spent)
        invalid = [
            {"answers": ["바다", "강"], "spend": False},
            {"answers": ["바다", "바다"], "spend": True},
            {"answers": ["바다"], "spend": True},
            {"answers": ["바다"], "spend": 1},
            {"answers": ["sea"], "spend": False},
            {"answers": [{}], "spend": False},
        ]
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                game.parse_guesses(encode(payload), 3, False)
        self.assertEqual(game.parse_guesses('{"answers":[],"spend":false}', 0, True), ([], False))

    def test_similarity_rejects_invalid_numbers_and_types(self):
        self.assertEqual(game.similarity_result('{"similarity":95.001,"noun":true}'),
                         {"similarity": 95.001, "noun": True})
        for value in (True, -1, 101, float("nan"), float("inf"), 10 ** 400, "96"):
            with self.subTest(value=str(value)[:30]), self.assertRaises(ValueError):
                game.similarity_result(encode({"similarity": value, "noun": True}))
        with self.assertRaises(ValueError):
            game.similarity_result('{"similarity":80,"noun":1}')

    def test_two_round_scores_and_complete_tie_order(self):
        match = WrongGuesses(PLAYERS, 7)
        result = game.play(match)
        self.assertEqual(result["scores"], dict.fromkeys(PLAYERS, 18))
        self.assertEqual(result["ranking"], result["tie_order"])
        self.assertEqual(result["living"], result["ranking"][:2])
        self.assertEqual(result["prison"], result["ranking"][2:5])
        self.assertEqual(result["eliminated"], result["ranking"][5:])
        self.assertEqual(result["pieces_awarded"], {result["ranking"][0]: 4})
        self.assertEqual(result["pieces"][result["ranking"][0]], 5)
        verdicts = events(match, "word_verdict")
        self.assertEqual(len(verdicts), 36)
        self.assertEqual([next(iter(verdict["points"].values())) for verdict in verdicts[:3]], [1, 2, 3])
        self.assertEqual([next(iter(verdict["points"].values())) for verdict in verdicts[-3:]], [2, 4, 6])

    def test_piece_extra_answer_resets_for_new_secret_but_not_next_phase(self):
        class PaidGuesses(WrongGuesses):
            def decide_together(self, phase, decisions, **kwargs):
                if phase != "word_guess":
                    return super().decide_together(phase, decisions, **kwargs)
                extra = encode({"answers": ["우주선", "비행선"], "spend": True})
                first_phase = events(self, "word_phase")[-1]["phase"] == 1
                for decision in decisions.values():
                    if decision.accepts(extra) != first_phase:
                        raise AssertionError("추가 답 허용 상태가 차례와 단계를 따르지 않습니다.")
                if first_phase:
                    decisions = {name: replace(decision, default=extra) for name, decision in decisions.items()}
                    return Match.decide_together(self, phase, decisions, **kwargs)
                return super().decide_together(phase, decisions, **kwargs)

        match = PaidGuesses(PLAYERS, 2, pieces=[20] * 6)
        result = game.play(match)
        for name in PLAYERS:
            paid = [event for event in match.events if event.msg_type == "word_guess" and event.agent_name == name
                    and json.loads(event.content)["spent"]]
            self.assertEqual(len(paid), 10)
            self.assertEqual(result["pieces"][name], 10 + result["pieces_awarded"].get(name, 0))

    def test_correct_guess_on_phase_two_earns_one_and_ends_secret(self):
        class CorrectSecond(WrongGuesses):
            def decide_together(self, phase, decisions, **kwargs):
                if phase != "word_guess" or events(self, "word_phase")[-1]["phase"] != 2:
                    return super().decide_together(phase, decisions, **kwargs)
                stage = events(self, "word_phase")[-1]
                secret = next(record["word"] for record in events(self, "word_secret")
                              if record["round"] == stage["round"] and record["setter"] == stage["setter"])
                answers = {name: replace(decision, default=encode({"answers": [secret], "spend": False}))
                           for name, decision in decisions.items()}
                return Match.decide_together(self, phase, answers, **kwargs)

        match = CorrectSecond(PLAYERS, 8)
        game.play(match)
        verdicts = events(match, "word_verdict")
        self.assertEqual(len(verdicts), 24)
        for verdict in verdicts:
            if verdict["phase"] == 1:
                self.assertIsNone(verdict["word"])
                self.assertFalse(verdict["end"])
                self.assertEqual(verdict["points"], {verdict["setter"]: verdict["round"]})
            else:
                self.assertEqual(len(verdict["correct"]), 5)
                self.assertTrue(verdict["end"])
                self.assertNotIn(verdict["setter"], verdict["points"])
                self.assertEqual(set(verdict["points"].values()), {verdict["round"]})

    def test_five_inherited_survivors_play_without_adding_returnee(self):
        match = WrongGuesses(PLAYERS[:5], 8)
        result = game.play(match)
        self.assertEqual(set(result["ranking"]), set(PLAYERS[:5]))
        self.assertEqual(len(result["living"]), 2)
        self.assertEqual(len(result["prison"]), 2)
        self.assertEqual(len(result["eliminated"]), 1)
        self.assertEqual(len(events(match, "word_envelope")), 5)
        self.assertEqual(len(events(match, "word_secret")), 10)
        self.assertEqual(result["scores"], dict.fromkeys(PLAYERS[:5], 18))

    def test_cli_records_five_or_six_player_match(self):
        with TemporaryDirectory() as directory, redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            for count in (5, 6):
                path = Path(directory) / f"{count}.jsonl"
                run_cli(game.play, title=DAY_FIVE_MAIN, seats=(6, 5),
                        argv=["--players", *PLAYERS[:count], "--output", str(path)])
                records = [json.loads(line) for line in path.read_text().splitlines()]
                self.assertEqual(records[0]["players"], list(PLAYERS[:count]))
                self.assertEqual(records[-1]["type"], "result")
                self.assertEqual(len(records[-1]["ranking"]), count)

    def test_private_envelopes_secrets_and_hints_are_only_visible_to_owner(self):
        match = WrongGuesses(PLAYERS, 9)
        game.play(match)
        self.assertEqual(len(events(match, "word_envelope")), 6)
        self.assertEqual({tuple(record["words"]) for record in events(match, "word_envelope")}, set(ENVELOPES))
        secrets = events(match, "word_secret")
        for name in PLAYERS:
            own = [record["word"] for record in secrets if record["setter"] == name]
            self.assertEqual(len(set(own)), 2)
        for event in match.events:
            if event.msg_type in {"word_envelope", "word_secret", "word_hint", "word_guess", "decision_note"}:
                self.assertEqual(event.visible_to, [event.agent_name])
            if event.msg_type == "word_similarity":
                self.assertNotIn("word", json.loads(event.content))
                self.assertEqual(event.visible_to, "all")
            if event.msg_type == "action":
                self.assertEqual(event.visible_to, [event.agent_name])
        for record in events(match, "word_verdict"):
            self.assertEqual(record["word"] is None, not record["end"])

    def test_threshold_is_strict_and_fallback_uses_first_highest_current_hint(self):
        for score, expected_count, forced in ((95, 10, True), (95.01, 1, False)):
            match = WrongGuesses(PLAYERS, 3)
            with patch.object(game, "_judge", return_value={"similarity": score, "noun": True, "mode": "scripted"}):
                game.play(match)
            clues = events(match, "word_clue")
            hints = events(match, "word_hint")
            self.assertEqual(len(hints), len(clues) * expected_count)
            for clue in clues:
                current = [hint for hint in hints if all(hint[key] == clue[key] for key in ("round", "setter", "phase"))]
                self.assertEqual(clue["word"], current[0]["word"])
                self.assertEqual(clue["forced"], forced)

    def test_invalid_noun_consumes_opportunity_without_substitution_or_word_leak(self):
        match = WrongGuesses(PLAYERS, 4)
        with patch.object(game, "_judge", return_value={"similarity": 99, "noun": False, "mode": "ai"}):
            game.play(match)
        clues = events(match, "word_clue")
        self.assertTrue(all(clue["word"] is None for clue in clues))
        self.assertEqual(len(events(match, "word_hint")), len(clues) * 10)
        self.assertTrue(all(record["similarity"] is None and record["valid"] is False
                            for record in events(match, "word_similarity")))

    def test_deadlines_are_cumulative_and_late_guesses_do_not_spend_pieces(self):
        class SlowMatch(WrongGuesses):
            def decide_together(self, phase, decisions, **kwargs):
                if phase == "word_guess":
                    decisions = {name: replace(decision, default=encode({
                        "answers": ["우주선", "비행선"], "spend": True})) for name, decision in decisions.items()}
                    answers = Match.decide_together(self, phase, decisions, **kwargs)
                else:
                    answers = super().decide_together(phase, decisions, **kwargs)
                if phase in {"word_hint", "word_guess_preparation", "word_guess"}:
                    seconds = 600 if phase == "word_hint" else 160
                    kwargs["response_times"].update(dict.fromkeys(decisions, seconds * 1_000_000_000))
                return answers

        match = SlowMatch(PLAYERS, 5, pieces=[2] * 6)
        with patch.object(game, "_judge", return_value={"similarity": 50, "noun": True, "mode": "scripted"}):
            result = game.play(match)
        self.assertEqual(len(events(match, "word_hint")), 36)
        self.assertTrue(all(record["answers"] == [] and record["spent"] == 0 for record in events(match, "word_guess")))
        for name, balance in result["pieces"].items():
            self.assertEqual(balance, 2 + result["pieces_awarded"].get(name, 0))

    def test_judge_is_isolated_cached_and_retries_malformed_response(self):
        model = Mock()
        model.sample_text.side_effect = ["bad", '{"similarity":87,"noun":true}']
        match = Match(PLAYERS, 1, models={"P01": model}, live_turns=10)
        match.event("private_test", "협상 비밀 문장", private=["P01"])
        cache = {}
        first = game._judge(match, "P01", "바다", "파도", cache)
        self.assertEqual(first["similarity"], 87)
        self.assertEqual(game._judge(match, "P02", "바다", "파도", cache), first)
        self.assertEqual(model.sample_text.call_count, 2)
        self.assertEqual(match.live_turns, 8)
        self.assertNotIn("협상 비밀 문장", model.sample_text.call_args.kwargs["prompt"])
        self.assertEqual(len(events(match, "invalid_action")), 1)
        model.sample_text.side_effect = ['{"similarity":NaN,"noun":true}', "bad"]
        with self.assertRaisesRegex(RuntimeError, "유사도 판정"):
            game._judge(match, "P01", "바다", "하늘", cache)
        self.assertNotIn(("바다", "하늘"), cache)

    def test_similarity_journal_replays_without_model_call_then_cache_reuses_pair(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            model = Mock()
            model.sample_text.return_value = '{"similarity":89,"noun":true}'
            header = {"type": "match", "game": "히든 워드 재개 테스트"}
            for resuming in (False, True):
                with MatchLog(path, resume=resuming) as log:
                    log.write(header)
                    match = Match(PLAYERS, 1, models={"P01": model}, live_turns=10,
                        resume_log=log, count_calls=lambda: model.sample_text.call_count,
                        on_event=lambda event: log.write({"type": "event", **asdict(event), "model_calls": 1}))
                    match.event("before_similarity", {})
                    cache = {}
                    verdict = game._judge(match, "P01", "바다", "파도", cache)
                    match.event("after_similarity", verdict)
                    self.assertEqual(match.live_turns, 9)
                    self.assertEqual(game._judge(match, "P02", "바다", "파도", cache), verdict)
                    log.write({"type": "interrupted", "model_calls": 1})
            model.sample_text.assert_called_once()


if __name__ == "__main__":
    unittest.main()
