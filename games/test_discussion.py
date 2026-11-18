"""Group whisper privacy, location validation, and replay checks."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from chatarena.message import Message

from .either_or.discussion import Discussion, format_speech
from .match import Match, run_cli
from .models import OpenAILanguageModel
from .resume_legacy import LegacyDecisions


class GroupWhisperTest(unittest.TestCase):
    players = ("P01", "P02", "P03", "P04", "P05")

    def record(self, discussion, player, payload, *, notes=False):
        decision = discussion.parse(player, json.dumps(payload), 0, notes=notes)
        return discussion.record(player, decision, 0)

    def test_hallway_groups_and_single_recipient_remain_compatible(self):
        discussion = Discussion(self.players, 1)
        for target in ("P02", ["P02"], ["P03", "P02"]):
            with self.subTest(target=target):
                events = self.record(discussion, "P01", {
                    "type": "speak", "channel": "whisper", "to": target, "text": "함께 확인하자.",
                })
                recipients = [target] if isinstance(target, str) else target
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0].msg_type, "whisper")
                self.assertEqual(events[0].visible_to, ["P01", *recipients])
                self.assertIn("P01 → " + ", ".join(recipients), format_speech(events[0]))

    def test_room_group_reaches_only_named_players_and_their_model_prompts(self):
        prompts = []
        client = Mock()

        def respond(**kwargs):
            prompt = kwargs["input"][0]["content"][0]["text"]
            prompts.append(prompt)
            action = "{}" if "비공개 관계 평가를 갱신하세요" in prompt else "대기"
            return SimpleNamespace(status="completed", output_text=json.dumps({"action": action}), usage=None)

        client.responses.create.side_effect = respond
        model = OpenAILanguageModel("test-model", client)
        match = Match(self.players, 1, model=model, live_players=self.players, live_turns=20)
        discussion = Discussion(self.players, 1)
        for player in self.players[1:4]:
            for event in self.record(discussion, player, {"type": "move", "room": 2}):
                match.event(event.msg_type, event.content, actor=event.agent_name)
        secret = "P02와 P03에게만 전달한 교환 제안"
        events = self.record(discussion, "P01", {
            "type": "speak", "channel": "whisper", "to": ["P02", "P03"], "room": 2,
            "text": secret, "note": "선택한 두 사람의 응답을 기다린다.",
        }, notes=True)
        self.assertEqual([event.msg_type for event in events], ["room_move", "whisper", "discussion_note"])
        self.assertEqual(discussion.location("P01"), 2)
        self.assertEqual(events[1].visible_to, ["P01", "P02", "P03"])
        self.assertEqual(events[2].visible_to, ["P01"])
        for event in events:
            match.event(event.msg_type, event.content, actor=event.agent_name,
                        private=() if event.visible_to == "all" else event.visible_to)
        for player in self.players:
            with self.subTest(player=player):
                receives = player in {"P01", "P02", "P03"}
                self.assertEqual(any(event.content == secret for event in match.observations(player)), receives)
                match.decide(player, "test", "확인한 제안에 따라 행동하세요.", "대기", options=("대기",))
                self.assertEqual(secret in prompts[-1], receives)
        match.review_relationships("그룹 대화 종료")
        reviews = [prompt for prompt in prompts if "비공개 관계 평가를 갱신하세요" in prompt]
        self.assertEqual(len(reviews), len(self.players))
        for player in self.players:
            prompt = next(prompt for prompt in reviews if f"Exercise: {player}의" in prompt)
            self.assertEqual(secret in prompt, player in {"P01", "P02", "P03"})

    def test_invalid_groups_cannot_move_sender_or_broaden_invitations(self):
        discussion = Discussion(self.players, 1)
        self.record(discussion, "P02", {"type": "move", "room": 2})
        self.record(discussion, "P03", {"type": "move", "room": 3})
        invalid_targets = ([], ["P02", "P02"], ["P01"], ["P99"], ["P02", 2], ["P02", None],
                           ["P02", []], ["P02", {}], None, 2, {}, True, "", ["P02", "P03"])
        for target in invalid_targets:
            with self.subTest(target=target):
                with self.assertRaises(ValueError):
                    self.record(discussion, "P01", {
                        "type": "speak", "channel": "whisper", "to": target, "room": 2,
                        "text": "이 메시지는 전달되면 안 된다.", "note": "이 메모도 전달되면 안 된다.",
                    }, notes=True)
                self.assertEqual(discussion.location("P01"), 0)
                self.assertEqual(discussion.location("P02"), 2)
                self.assertEqual(discussion.location("P03"), 3)
        with self.assertRaises(ValueError):
            self.record(discussion, "P01", {
                "type": "speak", "channel": "room_invite", "to": ["P02", "P03"], "room": 2, "text": "초대",
            })
        invite = self.record(discussion, "P01", {
            "type": "speak", "channel": "room_invite", "to": "P02", "room": 2, "text": "초대",
        })
        self.assertEqual(invite[-1].visible_to, ["P01", "P02"])
        saved = {"type": "speak", "channel": "whisper", "to": "P03", "text": "이전 교차 장소 기록"}
        with discussion.restore_history():
            restored = self.record(discussion, "P01", saved)
        self.assertEqual(restored[0].visible_to, ["P01", "P03"])
        with self.assertRaises(ValueError):
            self.record(discussion, "P01", saved)

    def test_legacy_recovery_keeps_all_group_recipients_and_single_recipient_shape(self):
        for recipients in (["P01", "P02"], ["P01", "P03", "P02"]):
            with self.subTest(recipients=recipients):
                events = [
                    asdict(Message("P01", "P01 → 2번 논의실", turn=0, msg_type="room_move")),
                    asdict(Message("P01", "공동 제안", turn=1, msg_type="whisper", visible_to=recipients)),
                    asdict(Message("P01", "선택한 상대에게만 전달한다.", turn=2,
                                   msg_type="discussion_note", visible_to=["P01"])),
                ]
                response, _ = LegacyDecisions(events).query("P01", "choice_2_negotiation", 0)
                action = json.loads(response)
                expected = recipients[1] if len(recipients) == 2 else recipients[1:]
                self.assertEqual(action["to"], expected)
                self.assertEqual(action["room"], 2)
                self.assertEqual(action["note"], "선택한 상대에게만 전달한다.")

    def test_interrupted_group_whisper_replays_without_duplicate_model_calls(self):
        original_event = Match.event

        def respond(prompt):
            if "비공개 관계 평가를 갱신하세요" in prompt:
                return json.dumps({"action": "{}"})
            stage = 2 if "그룹 발언 2" in prompt.rsplit("Exercise:", 1)[-1] else 1
            action = {"type": "speak", "channel": "whisper", "to": ["P02", "P03"],
                      "text": f"그룹 제안 {stage}", "note": "두 상대의 응답을 기다린다."}
            return json.dumps({"action": json.dumps(action, ensure_ascii=False)})

        def play(match):
            discussion = Discussion(match.players, 2)
            for stage in (1, 2):
                def valid(action):
                    try:
                        discussion.parse("P01", action, len(match.events), notes=True)
                    except (ValueError, TypeError):
                        return False
                    return True

                action = match.request_action("P01", "group_talk", f"그룹 발언 {stage}",
                                              '{"type":"pass","note":"대기"}', valid=valid)
                for event in self.record(discussion, "P01", json.loads(action), notes=True):
                    match.event(event.msg_type, event.content, actor=event.agent_name,
                                private=() if event.visible_to == "all" else event.visible_to)
            return {"ended": True}

        def interrupt(match, kind, data, **kwargs):
            original_event(match, kind, data, **kwargs)
            if kind == "whisper":
                raise RuntimeError("interrupted after group whisper")

        with (TemporaryDirectory() as directory, redirect_stdout(StringIO()), redirect_stderr(StringIO()),
              patch("games.models.CodexLanguageModel._complete", side_effect=respond) as completion):
            full = Path(directory) / "full.jsonl"
            resumed = Path(directory) / "resumed.jsonl"
            arguments = ["--model", "test-model", "--model-player", "P01", "--model-turns", "10"]
            run_cli(play, title="그룹 귓속말 재개", seats=4, argv=[*arguments, "--output", str(full)])
            with patch.object(Match, "event", interrupt):
                with self.assertRaisesRegex(RuntimeError, "after group whisper"):
                    run_cli(play, title="그룹 귓속말 재개", seats=4, argv=[*arguments, "--output", str(resumed)])
            prefix = [json.loads(line) for line in resumed.read_text().splitlines()]
            calls_before = completion.call_count
            run_cli(play, title="그룹 귓속말 재개", seats=4, argv=["--resume", "--output", str(resumed)])
            expected = [json.loads(line) for line in full.read_text().splitlines()]
            actual = [json.loads(line) for line in resumed.read_text().splitlines()]
            self.assertEqual(actual, expected)
            self.assertEqual(actual[:len(prefix) - 1], prefix[:-1])
            self.assertEqual(completion.call_count - calls_before,
                             expected[-1]["model_calls"] - prefix[-1]["model_calls"])
            whispers = [row for row in actual if row.get("msg_type") == "whisper"]
            self.assertEqual([row["visible_to"] for row in whispers], [["P01", "P02", "P03"]] * 2)


if __name__ == "__main__":
    unittest.main()
