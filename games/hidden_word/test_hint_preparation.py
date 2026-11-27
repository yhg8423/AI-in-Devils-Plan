from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from ..match import DAY_FIVE_MAIN, Decision, Match, encode, run_cli
from ..models import StrategyNote
from ..resume import MatchLog
from . import __main__ as cli, game
from .vectors import WordVectors
from .words import ASSOCIATIONS, WORDS


PLAYERS = tuple(f"P{number:02}" for number in range(1, 6))
PHASES = ("word_hint_preparation", "word_hint_draft", "word_hint_review", "word_hint")
OUTPUTS = dict(zip(PHASES, ("비공개 계획 요약", "비밀초안낱말", "비공개 수정 검토", "수정힌트낱말")))
SECOND = 1_000_000_000


class Interrupted(RuntimeError):
    pass


class LiveMatch(Match):
    """Exercise real decision reservation and journaling without contacting a model."""
    def __init__(self, *, durations=None, **kwargs):
        super().__init__(PLAYERS, 11, live_turns=5000, allow_review=False,
                         count_calls=lambda: 0, **kwargs)
        self.backends = dict.fromkeys(PLAYERS, object())
        self.queries = []
        self.durations = durations or {}

    def decide_together(self, phase, decisions, **kwargs):
        self.phase, self.defaults = phase, {name: decision.default for name, decision in decisions.items()}
        result = super().decide_together(phase, decisions, **kwargs)
        if kwargs.get("response_times") is not None:
            kwargs["response_times"].update(dict.fromkeys(decisions, self.durations.get(phase, 0)))
        return result

    def request_action(self, name, phase, prompt, default, **kwargs):
        self.phase, self.defaults = phase, {name: default}
        return super().request_action(name, phase, prompt, default, **kwargs)

    def _query(self, name, prompt, *args, **kwargs):
        self.queries.append({"phase": self.phase, "name": name, "prompt": prompt,
                             "observations": list(self.observations(name)), "review": kwargs.get("allow_review")})
        return OUTPUTS.get(self.phase, self.defaults[name]), StrategyNote(text=f"선택 근거 {self.phase}")


class HintPreparationTest(unittest.TestCase):
    def setUp(self):
        words = sorted(set(WORDS).union(*(set(hints) for hints in ASSOCIATIONS.values())))
        self.vectors = WordVectors(words, [[1, 0] for _ in words])
        self.decision = Decision("정답을 숨길 힌트를 고르세요.", "시연힌트", valid=lambda value: bool(value))

    def play_to_first_clue(self, match):
        def stop(event):
            if event.msg_type == "word_clue":
                raise Interrupted()
        match.on_event = stop
        with self.assertRaises(Interrupted):
            game.play(match, vectors=self.vectors)

    def test_four_calls_share_private_context_but_only_final_hint_is_scored(self):
        match = LiveMatch()
        with patch.object(game, "_judge", return_value={"similarity": 100, "valid": True, "mode": "openai"}) as judge:
            self.play_to_first_clue(match)
        calls = [query for query in match.queries if query["phase"] in PHASES]
        self.assertEqual([query["phase"] for query in calls], list(PHASES))
        self.assertTrue(all(query["review"] is False for query in calls))
        self.assertEqual(5000 - match.live_turns, len(match.queries))
        for index, previous in ((1, PHASES[0]), (2, PHASES[1]), (3, PHASES[2])):
            self.assertTrue(any(OUTPUTS[previous] in event.content for event in calls[index]["observations"]))
        self.assertIn(encode(OUTPUTS[PHASES[1]]), calls[2]["prompt"])
        self.assertIn(encode(OUTPUTS[PHASES[1]]), calls[3]["prompt"])
        judge.assert_called_once()
        self.assertEqual(judge.call_args.args[2], OUTPUTS["word_hint"])
        public = [event for event in match.events if event.visible_to == "all"]
        self.assertFalse(any(OUTPUTS["word_hint_draft"] in event.content for event in public))
        self.assertEqual([json.loads(event.content)["word"] for event in public if event.msg_type == "word_hint"],
                         [OUTPUTS["word_hint"]])
        setter = calls[0]["name"]
        for event in match.events:
            if event.msg_type in {"action", "decision_note"} and json.loads(event.content)["phase"] in PHASES:
                self.assertEqual(event.visible_to, [setter])
        for other in set(PLAYERS) - {setter}:
            self.assertFalse(any(OUTPUTS[phase] in event.content for phase in PHASES[:3]
                                 for event in match.observations(other)))

    def test_timeout_in_each_stage_skips_remaining_calls_and_does_not_publish_or_score(self):
        for index, slow_phase in enumerate(PHASES):
            with self.subTest(stage=slow_phase):
                match = LiveMatch(durations={slow_phase: 901 * SECOND})
                with patch.object(game, "_judge", side_effect=AssertionError("late hint must not be scored")):
                    self.play_to_first_clue(match)
                self.assertEqual([query["phase"] for query in match.queries if query["phase"] in PHASES],
                                 list(PHASES[:index + 1]))
                self.assertFalse(any(event.msg_type in {"word_hint", "word_similarity"} for event in match.events))

    def test_deadline_accumulates_across_stages_and_hint_attempts(self):
        match = LiveMatch(durations=dict.fromkeys(PHASES, 200 * SECOND))
        with patch.object(game, "_judge", return_value={"similarity": 50, "valid": True, "mode": "openai"}) as judge:
            self.play_to_first_clue(match)
        self.assertEqual([query["phase"] for query in match.queries if query["phase"] in PHASES],
                         [*PHASES, PHASES[0]])
        judge.assert_called_once()
        self.assertEqual(sum(event.msg_type == "word_hint" for event in match.events), 1)

    def test_each_completed_stage_replays_from_journal_without_another_model_call(self):
        for index, stop_phase in enumerate(PHASES):
            with self.subTest(stage=stop_phase), TemporaryDirectory() as directory:
                path = Path(directory) / "events.jsonl"
                header = {"type": "match", "game": DAY_FIVE_MAIN}

                def record(log, stop=False):
                    def write(event):
                        log.write({"type": "event", **asdict(event), "model_calls": 0})
                        data = json.loads(event.content)
                        key = "note" if stop_phase in {PHASES[0], PHASES[2]} else "action"
                        if stop and data.get("phase") == stop_phase and data.get(key) == OUTPUTS[stop_phase]:
                            raise Interrupted()
                    return write

                with MatchLog(path) as log:
                    log.write(header)
                    match = LiveMatch(resume_log=log, on_event=record(log, stop=True))
                    with self.assertRaises(Interrupted):
                        game._prepared_hint(match, PLAYERS[0], self.decision, 900 * SECOND)
                    log.write({"type": "interrupted", "model_calls": 0})
                before = path.read_text().splitlines()
                self.assertEqual([query["phase"] for query in match.queries], list(PHASES[:index + 1]))
                with MatchLog(path, resume=True) as log:
                    log.write(header)
                    resumed = LiveMatch(resume_log=log, on_event=record(log))
                    hint, _ = game._prepared_hint(resumed, PLAYERS[0], self.decision, 900 * SECOND)
                    log.write({"type": "result", "hint": hint, "model_calls": 0})
                self.assertEqual([query["phase"] for query in resumed.queries], list(PHASES[index + 1:]))
                self.assertEqual(hint, OUTPUTS["word_hint"])
                self.assertEqual(path.read_text().splitlines()[:len(before) - 1], before[:-1])

    def test_v4_without_preparation_marker_resumes_exact_legacy_prefix(self):
        self.assertEqual(sha256(game.LEGACY_RULES.encode()).hexdigest(),
                         "2f20f9da42fd63a6c3096a9f1a9a026f674225c30b7bc0830a0fbafb4b9965bf")
        def interrupt(match):
            record = match.on_event
            def stop(event):
                record(event)
                if event.msg_type == "word_verdict":
                    raise Interrupted()
            match.on_event = stop
            return game.play(match)

        with (TemporaryDirectory() as directory, redirect_stdout(StringIO()), redirect_stderr(StringIO()),
              patch.object(game, "load_vectors", return_value=self.vectors)):
            path = Path(directory) / "events.jsonl"
            with self.assertRaises(Interrupted):
                run_cli(interrupt, title=DAY_FIVE_MAIN, seats=5, argv=["--output", str(path)])
            legacy, turn = [], 0
            for row in map(json.loads, path.read_text().splitlines()):
                if row.get("type") == "event":
                    if row["msg_type"] == "rules":
                        row["content"] = game.LEGACY_RULES
                    elif row["msg_type"] == "word_setup":
                        setup = json.loads(row["content"])
                        del setup["hint_preparation"], setup["hint_language"]
                        setup.pop("prison_seats", None)
                        row["content"] = encode(setup)
                    elif row["msg_type"] in {"action", "decision_note"} and json.loads(row["content"])["phase"] in PHASES[:3]:
                        continue
                    row["turn"] = turn
                    turn += 1
                legacy.append(row)
            path.write_text("\n".join(map(encode, legacy)) + "\n")
            before = path.read_text().splitlines()
            with patch.object(game, "_prepared_hint", side_effect=AssertionError("legacy workflow must stay unchanged")):
                run_cli(game.play, title=DAY_FIVE_MAIN, seats=5, argv=["--resume", "--output", str(path)])
            self.assertEqual(path.read_text().splitlines()[:len(before) - 1], before[:-1])
            self.assertEqual(json.loads(path.read_text().splitlines()[-1])["type"], "result")

    def test_unknown_preparation_marker_is_rejected_before_changing_log(self):
        match = Match(PLAYERS, 11)
        self.play_to_first_clue(match)
        setup = next(event for event in match.events if event.msg_type == "word_setup")
        data = json.loads(setup.content)
        data["hint_preparation"] = "unknown"
        with (TemporaryDirectory() as directory, redirect_stderr(StringIO()),
              patch.object(cli, "load_vectors", return_value=self.vectors)):
            path = Path(directory) / "events.jsonl"
            path.write_text(encode({"type": "match", "game": DAY_FIVE_MAIN}) + "\n"
                            + encode({"type": "event", "msg_type": "word_setup", "content": encode(data)}) + "\n")
            before = path.read_bytes()
            with self.assertRaises(SystemExit):
                cli.main(["--resume", "--output", str(path)])
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
