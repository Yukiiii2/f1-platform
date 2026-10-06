"""Configurable model boundary using the existing HTTP dependency."""

import json
from typing import Protocol

import httpx


class AIUnavailable(Exception):
    """Only fixed, public-safe messages cross the AI boundary."""


class ModelClient(Protocol):
    def respond(self, *, input, tools, require_tool, output_schema) -> dict: ...


def strict_schema(schema):
    """Responses strict objects require every property, including nullable ones."""
    if isinstance(schema, list):
        return [strict_schema(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    result = {
        key: strict_schema(value) for key, value in schema.items() if key != "default"
    }
    if result.get("type") == "object":
        result["additionalProperties"] = False
        result["required"] = list(result.get("properties", {}))
    return result


class OpenAIResponsesClient:
    def __init__(self, api_key: str, model: str, http: httpx.Client):
        self._api_key, self.model, self.http = api_key, model, http

    def respond(self, *, input, tools, require_tool, output_schema):
        try:
            if self._api_key in json.dumps(
                {
                    "input": input,
                    "tools": tools,
                    "schema": output_schema,
                    "model": self.model,
                }
            ):
                raise ValueError("Unsafe model input")
            response = self.http.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self.model,
                    "input": input,
                    "tools": tools,
                    "tool_choice": "required" if require_tool else "auto",
                    "parallel_tool_calls": False,
                    "store": False,
                    "include": ["reasoning.encrypted_content"],
                    "max_output_tokens": 3000,
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "name": "pitwall_answer",
                            "strict": True,
                            "schema": strict_schema(output_schema),
                        }
                    },
                },
                timeout=20,
            )
            response.raise_for_status()
            if len(response.content) > 500000:
                raise ValueError("Oversized response")
            payload = response.json()
            if payload.get("status") != "completed" or self._api_key in json.dumps(
                payload
            ):
                raise ValueError("Incomplete or unsafe response")
            output = payload["output"]
            if not isinstance(output, list):
                raise ValueError("Invalid response")
            text = "".join(
                part["text"]
                for item in output
                if item.get("type") == "message"
                for part in item.get("content", [])
                if part.get("type") == "output_text"
            )
            return {"output": output, "answer": json.loads(text) if text else None}
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
            raise AIUnavailable(
                "Pitwall model service is temporarily unavailable"
            ) from None
