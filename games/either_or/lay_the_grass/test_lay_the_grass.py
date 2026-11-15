from collections import Counter
import json
from dataclasses import asdict
import unittest
from unittest.mock import Mock

from concordia.language_model.language_model import LanguageModel

from .choice_five import INFORMATION, MAX_NOTE_LENGTH, OBSTACLE_RULES, PARTNER_RULES, PREVIEW, SCORE, STANCE_RULES, format_speech
from .board import PARK, TILE_ROWS, Placement, Shape, tile_shape, variants
from .demo import make_grass_demo
from .environment import ATTACK, CHECK, DEFENSE, FAIL, MANHOLE, MAX_PLAN_LENGTH, PHASE_LABELS, TREE, LayTheGrass
from .live import LiveGrassBackend
from .simulation import ConcordiaBackend, play_arena


class TileGeometryTest(unittest.TestCase):
    def test_public_diagrams_and_rotation(self) -> None:
        self.assertEqual(len(PARK), 121)
        self.assertEqual(
            [(len(tile_shape(n, 0).cells), len(tile_shape(n, 0).holes)) for n in TILE_ROWS],
            [(10, 0), (9, 2), (8, 3), (7, 4), (7, 5), (7, 6), (9, 8)],
        )
        original = tile_shape(6, 0)
        right = max(col for _, col in original.cells)
        reflected = Shape(
            frozenset((row, right - col) for row, col in original.cells),
            frozenset((row, right - col) for row, col in original.holes),
        )
        self.assertNotIn(reflected, {shape for _, shape in variants(6, False)})
        with self.assertRaises(ValueError):
            tile_shape(6, 45)

    def test_defense_can_cut_connected_edges_but_not_the_number_or_center(self) -> None:
        self.assertEqual(len(tile_shape(3, 90, ((0, 0), (0, 1))).cells), 8)
        for number, cut in (
            (3, ((1, 2),)),           # numbered cell
            (3, ((1, 1),)),           # creates an enclosed gap
            (3, ((0, 0), (0, 2))),    # nonadjacent cuts
            (11, ((1, 1),)),          # disconnects the tile
        ):
            with self.subTest(number=number, cut=cut), self.assertRaises(ValueError):
                tile_shape(number, 0, cut)
        with self.assertRaises(ValueError):
            Placement(0, 0, 0, ((0, 0),)).shape(3, defense=False)


class LayTheGrassTest(unittest.TestCase):
    def test_room_move_and_speech_share_one_turn_in_both_discussions(self) -> None:
        names = [f"P{n:02}" for n in range(1, 17)]
        wait = '{"type":"pass","note":"계획을 유지한다."}'
        for after_preview in (False, True):
            with self.subTest(after_preview=after_preview):
                game = LayTheGrass(dict.fromkeys(names, 0), names, discussion_rounds=2)
                game.reset()
                if after_preview:
                    for _ in range(2 * len(names)):
                        game.step(game.get_next_player(), wait)
                    for name in names:
                        game.step(name, SCORE)
                    self.assertEqual(game.phase, "talk")
                for name in names:
                    action = {"type": "pass", "note": "답변을 기다린다."}
                    if name in {"P01", "P02", "P03"}:
                        action["room"] = 2 if name == "P03" else 1
                    game.step(name, json.dumps(action))

                speech = {"type": "speak", "channel": "room", "text": "같이 배치 위치를 정하자.",
                          "note": "P03과 배치가 겹치는지 확인한다."}
                start = len(game.match_events())
                invalid = json.dumps({**speech, "room": 0})
                self.assertFalse(game.check_action(invalid, "P01"))
                with self.assertRaises(ValueError):
                    game.step("P01", invalid)
                action = json.dumps({**speech, "room": 2})
                self.assertTrue(game.check_action(action, "P01"))
                self.assertIn("현재 위치 1번 논의실", game.get_observation("P01")[-1].content)
                game.step("P01", action)
                self.assertEqual(game.get_next_player(), "P02")
                move, message, note = game.match_events(start)
                self.assertEqual([move.msg_type, message.msg_type, note.msg_type],
                                 ["room_move", "room", "discussion_note"])
                self.assertEqual({event.turn for event in (move, message, note)}, {message.turn})
                self.assertEqual(message.visible_to, ["P01", "P03"])
                self.assertIn(message, game.get_observation("P03"))
                self.assertNotIn(message, game.get_observation("P02"))
                self.assertNotIn(note, game.get_observation("P03"))

    def test_room_invites_are_private_and_accept_or_decline_once_in_both_discussions(self) -> None:
        names = [f"P{n:02}" for n in range(1, 17)]

        def action(**fields):
            return json.dumps({"note": "타일 배치 후보를 조율한다.", **fields}, ensure_ascii=False)

        def invite(game, sender, recipient, room):
            start = len(game.match_events())
            game.step(sender, action(
                type="speak", channel="room_invite", to=recipient, room=room, text="구역을 비교하자.",
            ))
            return next(message for message in game.match_events(start) if message.msg_type == "room_invite")

        game = LayTheGrass(dict.fromkeys(names, 0), names, discussion_rounds=2)
        game.reset()
        for phase in (None, "talk"):
            with self.subTest(phase=phase):
                invitation = invite(game, "P01", "P03", 3)
                accept = action(
                    type="respond_invite", invite_id=invitation.turn, decision="accept", text="나는 가운데를 볼게.",
                )
                self.assertEqual(invitation.visible_to, ["P01", "P03"])
                self.assertNotIn(invitation, game.get_observation("P02"))
                self.assertFalse(game.check_action(accept, "P02"))
                start = len(game.match_events())
                game.step("P02", action(type="move", room=3))
                self.assertEqual([event.msg_type for event in game.match_events(start)], ["room_move", "discussion_note"])
                self.assertIn(f"초대 #{invitation.turn} · P01 · 3번 논의실", game.get_observation("P03")[-1].content)
                self.assertTrue(game.check_action(accept, "P03"))
                start = len(game.match_events())
                game.step("P03", accept)
                move, response, speech, note = game.match_events(start)
                self.assertEqual((move.msg_type, response.msg_type, speech.msg_type, note.msg_type),
                                 ("room_move", "room_invite_response", "room", "discussion_note"))
                self.assertEqual({event.turn for event in (move, response, speech, note)}, {move.turn})
                self.assertEqual(response.visible_to, ["P03", "P01"])
                self.assertEqual(speech.visible_to, ["P01", "P02", "P03"])
                self.assertNotIn(response, game.get_observation("P02"))

                other = invite(game, "P04", "P05", 4)
                start = len(game.match_events())
                game.step("P05", action(type="respond_invite", invite_id=other.turn, decision="decline"))
                response, _ = game.match_events(start)
                self.assertEqual(response.msg_type, "room_invite_response")
                self.assertEqual(response.visible_to, ["P05", "P04"])
                self.assertIn("거절", response.content)
                for name in names[5:] + names[:2]:
                    game.step(name, action(type="pass"))
                self.assertIn("현재 위치 3번 논의실", game.get_observation("P03")[-1].content)
                self.assertFalse(game.check_action(accept, "P03"))
                for name in names[2:-1]:
                    game.step(name, action(type="pass"))
                pending = invite(game, "P16", "P01", 2)
                if phase is None:
                    for name in names:
                        game.step(name, SCORE)
                    self.assertFalse(game.check_action(
                        action(type="respond_invite", invite_id=pending.turn, decision="accept"), "P01",
                    ))
        self.assertEqual(game.phase, "draft")

    def test_draft_prompt_keeps_rules_and_private_preview_after_long_discussion(self) -> None:
        names = [f"P{n:02}" for n in range(1, 17)]
        scores = {name: seat for seat, name in enumerate(names)}
        scores["P03"] = scores["P02"]
        game = LayTheGrass(scores, names, discussion_rounds=5)
        game.reset()
        board = game.render_board()
        for note in (None, " ", "가" * (MAX_NOTE_LENGTH + 1)):
            self.assertFalse(game.check_action(json.dumps({"type": "pass", "note": note}), "P01"))
        self.assertFalse(game.check_action('{"type":"pass"}', "P01"))
        for round_number in range(1, 6):
            for name in names:
                game.step(name, json.dumps({"type": "pass", "note": f"선택 5 전 {name} 메모 {round_number}"}))
        model = Mock(spec=LanguageModel)
        model.sample_choice.return_value = (0, "a", {})
        backend = ConcordiaBackend("P01", model)
        backend.query("P01", "잔디 깔기 참가자", game.get_observation("P01"))
        choice_prompt = model.sample_choice.call_args.kwargs["prompt"]
        self.assertIn("선택 5 전 P01 메모 5", choice_prompt)
        self.assertNotIn("선택 5 전 P01 메모 4", choice_prompt)
        self.assertNotIn("선택 5 전 P02 메모 5", choice_prompt)
        for name in names:
            game.step(name, INFORMATION if name == "P01" else SCORE)
        self.assertEqual(game.phase, "plan")
        self.assertEqual(game.get_next_player(), "P01")
        self.assertFalse(game.check_action("계획", "P02"))
        self.assertFalse(game.check_action(" ", "P01"))
        self.assertFalse(game.check_action("가" * (MAX_PLAN_LENGTH + 1), "P01"))
        plan = "3번과 방어를 우선 검토하고, 협력 상대가 없으면 견제를 고른다."
        model.sample_text.return_value = plan
        action = backend.query("P01", "잔디 깔기 참가자", game.get_observation("P01"))
        self.assertIn(PREVIEW, model.sample_text.call_args.kwargs["prompt"])
        self.assertIn("협상 전에 볼 짧은 비공개 전략 메모", model.sample_text.call_args.kwargs["prompt"])
        game.step("P01", action)
        self.assertEqual(game.phase, "talk")
        self.assertFalse(any(message.msg_type in {"preview", "grass_plan"}
                             for message in game.get_observation("P02")))
        self.assertIn("잔디 타일을 고르기 전 협상", game.get_observation("P01")[-1].content)
        for round_number in range(1, 6):
            for name in names:
                game.step(name, json.dumps({
                    "type": "speak", "channel": "public", "text": "5번 타일을 고를게요.",
                    "note": f"미리보기 후 {name} 메모 {round_number}",
                }))

        model.sample_text.return_value = "3"
        for name, standing in (("P01", "+0점 · 내 현재 순위 16위"), ("P02", "+6점 · 내 현재 순위 공동 14위")):
            with self.subTest(player=name):
                backend = ConcordiaBackend(name, model)
                action = backend.query(name, "잔디 깔기 참가자", game.get_observation(name))
                prompt = model.sample_text.call_args.kwargs["prompt"]
                self.assertIn("5번 타일을 고를게요.", prompt)
                self.assertIn(f"\n{board}\n타일 도안", prompt)
                self.assertIn("잔디 타일 번호는 3, 4, 6, 7, 9, 11, 13입니다.", prompt)
                self.assertIn("‘선택 5’의 5는 양자택일의 진행 단계 번호", prompt)
                self.assertIn(f"내 누적 승점 {standing} / 16명", prompt)
                self.assertIn("공개 누적 승점 (높은 순) P16 +20 · P15 +19", prompt)
                self.assertIn("내 승점과 최종 순위를 높이고 생존 가능성을 키우세요.", prompt)
                self.assertEqual(PREVIEW in prompt, name == "P01")
                self.assertEqual(PREVIEW.splitlines()[0] in prompt, name == "P01")
                self.assertEqual(plan in prompt, name == "P01")
                self.assertIn(f"미리보기 후 {name} 메모 5", prompt)
                self.assertNotIn(f"미리보기 후 {name} 메모 4", prompt)
                other = "P02" if name == "P01" else "P01"
                self.assertNotIn(f"미리보기 후 {other} 메모", prompt)
                game.step(name, action)

    def test_16_concordia_players_complete_the_match(self) -> None:
        arena = make_grass_demo()
        game = arena.environment
        initial_scores = game.scores
        play_arena(arena)
        self.assertTrue(game.is_terminal())
        log = game.get_observation()
        preview_discussion = next(
            message.turn for message in log
            if message.msg_type == "grass_phase" and message.content == PHASE_LABELS["talk"]
        )
        plans = [message for message in game.match_events() if message.msg_type == "grass_plan"]
        self.assertEqual([message.agent_name for message in plans], ["P03", "P05"])
        self.assertTrue(all(message.turn < preview_discussion and message.visible_to == [message.agent_name]
                            for message in plans))
        self.assertFalse(any(message.msg_type == "grass_plan" for message in log))
        notes = [message for message in game.match_events() if message.msg_type == "discussion_note"]
        self.assertEqual(Counter(message.agent_name for message in notes), dict.fromkeys(game.player_names, 20))
        self.assertTrue(all(message.visible_to == [message.agent_name] for message in notes))
        self.assertFalse(any(message.msg_type == "discussion_note" for message in log))
        first_draft = next(message.turn for message in log if message.msg_type == "grass_tile")
        room_chat = [
            message for message in game.get_observation("P04")
            if message.msg_type == "room" and preview_discussion < message.turn < first_draft
        ]
        self.assertEqual([message.agent_name for message in room_chat], ["P05", "P04", "P05", "P04"])
        self.assertEqual([message.visible_to for message in room_chat], [
            ["P04", "P05", "P06"], *[["P04", "P05", "P07"]] * 3,
        ])
        for player in arena.players:
            with self.subTest(player=player.name):
                observed_chat = [
                    message for message in game.get_observation(player.name)
                    if message.msg_type == "room" and preview_discussion < message.turn < first_draft
                ]
                expected_chat = [message for message in room_chat if player.name in message.visible_to]
                self.assertEqual(observed_chat, expected_chat)
                memories = "\n".join(player.backend.memory.get_all_memories_as_text())
                for message in room_chat:
                    self.assertEqual(format_speech(message) in memories, message in expected_chat)
        draft_order = [message.agent_name for message in log if message.msg_type == "grass_tile"]
        self.assertEqual(draft_order, sorted(initial_scores, key=lambda name: (
            initial_scores[name] + (0 if name in {"P03", "P05"} else 5),
            game.priority[name],
        )))
        placements = {
            message.agent_name: json.loads(message.content)
            for message in log if message.msg_type == "grass_placement"
        }
        self.assertEqual(len(placements), 16)
        self.assertEqual(list(placements), sorted(initial_scores, key=lambda name: (
            placements[name]["tile"], game.priority[name],
        )))
        self.assertEqual(len(game.placed), 13)
        self.assertEqual(len(game.occupied), sum(len(shape.cells) for shape in game.placed.values()))
        for shape in game.placed.values():
            self.assertLessEqual(shape.cells, PARK)
            self.assertLessEqual(shape.cells & game.trees, shape.holes)
        self.assertEqual(placements["P04"]["points"], 7)  # tile 3 × 2 and a +1 manhole
        self.assertEqual(placements["P16"]["points"], -4)
        self.assertEqual(placements["P09"]["points"], 0)
        self.assertEqual(game.shared_edges, {"P04": 4, "P05": 4})
        self.assertEqual(game.scores["P04"], initial_scores["P04"] + 5 + 7 + 2)
        self.assertEqual(game.scores["P05"], initial_scores["P05"] + 4 + 2)
        self.assertNotIn("preview", {message.msg_type for message in log})
        self.assertIn("preview", {message.msg_type for message in game.get_observation("P05")})
        self.assertNotIn("preview", {message.msg_type for message in game.get_observation("P01")})

    def test_tree_holes_collisions_and_check_bonus(self) -> None:
        names = [f"P{n:02}" for n in range(1, 17)]
        game = LayTheGrass(dict.fromkeys(names, 0), names)
        game.reset()
        for _ in names:
            game.step(game.get_next_player(), SCORE)
        for _ in names:
            game.step(game.get_next_player(), "4")
        self.assertIn(STANCE_RULES, game.get_observation("P01")[-1].content)
        self.assertNotIn(PARTNER_RULES, game.get_observation("P01")[-1].content)
        for _ in names:
            name = game.get_next_player()
            game.step(name, ATTACK if name in {"P01", "P02"} else DEFENSE)
        self.assertIn(PARTNER_RULES, game.get_observation("P01")[-1].content)
        self.assertNotIn(OBSTACLE_RULES, game.get_observation("P01")[-1].content)
        for _ in names:
            game.step(game.get_next_player(), CHECK)
        self.assertIn(OBSTACLE_RULES, game.get_observation("P01")[-1].content)
        for _ in names:
            name = game.get_next_player()
            game.step(name, MANHOLE if name == "P01" else TREE)
        self.assertEqual(game.phase, "manhole")
        game.step("P01", "[[4,2],[0,18]]")
        self.assertEqual(game.phase, "tree")
        self.assertFalse(game.check_action("[4,2]", "P02"))
        game.step("P02", "[5,2]")  # hole in P01's placement
        game.step("P03", "[5,4]")  # solid cell in an alternative placement
        intended = Placement(4, 2, 0)
        blocked = Placement(4, 3, 0)
        available = sorted(
            PARK - intended.shape(4, defense=False).cells - blocked.shape(4, defense=False).cells
            - game.trees - game.manholes.keys()
        )
        for cell in available[:13]:
            game.step(game.get_next_player(), json.dumps(cell))
        self.assertEqual(game.phase, "place")
        model = Mock(spec=LanguageModel)
        model.sample_text.return_value = "1"
        backend = LiveGrassBackend("P01", model, game)
        action = backend.query("P01", "잔디 깔기 참가자", game.get_observation("P01"))
        prompt = model.sample_text.call_args.kwargs["prompt"]
        self.assertIn("내 경기 페르소나 · P01", prompt)
        self.assertNotIn("내 경기 페르소나 · P02", prompt)
        candidate = next(line for line in prompt.splitlines() if line.startswith("후보 1 "))
        self.assertEqual(json.loads(action), json.loads(candidate.removeprefix("후보 1 ")))
        self.assertTrue(game.check_action(action, "P01"))
        self.assertFalse(game.check_action(json.dumps(asdict(blocked)), "P01"))
        game.step("P01", json.dumps(asdict(intended)))
        self.assertFalse(game.check_action(json.dumps(asdict(intended)), "P02"))
        for _ in names[1:]:
            game.step(game.get_next_player(), FAIL)
        self.assertTrue(game.is_terminal())
        self.assertEqual(game.scores["P01"], 5 + 8 + 1 + 5)
        self.assertEqual(game.scores["P02"], 5 - 4)
        self.assertEqual(game.scores["P03"], 5)
