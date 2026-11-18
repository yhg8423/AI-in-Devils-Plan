import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from .export_replays import PREDECESSORS, STAGES, encode_rows, export_replays
from .spectator import CASE_STAGES, case_catalog, find_matches, next_match, read_match


class ExportReplaysTest(unittest.TestCase):
    def test_exports_portable_playable_matches_in_both_languages(self):
        self.check_round_trip(STAGES[:4])

    def test_exports_day_three_after_its_day_two_predecessors(self):
        self.check_round_trip(STAGES[:5])

    def test_exports_day_three_prison_after_its_main_match(self):
        self.check_round_trip(STAGES)

    def check_round_trip(self, stages):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "runs"
            output = root / "play_results"
            campaign = source / "matches" / "example"
            logs = [campaign / stage / "events.jsonl" for stage in stages]
            for index, log in enumerate(logs):
                log.parent.mkdir(parents=True)
                header = {"type": "match", "game": CASE_STAGES[index], "players": ["P01"], "seed": 1,
                          "local_settings": "/home/user/config"}
                header.update({key: str(logs[prior]) for key, prior in PREDECESSORS[index].items()})
                event = {"type": "event", "turn": 5, "msg_type": "decision_note", "agent_name": "P01",
                         "content": "계획", "visible_to": ["P01"], "timestamp": 123}
                log.write_text(encode_rows([header, event, {"type": "result", "ranking": ["P01"]}]), encoding="utf-8")
                (log.parent / "events.decisions.jsonl").write_text("private", encoding="utf-8")
                (log.parent / "events.en.jsonl").write_text(
                    encode_rows([{"turn": 5, "text": "Plan"}]), encoding="utf-8",
                )
            original = [log.read_bytes() for log in logs]

            self.assertEqual(export_replays([campaign], source, output), [output / "matches" / "example"])
            self.assertEqual([log.read_bytes() for log in logs], original)
            case, = case_catalog(output)
            run_ids = [f"matches/example/{stage}" for stage in stages]
            self.assertEqual([match["id"] for match in case["matches"]], run_ids)
            exported = find_matches(output)
            for index, run_id in enumerate(run_ids):
                log = exported[run_id]
                self.assertEqual({path.name for path in log.parent.iterdir()}, {"events.jsonl", "events.en.jsonl"})
                header = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
                self.assertNotIn("local_settings", header)
                for key, prior in PREDECESSORS[index].items():
                    self.assertEqual(header[key], f"{run_ids[prior]}/events.jsonl")
                korean = read_match(log)["steps"][0]["events"][0]
                english = read_match(log, language="en")["steps"][0]["events"][0]
                self.assertEqual(korean["content"], "계획")
                self.assertEqual(english, {**korean, "translation": {"text": "Plan"}})
                self.assertEqual(english["visible_to"], ["P01"])
                if index + 1 < len(run_ids):
                    self.assertEqual(next_match(output, exported, run_id)["id"], run_ids[index + 1])

            with self.assertRaises(FileExistsError):
                export_replays([campaign], source, output)

    def test_rejects_incomplete_run_without_writing_output(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "runs"
            output = root / "play_results"
            campaign = source / "matches" / "example"
            log = campaign / STAGES[0] / "events.jsonl"
            log.parent.mkdir(parents=True)
            log.write_text(encode_rows([{"type": "match"}, {"type": "interrupted"}]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "completed full match"):
                export_replays([campaign], source, output)
            self.assertFalse(output.exists())
