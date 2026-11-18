"""Memory slots must constrain the model's real input, including relationship reviews."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from ..match import Match
from ..models import CodexLanguageModel
from .memory import PiggyMemory, parse_memory_selection


PLAYERS = ("P01", "P02", "P03", "P04")


class PiggyMemoryTest(unittest.TestCase):
    def test_selection_requires_three_distinct_current_bank_ids(self):
        self.assertEqual(parse_memory_selection("[5,1,3]", range(1, 6)), [1, 3, 5])
        for answer in ("[1,2]", "[1,2,3,4]", "[1,1,2]", "[true,2,3]", "[1,2,6]", '["1",2,3]', "{}"):
            with self.subTest(answer=answer), self.assertRaises(ValueError):
                parse_memory_selection(answer, range(1, 6))

    def test_only_selected_counts_follow_updates_replacements_and_reset_epochs(self):
        banks = {bank: {"black": bank + 10, "white": bank + 20} for bank in range(1, 6)}
        memory = PiggyMemory(PLAYERS, banks)
        memory.select("P01", [1, 2, 3])
        memory.select("P02", [3, 4, 5])
        banks[1]["black"] += 4
        banks[4]["black"] += 99
        self.assertEqual(memory.recall("P01")["banks"], {str(bank): banks[bank] for bank in (1, 2, 3)})
        del banks[4]
        banks[6] = {"black": 1, "white": 1}
        memory.replace(4, 6)
        self.assertEqual(set(memory.recall("P01")["banks"]), {"1", "2", "3"})
        self.assertEqual(set(memory.recall("P02")["banks"]), {"3", "5", "6"})
        del banks[1]
        banks[7] = {"black": 1, "white": 1}
        memory.replace(1, 7)
        self.assertEqual(memory.recall("P01")["banks"], {str(bank): banks[bank] for bank in (2, 3, 7)})
        self.assertEqual(memory.recall("P01")["banks"]["7"], {"black": 1, "white": 1})
        banks.clear()
        banks.update({bank: {"black": 1, "white": 1} for bank in range(1, 6)})
        memory.reset(1)
        self.assertEqual(memory.recall("P01"), {"reset": 1, "banks": {}})
        self.assertEqual(memory.recall("P02")["banks"], {})
        memory.select("P01", [1, 4, 5])
        self.assertEqual(memory.recall("P01")["banks"], {str(bank): {"black": 1, "white": 1} for bank in (1, 4, 5)})

    def test_action_and_relationship_prompts_cannot_recover_expired_unselected_counts(self):
        prompts = []

        def complete(prompt):
            prompts.append(prompt)
            if "비공개 관계 평가를 갱신하세요" in prompt:
                return json.dumps({"action": "{}", "note": ""})
            return json.dumps({"action": "pass", "note": "OLD_NOTE94717"})

        with TemporaryDirectory() as directory:
            model = CodexLanguageModel("test-model", Path(directory))
            ratings = {"P01": {"P02": {"affinity": 60, "trust": 65, "reason": "OLD_REASON94729"}}}
            match = Match(PLAYERS, 23, models={"P01": model}, live_turns=12, relationships=ratings)
            banks = {bank: {"black": 1, "white": 1} for bank in range(1, 6)}
            banks[4] = {"black": 94747, "white": 94753}
            memory = PiggyMemory(PLAYERS, banks)
            memory.select("P01", [1, 2, 3])
            match.model_observations = memory
            lower = {name: bank for bank, name in enumerate(PLAYERS, 1)}
            upper = {name: 5 if name == "P01" else None for name in PLAYERS}
            state = {"lower": lower, "upper": upper, "scores": dict.fromkeys(PLAYERS, 0)}
            match.event("rules", "돼지 저금통 기억 슬롯 검증")
            match.event("pig_setup", {"order": list(PLAYERS), **state})
            match.event("pig_turn", {"turn": 1, "player": "P01", "color": "black", **state})
            match.event("pig_recall", memory.recall("P01"), actor="P01", private=["P01"])
            match.event("pig_memory_selection", {"reset": 0, "banks": [3, 4, 5], "note": "OTHER_SELECTION94761"},
                        actor="P02", private=["P02"])
            match.event("pig_contents", {"banks": banks}, private=["__operator__"])
            match.event("pig_deposit", {"turn": 1, "player": "P02", "to": "P01", "bank": 4,
                                        "black": 94711, "white": 94713, **state})
            match.event("public", "OLD_ADVICE94723 · 94711 · 94713", actor="P02")
            with patch.object(model, "_complete", side_effect=complete):
                match.decide("P01", "test_memory", "지금 볼 수 있는 정보로 판단하세요.", "pass", options=("pass",))
                self.assertIn("OLD_ADVICE94723", prompts[-1])
                match.event("action", {"phase": "pig_count", "action": "OLD_ACTION94719"}, actor="P01", private=["P01"])
                match.event("discussion_note", "OLD_STRATEGY94737", actor="P01", private=["P01"])
                match.event("pig_turn", {"turn": 2, "player": "P02", "color": "white", **state})
                match.event("public", "CURRENT_ADVICE94741", actor="P02")
                match.decide("P01", "test_memory", "새 차례에서 판단하세요.", "pass", options=("pass",))
                self.assertIn("CURRENT_ADVICE94741", prompts[-1])
                match.review_relationships("새 차례 대화 완료")
            self.assertTrue(any("비공개 관계 평가를 갱신하세요" in prompt for prompt in prompts[1:]))
            for prompt in prompts:
                if "비공개 관계 평가를 갱신하세요" not in prompt:
                    self.assertIn("별도 메모·기록장·장부·누적 카운터를 작성하거나 조회할 수 없으며", prompt)
                    self.assertIn("'기록했다'고 말해도 기억 슬롯 밖의 수량이 다음 턴에 보존되지 않습니다", prompt)
                    self.assertIn("동전을 추가하겠다는 계획은 실제로 추가·전달되기 전까지", prompt)
                for token in ("94729", "94747", "94753", "94761"):
                    self.assertNotIn(token, prompt, f"Private token {token} leaked into a model input")
            for prompt in prompts[1:]:
                for token in ("94711", "94713", "94717", "94719", "94723", "94737"):
                    self.assertNotIn(token, prompt, f"Expired/private token {token} leaked into a fresh model input")
            self.assertEqual(match.relationships["P01"]["P02"]["reason"], "OLD_REASON94729")
            self.assertIs(match.backends["P01"].relationships, match.relationships["P01"])


if __name__ == "__main__":
    unittest.main()
