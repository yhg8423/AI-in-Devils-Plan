import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from .spectator import case_catalog, find_matches, match_catalog, model_counts, next_match, read_match


class SpectatorLogTest(unittest.TestCase):
    def test_guest_model_is_separate_even_when_regular_players_use_the_same_model(self):
        players = [f"P{seat:02}" for seat in range(1, 8)] + ["G01"]
        for model in ("gpt-6.1-sol", "gpt-6-luna"):
            with self.subTest(model=model):
                groups = model_counts({"players": players, "model_players": players, "model": model,
                                       "effort": "low", "model_overrides": {
                                           "G01": {"model": "gpt-6.1-sol", "effort": "low"}}})
                self.assertEqual(groups, [
                    {"model": model, "effort": "low", "count": 7},
                    {"model": "gpt-6.1-sol", "effort": "low", "count": 1, "guest": True},
                ])

    def test_cases_keep_explicit_lineage_and_prefer_linked_model_records(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / "runs"

            def record(run_id, game, status="result", **header):
                log = root / run_id / "events.jsonl"
                log.parent.mkdir(parents=True, exist_ok=True)
                log.write_text(json.dumps({"type": "match", "game": game, **header}) + "\n" +
                               json.dumps({"type": status}) + "\n", encoding="utf-8")
                return log

            main, prison, market, roulette = ("1일차 메인 매치 · 양자택일", "1일차 감옥 매치 · 무거운 13",
                                             "2일차 메인 매치 · 미스터리 거래소", "2일차 감옥 매치 · 러시안 룰렛")
            one = record("matches/a/root", main, model="gpt-6-luna", effort="medium", provider="codex",
                         players=["P01", "P06"], model_players=["P01", "P06"], image_model="gpt-6.1-terra",
                         model_overrides={"P06": {"model": "gpt-6.1-sol", "effort": "low"}})
            two = record("matches/b/prison", prison, from_main=f"runs/{one.parent.relative_to(root)}/events.jsonl",
                         model="gpt-6-luna", effort="medium", players=["P01", "P02"], model_players=["P01"])
            three = record("matches/a/market", market, from_main=str(one), from_prison=str(two))
            record("matches/a/roulette", roulette, "interrupted", from_main=str(three))
            record("matches/a/short-branch", prison, from_main=str(one))
            other = record("matches/other", main, model="gpt-6.1-sol")
            record("matches/a/wrong-main", market, from_main=str(other), from_prison=str(two))
            record("matches/unfinished", main, "interrupted", model="gpt-6-luna")
            record("matches/demo", main)

            case, = case_catalog(root)
            self.assertEqual(case["id"], "matches/a/root")
            self.assertEqual(case["model"], "gpt-6-luna")
            self.assertEqual(case["model_overrides"], {"P06": {"model": "gpt-6.1-sol", "effort": "low"}})
            self.assertIsInstance(case["started_at"], int)
            self.assertEqual([(match["id"], match["game"], match["status"]) for match in case["matches"]], [
                ("matches/a/root", main, "complete"), ("matches/b/prison", prison, "complete"),
                ("matches/a/market", market, "complete"), ("matches/a/roulette", roulette, "interrupted"),
            ])
            main_match, prison_match, *_ = case["matches"]
            self.assertEqual(main_match["model_counts"], [
                {"model": "gpt-6-luna", "effort": "medium", "count": 1},
                {"model": "gpt-6.1-sol", "effort": "low", "count": 1},
            ])
            self.assertEqual(main_match["image_model"], "gpt-6.1-terra")
            self.assertEqual(prison_match["model_counts"], [
                {"model": "gpt-6-luna", "effort": "medium", "count": 1},
                {"model": None, "effort": None, "count": 1},
            ])
            self.assertNotIn("image_model", prison_match)

    def test_next_match_uses_the_immediate_source_in_linked_records(self):
        main = "matches/campaign/day1-main"
        prison = "matches/campaign/day1-prison"
        market = "matches/campaign/day2-main"
        standalone = "matches/day1-prison"
        prison_title = "1일차 감옥 매치 · 무거운 13"
        market_title = "2일차 메인 매치 · 미스터리 거래소"
        with TemporaryDirectory() as directory:
            root = Path(directory) / "runs"
            for run_id, header in (
                (main, {"game": "1일차 메인 매치 · 양자택일"}),
                (prison, {"game": prison_title, "from_main": f"runs/{main}/events.jsonl"}),
                (market, {"game": market_title, "from_main": f"runs/{main}/events.jsonl",
                          "from_prison": str(root / prison / "events.jsonl")}),
                (standalone, {"game": prison_title}),
            ):
                log = root / run_id / "events.jsonl"
                log.parent.mkdir(parents=True)
                log.write_text(json.dumps(header) + "\n", encoding="utf-8")

            logs = find_matches(root)
            self.assertEqual(next_match(root, logs, main), {"id": prison, "game": prison_title})
            self.assertEqual(next_match(root, logs, prison), {"id": market, "game": market_title})
            self.assertIsNone(next_match(root, logs, standalone))
            self.assertIsNone(next_match(root, logs, market))

    def test_case_counts_split_same_model_by_image_assignment(self):
        header = {"type": "match", "game": "1일차 메인 매치 · 양자택일", "model": "gpt-6-luna", "effort": "medium",
                  "players": ["P01", "P02", "P03"], "model_players": ["P01", "P02"],
                  "image_model": "gpt-6.1-sol", "image_model_overrides": {"P02": "gpt-6.1-terra"}}
        with TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "matches/day1-main/events.jsonl"
            log.parent.mkdir(parents=True)
            log.write_text(json.dumps(header) + '\n{"type": "result"}\n', encoding="utf-8")
            case, = case_catalog(root)
        match, = case["matches"]
        self.assertNotIn("image_model", match)
        self.assertEqual(match["model_counts"], [
            {"model": "gpt-6-luna", "effort": "medium", "count": 1, "image_model": "gpt-6.1-sol"},
            {"model": "gpt-6-luna", "effort": "medium", "count": 1, "image_model": "gpt-6.1-terra"},
            {"model": None, "effort": None, "count": 1},
        ])

    def test_catalog_reads_nested_campaign_headers_without_opening_event_rows(self):
        game = "1일차 메인 매치 · 양자택일"
        with TemporaryDirectory() as directory:
            root = Path(directory)
            runs = root / "matches"
            for run_id, content in (
                ("campaign/day1-main", json.dumps({"game": game, "model": "luna"}) + "\n{unfinished"),
                ("day1-main", json.dumps({"game": game}) + "\n"),
                ("pending/day1-main", json.dumps({"game": game})),
            ):
                log = runs / run_id / "events.jsonl"
                log.parent.mkdir(parents=True)
                log.write_text(content, encoding="utf-8")
            (runs / "alias").symlink_to(runs / "campaign", target_is_directory=True)
            self.assertEqual(set(find_matches(root)), {
                "matches/campaign/day1-main", "matches/day1-main", "matches/pending/day1-main",
            })
            self.assertEqual({row["id"]: (row["game"], row["has_model"]) for row in match_catalog(root)}, {
                "matches/campaign/day1-main": (game, True), "matches/day1-main": (game, False),
            })

    def test_discovers_both_formats_and_preserves_private_events(self):
        header = {"type": "match", "game": "2일차 메인 매치 · 미스터리 거래소", "seed": 1, "players": ["P01"]}
        event = {"type": "event", "msg_type": "preview", "agent_name": "System", "content": "단서", "visible_to": ["P01"]}
        result = {"type": "result", "ranking": ["P01"], "assets": {"P01": 100_000}, "eliminated": []}
        with TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "matches" / "day2-main" / "events.jsonl"
            log.parent.mkdir(parents=True)
            log.write_text("".join(json.dumps(row) + "\n" for row in (header, event, result)), encoding="utf-8")
            grass = root / "luna" / "events.jsonl"
            grass.parent.mkdir()
            grass.touch()
            (root / "alias").symlink_to(log.parent, target_is_directory=True)
            self.assertEqual(find_matches(root), {"matches/day2-main": log, "luna": grass})
            replay = read_match(log)
        self.assertEqual(replay["format"], "match")
        self.assertEqual(replay["game"], header["game"])
        self.assertTrue(replay["complete"])
        first, last = [step["events"][0] for step in replay["steps"]]
        self.assertEqual(first["visible_to"], ["P01"])
        self.assertEqual(last["visible_to"], "all")
        self.assertEqual(json.loads(last["content"]), result)

    def test_partial_live_row_is_only_visible_after_write_completes(self):
        header = {
            "type": "match", "model": "mock", "initial_scores": {"P01": 0},
            "priority": {"P01": 0}, "discussion_rounds": 1,
        }
        note = {
            "msg_type": "discussion_note", "agent_name": "P01",
            "content": "다음 라운드에 협상한다.", "visible_to": ["P01"],
        }
        row = json.dumps({
            "type": "step", "phase": "before_choice", "round": 1, "player": "P01",
            "action": "원본 모델 출력", "events": [note],
        }, ensure_ascii=False).encode()
        with TemporaryDirectory() as directory:
            log = Path(directory) / "events.jsonl"
            with log.open("wb", buffering=0) as writer:
                writer.write(json.dumps(header).encode() + b"\n")
                writer.write(row[:-10])
                self.assertEqual(read_match(log)["steps"], [])
                writer.write(row[-10:] + b"\n")
                steps = read_match(log)["steps"]
        self.assertEqual(steps, [{
            "phase": "before_choice", "round": 1, "player": "P01", "events": [note],
        }])

    def test_english_translation_is_optional_and_preserves_the_original_events(self):
        header = {"type": "match", "game": "1일차 메인 매치 · 양자택일", "seed": 1, "players": ["P01", "P02"]}
        whisper = {"type": "event", "turn": 41, "msg_type": "whisper", "agent_name": "P01",
                   "content": "함께 할까요?", "visible_to": ["P01", "P02"]}
        note = {"type": "event", "msg_type": "decision_note", "agent_name": "P01",
                "content": json.dumps({"phase": "choice_1", "note": "점수를 고른다."}), "visible_to": ["P01"]}
        with TemporaryDirectory() as directory:
            log = Path(directory) / "events.jsonl"
            text = "".join(json.dumps(row) + "\n" for row in [header, whisper, note])
            log.write_text(text)
            korean = read_match(log)
            self.assertEqual(read_match(log, language="en"), korean)
            sidecar = log.with_name("events.en.jsonl")
            sidecar.write_text('{"turn":41,"text":"Shall we work together?"}\n'
                               '{"turn":1,"fields":{"note":"I will choose points."}}\n'
                               '{"turn":1,"text":"An incomplete')
            english = read_match(log, language="en")
            first, second = (step["events"][0] for step in english["steps"])
            self.assertEqual(first["translation"], {"text": "Shall we work together?"})
            self.assertEqual(second["translation"], {"fields": {"note": "I will choose points."}})
            for original, event in zip(korean["steps"], (first, second), strict=True):
                self.assertEqual({key: value for key, value in event.items() if key != "translation"},
                                 original["events"][0])
            self.assertEqual(read_match(log), korean)
            self.assertEqual(log.read_text(), text)
            sidecar.write_text('{"turn":41,"text":"Would you like to team up?"}\n')
            self.assertNotEqual(read_match(log, language="en")["translation_version"], english["translation_version"])

    def test_standalone_grass_translation_uses_event_ordinals(self):
        header = {
            "type": "match", "model": "mock", "initial_scores": {"P01": 0},
            "priority": {"P01": 0}, "discussion_rounds": 1,
        }
        events = [
            {"turn": 3, "msg_type": "rules", "agent_name": "System", "content": "규칙", "visible_to": "all"},
            {"turn": 3, "msg_type": "discussion_note", "agent_name": "P01", "content": "전략", "visible_to": ["P01"]},
            {"turn": 3, "msg_type": "public", "agent_name": "P01", "content": "대화", "visible_to": "all"},
        ]
        step = {"type": "step", "phase": "before_choice", "round": 1, "player": "P01", "events": events}
        with TemporaryDirectory() as directory:
            log = Path(directory) / "events.jsonl"
            log.write_text(json.dumps(header) + "\n" + json.dumps(step) + "\n")
            log.with_name("events.en.jsonl").write_text('{"turn":0,"text":"Rules"}\n'
                                                        '{"turn":1,"text":"Strategy"}\n'
                                                        '{"turn":2,"text":"Conversation"}\n')
            shown = read_match(log, language="en")["steps"][0]["events"]
        self.assertEqual([event["translation"]["text"] for event in shown], ["Strategy", "Conversation"])
