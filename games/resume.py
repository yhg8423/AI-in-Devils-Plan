"""Persist model decisions separately from the events shown by the spectator."""

from collections.abc import Callable
from contextlib import ExitStack
import fcntl
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import BinaryIO, TypeVar


_T = TypeVar("_T")
_EVENT_FIELDS = ("agent_name", "content", "turn", "visible_to", "msg_type")


class ResumeError(ValueError):
    """This log cannot safely be resumed."""


def _line(row: object) -> bytes:
    return (json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def _rows(stream: BinaryIO):
    """Read committed rows and their offsets, ignoring the unwritten tail."""
    while True:
        start = stream.tell()
        raw = stream.readline()
        if not raw.endswith(b"\n"):
            return
        if raw.strip():
            try:
                row = json.loads(raw)
            except (ValueError, RecursionError) as error:
                raise ResumeError(f"{stream.name}: JSONL 기록을 읽을 수 없습니다 (바이트 {start}).") from error
            if not isinstance(row, dict):
                raise ResumeError(f"{stream.name}: JSONL 기록은 객체여야 합니다 (바이트 {start}).")
            yield start, stream.tell(), row


class DecisionJournal:
    def __init__(self, path: Path, stack: ExitStack, *, resuming: bool, before_live: Callable[[], None]):
        self._path = path
        self._stack = stack
        self._before_live = before_live
        self._rows = []
        self._staged = []
        self._cursor = 0
        self._offset = 0
        self._stream = None
        if path.exists():
            if not resuming:
                raise ResumeError(f"{path}: 이미 결정 기록이 있습니다. 새 출력 경로를 지정하세요.")
            with path.open("rb") as stream:
                for _, end, row in _rows(stream):
                    if set(row) != {"key", "value"}:
                        raise ResumeError(f"{path}: 결정 기록 형식이 올바르지 않습니다.")
                    self._rows.append(row)
                    self._offset = end

    @property
    def position(self) -> int:
        return self._cursor + len(self._staged)

    @property
    def remaining(self) -> int:
        return len(self._rows) - self._cursor

    @property
    def prior_calls(self) -> int:
        counts = (row["value"].get("model_calls") for row in self._rows if isinstance(row["value"], dict))
        return max((count for count in counts if type(count) is int), default=0)

    def peek_key(self):
        return self._rows[self._cursor]["key"] if self.remaining else None

    def remember(self, key, value) -> None:
        """Stage a decision reconstructed from a legacy event log."""
        if self._rows or self._stream is not None:
            raise ResumeError("기존 결정 기록과 복원한 결정을 섞을 수 없습니다.")
        self._staged.append({"key": key, "value": value})

    def flush_staged(self) -> None:
        if not self._staged:
            return
        # Install the complete legacy prefix at once so a failed migration can be retried.
        with NamedTemporaryFile(dir=self._path.parent, prefix=self._path.name + ".", delete=False) as stream:
            temporary = Path(stream.name)
        try:
            temporary.write_bytes(b"".join(_line(row) for row in self._staged))
            temporary.replace(self._path)
        finally:
            temporary.unlink(missing_ok=True)
        self._offset = self._path.stat().st_size
        self._rows = self._staged
        self._cursor = len(self._rows)
        self._staged = []

    def call(self, key, invoke: Callable[[], _T]) -> _T:
        if self.remaining:
            saved = self._rows[self._cursor]
            if saved["key"] != json.loads(_line(key)):
                raise ResumeError(f"결정 기록 {self._cursor + 1}의 순서가 현재 게임과 일치하지 않습니다.")
            self._cursor += 1
            return saved["value"]

        self._before_live()
        value = invoke()
        if self._stream is None:
            mode = "r+b" if self._path.exists() else "x+b"
            self._stream = self._stack.enter_context(self._path.open(mode))
            self._stream.seek(self._offset)
            self._stream.truncate()
        self._stream.write(_line({"key": key, "value": value}))
        self._stream.flush()
        self._rows.append({"key": key, "value": value})
        self._cursor += 1
        return value


class MatchLog:
    def __init__(self, path: Path, *, resume: bool = False):
        self.path = path
        self.resume = resume
        self.header = None
        self.events = []
        self.prior_calls = 0
        self.events_seen = 0
        self._append_at = 0
        self._continued = not resume
        self._appending = False
        self._stack = ExitStack()

    def __enter__(self):
        path = self.path
        journal_path = path.with_name(path.stem + ".decisions.jsonl")
        if not self.resume:
            if journal_path.exists():
                raise ResumeError(f"{journal_path}: 이미 결정 기록이 있습니다. 새 출력 경로를 지정하세요.")
            path.parent.mkdir(parents=True, exist_ok=True)
        with ExitStack() as opening:
            try:
                self._stream = opening.enter_context(path.open("r+b" if self.resume else "x+b"))
            except FileExistsError as error:
                raise ResumeError("이미 플레이 기록이 있습니다. 새 출력 경로를 지정하거나 --resume을 사용하세요.") from error
            try:
                fcntl.flock(self._stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ResumeError(f"{path}: 이미 실행 중인 매치 기록입니다.") from error
            if self.resume:
                self._read_events()
            self.journal = DecisionJournal(journal_path, self._stack, resuming=self.resume,
                                           before_live=self.complete_replay)
            self.prior_calls = max(self.prior_calls, self.journal.prior_calls)
            self._stack.enter_context(opening.pop_all())
        return self

    def __exit__(self, *exc):
        return self._stack.__exit__(*exc)

    def _read_events(self) -> None:
        terminal = None
        for start, end, row in _rows(self._stream):
            if self.header is None and row.get("type") == "match" and isinstance(row.get("game"), str):
                self.header = row
                self._append_at = end
                continue
            if self.header is None or terminal is not None:
                raise ResumeError(f"{self.path}: 플레이 기록의 행 순서가 올바르지 않습니다.")
            kind = row.get("type")
            if kind == "event" and row.get("turn") == len(self.events) and all(key in row for key in _EVENT_FIELDS):
                self.events.append(row)
                self._append_at = end
            elif kind in {"interrupted", "result"}:
                terminal = kind
                self._append_at = start
            else:
                raise ResumeError(f"{self.path}: 플레이 기록을 복원할 수 없습니다 (바이트 {start}).")
            self.prior_calls = row.get("model_calls", self.prior_calls)
        if self.header is None:
            raise ResumeError(f"{self.path}: 매치 시작 기록이 없습니다.")
        if terminal == "result":
            raise ResumeError(f"{self.path}: 이미 완료된 매치입니다.")
        if type(self.prior_calls) is not int or self.prior_calls < 0:
            raise ResumeError(f"{self.path}: 저장된 모델 호출 수가 올바르지 않습니다.")

    def complete_replay(self) -> None:
        """Require the complete saved prefix before asking for a fresh decision."""
        if self.events_seen != len(self.events) or self.journal.remaining:
            raise ResumeError("저장된 플레이 기록을 모두 복원하기 전에 새 결정이 필요합니다.")
        self.journal.flush_staged()
        self._continued = True

    def write(self, row: dict) -> bool:
        kind = row["type"]
        if self.resume and kind == "match":
            if json.loads(_line(row)) != self.header:
                raise ResumeError("저장된 매치 설정과 현재 설정이 일치하지 않습니다.")
            return False
        if kind == "event" and self.events_seen < len(self.events):
            saved = self.events[self.events_seen]
            if any(saved[key] != row.get(key) for key in _EVENT_FIELDS):
                raise ResumeError(f"저장된 플레이 기록 {self.events_seen + 1}번이 현재 게임과 일치하지 않습니다.")
            self.events_seen += 1
            return False
        if kind == "interrupted" and not self._continued and not self._appending:
            return False
        if kind == "result" or (kind == "event" and not self._continued):
            self.complete_replay()
        if not self._appending:
            self._stream.seek(self._append_at)
            self._stream.truncate()
            self._appending = True
        self._stream.write(_line(row))
        self._stream.flush()
        return True
