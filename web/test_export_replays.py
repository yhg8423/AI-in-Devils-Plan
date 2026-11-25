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
        self.check_round_trip(STAGES[:6])

    def test_exports_day_four_main_after_day_three(self):
        self.check_round_trip(STAGES[:7])

    def test_exports_day_four_prison_after_its_main_match(self):
        self.check_round_trip(STAGES[:8])

    def test_exports_day_five_main_after_day_four_prison(self):
        self.check_round_trip(STAGES)

    def check_round_trip(self, stages):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "runs"
            output = root / "play_results"
            campaign = source / "matches" / "example"
            logs = [campaign / stage / "events.jsonl" for stage in stages]
            results = []
            for index, log in enumerate(logs):
                log.parent.mkdir(parents=True)
                header = {"type": "match", "game": CASE_STAGES[index], "players": ["P01"], "seed": 1,
                          "local_settings": "/home/user/config"}
                header.update({key: str(logs[prior]) for key, prior in PREDECESSORS[index].items()})
                event = {"type": "event", "turn": 5, "msg_type": "decision_note", "agent_name": "P01",
                         "content": "계획", "visible_to": ["P01"], "timestamp": 123}
                result = {"type": "result", "ranking": ["P01"]}
                if stages[index] == "day3-prison":
                    header["players"] = ["P01", "P02", "P03", "P04"]
                    report = {"round": 1, "players": header["players"],
                              "scores": {"P01": 1, "P02": -1, "P03": 0, "P04": 0},
                              "safe": ["P01", "P03", "P04"], "eliminated": ["P02"], "remaining": [], "turns": 1}
                    result.update(ranking=["P01", "P03", "P04", "P02"],
                                  scores=dict.fromkeys(header["players"], 0),
                                  eliminated=["P02"], survivors=report["safe"],
                                  pieces_awarded={"P01": 1, "P02": 0, "P03": 1, "P04": 1},
                                  turns=101, resets=0, turn_limit=100, end_reason="turn_limit", main_turns=100,
                                  tiebreaks=[report])
                if stages[index] == "day4-main":
                    header["players"] = ["P01", "G01"]
                    result.update(all_ranking=["G01", "P01"], scores={"P01": 0, "G01": 8},
                                  filled={"P01": 0, "G01": 9}, remaining_value={"P01": 18, "G01": 4},
                                  shapes={"P01": {"triangle": 0}, "G01": {"triangle": 3}},
                                  boards={"P01": [[None]], "G01": [["triangle"]]},
                                  coins={"P01": {"10": 1}, "G01": {"2": 2}}, guest="G01",
                                  guest_result={"player": "G01", "rank": 1, "first": True,
                                                "full_board": True, "prize_won": 20_000_000}, forced_last=[])
                if stages[index] == "day4-prison":
                    header["players"] = ["P01", "P02", "P03"]
                    result.update(ranking=["P01", "P02", "P03"], survivors=["P01", "P02"], eliminated=["P03"],
                                  scores={"P01": 20, "P02": 15, "P03": 14}, largest={"P01": 20, "P02": 10, "P03": 14},
                                  second_scores={"P02": 26, "P03": 23}, second_largest={"P02": 20, "P03": 23},
                                  rounds=2, turns=70, pieces_awarded={"P01": 1, "P02": 1, "P03": 0},
                                  pieces={"P01": 2, "P02": 2, "P03": 1},
                                  games=[{"game": 1, "round": 1, "replay": 0, "scores": {"P01": 20}}])
                results.append(result)
                log.write_text(encode_rows([header, event, result]), encoding="utf-8")
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
                for language in ("ko", "en"):
                    final = read_match(log, language=language)["steps"][-1]["events"][0]
                    self.assertEqual(json.loads(final["content"]), results[index])
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
