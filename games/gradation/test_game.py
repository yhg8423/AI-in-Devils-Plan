"""Hidden cup identity, preparation validation, tournament streaks, and resume."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from io import BytesIO, StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from games import match as runtime
from games.match import Match, encode, run_cli
from games.models import StrategyNote
from .__main__ import main
from .game import (COLORS, TITLE, Duel, accepts_layout, accepts_slot, board_image,
                   observations, parse_layout, parse_slot, play, validate_numbers)


LOW = [0, 0, 1, 1, 2, 2, 3]
HIGH = [1, 2, 3, 4, 5, 6, 8]
PLAYERS = ["A", "B", "C"]


def rows(match, kind):
    return [json.loads(event.content) for event in match.events if event.msg_type == kind]


def controlled(outcomes, players=PLAYERS):
    """Play real legal layouts whose sorted corresponding slots force each winner."""
    match = Match(players, 19)
    original_prepare, original_choose = match.decide_together, match.decide
    def prepare(phase, decisions, **kwargs):
        number = len(rows(match, "grad_match"))
        winner = outcomes[number - 1]
        decisions = {name: replace(decision, default=encode({"numbers": HIGH if name == winner else LOW}))
                     for name, decision in decisions.items()}
        return original_prepare(phase, decisions, **kwargs)
    def choose(name, phase, prompt, default, **kwargs):
        return original_choose(name, phase, prompt, kwargs["options"][0], **kwargs)
    match.decide_together, match.decide = prepare, choose
    with patch.object(match.rng, "sample", return_value=list(players)):
        result = play(match)
    return match, result


class LayoutTests(unittest.TestCase):
    def test_seven_sorted_integer_numbers_inventory_and_sum(self):
        self.assertEqual(validate_numbers(LOW), LOW)
        self.assertEqual(validate_numbers([3, 3, 4, 4, 5, 5, 6]), [3, 3, 4, 4, 5, 5, 6])
        self.assertEqual(parse_layout(encode({"numbers": HIGH})), HIGH)
        for invalid in (LOW[:-1], [0] * 7, [0, 0, 1, 1, 2, 2, True],
                        [0, 0, 1, 1, 2, 2, 10], [0, 0, 1, 1, 2, 2, -1],
                        [0, 0, 1, 1, 2, 3, 2], [3, 3, 4, 4, 5, 5, 7],
                        [0, 0, 1, 1, 2, 2, 3.0], tuple(LOW)):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_numbers(invalid)
            if not isinstance(invalid, tuple):
                self.assertFalse(accepts_layout(encode({"numbers": invalid})))
        self.assertFalse(accepts_layout(encode({"numbers": LOW, "sum": 9})))
        self.assertFalse(accepts_layout("invalid"))

    def test_own_slot_validation_and_consumption_are_atomic(self):
        duel = Duel(["A", "B"], {"A": LOW, "B": HIGH})
        self.assertEqual(parse_slot('{"slot": 1}', duel.unused["A"]), 1)
        self.assertEqual(duel.take("A", 1), {"color": "black", "value": 0})
        before = duel.remaining()
        for slot in (1, True, 0, 8, "2"):
            with self.subTest(slot=slot), self.assertRaises(ValueError):
                duel.take("A", slot)
            self.assertEqual(duel.remaining(), before)
        self.assertFalse(accepts_slot('{"slot":true}', {1, 2}))
        self.assertFalse(accepts_slot('{"slot":2,"value":1}', {1, 2}))

    def test_scoring_and_round_ties_preserve_the_leader(self):
        duel = Duel(["A", "B"], {"A": LOW, "B": HIGH})
        winner, leader = duel.reveal({"A": {"value": 3}, "B": {"value": 4}}, "A")
        self.assertEqual((winner, leader, duel.scores), ("B", "B", {"A": 0, "B": 1}))
        self.assertEqual(duel.reveal({"A": {"value": 3}, "B": {"value": 3}}, "A"), (None, "A"))
        self.assertEqual(duel.scores, {"A": 0, "B": 1})


class PrivacyTests(unittest.TestCase):
    def test_rendered_color_groups_grow_lighter_toward_the_center(self):
        import pygame
        picture = pygame.image.load(BytesIO(board_image("A", ["A", "B"])))
        brightness = [sum(picture.get_at((45 + index * 264, 185))[:3]) for index in range(4)]
        self.assertEqual(brightness, sorted(brightness))
        self.assertEqual(len(set(brightness)), 4)

    def test_images_hide_opponent_numbers_and_which_same_color_end_was_used(self):
        first = Duel(["A", "B"], {"A": LOW, "B": LOW})
        second = Duel(["A", "B"], {"A": LOW, "B": HIGH})
        self.assertEqual(board_image("A", first.players, LOW, first.unused["A"], first.remaining()),
                         board_image("A", second.players, LOW, second.unused["A"], second.remaining()))
        first.take("B", 1)
        second.take("B", 7)
        self.assertEqual(first.remaining(), second.remaining())
        first_image = board_image("A", first.players, LOW, first.unused["A"], first.remaining(), {"B": "black"})
        second_image = board_image("A", second.players, LOW, second.unused["A"], second.remaining(), {"B": "black"})
        self.assertEqual(first_image, second_image)
        self.assertNotEqual(board_image("A", first.players, LOW), board_image("A", first.players, HIGH))
        self.assertTrue(first_image.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_public_offers_and_remaining_never_contain_original_slot_identity(self):
        match, _ = controlled(["A", "A"])
        public = [event for event in match.events if event.visible_to == "all"]
        self.assertFalse(any(event.msg_type in {"grad_layout", "grad_selection"} for event in public))
        for event in public:
            if event.msg_type == "grad_offer":
                self.assertEqual(set(json.loads(event.content)), {"match", "round", "player", "color"})
            if event.msg_type == "grad_round":
                remaining = json.loads(event.content)["remaining"]
                self.assertTrue(all(set(counts) == {"black", "silver", "gray", "white"} for counts in remaining.values()))
            if event.msg_type == "grad_reveal":
                self.assertTrue(all(set(choice) == {"color", "value"} for choice in json.loads(event.content)["choices"].values()))
        for index, event in enumerate(match.events):
            if event.msg_type != "grad_offer":
                continue
            current = json.loads(event.content)
            same_round = [row for row in match.events[:index + 1] if row.msg_type == "grad_offer"
                          and (json.loads(row.content)["match"], json.loads(row.content)["round"])
                          == (current["match"], current["round"])]
            if len(same_round) == 1:
                self.assertFalse(any(row.msg_type == "grad_reveal" and (json.loads(row.content)["match"], json.loads(row.content)["round"])
                                     == (current["match"], current["round"]) for row in match.events[:index + 1]))
        for name in PLAYERS:
            own = observations(name, match.events)
            own_via_match = observations(name, match.observations(name))
            self.assertEqual(own, own_via_match)
            for event in own:
                if event.msg_type in {"grad_layout", "grad_selection", "action", "decision_note", "invalid_action"}:
                    self.assertIn(name, event.visible_to)
            self.assertTrue(all(event.visible_to == [name] for event in own if event.msg_type == "grad_layout"))

    def test_follower_model_sees_only_offer_color_before_numbers_reveal(self):
        match = Match(["A", "B"], 2, models={"A": object(), "B": object()}, live_turns=100)
        requests = []
        def query(name, prompt, *args, **kwargs):
            images = kwargs.get("images", args[1] if len(args) > 1 else ())
            self.assertTrue(images[0].startswith(b"\x89PNG"))
            own = observations(name, match.observations(name))
            self.assertFalse(any(e.msg_type == "grad_layout" and e.agent_name != name for e in own))
            if "동시에 비공개 제출" in prompt:
                return encode({"numbers": HIGH if name == "A" else LOW}), StrategyNote(text=f"private-{name}")
            current = rows(match, "grad_round")[-1]
            offered = [row for row in rows(match, "grad_offer") if row["match"] == current["match"] and row["round"] == current["round"]]
            requests.append((name, prompt, offered))
            if offered:
                self.assertEqual(len(offered), 1)
                self.assertNotIn("value", offered[0])
                self.assertNotIn("slot", offered[0])
                self.assertIn(offered[0]["color"], prompt)
                self.assertIn("아직 어느 제출 숫자도 공개되지", prompt)
            options = prompt.split("다음 중 하나를 그대로 출력하세요.\n")[-1].splitlines()
            return options[0], StrategyNote(text=f"private-{name}")
        with patch.object(match, "_query", side_effect=query):
            result = play(match)
        self.assertEqual(result["survivors"], ["A"])
        self.assertEqual(len(requests), 14)
        self.assertEqual(sum(bool(offered) for _, _, offered in requests), 7)
        for name in match.players:
            own = observations(name, match.observations(name))
            self.assertTrue(any(e.msg_type == "decision_note" for e in own))
            self.assertFalse(any(e.msg_type == "decision_note" and e.agent_name != name for e in own))


class TournamentTests(unittest.TestCase):
    def test_two_consecutive_wins_are_required_not_two_cumulative_wins(self):
        match, result = controlled(["A", "C", "B", "A", "C", "C"])
        games = rows(match, "grad_match_result")
        self.assertEqual([row["streak"] for row in games], [1, 1, 1, 1, 1, 2])
        self.assertEqual(result["matches"], 6)
        self.assertEqual(result["finalists"], ["C"])
        self.assertCountEqual(result["eliminated"], ["A", "B"])
        starts = rows(match, "grad_match")
        for previous, current in zip(games, starts[1:]):
            self.assertEqual(current["leader"], previous["winner"])
            self.assertIn(previous["winner"], current["players"])
            self.assertIn(previous["waiting"], current["players"])

    def test_total_tie_replays_without_incrementing_streak_or_rotating_waiting(self):
        match, result = controlled(["A", None, "C", "C"])
        games, starts = rows(match, "grad_match_result"), rows(match, "grad_match")
        self.assertEqual([row["streak"] for row in games], [1, 1, 1, 2])
        self.assertTrue(games[1]["tied"])
        self.assertEqual(starts[1]["players"], starts[2]["players"])
        self.assertEqual(starts[1]["waiting"], starts[2]["waiting"])
        self.assertEqual(starts[1]["leader"], starts[2]["leader"])
        self.assertEqual(starts[2]["replay"], 1)
        self.assertEqual(len(rows(match, "grad_layout")), result["matches"] * 2)
        self.assertEqual(result["survivors"], ["C"])

    def test_two_player_route_is_one_decisive_duel_with_tie_replay(self):
        match, result = controlled([None, "B"], ["A", "B"])
        self.assertTrue(rows(match, "grad_setup")[0]["duel"])
        self.assertEqual(result["matches"], 2)
        self.assertEqual(rows(match, "grad_match_result")[-1]["streak"], 1)
        self.assertEqual(result["survivors"], ["B"])
        self.assertEqual(result["eliminated"], ["A"])
        self.assertEqual(result["pieces"], {"A": 1, "B": 1})

    def test_full_scripted_games_finish_and_are_seed_deterministic(self):
        for players in (PLAYERS, PLAYERS[:2]):
            first, second = Match(players, 31, pieces=list(range(len(players)))), Match(players, 31, pieces=list(range(len(players))))
            result = play(first)
            self.assertEqual(play(second), result)
            self.assertEqual([event.content for event in first.events], [event.content for event in second.events])
            self.assertEqual(len(result["survivors"]), 1)
            self.assertEqual(len(result["eliminated"]), len(players) - 1)
            self.assertEqual(len(rows(first, "grad_reveal")), result["matches"] * 7)
            self.assertLess(result["matches"], 50)
            self.assertEqual(result["pieces"], dict(zip(players, range(len(players)))))
            self.assertFalse(first.relationship_reviews_enabled)
        for invalid in (["A"], ["A", "A"], ["A", "B", "C", "D"]):
            with self.assertRaises(ValueError):
                play(Match(invalid, 1))

    def test_invalid_and_late_layouts_use_valid_precomputed_fallback_without_penalty(self):
        match = Match(["A", "B"], 22)
        prepare = match.decide_together
        def late(phase, decisions, **kwargs):
            defaults = {name: replace(decision, default=encode({"numbers": HIGH})) for name, decision in decisions.items()}
            answers = prepare(phase, defaults, **kwargs)
            kwargs["response_times"].update({"A": 300_000_000_001, "B": 300_000_000_000})
            return answers
        match.decide_together = late
        with patch(f"{play.__module__}.random_layout", return_value=LOW.copy()):
            result = play(match)
        initial = rows(match, "grad_layout")[:2]
        layouts = {row["player"]: row["numbers"] for row in initial}
        self.assertEqual(layouts, {"A": LOW, "B": HIGH})
        self.assertEqual(result["survivors"], ["B"])
        self.assertTrue(all(sum(row["scores"].values()) <= 7 for row in rows(match, "grad_match_result")))
        invalid = Match(["A", "B"], 20, models={"A": object(), "B": object()}, live_turns=2)
        with patch.object(invalid, "_query", return_value=("bad", StrategyNote(text="private"))):
            result = play(invalid)
        self.assertEqual(invalid.live_turns, 0)
        self.assertEqual(len(rows(invalid, "invalid_action")), 2)
        self.assertTrue(all(accepts_layout(encode({"numbers": row["numbers"]})) for row in rows(invalid, "grad_layout")))
        self.assertEqual(len(result["survivors"]), 1)

    def test_direct_cli_accepts_default_three_and_explicit_two_seats(self):
        with (TemporaryDirectory() as directory, redirect_stdout(StringIO()), redirect_stderr(StringIO()),
              patch.object(runtime, "DAY_SIX_PRISON", TITLE, create=True),
              patch.object(runtime, "DAY_SIX_MAIN", "6일차 메인 매치 · HIT, STAY", create=True)):
            for players in ([], ["A", "B"]):
                output = Path(directory) / f"seats-{len(players)}.jsonl"
                main(["--seed", "31", "--output", str(output), *( ["--players", *players] if players else [])])
                records = [json.loads(line) for line in output.read_text().splitlines()]
                self.assertEqual(len(records[0]["players"]), len(players) or 3)
                self.assertEqual(len(records[-1]["survivors"]), 1)

    def test_resume_mid_round_reuses_committed_private_choices_and_model_responses(self):
        event = Match.event
        def query(name, prompt, *args, **kwargs):
            if "동시에 비공개 제출" in prompt:
                return encode({"numbers": HIGH if name == "A" else LOW}), StrategyNote(text="private")
            options = prompt.split("다음 중 하나를 그대로 출력하세요.\n")[-1].splitlines()
            return options[0], StrategyNote(text="private")
        with (TemporaryDirectory() as directory, redirect_stdout(StringIO()), redirect_stderr(StringIO()),
              patch.object(Match, "_query", side_effect=query),
              patch("games.match.monotonic_ns", return_value=70_000_000_000)):
            root = Path(directory)
            complete, interrupted = root / "complete.jsonl", root / "interrupted.jsonl"
            arguments = ["--players", "A", "B", "--seed", "17", "--model", "test", "--model-turns", "16"]
            run_cli(play, title=TITLE, seats=(3, 2), argv=[*arguments, "--output", str(complete)])
            def stop(match, kind, value, **kwargs):
                event(match, kind, value, **kwargs)
                if kind == "grad_offer":
                    raise RuntimeError("committed first offer")
            with patch.object(Match, "event", stop), self.assertRaisesRegex(RuntimeError, "committed first offer"):
                run_cli(play, title=TITLE, seats=(3, 2), argv=[*arguments, "--output", str(interrupted)])
            calls = []
            def resume_query(name, prompt, *args, **kwargs):
                calls.append((name, prompt))
                return query(name, prompt, *args, **kwargs)
            with patch.object(Match, "_query", side_effect=resume_query):
                run_cli(play, title=TITLE, seats=(3, 2), argv=["--resume", "--output", str(interrupted)])
            self.assertEqual(len(calls), 13)
            self.assertEqual([json.loads(line) for line in complete.read_text().splitlines()],
                             [json.loads(line) for line in interrupted.read_text().splitlines()])


if __name__ == "__main__":
    unittest.main()
