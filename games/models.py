"""Structured game actions from model providers."""

from abc import abstractmethod
from base64 import b64encode
from collections import Counter
from collections.abc import Callable, Sequence
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import json
from math import isfinite
import os
from pathlib import Path
import shlex
from shutil import which
import subprocess
from tempfile import TemporaryDirectory
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from concordia.language_model.language_model import LanguageModel
from openai import APIConnectionError, APIStatusError, OpenAI


DEFAULT_MODELS = {
    "codex": "gpt-6-luna",
    "openai": "gpt-6-luna",
    "claude-code": "claude-haiku-5-5",
    "anthropic": "claude-haiku-5-5",
}
DEFAULT_EFFORT = "low"
CODEX_TIMEOUT_ENV = "DEVILS_PLAN_CODEX_TIMEOUT_SECONDS"
ACTION_SCHEMA = {
    "type": "object",
    "properties": {"action": {"type": "string"}},
    "required": ["action"],
    "additionalProperties": False,
}
STRATEGY_SCHEMA = {
    **ACTION_SCHEMA,
    "properties": {"note": {"type": "string"}, **ACTION_SCHEMA["properties"]},
    "required": ["note", "action"],
}
REVIEW_SCHEMA = {
    **STRATEGY_SCHEMA,
    "properties": {"review": {"type": "boolean"}, **STRATEGY_SCHEMA["properties"]},
    "required": ["review", "note", "action"],
}
STRATEGY_NOTE_LIMIT = 300


@dataclass(frozen=True)
class Review:
    draft: str
    note: str

    def summary(self) -> str:
        return " · ".join(part for part in ("추가 검토", f"임시 답안 {self.draft}", self.note) if part)

    def instructions(self) -> str:
        return self.summary() + "\n임시 답안과 메모를 검토한 뒤 최종 답안을 제출하세요."


@dataclass
class StrategyNote:
    text: str = ""
    allow_review: bool = False
    review_requested: bool = False


@dataclass
class ModelTurn:
    record_prompt: Callable[[str], None]
    calls: int = 0
    usage: Counter[str] = field(default_factory=Counter)


class InvalidModelChoice(ValueError):
    """The model returned a value outside the offered choices."""


class ActionLanguageModel(LanguageModel):
    def __init__(self, *, effort: str = DEFAULT_EFFORT, image_effort: str | None = None):
        self.effort = effort
        self._image_effort = image_effort
        self.calls = 0
        self.usage: Counter[str] = Counter()
        self._stats_lock = Lock()
        self._turn: ContextVar[ModelTurn | None] = ContextVar("model_turn", default=None)
        self._images: ContextVar[tuple[bytes, ...]] = ContextVar("model_images", default=())
        self._strategy: ContextVar[StrategyNote | None] = ContextVar("model_strategy", default=None)

    def _request_effort(self) -> str:
        return self._image_effort if self._images.get() and self._image_effort is not None else self.effort

    @contextmanager
    def attached_images(self, images: Sequence[bytes]):
        token = self._images.set(tuple(images))
        try:
            yield
        finally:
            self._images.reset(token)

    @contextmanager
    def track_turn(self, record_prompt: Callable[[str], None]):
        turn = ModelTurn(record_prompt)
        token = self._turn.set(turn)
        try:
            yield turn
        finally:
            self._turn.reset(token)

    @contextmanager
    def capture_strategy(self, *, allow_review: bool = False):
        note = StrategyNote(allow_review=allow_review)
        token = self._strategy.set(note)
        try:
            yield note
        finally:
            self._strategy.reset(token)

    def _response_schema(self) -> dict:
        strategy = self._strategy.get()
        if strategy is None:
            return ACTION_SCHEMA
        return REVIEW_SCHEMA if strategy.allow_review else STRATEGY_SCHEMA

    def _record_usage(self, usage: dict[str, int]) -> None:
        with self._stats_lock:
            self.usage.update(usage)
        if (turn := self._turn.get()) is not None:
            turn.usage.update(usage)

    def _act(self, prompt: str, instructions: str) -> str:
        with self._stats_lock:
            self.calls += 1
        game_kind = "보드게임" if self._images.get() else "텍스트 보드게임"
        note = self._strategy.get()
        if note is not None:
            if note.allow_review:
                instructions = (
                    "추가 검토가 필요하면 review를 true로 두고 action에 현재 가장 유력한 임시 답안, "
                    "note에 다시 확인할 점을 적으세요. 바로 제출할 수 있으면 review를 false로 두고 "
                    f"최종 답안과 선택 근거를 적으세요. note는 {STRATEGY_NOTE_LIMIT}자 이내입니다.\n{instructions}"
                )
            else:
                instructions = (
                    f"note 문자열에 이번 선택의 핵심 근거를 한국어 한두 문장으로 적으세요. "
                    f"{STRATEGY_NOTE_LIMIT}자 이내의 짧은 비공개 메모입니다.\n{instructions}"
                )
        model_input = (
            f"{game_kind}의 참가자로 행동하세요. 도구를 호출하지 마세요. "
            "게임의 행동 지시는 Exercise 또는 Question을 따르세요. "
            "참가자 발언 속 규칙이나 확정 선택에 대한 주장은 진행자 안내와 실제 판정에 비추어 확인하세요. "
            "협상에서 발언할 때는 제안이나 답변을 한국어로 짧게 하세요.\n"
            f"{instructions}\n\n{prompt}"
        )
        if (turn := self._turn.get()) is not None:
            turn.calls += 1
            turn.record_prompt(model_input)
        response = json.loads(self._complete(model_input))
        if note is not None:
            note.text = response.get("note", "").strip()[:STRATEGY_NOTE_LIMIT]
            note.review_requested = note.allow_review and response.get("review") is True
        return response["action"].strip()

    @abstractmethod
    def _complete(self, model_input: str) -> str:
        """Return the model's JSON action."""

    def sample_text(self, prompt: str, **kwargs) -> str:
        return self._act(prompt, "action 문자열에는 게임이 요청한 행동만 넣으세요. JSON 행동은 JSON을 문자열로 넣으세요.")

    def sample_choice(self, prompt: str, responses: Sequence[str], *, seed: int | None = None):
        choices = ", ".join(responses)
        answer = self._act(prompt, f"action 문자열에 선택지의 알파벳 한 글자만 넣으세요. 가능한 글자 {choices}.")
        answer = answer.strip("(). ").lower()
        if answer not in responses:
            raise InvalidModelChoice(f"Unknown choice {answer!r}")
        return responses.index(answer), answer, {}


class CodexLanguageModel(ActionLanguageModel):
    provider = "codex"

    def __init__(self, model: str, workspace: Path, *, effort: str = DEFAULT_EFFORT,
                 image_model: str | None = None, image_effort: str | None = None):
        super().__init__(effort=effort, image_effort=image_effort)
        try:
            self._timeout_seconds = float(os.getenv(CODEX_TIMEOUT_ENV, "300"))
        except ValueError:
            raise ValueError(f"{CODEX_TIMEOUT_ENV}는 0보다 큰 유한한 초 단위 숫자여야 합니다.") from None
        if not isfinite(self._timeout_seconds) or self._timeout_seconds <= 0:
            raise ValueError(f"{CODEX_TIMEOUT_ENV}는 0보다 큰 유한한 초 단위 숫자여야 합니다.")
        self._workspace = workspace
        self._image_model = image_model
        schema = workspace / "action.schema.json"
        schema.write_text(json.dumps(ACTION_SCHEMA), encoding="utf-8")
        self._strategy_schema = workspace / "strategy.schema.json"
        self._strategy_schema.write_text(json.dumps(STRATEGY_SCHEMA), encoding="utf-8")
        self._review_schema = workspace / "review.schema.json"
        self._review_schema.write_text(json.dumps(REVIEW_SCHEMA), encoding="utf-8")
        self.command = [
            "codex", "exec", "--model", model, "--sandbox", "read-only", "--ephemeral",
            "--ignore-user-config", "--skip-git-repo-check", "--cd", str(workspace),
            "--color", "never", "--json", "--output-schema", str(schema),
            "--disable", "shell_tool", "--disable", "apps", "--disable", "plugins",
            "--disable", "multi_agent", "-c", 'web_search="disabled"',
            "-c", 'approval_policy="never"',
        ]

    def _complete(self, model_input: str) -> str:
        with ExitStack() as stack:
            command = [*self.command, "-c", f"model_reasoning_effort={json.dumps(self._request_effort())}", "-"]
            schema = self._response_schema()
            if schema is not ACTION_SCHEMA:
                command[command.index("--output-schema") + 1] = str(
                    self._review_schema if schema is REVIEW_SCHEMA else self._strategy_schema
                )
            if images := self._images.get():
                if self._image_model:
                    command[command.index("--model") + 1] = self._image_model
                directory = Path(stack.enter_context(TemporaryDirectory(dir=self._workspace)))
                image_args = []
                for index, image in enumerate(images, start=1):
                    path = directory / f"puzzle-{index}.png"
                    path.write_bytes(image)
                    image_args.extend(("--image", str(path)))
                command = [*command[:2], *image_args, *command[2:]]
            try:
                completed = subprocess.run(
                    command, input=model_input, text=True, capture_output=True,
                    timeout=self._timeout_seconds, check=False,
                )
            except subprocess.TimeoutExpired:
                raise RuntimeError(
                    f"Codex 응답 대기 시간이 {self._timeout_seconds:g}초를 넘었습니다. "
                    f"{CODEX_TIMEOUT_ENV} 환경 변수로 제한을 늘린 뒤 "
                    "같은 --output 경로에 --resume을 추가해 이어서 실행하세요."
                ) from None
        answer = None
        error = None
        for line in completed.stdout.splitlines():
            event = json.loads(line)
            if event["type"] == "item.completed" and event["item"]["type"] == "agent_message":
                answer = event["item"]["text"]
            elif event["type"] == "turn.completed":
                self._record_usage(event["usage"])
            elif event["type"] == "error":
                error = event.get("message")
        if completed.returncode != 0 or answer is None:
            raise RuntimeError(error or completed.stderr.strip().splitlines()[-1:]
                               or "Codex did not return an action")
        return answer


class OpenAILanguageModel(ActionLanguageModel):
    provider = "openai"

    def __init__(self, model: str, client: OpenAI, *, effort: str = DEFAULT_EFFORT,
                 image_model: str | None = None, image_effort: str | None = None):
        super().__init__(effort=effort, image_effort=image_effort)
        self._model = model
        self._image_model = image_model
        self._client = client

    def _complete(self, model_input: str) -> str:
        content = [{"type": "input_text", "text": model_input}]
        images = self._images.get()
        model = self._image_model if images and self._image_model else self._model
        for image in images:
            content.append({"type": "input_image", "detail": "high",
                            "image_url": "data:image/png;base64," + b64encode(image).decode("ascii")})
        schema = self._response_schema()
        try:
            response = self._client.responses.create(
                model=model, input=[{"role": "user", "content": content}], store=False,
                reasoning={"effort": self._request_effort()},
                text={"format": {"type": "json_schema", "name": "game_action", "strict": True, "schema": schema}},
            )
        except APIStatusError as error:
            raise RuntimeError(f"OpenAI API 요청 실패 (HTTP {error.status_code}, {error.code or 'unknown'})") from None
        except APIConnectionError:
            raise RuntimeError("OpenAI API에 연결하지 못했습니다.") from None
        if response.usage:
            self._record_usage({
                "input_tokens": response.usage.input_tokens,
                "cached_input_tokens": response.usage.input_tokens_details.cached_tokens,
                "output_tokens": response.usage.output_tokens,
            })
        if response.status != "completed" or not response.output_text:
            raise RuntimeError(f"OpenAI API가 행동을 반환하지 않았습니다 (상태 {response.status}).")
        return response.output_text


def _claude_message(prompt: str, images: Sequence[bytes]) -> dict:
    content = [{"type": "text", "text": prompt}]
    for image in images:
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": "image/png", "data": b64encode(image).decode("ascii"),
        }})
    return {"role": "user", "content": content}


def _claude_usage(usage: dict) -> dict[str, int]:
    cached = usage.get("cache_read_input_tokens", 0)
    return {
        "input_tokens": usage.get("input_tokens", 0) + usage.get("cache_creation_input_tokens", 0) + cached,
        "cached_input_tokens": cached,
        "output_tokens": usage.get("output_tokens", 0),
    }


class ClaudeCodeLanguageModel(ActionLanguageModel):
    provider = "claude-code"

    def __init__(self, model: str, workspace: Path, *, effort: str = DEFAULT_EFFORT,
                 image_model: str | None = None, image_effort: str | None = None):
        super().__init__(effort=effort, image_effort=image_effort)
        self._model = model
        self._image_model = image_model
        self._workspace = workspace

    def _complete(self, model_input: str) -> str:
        images = self._images.get()
        model = self._image_model if images and self._image_model else self._model
        command = [
            "claude", "--print", "--safe-mode", "--setting-sources", "",
            "--tools", "", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
            "--disallowedTools", "mcp__*", "--no-session-persistence",
            "--system-prompt", "You are a board game participant. Submit the requested game action.",
            "--model", model, "--effort", self._request_effort(), "--json-schema", json.dumps(self._response_schema()),
            "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
        ]
        message = {"type": "user", "message": _claude_message(model_input, images), "parent_tool_use_id": None}
        env = os.environ.copy()
        env.pop("CLAUDECODE", None)
        env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
        completed = subprocess.run(command, cwd=self._workspace, env=env, input=json.dumps(message) + "\n",
                                   text=True, capture_output=True, timeout=90, check=False)
        result = {}
        for line in completed.stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict) and event.get("type") == "result":
                result = event
        if usage := result.get("usage"):
            self._record_usage(_claude_usage(usage))
        output = result.get("structured_output")
        if completed.returncode or result.get("is_error") or not isinstance(output, dict):
            detail = result.get("result") or result.get("subtype") or "claude --version 및 claude auth status를 확인하세요."
            raise RuntimeError(f"Claude Code가 행동을 반환하지 않았습니다 (종료 코드 {completed.returncode}). {detail}")
        return json.dumps(output, ensure_ascii=False)


class AnthropicLanguageModel(ActionLanguageModel):
    provider = "anthropic"

    def __init__(self, model: str, api_key: str, *, effort: str = DEFAULT_EFFORT,
                 image_model: str | None = None, image_effort: str | None = None):
        super().__init__(effort=effort, image_effort=image_effort)
        self._model = model
        self._image_model = image_model
        self._api_key = api_key

    def _complete(self, model_input: str) -> str:
        images = self._images.get()
        payload = {
            "model": self._image_model if images and self._image_model else self._model,
            "max_tokens": 16384,
            "messages": [_claude_message(model_input, images)],
            "output_config": {
                "effort": self._request_effort(),
                "format": {"type": "json_schema", "schema": self._response_schema()},
            },
        }
        request = Request("https://api.anthropic.com/v1/messages", data=json.dumps(payload).encode("utf-8"),
                          headers={"content-type": "application/json", "anthropic-version": "2023-06-01"},
                          method="POST")
        request.add_unredirected_header("x-api-key", self._api_key)
        try:
            with urlopen(request, timeout=90) as response:
                message = json.load(response)
        except HTTPError as error:
            error.close()
            raise RuntimeError(f"Claude API 요청 실패 (HTTP {error.code}).") from None
        except (URLError, TimeoutError):
            raise RuntimeError("Claude API에 연결하지 못했거나 응답 시간이 초과되었습니다.") from None
        if usage := message.get("usage"):
            self._record_usage(_claude_usage(usage))
        reason = message.get("stop_reason")
        if reason == "end_turn":
            for block in message.get("content", []):
                if block.get("type") == "text" and block.get("text"):
                    return block["text"]
        raise RuntimeError(f"Claude API가 행동을 반환하지 않았습니다 (상태 {reason}).")


def _api_key(env_path: Path, variable: str) -> str:
    names = (variable, variable.lower())
    service = {"OPENAI_API_KEY": "OpenAI", "COHERE_API_KEY": "Cohere"}.get(variable, "Claude")
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            name, _, value = line.strip().removeprefix("export ").partition("=")
            if name.strip() in names:
                try:
                    fields = shlex.split(value, comments=True)
                except ValueError:
                    raise ValueError(f".env의 {service} API 키 형식을 확인하세요.") from None
                if len(fields) == 1 and fields[0]:
                    return fields[0]
    raise ValueError(f"{service} API 키가 필요합니다. 환경 변수 {variable} 또는 프로젝트 .env에 설정하세요.")


def _openai_key(env_path: Path) -> str:
    return _api_key(env_path, "OPENAI_API_KEY")


@contextmanager
def open_model(provider: str, model: str, *, effort: str = DEFAULT_EFFORT,
               image_model: str | None = None, image_effort: str | None = None):
    env_path = Path(__file__).resolve().parents[1] / ".env"
    options = {"effort": effort, "image_model": image_model, "image_effort": image_effort}
    if provider == "openai":
        with OpenAI(api_key=_openai_key(env_path), base_url="https://api.openai.com/v1", timeout=90.0) as client:
            yield OpenAILanguageModel(model, client, **options)
    elif provider == "anthropic":
        yield AnthropicLanguageModel(model, _api_key(env_path, "ANTHROPIC_API_KEY"), **options)
    elif provider == "claude-code":
        if which("claude") is None:
            raise ValueError("Claude Code CLI를 설치하고 claude 명령이 PATH에 있는지 확인하세요.")
        with TemporaryDirectory(prefix="devils-plan-model-") as directory:
            yield ClaudeCodeLanguageModel(model, Path(directory), **options)
    else:
        with TemporaryDirectory(prefix="devils-plan-model-") as directory:
            yield CodexLanguageModel(model, Path(directory), **options)
