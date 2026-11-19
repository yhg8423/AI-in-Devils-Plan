"""Create English replay text alongside Korean match logs."""

import argparse
from contextlib import closing
from itertools import batched
import json
from pathlib import Path
import re
import sqlite3
import subprocess
from tempfile import NamedTemporaryFile, TemporaryDirectory

from .spectator import find_matches


HANGUL = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣ]")
MASKED_CLUE = re.compile(r"([□▧]+)")
ROOM_INVITE = re.compile(r"^초대 #(\d+) · ([1-4])번\s*(?:논의실|룸) · (.*)$", re.S)
ROOM_MOVE = re.compile(r"^([PG]\d+ → )(?:(\d+)번\s*(?:논의실|룸)|복도)$")
GLOSSARY = {
    "성과금": "Bonus", "보험금": "Insurance", "개인": "Solo", "팀": "Team",
    "공공": "Public", "헌신": "Devotion", "양보": "Concession", "점수": "Points",
    "정보": "Information", "공격": "Attack", "방어": "Defense", "상생": "Cooperate",
    "견제": "Compete", "가로수": "Tree", "맨홀": "Manhole", "지목": "Nomination",
    "패스": "Pass", "빨강": "Red", "초록": "Green", "파랑": "Blue", "레인보우": "Rainbow",
    "수락": "Accepted", "거절": "Declined",
    "비공개 행동을 했습니다.": "Took a private action.",
}
GAME_TERMS = {
    "네모 세기": "Rectangle Counting", "큐브 세기": "Cube Counting",
    "잔디 깔기": "Lay the Grass", "기억 포커": "Memory Poker",
    "연맹의 징표": "Alliance Token", "생활동": "Living Quarters", "감옥동": "Prison Wing",
    "피스": "Piece", "맛소금융": "Matso Finance", "무조건설": "Mujo Construction",
    "방어제철": "Bangeo Steel", "알트엔터": "Alt Entertainment", "열림보안": "Yeollim Security",
    "코요테크": "Koyo Tech", "후자전자": "Huja Electronics",
    "돼지 저금통": "Piggy Bank",
    "경매 빙고": "Auction Bingo",
}
TERM_PATTERN = re.compile("|".join(map(re.escape, GAME_TERMS)))
PLAYER_ID = re.compile(r"(?i)\b([pg])([0-9]{2})(?![0-9])")


def source_events(snapshot: bytes):
    """Yield source indexes independently of the replay visibility filter."""
    index = 0
    for line in snapshot.split(b"\n")[:-1]:
        if not line.strip():
            continue
        row = json.loads(line)
        if row["type"] == "event":
            turn = row.get("turn")
            yield turn if type(turn) is int else index, row
            index += 1
        elif row["type"] == "step":
            for event in row["events"]:
                yield index, event
                index += 1


def convert_text(text, translate):
    if not HANGUL.search(text):
        return text
    if text in GLOSSARY:
        return GLOSSARY[text]
    if text.lstrip().startswith(("{", "[")):
        try:
            structured = json.loads(text)
        except ValueError:
            pass
        else:
            return json.dumps(convert_value(structured, translate), ensure_ascii=False, separators=(",", ":"))
    # Keep line boundaries, so rules retain headings and paragraphs.
    if "\n" in text:
        return "\n".join(convert_text(line, translate) for line in text.split("\n"))
    # Letter-by-letter clues keep the exact hidden and next-reveal markers.
    if MASKED_CLUE.search(text):
        return "".join(part.replace(part.strip(), convert_text(part.strip(), translate), 1)
                       if HANGUL.search(part) else part for part in MASKED_CLUE.split(text))
    if invite := ROOM_INVITE.match(text):
        return f"Invite #{invite[1]} · Room {invite[2]} · {convert_text(invite[3], translate)}"
    if move := ROOM_MOVE.fullmatch(text):
        return move[1] + ("Hallway" if move[2] is None else f"Room {move[2]}")
    return translate(text)


def convert_value(value, translate):
    if isinstance(value, str):
        return convert_text(value, translate)
    if isinstance(value, list):
        return [convert_value(item, translate) for item in value]
    if isinstance(value, dict):
        return {key: convert_value(item, translate) for key, item in value.items()}
    return value


def translation_rows(snapshot, translate):
    for turn, event in source_events(snapshot):
        content = event["content"]
        if not HANGUL.search(content):
            continue
        try:
            data = json.loads(content)
        except ValueError:
            data = None
        if isinstance(data, dict):
            fields = {key: translated for key, value in data.items()
                      if (translated := convert_value(value, translate)) != value}
            if fields:
                yield {"turn": turn, "fields": fields}
        else:
            translated = convert_text(content, translate)
            if translated != content:
                yield {"turn": turn, "text": translated}


def translate_batch(process, texts):
    prepared = [TERM_PATTERN.sub(lambda term: GAME_TERMS[term[0]], text) for text in texts]
    process.stdin.write(json.dumps(prepared, ensure_ascii=False) + "\n")
    process.stdin.flush()
    response = process.stdout.readline()
    if not response:
        raise RuntimeError("Translator exited before returning the batch.")
    translations = json.loads(response)
    if (not isinstance(translations, list) or len(translations) != len(texts)
            or any(not isinstance(text, str) or not text.strip() for text in translations)):
        raise RuntimeError("Translator must return a nonempty string for each input, in order.")
    return [PLAYER_ID.sub(lambda match: match[1].upper() + match[2], text) for text in translations]


def translate_logs(root, logs, command, batch_size):
    with closing(sqlite3.connect(root / ".translation-ko-en.sqlite3")) as cache:
        cache.execute("CREATE TABLE IF NOT EXISTS translations (source TEXT PRIMARY KEY, target TEXT NOT NULL)")
        translations = dict(cache.execute("SELECT source, target FROM translations"))
        process = None
        try:
            for log in logs:
                snapshot = log.read_bytes()
                needed = {}

                def collect(text):
                    if text not in translations:
                        needed[text] = None
                    return text

                for _ in translation_rows(snapshot, collect):
                    pass
                if needed and process is None:
                    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                               text=True, encoding="utf-8")
                for texts in batched(needed, batch_size):
                    translated = list(zip(texts, translate_batch(process, texts), strict=True))
                    with cache:
                        cache.executemany("INSERT OR REPLACE INTO translations VALUES (?, ?)", translated)
                    translations.update(translated)
                output = log.with_name("events.en.jsonl")
                with NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent, delete=False) as temp:
                    pending = Path(temp.name)
                    try:
                        for row in translation_rows(snapshot, translations.__getitem__):
                            temp.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
                    except BaseException:
                        pending.unlink(missing_ok=True)
                        raise
                pending.replace(output)
                print(f"{output} · {len(needed)} newly translated passages", flush=True)
        finally:
            if process is not None:
                try:
                    process.stdin.close()
                finally:
                    process.stdout.close()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="*", type=Path, help="events.jsonl files (default: all logs under --runs)")
    parser.add_argument("--runs", type=Path, default=Path("runs"), help="replay directory and translation cache")
    parser.add_argument("--translator", type=Path, help="executable reading and writing JSON arrays, one per line")
    parser.add_argument("--batch-size", type=int, default=128)
    args = parser.parse_args()
    logs = args.logs or list(find_matches(args.runs).values())
    if not logs or any(path.name != "events.jsonl" or not path.is_file() for path in logs):
        parser.error("Specify existing events.jsonl files or a --runs directory containing replay logs.")
    if args.batch_size < 1:
        parser.error("--batch-size must be positive.")
    args.runs.mkdir(parents=True, exist_ok=True)
    try:
        with TemporaryDirectory(prefix="devils-translate-") as work:
            if args.translator is None:
                executable = Path(work) / "translate_ko_en"
                source = Path(__file__).with_name("translate_ko_en.swift")
                subprocess.run(["swiftc", "-parse-as-library", "-module-cache-path", work,
                                str(source), "-o", str(executable)], check=True)
            else:
                executable = args.translator.resolve()
            translate_logs(args.runs, logs, [str(executable)], args.batch_size)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"{error}\n")
    except KeyboardInterrupt:
        parser.exit(130, "Translation stopped. Saved batches will be reused on the next run.\n")


if __name__ == "__main__":
    main()
