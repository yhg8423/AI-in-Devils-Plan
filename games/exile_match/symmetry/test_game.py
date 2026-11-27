"""Three-color private work, strict full replacements, race privacy, and resume."""

from base64 import b64decode, b64encode
from collections import OrderedDict
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from copy import deepcopy
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
from shapely.affinity import rotate

from ...match import FIFTH_EXILE, Match, encode, run_cli
from ...models import OpenAILanguageModel, StrategyNote
from . import game
from .puzzles import COLORS, judge, make_puzzles, placement_polygon


PLAYERS = ("P01", "P02", "P03", "P04")
PUZZLES = make_puzzles(19)
SOLUTION = {puzzle["id"]: puzzle["solution"] for puzzle in PUZZLES}


def arrange(placements=SOLUTION, submit=True):
    return encode({"type": "arrange", "placements": placements, "submit": submit})


def rows(match, kind):
    return [json.loads(event.content) for event in match.events if event.msg_type == kind]


def render(puzzle, placements=(), *, detailed=False):
    image = (b"\x89PNG\r\n\x1a\nEXACT-OWN-PNG" + (b"DETAIL" if detailed else b"")
             + encode({"color": puzzle["id"], "placements": placements}).encode())
    return {"id": sha256(image).hexdigest()[:16], "width": 960, "height": 640,
            "image": "data:image/png;base64," + b64encode(image).decode("ascii")}


def atlas(puzzle, *, common_scale=False):
    image = b"\x89PNG\r\n\x1a\nSTATIC-ATLAS-" + (b"COMMON-" if common_scale else b"") + puzzle["id"].encode()
    return {"id": sha256(image).hexdigest()[:16], "width": 1800, "height": 1200,
            "image": "data:image/png;base64," + b64encode(image).decode("ascii")}


def tutorial(language="en"):
    image = b"\x89PNG\r\n\x1a\nSEPARATE-PRACTICE-EXAMPLE-" + language.encode()
    return {"id": sha256(image).hexdigest()[:16], "width": 1600, "height": 1000,
            "image": "data:image/png;base64," + b64encode(image).decode("ascii")}


def workbench(puzzle, placements=(), *, axis=None):
    image = b"\x89PNG\r\n\x1a\nSILHOUETTE-" + encode({"color": puzzle["id"], "placements": placements, "axis": axis}).encode()
    return {"id": sha256(image).hexdigest()[:16], "width": 1440, "height": 900,
            "image": "data:image/png;base64," + b64encode(image).decode("ascii")}


@contextmanager
def puzzles(version=3):
    original = game._initial_protocol

    def protocol(match):
        if match.resume_log is not None and match.resume_log.resume:
            return original(match)
        return version, {2: game.LEGACY_RULES, 3: game.RULES, 4: game.FOCUS_RULES, 5: game.WORKBENCH_RULES}[version]

    with (patch.object(game, "make_puzzles", return_value=[{**puzzle, "internal": "NEVER-PUBLISH"} for puzzle in PUZZLES]),
          patch.object(game, "board", side_effect=render), patch.object(game, "piece_atlas", side_effect=atlas),
          patch.object(game, "measurement_atlas", side_effect=atlas),
          patch.object(game, "tutorial_image", side_effect=tutorial), patch.object(game, "workbench_image", side_effect=workbench),
          patch.object(game, "_initial_protocol", side_effect=protocol)):
        yield


class LiveMatch(Match):
    def __init__(self, players=PLAYERS, seed=19, *, reply=None, times=None, live_turns=200):
        super().__init__(players, seed, model=OpenAILanguageModel("test", Mock()), live_players=players,
                         live_turns=live_turns)
        self.reply = reply or (lambda name, window: arrange())
        self.times = times or {name: index for index, name in enumerate(PLAYERS)}
        self.requests = []

    def decide_together(self, phase, decisions, **kwargs):
        self.window = rows(self, "sym_window")[-1]["window"]
        answers = super().decide_together(phase, decisions, **kwargs)
        kwargs["response_times"].update({name: self.times[name] for name in decisions if name in kwargs["response_times"]})
        return answers

    def _query(self, name, prompt, *args, **kwargs):
        self.requests.append((name, self.window, prompt,
                              self.model_observations(name, self.observations(name)), kwargs["images"]))
        reply = self.reply(name, self.window)
        return reply if isinstance(reply, tuple) else (reply, StrategyNote(text=f"PRIVATE-{name}"))


class SymmetryTest(unittest.TestCase):
    def test_visible_edge_and_vertex_choices_build_actual_puzzles_without_measuring_pixels(self):
        commands = {
            "blue": [{"piece": "B2", "edge": 7, "vertex": 5, "to_piece": "B1", "to_edge": 2, "to_vertex": 4}],
            "red": [{"piece": "R2", "edge": 1, "vertex": 2, "to_piece": "R1", "to_edge": 2, "to_vertex": 2},
                    {"piece": "R3", "edge": 4, "vertex": 4, "to_piece": "R1", "to_edge": 0, "to_vertex": 1}],
            "green": [{"piece": "G2", "edge": 0, "vertex": 0, "to_piece": "G1", "to_edge": 2, "to_vertex": 3},
                      {"piece": "G3", "edge": 2, "vertex": 2, "to_piece": "G2", "to_edge": 2, "to_vertex": 3}],
        }
        for angle in (0, 17.3, 149.75):
            selected = {puzzle["id"]: [{**puzzle["solution"][0], "x": -2.125, "y": 3.75, "rotation": angle},
                                       *commands[puzzle["id"]]] for puzzle in PUZZLES}
            result = game.parse_action(arrange(selected), PUZZLES)
            for puzzle in PUZZLES:
                with self.subTest(color=puzzle["id"], angle=angle):
                    placements = result["placements"][puzzle["id"]]
                    self.assertTrue(judge(puzzle, placements))
                    self.assertTrue(all(set(row) == {"piece", "x", "y", "rotation"} for row in placements))
        before_target = {"blue": [commands["blue"][0]], "red": [], "green": []}
        with self.assertRaises(ValueError):
            game.parse_action(arrange(before_target), PUZZLES)

    def test_full_replacement_parser_requires_three_colors_and_rejects_unsafe_placement_forms(self):
        self.assertEqual(game.parse_action(game.WAIT, PUZZLES), {"type": "wait"})
        partial = {"blue": SOLUTION["blue"][:1], "red": [], "green": []}
        self.assertEqual(game.parse_action(arrange(partial, False), PUZZLES)["placements"], partial)
        invalid = [None, [], {"type": "wait", "extra": 1},
                   {"type": "arrange", "placements": partial, "submit": 1},
                   {"type": "arrange", "placements": {"blue": [], "red": []}, "submit": True},
                   {"type": "arrange", "placements": {**partial, "yellow": []}, "submit": True},
                   {"type": "arrange", "placements": partial, "submit": True, "flip": True}]
        placement = {"piece": "B1", "x": 0, "y": 0, "rotation": 0}
        for changes in ({"piece": "R1"}, {"x": True}, {"rotation": True}, {"rotation": float("nan")},
                        {"x": float("inf")}, {"y": -1_000_001}, {"flip": True}, {"piece": []}):
            invalid.append({"type": "arrange", "placements": {**partial, "blue": [{**placement, **changes}]}, "submit": True})
        invalid.append({"type": "arrange", "placements": {**partial, "blue": [placement, placement]}, "submit": True})
        invalid.append({"type": "arrange", "placements": {**partial, "green": None}, "submit": True})
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                game.parse_action(encode(value), PUZZLES)
        with self.assertRaises(ValueError):
            game.parse_action(" " * (game.MAX_ACTION_SIZE + 1), PUZZLES)
        overlap = [dict(placement, piece="B1"), dict(placement, piece="B2")]
        self.assertEqual(len(game.parse_action(arrange({**partial, "blue": overlap}), PUZZLES)["placements"]["blue"]), 2)
        continuous = {**placement, "x": -2.125, "y": 19.75, "rotation": 32.5}
        parsed = game.parse_action(arrange({**partial, "blue": [continuous]}), PUZZLES)
        self.assertEqual(parsed["placements"]["blue"], [continuous])

    def test_arrange_color_parser_validates_one_color_and_matching_focus(self):
        action = encode({"type": "arrange_color", "color": "red", "placements": SOLUTION["red"], "submit": False})
        self.assertEqual(game.parse_action(action, PUZZLES), {"type": "arrange_color", "color": "red",
                                                            "placements": SOLUTION["red"], "submit": False})
        self.assertTrue(game._accepts(action, PUZZLES, "red"))
        self.assertFalse(game._accepts(action, PUZZLES, "blue"))
        self.assertFalse(game._accepts(action, PUZZLES))
        for changes in ({"color": "yellow"}, {"color": []}, {"placements": None}, {"submit": 1}, {"extra": 1}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                game.parse_action(encode({**json.loads(action), **changes}), PUZZLES)

    def test_v4_focuses_one_color_and_preserves_other_work_with_three_images(self):
        with puzzles(4):
            match = LiveMatch(reply=lambda *args: arrange())
            result = game.play(match)
        self.assertEqual(result["turns"], 3)
        setup = rows(match, "sym_setup")[0]
        self.assertEqual((setup["version"], setup["focus_mode"], setup["focus_start_window"]), (4, "one_color", 1))
        self.assertEqual([row["focus_color"] for row in rows(match, "sym_window")], list(COLORS))
        for row in rows(match, "sym_board"):
            for index, color in enumerate(COLORS):
                self.assertEqual(row["placements"][color], SOLUTION[color] if index < row["window"] else [])
        for name, window, prompt, history, images in match.requests:
            color = tuple(COLORS)[window - 1]
            puzzle = next(p for p in PUZZLES if p["id"] == color)
            self.assertEqual(len(images), 4 if window == 1 else 3)
            self.assertEqual(images[1:3], game._image_bytes([atlas(puzzle, common_scale=True), atlas(puzzle)]))
            self.assertIn(f"이번 집중 색: {color}", prompt)
            self.assertIn("내 보존 중인 다른 색 조각 수", prompt)
            self.assertIn("이번 색이 틀렸다는 뜻이 아닙니다", prompt)
            self.assertNotIn("앞의 이미지 여섯", prompt)
        for puzzle in rows(match, "sym_puzzles")[0]["puzzles"]:
            self.assertEqual(puzzle["overview"], atlas(next(p for p in PUZZLES if p["id"] == puzzle["id"]), common_scale=True))

    def test_v4_arrange_color_updates_only_its_focus_and_rejects_other_colors(self):
        def reply(name, window):
            color = tuple(COLORS)[(window - 1) % 3]
            return encode({"type": "arrange_color", "color": color, "placements": SOLUTION[color], "submit": True})

        with puzzles(4):
            match = LiveMatch(reply=reply)
            self.assertEqual(game.play(match)["turns"], 3)
        with puzzles(4):
            wrong = encode({"type": "arrange_color", "color": "green", "placements": SOLUTION["green"], "submit": True})
            match = LiveMatch(reply=lambda *args: wrong, live_turns=4)
            result = game.play(match)
        self.assertEqual(len(rows(match, "invalid_action")), 4)
        self.assertTrue(all(row["window"] == 2 for row in rows(match, "sym_board")))
        self.assertEqual(result["turns"], 2)  # The unchanged scripted fallback still places the whole pack.

    def test_visit_memory_deduplicates_rigid_motion_and_keeps_counts_without_grading(self):
        puzzle = PUZZLES[0]
        first = deepcopy(puzzle["solution"])
        first = [{**placement, "rotation": placement["rotation"] + 360} for placement in first]
        history = OrderedDict()
        with (patch.object(game, "judge", side_effect=AssertionError("memory must not grade")),
              patch.object(game, "accepted_axes", side_effect=AssertionError("memory must not grade"))):
            game.remember_visit(history, puzzle, first, 1)
            shifted = []
            for placement in first:
                polygon = rotate(placement_polygon(puzzle, placement), 17.3, origin=(0, 0))
                shifted.append({**placement, "x": polygon.bounds[0] + 19.123456789, "y": polygon.bounds[1] - 7.5,
                                "rotation": placement["rotation"] + 17.3})
            game.remember_visit(history, puzzle, shifted, 2)
            self.assertEqual(len(history), 1)
            self.assertEqual(next(iter(history.values()))["count"], 2)
            self.assertEqual(next(iter(history.values()))["placements"], shifted)
            for n in range(1, 15):
                changed = [first[0], {**first[1], "x": first[1]["x"] + n}]
                game.remember_visit(history, puzzle, changed, 2 + n)
            game.remember_visit(history, puzzle, first, 17)
        self.assertEqual(next(reversed(history.values()))["count"], 3)
        visits = list(history.values())[-12:]
        prompt = game.focus_prompt("P01", 18, "blue", first, visits=visits)
        self.assertEqual(len(visits), 12)
        self.assertIn("방문 기록은 정답·오답 판정이 아닙니다", prompt)
        self.assertTrue(all(set(row) == {"placements", "count", "last_window"} for row in visits))

    def test_v4_review_previews_only_focus_and_stops_identical_geometry_after_first_review(self):
        passes = {}

        def reply(name, window):
            passes[name, window] = passes.get((name, window), 0) + 1
            if window > 1:
                return game.WAIT
            draft = {color: [] for color in COLORS}
            draft["blue"] = SOLUTION["blue"]
            return arrange(draft), StrategyNote(text="brief own review", review_requested=True)

        with puzzles(4):
            match = LiveMatch(reply=reply, live_turns=12)
            game.play(match)
        self.assertTrue(all(passes[name, 1] == 2 for name in PLAYERS))
        self.assertEqual(len([request for request in match.requests if request[1] == 1]), 8)
        for name in PLAYERS:
            own = [request for request in match.requests if request[0] == name and request[1] == 1]
            self.assertEqual(own[1][4][0], game._image_bytes([render(PUZZLES[0], SOLUTION["blue"], detailed=True)])[0])
            self.assertEqual(len(own[1][4]), 4)

    def test_historical_three_or_four_player_protocols_keep_their_original_cutoff(self):
        for players in (PLAYERS[:3], PLAYERS):
            with self.subTest(players=players), puzzles():
                match = LiveMatch(players, times={"P01": 90, "P02": 60, "P03": 30, "P04": 120})
                result = game.play(match)
                expected = ["P03", "P02", "P01"] + (["P04"] if len(players) == 4 else [])
                self.assertEqual(result["ranking"], expected)
                self.assertEqual(result["survivors"], expected[:-1])
                self.assertEqual(result["eliminated"], expected[-1:])
                self.assertEqual(result["turns"], 1)
                self.assertEqual(result["scores"], dict.fromkeys(players, 3))
                self.assertEqual(result["attempts"][expected[-1]], 0)
                self.assertEqual(rows(match, "sym_setup")[0]["survivors"], len(players) - 1)
                self.assertEqual(rows(match, "sym_setup")[0]["mode"], "polygons")
                self.assertEqual(rows(match, "sym_setup")[0]["version"], 3)
                self.assertNotIn("grid_size", rows(match, "sym_setup")[0])
                self.assertEqual(len(rows(match, "sym_puzzles")), 1)
                self.assertEqual([row["player"] for row in rows(match, "sym_buzz")], expected[:-1])
                self.assertFalse(match.relationship_reviews_enabled)

    def test_new_four_player_game_stops_after_two_and_eliminates_both_remaining_players(self):
        protocol = game._initial_protocol
        with puzzles(5), patch.object(game, "_initial_protocol", side_effect=protocol):
            match = LiveMatch(reply=lambda name, window: arrange(submit=window >= 3),
                              times={"P01": 90, "P02": 60, "P03": 30, "P04": 120})
            result = game.play(match)
        self.assertEqual(result["survivors"], ["P03", "P02"])
        self.assertEqual(result["eliminated"], ["P01", "P04"])
        self.assertEqual(result["ranking_groups"], [["P03"], ["P02"], ["P01", "P04"]])
        self.assertEqual(rows(match, "sym_setup")[0]["survivors"], 2)
        self.assertEqual(len(rows(match, "sym_finish")), 2)
        self.assertEqual([row["player"] for row in rows(match, "sym_buzz")], ["P03", "P02"])
        self.assertTrue(all(result["attempts"][name] == 0 for name in result["eliminated"]))
        self.assertIn("먼저 완성한 2명이 생존", next(event.content for event in match.events if event.msg_type == "rules"))
        with self.assertRaisesRegex(ValueError, "4명"):
            game.play(Match(PLAYERS[:3], 19))

    def test_historical_three_player_log_keeps_its_two_survivors_on_resume(self):
        original_event = Match.event

        def stop_after_first_finisher(match, kind, value, **kwargs):
            original_event(match, kind, value, **kwargs)
            if kind == "sym_finish":
                raise RuntimeError("historical finisher saved")

        with (TemporaryDirectory() as directory, puzzles(3), redirect_stdout(StringIO()), redirect_stderr(StringIO()),
              patch.object(Match, "_query", return_value=(arrange(), StrategyNote(text="private"))),
              patch("games.match.monotonic_ns", return_value=70_000_000_000)):
            full, partial = Path(directory) / "full.jsonl", Path(directory) / "partial.jsonl"
            arguments = ["--players", *PLAYERS[:3], "--seed", "19", "--model", "test", "--model-turns", "3"]
            run_cli(game.play, title=FIFTH_EXILE, seats=(4, 3), argv=[*arguments, "--output", str(full)])
            with patch.object(Match, "event", stop_after_first_finisher), self.assertRaisesRegex(RuntimeError, "historical finisher"):
                run_cli(game.play, title=FIFTH_EXILE, seats=(4, 3), argv=[*arguments, "--output", str(partial)])
            before = partial.read_text().splitlines()
            setup = next(json.loads(row["content"]) for row in map(json.loads, before)
                         if row.get("msg_type") == "sym_setup")
            self.assertEqual(setup["survivors"], 2)
            self.assertEqual(len(setup["players"]), 3)
            with patch.object(Match, "_query", side_effect=AssertionError("saved response queried twice")):
                run_cli(game.play, title=FIFTH_EXILE, seats=(4, 3), argv=["--resume", "--output", str(partial)])
            self.assertEqual(partial.read_bytes(), full.read_bytes())
            self.assertEqual(partial.read_text().splitlines()[:len(before) - 1], before[:-1])

    def test_equal_slow_responses_follow_disclosed_priority_without_a_timer(self):
        with puzzles():
            match = LiveMatch(times=dict.fromkeys(PLAYERS, 900_000_000_000))
            result = game.play(match)
        self.assertEqual(result["ranking"], rows(match, "sym_setup")[0]["priority"])
        self.assertTrue(all(row["correct"] for row in rows(match, "sym_verdict")))

    def test_partial_overlap_wait_and_format_failure_keep_own_work_then_allow_retries(self):
        incomplete = deepcopy(SOLUTION)
        incomplete["green"] = incomplete["green"][:-1]
        work = {"blue": SOLUTION["blue"], "red": [{"piece": "R1", "x": 0, "y": 0, "rotation": 0},
                                                     {"piece": "R2", "x": 0, "y": 0, "rotation": 0}], "green": []}

        def reply(name, window):
            if window == 1:
                return {"P01": arrange(submit=False), "P02": arrange(incomplete),
                        "P03": arrange(work, False), "P04": game.WAIT}[name]
            if window == 2:
                return arrange() if name == "P01" else "broken JSON" if name == "P02" else game.WAIT
            return arrange() if name in {"P02", "P04"} else arrange({**work, "green": [{"piece": "G1", "x": True, "y": 0, "rotation": 0}]})

        with puzzles():
            match = LiveMatch(reply=reply)
            result = game.play(match)
        self.assertEqual(result["ranking"], ["P01", "P02", "P04", "P03"])
        self.assertEqual(result["turns"], 3)
        self.assertEqual(result["scores"], {"P01": 3, "P02": 3, "P03": 1, "P04": 3})
        self.assertEqual(result["attempts"], {"P01": 1, "P02": 2, "P03": 0, "P04": 1})
        self.assertEqual([row["correct"] for row in rows(match, "sym_verdict")], [False, True, True, True])
        self.assertEqual(rows(match, "sym_window")[2]["active"], ["P02", "P03", "P04"])
        self.assertEqual(len(rows(match, "invalid_action")), 2)
        self.assertEqual(len(rows(match, "sym_board")), 6)
        self.assertEqual(rows(match, "sym_reveal")[0]["boards"]["P03"]["placements"], work)
        initial = {puzzle["id"]: puzzle["board"] for puzzle in rows(match, "sym_puzzles")[0]["puzzles"]}
        for name, window, prompt, history, images in match.requests:
            previous = [row for row in rows(match, "sym_board") if row["player"] == name and row["window"] < window]
            expected = previous[-1]["boards"] if previous else initial
            self.assertEqual(images[:3], tuple(b64decode(expected[color]["image"].partition(",")[2]) for color in COLORS))
            self.assertEqual(images[3:6], game._image_bytes([atlas(puzzle) for puzzle in PUZZLES]))
            self.assertEqual(len(images), 7 if window == 1 else 6)
            self.assertEqual([event.msg_type for event in history], ["rules"])
            self.assertNotIn("NEVER-PUBLISH", prompt)
            if window > 1:
                self.assertIn(f"PRIVATE-{name}", prompt)
            self.assertNotIn('"cells"', prompt)
            for other in PLAYERS:
                if other != name:
                    self.assertNotIn(f"PRIVATE-{other}", prompt)

    def test_replacing_with_empty_color_lists_erases_previous_work(self):
        empty = {color: [] for color in COLORS}

        def reply(name, window):
            return arrange(submit=False) if window == 1 else arrange(empty, False) if window == 2 else arrange()

        with puzzles():
            match = LiveMatch(reply=reply)
            game.play(match)
        self.assertTrue(all(row["placements"] == empty for row in rows(match, "sym_board") if row["window"] == 2))

    def test_malformed_live_replies_do_not_get_solved_defaults_and_wait_uses_normal_call_budget(self):
        for reply in ("invalid JSON", game.WAIT):
            with self.subTest(reply=reply), puzzles():
                match = LiveMatch(reply=lambda *args: reply, live_turns=8)
                result = game.play(match)
                self.assertEqual(result["turns"], 3)
                self.assertEqual(len(rows(match, "sym_puzzles")), 1)
                self.assertTrue(all(row["window"] == 3 for row in rows(match, "sym_board")))
                self.assertTrue(all(row["window"] == 3 for row in rows(match, "sym_verdict")))
                self.assertEqual(len(rows(match, "invalid_action")), 8 if reply != game.WAIT else 0)

    def test_no_work_completed_color_hints_or_fixtures_are_public_before_final_reveal(self):
        with puzzles():
            match = LiveMatch()
            game.play(match)
        reveal = next(index for index, event in enumerate(match.events) if event.msg_type == "sym_reveal")
        finishes = [index for index, event in enumerate(match.events) if event.msg_type == "sym_finish"]
        self.assertEqual(len(finishes), 3)
        self.assertGreater(reveal, max(finishes))
        for index, event in enumerate(match.events):
            if event.msg_type in {"action", "decision_note", "sym_board"}:
                self.assertEqual(event.visible_to, [event.agent_name])
            if event.msg_type in {"sym_buzz", "sym_verdict", "sym_finish"}:
                self.assertEqual(event.visible_to, "all")
                self.assertFalse({"placements", "boards", "axes", "colors", "scores"} & set(json.loads(event.content)))
            if index < reveal and event.visible_to == "all" and event.msg_type not in {"rules", "sym_tutorial"}:
                self.assertNotIn("solution", event.content)
                self.assertNotIn('"cells"', event.content)
        for puzzle in rows(match, "sym_puzzles")[0]["puzzles"]:
            self.assertEqual(set(puzzle), {"id", "label", "piece_ids", "board", "details"})
        self.assertEqual(set(rows(match, "sym_reveal")[0]["boards"]), set(PLAYERS))

    def test_initial_model_requests_never_contain_scripted_fixture_placements(self):
        with puzzles():
            match = LiveMatch()
            game.play(match)
        kinds = [event.msg_type for event in match.events]
        self.assertEqual(kinds[kinds.index("sym_puzzles") + 1:kinds.index("sym_window")], ["sym_tutorial"])
        self.assertEqual(rows(match, "sym_tutorial"), [{"version": 1, "board": tutorial(),
                                                      "explanations": game.TUTORIAL_EXPLANATIONS}])
        for name, window, prompt, history, images in match.requests:
            self.assertEqual(len(images), 7)
            self.assertNotIn(encode(SOLUTION), prompt)
            self.assertIn(encode({color: [] for color in COLORS}), prompt)
            self.assertIn("시계 방향", prompt)
            self.assertIn("왼쪽 위", prompt)
            self.assertIn("부분 접합", prompt)
            self.assertIn("길이가 다른 변", prompt)
            self.assertIn("점 접촉", prompt)
            self.assertIn(game.TUTORIAL_EXPLANATIONS["ko"], prompt)
            self.assertIn("일곱 번째 이미지", prompt)
            self.assertEqual(images[6:], game._image_bytes([tutorial()]))

    def test_own_final_notes_and_failed_whole_packs_are_bounded_and_private(self):
        def reply(name, window):
            placements = {"blue": [{"piece": "B1", "x": PLAYERS.index(name) * 100 + window + .123456789012345,
                                    "y": -1.23456789012345, "rotation": 17.125}], "red": [], "green": []}
            return (arrange() if window == 15 else arrange(placements),
                    StrategyNote(text=f"NOTE-{name}-{window}"))

        with puzzles():
            match = LiveMatch(reply=reply)
            game.play(match)
        for name, window, prompt, history, images in match.requests:
            if window != 15:
                continue
            note_text = prompt.split("내 최근 최종 전략 메모 (최대 3개): ", 1)[1].split("\n", 1)[0]
            failure_text = prompt.split("내 최근 전체 검사 실패 기록 (최대 12개): ", 1)[1]
            self.assertEqual(json.loads(note_text), [{"window": n, "note": f"NOTE-{name}-{n}"} for n in (12, 13, 14)])
            failures = json.loads(failure_text)
            self.assertEqual([row["window"] for row in failures], list(range(3, 15)))
            for failure in failures:
                self.assertEqual(set(failure), {"window", "action", "correct"})
                self.assertFalse(failure["correct"])
                action = json.loads(failure["action"])
                self.assertEqual(set(action["placements"]), set(COLORS))
                self.assertEqual(action["placements"]["blue"][0]["x"],
                                 PLAYERS.index(name) * 100 + failure["window"] + .123456789012345)
            self.assertIn(encode({"piece": "B1", "x": PLAYERS.index(name) * 100 + 14 + .123456789012345,
                                  "y": -1.23456789012345, "rotation": 17.125}), prompt)
            for other in PLAYERS:
                if other != name:
                    self.assertNotIn(f"NOTE-{other}-", prompt)

    def test_three_passes_preview_own_drafts_without_judging_and_record_only_final_work(self):
        passes = dict.fromkeys(PLAYERS[:3], 0)
        first = {"blue": SOLUTION["blue"][:1], "red": [], "green": []}
        second = {"blue": SOLUTION["blue"], "red": SOLUTION["red"][:1], "green": []}

        def reply(name, window):
            self.assertEqual(judging.call_count, 0)
            passes[name] += 1
            step = passes[name]
            return arrange((first, second, SOLUTION)[step - 1]), StrategyNote(
                text=f"PASS-{name}-{step}", review_requested=step < 3)

        with puzzles(), patch.object(game, "judge", wraps=game.judge) as judging:
            match = LiveMatch(PLAYERS[:3], reply=reply, live_turns=9)
            game.play(match)
        self.assertEqual(passes, dict.fromkeys(PLAYERS[:3], 3))
        self.assertEqual(match.live_turns, 0)
        self.assertEqual(len(rows(match, "sym_board")), 3)
        self.assertTrue(all(row["placements"] == SOLUTION for row in rows(match, "sym_board")))
        self.assertEqual(len(rows(match, "action")), 3)
        self.assertEqual(len(rows(match, "sym_buzz")), 2)
        for name in PLAYERS[:3]:
            requests = [request for request in match.requests if request[0] == name]
            for request, placements in zip(requests, ({color: [] for color in COLORS}, first, second), strict=True):
                self.assertEqual(request[4][:3], game._image_bytes([
                    render(puzzle, placements[puzzle["id"]], detailed=True) for puzzle in PUZZLES]))
                self.assertEqual(request[4][3:6], game._image_bytes([atlas(puzzle) for puzzle in PUZZLES]))
                self.assertEqual(request[4][6:], game._image_bytes([tutorial()]))
                self.assertNotIn('"correct":', request[2])
                self.assertNotIn("색별 정답 여부:", request[2])
        notes = rows(match, "decision_note")
        self.assertEqual(sum(note.get("review") is True for note in notes), 6)
        self.assertEqual(sum(not note.get("review") for note in notes), 3)

    def test_review_false_stops_after_one_pass(self):
        with puzzles():
            match = LiveMatch(PLAYERS[:3])
            game.play(match)
        self.assertEqual(len(match.requests), 3)
        self.assertFalse(any(row.get("review") for row in rows(match, "decision_note")))

    def test_next_window_carries_final_note_without_interim_drafts(self):
        counts = {}

        def reply(name, window):
            key = name, window
            counts[key] = counts.get(key, 0) + 1
            draft = window == 1 and counts[key] == 1
            return (arrange() if window == 2 else arrange({color: [] for color in COLORS}),
                    StrategyNote(text=f"{'DRAFT' if draft else 'FINAL'}-{name}", review_requested=draft))

        with puzzles():
            match = LiveMatch(PLAYERS[:3], reply=reply, live_turns=9)
            game.play(match)
        for name, window, prompt, history, images in match.requests:
            self.assertEqual(len(images), 7 if window == 1 else 6)
            self.assertIn(game.TUTORIAL_EXPLANATIONS["ko"], prompt)
            if window == 2:
                self.assertIn(f"FINAL-{name}", prompt)
                self.assertNotIn("DRAFT-", prompt)
                self.assertNotIn("일곱 번째 이미지", prompt)

    def test_scripted_game_is_deterministic_preserves_pieces_and_requires_three_or_four_unique_players(self):
        with puzzles():
            first, second = Match(PLAYERS, 19, pieces=[0, 1, 2, 3]), Match(PLAYERS, 19, pieces=[0, 1, 2, 3])
            self.assertEqual(game.play(first), game.play(second))
        self.assertEqual(first.pieces, dict(zip(PLAYERS, [0, 1, 2, 3], strict=True)))
        self.assertEqual([(event.msg_type, event.content) for event in first.events],
                         [(event.msg_type, event.content) for event in second.events])
        for players in (PLAYERS[:2], (*PLAYERS, "P05"), ("P01",) * 3):
            with self.subTest(players=players), self.assertRaises(ValueError):
                game.play(Match(players, 1))

    def test_initial_and_private_interruptions_restore_tutorial_and_race_without_duplicate_queries(self):
        original_event = Match.event
        with (TemporaryDirectory() as directory, puzzles(5), redirect_stdout(StringIO()), redirect_stderr(StringIO()),
              patch.object(Match, "_query", return_value=(arrange(), StrategyNote(text="private"))),
              patch("games.match.monotonic_ns", return_value=70_000_000_000)):
            root = Path(directory)
            full = root / "full.jsonl"
            arguments = ["--players", *PLAYERS, "--seed", "19", "--model", "test", "--model-turns", "4"]
            run_cli(game.play, title=FIFTH_EXILE, seats=(3, 4), argv=[*arguments, "--output", str(full)])
            expected = [json.loads(line) for line in full.read_text().splitlines()]
            historical_setup = next(json.loads(row["content"]) for row in expected if row.get("msg_type") == "sym_setup")
            self.assertEqual(historical_setup["survivors"], 3)
            saved = json.loads(full.with_name("full.decisions.jsonl").read_text().splitlines()[0])["value"]["value"]
            self.assertTrue(all(reply[2] == 0 for reply in saved.values()))
            initial = {"rules", "sym_setup", "sym_puzzles", "sym_tutorial"}
            for checkpoint in ("rules", "sym_setup", "sym_puzzles", "sym_tutorial", "decision_note", "action",
                               "sym_board", "sym_buzz", "sym_verdict", "sym_finish", "sym_reveal"):
                with self.subTest(checkpoint=checkpoint):
                    output = root / f"{checkpoint}.jsonl"

                    def interrupt(match, kind, value, **kwargs):
                        original_event(match, kind, value, **kwargs)
                        if kind == checkpoint:
                            raise RuntimeError("interrupted after committed event")

                    with patch.object(Match, "event", interrupt), self.assertRaisesRegex(RuntimeError, "committed event"):
                        run_cli(game.play, title=FIFTH_EXILE, seats=(3, 4), argv=[*arguments, "--output", str(output)])
                    prefix = [json.loads(line) for line in output.read_text().splitlines()]
                    replies = patch.object(Match, "_query", return_value=(arrange(), StrategyNote(text="private"))) if checkpoint in initial else patch.object(
                        Match, "_query", side_effect=AssertionError("committed response queried twice"))
                    with (replies as query_mock,
                          patch.object(game, "tutorial_image", side_effect=tutorial if checkpoint in initial - {"sym_tutorial"} else
                                       AssertionError("saved tutorial regenerated")) as image_mock,
                          patch("games.match.monotonic_ns", return_value=999_000_000_000)):
                        run_cli(game.play, title=FIFTH_EXILE, seats=(3, 4), argv=["--resume", "--output", str(output)])
                    self.assertEqual(query_mock.call_count, 4 if checkpoint in initial else 0)
                    self.assertEqual(image_mock.call_count, 1 if checkpoint in initial - {"sym_tutorial"} else 0)
                    actual = [json.loads(line) for line in output.read_text().splitlines()]
                    self.assertEqual(actual, expected)
                    self.assertEqual(actual[:len(prefix) - 1], prefix[:-1])

    def test_v2_replays_legacy_images_then_migrates_once_and_resumes_modern_private_checkpoints(self):
        original_event = Match.event
        with (TemporaryDirectory() as directory, puzzles(), redirect_stdout(StringIO()), redirect_stderr(StringIO()),
              patch("games.match.monotonic_ns", return_value=70_000_000_000)):
            root = Path(directory)
            old = root / "v2.jsonl"
            arguments = ["--players", *PLAYERS, "--seed", "19", "--model", "test", "--model-turns", "40"]

            def stop_v2(match, kind, value, **kwargs):
                original_event(match, kind, value, **kwargs)
                if kind == "sym_window" and value["window"] == 2:
                    raise RuntimeError("old checkpoint")

            with (patch.object(game, "_initial_protocol", return_value=(2, game.LEGACY_RULES)),
                  patch.object(Match, "_query", return_value=(arrange({color: [] for color in COLORS}), StrategyNote(text="OLD-OWN"))),
                  patch.object(Match, "event", stop_v2), self.assertRaisesRegex(RuntimeError, "old checkpoint")):
                run_cli(game.play, title=FIFTH_EXILE, seats=(3, 4), argv=[*arguments, "--output", str(old)])
            old_bytes = old.read_bytes()
            old_journal = old.with_name("v2.decisions.jsonl").read_bytes()
            prefix = [json.loads(line) for line in old_bytes.splitlines()][:-1]
            self.assertEqual(json.loads(prefix[2]["content"])["version"], 2)
            saved_explanation = game.TUTORIAL_EXPLANATIONS["ko"]
            queried = []

            def query(match, name, prompt, *args, **kwargs):
                queried.append(name)
                window = rows(match, "sym_window")[-1]["window"]
                self.assertEqual(len(kwargs["images"]), 5)
                self.assertIn("OLD-OWN", prompt)
                self.assertIn('"window":1', prompt)
                self.assertIn("부분 접합", prompt)
                self.assertIn(saved_explanation, prompt)
                self.assertNotIn("CHANGED-TUTORIAL", prompt)
                return arrange(), StrategyNote(text="MODERN-OWN")

            def fork(name):
                output = root / f"{name}.jsonl"
                output.write_bytes(old_bytes)
                output.with_name(f"{name}.decisions.jsonl").write_bytes(old_journal)
                return output

            full = fork("full")
            with patch.object(Match, "_query", query):
                run_cli(game.play, title=FIFTH_EXILE, seats=(3, 4), argv=["--resume", "--output", str(full)])
            expected = [json.loads(line) for line in full.read_text().splitlines()]
            self.assertEqual(len(queried), 12)
            self.assertEqual(expected[:len(prefix)], prefix)
            tools = [row for row in expected if row.get("msg_type") == "sym_tools"]
            self.assertEqual(len(tools), 1)
            self.assertEqual(json.loads(tools[0]["content"])["thinking_passes"], 3)
            tool_index = expected.index(tools[0])
            self.assertEqual(expected[tool_index - 1]["msg_type"], "sym_window")
            self.assertNotIn("details", prefix[3]["content"])
            for checkpoint in ("sym_tools", "sym_tutorial", "decision_note", "action", "sym_board"):
                output = fork(checkpoint)
                queried.clear()

                def interrupt(match, kind, value, **kwargs):
                    original_event(match, kind, value, **kwargs)
                    upgraded = any(event.msg_type == "sym_tools" for event in match.events)
                    if upgraded and kind == checkpoint:
                        raise RuntimeError("modern checkpoint")

                with (patch.object(Match, "_query", query), patch.object(Match, "event", interrupt),
                      self.assertRaisesRegex(RuntimeError, "modern checkpoint")):
                    run_cli(game.play, title=FIFTH_EXILE, seats=(3, 4), argv=["--resume", "--output", str(output)])
                changed_text = {"ko": "CHANGED-TUTORIAL", "en": "CHANGED-TUTORIAL"}
                with patch.object(Match, "_query", query), patch.object(game, "TUTORIAL_EXPLANATIONS", changed_text if checkpoint == "sym_tutorial" else game.TUTORIAL_EXPLANATIONS):
                    run_cli(game.play, title=FIFTH_EXILE, seats=(3, 4), argv=["--resume", "--output", str(output)])
                self.assertEqual([json.loads(line) for line in output.read_text().splitlines()], expected)
                self.assertEqual(len(queried), 12)

    def test_existing_v3_without_tutorial_preserves_prefix_before_one_safe_migration(self):
        original_event = Match.event
        with (TemporaryDirectory() as directory, puzzles(), redirect_stdout(StringIO()), redirect_stderr(StringIO()),
              patch("games.match.monotonic_ns", return_value=70_000_000_000)):
            root = Path(directory)
            arguments = ["--players", *PLAYERS, "--seed", "19", "--model", "test", "--model-turns", "20"]
            for checkpoint in ("sym_board", "sym_window"):
                output = root / f"old-v3-{checkpoint}.jsonl"

                def interrupt(match, kind, value, **kwargs):
                    original_event(match, kind, value, **kwargs)
                    if kind == checkpoint and (kind != "sym_window" or value["window"] == 2):
                        raise RuntimeError("pre-tutorial checkpoint")

                with (patch.object(game, "_tutorial_at_start", return_value=False),
                      patch.object(Match, "event", interrupt),
                      patch.object(Match, "_query", return_value=(arrange({color: [] for color in COLORS}), StrategyNote(text="OLD-V3"))),
                      self.assertRaisesRegex(RuntimeError, "pre-tutorial checkpoint")):
                    run_cli(game.play, title=FIFTH_EXILE, seats=(3, 4), argv=[*arguments, "--output", str(output)])
                prefix = [json.loads(line) for line in output.read_text().splitlines()][:-1]
                self.assertFalse(any(row.get("msg_type") == "sym_tutorial" for row in prefix))
                calls = []

                def query(match, name, prompt, *args, **kwargs):
                    calls.append(name)
                    window = rows(match, "sym_window")[-1]["window"]
                    self.assertEqual(len(kwargs["images"]), 5)
                    self.assertIn(game.TUTORIAL_EXPLANATIONS["ko"], prompt)
                    return arrange(), StrategyNote(text="NEW-V3")

                with patch.object(Match, "_query", query):
                    run_cli(game.play, title=FIFTH_EXILE, seats=(3, 4), argv=["--resume", "--output", str(output)])
                actual = [json.loads(line) for line in output.read_text().splitlines()]
                self.assertEqual(actual[:len(prefix)], prefix)
                examples = [index for index, row in enumerate(actual) if row.get("msg_type") == "sym_tutorial"]
                self.assertEqual(len(examples), 1)
                before = next(row for row in reversed(actual[:examples[0]]) if row.get("msg_type") == "sym_window")
                self.assertEqual(before["msg_type"], "sym_window")
                self.assertEqual(json.loads(before["content"])["window"], 2)
                self.assertEqual(len(calls), 12)

    def test_v2_rules_only_prefix_keeps_legacy_setup_before_tools_and_tutorial(self):
        original_event = Match.event
        with (TemporaryDirectory() as directory, puzzles(), redirect_stdout(StringIO()), redirect_stderr(StringIO()),
              patch("games.match.monotonic_ns", return_value=70_000_000_000)):
            output = Path(directory) / "v2-rules.jsonl"
            arguments = ["--players", *PLAYERS, "--seed", "19", "--model", "test", "--model-turns", "4"]

            def interrupt(match, kind, value, **kwargs):
                original_event(match, kind, value, **kwargs)
                if kind == "rules":
                    raise RuntimeError("legacy rules checkpoint")

            with (patch.object(game, "_initial_protocol", return_value=(2, game.LEGACY_RULES)),
                  patch.object(Match, "event", interrupt), self.assertRaisesRegex(RuntimeError, "legacy rules checkpoint")):
                run_cli(game.play, title=FIFTH_EXILE, seats=(3, 4), argv=[*arguments, "--output", str(output)])
            prefix = [json.loads(line) for line in output.read_text().splitlines()][:-1]
            with patch.object(Match, "_query", return_value=(arrange(), StrategyNote())) as query:
                run_cli(game.play, title=FIFTH_EXILE, seats=(3, 4), argv=["--resume", "--output", str(output)])
            actual = [json.loads(line) for line in output.read_text().splitlines()]
            self.assertEqual(actual[:len(prefix)], prefix)
            self.assertEqual(json.loads(next(row["content"] for row in actual if row.get("msg_type") == "sym_setup"))["version"], 2)
            kinds = [row.get("msg_type") for row in actual]
            window = kinds.index("sym_window")
            self.assertEqual(kinds[window:window + 3], ["sym_window", "sym_tools", "sym_tutorial"])
            self.assertEqual(query.call_count, 4)

    def test_saved_tools3_replays_exactly_before_tools5_even_at_same_window(self):
        original_event = Match.event
        with (TemporaryDirectory() as directory, puzzles(2), redirect_stdout(StringIO()), redirect_stderr(StringIO()),
              patch("games.match.monotonic_ns", return_value=70_000_000_000)):
            output = Path(directory) / "tools3.jsonl"
            arguments = ["--players", *PLAYERS, "--seed", "19", "--model", "test", "--model-turns", "16"]
            tools3 = {"version": 3, "thinking_passes": 3,
                      "puzzles": [{"id": puzzle["id"], "details": atlas(puzzle)} for puzzle in PUZZLES]}

            def interrupt(match, kind, value, **kwargs):
                original_event(match, kind, value, **kwargs)
                if kind == "sym_window" and value["window"] == 2:
                    original_event(match, "sym_tools", tools3)
                    raise RuntimeError("saved tools3 checkpoint")

            with (patch.object(Match, "event", interrupt),
                  patch.object(Match, "_query", return_value=(arrange({color: [] for color in COLORS}), StrategyNote())),
                  self.assertRaisesRegex(RuntimeError, "saved tools3 checkpoint")):
                run_cli(game.play, title=FIFTH_EXILE, seats=(3, 4), argv=[*arguments, "--output", str(output)])
            prefix = [json.loads(line) for line in output.read_text().splitlines()][:-1]
            with patch.object(Match, "_query", return_value=(arrange(), StrategyNote())) as query:
                run_cli(game.play, title=FIFTH_EXILE, seats=(3, 4), argv=["--resume", "--output", str(output)])
            actual = [json.loads(line) for line in output.read_text().splitlines()]
            self.assertEqual(actual[:len(prefix)], prefix)
            tools = [json.loads(row["content"]) for row in actual if row.get("msg_type") == "sym_tools"]
            self.assertEqual(tools[0], tools3)
            self.assertEqual([tool["version"] for tool in tools], [3, 5])
            self.assertEqual((tools[1]["focus_start_window"], tools[1]["focus_color"]), (2, "blue"))
            self.assertEqual(query.call_count, 12)

    def test_v3_review_note_checkpoints_replay_committed_passes_and_query_only_remaining_passes(self):
        original_event = Match.event
        with (TemporaryDirectory() as directory, puzzles(), redirect_stdout(StringIO()), redirect_stderr(StringIO()),
              patch("games.match.monotonic_ns", return_value=70_000_000_000)):
            root = Path(directory)
            arguments = ["--players", *PLAYERS, "--seed", "19", "--model", "test", "--model-turns", "12"]
            queried = []

            def query(match, name, prompt, *args, **kwargs):
                queried.append(name)
                return arrange(), StrategyNote(text="BRIEF-OWN", review_requested=kwargs["allow_review"])

            full = root / "full.jsonl"
            with patch.object(Match, "_query", query):
                run_cli(game.play, title=FIFTH_EXILE, seats=(3, 4), argv=[*arguments, "--output", str(full)])
            expected = [json.loads(line) for line in full.read_text().splitlines()]
            self.assertEqual(len(queried), 12)
            for pass_number, first_calls in ((1, 4), (2, 8)):
                output = root / f"review-{pass_number}.jsonl"

                def interrupt(match, kind, value, **kwargs):
                    original_event(match, kind, value, **kwargs)
                    if kind == "decision_note" and value.get("pass") == pass_number:
                        raise RuntimeError("review checkpoint")

                queried.clear()
                with (patch.object(Match, "_query", query), patch.object(Match, "event", interrupt),
                      self.assertRaisesRegex(RuntimeError, "review checkpoint")):
                    run_cli(game.play, title=FIFTH_EXILE, seats=(3, 4), argv=[*arguments, "--output", str(output)])
                self.assertEqual(len(queried), first_calls)
                queried.clear()
                with patch.object(Match, "_query", query):
                    run_cli(game.play, title=FIFTH_EXILE, seats=(3, 4), argv=["--resume", "--output", str(output)])
                self.assertEqual(len(queried), 12 - first_calls)
                self.assertEqual([json.loads(line) for line in output.read_text().splitlines()], expected)


if __name__ == "__main__":
    unittest.main()
