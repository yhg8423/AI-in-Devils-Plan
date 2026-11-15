from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import re
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
from threading import local
import unittest
from unittest.mock import patch

from .match import Decision, run_cli


class ResumeTest(unittest.TestCase):
    def test_resume_reuses_committed_decisions_and_skips_completed_matches(self):
        players = ("P06", "P01")
        calls = []
        completed_choices = []
        interrupted = True
        clock = local()
        clock_start = 1_000_000

        def complete(command, *, input, **kwargs):
            exercise = input.rsplit("Exercise:", 1)[-1]
            stage, player = re.search(r"단계 ([12]) 참가자 (P\d{2})", exercise).groups()
            reviewed = "임시 답안 개인" in exercise
            model = command[command.index("--model") + 1]
            effort = next(json.loads(arg.split("=", 1)[1]) for arg in command
                          if arg.startswith("model_reasoning_effort="))
            calls.append((stage, player, reviewed, model, effort))
            if stage == "2" and player == "P01" and interrupted:
                raise RuntimeError("provider stopped")
            clock.now = clock_start + (789 if reviewed else (456 if player == "P06" else 123))
            if stage == "1" and player == "P06" and not reviewed:
                reply = {"action": "개인", "note": "팀의 이득을 더 비교한다.", "review": True}
            elif stage == "1" and player == "P01":
                reply = {"action": "잘못된 응답", "note": "유효하지 않은 답"}
            else:
                reply = {"action": "팀", "note": "함께 한다."}
            event = {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(reply)}}
            return CompletedProcess(command, 0, json.dumps(event), "")

        def play(match):
            self.assertEqual(match.players, players)
            self.assertEqual(match.pieces, {"P06": 7, "P01": 3})
            match.event("board", {"draw": match.rng.randrange(1000)})
            for stage in (1, 2):
                clock.now = clock_start
                decisions = {player: Decision(f"단계 {stage} 참가자 {player}", "개인", options=("팀", "개인"))
                             for player in players}
                times = {}
                answers = match.decide_together(f"choice_{stage}", decisions, response_times=times)
                completed_choices.append((answers, times))
                match.event("choices", {"stage": stage, "answers": answers, "times": times})
            return {"ended": True}

        with (TemporaryDirectory() as directory, redirect_stdout(StringIO()), redirect_stderr(StringIO()),
              patch("games.models.subprocess.run", side_effect=complete),
              patch("games.match.monotonic_ns", side_effect=lambda: getattr(clock, "now", clock_start))):
            output = Path(directory) / "events.jsonl"
            title = "재개 테스트"
            first = ["--output", str(output), "--players", *players, "--pieces", "7", "3", "--seed", "19",
                     "--model", "test-luna", "--effort", "medium", "--player-model", "P06:test-sol:low"]
            resume = ["--resume", "--output", str(output)]
            with self.assertRaisesRegex(RuntimeError, "provider stopped"):
                run_cli(play, title=title, seats=2, argv=first)

            before = output.read_text(encoding="utf-8").splitlines()
            self.assertEqual(json.loads(before[-1])["type"], "interrupted")
            self.assertCountEqual(calls, [
                ("1", "P06", False, "test-sol", "low"), ("1", "P01", False, "test-luna", "medium"),
                ("1", "P06", True, "test-sol", "low"),
                ("2", "P06", False, "test-sol", "low"), ("2", "P01", False, "test-luna", "medium"),
            ])
            calls.clear()
            interrupted = False
            run_cli(play, title=title, seats=2, argv=resume)

            after = output.read_text(encoding="utf-8").splitlines()
            self.assertEqual(after[:len(before) - 1], before[:-1])
            records = list(map(json.loads, after))
            self.assertEqual(records[-1]["type"], "result")
            self.assertEqual(records[-1]["model_calls"], 7)
            self.assertNotIn("interrupted", [record["type"] for record in records])
            events = [record for record in records if record["type"] == "event"]
            self.assertEqual([event["turn"] for event in events], list(range(len(events))))
            self.assertEqual([event["msg_type"] for event in events].count("board"), 1)
            self.assertEqual(completed_choices, [
                ({"P06": "팀", "P01": "개인"}, {"P06": 789, "P01": 123}),
                ({"P06": "팀", "P01": "개인"}, {"P06": 789, "P01": 123}),
                ({"P06": "팀", "P01": "팀"}, {"P06": 456, "P01": 123}),
            ])
            self.assertCountEqual(calls, [
                ("2", "P06", False, "test-sol", "low"), ("2", "P01", False, "test-luna", "medium"),
            ])
            calls.clear()
            with self.assertRaises(SystemExit):
                run_cli(play, title=title, seats=2, argv=resume)
            self.assertEqual(output.read_text(encoding="utf-8").splitlines(), after)
            self.assertEqual(calls, [])

    def test_resume_rejects_changed_event_prefix_without_modifying_record(self):
        def first_play(match):
            match.event("board", {"cards": ["A", "K"]})
            raise KeyboardInterrupt

        def changed_play(match):
            match.event("board", {"cards": ["K", "A"]})
            self.fail("A different board must stop replay immediately")

        with TemporaryDirectory() as directory, redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            output = Path(directory) / "events.jsonl"
            args = ["--output", str(output)]
            with self.assertRaises(KeyboardInterrupt):
                run_cli(first_play, title="재개 테스트", seats=2, argv=args)
            before = output.read_bytes()
            with self.assertRaises((ValueError, SystemExit)):
                run_cli(changed_play, title="재개 테스트", seats=2, argv=[*args, "--resume"])
            self.assertEqual(output.read_bytes(), before)
