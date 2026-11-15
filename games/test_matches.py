from base64 import b64decode
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
from random import Random
import re
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
from threading import Barrier, Event, local
from time import monotonic_ns
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from concordia.language_model.language_model import LanguageModel
from web.spectator import find_matches, read_match

from .either_or.cube_counting import cube_height, cube_priority
from .either_or.game import LimitedGrassBackend, play as either_or
from .either_or.lay_the_grass.demo import make_grass_arena
from .either_or.lay_the_grass.environment import LayTheGrass
from .either_or.memory_poker import hand_rank, memory_stage, poker_duel
from .either_or.negotiation import negotiate
from .either_or.rectangle_counting import count_rectangles, rectangle_race, rectangle_stage
from .heavy_13.game import place, play as heavy_13
from .match import DAY_ONE_MAIN, DAY_ONE_PRISON, DAY_TWO_MAIN, Decision, Match, run_cli
from .models import CodexLanguageModel, OpenAILanguageModel, StrategyNote, _openai_key
from .mystery_stock_market.game import next_prices, play as market, trade_orders
from .personas import persona_context
from .russian_roulette.game import play as roulette


class MatchTest(unittest.TestCase):
    def test_simultaneous_model_requests_use_only_their_own_persona(self):
        names = tuple(f"P{seat:02}" for seat in range(16, 0, -1)) + ("Guest",)
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(status="completed", output_text='{"action":"대기"}', usage=None)
        model = OpenAILanguageModel("test-model", client)
        match = Match(names, 1, model=model, live_players=names, live_turns=len(names))
        personas = {name: persona_context(name) for name in names if name != "Guest"}
        self.assertTrue(all(personas.values()))
        self.assertEqual(len(set(personas.values())), 16)
        self.assertEqual(match.decide_together("test", {
            name: Decision(f"{name} 이번 선택", "대기", options=("대기",)) for name in names
        }), dict.fromkeys(names, "대기"))

        requests = [call.kwargs["input"][0]["content"][0]["text"] for call in client.responses.create.call_args_list]
        for name in names:
            prompt, = [request for request in requests if f"{name} 이번 선택" in request]
            self.assertEqual([owner for owner, persona in personas.items() if persona in prompt],
                             [name] if name in personas else [])

    def test_simultaneous_submissions_wait_for_all_private_decisions(self):
        names = ("P01", "P02", "P03")
        client = Mock()
        model = OpenAILanguageModel("test-model", client)
        match = Match(names, 1, model=model, live_players=names, live_turns=2)
        match.event("scoreboard", dict.fromkeys(names, 0))
        match.event("preview", "P01만 보는 정보", private=["P01"])
        start = len(match.events)
        together = Barrier(2, timeout=5)

        def complete(**kwargs):
            self.assertEqual(kwargs["text"]["format"]["schema"]["required"], ["note", "action"])
            name = kwargs["input"][0]["content"][0]["text"].splitlines()[-1]
            response = {"action": "공공" if name == "P01" else "잘못된 선택", "note": f"{name}의 선택 기준"}
            return SimpleNamespace(status="completed", output_text=json.dumps(response), usage=None)

        client.responses.create.side_effect = complete

        def query(name, role, history):
            self.assertEqual(len(match.events), start)
            self.assertEqual(history[-1].turn, start)
            self.assertEqual(any(event.msg_type == "preview" for event in history), name == "P01")
            together.wait()
            return model.sample_text(name)

        with (patch.object(match.backends["P01"], "query", side_effect=query),
              patch.object(match.backends["P02"], "query", side_effect=query),
              patch.object(match.backends["P03"], "query") as unused):
            answers = match.decide_together("choice_4", {
                name: Decision("투표하세요.", "개인", options=("공공", "개인")) for name in names
            })
        unused.assert_not_called()
        self.assertEqual(answers, {"P01": "공공", "P02": "개인", "P03": "개인"})
        self.assertEqual([event.visible_to for event in match.events[start:]],
                         [["P01"], ["P01"], ["P02"], ["P02"], ["P03"]])
        notes = [event for event in match.events[start:] if event.msg_type == "decision_note"]
        self.assertEqual([json.loads(note.content) for note in notes],
                         [{"phase": "choice_4", "note": "P01의 선택 기준"}])
        self.assertNotIn(notes[0], match.observations("P02"))
        self.assertEqual(model.calls, 2)

    def test_simultaneous_review_reserves_only_one_extra_call_and_keeps_draft_private(self):
        names = ("P01", "P02")
        client = Mock()
        model = OpenAILanguageModel("test-model", client)
        match = Match(names, 1, model=model, live_players=names, live_turns=3)
        together = Barrier(2, timeout=5)

        def complete(**kwargs):
            request = kwargs["input"][0]["content"][0]["text"]
            schema = kwargs["text"]["format"]["schema"]["required"]
            name = request.splitlines()[-1]
            if "임시 답안 개인" in request:
                self.assertEqual(name, "P01")
                self.assertEqual(schema, ["note", "action"])
                self.assertIn("개인 선택의 비용 확인", request)
                response = {"action": "공공", "note": "표를 모을 가능성이 높다."}
            else:
                self.assertEqual(schema, ["review", "note", "action"])
                response = {"review": name == "P01", "action": "개인", "note": "개인 선택의 비용 확인"}
            return SimpleNamespace(status="completed", output_text=json.dumps(response), usage=None)

        client.responses.create.side_effect = complete

        def query(name, role, history):
            self.assertFalse(any(event.msg_type == "action" for event in match.events))
            if not history[:-1]:
                together.wait()
            else:
                self.assertEqual([event.visible_to for event in history[:-1]], [["P01"]])
            return model.sample_text(history[-1].content + "\n" + name)

        with (patch.object(match.backends["P01"], "query", side_effect=query),
              patch.object(match.backends["P02"], "query", side_effect=query)):
            answers = match.decide_together("choice_4", {
                name: Decision("투표하세요.", "개인", options=("공공", "개인")) for name in names
            })
        self.assertEqual(answers, {"P01": "공공", "P02": "개인"})
        self.assertEqual(model.calls, 3)
        review = match.events[0]
        self.assertIn("임시 답안 개인", review.content)
        self.assertNotIn(review, match.observations("P02"))

    def test_openai_cli_sends_structured_text_and_multi_image_actions(self):
        with (TemporaryDirectory() as directory, patch.dict("os.environ", {}, clear=True),
              patch("games.models.OpenAI") as openai, patch("games.models._openai_key") as key,
              redirect_stdout(StringIO()), redirect_stderr(StringIO())):
            path = Path(directory)
            env = path / ".env"
            env.write_text("openai_api_key='fixture-key' # local config\n", encoding="utf-8")
            key.side_effect = lambda _: _openai_key(env)
            client = openai.return_value.__enter__.return_value
            client.responses.create.side_effect = [
                SimpleNamespace(status="completed", output_text='{"action":"360","note":"네 그림을 비교했다."}', usage=None),
                SimpleNamespace(status="completed", output_text='{"action":"개인","note":"혼자 진행한다."}', usage=None),
            ]
            images = (b"view-1", b"view-2", b"view-3", b"view-4")

            def play(match):
                self.assertFalse(read_match(output)["complete"])
                self.assertEqual(match.decide("P16", "cubes", "그림을 보세요.", "0", images=images,
                                              valid=lambda action: action in ("0", "360")), "360")
                live = read_match(output)
                self.assertEqual(live["model_calls"], 1)
                self.assertEqual(live["steps"][-1]["events"][0]["visible_to"], ["P16"])
                self.assertEqual(match.decide("P01", "choice_2", "참가 방식을 고르세요.", "개인", options=("개인",)), "개인")
                return {}

            output = path / "events.jsonl"
            run_cli(play, title="테스트 경기", seats=16,
                    argv=["--provider", "openai", "--effort", "medium", "--image-model", "gpt-6.1-terra",
                          "--output", str(output)])
            rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(rows[0]["provider"], "openai")
            self.assertEqual(rows[0]["image_model"], "gpt-6.1-terra")
            self.assertTrue(rows[0]["allow_review"])
            self.assertEqual(rows[0]["model_players"], rows[0]["players"])
            self.assertEqual(rows[-1]["model_calls"], 2)
            self.assertTrue(read_match(output)["complete"])
            notes = [row for row in rows if row.get("msg_type") == "decision_note"]
            self.assertEqual([row["visible_to"] for row in notes], [["P16"], ["P01"]])
            self.assertNotIn("fixture-key", output.read_text(encoding="utf-8"))
            self.assertEqual(openai.call_args.kwargs["api_key"], "fixture-key")
            image_turn, text_turn = [call.kwargs for call in client.responses.create.call_args_list]
            self.assertEqual(image_turn["model"], "gpt-6.1-terra")
            self.assertEqual(image_turn["reasoning"], {"effort": "medium"})
            self.assertFalse(image_turn["store"])
            self.assertTrue(image_turn["text"]["format"]["strict"])
            text, *attachments = image_turn["input"][0]["content"]
            self.assertEqual(text["type"], "input_text")
            self.assertIn(persona_context("P16"), text["text"])
            self.assertNotIn(persona_context("P01"), text["text"])
            self.assertEqual([image["type"] for image in attachments], ["input_image"] * 4)
            self.assertEqual(tuple(b64decode(image["image_url"].split(",", 1)[1]) for image in attachments), images)
            self.assertEqual(text_turn["model"], "gpt-6-luna")
            self.assertEqual([item["type"] for item in text_turn["input"][0]["content"]], ["input_text"])
            self.assertIn(persona_context("P01"), text_turn["input"][0]["content"][0]["text"])

    def test_either_or_preserves_live_grass_log_on_interrupt(self):
        with TemporaryDirectory() as directory, redirect_stderr(StringIO()):
            root = Path(directory)
            output = root / "matches/day1-main/events.jsonl"

            def make_interruptible_arena(*args, **kwargs):
                arena = make_grass_arena(*args, **kwargs)
                step = arena.environment.step
                calls = 0

                def interrupt_after_one_turn(*args, **kwargs):
                    nonlocal calls
                    if calls:
                        self.assertEqual(find_matches(root), {"matches/day1-main": output})
                        live = read_match(output)
                        self.assertFalse(live["complete"])
                        note = live["steps"][-1]["events"][0]
                        self.assertEqual(note["msg_type"], "discussion_note")
                        self.assertEqual(note["visible_to"], [note["agent_name"]])
                        raise KeyboardInterrupt
                    calls += 1
                    return step(*args, **kwargs)

                arena.environment.step = interrupt_after_one_turn
                return arena

            with patch("games.either_or.game.make_grass_arena", side_effect=make_interruptible_arena):
                with self.assertRaises(KeyboardInterrupt):
                    run_cli(either_or, title="1일차 메인 매치 · 양자택일", seats=16, argv=["--output", str(output)])
            replay = read_match(output)
            self.assertFalse(replay["complete"])
            self.assertTrue(replay["interrupted"])
            self.assertEqual(replay["steps"][-1]["events"][0]["msg_type"], "match_interrupted")

    def test_match_cli_defaults_to_all_model_players(self):
        cases = [(seats, [], 2000) for seats in (16, 7, 12, 6)]
        cases += [(16, ["--model-player", "P16"], 3), (16, ["--model-turns", "16", "--no-allow-review"], 16)]
        for seats, args, turns in cases:
            with self.subTest(seats=seats, args=args), redirect_stdout(StringIO()):
                play = Mock(return_value={})
                run_cli(play, title="테스트 경기", seats=seats, argv=["--model", "gpt-6-luna", *args])
                match, = play.call_args.args
                players = ["P16"] if "--model-player" in args else list(match.players)
                self.assertEqual(list(match.backends), players)
                self.assertEqual(match.live_turns, turns)
                self.assertEqual(match.allow_review, "--no-allow-review" not in args)

    def test_mixed_models_route_codex_calls_and_share_one_budget(self):
        luna = ("gpt-6-luna", "high")
        sol = ("gpt-6.1-sol", "low")
        terra = ("gpt-6.1-terra", "low")
        overrides = ("P06", "P09", "P16")
        calls = []
        pass_action = '{"type":"pass","note":"다음 차례를 기다린다."}'

        def complete(command, *, input, **kwargs):
            model = command[command.index("--model") + 1]
            effort = next(json.loads(arg.split("=", 1)[1]) for arg in command if arg.startswith("model_reasoning_effort="))
            if "비공개 관계 평가를 갱신하세요" in input:
                name = re.search(r"Exercise: (P\d+)의 비공개 관계 평가", input)[1]
                phase, response = f"관계 {name}", {"action": "{}"}
            elif "--image" in command:
                self.assertEqual(Path(command[command.index("--image") + 1]).read_bytes(), b"image")
                phase, response = re.search(r"Exercise: (큐브 P\d+)", input)[1], {"action": "12", "note": "그림을 확인했다."}
            elif "이번 선택 P06" in input:
                phase, response = ("검토 P06", {"action": "팀", "note": "팀으로 정했다."}) if "임시 답안 개인" in input else (
                    "선택 P06", {"action": "개인", "note": "다시 비교한다.", "review": True})
            elif "이번 선택 P01" in input:
                phase, response = "선택 P01", {"action": "개인", "note": "혼자 진행한다."}
            else:
                self.assertIn(persona_context("P06"), input)
                phase, response = "잔디 P06", {"action": pass_action}
            calls.append((phase, (model, effort)))
            event = {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(response)}}
            return CompletedProcess(command, 0, json.dumps(event), "")

        def play(match):
            decisions = {name: Decision(f"이번 선택 {name}", "개인", options=("개인", "팀")) for name in ("P01", "P06")}
            self.assertEqual(match.decide_together("choice_2", decisions), {"P01": "개인", "P06": "팀"})
            for name in ("P01", "P09", "P02"):
                self.assertEqual(match.decide(name, "cubes", f"큐브 {name}", "0", images=(b"image",),
                                              options=("0", "12")), "12")
            grass_order = ("P06", *(name for name in match.players if name != "P06"))
            game = LayTheGrass(dict.fromkeys(grass_order, 0), grass_order, discussion_rounds=1)
            game.reset()
            scripted = Mock()
            backend = LimitedGrassBackend("P06", game, match, scripted)
            self.assertEqual(backend.query("P06", "잔디 깔기 참가자", game.get_observation("P06")), pass_action)
            scripted.query.assert_not_called()
            match.event("placement", "관계 평가 근거", private=("P06", "P16"))
            match.review_relationships("협상 종료")
            self.assertEqual(match.live_turns, 0)
            self.assertEqual(match.decide("P01", "test", "선택하세요.", "대기", options=("대기",)), "대기")
            return {}

        with (TemporaryDirectory() as directory, redirect_stdout(StringIO()), redirect_stderr(StringIO()),
              patch("games.models.subprocess.run", side_effect=complete)):
            log = Path(directory) / "events.jsonl"
            args = ["--provider", "codex", "--model", luna[0], "--effort", luna[1], "--model-turns", "9",
                    "--image-model-for", f"{luna[0]}:{luna[1]}:{terra[0]}",
                    "--player-model", f"P02:{terra[0]}:{terra[1]}", "--output", str(log)]
            for name in overrides:
                args.extend(("--player-model", f"{name}:{sol[0]}:{sol[1]}"))
            run_cli(play, title=DAY_ONE_MAIN, seats=16, argv=args)
            header, *_, result = map(json.loads, log.read_text(encoding="utf-8").splitlines())
            self.assertEqual(header["model_players"], header["players"])
            self.assertEqual(header["model_overrides"], {
                "P02": {"model": terra[0], "effort": terra[1]},
                **{name: {"model": sol[0], "effort": sol[1]} for name in overrides},
            })
            self.assertEqual(header["image_model_overrides"], {name: terra[0] for name in header["players"]
                                                               if name not in (*overrides, "P02")})
            self.assertEqual(result["model_calls"], 9)
        self.assertCountEqual(calls, [("선택 P01", luna), ("선택 P06", sol), ("검토 P06", sol), ("큐브 P09", sol),
                                      ("큐브 P01", (terra[0], "high")), ("큐브 P02", terra),
                                      ("잔디 P06", sol), ("관계 P06", sol), ("관계 P16", sol)])

    def test_day_one_to_day_two(self):
        names = [f"P{i:02}" for i in range(1, 17)]
        day_one = Match(names, 1)
        main = either_or(day_one)
        self.assertEqual(sorted(main["ranking"]), names)
        self.assertEqual(len(main["living"]), 7)
        self.assertEqual(len(main["prison"]), 7)
        self.assertEqual(len(main["eliminated"]), 2)
        self.assertTrue(main["grass_placements"])
        self.assertTrue(any(event.msg_type == "poker_result" for event in day_one.events))
        announcements = [event for event in day_one.events if event.msg_type == "rules"]
        self.assertEqual([event.content.splitlines()[0] for event in announcements], [
            "양자택일 · 게임 규칙", "선택 1 · 성과금 / 보험금", "미니게임 1 · 큐브 세기",
            "선택 2 · 팀 / 개인", "미니게임 2 · 네모 세기", "네모 세기 · 팀 대표 선출",
            "선택 3 · 네모 세기 정산과 추가 대결",
            "선택 4 · 공공의 이익 / 개인의 이익", "선택 5 · 점수 / 정보", "선택 6 · 공격 또는 방어",
            "선택 7 · 상생 또는 견제", "선택 8 · 가로수 또는 맨홀", "선택 9 · 탈락 인원 1명 / 2명",
            "미니게임 4 · 기억 포커와 선택 10", "최종 배정 · 연맹의 징표와 피스 정산",
        ])
        self.assertTrue(all(event.visible_to == "all" for event in announcements))
        rectangle_result = next(event for event in day_one.events if event.msg_type == "rectangle_result")
        representatives = next(event for event in day_one.events if event.msg_type == "representatives")
        settlement_rules = next(event for event in announcements if event.content.startswith("선택 3 ·"))
        last_standing = max(event.turn for event in day_one.events if event.msg_type == "rectangle_standings")
        self.assertLess(last_standing, rectangle_result.turn)
        self.assertLess(rectangle_result.turn, representatives.turn)
        self.assertLess(representatives.turn, settlement_rules.turn)
        buzzes = [json.loads(event.content) for event in day_one.events[:rectangle_result.turn] if event.msg_type == "buzz"]
        correct = [buzz["player"] for buzz in buzzes if buzz["correct"]]
        priority = json.loads(next(event.content for event in day_one.events if event.msg_type == "priority"))["order"]
        for rep, team in json.loads(representatives.content).items():
            self.assertEqual(rep, max(team, key=lambda name: (correct.count(name), -priority.index(name))))
        for choice in (2, 4, 9):
            start, end = (next(event.turn for event in day_one.events if event.msg_type == kind
                               and json.loads(event.content)["choice"] == choice)
                          for kind in ("negotiation_start", "negotiation_end"))
            discussion = day_one.events[start + 1:end]
            rounds = [json.loads(event.content)["round"] for event in discussion if event.msg_type == "negotiation_round"]
            notes = [event for event in discussion if event.msg_type == "discussion_note"]
            self.assertEqual(rounds, list(range(1, 11)))
            self.assertEqual(len(notes), 10 * len(names))
            self.assertTrue(all(note.visible_to == [note.agent_name] for note in notes))
            for channel in ("room", "whisper"):
                speech = next(event for event in discussion if event.msg_type == channel)
                self.assertEqual(len(speech.visible_to), 2)
                self.assertIn(speech, day_one.observations(speech.visible_to[-1]))
                outsider = next(name for name in names if name not in speech.visible_to)
                self.assertNotIn(speech, day_one.observations(outsider))
            first_choice = next(event.turn for event in day_one.events if event.msg_type == "action"
                                and json.loads(event.content)["phase"] == f"choice_{choice}")
            self.assertLess(end, first_choice)
        preview = next(event for event in day_one.events if event.msg_type == "preview")
        owner, = preview.visible_to
        self.assertIn(preview, day_one.observations(owner))
        self.assertNotIn(preview, day_one.observations(next(name for name in names if name != owner)))
        draft_end = max(event.turn for event in day_one.events if event.msg_type == "grass_tile")
        self.assertLess(preview.turn, draft_end)
        for choice in (6, 7, 8):
            announcement = next(event for event in announcements if event.content.startswith(f"선택 {choice} ·"))
            reveal = next(event for event in day_one.events if event.msg_type == "grass_choices"
                          and json.loads(event.content)["choice"] == choice)
            self.assertLess(draft_end, announcement.turn)
            self.assertLess(announcement.turn, reveal.turn)
            draft_end = reveal.turn

        first_prison = Match(main["prison"], 1)
        prison = heavy_13(first_prison)
        self.assertEqual(sum(event.msg_type == "round" for event in first_prison.events), 14)
        self.assertEqual(sum(event.msg_type == "placement" for event in first_prison.events), 14 * 7)
        self.assertEqual(len(prison["eliminated"]), 2)
        self.assertLessEqual(sum(prison["pieces_awarded"].values()), 4)
        survivors = [name for name in main["ranking"] if name not in main["eliminated"] + prison["eliminated"]]
        balances = [main["pieces"][name] + prison["pieces_awarded"].get(name, 0) for name in survivors]

        day_two = Match(survivors, 1, pieces=balances)
        second_main = market(day_two)
        self.assertEqual(len(second_main["prison"]), 6)
        self.assertEqual(len(second_main["eliminated"]), 1)
        market_rounds = [json.loads(event.content) for event in day_two.events if event.msg_type == "market"]
        self.assertEqual([row["round"] for row in market_rounds], list(range(1, 25)))
        self.assertTrue(any(row["assets"] is None and None in row["stocks"].values() for row in market_rounds))
        hints = [event for event in day_two.events if event.msg_type == "hints"]
        hint_stages = [json.loads(event.content) for event in hints]
        for stock, full in hint_stages[-1].items():
            self.assertTrue({"□", "▧"}.isdisjoint(full))
            for earlier, later in zip(hint_stages, hint_stages[1:]):
                self.assertIn("▧", earlier[stock])
                for before, after in zip(earlier[stock], later[stock], strict=True):
                    if before == "▧":
                        self.assertNotIn(after, "□▧")
                    elif before == "□":
                        self.assertIn(after, "□▧")
                    else:
                        self.assertEqual(before, after)
        for event, reveal_round in zip(hints, (1, 5, 10, 15, 20), strict=True):
            following_market = day_two.events[event.turn + 1]
            self.assertEqual(following_market.msg_type, "market")
            self.assertEqual(json.loads(following_market.content)["round"], reveal_round)
        preview = next(event for event in day_two.events if event.msg_type == "preview")
        owner, = preview.visible_to
        stock, sentence = preview.content.split(" · ", 1)
        self.assertEqual(sentence, hint_stages[1][stock])
        self.assertIn(preview, day_two.observations(owner))
        self.assertNotIn(preview, day_two.observations(next(name for name in survivors if name != owner)))

        second_prison = Match(second_main["prison"], 1)
        prison_result = roulette(second_prison)
        self.assertEqual(len(prison_result["eliminated"]), 2)
        self.assertEqual(sum(value == 0 for value in prison_result["credits"].values()), 3)
        self.assertEqual(sum(prison_result["pieces_awarded"].values()), 4)
        self.assertTrue(any(event.msg_type == "swap" for event in second_prison.events))
        hidden = next(event for event in second_prison.events if event.msg_type == "inspection"
                      and event.visible_to != "all")
        other = next(name for name in second_prison.players if name not in hidden.visible_to)
        self.assertNotIn(hidden, second_prison.observations(other))
        notice = second_prison.events[hidden.turn - 1]
        self.assertEqual(notice.msg_type, "private_action")
        self.assertIn(notice, second_prison.observations(other))
        self.assertEqual(notice.content, "비공개 행동을 했습니다.")

    def test_cli_carries_players_and_pieces_through_both_elimination_branches(self):
        for eliminations in (2, 1):
            with (
                self.subTest(eliminations=eliminations),
                TemporaryDirectory() as directory,
                redirect_stdout(StringIO()),
                redirect_stderr(StringIO()),
            ):
                main_log, prison_log, market_log, roulette_log = [
                    Path(directory) / game / "events.jsonl"
                    for game in ("day1-main", "day1-prison", "day2-main", "day2-prison")
                ]

                def play_stage(game, title, seats, output, *args, **kwargs):
                    run_cli(game, title=title, seats=seats, argv=["--output", str(output), *args], **kwargs)
                    lines = output.read_bytes().splitlines()
                    return json.loads(lines[0]), json.loads(lines[-1])

                main_args = ["--pieces", *(["8"] * 16)] if eliminations == 1 else []
                _, main = play_stage(either_or, DAY_ONE_MAIN, 16, main_log, *main_args)
                self.assertEqual(len(main["eliminated"]), eliminations)
                self.assertEqual(len(main["living"]), 9 - eliminations)
                self.assertEqual(len(main["prison"]), 7)
                prison_start, prison = play_stage(
                    heavy_13, DAY_ONE_PRISON, 7, prison_log, "--from-main", str(main_log), previous_main=DAY_ONE_MAIN,
                )
                self.assertEqual(prison_start["players"], main["prison"])
                self.assertEqual(prison_start["pieces"], {name: main["pieces"][name] for name in main["prison"]})
                market_start, second_main = play_stage(
                    market, DAY_TWO_MAIN, (12, 13), market_log, "--from-main", str(main_log),
                    "--from-prison", str(prison_log), previous_main=DAY_ONE_MAIN, after_prison=True,
                )
                eliminated = set(main["eliminated"] + prison["eliminated"])
                survivors = [name for name in main["ranking"] if name not in eliminated]
                self.assertEqual(len(survivors), 14 - eliminations)
                self.assertEqual(market_start["players"], survivors)
                self.assertEqual(market_start["pieces"], {
                    name: main["pieces"][name] + prison["pieces_awarded"].get(name, 0) for name in survivors
                })
                self.assertEqual(len(second_main["prison"]), 6)
                self.assertEqual(len(second_main["living"]), len(survivors) - 7)
                roulette_start, _ = play_stage(
                    roulette, "2일차 감옥 매치 · 러시안 룰렛", 6, roulette_log,
                    "--from-main", str(market_log), previous_main=DAY_TWO_MAIN,
                )
                self.assertEqual(roulette_start["players"], second_main["prison"])
                self.assertEqual(roulette_start["pieces"], {
                    name: second_main["pieces"][name] for name in second_main["prison"]
                })

    def test_private_relationship_updates_follow_players_across_matches(self):
        players = [f"P{seat:02}" for seat in range(1, 10)]
        prison_players = players[1:-1]
        pieces = dict.fromkeys(players, 1)
        calls = []

        def complete(prompt):
            calls.append(prompt)
            if "비공개 관계 평가를 갱신하세요" in prompt:
                if "Exercise: P02" in prompt and "방을 옮겨 약속을 지킴" in prompt:
                    ratings = {"P03": {"affinity": 62, "trust": 80, "reason": "방을 옮겨 약속을 지킴"}}
                elif "Exercise: P02" in prompt and "P02에게만 한 약속" in prompt:
                    ratings = {"P03": {"affinity": 56, "trust": 51, "reason": "P02에게만 한 약속"}}
                elif "Exercise: P01" in prompt:
                    ratings = {other: {"affinity": 70, "trust": 55, "reason": "공개 협력 제안"}
                               for other in ("P02", "P09")}
                else:
                    ratings = {}
                return json.dumps({"action": json.dumps(ratings, ensure_ascii=False)})
            return json.dumps({"action": "대기", "note": ""})

        def main(match):
            match.event("public", "공개 협력 제안", actor="P02")
            match.event("public", "저도 공개적으로 협력하겠습니다.", actor="P09")
            match.event("whisper", "P02에게만 한 약속", actor="P03", private=("P02", "P03"))
            match.review_relationships("협상 종료")
            match.decide("P02", "test", "내 차례", "대기", options=("대기",))
            return {"ranking": players, "prison": prison_players, "eliminated": ["P09"], "pieces": pieces}

        def prison(match):
            self.assertEqual(match.relationships["P02"]["P03"]["trust"], 51)
            match.event("whisper", "방을 옮겨 약속을 지킴", actor="P03", private=("P02", "P03"))
            return {"eliminated": ["P04"], "pieces": {name: pieces[name] for name in prison_players}}

        def market_start(match):
            self.assertEqual(match.players, ("P01", "P02", "P03", "P05", "P06", "P07", "P08"))
            self.assertEqual(match.relationships["P01"]["P02"]["trust"], 55)
            self.assertNotIn("P09", match.relationships["P01"])
            self.assertEqual(match.relationships["P02"]["P03"]["trust"], 80)
            self.assertEqual(match.relationships["P03"], {})
            match.decide("P02", "test", "내 차례", "대기", options=("대기",))
            return {"prison": ["P02", "P03"], "pieces": pieces}

        def day_two_prison(match):
            self.assertEqual(match.relationships["P02"]["P03"]["trust"], 80)
            match.decide("P02", "test", "내 차례", "대기", options=("대기",))
            return {"eliminated": []}

        with (TemporaryDirectory() as directory, redirect_stdout(StringIO()), redirect_stderr(StringIO()),
              patch("games.models.CodexLanguageModel._complete", side_effect=complete)):
            main_log, prison_log, market_log, second_prison_log = [
                Path(directory) / f"{stage}.jsonl" for stage in ("main", "prison", "market", "second-prison")
            ]
            model = ["--model", "test-model"]
            model += ["--player-model", "P02:other-model:high", "--player-model", "P09:other-model:high"]
            run_cli(main, title=DAY_ONE_MAIN, seats=9, argv=[*model, "--output", str(main_log)])
            run_cli(prison, title=DAY_ONE_PRISON, seats=7, previous_main=DAY_ONE_MAIN,
                    argv=[*model, "--from-main", str(main_log), "--output", str(prison_log)])
            run_cli(market_start, title=DAY_TWO_MAIN, seats=7, previous_main=DAY_ONE_MAIN, after_prison=True,
                    argv=[*model, "--from-main", str(main_log), "--from-prison", str(prison_log), "--output", str(market_log)])
            run_cli(day_two_prison, title="2일차 감옥 매치", seats=2, previous_main=DAY_TWO_MAIN,
                    argv=[*model, "--from-main", str(market_log), "--output", str(second_prison_log)])
            for path in (main_log, prison_log, market_log, second_prison_log):
                header, *rows = map(json.loads, path.read_text().splitlines())
                expected_overrides = {"P02", "P09"} if path == main_log else {"P02"}
                self.assertEqual(set(header["model_overrides"]), expected_overrides)
                for row in rows:
                    if row.get("msg_type") == "relationship_update":
                        self.assertEqual(row["visible_to"], [row["agent_name"]])
        p01_reviews = [prompt for prompt in calls if "Exercise: P01의 비공개 관계 평가" in prompt]
        self.assertEqual(len(p01_reviews), 1)
        self.assertNotIn("P02에게만 한 약속", p01_reviews[0])
        self.assertIn(persona_context("P01"), p01_reviews[0])
        self.assertNotIn(persona_context("P02"), p01_reviews[0])
        action_prompts = [prompt for prompt in calls if "Exercise: 내 차례" in prompt]
        self.assertEqual(len(action_prompts), 3)
        for prompt in action_prompts:
            self.assertIn(persona_context("P02"), prompt)
            self.assertNotIn(persona_context("P01"), prompt)
        self.assertIn("신뢰도 51/100", action_prompts[0])
        self.assertIn("신뢰도 80/100", action_prompts[1])
        self.assertNotIn("신뢰도 55/100", action_prompts[1])
        self.assertIn("신뢰도 80/100", action_prompts[2])

    def test_negotiation_whisper_reaches_recipient_and_notes_reach_next_choice(self):
        names = [f"P{i:02}" for i in range(1, 17)]
        model = Mock(spec=LanguageModel)
        model.sample_text.side_effect = [
            '{"type":"speak","channel":"whisper","to":"P02","text":"아홉 번째 표를 확인해줘","note":"표가 여덟이면 다시 제안한다"}',
            '{"type":"pass","note":"귓속말을 참고해 투표한다"}',
            '{"type":"pass","note":"공개 발언을 기다린다"}',
            '공공',
        ]
        match = Match(names, 1, model=model, live_players=names[:3], live_turns=3)
        negotiate(match, 4, "선택 4를 투표하기 전입니다.", names[:3], ("제안", "응답", "귓속말"))
        match.live_turns = 1
        action = match.decide(names[0], "choice_4", "투표하세요.", "개인", options=("공공", "개인"))
        first, recipient, outsider, vote = [call.kwargs["prompt"] for call in model.sample_text.call_args_list]
        self.assertIn("협상 1/10라운드", first)
        self.assertIn("1번 논의실", first)
        self.assertIn("아홉 번째 표를 확인해줘", recipient)
        self.assertNotIn("아홉 번째 표를 확인해줘", outsider)
        self.assertIn("표가 여덟이면 다시 제안한다", vote)
        self.assertEqual(action, "공공")

    def test_roulette_talk_is_independent_of_credit_turns_and_keeps_whispers_private(self):
        names = [f"P{i:02}" for i in range(1, 7)]
        seats = names.copy()
        Random(1).shuffle(seats)
        sender, neighbor, outsider, donor, manipulator, wrap_neighbor = seats
        public_text = "첫 조사 전에 아는 정보를 나눌까요?"
        next_text = "시계 방향 옆자리에게만 전하는 말"
        wrap_text = "마지막 옆자리에게만 전하는 말"
        reply_text = "옆자리의 제안에 답합니다."
        rejected_text = "건너편 자리로는 전달하면 안 되는 말"
        zero_text = "크레딧은 없지만 조사 결과를 나눌 수 있어요."
        reflection_text = "조사 결과를 공개하기 전에 옆자리의 계획부터 확인한다."
        credit_choices = dict(zip(seats, ("회전 2", "공개 조사 1", "비공개 조사 2", "조작 3", "조작 3", "공개 조사 3")))
        opening = "다음 크레딧 행동 전 전원에게 주어진 대화 기회입니다."
        follow_up = "방금 들은 발언에 답할 수 있는 기회입니다."

        def respond(prompt, **kwargs):
            if "비공개 관계 평가를 갱신하세요" in prompt:
                return "{}"
            name = re.search(r"role of (P\d+) are", prompt)[1]
            exercise = prompt.split("Exercise: ", 1)[1]
            first_round = '"round":2' not in prompt and '"round":1' in prompt
            if opening in exercise:
                if first_round and f"행동은 {sender}의 차례" in exercise and name == wrap_neighbor:
                    return json.dumps([{"channel": "public", "text": public_text}])
                if first_round and f"행동은 {neighbor}의 차례" in exercise:
                    if name == sender:
                        return json.dumps([
                            {"channel": "whisper", "to": neighbor, "text": next_text},
                            {"channel": "whisper", "to": wrap_neighbor, "text": wrap_text},
                        ])
                    if name == neighbor:
                        return json.dumps([{"channel": "whisper", "to": wrap_neighbor, "text": rejected_text}])
                if name == sender and "내 크레딧 0." in exercise and zero_text not in prompt:
                    return json.dumps([{"channel": "public", "text": zero_text}])
                return "[]"
            if follow_up in exercise:
                if first_round and name == neighbor and next_text in prompt:
                    return json.dumps([{"channel": "whisper", "to": sender, "text": reply_text}])
                return "[]"
            if "행동 후 비공개 복기입니다" in exercise:
                return reflection_text if name == outsider else "이번 결과를 반영해 다음 행동을 고른다."
            if "조작권을 얻었습니다" in exercise:
                return "6"
            if first_round:
                return credit_choices[name]
            return "회전 2" if "\n회전 2\n" in exercise else "공개 조사 1"

        model = Mock(spec=LanguageModel)
        model.sample_text.side_effect = respond
        match = Match(names, 1, model=model, live_players=names, live_turns=2000)
        roulette(match)

        prompts = [call.kwargs["prompt"] for call in model.sample_text.call_args_list]

        def speech_prompts(phase, acting):
            return {re.search(r"role of (P\d+) are", prompt)[1]: prompt for prompt in prompts
                    if phase in prompt and f"행동은 {acting}의 차례" in prompt and '"round":2' not in prompt
                    and '"round":1' in prompt}

        before_first = speech_prompts(opening, sender)
        public_replies = speech_prompts(follow_up, sender)
        self.assertEqual(set(before_first), set(names))
        self.assertEqual(set(public_replies), set(names))
        self.assertTrue(all(public_text not in prompt for prompt in before_first.values()))
        self.assertTrue(all(public_text in prompt for prompt in public_replies.values()))
        after_shift = speech_prompts(opening, neighbor)
        self.assertIn(f"내 양옆 자리 {wrap_neighbor}, {neighbor}", after_shift[sender])
        self.assertIn("개인전입니다.", after_shift[sender])
        self.assertIn(
            f"1번 {outsider} · 2번 {donor} · 3번 {manipulator} · 4번 {wrap_neighbor} · 5번 {sender} · 6번 {neighbor}",
            after_shift[sender],
        )
        self.assertTrue(all(next_text not in prompt for prompt in after_shift.values()))
        private_replies = speech_prompts(follow_up, neighbor)
        self.assertEqual(set(private_replies), {neighbor, wrap_neighbor})
        self.assertIn(next_text, private_replies[neighbor])
        self.assertNotIn(wrap_text, private_replies[neighbor])
        self.assertIn(wrap_text, private_replies[wrap_neighbor])
        self.assertNotIn(next_text, private_replies[wrap_neighbor])
        self.assertNotIn(rejected_text, private_replies[wrap_neighbor])

        whispers = [event for event in match.events if event.msg_type == "whisper"]
        self.assertEqual([(event.content, event.visible_to) for event in whispers],
                         [(next_text, [sender, neighbor]), (wrap_text, [sender, wrap_neighbor]),
                          (reply_text, [neighbor, sender])])
        credit_actions = [event for event in match.events if event.msg_type == "action"
                          and json.loads(event.content)["phase"] == "credit"]
        self.assertLess(whispers[-1].turn, credit_actions[1].turn)
        self.assertEqual(json.loads(credit_actions[1].content)["action"], "공개 조사 1")
        self.assertTrue(any(event.msg_type == "public" and event.content == zero_text
                            and event.agent_name == sender for event in match.events))
        hidden = next(event for event in match.events if event.msg_type == "inspection" and event.visible_to == [outsider])
        reflection = match.events[hidden.turn + 1]
        self.assertEqual(reflection.msg_type, "decision_note")
        self.assertEqual(reflection.visible_to, [outsider])
        self.assertEqual(json.loads(reflection.content), {"phase": "roulette_reflection", "note": reflection_text})
        self.assertEqual(sum(event.msg_type == "decision_note" and
                             json.loads(event.content)["phase"] == "roulette_reflection" for event in match.events),
                         len(credit_actions) - 1)
        reflection_prompt = next(prompt for prompt in prompts if "행동 후 비공개 복기입니다" in prompt
                                 and f"role of {outsider} are" in prompt and hidden.content in prompt)
        self.assertIn("방금 한 행동: 비공개 조사 2.", reflection_prompt)
        self.assertIn("내 남은 크레딧 14.", reflection_prompt)
        after_inspection = speech_prompts(opening, donor)
        self.assertIn(hidden.content, after_inspection[outsider])
        self.assertNotIn(hidden.content, after_inspection[neighbor])
        self.assertIn(reflection_text, after_inspection[outsider])
        self.assertNotIn(reflection_text, after_inspection[neighbor])
        self.assertFalse(speech_prompts(follow_up, donor))
        rejected = next(event for event in match.events if event.msg_type == "invalid_action")
        self.assertEqual(rejected.visible_to, [neighbor])
        exchanged = next(event for event in match.events if event.msg_type == "swap")
        self.assertEqual(json.loads(exchanged.content), {"player": manipulator, "slots": [6, 1]})
        self.assertEqual(exchanged.visible_to, [manipulator])
        self.assertNotIn(exchanged, match.observations(donor))
        self.assertTrue(any("결과: 6번과 1번 칸의 내용을 교환했습니다." in prompt for prompt in prompts))

    def test_choice_two_starts_rectangles_as_soon_as_everyone_submits(self):
        names = [f"P{i:02}" for i in range(1, 17)]
        model = Mock(spec=LanguageModel)
        submissions = ["P01 P02 P03", "P02 P03 P01", "P03 P02 P01", *["개인"] * 13]
        attempts = iter(submissions * 4)

        def answer(prompt, **kwargs):
            choice = next(attempts)
            turn = model.sample_text.call_count
            if turn <= len(names) * 3:
                self.assertIn("지금은 협상만 할 수 있습니다.", prompt)
                if turn % len(names) == 1:
                    return json.dumps({"type": "speak", "channel": "public", "text": "같이 풀 팀원을 찾아요.",
                                       "note": "팀을 검토한다."})
            return json.dumps({"type": "submit", "choice": choice, "note": "지금 확정한다."})

        model.sample_text.side_effect = answer
        match = Match(names, 1, model=model, live_players=names, live_turns=len(names) * 4)
        rectangle_stage(match, names, dict.fromkeys(names, 0), match.pieces.copy())

        rounds = [event for event in match.events if event.msg_type == "negotiation_round"]
        self.assertEqual([json.loads(event.content)["round"] for event in rounds], [1, 2, 3, 4])
        start = next(event for event in match.events if event.msg_type == "negotiation_start")
        self.assertEqual(json.loads(start.content)["submission_opens_on"], 4)
        for first, last in zip(rounds[:3], rounds[1:]):
            events = match.events[first.turn + 1:last.turn]
            self.assertTrue(any(event.msg_type == "public" for event in events))
            self.assertTrue(any(event.msg_type == "invalid_action" for event in events))
            self.assertFalse(any(event.msg_type in {"action", "choice_progress"} for event in events))
        end = next(event for event in match.events if event.msg_type == "negotiation_end")
        self.assertEqual(json.loads(end.content), {"choice": 2, "reason": "all_submitted"})
        choices = [event for event in match.events if event.msg_type == "action"
                   and json.loads(event.content)["phase"] == "choice_2"]
        self.assertEqual([event.agent_name for event in choices], names)
        self.assertTrue(all(rounds[-1].turn < event.turn < end.turn and event.visible_to == [event.agent_name]
                            for event in choices))
        self.assertNotIn(choices[0], match.observations("P02"))
        teams = match.events[end.turn + 1]
        self.assertEqual(teams.msg_type, "teams")
        self.assertEqual(json.loads(teams.content)["teams"][0], names[:3])
        self.assertEqual(match.events[teams.turn + 1].msg_type, "rectangle_puzzle")

    def test_choice_two_deadline_collects_only_remaining_choices(self):
        names = [f"P{i:02}" for i in range(1, 17)]
        model = Mock(spec=LanguageModel)
        team_choice = "P01 P02 P03"
        early = {"type": "submit", "choice": team_choice, "note": "이 팀에 합류한다."}
        invalid = {**early, "choice": "P01 P03 P04"}
        duplicate = {**early, "choice": "개인"}
        speech = {"type": "speak", "channel": "public", "text": "팀 구역을 나눠 봐요.", "note": "팀원과 계속 조율한다."}
        pass_action = {"type": "pass", "note": "협상을 더 지켜본다."}
        actions = [*[pass_action] * 9, early, invalid, pass_action, duplicate, pass_action, pass_action,
                   speech, pass_action, pass_action, *[pass_action] * 12]
        model.sample_text.side_effect = [*(json.dumps(action) for action in actions), team_choice, team_choice]
        match = Match(names, 1, model=model, live_players=names[:3], live_turns=32)
        rectangle_stage(match, names, dict.fromkeys(names, 0), match.pieces.copy())

        end = next(event for event in match.events if event.msg_type == "negotiation_end")
        self.assertEqual(json.loads(end.content), {"choice": 2, "reason": "limit"})
        self.assertEqual(sum(event.msg_type == "negotiation_round" for event in match.events), 10)
        choices = [event for event in match.events if event.msg_type == "action"
                   and json.loads(event.content)["phase"] == "choice_2"]
        self.assertEqual([event.agent_name for event in choices], names)
        self.assertEqual([event.agent_name for event in choices if event.turn < end.turn], ["P01"])
        self.assertEqual(json.loads(choices[0].content)["action"], team_choice)
        self.assertEqual(sum(event.msg_type == "invalid_action" for event in match.events[:end.turn]), 2)
        self.assertTrue(any(event.msg_type == "public" and event.agent_name == "P01" for event in match.events[:end.turn]))
        teams = next(event for event in match.events if event.msg_type == "teams")
        self.assertEqual(json.loads(teams.content)["teams"][0], names[:3])

    def test_cube_review_delays_grading_and_retry_receives_its_own_wrong_guess(self):
        names = [f"P{i:02}" for i in range(1, 17)]
        calls = []

        def run(command, *, input, **kwargs):
            images = [Path(command[index + 1]).read_bytes() for index, arg in enumerate(command) if arg == "--image"]
            self.assertEqual(command[command.index("--model") + 1], "gpt-6.1-terra" if images else "gpt-6-luna")
            calls.append((input, images))
            schema = json.loads(Path(command[command.index("--output-schema") + 1]).read_text())
            response = {"action": "개인"}
            if images:
                self.assertEqual(schema["required"], ["review", "note", "action"] if len(calls) == 1 else ["note", "action"])
                response = {"action": ("175", "182", "360")[len(calls) - 1], "note": "층별로 나누어 셌다."}
                if len(calls) == 1:
                    response["review"] = True
            else:
                self.assertEqual(schema["required"], ["note", "action"])
            event = {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(response)}}
            return CompletedProcess(command, 0, json.dumps(event), "")

        with TemporaryDirectory() as workspace, patch("games.models.subprocess.run", side_effect=run):
            model = CodexLanguageModel("gpt-6-luna", Path(workspace), image_model="gpt-6.1-terra")
            match = Match(names, 1, model=model, live_players=names[:1], live_turns=3, allow_review=True)
            cube_priority(match)
            match.live_turns = 1
            match.decide(names[0], "choice_2", "참가 방식을 고르세요.", "개인", options=("개인",))

        (prompt, images), (review_prompt, review_images), (retry_prompt, retry_images), (next_prompt, next_images) = calls
        event = next(event for event in match.events if event.msg_type == "cube_puzzle")
        data = json.loads(event.content)
        self.assertEqual(set(data), {"images"})
        self.assertEqual(len(images), 4)
        self.assertEqual(images, [b64decode(image) for image in data["images"]])
        self.assertTrue(all(image.startswith(b"\x89PNG\r\n\x1a\n") for image in images))
        self.assertEqual(len(set(images)), 4)
        self.assertEqual(images, review_images)
        self.assertEqual(images, retry_images)
        self.assertIn("15명이 맞히면 종료", prompt)
        self.assertIn("우선권 16위", prompt)
        self.assertIn("20초가 지나야 다시 제출", prompt)
        self.assertIn("전체 개수만 정수 하나로 출력", prompt)
        self.assertIn("개수를 어떻게 셌는지 짧게 남기세요", prompt)
        for request in (prompt, review_prompt, retry_prompt):
            instructions = request.split("Exercise: ", 1)[1].split("\n추가 검토 · 임시 답안", 1)[0]
            self.assertNotIn("층", instructions)
        self.assertIn("가상 시간 5초 뒤", prompt)
        self.assertIn("임시 답안 175", review_prompt)
        self.assertNotIn("오답 판정을 받은 개수", prompt)
        self.assertIn("이전에 제출해 오답 판정을 받은 개수는 182입니다.", retry_prompt)
        self.assertNotIn("개수는 175입니다.", retry_prompt)
        self.assertNotIn("heights", prompt + retry_prompt)
        self.assertNotIn("360", prompt + retry_prompt)
        for image in data["images"]:
            self.assertNotIn(image, prompt + retry_prompt + next_prompt)
        self.assertEqual(next_images, [])
        notes = [event for event in match.events if event.msg_type == "decision_note"]
        self.assertEqual([json.loads(event.content) for event in notes], [
            {"phase": "cubes", "note": "추가 검토 · 임시 답안 175 · 층별로 나누어 셌다."},
            *[{"phase": "cubes", "note": "층별로 나누어 셌다."}] * 2,
        ])
        self.assertTrue(all(event.visible_to == [names[0]] for event in notes))
        self.assertFalse(any(event in match.observations(names[1]) for event in notes))
        layers = [sum(cube_height(row, col) > level for row in range(10) for col in range(10)) for level in range(6)]
        self.assertEqual(layers, [100, 100, 60, 60, 20, 20])
        result = next(event for event in match.events if event.msg_type == "priority")
        self.assertEqual(json.loads(result.content)["answer"], 360)
        submissions = [json.loads(event.content) for event in match.events if event.msg_type == "cube_answer"]
        self.assertEqual(sum(submission["correct"] for submission in submissions), 15)
        first, retry = [submission for submission in submissions if submission["player"] == names[0]]
        self.assertFalse(first["correct"])
        self.assertEqual(first["guess"], 182)
        self.assertEqual(first["time"], Random(1).randrange(5, 50) + 5)
        self.assertTrue(retry["correct"])
        self.assertEqual(retry["time"] - first["time"], 20)

    def test_funded_choice_nine_and_nonadjacent_nomination(self):
        names = [f"P{i:02}" for i in range(1, 17)]
        funded = Match(names, 1, pieces=[8] * 16)
        result = either_or(funded)
        choice = next(json.loads(event.content) for event in funded.events if event.msg_type == "choice_9_result")
        self.assertGreaterEqual(choice["pledged"], 8)
        self.assertEqual(len(result["eliminated"]), 1)
        self.assertEqual(len(result["living"]), 8)
        self.assertEqual(len(result["prison"]), 7)

        match = Match(names, 1)
        ranking = names.copy()
        pieces = dict.fromkeys(names, 0)
        original = match.decide

        def choose(name, phase, prompt, default, **kwargs):
            if phase == "nominate" and name == names[-2] and names[4] in kwargs["options"]:
                default = names[4]
            return original(name, phase, prompt, default, **kwargs)

        def duel(_, challenger, opponent):
            return challenger if (challenger, opponent) == (names[-2], names[4]) else opponent

        with (patch.object(match, "decide", side_effect=choose),
              patch.object(match, "decide_together", return_value=dict.fromkeys(names, "지목")),
              patch("games.either_or.memory_poker.poker_duel", side_effect=duel)):
            memory_stage(match, ranking, pieces)
        self.assertEqual(ranking[5], names[4])
        self.assertEqual(ranking[13], names[14])
        self.assertEqual(ranking[14], names[13])
        self.assertEqual(sum(pieces.values()), 3)

    def test_thresholds_and_puzzle_scoring(self):
        stack = [6, 6, 0]
        self.assertEqual(place(stack, 1), 3)
        self.assertEqual(stack, [1])
        self.assertEqual(count_rectangles([[1, 1], [0, 1]], 2), 2)
        self.assertGreater(hand_rank([(14, "S"), (2, "S"), (3, "S"), (4, "S"), (5, "S")]),
                           hand_rank([(13, "S"), (13, "H"), (13, "C"), (13, "D"), (2, "S")]))

    def test_rectangle_buzzer_follows_response_completion(self):
        names = ("P01", "P02")
        match = Match(names, 1, model=Mock(spec=LanguageModel), live_players=names, live_turns=2)
        earlier_response = Event()
        worker = local()

        def query(name, prompt, **kwargs):
            self.assertIn("답을 정수 하나로 제출하거나 패스", prompt)
            if name == "P01":
                self.assertTrue(earlier_response.wait(timeout=2))
            worker.player = name
            return "16", StrategyNote()

        def clock():
            timestamp = monotonic_ns()
            if getattr(worker, "player", None) == "P02":
                earlier_response.set()
            return timestamp

        with (patch.object(match, "_query", side_effect=query), patch("games.match.monotonic_ns", side_effect=clock),
              patch("games.either_or.rectangle_counting.count_rectangles", return_value=16)):
            self.assertEqual(rectangle_race(match, [("P01",), ("P02",)]), ("P02",))

        buzzes = [json.loads(event.content) for event in match.events if event.msg_type == "buzz"]
        self.assertEqual([(buzz["player"], buzz["answer"], buzz["clock"]) for buzz in buzzes], [("P02", 16, "response")])

    def test_rectangle_buzzer_skips_invalid_late_and_repeat_team_answers(self):
        teams = [("P01",), ("P02", "P03", "P04"), ("P05",), ("P06",)]
        names = [name for team in teams for name in team]
        match = Match(names, 1, model=Mock(spec=LanguageModel), live_players=names, live_turns=len(names))
        responses = {"P01": ("0 16", 1), "P02": ("15", 2), "P03": ("16", 3),
                     "P04": ("패스", 4), "P05": ("16", 301), "P06": ("14", 300)}
        worker = local()

        def query(name, prompt, **kwargs):
            answer, worker.seconds = responses[name]
            return answer, StrategyNote()

        with (patch.object(match, "_query", side_effect=query),
              patch("games.match.monotonic_ns", side_effect=lambda: getattr(worker, "seconds", 0) * 1_000_000_000),
              patch("games.either_or.rectangle_counting.count_rectangles", return_value=16)):
            self.assertIsNone(rectangle_race(match, teams, phase="rectangle_challenge"))

        buzzes = [json.loads(event.content) for event in match.events if event.msg_type == "buzz"]
        self.assertEqual([(buzz["player"], buzz["time"], buzz["correct"]) for buzz in buzzes],
                         [("P02", 2, False), ("P06", 300, False)])
        rejected = next(event for event in match.events if event.msg_type == "invalid_action")
        self.assertEqual(rejected.visible_to, ["P01"])
        self.assertEqual(json.loads(rejected.content)["action"], "0 16")

    def test_poker_recalls_only_eight_to_ten_selected_cards(self):
        valid_selections = ("BCDEFGHI", "BCDEFGHIJ", "BCDEFGHIJK")
        for selection in (*valid_selections, "BCDEFGH", "BCDEFGHIJKL", None):
            with self.subTest(selection=selection):
                client = Mock()
                requests = []

                def complete(**kwargs):
                    prompt = kwargs["input"][0]["content"][0]["text"]
                    requests.append(prompt)
                    reveal = match.events[-1]
                    self.assertEqual((reveal.msg_type, reveal.visible_to), ("poker_cards", "all"))
                    shown = json.loads(reveal.content)
                    self.assertNotIn(reveal.content, prompt)
                    if len(requests) == 1:
                        cards = prompt.split("공개된 카드 위치 ", 1)[1].split(". 공유 카드", 1)[0].split()
                        self.assertEqual(len(cards), 16)
                        self.assertEqual(shown, {"phase": "memorize", "display": [card.split("=")[1] for card in cards],
                                                 "players": ["P01", "P02"]})
                        self.assertIn("기억할 위치를 8~10개 고르세요", prompt)
                        result = {"action": selection or f"반려 답안 {cards[0]}", "note": f"암기 메모 {cards[0]}"}
                    else:
                        self.assertEqual(shown["phase"], "memory_poker")
                        self.assertIn(f"공유 카드 3장은 {shown['community']}.", prompt)
                        result = {"action": "A B", "note": "A는 기억하지 못해 추측했다."}
                    return SimpleNamespace(status="completed", output_text=json.dumps(result), usage=None)

                client.responses.create.side_effect = complete
                model = OpenAILanguageModel("test-model", client)
                match = Match(("P01", "P02"), 1, model=model, live_players=("P01",), live_turns=2)
                poker_duel(match, "P01", "P02")

                next_prompt = requests[1]
                recalled = next_prompt.split("내가 기억한 카드 위치 ", 1)[1].split(". 공유 카드", 1)[0].split()
                self.assertNotIn("암기 메모", next_prompt)
                self.assertNotIn("반려 답안", next_prompt)
                self.assertNotIn("공개된 카드 위치", next_prompt)
                first_reveal = next(event for event in match.events if event.msg_type == "poker_cards")
                self.assertNotIn(first_reveal.content, next_prompt)
                self.assertTrue(8 <= len(recalled) <= 10)
                if selection in valid_selections:
                    self.assertEqual("".join(card[0] for card in recalled), selection)
                    self.assertFalse(any(card.startswith("A=") for card in recalled))
                else:
                    self.assertTrue(any(event.msg_type == "invalid_action" for event in match.events))
                self.assertTrue(any(event.msg_type == "action" and event.agent_name == "P01"
                                    and json.loads(event.content) == {"phase": "memory_poker", "action": "A B"}
                                    for event in match.events))

    def test_market_orders_and_opening_snapshot(self):
        start = [10_000] * 7
        held = [7, 2, 5, 0, 8, 1, 4]
        bought, sold = [7, 2, 5, 5, 8, 11, 6], [0, 0, 0, 5, 0, 10, 2]
        self.assertEqual(next_prices(start, start, held, bought, sold, set(), 1),
                         [10_000, 9_000, 9_000, 10_000, 9_000, 11_400, 9_000])
        holdings = [0] * 7
        with self.assertRaises(ValueError):
            trade_orders("[[1, 1], [2, 20]]", 100_000, holdings, start)
        self.assertEqual(holdings, [0] * 7)
        orders, cash, after = trade_orders("[[1, 10], [1, -10]]", 100_000, holdings, start)
        self.assertEqual((orders, cash, after), ([[1, 10], [1, -10]], 100_000, holdings))

    def test_market_trades_and_private_negotiation_interleave(self):
        names = tuple(f"P{i:02}" for i in range(1, 13))
        client = Mock()
        model = OpenAILanguageModel("test-model", client)
        match = Match(names, 1, model=model, live_players=names, live_turns=37)
        invitation = "둘이서 코요테크 매수량을 맞춰요."
        reply = "방에 들어와 후자전자 거래량과 비교하겠습니다."
        whisper = "코요테크를 다시 팔아도 매수량은 남습니다."

        def complete(**kwargs):
            call = client.responses.create.call_count
            prompt = kwargs["input"][0]["content"][0]["text"]
            action = {"type": "pass"}
            if call in (1, 2):
                action = {"type": "speak", "channel": "room_invite", "to": "P02", "room": 2,
                          "text": invitation, "orders": [[6, call + 1]]}
                self.assertIn(persona_context("P01"), prompt)
                self.assertNotIn(persona_context("P02"), prompt)
                if call == 2:
                    self.assertIn("추가 검토 · 임시 답안", prompt)
            elif call == 3:
                invite_id = int(re.search(r"초대 #(\d+) · P01 · 2번 논의실", prompt)[1])
                self.assertIn(invitation, prompt)
                self.assertNotIn('"cash":70000', prompt)
                action = {"type": "respond_invite", "invite_id": invite_id, "decision": "accept", "text": reply}
            elif call == 4:
                self.assertNotIn(invitation, prompt)
                self.assertNotIn(reply, prompt)
                self.assertNotIn('"cash":70000', prompt)
            elif call == 25:
                self.assertIn("거래 시간 2/5분 차", prompt)
                self.assertIn("내 현금 70000원", prompt)
                self.assertIn("'코요테크', 10000, 3", prompt)
                self.assertIn(reply, prompt)
                action = {"type": "speak", "channel": "whisper", "to": "P02", "text": whisper, "orders": [[6, -3]]}
            elif call == 36:
                self.assertIn("내 현금 100000원", prompt)
                action = {"type": "trade", "orders": [[6, 2], [6, -2]]}
            elif call == 37:
                self.assertIn(whisper, prompt)
            response = {"action": json.dumps(action, ensure_ascii=False), "note": "체결과 대화에 따라 계획을 조정한다."}
            if "review" in kwargs["text"]["format"]["schema"]["properties"]:
                response["review"] = call == 1
            return SimpleNamespace(status="completed", output_text=json.dumps(response), usage=None)

        client.responses.create.side_effect = complete
        market(match)
        first, second = [event for event in match.events if event.msg_type == "market"][:2]
        self.assertEqual(json.loads(first.content)["stocks"]["코요테크"]["price"], 10_000)
        self.assertEqual(json.loads(second.content)["stocks"]["코요테크"],
                         {"price": 11_400, "held": 0, "bought": 5, "sold": 5})
        fills = [event for event in match.events if event.msg_type == "trade_fill" and event.turn < second.turn]
        self.assertEqual([json.loads(event.content)["cash"] for event in fills], [70_000, 100_000, 100_000])
        self.assertTrue(all(event.visible_to == ["P01"] for event in fills))
        for kind in ("room_invite", "room_invite_response", "room", "whisper"):
            event = next(event for event in match.events if event.msg_type == kind)
            self.assertIn(event, match.observations("P02"))
            self.assertNotIn(event, match.observations("P03"))
