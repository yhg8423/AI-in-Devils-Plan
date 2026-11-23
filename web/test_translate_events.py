import json
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
import unittest

from games.mystery_stock_market.game import STOCK_RULES, stock_hint

from .spectator import read_match
from .translate_events import convert_text, translate_logs


class TranslateEventsTests(unittest.TestCase):
    def test_market_clue_translation_preserves_public_and_private_reveals(self):
        huja_rule = STOCK_RULES[-1]
        steel_rule = STOCK_RULES[2]

        def unexpected_translation(text):
            self.fail(f"Known market clue was sent to the translator: {text}")

        early = convert_text(stock_hint(huja_rule, 15), unexpected_translation)
        self.assertIn("total holdings", early)
        self.assertIn("▧", early)
        self.assertNotIn("10 shares", early)
        self.assertNotIn("30 shares", early)
        final = convert_text(stock_hint(huja_rule, 20), unexpected_translation)
        self.assertIn("at least 10 shares and at most 30 shares", final)
        self.assertNotRegex(final, "[□▧]")
        preview = convert_text(f"후자전자 · {stock_hint(huja_rule, 15)}", unexpected_translation)
        self.assertEqual(preview, f"Huja Electronics · {early}")

        steel = convert_text(stock_hint(steel_rule, 20), unexpected_translation)
        self.assertIn("increase: −₩200 per share added", steel)
        self.assertIn("Decrease: +₩200 per share removed", steel)

    def test_translates_only_event_content_and_reuses_cached_text(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "events.jsonl"

            def event(kind, content, turn):
                return {"type": "event", "agent_name": "P01", "msg_type": kind,
                        "visible_to": ["P01"], "content": content, "turn": turn}

            rows = [
                {"type": "match", "game": "양자택일", "players": ["P01"], "seed": 1},
                event("room_invite", "초대 #2 · 1번 논의실 · 같이 하자", 0),
                event("hints", json.dumps({"알트엔터": "□□ 같이 하자 ▧ □"}, ensure_ascii=False), 1),
                event("relationship_update", json.dumps({"ratings": {"P02": {"trust": 50, "reason": "같이 하자"}}},
                                                       ensure_ascii=False), 2),
                event("room_move", "G01 → 2번 논의실", 3),
            ]
            original = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows) + '{"type": "event"'
            log.write_text(original, encoding="utf-8")
            backend = ["-c", "import json, sys\nfor line in sys.stdin:\n"
                       " print(json.dumps(['Let’s work together' for text in json.loads(line)]), flush=True)"]
            translate_logs(root, [log], [sys.executable, *backend], 8)
            self.assertEqual(log.read_text(encoding="utf-8"), original)
            output = log.with_name("events.en.jsonl")
            translations = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(translations, [
                {"turn": 0, "text": "Invite #2 · Room 1 · Let’s work together"},
                {"turn": 1, "fields": {"알트엔터": "□□ Let’s work together ▧ □"}},
                {"turn": 2, "fields": {"ratings": {"P02": {"trust": 50, "reason": "Let’s work together"}}}},
                {"turn": 3, "text": "G01 → Room 2"},
            ])
            with sqlite3.connect(root / ".translation-ko-en.sqlite3") as cache:
                self.assertEqual(cache.execute("SELECT count(*) FROM translations").fetchone(), (1,))
            translate_logs(root, [log], ["unavailable-translator"], 8)
            match = read_match(log, language="en")
            self.assertEqual(match["steps"][0]["events"][0]["translation"]["text"], translations[0]["text"])
            self.assertEqual(match["steps"][0]["events"][0]["visible_to"], ["P01"])
