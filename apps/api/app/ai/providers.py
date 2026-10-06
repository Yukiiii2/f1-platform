"""Server-side provider selection, independent of Pitwall business logic."""

from contextlib import contextmanager

import httpx
from google import genai
from google.genai import types
from google.genai.client import DebugConfig

from app.ai.client import AIUnavailable, OpenAIResponsesClient
from app.ai.gemini import GeminiClient, GeminiHTTPClient


@contextmanager
def configured_client(settings):
    secret = (
        settings.gemini_api_key
        if settings.pitwall_provider == "gemini"
        else settings.openai_api_key
    )
    key = secret.get_secret_value() if secret else ""
    if not key.strip() or not settings.pitwall_model:
        raise AIUnavailable("Pitwall is not configured")
    try:
        transport = (
            GeminiHTTPClient if settings.pitwall_provider == "gemini" else httpx.Client
        )
        with transport(follow_redirects=False) as http:
            if settings.pitwall_provider == "gemini":
                with genai.Client(
                    api_key=key,
                    vertexai=False,
                    enterprise=False,
                    debug_config=DebugConfig(
                        client_mode="api", replays_directory=None, replay_id=None
                    ),
                    http_options=types.HttpOptions(
                        base_url="https://generativelanguage.googleapis.com",
                        api_version="v1beta",
                        httpx_client=http,
                        timeout=20000,
                        # GeminiHTTPClient prevents automatic failure retries.
                        retry_options=types.HttpRetryOptions(attempts=1),
                    ),
                ) as sdk:
                    yield GeminiClient(
                        key,
                        settings.pitwall_model,
                        sdk,
                        fallback_models=tuple(
                            filter(None, settings.pitwall_fallback_models.split(","))
                        ),
                        max_retries=settings.pitwall_max_retries,
                    )
            else:
                yield OpenAIResponsesClient(key, settings.pitwall_model, http)
    except (genai.errors.APIError, httpx.HTTPError, ValueError, TypeError):
        raise AIUnavailable(
            "Pitwall model service is temporarily unavailable"
        ) from None
