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


class HintLanguageTest(unittest.TestCase):
    def setUp(self):
        words = sorted({"ㄱ"}.union(WORDS, *(set(hints) for hints in ASSOCIATIONS.values())))
        self.vectors = WordVectors(words, [[1, 0] for _ in words])

    def first_clue(self, match):
        def stop(event):
            if event.msg_type == "word_clue":
                raise Interrupted()
        match.on_event = stop
        with self.assertRaises(Interrupted):
            game.play(match, vectors=self.vectors)

    def test_korean_validation_normalizes_without_dictionary_or_length_limits(self):
        for value in ("용기류", "쾨펜", "인공지능연구개발지원시스템관리체계", "ㄱ", "쉼",
                      "  " + normalize("NFD", "용기류") + "  "):
            with self.subTest(value=value):
                self.assertTrue(game._valid_hint(value, "정답", vectors=self.vectors))
        for value in ("courage", "용기courage", "ｃｏｕｒａｇｅ", "영어Ｘ", "123", "용기1", "용기!", "🧠",
                      "가다", "예쁘다", "용기가", "용기를", "학교의", "없는낱말", "우산을든사람", "", " ", None):
            with self.subTest(value=value):
                self.assertFalse(game._valid_hint(value, "정답", vectors=self.vectors))
        for value in ("정답", " 정답 ", normalize("NFD", "정답")):
            self.assertFalse(game._valid_hint(value, "정답", vectors=self.vectors))
        self.assertTrue(game._valid_hint("courage", "정답"))

    def test_invalid_draft_and_final_never_reach_embedding_or_public_scores(self):
        for phase in ("word_hint_draft", "word_hint"):
            for value in ("courage", "용기courage", "ｃｏｕｒａｇｅ", "용기1", "용기!", "가다", "예쁘다", "용기가"):
                with self.subTest(phase=phase, value=value):
                    match = LiveMatch()
                    with (patch.dict(OUTPUTS, {phase: value}),
                          patch.object(self.vectors, "hint_similarity", return_value=100) as embed):
                        self.first_clue(match)
                    invalid = [event for event in match.events if event.msg_type == "invalid_action"]
                    self.assertEqual([json.loads(event.content)["phase"] for event in invalid], [phase])
                    self.assertEqual(json.loads(invalid[0].content)["action"], value)
                    self.assertNotEqual(invalid[0].visible_to, "all")
                    embed.assert_called_once()
                    self.assertNotEqual(embed.call_args.args[1], value)
                    for event in match.events:
                        if event.msg_type in {"word_hint", "word_similarity", "word_clue"}:
                            hint = json.loads(event.content)["word"]
                            self.assertNotEqual(hint, value)
                            self.assertTrue(game._valid_hint(hint, "정답", vectors=self.vectors))

    def test_unregistered_korean_hints_are_normalized_and_scored(self):
        for value in ("용기류", "쾨펜", "인공지능연구개발지원시스템관리체계", "ㄱ", normalize("NFD", "용기류")):
            with self.subTest(value=value):
                match = LiveMatch()
                with (patch.dict(OUTPUTS, {"word_hint_draft": value, "word_hint": value}),
                      patch.object(self.vectors, "hint_similarity", return_value=100) as embed):
                    self.first_clue(match)
                embed.assert_called_once()
                self.assertEqual(embed.call_args.args[1], normalize("NFC", value))
                self.assertFalse(any(event.msg_type == "invalid_action" for event in match.events))
                setup = next(json.loads(event.content) for event in match.events if event.msg_type == "word_setup")
                self.assertEqual(setup["hint_language"], "ko_noun_v1")
                self.assertEqual(setup["hint_filter"], "openai_text_embedding_v1")

    def test_unknown_language_is_rejected_before_modifying_saved_log(self):
        match = Match(PLAYERS, 11)
        self.first_clue(match)
        setup = next(json.loads(event.content) for event in match.events if event.msg_type == "word_setup")
        setup["hint_language"] = "en"
        with (TemporaryDirectory() as directory, redirect_stderr(StringIO()),
              patch.object(cli, "load_vectors", return_value=self.vectors)):
            path = Path(directory) / "events.jsonl"
            path.write_text(encode({"type": "match", "game": DAY_FIVE_MAIN}) + "\n"
                            + encode({"type": "event", "msg_type": "word_setup", "content": encode(setup)}) + "\n")
            before = path.read_bytes()
            with self.assertRaises(SystemExit):
                cli.main(["--resume", "--output", str(path)])
            self.assertEqual(path.read_bytes(), before)

    def test_legacy_english_hint_replays_exactly_without_embedding_or_model_call(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            header = {"type": "match", "game": DAY_FIVE_MAIN}

            def record(log, stop_kind):
                def write(event):
                    log.write({"type": "event", **asdict(event), "model_calls": 0})
                    if event.msg_type == stop_kind:
                        raise Interrupted()
                return write

            # Generate the former permissive response sequence with the real journal.
            validate = game._valid_hint
            with (patch.dict(OUTPUTS, {"word_hint_draft": "courage", "word_hint": "courage"}),
                  patch.object(game, "_valid_hint", side_effect=lambda value, secret, **_: validate(value, secret)),
                  patch.object(self.vectors, "hint_similarity", return_value=100), MatchLog(path) as log):
                log.write(header)
                match = LiveMatch(resume_log=log, on_event=record(log, "word_hint"))
                with self.assertRaises(Interrupted):
                    game.play(match, vectors=self.vectors)
                log.write({"type": "interrupted", "model_calls": 0})
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            for row in rows:
                if row.get("msg_type") == "rules":
                    row["content"] = game.LEGACY_PREPARED_RULES
                elif row.get("msg_type") == "word_setup":
                    setup = json.loads(row["content"])
                    del setup["hint_language"]
                    setup.pop("prison_seats", None)
                    row["content"] = encode(setup)
            path.write_text("\n".join(map(encode, rows)) + "\n")
            before = path.read_text().splitlines()
            with (MatchLog(path, resume=True) as log,
                  patch.object(game, "_judge", side_effect=AssertionError("saved English score must not be recalculated"))):
                log.write(header)
                resumed = LiveMatch(resume_log=log, on_event=record(log, "word_similarity"))
                with self.assertRaises(Interrupted):
                    game.play(resumed, vectors=self.vectors)
                log.write({"type": "interrupted", "model_calls": 0})
            self.assertEqual(resumed.queries, [])
            self.assertEqual(path.read_text().splitlines()[:len(before) - 1], before[:-1])
            self.assertFalse(any(event.msg_type == "invalid_action" for event in resumed.events))
            public = [json.loads(event.content)["word"] for event in resumed.events
                      if event.msg_type in {"word_hint", "word_similarity"}]
            self.assertEqual(public, ["courage", "courage"])


if __name__ == "__main__":
    unittest.main()
