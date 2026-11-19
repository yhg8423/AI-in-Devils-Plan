"""Export selected, completed runs for public replay, including private in-game events."""

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from .spectator import CASE_STAGES, EVENT_FIELDS, source_paths
from .translate_events import translation_rows


STAGES = ("day1-main", "day1-prison", "day2-main", "day2-prison", "day3-main", "day3-prison")
PREDECESSORS = (
    {},
    {"from_main": 0},
    {"from_main": 0, "from_prison": 1},
    {"from_main": 2},
    {"from_main": 2, "from_prison": 3},
    {"from_main": 4},
)
HEADER_FIELDS = (
    "type", "game", "players", "seed", "pieces", "model", "effort", "provider",
    "model_players", "model_overrides", "image_model", "image_model_overrides", "image_effort_overrides",
    "allow_review", "model_turn_limit",
)
RESULT_FIELDS = (
    "type", "ranking", "scores", "priority", "grass_placements", "alliance_saved",
    "living", "prison", "eliminated", "pieces", "prize_token", "penalties",
    "pieces_awarded", "assets", "rounds", "credits", "seats", "survivors", "model_calls",
    "raw_scores", "manitos", "pieces_spent", "turns", "resets",
    "turn_limit", "end_reason", "main_turns", "tiebreaks",
)


def decode_rows(path):
    if path.is_symlink():
        raise ValueError(f"{path}: symbolic links are not supported")
    snapshot = path.read_bytes()
    if snapshot and not snapshot.endswith(b"\n"):
        raise ValueError(f"{path}: incomplete JSONL row")
    rows = [json.loads(line) for line in snapshot.split(b"\n") if line.strip()]
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"{path}: expected JSON objects")
    return snapshot, rows


def prepare_match(log, game, predecessors, logs, source_root, campaign):
    snapshot, rows = decode_rows(log)
    if len(rows) < 2 or rows[0].get("type") != "match" or rows[-1].get("type") != "result":
        raise ValueError(f"{log}: expected a completed full match")
    header, *events, result = rows
    title = header.get("game")
    if not isinstance(title, str) or title.split(" · ", 1)[0] != game:
        raise ValueError(f"{log}: unexpected match stage")
    if not isinstance(header.get("players"), list) or "seed" not in header:
        raise ValueError(f"{log}: missing replay header fields")
    header_out = {field: header[field] for field in HEADER_FIELDS if field in header}
    for key in ("from_main", "from_prison"):
        if key not in predecessors:
            if key in header:
                raise ValueError(f"{log}: unexpected {key} link")
            continue
        prior = predecessors[key]
        if logs[prior].resolve() not in source_paths(source_root, header.get(key)):
            raise ValueError(f"{log}: {key} must point to this run's {STAGES[prior]}")
        header_out[key] = f"matches/{campaign}/{STAGES[prior]}/events.jsonl"

    event_rows = []
    turns = set()
    for index, event in enumerate(events):
        if event.get("type") != "event" or any(field not in event for field in EVENT_FIELDS):
            raise ValueError(f"{log}: invalid replay event")
        turn = event.get("turn")
        turn = turn if type(turn) is int else index
        if turn in turns:
            raise ValueError(f"{log}: duplicate replay event turn {turn}")
        turns.add(turn)
        event_rows.append({"type": "event", "turn": turn, **{field: event[field] for field in EVENT_FIELDS}})

    required = {row["turn"] for row in translation_rows(snapshot, lambda text: text + " (EN)")}
    sidecar = log.with_name("events.en.jsonl")
    _, translated_rows = decode_rows(sidecar)
    translated_turns = set()
    for row in translated_rows:
        turn = row.get("turn")
        text, fields = row.get("text"), row.get("fields")
        is_text = set(row) == {"turn", "text"} and isinstance(text, str) and text.strip()
        is_fields = set(row) == {"turn", "fields"} and isinstance(fields, dict) and fields
        if type(turn) is not int or turn not in turns or turn in translated_turns or not (is_text or is_fields):
            raise ValueError(f"{sidecar}: invalid translation at turn {turn}")
        translated_turns.add(turn)
    if missing := required - translated_turns:
        raise ValueError(f"{sidecar}: {len(missing)} replay events are missing translations")

    result_out = {field: result[field] for field in RESULT_FIELDS if field in result}
    return [header_out, *event_rows, result_out], translated_rows


def encode_rows(rows):
    return "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows)


def export_replays(campaigns, source_root, output_root):
    source_root = source_root.resolve()
    destination_root = output_root / "matches"
    prepared = {}
    for campaign in campaigns:
        if campaign.is_symlink() or campaign.resolve().parent != source_root / "matches":
            raise ValueError(f"{campaign}: select a campaign under {source_root / 'matches'}")
        destination = destination_root / campaign.name
        if destination in prepared or destination.exists() or destination.is_symlink():
            raise FileExistsError(f"{destination}: export would overwrite an existing campaign")
        logs = [campaign / stage / "events.jsonl" for stage in STAGES]
        if any(log.parent.is_symlink() for log in logs):
            raise ValueError(f"{campaign}: symbolic links are not supported")
        while len(logs) > 4 and not logs[-1].is_symlink() and not logs[-1].exists():
            logs.pop()
        prepared[destination] = [
            prepare_match(log, game, links, logs, source_root, campaign.name)
            for log, game, links in zip(logs, CASE_STAGES[:len(logs)], PREDECESSORS[:len(logs)], strict=True)
        ]

    destination_root.mkdir(parents=True, exist_ok=True)
    for destination, matches in prepared.items():
        with TemporaryDirectory(dir=destination_root, prefix=".export-") as temp:
            stage_root = Path(temp)
            for stage, (events, translated) in zip(STAGES[:len(matches)], matches, strict=True):
                path = stage_root / stage
                path.mkdir()
                (path / "events.jsonl").write_text(encode_rows(events), encoding="utf-8")
                (path / "events.en.jsonl").write_text(encode_rows(translated), encoding="utf-8")
            destination.mkdir()
            try:
                stage_root.rename(destination)
            except OSError:
                destination.rmdir()
                raise
    return list(prepared)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaigns", nargs="+", type=Path, metavar="CAMPAIGN",
                        help="completed campaign directory under runs/matches")
    parser.add_argument("--source-root", type=Path, default=Path("runs"))
    parser.add_argument("--output-root", type=Path, default=Path("play_results"))
    args = parser.parse_args()
    try:
        for path in export_replays(args.campaigns, args.source_root, args.output_root):
            print(path)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
