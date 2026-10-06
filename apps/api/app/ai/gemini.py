"""Gemini Interactions adapter; application orchestration stays provider-neutral."""

import json
import logging
import re
from time import monotonic, sleep

import httpx
from google import genai

from app.ai.client import AIUnavailable

# The SDK's opt-in debug logger prints auth headers and unvalidated payloads.
# Suppress it even when GOOGLE_GENAI_DEBUG is set; HTTP status logs remain usable.
logging.getLogger("google.genai").addFilter(lambda record: False)
logger = logging.getLogger(__name__)


class GeminiRequestError(AIUnavailable):
    """Only safe status metadata survives an upstream HTTP/transport failure."""

    def __init__(self, status, category, retryable):
        super().__init__("Pitwall model service is temporarily unavailable")
        self.status, self.category, self.retryable = status, category, retryable


def quota_exhausted(response):
    """Daily/zero/billing quotas cannot recover through a short rate-limit retry."""
    try:
        error = response.json().get("error", {})
        if re.search(
            r"limit:\s*0\b|daily quota|quota exhausted", error.get("message", ""), re.I
        ):
            return True
        for detail in error.get("details", []):
            if detail.get("reason") in {
                "QUOTA_EXHAUSTED",
                "DAILY_LIMIT_EXCEEDED",
                "BILLING_DISABLED",
            }:
                return True
            for violation in detail.get("violations", []):
                identifier = str(violation.get("quotaId", "")) + str(
                    violation.get("quotaMetric", "")
                )
                if (
                    re.search(r"per_?day|daily", identifier, re.I)
                    or str(violation.get("quotaValue")) == "0"
                ):
                    return True
    except (ValueError, AttributeError, TypeError):
        pass
    return False


class GeminiHTTPClient(httpx.Client):
    """Normalize failed requests before the SDK can retry or echo their details."""

    def send(self, request, **kwargs):
        try:
            response = super().send(request, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPError as error:
            status = (
                error.response.status_code
                if isinstance(error, httpx.HTTPStatusError)
                else None
            )
            if status == 429 and quota_exhausted(error.response):
                category, retryable = "quota_exhausted", False
            elif status in {429, 500, 502, 503, 504}:
                category, retryable = (
                    ("rate_limit" if status == 429 else "upstream_unavailable"),
                    True,
                )
            elif status in {401, 403}:
                category, retryable = "authentication", False
            elif status is None:
                category, retryable = "network_error", True
            else:
                category, retryable = "permanent_request_error", False
            logger.warning(
                "Gemini transport failure: exception=%s http_status=%s",
                type(error).__name__,
                error.response.status_code
                if isinstance(error, httpx.HTTPStatusError)
                else None,
            )
            raise GeminiRequestError(status, category, retryable) from None


def history(input):
    """Translate the boundary's messages, retaining opaque native model steps."""
    instructions, steps, calls = [], [], {}
    for item in input:
        if "_gemini_step" in item:
            step = item["_gemini_step"]
            steps.append(step)
            if step["type"] == "function_call":
                if step["id"] in calls:
                    raise ValueError("Duplicate call ID")
                calls[step["id"]] = step["name"]
        elif item.get("role") == "developer":
            instructions.append(item["content"])
        elif item.get("role") == "user":
            steps.append(
                {
                    "type": "user_input",
                    "content": [{"type": "text", "text": item["content"]}],
                }
            )
        elif item.get("type") == "function_call_output":
            steps.append(
                {
                    "type": "function_result",
                    "name": calls[item["call_id"]],
                    "call_id": item["call_id"],
                    "result": [{"type": "text", "text": item["output"]}],
                }
            )
        else:
            raise ValueError("Unexpected model history item")
    return "\n\n".join(instructions), steps


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        sdk: genai.Client,
        *,
        fallback_models=(),
        max_retries=1,
    ):
        self._api_key, self.model, self.sdk = api_key, model, sdk
        self.models = tuple(dict.fromkeys((model, *fallback_models)))
        self.max_retries = max_retries
        self._model_index, self._deadline = 0, None

    def _create(self, arguments):
        if self._deadline is None:
            self._deadline = monotonic() + 45
        for index in range(self._model_index, len(self.models)):
            model = self.models[index]
            label = (
                model
                if re.fullmatch(r"gemini-[a-z0-9.-]{1,90}", model)
                else "invalid_model"
            )
            for retry in range(self.max_retries + 1):
                remaining = self._deadline - monotonic()
                if remaining <= 0:
                    logger.warning(
                        "Gemini model=%s category=budget_exhausted "
                        "retry=%s decision=stop",
                        label,
                        retry,
                    )
                    raise AIUnavailable(
                        "Pitwall model service is temporarily unavailable"
                    )
                try:
                    interaction = self.sdk.interactions.create(
                        **(arguments | {"model": model}), timeout=min(20, remaining)
                    )
                    if monotonic() >= self._deadline:
                        logger.warning(
                            "Gemini model=%s category=budget_exhausted "
                            "retry=%s decision=stop",
                            label,
                            retry,
                        )
                        raise AIUnavailable(
                            "Pitwall model service is temporarily unavailable"
                        )
                    self._model_index, self.model = index, model
                    logger.info(
                        "Gemini model=%s category=success retry=%s decision=use_model",
                        label,
                        retry,
                    )
                    return interaction
                except GeminiRequestError as error:
                    decision = (
                        "stop"
                        if not error.retryable
                        else "retry"
                        if retry < self.max_retries
                        else "fallback"
                        if index + 1 < len(self.models)
                        else "stop"
                    )
                    logger.warning(
                        "Gemini model=%s category=%s http_status=%s "
                        "retry=%s decision=%s",
                        label,
                        error.category,
                        error.status,
                        retry,
                        decision,
                    )
                    if not error.retryable:
                        raise
                    if retry < self.max_retries:
                        delay = 2**retry
                        if delay >= self._deadline - monotonic():
                            logger.warning(
                                "Gemini model=%s category=budget_exhausted "
                                "retry=%s decision=stop",
                                label,
                                retry,
                            )
                            raise AIUnavailable(
                                "Pitwall model service is temporarily unavailable"
                            ) from None
                        sleep(delay)
        raise AIUnavailable("Pitwall model service is temporarily unavailable")

    def respond(self, *, input, tools, require_tool, output_schema):
        try:
            if self._api_key in json.dumps(
                {
                    "input": input,
                    "tools": tools,
                    "schema": output_schema,
                    "models": self.models,
                }
            ):
                raise ValueError("Unsafe model input")
            instruction, steps = history(input)
            declarations = [
                {
                    key: tool[key]
                    for key in ("type", "name", "description", "parameters")
                }
                for tool in tools
            ]
            config = {
                "max_output_tokens": 3000,
                "tool_choice": (
                    {
                        "allowed_tools": {
                            "mode": "any",
                            "tools": [tool["name"] for tool in tools],
                        }
                    }
                    if require_tool
                    else "auto"
                ),
            }
            arguments = {
                "model": self.model,
                "input": steps,
                "system_instruction": instruction,
                "tools": declarations,
                "generation_config": config,
                "store": False,
            }
            # The first turn must call an application tool, not produce an answer.
            if not require_tool:
                arguments["response_format"] = {
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": output_schema,
                }
            interaction = self._create(arguments)
            payload = interaction.model_dump(mode="json", exclude_none=True)
            encoded = json.dumps(payload)
            if len(encoded) > 500000 or self._api_key in encoded:
                raise ValueError("Oversized or unsafe response")
            if payload["status"] not in {"requires_action", "completed"}:
                raise ValueError("Incomplete response")
            output, call_ids = [], set()
            for step in payload.get("steps", []):
                kind = step["type"]
                if kind not in {"thought", "function_call", "model_output"}:
                    raise ValueError("Unexpected model step")
                if kind == "function_call":
                    if (
                        not step["id"]
                        or step["id"] in call_ids
                        or not isinstance(step["arguments"], dict)
                    ):
                        raise ValueError("Invalid function call")
                    call_ids.add(step["id"])
                    output.append(
                        {
                            "type": "function_call",
                            "name": step["name"],
                            "arguments": json.dumps(step["arguments"]),
                            "call_id": step["id"],
                            "_gemini_step": step,
                        }
                    )
                else:
                    # Thought signatures remain private, but must be replayed intact.
                    output.append({"type": "gemini_step", "_gemini_step": step})
            if call_ids:
                return {"output": output, "answer": None}
            if payload["status"] != "completed" or not interaction.output_text:
                raise ValueError("No structured answer")
            return {"output": output, "answer": json.loads(interaction.output_text)}
        except Exception:
            # Interactions and GenerateContent expose different SDK error types.
            # Keep every provider/decoding failure behind the public-safe boundary.
            raise AIUnavailable(
                "Pitwall model service is temporarily unavailable"
            ) from None
