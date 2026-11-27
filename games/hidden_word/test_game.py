from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from io import StringIO
import json
from math import sqrt
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
from unicodedata import normalize

from ..match import DAY_FIVE_MAIN, Match, encode, run_cli
from ..models import StrategyNote
from . import __main__ as cli, game
from .vectors import WordVectors
from .words import ASSOCIATIONS, DECK_SHA256, ENVELOPES, WORDS


PLAYERS = tuple(f"P{number:02}" for number in range(1, 7))


def events(match, kind):
    return [json.loads(event.content) for event in match.events if event.msg_type == kind]


class WrongGuesses(Match):
    def decide_together(self, phase, decisions, **kwargs):
        if phase == "word_guess":
            decisions = {name: replace(decision, default=encode({"answers": ["우주선"], "spend": False}))
                         for name, decision in decisions.items()}
        return super().decide_together(phase, decisions, **kwargs)


class OutsideHints(WrongGuesses):
    hint = "미등재용어"

    def decide_together(self, phase, decisions, **kwargs):
        if phase == "word_hint":
            decisions = {name: replace(decision, default=self.hint) for name, decision in decisions.items()}
        return super().decide_together(phase, decisions, **kwargs)


class HiddenWordTest(unittest.TestCase):
    def setUp(self):
        vocabulary = ["대양", *sorted(set(WORDS).union(*(set(hints) for hints in ASSOCIATIONS.values())))]
        self.vectors = WordVectors(vocabulary, [[1, 0] for _ in vocabulary])
        loader = patch.object(game, "load_vectors", return_value=self.vectors)
        loader.start()
        self.addCleanup(loader.stop)

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

    def test_no_relationship_reviews_during_play_or_generic_final_checkpoint(self):
        previous = {PLAYERS[0]: {PLAYERS[1]: {"affinity": 65, "trust": 40, "reason": "이전 경기 근거"}}}
        match = WrongGuesses(PLAYERS, 7, relationships=previous)
        with patch.object(match, "review_relationships", side_effect=AssertionError("no review checkpoints")):
            game.play(match)
        self.assertFalse(match.relationship_reviews_enabled)
        self.assertEqual(match.relationships[PLAYERS[0]], previous[PLAYERS[0]])
        self.assertFalse(events(match, "relationship_update"))
        self.assertTrue(events(match, "decision_note"))
        self.assertIs(events(match, "word_setup")[0]["relationship_reviews"], False)
        model = Mock()
        match.models = {PLAYERS[0]: model}
        match.backends = {PLAYERS[0]: object()}
        match.live_turns = 100
        match.review_relationships("매치 종료")
        model.sample_text.assert_not_called()
        self.assertEqual(match.live_turns, 100)

    def test_live_players_have_private_strategy_without_discussion_or_room_actions(self):
        class LiveMatch(Match):
            def __init__(self):
                super().__init__(PLAYERS, 7, live_turns=5000)
                self.backends = dict.fromkeys(PLAYERS, object())
                self.queries, self.checkpoints = [], []

            def decide_together(self, phase, decisions, **kwargs):
                self.current_phase = phase
                self.defaults = {name: encode({"answers": ["우주선"], "spend": False})
                                 if phase == "word_guess" else decision.default
                                 for name, decision in decisions.items()}
                return super().decide_together(phase, decisions, **kwargs)

            def request_action(self, name, phase, prompt, default, **kwargs):
                if phase != "word_envelope":
                    raise AssertionError(f"Unexpected individual action: {phase}")
                self.current_phase, self.defaults = phase, {name: default}
                return super().request_action(name, phase, prompt, default, **kwargs)

            def _query(self, name, prompt, *args, **kwargs):
                stage = next((json.loads(event.content) for event in reversed(self.events)
                              if event.msg_type == "word_phase"), {})
                self.queries.append((self.current_phase, name, prompt, stage))
                return self.defaults[name], StrategyNote(text="공개된 정보로 내 계획을 검토한다.")

            def review_relationships(self, checkpoint):
                self.checkpoints.append(checkpoint)

        match = LiveMatch()
        result = game.play(match)
        self.assertTrue(match.queries)
        self.assertLess(match.live_turns, 5000)
        self.assertEqual(result["scores"], dict.fromkeys(PLAYERS, 18))
        self.assertIs(events(match, "word_setup")[0]["discussion"], False)
        forbidden = {"public", "whisper", "room", "room_move", "room_invite", "room_invite_response", "discussion_note"}
        self.assertFalse(any(event.msg_type in forbidden or event.msg_type.startswith("word_discussion")
                             for event in match.events))
        self.assertNotIn("word_discussion", {phase for phase, _, _, _ in match.queries})
        for phase in ("word_preparation", "word_guess_preparation"):
            notes = [event for event in match.events if event.msg_type == "decision_note"
                     and json.loads(event.content)["phase"] == phase]
            self.assertEqual({note.agent_name for note in notes}, set(PLAYERS))
            self.assertTrue(all(note.visible_to == [note.agent_name] for note in notes))
        actions = events(match, "action")
        self.assertFalse(any(action["phase"].startswith("word_discussion") for action in actions))
        self.assertEqual(match.checkpoints, [])
        self.assertFalse(match.relationship_reviews_enabled)
        first = events(match, "word_hint")[0]
        for kind in ("word_hint", "word_guess_preparation", "word_guess"):
            prompts = [prompt for phase, _, prompt, stage in match.queries if phase == kind
                       and stage == {"round": first["round"], "setter": first["setter"], "phase": 3}]
            self.assertTrue(prompts)
            self.assertTrue(all(encode(first) in prompt for prompt in prompts))
        for kind, _, prompt, stage in match.queries:
            if kind not in {"word_hint", "word_guess_preparation", "word_guess"}:
                continue
            history, _ = json.JSONDecoder().raw_decode(prompt.split("모든 공개 후보와 보정 점수: ", 1)[1])
            self.assertTrue(all(item["setter"] == stage["setter"] and item["round"] == stage["round"]
                                and item["phase"] <= stage["phase"] for item in history))
        second = events(match, "word_turn")[1]
        next_prompt = next(prompt for phase, _, prompt, stage in match.queries if phase == "word_hint"
                           and stage == {"round": second["round"], "setter": second["setter"], "phase": 1})
        self.assertIn("모든 공개 후보와 보정 점수: []", next_prompt)
        self.assertNotIn(encode(first), next_prompt)

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
        self.assertEqual(result["living"], result["ranking"][:1])
        self.assertEqual(result["prison"], result["ranking"][1:4])
        self.assertEqual(len(result["eliminated"]), 1)
        self.assertEqual(len(events(match, "word_envelope")), 5)
        self.assertEqual(len(events(match, "word_secret")), 10)
        self.assertEqual(result["scores"], dict.fromkeys(PLAYERS[:5], 18))

    def test_legacy_five_player_resume_preserves_two_prisoners(self):
        def interrupt(match):
            record = match.on_event
            def stop(event):
                record(event)
                if event.msg_type == "word_setup":
                    raise RuntimeError("test interruption")
            match.on_event = stop
            return game.play(match)

        with TemporaryDirectory() as directory, redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            path = Path(directory) / "events.jsonl"
            with self.assertRaisesRegex(RuntimeError, "interruption"):
                run_cli(interrupt, title=DAY_FIVE_MAIN, seats=(6, 5),
                        argv=["--players", *PLAYERS[:5], "--output", str(path)])
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            for row in rows:
                if row.get("msg_type") == "rules":
                    row["content"] = row["content"].replace(game.ASSIGNMENTS, game.LEGACY_ASSIGNMENTS)
                if row.get("msg_type") == "word_setup":
                    setup = json.loads(row["content"])
                    del setup["prison_seats"]
                    row["content"] = encode(setup)
            path.write_text("".join(encode(row) + "\n" for row in rows))
            run_cli(game.play, title=DAY_FIVE_MAIN, seats=(6, 5), argv=["--resume", "--output", str(path)])
            result = json.loads(path.read_text().splitlines()[-1])
            self.assertEqual(len(result["living"]), 2)
            self.assertEqual(len(result["prison"]), 2)

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

    def test_candidates_are_public_while_envelopes_secrets_and_guesses_stay_private(self):
        match = WrongGuesses(PLAYERS, 9)
        game.play(match)
        self.assertEqual(len(events(match, "word_envelope")), 6)
        self.assertEqual({tuple(record["words"]) for record in events(match, "word_envelope")}, set(ENVELOPES))
        secrets = events(match, "word_secret")
        for name in PLAYERS:
            own = [record["word"] for record in secrets if record["setter"] == name]
            self.assertEqual(len(set(own)), 2)
        for event in match.events:
            if event.msg_type in {"word_envelope", "word_secret", "word_guess", "decision_note"}:
                self.assertEqual(event.visible_to, [event.agent_name])
            if event.msg_type == "word_similarity":
                record = json.loads(event.content)
                self.assertIn("word", record)
                self.assertNotIn("nearest", record)
                self.assertNotIn("cutoff", record)
                self.assertNotIn("maximum", record)
                self.assertNotIn("raw_similarity", record)
                self.assertIsInstance(record["qualifies"], bool)
                self.assertEqual(event.visible_to, "all")
            if event.msg_type == "word_hint":
                record = json.loads(event.content)
                self.assertEqual(event.visible_to, "all")
                self.assertTrue(all(event in match.observations(name) for name in PLAYERS))
                self.assertTrue(self.vectors.is_hint(record["word"]))
                self.assertNotIn("nearest", record)
                self.assertNotIn("cutoff", record)
                self.assertNotIn("maximum", record)
                self.assertNotIn("raw_similarity", record)
            if event.msg_type == "action":
                self.assertEqual(event.visible_to, [event.agent_name])
        for record in events(match, "word_verdict"):
            self.assertEqual(record["word"] is None, not record["end"])
        self.assertEqual(events(match, "word_hint"), events(match, "word_similarity"))
        self.assertEqual(events(match, "word_setup")[0]["hint_visibility"], "public")

    def test_threshold_is_strict_and_fallback_searches_full_vocabulary(self):
        for score, expected_count, forced in ((57, 10, True), (57.01, 1, False), (58, 1, False)):
            match = WrongGuesses(PLAYERS, 3)
            with (patch.object(self.vectors, "nearest", return_value={"word": "대양", "similarity": 60}),
                  patch.object(game, "_judge", return_value={"similarity": score, "valid": True, "mode": "openai"})):
                game.play(match)
            clues = events(match, "word_clue")
            hints = events(match, "word_hint")
            self.assertEqual(len(hints), len(clues) * expected_count)
            for clue in clues:
                current = [hint for hint in hints if all(hint[key] == clue[key] for key in ("round", "setter", "phase"))]
                if forced:
                    self.assertEqual(clue["word"], "대양")
                    self.assertNotIn(clue["word"], [hint["word"] for hint in current])
                    self.assertEqual(clue["source"], "openai_stdict_nearest")
                else:
                    self.assertEqual(clue["word"], current[0]["word"])
                    self.assertEqual(clue["source"], "submitted_hint")
                self.assertEqual(clue["forced"], forced)
                self.assertTrue(all(hint["qualifies"] is not forced for hint in current))
                self.assertTrue(all(hint["score_display"] == "nearest_noun_99_9" for hint in current))
                self.assertAlmostEqual(current[0]["similarity"], score / 60 * 100)
                self.assertEqual(clue["score_display"], "nearest_noun_99_9")
                if forced:
                    self.assertEqual(clue["similarity"], 99.9)
            self.assertEqual(events(match, "word_setup")[0]["fallback"], "vocabulary_nearest")
            self.assertEqual(events(match, "word_setup")[0]["version"], 4)
            self.assertEqual(events(match, "word_setup")[0]["score_mode"], "openai")
            self.assertEqual(events(match, "word_setup")[0]["reveal_rule"], "nearest_noun_ratio_v1")
            self.assertEqual(events(match, "word_setup")[0]["hint_filter"], "openai_text_embedding_v1")
            self.assertEqual(events(match, "word_setup")[0]["scorer"], game.scorer_metadata(self.vectors))
            self.assertEqual(events(match, "word_setup")[0]["score_display"], "nearest_noun_99_9")
            self.assertEqual(events(match, "word_setup")[0]["score_ceiling"], 99.9)
            self.assertIn("정답을 제외한 최근접 사전 명사를 99.9점으로 놓고 보정합니다.", game.RULES)
            self.assertIn("기준을 넘지 못하면 제출한 힌트와 관계없이 표준국어대사전 명사 전체에서", game.RULES)
            self.assertIn("표준국어대사전 명사 213,810개와 OpenAI text-embedding-3-large 임베딩을 사용합니다.", game.RULES)

    def test_same_raw_pair_has_target_specific_corrected_score(self):
        vocabulary = [*self.vectors._words, "연안"]
        special = {"학교": [1, 0, 0, 0, 0], "병원": [0.5, sqrt(0.75), 0, 0, 0],
                   "대양": [0.52, 0, sqrt(1 - 0.52 ** 2), 0, 0],
                   "연안": [0.3, 0.6 * sqrt(0.75), 0, 0.8, 0]}
        vectors = WordVectors(vocabulary, [special.get(word, [0, 0, 0, 0, 1]) for word in vocabulary])

        class PairHints(WrongGuesses):
            def decide_together(self, phase, decisions, **kwargs):
                if phase == "word_secret":
                    decisions = {name: replace(decision, default=next(
                        (word for word in ("학교", "병원") if word in decision.options), decision.default))
                        for name, decision in decisions.items()}
                elif phase == "word_hint":
                    stage = events(self, "word_phase")[-1]
                    secret = next(record["word"] for record in events(self, "word_secret")
                                  if record["round"] == stage["round"] and record["setter"] == stage["setter"])
                    if secret in ("학교", "병원"):
                        hint = "병원" if secret == "학교" else "학교"
                        decisions = {name: replace(decision, default=hint) for name, decision in decisions.items()}
                return super().decide_together(phase, decisions, **kwargs)

        match = PairHints(PLAYERS, 4)
        game.play(match, vectors=vectors)
        for secret, expected in (("학교", True), ("병원", False)):
            owner = next(record["setter"] for record in events(match, "word_secret")
                         if record["round"] == 1 and record["word"] == secret)
            records = [record for record in events(match, "word_similarity") if record["round"] == 1 and record["setter"] == owner]
            self.assertEqual({record["qualifies"] for record in records}, {expected})
            for record in records:
                corrected = vectors.similarity("학교", "병원") / vectors.nearest(secret)["similarity"] * 100
                self.assertAlmostEqual(record["similarity"], corrected, places=5)

    def test_registered_korean_dictionary_nouns_are_accepted(self):
        registered = ("명사", "강", "바다", "봄", "별", "쾨펜", "ㄱ")
        vocabulary = [*self.vectors._words, *(word for word in registered if word not in self.vectors)]
        vectors = WordVectors(vocabulary, [[1, 0] for _ in vocabulary])
        for word in registered:
            with self.subTest(word=word):
                self.assertTrue(game._judge(vectors, "도서관", word, {})["valid"])

        class DictionaryHints(WrongGuesses):
            def decide_together(self, phase, decisions, **kwargs):
                if phase == "word_hint":
                    for decision in decisions.values():
                        self_test.assertTrue(decision.accepts(hint))
                        self_test.assertNotIn("고유명사, 정답 자체와 설명을 제외", decision.prompt)
                    decisions = {name: replace(decision, default=hint) for name, decision in decisions.items()}
                return super().decide_together(phase, decisions, **kwargs)

        self_test = self
        for hint in ("명사", "쾨펜", "ㄱ"):
            with self.subTest(submitted_hint=hint):
                match = DictionaryHints(PLAYERS, 4)
                game.play(match, vectors=vectors)
                records = events(match, "word_similarity")
                self.assertEqual({record["word"] for record in records}, {hint})
                self.assertTrue(all(record["valid"] and record["qualifies"] for record in records))
                self.assertFalse(any(event.msg_type == "invalid_action" for event in match.events))
        self.assertIn("제출 힌트는 사전 등재 여부와 관계없이 임베딩으로 채점합니다.", game.RULES)

    def test_outside_dictionary_hint_is_scored_without_changing_reference_maximum(self):
        with (patch.object(self.vectors, "is_hint", side_effect=AssertionError("must not gate submitted hints")),
              patch.object(self.vectors, "hint_similarity", return_value=98) as scorer):
            cache = {}
            judgement = game._judge(self.vectors, "학교", "미등재용어", cache)
            self.assertEqual(judgement, {"similarity": 98, "valid": True, "mode": "openai"})
            self.assertEqual(game._judge(self.vectors, "학교", "미등재용어", cache), judgement)
            scorer.assert_called_once_with("학교", "미등재용어")

        original_metadata = self.vectors.metadata.copy()
        match = OutsideHints(PLAYERS, 4)
        with (patch.object(self.vectors, "hint_similarity", return_value=98),
              patch.object(self.vectors, "nearest", return_value={"word": "대양", "similarity": 60})):
            game.play(match)
        clues = events(match, "word_clue")
        self.assertTrue(all(clue["word"] == "미등재용어" and clue["source"] == "submitted_hint" and not clue["forced"] for clue in clues))
        self.assertEqual(len(events(match, "word_hint")), len(clues))
        self.assertTrue(all(record["similarity"] == 99.9 and record["valid"] and record["qualifies"]
                            and "reason" not in record for record in events(match, "word_similarity")))
        self.assertEqual({record["word"] for record in events(match, "word_hint")}, {"미등재용어"})
        self.assertEqual({record["word"] for record in events(match, "word_similarity")}, {"미등재용어"})
        self.assertNotIn("미등재용어", self.vectors)
        self.assertEqual(self.vectors.metadata, original_metadata)
        self.assertFalse(any(event.msg_type == "invalid_action" for event in match.events))

    def test_hint_normalization_precedes_scoring_and_rejects_secret_variants(self):
        self_test = self

        class NormalizedHints(OutsideHints):
            def decide_together(self, phase, decisions, **kwargs):
                if phase == "word_hint":
                    stage = events(self, "word_phase")[-1]
                    secret = next(item["word"] for item in events(self, "word_secret")
                                  if item["round"] == stage["round"] and item["setter"] == stage["setter"])
                    for decision in decisions.values():
                        for forbidden in ("  ", secret, " " + secret + " ", normalize("NFD", secret)):
                            self_test.assertFalse(decision.accepts(forbidden))
                        self_test.assertNotIn("사전 등재 명사", decision.prompt)
                return super().decide_together(phase, decisions, **kwargs)

        match = NormalizedHints(PLAYERS, 4)
        match.hint = "  " + normalize("NFD", "명사표현") + "  "
        with patch.object(self.vectors, "hint_similarity", return_value=100) as scorer:
            game.play(match)
        self.assertEqual({record["word"] for record in events(match, "word_hint")}, {"명사표현"})
        self.assertTrue(all(call.args[1] == "명사표현" for call in scorer.call_args_list))

    def test_hint_embedding_failure_interrupts_without_invalid_or_numeric_event(self):
        match = OutsideHints(PLAYERS, 4)
        with patch.object(self.vectors, "hint_similarity", side_effect=RuntimeError("embedding unavailable")):
            with self.assertRaisesRegex(RuntimeError, "embedding unavailable"):
                game.play(match)
        self.assertFalse(events(match, "word_hint"))
        self.assertFalse(events(match, "word_similarity"))
        self.assertFalse(any(event.msg_type == "invalid_action" for event in match.events))

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
                    seconds = hint_seconds if phase == "word_hint" else 160
                    kwargs["response_times"].update(dict.fromkeys(decisions, seconds * 1_000_000_000))
                return answers

        for hint_seconds, expected_hints in ((600, 36), (901, 0)):
            match = SlowMatch(PLAYERS, 5, pieces=[2] * 6)
            with patch.object(game, "_judge", return_value={"similarity": 50, "valid": True, "mode": "openai"}):
                result = game.play(match)
            self.assertEqual(len(events(match, "word_hint")), expected_hints)
            self.assertEqual({clue["word"] for clue in events(match, "word_clue")}, {"대양"})
            self.assertTrue(all(record["answers"] == [] and record["spent"] == 0 for record in events(match, "word_guess")))
            for name, balance in result["pieces"].items():
                self.assertEqual(balance, 2 + result["pieces_awarded"].get(name, 0))

    def test_embedding_scores_preserve_negatives_and_cache_symmetric_pair(self):
        vectors = WordVectors(["학교", "병원"], [[1, 0], [-1, 0]])
        vectors.similarity = Mock(wraps=vectors.similarity)
        cache = {}
        first = game._judge(vectors, "학교", "병원", cache)
        self.assertEqual(first, {"similarity": -100, "valid": True, "mode": "openai"})
        self.assertEqual(game._judge(vectors, "병원", "학교", cache), first)
        vectors.similarity.assert_called_once()

    def test_similarity_ignores_participant_model_and_remaining_budget(self):
        scores = []
        for remaining in (0, 10):
            match = WrongGuesses(PLAYERS, 3, live_turns=remaining)
            model = Mock()
            match.models = {name: model for name in PLAYERS}
            game.play(match)
            model.sample_text.assert_not_called()
            self.assertEqual(match.live_turns, remaining)
            scores.append(events(match, "word_similarity"))
            self.assertTrue(all(record["mode"] == "openai" for record in scores[-1]))
        self.assertEqual(*scores)

    def test_interrupted_match_replays_with_same_vectors(self):
        def interrupt(match):
            record = match.on_event
            def stop(event):
                record(event)
                if event.msg_type == "word_verdict":
                    raise RuntimeError("test interruption")
            match.on_event = stop
            return game.play(match)

        with TemporaryDirectory() as directory, redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            path = Path(directory) / "events.jsonl"
            with self.assertRaisesRegex(RuntimeError, "interruption"):
                run_cli(interrupt, title=DAY_FIVE_MAIN, seats=6, argv=["--output", str(path)])
            before = path.read_text().splitlines()
            wrong_vectors = WordVectors(self.vectors._words, [[0, 1] for _ in self.vectors._words])
            original = path.read_bytes()
            with patch.object(cli, "load_vectors", return_value=wrong_vectors), self.assertRaises(SystemExit):
                cli.main(["--resume", "--output", str(path)])
            self.assertEqual(path.read_bytes(), original)
            run_cli(game.play, title=DAY_FIVE_MAIN, seats=6, argv=["--resume", "--output", str(path)])
            after = path.read_text().splitlines()
            self.assertEqual(after[:len(before) - 1], before[:-1])
            self.assertEqual(json.loads(after[-1])["type"], "result")

    def test_saved_oov_scores_and_scripted_guesses_replay_without_embedding(self):
        def interrupt(match):
            # Match journals active model backends, even after their turn budget is exhausted.
            match.backends = dict.fromkeys(PLAYERS, object())
            record = match.on_event

            def stop(event):
                record(event)
                if event.msg_type == "word_verdict":
                    raise RuntimeError("test interruption")

            match.on_event = stop
            return game.play(match)

        with (TemporaryDirectory() as directory, redirect_stdout(StringIO()), redirect_stderr(StringIO()),
              patch("games.match.Match", OutsideHints)):
            path = Path(directory) / "events.jsonl"
            with patch.object(self.vectors, "hint_similarity", return_value=100):
                with self.assertRaisesRegex(RuntimeError, "test interruption"):
                    run_cli(interrupt, title=DAY_FIVE_MAIN, seats=6, argv=["--output", str(path)])
            before = path.read_text().splitlines()
            with patch.object(self.vectors, "hint_similarity", side_effect=AssertionError("saved prefix must not embed")) as scorer:
                with self.assertRaisesRegex(RuntimeError, "test interruption"):
                    run_cli(interrupt, title=DAY_FIVE_MAIN, seats=6, argv=["--resume", "--output", str(path)])
                scorer.assert_not_called()
            after = path.read_text().splitlines()
            self.assertEqual(after[:len(before) - 1], before[:-1])

    def test_old_private_hint_match_cannot_resume_as_public_game(self):
        def interrupt(match):
            record = match.on_event
            def stop(event):
                record(event)
                if event.msg_type == "word_verdict":
                    raise RuntimeError("test interruption")
            match.on_event = stop
            return game.play(match)

        with TemporaryDirectory() as directory, redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            path = Path(directory) / "events.jsonl"
            with self.assertRaisesRegex(RuntimeError, "interruption"):
                run_cli(interrupt, title=DAY_FIVE_MAIN, seats=6, argv=["--output", str(path)])
            records = [json.loads(line) for line in path.read_text().splitlines()]
            for row in records:
                if row.get("msg_type") == "rules":
                    row["content"] = "이전 규칙: 후보 단어는 출제자만 확인합니다."
                if row.get("msg_type") == "word_setup":
                    setup = json.loads(row["content"])
                    del setup["hint_visibility"], setup["score_display"], setup["score_ceiling"]
                    row["content"] = encode(setup)
                if row.get("msg_type") == "word_hint":
                    row["visible_to"] = [row["agent_name"]]
                if row.get("msg_type") == "word_similarity":
                    data = json.loads(row["content"])
                    del data["word"]
                    row["content"] = encode(data)
            path.write_text("\n".join(map(encode, records)) + "\n")
            before = path.read_bytes()
            with self.assertRaisesRegex(ValueError, "비공개"):
                game.validate_saved_setup(setup, self.vectors)
            with patch.object(cli, "load_vectors", return_value=self.vectors), self.assertRaises(SystemExit):
                cli.main(["--resume", "--output", str(path)])
            self.assertEqual(path.read_bytes(), before)

    def test_cli_preflight_errors_do_not_create_logs_and_help_needs_no_model(self):
        with TemporaryDirectory() as directory, redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            path = Path(directory) / "new" / "events.jsonl"
            for problem in (FileNotFoundError("missing word vectors"), ValueError("corrupt word vectors")):
                with patch.object(cli, "load_vectors", side_effect=problem), self.assertRaises(SystemExit):
                    cli.main(["--output", str(path)])
                self.assertFalse(path.parent.exists())
            incomplete = WordVectors(["바다"], [[1, 0]])
            with patch.object(cli, "load_vectors", return_value=incomplete), self.assertRaises(SystemExit):
                cli.main(["--output", str(path)])
            self.assertFalse(path.parent.exists())
            with (patch.object(self.vectors, "nearest", return_value={"word": "대양", "similarity": 0}),
                  patch.object(cli, "load_vectors", return_value=self.vectors)):
                with self.assertRaisesRegex(ValueError, "양수"):
                    game.validate_vectors(self.vectors)
                with self.assertRaises(SystemExit):
                    cli.main(["--output", str(path)])
            self.assertFalse(path.parent.exists())
            with patch.object(cli, "load_vectors", side_effect=AssertionError("must not load")), self.assertRaises(SystemExit) as error:
                cli.main(["--help"])
            self.assertEqual(error.exception.code, 0)

    def test_cli_rejects_incompatible_saved_setup_without_changing_record(self):
        with TemporaryDirectory() as directory, redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            path = Path(directory) / "events.jsonl"
            valid = {"version": 4, "hint_visibility": "public", "score_mode": "openai",
                     "scorer": game.scorer_metadata(self.vectors), "deck_sha256": DECK_SHA256,
                     "discussion": False, "relationship_reviews": False,
                     "fallback": "vocabulary_nearest", "reveal_rule": "nearest_noun_ratio_v1",
                     "hint_filter": "openai_text_embedding_v1", "score_display": "nearest_noun_99_9", "score_ceiling": 99.9}
            game.validate_saved_setup(valid, self.vectors)
            changes = (
                ({"version": 1}, "이전 유사도"),
                ({"version": 2, "score_mode": "fasttext", "hint_filter": "same_as_nearest"}, "이전 유사도"),
                ({"version": 3, "hint_filter": "stdict_noun_membership_v1"}, "이전 유사도"),
                ({"hint_visibility": "private"}, "비공개"),
                ({"score_mode": "fasttext"}, "판정기가 변경"),
                ({"scorer": {**valid["scorer"], "id": "fasttext-cc-ko-300"}}, "모델 정보·체크섬"),
                ({"scorer": {**valid["scorer"], "sha256": "different"}}, "모델 정보·체크섬"),
                ({"scorer": {**valid["scorer"], "out_of_vocabulary": "reject"}}, "모델 정보·체크섬"),
                ({"deck_sha256": "different"}, "단어 봉투"),
                ({"discussion": True}, "대화 구간"),
                ({"relationship_reviews": True}, "관계 평가"),
                ({"relationship_reviews": None}, "관계 평가"),
                ({"fallback": "submitted_highest"}, "힌트 공개 규칙"),
                ({"reveal_rule": "raw_cosine"}, "힌트 공개 기준"),
                ({"hint_filter": "stdict_noun_membership_v1"}, "힌트 명사 판정"),
                ({"score_display": "unknown"}, "점수 표시"),
                ({"score_ceiling": 100}, "점수 표시"),
            )
            for change, expected in changes:
                setup = {**valid, **change}
                with self.subTest(change=change), self.assertRaisesRegex(ValueError, expected):
                    game.validate_saved_setup(setup, self.vectors)
                path.write_text(encode({"type": "match", "game": DAY_FIVE_MAIN}) + "\n"
                                + encode({"type": "event", "msg_type": "word_setup", "content": encode(setup)}) + "\n")
                before = path.read_bytes()
                with patch.object(cli, "load_vectors", return_value=self.vectors), self.assertRaises(SystemExit):
                    cli.main(["--resume", "--output", str(path)])
                self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
