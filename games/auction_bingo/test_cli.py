from contextlib import nullcontext, redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from ..match import DAY_FOUR_MAIN, DAY_THREE_MAIN, DAY_THREE_PRISON, run_cli


def fake_model(provider, model, *, effort, **kwargs):
    return nullcontext(Mock(calls=0, config=(provider, model, effort)))


class AuctionBingoCliTest(unittest.TestCase):
    def run_match(self, play, args):
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            run_cli(play, title=DAY_FOUR_MAIN, seats=7, previous_main=DAY_THREE_MAIN,
                    after_prison=True, guest="G01", argv=args)

    def test_continuation_keeps_survivors_pieces_and_relationships_and_adds_guest(self):
        players = [f"P{index:02}" for index in range(1, 10)]
        balances = {name: index for index, name in enumerate(players, 1)}
        prisoners = players[4:8]
        rating = {"P02": {"affinity": 62, "trust": 58, "reason": "협력 확인"}}
        with TemporaryDirectory() as directory:
            root = Path(directory)
            main = root / "main.jsonl"
            prison = root / "prison.jsonl"
            output = root / "bingo.jsonl"
            main.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in [
                {"type": "match", "game": DAY_THREE_MAIN, "players": players},
                {"type": "event", "msg_type": "relationship_update", "agent_name": "P01",
                 "visible_to": ["P01"], "content": json.dumps({"ratings": rating})},
                {"type": "result", "ranking": players, "prison": prisoners,
                 "eliminated": ["P09"], "pieces": balances},
            ]) + "\n", encoding="utf-8")
            prison.write_text("\n".join(json.dumps(row) for row in [
                {"type": "match", "game": DAY_THREE_PRISON, "players": prisoners,
                 "pieces": {name: balances[name] for name in prisoners}},
                {"type": "result", "eliminated": ["P08"],
                 "pieces": {name: balances[name] + 1 for name in prisoners}},
            ]) + "\n", encoding="utf-8")

            def play(match):
                self.assertEqual(match.players, (*players[:7], "G01"))
                self.assertEqual(match.pieces, {
                    **{name: balances[name] + int(name in prisoners) for name in players[:7]}, "G01": 1,
                })
                self.assertEqual(match.relationships["P01"], rating)
                self.assertEqual(match.relationships["G01"], {})
                return {"ranking": players[:7], "pieces": match.pieces}

            self.run_match(play, ["--from-main", str(main), "--from-prison", str(prison),
                                  "--output", str(output)])
            header = json.loads(output.read_text().splitlines()[0])
            self.assertEqual(header["players"], [*players[:7], "G01"])
            self.assertEqual(header["pieces"]["G01"], 1)
            self.assertEqual(header["from_prison"], str(prison))

    def test_guest_can_use_its_own_provider_and_model(self):
        with TemporaryDirectory() as directory, patch("games.match.open_model") as opened:
            models = []

            def open_fake(*args, **kwargs):
                context = Mock()
                model = Mock(calls=0)
                context.__enter__ = Mock(return_value=model)
                context.__exit__ = Mock(return_value=False)
                models.append(model)
                return context

            opened.side_effect = open_fake
            output = Path(directory) / "events.jsonl"

            def play(match):
                self.assertEqual(set(match.models), set(match.players))
                self.assertIs(match.models["G01"], models[1])
                self.assertIs(match.models["P01"], models[0])
                return {"ranking": list(match.players[:-1])}

            self.run_match(play, ["--model", "main-model", "--player-model",
                                  "G01:anthropic:guest-model:low", "--output", str(output)])
            header = json.loads(output.read_text().splitlines()[0])
            self.assertEqual(header["model_players"][-1], "G01")
            self.assertEqual(header["model_overrides"]["G01"], {
                "provider": "anthropic", "model": "guest-model", "effort": "low",
            })

    def test_guest_defaults_to_codex_sol_low_with_openai_main_players(self):
        with TemporaryDirectory() as directory, patch("games.match.open_model", side_effect=fake_model) as opened:
            output = Path(directory) / "events.jsonl"

            def play(match):
                self.assertEqual(match.models["G01"].config, ("codex", "gpt-6.1-sol", "low"))
                self.assertTrue(all(match.models[name].config == ("openai", "main-luna", "high")
                                    for name in match.players if name != "G01"))
                return {"ranking": list(match.players[:-1])}

            self.run_match(play, ["--provider", "openai", "--model", "main-luna", "--effort", "high",
                                  "--output", str(output)])
            self.assertEqual(opened.call_count, 2)
            header = json.loads(output.read_text().splitlines()[0])
            self.assertEqual(header["model_overrides"]["G01"], {
                "provider": "codex", "model": "gpt-6.1-sol", "effort": "low",
            })

    def test_scripted_or_unselected_guest_does_not_open_a_guest_model(self):
        for args, live_players in (([], set()),
                                   (["--provider", "openai", "--model", "main-luna", "--model-player", "P01"], {"P01"})):
            with self.subTest(live_players=live_players), TemporaryDirectory() as directory, patch(
                "games.match.open_model", side_effect=fake_model,
            ) as opened:
                output = Path(directory) / "events.jsonl"

                def play(match):
                    self.assertEqual(set(match.models), live_players)
                    return {"ranking": list(match.players[:-1])}

                self.run_match(play, [*args, "--output", str(output)])
                self.assertEqual(opened.call_count, len(live_players))
                header = json.loads(output.read_text().splitlines()[0])
                self.assertNotIn("G01", header.get("model_overrides", {}))

    def test_resume_keeps_guest_default_and_accepts_repeated_regular_override(self):
        attempts = []

        def play(match):
            attempts.append(tuple(match.models[name].config for name in ("P01", "P02", "G01")))
            match.event("bingo_setup", {"guest": "G01"})
            if len(attempts) == 1:
                raise KeyboardInterrupt
            return {"ranking": list(match.players[:-1])}

        with TemporaryDirectory() as directory, patch("games.match.open_model", side_effect=fake_model):
            output = Path(directory) / "events.jsonl"
            override = "P01:openai:player-terra:medium"
            with self.assertRaises(KeyboardInterrupt):
                self.run_match(play, ["--provider", "openai", "--model", "main-luna", "--effort", "high",
                                      "--player-model", override, "--output", str(output)])
            header = output.read_text().splitlines()[0]
            self.run_match(play, ["--resume", "--output", str(output), "--player-model", override])
            self.assertEqual(output.read_text().splitlines()[0], header)
            self.assertEqual(attempts, [(('openai', 'player-terra', 'medium'), ('openai', 'main-luna', 'high'),
                                         ('codex', 'gpt-6.1-sol', 'low'))] * 2)

    def test_older_saved_guest_keeps_the_main_luna_model(self):
        attempts = []

        def play(match):
            attempts.append(match.models["G01"].config)
            self.assertIs(match.models["G01"], match.models["P01"])
            match.event("bingo_setup", {"guest": "G01"})
            if len(attempts) == 1:
                raise KeyboardInterrupt
            return {"ranking": list(match.players[:-1])}

        with TemporaryDirectory() as directory, patch("games.match.open_model", side_effect=fake_model):
            output = Path(directory) / "events.jsonl"
            with self.assertRaises(KeyboardInterrupt):
                self.run_match(play, ["--model", "gpt-6-luna", "--effort", "medium", "--player-model",
                                      "G01:codex:gpt-6-luna:medium", "--output", str(output)])
            rows = [json.loads(line) for line in output.read_text().splitlines()]
            rows[0].pop("model_overrides")  # Before guest defaults, G01 inherited the match model.
            output.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n")
            prefix = output.read_text().splitlines()[:-1]
            self.run_match(play, ["--resume", "--output", str(output)])
            self.assertEqual(attempts, [("codex", "gpt-6-luna", "medium")] * 2)
            self.assertEqual(output.read_text().splitlines()[:len(prefix)], prefix)
            self.assertNotIn("model_overrides", json.loads(output.read_text().splitlines()[0]))

    def test_resume_restores_regular_roster_and_only_one_guest(self):
        attempts = []

        def play(match):
            attempts.append((match.players, match.pieces.copy()))
            match.event("bingo_setup", {"guest": "G01"})
            if len(attempts) == 1:
                raise KeyboardInterrupt()
            return {"ranking": list(match.players[:-1])}

        with TemporaryDirectory() as directory:
            output = Path(directory) / "events.jsonl"
            roster = [f"P{index:02}" for index in range(10, 17)]
            with self.assertRaises(KeyboardInterrupt):
                self.run_match(play, ["--players", *roster, "--pieces", *["2"] * 7,
                                      "--output", str(output)])
            self.run_match(play, ["--resume", "--output", str(output)])
            self.assertEqual(attempts, [(tuple([*roster, "G01"]), {**dict.fromkeys(roster, 2), "G01": 1})] * 2)

    def test_regular_roster_cannot_reuse_guest_id(self):
        with self.assertRaises(SystemExit):
            self.run_match(lambda match: {}, ["--players", "G01", "P02", "P03", "P04", "P05", "P06", "P07"])
