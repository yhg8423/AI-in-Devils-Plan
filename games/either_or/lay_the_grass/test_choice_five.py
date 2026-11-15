import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from concordia.components.agent.observation import OBSERVATION_TAG

from .choice_five_demo import make_demo_arena
from .choice_five import CHANNEL_NAMES, CHOICE_REQUEST, INFORMATION, PREVIEW, ROOMS, SCORE
from .simulation import DISCUSSION_PROMPT, make_arena, play_choice_five


class ChoiceFiveIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.initial_scores = {f"P{seat:02}": seat - 9 for seat in range(1, 17)}
        self.informed_players = {"P03", "P16"}
        self.choices = {
            name: INFORMATION if name in self.informed_players else SCORE
            for name in self.initial_scores
        }

    def test_settlement_and_observations_for_all_16_players(self) -> None:
        arena = make_arena(self.initial_scores, self.choices)
        environment = arena.environment
        initial_view = [message.content for message in environment.get_observation()]
        with self.assertRaises(ValueError):
            environment.step("P01", "invalid")
        self.assertEqual(environment.get_next_player(), "P01")

        for _ in range(15):
            result = arena.step()
            self.assertFalse(result.terminal)
            self.assertTrue(all(reward == 0 for reward in result.reward.values()))
            self.assertEqual(environment.scores, self.initial_scores)
            for name in self.initial_scores:
                self.assertEqual(
                    [message.content for message in environment.get_observation(name)],
                    initial_view,
                )

        play_choice_five(arena)
        self.assertTrue(environment.is_terminal())
        expected_scores = {
            name: score if name in self.informed_players else score + 5
            for name, score in self.initial_scores.items()
        }
        self.assertEqual(environment.scores, expected_scores)
        public_result = environment.get_observation()[-1]
        self.assertEqual(public_result.msg_type, "scoreboard")
        self.assertEqual(json.loads(public_result.content), expected_scores)

        preview_in_memory = f"{OBSERVATION_TAG} " + PREVIEW.replace("\n", " ")
        scoreboard_in_memory = f"{OBSERVATION_TAG} {public_result.content}"
        for player in arena.players:
            with self.subTest(player=player.name):
                previews = [
                    message
                    for message in environment.get_observation(player.name)
                    if message.msg_type == "preview"
                ]
                memories = player.backend.memory.get_all_memories_as_text()
                self.assertIn(scoreboard_in_memory, memories)
                if player.name in self.informed_players:
                    self.assertEqual(len(previews), 1)
                    self.assertEqual(previews[0].visible_to, [player.name])
                    for option in ("공격", "방어", "상생", "견제", "가로수", "맨홀"):
                        self.assertIn(option, previews[0].content)
                    self.assertIn(preview_in_memory, memories)
                else:
                    self.assertEqual(previews, [])
                    self.assertNotIn(preview_in_memory, memories)

        with TemporaryDirectory() as directory:
            path = Path(directory) / "replay.json"
            arena.save_history(str(path))
            replay = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(
            [row["msg_type"] for row in replay],
            ["scoreboard", "choice_request", "scoreboard"],
        )
        self.assertEqual(json.loads(replay[-1]["content"]), expected_scores)

    def test_submission_order_does_not_change_result(self) -> None:
        forward = make_arena(self.initial_scores, self.choices)
        backward = make_arena(dict(reversed(self.initial_scores.items())), self.choices)
        play_choice_five(forward)
        play_choice_five(backward)
        self.assertEqual(forward.environment.scores, backward.environment.scores)
        for name in self.initial_scores:
            self.assertEqual(
                [message.content for message in forward.environment.get_observation(name)],
                [message.content for message in backward.environment.get_observation(name)],
            )

    def test_everyone_can_choose_information(self) -> None:
        choices = dict.fromkeys(self.initial_scores, INFORMATION)
        arena = make_arena(self.initial_scores, choices)
        initial_view = arena.environment.get_observation()
        play_choice_five(arena)
        self.assertEqual(arena.environment.scores, self.initial_scores)
        self.assertEqual(arena.environment.get_observation(), initial_view)
        for player in arena.players:
            self.assertEqual(
                arena.environment.get_observation(player.name)[-1].visible_to, [player.name]
            )

    def test_discussion_reaches_only_its_audience_and_influences_choices(self) -> None:
        arena = make_demo_arena()
        environment = arena.environment
        initial_scores = environment.scores
        for _ in range(10 * environment.num_players):
            arena.step()
        self.assertEqual(environment.scores, initial_scores)
        self.assertEqual(environment.get_next_player(), "P01")
        self.assertEqual(environment.get_observation()[-1].msg_type, "choice_request")

        play_choice_five(arena)
        self.assertTrue(environment.is_terminal())

        public = ("public", "P01", "각자 점수와 정보 중 무엇을 맡을지 정해요.")
        whispers = [
            ("whisper", "P02", "P03, 이번에는 네가 정보를 맡아줘."),
            ("whisper", "P03", "좋아. 내가 확인할게."),
            ("whisper", "P02", "고마워. 타일 순서에 영향을 주는 규칙이 있으면 알려줘."),
            ("whisper", "P03", "알겠어. 미리보기에서 그 부분부터 볼게."),
        ]
        room_chat = [
            ("room", "P04", "팀에서는 P05가 정보를 맡자."),
            ("room", "P05", "그럼 내가 정보를 고를게."),
        ]
        for player in arena.players:
            with self.subTest(player=player.name):
                expected_chat = [public]
                if player.name in {"P02", "P03"}:
                    expected_chat.extend(whispers)
                if player.name in {"P04", "P05", "P06"}:
                    expected_chat.extend(room_chat)
                view = environment.get_observation(player.name)
                self.assertEqual(
                    [
                        (message.msg_type, message.agent_name, message.content)
                        for message in view
                        if message.msg_type in CHANNEL_NAMES
                    ],
                    expected_chat,
                )
                memories = "\n".join(player.backend.memory.get_all_memories_as_text())
                self.assertIn(public[2], memories)
                for channel_messages in (whispers, room_chat):
                    for message in channel_messages:
                        self.assertEqual(message[2] in memories, message in expected_chat)

                chose_information = player.name in {"P03", "P05"}
                self.assertEqual(
                    any(message.msg_type == "preview" for message in view), chose_information
                )
                expected_delta = 0 if chose_information else 5
                self.assertEqual(
                    environment.scores[player.name] - initial_scores[player.name], expected_delta
                )

        with TemporaryDirectory() as directory:
            path = Path(directory) / "replay.json"
            arena.save_history(str(path))
            public_log = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(
            [row["msg_type"] for row in public_log],
            ["scoreboard", "discussion", "public", "room_move", "room_move", "room_move",
             "choice_request", "scoreboard"],
        )
        contents = [row["content"] for row in public_log]
        self.assertIn(public[2], contents)
        for message in whispers + room_chat:
            self.assertNotIn(message[2], contents)

    def test_discussion_rejects_invalid_recipients_and_wrong_phase(self) -> None:
        arena = make_arena(self.initial_scores, self.choices, discussion_rounds=1)
        environment = arena.environment
        initial_view = environment.get_observation()
        invalid_actions = (
            SCORE,
            '{"type":"speak","channel":"whisper","to":"P99","text":"hello"}',
            '{"type":"speak","channel":"whisper","to":"P01","text":"hello"}',
            '{"type":"speak","channel":"room","text":"hello"}',
            '{"type":"speak","channel":"public","text":" "}',
            '{"type":"move"}',
            '{"type":"move","room":3,"text":"hello"}',
            '{"type":"move_room","room":5}',
            '{"type":"move_room","room":true}',
            '{"type":"move_room","room":"1"}',
        )
        for action in invalid_actions:
            with self.subTest(action=action):
                self.assertFalse(environment.check_action(action, "P01"))
                with self.assertRaises(ValueError):
                    environment.step("P01", action)
        self.assertFalse(environment.check_action('{"type":"pass"}', "P02"))
        self.assertEqual(environment.get_next_player(), "P01")
        self.assertEqual(environment.get_observation(), initial_view)

    def test_pre_choice_brief_and_room_order(self) -> None:
        arena = make_arena(self.initial_scores, self.choices, discussion_rounds=1)
        game = arena.environment
        self.assertNotRegex(DISCUSSION_PROMPT, r'"room"\s*:\s*[1-4]')
        for offset, name in enumerate(game.player_names[:len(ROOMS)]):
            with self.subTest(player=name):
                request = game.get_observation(name)[-1]
                self.assertEqual(request.msg_type, "discussion_request")
                self.assertIn(CHOICE_REQUEST, request.content)
                self.assertNotIn(PREVIEW, request.content)
                order = ROOMS[offset:] + ROOMS[:offset]
                self.assertEqual(request.content.splitlines()[-len(ROOMS):], [
                    f"{room}번 논의실 비어 있음" for room in order
                ])
                self.assertTrue(game.check_action('{"type":"move_room","room":4}', name))
                game.step(name, '{"type":"pass"}')

    def test_whisper_requires_shared_location_and_stays_private(self) -> None:
        arena = make_arena(self.initial_scores, self.choices, discussion_rounds=2)
        environment = arena.environment
        for room, name in ((1, "P01"), (1, "P02"), (4, "P03"), (4, "P04")):
            environment.step(name, json.dumps({"type": "move_room", "room": room}))
        for name in environment.player_names[4:]:
            environment.step(name, '{"type":"pass"}')
        whisper = {"type": "speak", "channel": "whisper", "to": "P03", "text": "hello"}
        start = len(environment.match_events())
        self.assertFalse(environment.check_action(json.dumps(whisper), "P01"))
        with self.assertRaises(ValueError):
            environment.step("P01", json.dumps({**whisper, "room": 2}))
        self.assertEqual(environment.match_events(start), ())
        self.assertEqual(environment.get_next_player(), "P01")
        environment.step("P01", json.dumps({**whisper, "room": 4}))
        move, speech = environment.match_events(start)
        self.assertEqual((move.msg_type, move.content), ("room_move", "P01 → 4번 논의실"))
        self.assertEqual((speech.msg_type, speech.visible_to), ("whisper", ["P01", "P03"]))
        for name in environment.player_names:
            with self.subTest(player=name):
                view = environment.get_observation(name)
                self.assertEqual(any(m.msg_type == "whisper" for m in view), name in {"P01", "P03"})
        hall_whisper = {**whisper, "to": "P05", "room": 0}
        environment.step("P02", json.dumps(hall_whisper))
        self.assertEqual(environment.match_events()[-1].visible_to, ["P02", "P05"])
        self.assertIn("복도 P02 · P05", environment.get_observation("P03")[-1].content)
        self.assertTrue(environment.check_action(json.dumps({**whisper, "to": "P04"}), "P03"))

    def test_restoring_a_saved_cross_room_whisper_does_not_allow_a_new_one(self) -> None:
        game = make_arena(self.initial_scores, self.choices, discussion_rounds=1).environment
        game.step("P01", '{"type":"move","room":1}')
        saved = '{"type":"speak","channel":"whisper","to":"P01","text":"지난 기록"}'
        with game.discussion.restore_history():
            game.step("P02", saved)
        self.assertEqual(game.match_events()[-1].visible_to, ["P02", "P01"])
        self.assertFalse(game.check_action(saved, "P03"))
