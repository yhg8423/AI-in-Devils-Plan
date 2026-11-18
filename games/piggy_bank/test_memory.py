"""Memory slots must constrain the model's real input, including relationship reviews."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from ..match import Decision, Match
from ..models import CodexLanguageModel
from .memory import MEMORY_SUMMARY_LIMIT, PiggyMemory, parse_memory_selection, parse_memory_summary, parse_memory_update


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

    def test_free_summary_accepts_five_banks_strategy_and_forgetting_without_truth_correction(self):
        text = "1번 흑77, 2번 백9, 3번 불명, 4번 흑4, 5번 백5. 확신 없으면 의심하지 않는다."
        self.assertEqual(parse_memory_summary(text), text)
        self.assertEqual(parse_memory_summary(""), "")
        self.assertEqual(parse_memory_summary("가" * MEMORY_SUMMARY_LIMIT), "가" * MEMORY_SUMMARY_LIMIT)
        for invalid in (None, True, 123, {}, "가" * (MEMORY_SUMMARY_LIMIT + 1)):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                parse_memory_summary(invalid)
        banks = {bank: {"black": 991, "white": 993} for bank in range(1, 6)}
        memory = PiggyMemory(PLAYERS, banks, mode="summary")
        memory.update("P01", text, 1, 12)
        banks[1] = {"black": 1991, "white": 1993}
        self.assertEqual(memory.recall("P01"), {"reset": 0, "mode": "summary", "updated_turn": 1,
                                               "text": text, "limit": MEMORY_SUMMARY_LIMIT})
        del banks[1]
        banks[6] = {"black": 991, "white": 993}
        memory.replace(1, 6)
        self.assertEqual(memory.recall("P01")["text"], text)
        banks.clear()
        banks.update({bank: {"black": 1, "white": 1} for bank in range(1, 6)})
        memory.reset(1, turn=4)
        self.assertEqual(memory.recall("P01")["text"], text, "A public reset must be interpreted by the model, not rewrite its summary")
        self.assertEqual(memory.through["P01"], 12)
        self.assertEqual(memory.recall("P01")["reset"], 1)
        memory.update("P01", "리셋됐다. 예전 수량은 잊고 신중히 의심한다.", 4, 30)
        self.assertNotIn("77", memory.recall("P01")["text"])
        memory.update("P01", "", 5, 40)
        self.assertEqual(memory.recall("P01")["text"], "")

    def test_real_model_summary_bounds_history_and_keeps_wrong_or_omitted_facts(self):
        prompts = []
        wrong = "1번 흑77. 2·3·4·5번은 불확실하다. 확신 없으면 의심하지 않는다."
        forgotten = "구체적인 수량은 기억나지 않는다. 다음 공개 행동을 신중히 본다."

        def complete(prompt):
            prompts.append(prompt)
            if "비공개 관계 평가를 갱신하세요" in prompt:
                action = "{}"
            elif "UPDATE_SUMMARY_A" in prompt:
                action = wrong
            elif "BROKEN_SUMMARY" in prompt:
                action = "가" * (MEMORY_SUMMARY_LIMIT + 1)
            elif "UPDATE_SUMMARY_B" in prompt:
                action = forgotten
            else:
                action = "pass"
            return json.dumps({"action": action, "note": "OLD_SIDE_NOTE94717"})

        with TemporaryDirectory() as directory:
            model = CodexLanguageModel("test-model", Path(directory))
            ratings = {"P01": {"P02": {"affinity": 60, "trust": 65, "reason": "OLD_REASON94729"}}}
            match = Match(PLAYERS, 23, models={"P01": model}, live_turns=12, relationships=ratings)
            banks = {bank: {"black": 94601, "white": 94603} for bank in range(1, 6)}
            memory = PiggyMemory(PLAYERS, banks, mode="summary")
            memory.update("P02", "OTHER_PRIVATE94761", 0, 0)
            match.model_observations = memory
            lower = {name: bank for bank, name in enumerate(PLAYERS, 1)}
            upper = {name: 5 if name == "P01" else None for name in PLAYERS}
            state = {"lower": lower, "upper": upper, "scores": dict.fromkeys(PLAYERS, 0)}
            match.event("rules", "돼지 저금통 비공개 기억 요약 검증")
            match.event("pig_setup", {"order": list(PLAYERS), **state})
            match.event("discussion_note", "INITIAL_PLAN94701", actor="P01", private=["P01"])
            match.event("public", "OLD_ADVICE94723", actor="P02")

            def valid_update(answer):
                try:
                    parse_memory_summary(answer)
                except ValueError:
                    return False
                return True

            def update(marker, turn):
                response = match.decide_together("pig_memory_update", {
                    "P01": Decision(marker, memory.recall("P01")["text"], valid=valid_update),
                })["P01"]
                memory.update("P01", response, turn, len(match.events))

            with patch.object(model, "_complete", side_effect=complete):
                update("UPDATE_SUMMARY_A", 0)
                self.assertIn("INITIAL_PLAN94701", prompts[-1])
                self.assertIn("OLD_ADVICE94723", prompts[-1])
                memory_start = len(prompts)
                match.event("pig_turn", {"turn": 1, "player": "P02", "color": "black", **state})
                banks[1]["black"] += 1
                match.event("pig_deposit", {"turn": 1, "player": "P02", "to": "P01", "bank": 1,
                                            "black": 1, "white": 0, **state})
                match.event("pig_contents", {"banks": banks}, private=["__operator__"])
                match.event("pig_recall", memory.recall("P02"), actor="P02", private=["P02"])
                match.event("public", "CURRENT_ADVICE94741", actor="P02")
                match.event("pig_pass", {"turn": 1, "player": "P01", "bank": 1, "color": "black", "count": 94971})
                match.decide("P01", "test_summary", "현재 기억으로 판단하세요.", "pass", options=("pass",))
                self.assertIn(wrong, prompts[-1])
                self.assertIn("CURRENT_ADVICE94741", prompts[-1])
                update("BROKEN_SUMMARY", 1)
                self.assertIn("CURRENT_ADVICE94741", prompts[-1])
                self.assertIn("94971", prompts[-1], "The summary update must see the turn's outcome")
                self.assertEqual(memory.recall("P01")["text"], wrong, "Invalid updates retain the previous summary without consulting true counts")
                match.event("public", "NEW_COMPRESSION_FACT94743", actor="P02")
                update("UPDATE_SUMMARY_B", 1)
                self.assertIn("NEW_COMPRESSION_FACT94743", prompts[-1])
                forgotten_start = len(prompts)
                match.event("public", "AFTER_COMPRESSION94745", actor="P02")
                match.decide("P01", "test_summary", "현재 기억으로 판단하세요.", "pass", options=("pass",))
                self.assertIn(forgotten, prompts[-1])
                self.assertNotIn("77", prompts[-1])
                self.assertNotIn("CURRENT_ADVICE94741", prompts[-1])
                self.assertNotIn("NEW_COMPRESSION_FACT94743", prompts[-1])
                match.review_relationships("압축 후 새 대화")
            for prompt in prompts[forgotten_start:]:
                self.assertNotIn("CURRENT_ADVICE94741", prompt)
                self.assertNotIn("NEW_COMPRESSION_FACT94743", prompt)
            for prompt in prompts[memory_start:]:
                for token in ("94701", "94723", "94717"):
                    self.assertNotIn(token, prompt, "An expired initial plan, transcript, or side note must not bypass the summary")
            for prompt in prompts:
                for token in ("94601", "94603", "94761", "94729"):
                    self.assertNotIn(token, prompt, "True counts, another player's summary, and rating reasons must stay private")

    def test_dynamic_slots_accept_any_three_live_ids_without_restoring_dropped_counts(self):
        banks = {bank: {"black": 991, "white": 993} for bank in range(1, 6)}
        first = {"1": {"black": 77, "white": None}, "2": {"black": 2222, "white": 2223}, "3": {"black": 3333, "white": 3334}}
        changed = {"1": first["1"], "4": {"black": None, "white": None}, "5": {"black": 5, "white": None}}
        self.assertEqual(parse_memory_update(json.dumps(changed), banks), changed)
        for invalid in ({"1": first["1"]}, {**changed, "2": first["2"]}, {**changed, "6": changed["4"]},
                        {"01": first["1"], "4": changed["4"], "5": changed["5"]},
                        {**changed, "4": {"black": True, "white": None}},
                        {**changed, "4": {"black": -1, "white": None}},
                        {**changed, "4": {"black": 1.5, "white": None}},
                        {**changed, "4": {"black": 1}},
                        {**changed, "4": {"black": 1, "white": None, "note": "extra"}}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                parse_memory_update(json.dumps(invalid), banks)
        memory = PiggyMemory(PLAYERS, banks, mode="dynamic")
        memory.reset(0)
        self.assertEqual(memory.recall("P01")["banks"], {str(bank): {"black": 1, "white": 1} for bank in (1, 2, 3)})
        memory.update("P01", first, 1, 12)
        banks[1]["black"] += 1000
        self.assertEqual(memory.recall("P01")["banks"]["1"], first["1"], "Later true counts must not repair an incorrect belief")
        memory.update("P01", changed, 2, 24)
        self.assertEqual(memory.recall("P01")["banks"], changed)
        returned = {"1": first["1"], "2": {"black": None, "white": None}, "3": {"black": None, "white": None}}
        memory.update("P01", returned, 3, 36)
        self.assertEqual(memory.recall("P01")["banks"], returned)
        self.assertNotIn("2222", json.dumps(memory.recall("P01")))
        del banks[2]
        banks[6] = {"black": 991, "white": 993}
        memory.replace(2, 6)
        self.assertEqual(memory.selections["P01"], [1, 6, 3])
        self.assertEqual(memory.recall("P01")["banks"]["6"], {"black": 1, "white": 1})
        banks.clear()
        banks.update({bank: {"black": 1, "white": 1} for bank in range(1, 6)})
        memory.reset(1, turn=4)
        self.assertEqual(memory.recall("P01"), {"reset": 1, "mode": "dynamic", "updated_turn": 4,
                                               "banks": {str(bank): {"black": 1, "white": 1} for bank in (1, 2, 3)}})

    def test_real_model_rebinding_cannot_recover_dropped_slots_from_cache_or_truth(self):
        prompts = []
        first = {"1": {"black": 77, "white": None}, "2": {"black": 2222, "white": 2223}, "3": {"black": 3333, "white": 3334}}
        changed = {"1": first["1"], "4": {"black": None, "white": None}, "5": {"black": 5, "white": None}}
        returned = {"1": first["1"], "2": {"black": None, "white": None}, "3": {"black": None, "white": None}}

        def complete(prompt):
            prompts.append(prompt)
            if "REBIND_145" in prompt:
                action = json.dumps(changed)
            elif "REBIND_123" in prompt:
                action = json.dumps(returned)
            else:
                action = "pass"
            return json.dumps({"action": action, "note": "PRIVATE_SIDE_NOTE94717"})

        with TemporaryDirectory() as directory:
            model = CodexLanguageModel("test-model", Path(directory))
            ratings = {"P01": {"P02": {"affinity": 60, "trust": 65, "reason": "OLD_REASON94729"}}}
            match = Match(PLAYERS, 23, models={"P01": model}, live_turns=10, relationships=ratings)
            banks = {bank: {"black": 94601, "white": 94603} for bank in range(1, 6)}
            memory = PiggyMemory(PLAYERS, banks, mode="dynamic")
            memory.reset(0)
            match.model_observations = memory
            lower = {name: bank for bank, name in enumerate(PLAYERS, 1)}
            upper = {name: 5 if name == "P01" else None for name in PLAYERS}
            state = {"lower": lower, "upper": upper, "scores": dict.fromkeys(PLAYERS, 0)}
            match.event("rules", "돼지 저금통 동적 기억 슬롯 검증")
            match.event("pig_setup", {"order": list(PLAYERS), **state})
            match.event("discussion_note", "INITIAL_PLAN94701", actor="P01", private=["P01"])
            match.event("action", {"phase": "pig_count", "action": "OLD_DROPPED94719 · 2222 · 3333"}, actor="P01", private=["P01"])
            memory.update("P01", first, 0, len(match.events))
            memory.update("P02", {str(bank): {"black": 94761, "white": 94763} for bank in (1, 4, 5)}, 0, len(match.events))

            def valid_update(answer):
                try:
                    parse_memory_update(answer, banks)
                except ValueError:
                    return False
                return True

            def update(marker, turn):
                response = match.decide_together("pig_memory_update", {
                    "P01": Decision(marker, json.dumps(memory.recall("P01")["banks"]), valid=valid_update),
                })["P01"]
                memory.update("P01", json.loads(response), turn, len(match.events))

            with patch.object(model, "_complete", side_effect=complete):
                match.decide("P01", "test_dynamic", "현재 기억으로 판단하세요.", "pass", options=("pass",))
                self.assertIn("2222", prompts[-1], "The old slot value is initially in the backend's real input")
                update("REBIND_145", 1)
                memory_start = len(prompts)
                banks[1]["black"] += 5
                match.event("pig_contents", {"banks": banks}, private=["__operator__"])
                match.event("pig_recall", memory.recall("P02"), actor="P02", private=["P02"])
                match.event("public", "CURRENT_PUBLIC_ADVICE94741", actor="P02")
                match.decide("P01", "test_dynamic", "현재 기억으로 판단하세요.", "pass", options=("pass",))
                self.assertIn('"4":{"black":null,"white":null}', prompts[-1].replace(" ", ""))
                self.assertIn('"1":{"black":77,"white":null}', prompts[-1].replace(" ", ""))
                update("REBIND_123", 2)
                self.assertEqual(memory.recall("P01")["banks"], returned)
                update("INVALID_REBIND", 3)
                self.assertEqual(memory.recall("P01")["banks"], returned, "An invalid reply must retain the same three beliefs")
                match.event("public", "AFTER_REBIND94743", actor="P02")
                match.decide("P01", "test_dynamic", "현재 기억으로 판단하세요.", "pass", options=("pass",))
                self.assertIn('"2":{"black":null,"white":null}', prompts[-1].replace(" ", ""))
                match.review_relationships("슬롯 변경 후 새 대화")
            for prompt in prompts[memory_start:]:
                for token in ("2222", "2223", "3333", "3334", "94701", "94719", "94717"):
                    self.assertNotIn(token, prompt, "Dropped slot values must not return through a discarded transcript or cached backend")
            for prompt in prompts:
                for token in ("94601", "94603", "94761", "94763", "94729"):
                    self.assertNotIn(token, prompt, "Rebinding must not consult true counts, other players, or old rating reasons")

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
