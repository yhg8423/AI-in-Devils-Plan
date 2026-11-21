"""Serve a local, read-only spectator view of recorded and ongoing matches."""

import argparse
from collections import Counter
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
from threading import Lock
from urllib.parse import parse_qs, urlsplit

from games.either_or.lay_the_grass.board import PARK_ROWS
from games.exile_match.roster import (
    collect_exile_players, collect_second_exile_players, collect_third_exile_players, collect_fourth_exile_players,
    collect_fifth_exile_players,
)
from games.match import FIRST_EXILE, SECOND_EXILE, THIRD_EXILE, FOURTH_EXILE, FIFTH_EXILE


UI = Path(__file__).with_name("ui")
PLAY_RESULTS = UI.parent.parent / "play_results"
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.css": ("dist/app.css", "text/css; charset=utf-8"),
    "/app.js": ("dist/app.js", "text/javascript; charset=utf-8"),
    "/Galmuri11-Bold.woff2": ("dist/Galmuri11-Bold.woff2", "font/woff2"),
    "/favicon.ico": ("assets/favicon.ico", "image/x-icon"),
    "/og-image.jpg": ("assets/og-image.jpg", "image/jpeg"),
}
EVENT_TYPES = {
    "scoreboard", "room_move", "public", "room", "whisper", "grass_plan", "discussion_note", "decision_note",
    "room_invite", "room_invite_response",
    "grass_tile", "grass_choices", "grass_obstacle", "grass_placement", "grass_bonus",
}
EVENT_FIELDS = ("msg_type", "agent_name", "content", "visible_to")
CASE_STAGES = ("1일차 메인 매치", "1일차 감옥 매치", "2일차 메인 매치", "2일차 감옥 매치", "3일차 메인 매치", "3일차 감옥 매치", "4일차 메인 매치", "4일차 감옥 매치")
EXILE_GAMES = (FIRST_EXILE, SECOND_EXILE, THIRD_EXILE, FOURTH_EXILE, FIFTH_EXILE)


def find_matches(root: Path) -> dict[str, Path]:
    logs = []
    if root.is_symlink():
        return {}
    for pattern in ("*/events.jsonl", "matches/*/events.jsonl", "matches/*/*/events.jsonl"):
        for log in root.glob(pattern):
            if any(path.is_symlink() for path in (log, *log.parents) if path != root and root in path.parents):
                continue
            try:
                if log.is_file():
                    logs.append((log.stat().st_mtime_ns, log))
            except FileNotFoundError:
                continue
    return {log.parent.relative_to(root).as_posix(): log for _, log in sorted(logs, reverse=True)}


def read_match_header(log: Path) -> dict | None:
    try:
        with log.open("rb") as stream:
            line = stream.readline()
        header = json.loads(line) if line.endswith(b"\n") else None
    except (OSError, ValueError):
        return None
    if isinstance(header, dict) and isinstance(header.get("game"), str):
        header["game"] = header["game"].replace("달라진 그림 찾기", "틀린 그림 찾기")
        return header
    return None


def match_catalog(root: Path) -> list[dict]:
    return [
        {"id": run_id, "game": header["game"], "has_model": bool(header.get("model"))}
        for run_id, log in find_matches(root).items()
        if (header := read_match_header(log)) is not None
    ]


def match_status(log: Path) -> str:
    try:
        with log.open("rb") as stream:
            end = stream.seek(0, 2)
            tail = b""
            while end:
                start = max(0, end - 4096)
                stream.seek(start)
                tail = stream.read(end - start) + tail
                # Exclude a partial first row and the unfinished last row.
                rows = tail.split(b"\n")[int(start > 0):-1]
                if row := next((line for line in reversed(rows) if line.strip()), None):
                    event = json.loads(row)
                    if isinstance(event, dict):
                        if event.get("type") == "result":
                            return "complete"
                        if event.get("type") == "interrupted":
                            return "interrupted"
                    break
                end = start
    except (OSError, ValueError):
        pass
    return "in_progress"


def source_paths(root: Path, previous: object) -> tuple[Path, ...]:
    if not isinstance(previous, str) or not previous:
        return ()
    source = Path(previous)
    try:
        return source.resolve(), (root.parent / source).resolve(), (root / source).resolve()
    except (OSError, RuntimeError, ValueError):
        return ()


def exile_sources(root: Path, header: dict, logs, *, previous_exile: Path | None = None) -> list[Path]:
    """Validate an exile roster against its campaign and optional predecessor."""
    header = {**header, "game": str(header.get("game", "")).replace("달라진 그림 찾기", "틀린 그림 찾기")}
    if header.get("game") not in EXILE_GAMES or any(key in header for key in ("from_main", "from_prison")):
        raise ValueError("Expected an exile match with from_matches source links.")
    links = header.get("from_matches")
    if not isinstance(links, list) or not links:
        raise ValueError("An exile match needs a from_matches source prefix.")
    available = {path.resolve() for path in logs}
    sources = []
    for link in links:
        path = next((path for path in source_paths(root, link) if path in available), None)
        if path is None:
            raise ValueError("Exile sources must point to this campaign's recorded matches.")
        sources.append(path)
    if any(match_status(path) != "complete" for path in sources):
        raise ValueError("Exile sources must be completed matches.")
    if header["game"] == FIRST_EXILE:
        if "from_exile" in header:
            raise ValueError("The first exile match cannot have a previous exile match.")
        players = collect_exile_players(sources)
    else:
        if (previous_exile is None or previous_exile.resolve() not in source_paths(root, header.get("from_exile"))):
            raise ValueError("The exile match must point to this campaign's preceding exile match.")
        collectors = {SECOND_EXILE: collect_second_exile_players, THIRD_EXILE: collect_third_exile_players,
                      FOURTH_EXILE: collect_fourth_exile_players, FIFTH_EXILE: collect_fifth_exile_players}
        players = collectors[header["game"]](previous_exile, sources)
    if header.get("players") != players:
        raise ValueError("The exile roster must match the campaign's entrants and survivors in source order.")
    return sources


def model_counts(header: dict) -> list[dict]:
    roster = header.get("players")
    default = (header.get("model"), header.get("effort"))
    enabled = header.get("model_players")
    if default[0] and enabled is None:
        return [{"model": default[0], "effort": default[1], "count": None}]
    players = set(enabled or ()) if default[0] else set()
    overrides = header.get("model_overrides") or {}
    provider = header.get("provider") if any(config.get("provider") for config in overrides.values()) else None
    image_overrides = header.get("image_model_overrides") or {}
    counts = Counter({(provider, *default, None, False): 0})
    for player in roster or enabled or ():
        guest = player == "G01"
        if player not in players:
            counts[None, None, None, None, guest] += 1
            continue
        override = overrides.get(player)
        model, effort = (override["model"], override.get("effort")) if override else default
        player_provider = override.get("provider", provider) if override else provider
        default_image = header.get("image_model") if player_provider == provider else None
        image_model = image_overrides.get(player, default_image) if image_overrides or provider else None
        counts[player_provider, model, effort, image_model if image_model != model else None, guest] += 1
    return [{"model": model, "effort": effort, "count": count,
             **({"provider": player_provider} if player_provider else {}),
             **({"image_model": image_model} if image_model else {}),
             **({"guest": True} if guest else {})}
            for (player_provider, model, effort, image_model, guest), count in counts.items() if count]


def case_catalog(root: Path) -> list[dict]:
    records = {}
    exile_records = {}
    for run_id, log in find_matches(root).items():
        header = read_match_header(log)
        if header is None:
            continue
        if header["game"] in EXILE_GAMES:
            destination = exile_records
        elif header["game"].split(" · ", 1)[0] in CASE_STAGES:
            destination = records
        else:
            continue
        try:
            stat = log.stat()
            started_at = int(getattr(stat, "st_birthtime", stat.st_mtime) * 1000)
            destination[run_id] = (log.resolve(), header, started_at, match_status(log))
        except (OSError, RuntimeError, ValueError):
            continue

    by_path = {path: run_id for run_id, (path, _, _, _) in records.items()}
    children: dict[str, list[str]] = {}
    earlier_main: dict[str, str | None] = {}

    def source_run(source: object) -> str | None:
        return next((by_path[path] for path in source_paths(root, source) if path in by_path), None)

    for run_id, (_, header, _, _) in records.items():
        main = source_run(header.get("from_main"))
        if header["game"].split(" · ", 1)[0] in CASE_STAGES[2::2]:
            earlier_main[run_id] = main
            parent = source_run(header.get("from_prison"))
        else:
            parent = main
        if parent is not None:
            children.setdefault(parent, []).append(run_id)

    def summary(run_id, header, status):
        counts = model_counts(header)
        match = {"id": run_id, "game": header["game"], "status": status,
                 "model_counts": counts}
        image_model = header.get("image_model")
        if (image_model and image_model != header.get("model") and not header.get("image_model_overrides")
                and not any(group.get("provider") for group in counts)):
            match["image_model"] = image_model
        return match

    def chain(run_id: str, stage: int, previous: str | None = None) -> list[dict]:
        _, header, _, status = records[run_id]
        match = summary(run_id, header, status)
        path = [match]
        if stage == len(CASE_STAGES) - 1 or status != "complete":
            return path
        next_stage = CASE_STAGES[stage + 1]
        branches = (chain(child, stage + 1, run_id) for child in children.get(run_id, [])
                    if records[child][1]["game"].split(" · ", 1)[0] == next_stage
                    and (stage % 2 == 0 or earlier_main.get(child) == previous))
        path.extend(max(branches, key=lambda branch: (len(branch), sum(match["status"] == "complete" for match in branch)),
                        default=[]))
        return path

    cases = []
    for run_id, (_, header, started_at, status) in sorted(records.items(), key=lambda item: item[1][2], reverse=True):
        if header["game"].split(" · ", 1)[0] != CASE_STAGES[0] or status != "complete":
            continue
        model = header.get("model") if header.get("model_players") != [] else None
        cases.append({
            "id": run_id, "started_at": started_at, "matches": chain(run_id, 0), "model": model,
            **{key: header[key] for key in ("provider", "effort", "image_model", "model_overrides") if header.get(key)},
        })
    exile_paths = {record[0] for record in exile_records.values()}
    for run_id, (_, header, _, status) in exile_records.items():
        try:
            previous = next((path for path in source_paths(root, header.get("from_exile")) if path in exile_paths), None)
            sources = exile_sources(root, header, by_path, previous_exile=previous)
            source_ids = [by_path[path] for path in sources]
            case = next((case for case in cases
                         if [match["id"] for match in case["matches"][:len(source_ids)]] == source_ids), None)
            if case is not None:
                case.setdefault("exile_matches", []).append(summary(run_id, header, status))
        except (OSError, RuntimeError, ValueError, KeyError, TypeError):
            continue
    for case in cases:
        if "exile_matches" in case:
            case["exile_matches"].sort(key=lambda match: EXILE_GAMES.index(match["game"]))
    real = [case for case in cases if case["model"]]
    linked = [case for case in real if len(case["matches"]) > 1]
    return linked or real or cases


def next_match(root: Path, logs: dict[str, Path], run_id: str) -> dict | None:
    current = logs[run_id].resolve()
    current_header = read_match_header(current)
    if current_header and current_header["game"] in EXILE_GAMES:
        stage = EXILE_GAMES.index(current_header["game"])
        if stage + 1 == len(EXILE_GAMES):
            return None
        for candidate, log in logs.items():
            header = read_match_header(log)
            if not header or header["game"] != EXILE_GAMES[stage + 1]:
                continue
            try:
                exile_sources(root, header, logs.values(), previous_exile=current)
            except (OSError, RuntimeError, ValueError, KeyError, TypeError):
                continue
            return {"id": candidate, "game": header["game"]}
        return None
    for candidate, log in logs.items():
        if candidate == run_id or (header := read_match_header(log)) is None:
            continue
        if header["game"] in EXILE_GAMES:
            continue
        # A main match after a prison match records both sources. Continue from the prison match.
        previous = header.get("from_prison") or header.get("from_main")
        if current in source_paths(root, previous):
            return {"id": candidate, "game": header["game"]}
    return None


def read_translations(log: Path) -> tuple[dict, str | None]:
    path = log.with_name("events.en.jsonl")
    if path.is_symlink():
        return {}, None
    try:
        data = path.read_bytes()
    except OSError:
        return {}, None
    translations = {}
    for line in data.split(b"\n")[:-1]:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict) or type(row.get("turn")) is not int:
            continue
        text = row.get("text")
        fields = row.get("fields")
        if isinstance(text, str) and text:
            translations[row["turn"]] = {"text": text}
        elif isinstance(fields, dict) and fields:
            translations[row["turn"]] = {"fields": fields}
    return translations, sha256(data).hexdigest() if translations else None


def read_match(log: Path, *, language: str = "ko") -> dict:
    # The writer appends newline-terminated rows. Leave an in-flight row for the next poll.
    rows = [json.loads(line) for line in log.read_bytes().split(b"\n")[:-1] if line.strip()]
    if not rows:
        return {"steps": []}
    header = rows[0]
    full_match = "game" in header
    translations, version = read_translations(log) if language == "en" else ({}, None)
    translated = {"translation_version": version} if version else {}

    def event_payload(event: dict, turn: int) -> dict:
        payload = {key: event[key] for key in EVENT_FIELDS}
        if full_match and type(event.get("turn")) is int:
            turn = event["turn"]
        if turn in translations:
            payload["translation"] = translations[turn]
        return payload

    if full_match:
        steps = [
            {"events": [event_payload(row, index)]}
            for index, row in enumerate(row for row in rows[1:] if row["type"] == "event")
        ]
        last = rows[-1]
        complete = last["type"] == "result"
        interrupted = last["type"] == "interrupted"
        if complete or interrupted:
            steps.append({"events": [{
                "msg_type": "match_result" if complete else "match_interrupted", "agent_name": "System",
                "content": json.dumps(last, ensure_ascii=False) if complete else "중단되기 전까지의 기록입니다.",
                "visible_to": "all",
            }]})
        return {
            "format": "match", "game": header["game"], "players": header["players"],
            "model": header.get("model"), "effort": header.get("effort"), "provider": header.get("provider"),
            "seed": header["seed"],
            "model_players": header.get("model_players"),
            "model_overrides": header.get("model_overrides"),
            "image_model": header.get("image_model"),
            "image_model_overrides": header.get("image_model_overrides"),
            "image_effort_overrides": header.get("image_effort_overrides"),
            "board": PARK_ROWS if header["game"].endswith(" · 양자택일") else None,
            "complete": complete, "interrupted": interrupted, "model_calls": last.get("model_calls"), "steps": steps,
            **translated,
        }
    steps = []
    turn = 0
    for row in rows[1:]:
        if row["type"] != "step":
            continue
        events = []
        for event in row["events"]:
            if event["msg_type"] in EVENT_TYPES:
                events.append(event_payload(event, turn))
            turn += 1
        steps.append({"phase": row["phase"], "round": row["round"], "player": row["player"], "events": events})
    return {
        "format": "grass",
        "model": header["model"],
        "scores": header["initial_scores"],
        "priority": header["priority"],
        "rounds": header["discussion_rounds"],
        "board": PARK_ROWS,
        "complete": rows[-1]["type"] == "result",
        "steps": steps,
        **translated,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="데블스 플랜 플레이 관전과 다시 보기")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    asset_lock = Lock()
    built_sources = None

    def rebuild_ui() -> None:
        nonlocal built_sources
        sources = {}
        for directory, subdirectories, files in UI.walk():
            subdirectories[:] = [name for name in subdirectories if name not in {"dist", "node_modules"}
                                 and not name.startswith(".")]
            for name in files:
                if not name.startswith("."):
                    path = directory / name
                    sources[path] = path.stat().st_mtime_ns
        if sources == built_sources and all((UI / asset).is_file() for asset, _ in ASSETS.values()):
            return
        subprocess.run(["npm", "run", "build"], cwd=UI, check=True, timeout=30, stdout=subprocess.DEVNULL)
        built_sources = sources

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}":
                self.send_error(403)
                return
            url = urlsplit(self.path)
            try:
                if url.path in ASSETS:
                    name, mime = ASSETS[url.path]
                    with asset_lock:
                        if url.path == "/":
                            try:
                                rebuild_ui()
                            except (OSError, subprocess.SubprocessError) as error:
                                print(f"웹 빌드 실패: {error}", file=sys.stderr)
                                self.send_error(500, "Could not build the web interface",
                                                "Check the server terminal, fix the build error, and refresh.")
                                return
                        body = (UI / name).read_bytes()
                    self.respond(body, mime)
                elif url.path == "/api/runs":
                    self.respond_json(list(find_matches(PLAY_RESULTS)))
                elif url.path == "/api/catalog":
                    self.respond_json(match_catalog(PLAY_RESULTS))
                elif url.path == "/api/cases":
                    self.respond_json(case_catalog(PLAY_RESULTS))
                elif url.path == "/api/match":
                    query = parse_qs(url.query)
                    name = query.get("run", [""])[0]
                    logs = find_matches(PLAY_RESULTS)
                    log = logs.get(name)
                    if log is None:
                        self.send_error(404)
                        return
                    match = read_match(log, language=query.get("lang", ["ko"])[0])
                    if match.get("format") == "match" and match["complete"]:
                        match["next_match"] = next_match(PLAY_RESULTS, logs, name)
                    self.respond_json(match)
                else:
                    self.send_error(404)
            except FileNotFoundError:
                self.send_error(404)
            except (json.JSONDecodeError, KeyError, TypeError):
                self.send_error(422, "Could not read the match log")

        def respond_json(self, data: object) -> None:
            self.respond(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode(), "application/json")

        def respond(self, body: bytes, mime: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store" if mime == "application/json" else "no-cache")
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; object-src 'none'")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args) -> None:
            pass  # Polls would otherwise bury the startup URL.

    with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as server:
        print(f"데블스 플랜 웹  http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
