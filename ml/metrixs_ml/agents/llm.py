"""Claude runner: one agent turn = the SDK tool runner loop with an optional structured result.

Error policy (what may switch to the fallback model):
  • model unavailable — 404 model not found, 503 service unavailable, 529 overloaded
        → the whole agent turn is retried once on ML_AGENT_FALLBACK_MODEL (if configured);
  • safety refusal (stop_reason "refusal")
        → AgentRefusalError, never retried on another model — a refusal is not routed around;
  • technical error — 5xx other than 503/529, timeouts, connection errors, truncated output
        → AgentError, no model switch (the fallback would hit the same problem);
  • rate limit → AgentRateLimitError; missing/invalid credentials → AgentConfigError.
The SDK itself already retries 408/409/429/5xx a couple of times before any of this applies.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Generic, Protocol, Sequence, TypeVar

import anthropic
from anthropic.lib.tools import BetaFunctionTool
from pydantic import BaseModel

from .schemas import ToolCall

log = logging.getLogger("metrixs_ml.agents")

DEFAULT_MODEL = "claude-opus-5-5"
# Same tier, previous Opus — used only when the primary model is unavailable. Empty string disables.
DEFAULT_FALLBACK_MODEL = "claude-opus-5"
DEFAULT_EFFORT = "medium"
DEFAULT_MAX_TOKENS = 16_000
DEFAULT_MAX_ITERATIONS = 12

T = TypeVar("T", bound=BaseModel)

UNAVAILABLE_ERRORS = (anthropic.NotFoundError, anthropic.ServiceUnavailableError, anthropic.OverloadedError)


class AgentError(RuntimeError):
    """Technical failure: the model call failed or produced no usable answer."""


class AgentConfigError(AgentError):
    """No (valid) credentials for the Claude API."""


class AgentRateLimitError(AgentError):
    """Claude API rate limit."""


class AgentRefusalError(AgentError):
    """The model declined the request on safety grounds. Never retried on another model."""


class ModelUnavailableError(AgentError):
    """The requested model is unavailable (and so is the fallback, if one was tried)."""


@dataclass(frozen=True)
class AgentSettings:
    model: str = DEFAULT_MODEL
    fallback_model: str = DEFAULT_FALLBACK_MODEL
    effort: str = DEFAULT_EFFORT
    max_tokens: int = DEFAULT_MAX_TOKENS
    max_iterations: int = DEFAULT_MAX_ITERATIONS

    @classmethod
    def from_env(cls) -> "AgentSettings":
        return cls(
            model=os.environ.get("ML_AGENT_MODEL", DEFAULT_MODEL),
            fallback_model=os.environ.get("ML_AGENT_FALLBACK_MODEL", DEFAULT_FALLBACK_MODEL),
            effort=os.environ.get("ML_AGENT_EFFORT", DEFAULT_EFFORT),
        )


@dataclass(frozen=True)
class RunResult(Generic[T]):
    output: T | None
    text: str
    tool_calls: tuple[ToolCall, ...]
    model: str = ""
    fallback_reason: str | None = None


class LlmRunner(Protocol):
    def run(
        self,
        *,
        role: str,
        system: str,
        prompt: str,
        tools: Sequence[BetaFunctionTool],
        output_format: type[T] | None = None,
    ) -> RunResult[T]: ...


class ClaudeRunner:
    def __init__(self, settings: AgentSettings, client: anthropic.Anthropic | None = None) -> None:
        self.settings = settings
        self.client = client or anthropic.Anthropic()

    def _params(
        self, model: str, system: str, prompt: str, tools: Sequence[BetaFunctionTool], output_format: type | None
    ) -> dict:
        params: dict = {
            "model": model,
            "max_tokens": self.settings.max_tokens,
            "max_iterations": self.settings.max_iterations,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
            "tools": list(tools),
            "output_config": {"effort": self.settings.effort},
            # System prompt + tool definitions are identical across turns and agents: cache the prefix.
            "cache_control": {"type": "ephemeral"},
        }
        if output_format is not None:
            params["output_format"] = output_format
        return params

    def run(
        self,
        *,
        role: str,
        system: str,
        prompt: str,
        tools: Sequence[BetaFunctionTool],
        output_format: type[T] | None = None,
    ) -> RunResult[T]:
        primary, fallback = self.settings.model, self.settings.fallback_model
        try:
            return self._run_on(primary, role, system, prompt, tools, output_format)
        except ModelUnavailableError as exc:
            if not fallback or fallback == primary:
                raise
            log.warning("Модель %s недоступна (%s), агент «%s» перезапускается на %s", primary, exc, role, fallback)
            result = self._run_on(fallback, role, system, prompt, tools, output_format)
            return RunResult(
                output=result.output,
                text=result.text,
                tool_calls=result.tool_calls,
                model=fallback,
                fallback_reason=f"{primary} недоступна: {exc}",
            )

    def _run_on(self, model, role, system, prompt, tools, output_format) -> RunResult:
        calls: list[ToolCall] = []
        final = None
        try:
            for message in self.client.beta.messages.tool_runner(**self._params(model, system, prompt, tools, output_format)):
                final = message
                calls.extend(
                    ToolCall(role=role, name=b.name, input=dict(b.input)) for b in message.content if b.type == "tool_use"
                )
        except TypeError as exc:
            if "authentication method" in str(exc):
                raise AgentConfigError("Нет доступа к Claude API: задайте переменную окружения ANTHROPIC_API_KEY") from exc
            raise
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
            raise AgentConfigError("Claude API отклонил ключ доступа (ANTHROPIC_API_KEY)") from exc
        except anthropic.RateLimitError as exc:
            raise AgentRateLimitError("Превышен лимит запросов к Claude API, повторите позже") from exc
        except UNAVAILABLE_ERRORS as exc:
            raise ModelUnavailableError(f"модель {model} недоступна (HTTP {exc.status_code})") from exc
        except anthropic.APIStatusError as exc:
            log.error("Claude API error role=%s model=%s status=%s request_id=%s", role, model, exc.status_code, exc.request_id)
            raise AgentError(f"Техническая ошибка Claude API (HTTP {exc.status_code})") from exc
        except anthropic.APIConnectionError as exc:
            raise AgentError("Нет соединения с Claude API или истекло время ожидания") from exc

        return self._result(role, model, final, calls, output_format)

    @staticmethod
    def _result(role: str, model: str, final, calls: list[ToolCall], output_format: type[T] | None) -> RunResult[T]:
        if final is None:
            raise AgentError(f"Агент «{role}» не вернул ответ")
        if final.stop_reason == "refusal":
            raise AgentRefusalError(
                f"Агент «{role}»: модель отказалась выполнять запрос по правилам безопасности. "
                "Запрос не перенаправлялся на другую модель."
            )
        if final.stop_reason == "max_tokens":
            raise AgentError(f"Агент «{role}»: ответ не уместился в лимит токенов")

        text = "".join(b.text for b in final.content if b.type == "text")
        output = None
        if output_format is not None:
            output = getattr(final, "parsed_output", None) or output_format.model_validate_json(text)
        return RunResult(output=output, text=text, tool_calls=tuple(calls), model=model)
