"""Memory isolation, simultaneous judging, deadlines, boundary ties, and resume."""

from contextlib import contextmanager, redirect_stderr, redirect_stdout
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from ...match import (
    DAY_ONE_MAIN, DAY_ONE_PRISON, DAY_TWO_MAIN, DAY_TWO_PRISON, FIRST_EXILE, SECOND_EXILE, THIRD_EXILE,
    Match, canonical_game_title, encode, read_completed_match, run_cli,
)
from ...models import OpenAILanguageModel, StrategyNote
from ..roster import collect_third_exile_players
from . import game


PLAYERS = ("P01", "P02", "P03", "P04")
TITLE = SECOND_EXILE
LEGACY_TITLE = "유배지 매치 2 · 틀린 그림 찾기"
TARGETS = [{"id": f"D{index}", "x": index * 100, "y": 100, "w": 40, "h": 40}
           for index in range(1, 6)]


def marks(count):
    return [{"x": target["x"] + 20, "y": target["y"] + 20} for target in TARGETS[:count]]


def scene(seed, number=1):
    def view(color):
        return {"id": f"picture-{number}", "theme": "fishing", "width": 960, "height": 640,
                "shapes": [{"kind": "rect", "x": 0, "y": 0, "w": 10, "h": 10, "fill": color}]}
    return {"original": view("ORIGINAL-SECRET"), "changed": view("CHANGED-ONLY"),
            "targets": deepcopy(TARGETS)}


@contextmanager
def pictures():
    with (patch.object(game, "make_scene", side_effect=scene),
          patch.object(game, "picture", side_effect=lambda value, changed=False:
                       deepcopy(value["changed" if changed else "original"])),
          patch.object(game, "render_picture", side_effect=lambda value: encode(value).encode())):
        yield


def data(match, kind):
    return [json.loads(event.content) for event in match.events if event.msg_type == kind]


class LiveMatch(Match):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, model=OpenAILanguageModel("test", Mock()), live_players=PLAYERS,
                         live_turns=200, **kwargs)
        self.requests = []

    def decide_together(self, phase, decisions, **kwargs):
        self.phase = phase
        self.number = data(self, "picture_phase")[-1]["round"]
        return super().decide_together(phase, decisions, **kwargs)

    def count(self, player):
        return PLAYERS.index(player) + 1

    def _query(self, name, prompt, *args, **kwargs):
        history = self.model_observations(name, self.observations(name))
        self.requests.append((name, self.phase, self.number, prompt, history, kwargs["images"]))
        action = ({"memory": f"KEEP-{name}-{self.number}"} if self.phase == "picture_memorize" else
                  {"marks": marks(self.count(name))})
        return encode(action), StrategyNote(text="UNBOUNDED-ORIGINAL-RECALL " * 30)


class ChangedPictureTest(unittest.TestCase):
    def test_visible_title_changes_only_the_exact_second_exile_alias(self):
        self.assertEqual(SECOND_EXILE, "유배지 매치 2 · 달라진 그림 찾기")
        self.assertTrue(game.RULES.startswith("달라진 그림 찾기 ·"))
        self.assertEqual(canonical_game_title(LEGACY_TITLE), SECOND_EXILE)
        for title in (SECOND_EXILE, FIRST_EXILE, THIRD_EXILE, "틀린 그림 찾기", "유배지 매치 3 · 틀린 그림 찾기"):
            with self.subTest(title=title):
                self.assertEqual(canonical_game_title(title), title)

    def test_completed_legacy_second_exile_remains_a_valid_roster_predecessor_without_rewriting_it(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)

            def write(stage, title, players, eliminated, *, survivors=None, **links):
                path = root / f"{stage}.jsonl"
                header = {"type": "match", "game": title, "players": players, **links}
                result = {"type": "result", "eliminated": eliminated}
                if survivors is not None:
                    result["survivors"] = survivors
                path.write_text(encode(header) + "\n" + encode(result) + "\n", encoding="utf-8")
                return path

            all_players = [f"P{index:02}" for index in range(1, 17)]
            main = write("day1-main", DAY_ONE_MAIN, all_players, ["P13", "P12"])
            prison = write("day1-prison", DAY_ONE_PRISON,
                           [name for name in all_players if name not in {"P13", "P12"}], ["P09", "P14"],
                           from_main=str(main))
            first_players = ["P13", "P12", "P09", "P14"]
            first = write("exile1", FIRST_EXILE, first_players, ["P14"], survivors=first_players[:3],
                          from_matches=[str(main), str(prison)])
            market = write("day2-main", DAY_TWO_MAIN, [name for name in all_players if name not in first_players],
                           ["P08"], from_main=str(main), from_prison=str(prison))
            second = write("exile2", LEGACY_TITLE, ["P13", "P12", "P09", "P08"], ["P12", "P09"],
                           survivors=["P08", "P13"], from_exile=str(first),
                           from_matches=[str(main), str(prison), str(market)])
            roulette = write("day2-prison", DAY_TWO_PRISON,
                             [name for name in all_players if name not in {*first_players, "P08"}],
                             ["P07", "P06"], from_main=str(market))
            snapshots = {path: path.read_bytes() for path in root.iterdir()}
            self.assertEqual(read_completed_match(second, SECOND_EXILE)[0]["game"], LEGACY_TITLE)
            self.assertEqual(collect_third_exile_players(second, [main, prison, market, roulette]),
                             ["P08", "P13", "P07", "P06"])
            self.assertEqual({path: path.read_bytes() for path in root.iterdir()}, snapshots)
            with self.assertRaisesRegex(ValueError, THIRD_EXILE):
                read_completed_match(second, THIRD_EXILE)

    def test_action_parsers_accept_only_bounded_memories_and_up_to_five_pixel_marks(self):
        self.assertEqual(game.parse_memory(encode({"memory": "기" * 300})), "기" * 300)
        self.assertEqual(game.parse_memory(game.EMPTY_MEMORY), "")
        self.assertEqual(game.parse_marks(encode({"marks": [{"x": 0, "y": 639}, {"x": 959, "y": 0}]})),
                         [{"x": 0, "y": 639}, {"x": 959, "y": 0}])
        for value in (None, [], {"memory": True}, {"memory": "기" * 301}, {"memory": "x", "extra": 1}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                game.parse_memory(encode(value))
        for value in (None, [], {"marks": {}}, {"marks": marks(5) + marks(1)},
                      {"marks": [{"x": True, "y": 1}]}, {"marks": [{"x": 1.0, "y": 1}]},
                      {"marks": [{"x": -1, "y": 1}]}, {"marks": [{"x": 960, "y": 1}]},
                      {"marks": [{"x": 1, "y": 640}]}, {"marks": [{"x": 1}]},
                      {"marks": [{"x": 1, "y": 1, "target": "D1"}]}, {"marks": [], "extra": 1}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                game.parse_marks(encode(value))

    def test_scripted_game_plays_three_main_rounds_then_only_a_needed_boundary_tie(self):
        with pictures():
            match = Match(PLAYERS, 19, pieces=[0, 1, 2, 3])
            result = game.play(match)
        self.assertEqual(set(result["ranking"]), set(PLAYERS))
        self.assertEqual(len(result["survivors"]), 2)
        self.assertEqual(len(result["eliminated"]), 2)
        self.assertEqual(result["rounds"], 3)
        self.assertLessEqual(len(result["tiebreaks"]), 1)
        self.assertEqual(result["pieces"], dict(zip(PLAYERS, [0, 1, 2, 3], strict=True)))
        self.assertFalse(match.relationship_reviews_enabled)
        rounds = data(match, "picture_result")
        self.assertEqual(result["scores"], {
            player: sum(row["scores"][player] for row in rounds if not row["overtime"])
            for player in PLAYERS})
        phases = data(match, "picture_phase")
        self.assertEqual([row["stage"] for row in phases[:4]], ["observe", "blank", "answer", "reveal"])
        self.assertEqual(phases[0]["observe_seconds"], 180)
        self.assertEqual(phases[1]["blank_seconds"], 10)
        self.assertIsNone(phases[1]["picture"])
        self.assertEqual(phases[2]["answer_seconds"], 120)
        self.assertEqual(phases[0]["picture"]["shapes"][0]["fill"], "ORIGINAL-SECRET")
        self.assertEqual(phases[2]["picture"]["shapes"][0]["fill"], "CHANGED-ONLY")
        for event in match.events:
            if event.msg_type in {"picture_memory", "picture_marks", "action", "decision_note"}:
                self.assertEqual(event.visible_to, [event.agent_name])

    def test_answer_requests_receive_only_changed_picture_and_own_current_bounded_memory(self):
        with pictures():
            match = LiveMatch(PLAYERS, 19)
            result = game.play(match)
        self.assertEqual(result["ranking"], list(reversed(PLAYERS)))
        self.assertEqual(len(match.requests), 24)
        for player, phase, number, prompt, history, images in match.requests:
            with self.subTest(player=player, phase=phase, round=number):
                self.assertEqual([event.msg_type for event in history], ["rules"])
                self.assertNotIn("UNBOUNDED-ORIGINAL-RECALL", prompt)
                self.assertNotIn("targets", prompt)
                self.assertNotIn("ORIGINAL-SECRET", prompt)
                if phase == "picture_memorize":
                    self.assertIn(b"ORIGINAL-SECRET", images[0])
                    self.assertNotIn("KEEP-", prompt)
                else:
                    self.assertIn(b"CHANGED-ONLY", images[0])
                    self.assertNotIn(b"ORIGINAL-SECRET", images[0])
                    self.assertIn(f"KEEP-{player}-{number}", prompt)
                    for other in PLAYERS:
                        if other != player:
                            self.assertNotIn(f"KEEP-{other}-", prompt)
                    if number > 1:
                        self.assertNotIn(f"KEEP-{player}-{number-1}", prompt)
        for number in (1, 2, 3):
            reveal = next(index for index, event in enumerate(match.events)
                          if event.msg_type == "picture_result" and json.loads(event.content)["round"] == number)
            submitted = [index for index, event in enumerate(match.events)
                         if event.msg_type == "picture_marks" and json.loads(event.content)["round"] == number]
            self.assertEqual(len(submitted), 4)
            self.assertGreater(reveal, max(submitted))

    def test_invalid_and_late_model_responses_do_not_get_scripted_correct_answers(self):
        class TimedMatch(LiveMatch):
            def _query(self, name, prompt, *args, **kwargs):
                action, note = super()._query(name, prompt, *args, **kwargs)
                return ("not JSON" if self.phase == "picture_answer" and name == "P01" else action), note

            def decide_together(self, phase, decisions, **kwargs):
                answers = super().decide_together(phase, decisions, **kwargs)
                if self.number == 1:
                    kwargs["response_times"]["P04"] = (181 if phase == "picture_memorize" else 121) * 1_000_000_000
                return answers

        with pictures():
            match = TimedMatch(PLAYERS, 19)
            result = game.play(match)
        self.assertEqual(result["scores"], {"P01": 0, "P02": 6, "P03": 9, "P04": 8})
        self.assertEqual([(row["player"], row["phase"]) for row in data(match, "picture_timeout")],
                         [("P04", "picture_memorize"), ("P04", "picture_answer")])
        self.assertEqual(next(row for row in data(match, "picture_memory")
                              if row["player"] == "P04" and row["round"] == 1)["memory"], "")
        self.assertEqual(next(row for row in data(match, "picture_marks")
                              if row["player"] == "P04" and row["round"] == 1)["marks"], [])
        self.assertEqual(len(data(match, "invalid_action")), 3)

    def test_overtime_repeats_only_for_players_still_tied_across_the_survival_boundary(self):
        class TiedMatch(LiveMatch):
            def count(self, player):
                if self.number <= 3:
                    return 3
                if self.number == 4:
                    return {"P01": 5, "P02": 4, "P03": 4, "P04": 1}[player]
                return {"P02": 1, "P03": 2}[player]

        with pictures():
            match = TiedMatch(PLAYERS, 19)
            result = game.play(match)
        self.assertEqual(result["scores"], dict.fromkeys(PLAYERS, 9))
        self.assertEqual(result["ranking"], ["P01", "P03", "P02", "P04"])
        self.assertEqual(result["survivors"], ["P01", "P03"])
        self.assertEqual([row["players"] for row in result["tiebreaks"]], [list(PLAYERS), ["P02", "P03"]])
        self.assertEqual([row["slots"] for row in result["tiebreaks"]], [2, 1])
        for row in data(match, "picture_phase"):
            if row["overtime"]:
                self.assertEqual(row["observe_seconds"], 120)
        self.assertEqual({player for player, _, number, *_ in match.requests if number == 5}, {"P02", "P03"})

    def test_harmless_ties_stay_tied_and_do_not_trigger_an_unnecessary_extra_round(self):
        class GroupedMatch(LiveMatch):
            def count(self, player):
                return 4 if player in ("P01", "P02") else 2

        with pictures():
            result = game.play(GroupedMatch(PLAYERS, 19))
        self.assertEqual(result["ranking_groups"], [["P01", "P02"], ["P03", "P04"]])
        self.assertEqual(result["tiebreaks"], [])

    def test_invalid_model_budget_exhaustion_finishes_with_a_finite_scripted_tiebreak(self):
        class InvalidMatch(LiveMatch):
            def _query(self, *args, **kwargs):
                return "invalid JSON", StrategyNote()

        with pictures():
            match = InvalidMatch(PLAYERS, 19)
            match.live_turns = 24
            result = game.play(match)
        self.assertEqual(result["scores"], dict.fromkeys(PLAYERS, 0))
        self.assertEqual(len(result["tiebreaks"]), 1)
        self.assertEqual(match.live_turns, 0)
        self.assertEqual(len(set(result["tiebreaks"][0]["scores"].values())), 4)

    def test_game_rejects_an_incorrect_or_duplicate_roster(self):
        for players in (PLAYERS[:3], ("P01",) * 4):
            with self.subTest(players=players), self.assertRaises(ValueError):
                game.play(Match(players, 1))

    def test_interrupted_memory_and_submission_batches_resume_exactly_without_new_committed_calls(self):
        original_event = Match.event
        reply = encode({"action": game.EMPTY_MEMORY, "note": "그림의 눈에 띄는 부분을 기억한다."})
        with (TemporaryDirectory() as directory, pictures(), redirect_stdout(StringIO()), redirect_stderr(StringIO()),
              patch("games.models.CodexLanguageModel._complete", return_value=reply) as completion):
            root = Path(directory)
            arguments = ["--players", *PLAYERS, "--seed", "19", "--model", "test", "--model-turns", "8"]
            full = root / "full.jsonl"
            run_cli(game.play, title=TITLE, seats=4, argv=[*arguments, "--output", str(full)])
            expected = [json.loads(line) for line in full.read_text().splitlines()]
            for checkpoint in ("picture_setup", "picture_memory", "picture_marks", "picture_result"):
                with self.subTest(checkpoint=checkpoint):
                    output = root / f"{checkpoint}.jsonl"

                    def interrupt(match, kind, value, **kwargs):
                        original_event(match, kind, value, **kwargs)
                        if kind == checkpoint:
                            raise RuntimeError("interrupted after committed event")

                    with patch.object(Match, "event", interrupt), self.assertRaisesRegex(RuntimeError, "committed event"):
                        run_cli(game.play, title=TITLE, seats=4, argv=[*arguments, "--output", str(output)])
                    prefix = [json.loads(line) for line in output.read_text().splitlines()]
                    calls = completion.call_count
                    run_cli(game.play, title=TITLE, seats=4, argv=["--resume", "--output", str(output)])
                    actual = [json.loads(line) for line in output.read_text().splitlines()]
                    self.assertEqual(actual, expected)
                    self.assertEqual(actual[:len(prefix) - 1], prefix[:-1])
                    self.assertEqual(completion.call_count - calls, expected[-1]["model_calls"] - prefix[-1]["model_calls"])

    def test_old_title_and_exact_old_rules_resume_under_the_new_cli_title(self):
        original_event = Match.event
        legacy_rules = game.RULES.replace("달라진 그림 찾기 ·", "틀린 그림 찾기 ·", 1)
        reply = encode({"action": game.EMPTY_MEMORY, "note": "기억 요약"})
        with (TemporaryDirectory() as directory, pictures(), redirect_stdout(StringIO()), redirect_stderr(StringIO()),
              patch("games.models.CodexLanguageModel._complete", return_value=reply) as completion):
            root = Path(directory)
            arguments = ["--players", *PLAYERS, "--seed", "19", "--model", "test", "--model-turns", "8"]

            def old_header(path):
                lines = path.read_bytes().splitlines(keepends=True)
                header = json.loads(lines[0])
                self.assertEqual(header["game"], SECOND_EXILE)
                lines[0] = (encode({**header, "game": LEGACY_TITLE}) + "\n").encode()
                path.write_bytes(b"".join(lines))

            full = root / "full.jsonl"
            with patch.object(game, "RULES", legacy_rules):
                run_cli(game.play, title=SECOND_EXILE, seats=4, argv=[*arguments, "--output", str(full)])
            old_header(full)
            expected = [json.loads(line) for line in full.read_text().splitlines()]
            for checkpoint in ("rules", "picture_memory", "picture_marks"):
                with self.subTest(checkpoint=checkpoint):
                    output = root / f"{checkpoint}.jsonl"

                    def interrupt(match, kind, value, **kwargs):
                        original_event(match, kind, value, **kwargs)
                        if kind == checkpoint:
                            raise RuntimeError("legacy checkpoint")

                    with (patch.object(game, "RULES", legacy_rules), patch.object(Match, "event", interrupt),
                          self.assertRaisesRegex(RuntimeError, "legacy checkpoint")):
                        run_cli(game.play, title=SECOND_EXILE, seats=4, argv=[*arguments, "--output", str(output)])
                    old_header(output)
                    saved = output.read_bytes().splitlines(keepends=True)
                    prefix = [json.loads(line) for line in saved]
                    calls = completion.call_count
                    run_cli(game.play, title=SECOND_EXILE, seats=4, argv=["--resume", "--output", str(output)])
                    self.assertTrue(output.read_bytes().startswith(b"".join(saved[:-1])))
                    actual = [json.loads(line) for line in output.read_text().splitlines()]
                    self.assertEqual(actual, expected)
                    self.assertEqual(next(row["content"] for row in actual if row.get("msg_type") == "rules"), legacy_rules)
                    self.assertEqual(actual[0]["game"], LEGACY_TITLE)
                    self.assertEqual(completion.call_count - calls,
                                     expected[-1]["model_calls"] - prefix[-1]["model_calls"])


if __name__ == "__main__":
    unittest.main()
