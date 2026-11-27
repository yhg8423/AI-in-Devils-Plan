from collections import defaultdict
from contextlib import redirect_stderr
from dataclasses import asdict
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unicodedata import normalize
import unittest
from unittest.mock import patch

from ..match import DAY_FIVE_MAIN, Match, encode
from ..resume import MatchLog
from . import __main__ as cli, game
from .test_hint_preparation import Interrupted, LiveMatch, OUTPUTS, PLAYERS
from .vectors import WordVectors
from .words import ASSOCIATIONS, WORDS


class HintReuseTest(unittest.TestCase):
    def setUp(self):
        words = sorted({"대양", "유통"}.union(WORDS, *(set(hints) for hints in ASSOCIATIONS.values())))
        self.vectors = WordVectors(words, [[1, 0] for _ in words])

    def test_used_public_words_are_rejected_after_spelling_normalization(self):
        for text in ("유통", " 유통 ", normalize("NFD", "유통")):
            with self.subTest(text=text):
                self.assertFalse(game._valid_hint(text, "시장", vectors=self.vectors, used={"유통"}))
                self.assertTrue(game._valid_hint(text, "시장", vectors=self.vectors, used=set()))
        self.assertTrue(game._valid_hint("상권", "시장", used={"유통"}))

    def test_repeated_drafts_and_final_hints_use_fresh_defaults_across_all_phases(self):
        match = LiveMatch()
        with (patch.dict(OUTPUTS, {"word_hint_draft": "유통", "word_hint": " " + normalize("NFD", "유통") + " ",
                                  "word_guess": encode({"answers": ["우주선"], "spend": False})}),
              patch.object(self.vectors, "hint_similarity", return_value=100)):
            game.play(match, vectors=self.vectors)
        by_secret = defaultdict(list)
        for event in match.events:
            if event.msg_type == "word_hint":
                data = json.loads(event.content)
                by_secret[data["round"], data["setter"]].append(data)
        self.assertEqual(len(by_secret), len(PLAYERS) * 2)
        for hints in by_secret.values():
            self.assertEqual([hint["phase"] for hint in hints], [1, 2, 3])
            self.assertEqual(hints[0]["word"], "유통")
            self.assertEqual(len({hint["word"] for hint in hints}), 3)
        invalid = [event for event in match.events if event.msg_type == "invalid_action"]
        self.assertEqual(len(invalid), len(by_secret) * 4)
        self.assertEqual({json.loads(event.content)["phase"] for event in invalid}, {"word_hint_draft", "word_hint"})
        self.assertTrue(all(event.visible_to != "all" for event in invalid))
        setup = next(json.loads(event.content) for event in match.events if event.msg_type == "word_setup")
        self.assertEqual(setup["hint_reuse"], "unique_per_secret_v1")

    def test_same_phase_keeps_ten_distinct_attempts_after_the_demo_hints_run_out(self):
        match = LiveMatch()

        def stop(event):
            if event.msg_type == "word_clue":
                raise Interrupted()

        match.on_event = stop
        with (patch.dict(OUTPUTS, {"word_hint_draft": "유통", "word_hint": "유통"}),
              patch.object(self.vectors, "hint_similarity", return_value=50)):
            with self.assertRaises(Interrupted):
                game.play(match, vectors=self.vectors)
        hints = [json.loads(event.content) for event in match.events if event.msg_type == "word_hint"]
        self.assertEqual(len(hints), game.MAX_HINTS)
        self.assertEqual(len({hint["word"] for hint in hints}), game.MAX_HINTS)
        self.assertTrue(all(not hint["qualifies"] for hint in hints))

    def test_automatic_clues_and_submitted_candidates_do_not_repeat_for_one_secret(self):
        match = LiveMatch()
        with (patch.dict(OUTPUTS, {"word_hint_draft": "유통", "word_hint": "유통",
                                  "word_guess": encode({"answers": ["우주선"], "spend": False})}),
              patch.object(self.vectors, "hint_similarity", return_value=50)):
            game.play(match, vectors=self.vectors)
        seen = defaultdict(set)
        for event in match.events:
            if event.msg_type not in {"word_hint", "word_clue"}:
                continue
            data = json.loads(event.content)
            key = data["round"], data["setter"]
            self.assertNotIn(data["word"], seen[key])
            seen[key].add(data["word"])
        self.assertEqual(len(seen), len(PLAYERS) * 2)
        self.assertTrue(all(len(words) == (game.MAX_HINTS + 1) * 3 for words in seen.values()))

    def test_automatic_next_noun_keeps_the_original_normalization_reference(self):
        match = LiveMatch()

        def stop(event):
            if event.msg_type == "word_clue":
                raise Interrupted()

        def nearest(word, *, exclude=()):
            return {"word": "대양", "similarity": 60} if exclude else {"word": "유통", "similarity": 100}

        match.on_event = stop
        with (patch.dict(OUTPUTS, {"word_hint_draft": "유통", "word_hint": "유통"}),
              patch.object(self.vectors, "nearest", side_effect=nearest) as search,
              patch.object(self.vectors, "hint_similarity", return_value=50)):
            with self.assertRaises(Interrupted):
                game.play(match, vectors=self.vectors)
        clue = json.loads(next(event.content for event in match.events if event.msg_type == "word_clue"))
        self.assertTrue(clue["forced"])
        self.assertEqual(clue["word"], "대양")
        self.assertEqual(clue["similarity"], 60)
        submitted = {json.loads(event.content)["word"] for event in match.events if event.msg_type == "word_hint"}
        self.assertEqual(search.call_args.kwargs["exclude"], submitted)

    def test_new_reuse_rule_replays_the_saved_prefix_without_another_request(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            header = {"type": "match", "game": DAY_FIVE_MAIN}

            def record(log):
                def write(event):
                    log.write({"type": "event", **asdict(event), "model_calls": 0})
                    if event.msg_type == "word_clue" and json.loads(event.content)["phase"] == 2:
                        raise Interrupted()
                return write

            with (patch.dict(OUTPUTS, {"word_hint_draft": "유통", "word_hint": "유통",
                                      "word_guess": encode({"answers": ["우주선"], "spend": False})}),
                  patch.object(self.vectors, "hint_similarity", return_value=100), MatchLog(path) as log):
                log.write(header)
                with self.assertRaises(Interrupted):
                    game.play(LiveMatch(resume_log=log, on_event=record(log)), vectors=self.vectors)
                log.write({"type": "interrupted", "model_calls": 0})
            before = path.read_bytes()
            with (MatchLog(path, resume=True) as log,
                  patch.object(self.vectors, "hint_similarity", side_effect=AssertionError("saved hints must not embed"))):
                log.write(header)
                resumed = LiveMatch(resume_log=log, on_event=record(log))
                with self.assertRaises(Interrupted):
                    game.play(resumed, vectors=self.vectors)
                log.write({"type": "interrupted", "model_calls": 0})
            self.assertEqual(resumed.queries, [])
            self.assertEqual(path.read_bytes(), before)

    def test_unknown_reuse_rule_is_rejected_before_the_log_is_modified(self):
        match = Match(PLAYERS, 11)

        def stop(event):
            if event.msg_type == "word_setup":
                raise Interrupted()

        match.on_event = stop
        with self.assertRaises(Interrupted):
            game.play(match, vectors=self.vectors)
        setup = json.loads(next(event.content for event in match.events if event.msg_type == "word_setup"))
        setup["hint_reuse"] = "unknown"
        with (TemporaryDirectory() as directory, redirect_stderr(StringIO()),
              patch.object(cli, "load_vectors", return_value=self.vectors)):
            path = Path(directory) / "events.jsonl"
            path.write_text(encode({"type": "match", "game": DAY_FIVE_MAIN}) + "\n"
                            + encode({"type": "event", "msg_type": "word_setup", "content": encode(setup)}) + "\n")
            before = path.read_bytes()
            with self.assertRaises(SystemExit):
                cli.main(["--resume", "--output", str(path)])
            self.assertEqual(path.read_bytes(), before)

    def test_v5_without_reuse_marker_replays_its_existing_duplicate_hints(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            header = {"type": "match", "game": DAY_FIVE_MAIN}

            def record(log):
                def write(event):
                    log.write({"type": "event", **asdict(event), "model_calls": 0})
                    if event.msg_type == "word_clue" and json.loads(event.content)["phase"] == 2:
                        raise Interrupted()
                return write

            validate = game._valid_hint
            # Create the former repeated-proposal sequence with a real decision journal.
            with (patch.dict(OUTPUTS, {"word_hint_draft": "유통", "word_hint": "유통",
                                      "word_guess": encode({"answers": ["우주선"], "spend": False})}),
                  patch.object(game, "_valid_hint", side_effect=lambda value, secret, **options:
                               validate(value, secret, vectors=options.get("vectors"))),
                  patch.object(self.vectors, "hint_similarity", return_value=100), MatchLog(path) as log):
                log.write(header)
                with self.assertRaises(Interrupted):
                    game.play(LiveMatch(resume_log=log, on_event=record(log)), vectors=self.vectors)
                log.write({"type": "interrupted", "model_calls": 0})
            rows = list(map(json.loads, path.read_text().splitlines()))
            for row in rows:
                if row.get("msg_type") == "rules":
                    row["content"] = game.REPEATED_HINT_RULES.replace(game.LEGACY_ASSIGNMENTS, game.ASSIGNMENTS)
                elif row.get("msg_type") == "word_setup":
                    setup = json.loads(row["content"])
                    del setup["hint_reuse"]
                    row["content"] = encode(setup)
            path.write_text("\n".join(map(encode, rows)) + "\n")
            before = path.read_bytes()
            with (MatchLog(path, resume=True) as log,
                  patch.object(self.vectors, "hint_similarity", side_effect=AssertionError("saved hints must not embed"))):
                log.write(header)
                resumed = LiveMatch(resume_log=log, on_event=record(log))
                with self.assertRaises(Interrupted):
                    game.play(resumed, vectors=self.vectors)
                log.write({"type": "interrupted", "model_calls": 0})
            self.assertEqual(resumed.queries, [])
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual([json.loads(event.content)["word"] for event in resumed.events
                              if event.msg_type == "word_hint"], ["유통", "유통"])


if __name__ == "__main__":
    unittest.main()
