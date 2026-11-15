"""One Gemini wrapper for both companions (Nova's open-ended replies and ECHO's chat and rating).

Handles the parts every call needs: a timeout, retrying on the next model for rate limits and server
errors, translating every failure into `CompanionUnavailableError` (HTTP 503), and spotting blocked replies.
"""

import asyncio
import logging
from collections.abc import Sequence

import httpx2
from google import genai
from google.genai import errors, types

from app.core.errors import CompanionUnavailableError

log = logging.getLogger(__name__)

# Gemini errors worth retrying on the next model: rate limit / quota, overload, server errors.
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
# A wellbeing chat must be able to discuss distress, so only block clearly harmful content.
SAFETY_SETTINGS = [
    types.SafetySetting(category=c, threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH)
    for c in (
        types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        types.HarmCategory.HARM_CATEGORY_HARASSMENT,
        types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
    )
]


class GeminiClient:
    def __init__(self, client: genai.Client, timeout_s: float = 20.0) -> None:
        self._client = client
        self._timeout = timeout_s

    async def generate(
        self,
        models: Sequence[str],
        contents: list[types.Content],
        config: types.GenerateContentConfig,
        *,
        timeout_s: float | None = None,
    ) -> types.GenerateContentResponse:
        """Try each model in turn; move on after a timeout or a retryable error, fail fast on anything else."""
        order = list(dict.fromkeys(models))  # de-duplicated, order kept
        for i, model in enumerate(order):
            last = i == len(order) - 1
            try:
                async with asyncio.timeout(timeout_s or self._timeout):
                    return await self._client.aio.models.generate_content(model=model, contents=contents, config=config)
            except TimeoutError as exc:
                if last:
                    raise CompanionUnavailableError("the companion took too long to reply, please try again") from exc
                log.warning("Gemini %s timed out; retrying on %s", model, order[i + 1])
            except errors.APIError as exc:
                if last or exc.code not in RETRYABLE_STATUS:
                    raise CompanionUnavailableError(describe(exc)) from exc
                log.warning("Gemini %s failed (%s); retrying on %s", model, exc.code, order[i + 1])
            except httpx2.HTTPError as exc:
                raise CompanionUnavailableError("cannot reach the Gemini API") from exc
        raise CompanionUnavailableError(
            "no Gemini model available"
        )  # pragma: no cover - the loop always returns/raises


def blocked(response: types.GenerateContentResponse) -> bool:
    """True when Gemini's safety filters withheld the reply (most likely because the astronaut voiced distress)."""
    if response.prompt_feedback is not None and response.prompt_feedback.block_reason is not None:
        return True
    candidates = response.candidates or []
    return bool(candidates) and candidates[0].finish_reason in {
        types.FinishReason.SAFETY,
        types.FinishReason.PROHIBITED_CONTENT,
    }


def describe(exc: errors.APIError) -> str:
    message = (exc.message or "").lower()
    if exc.code == 429:
        return "Gemini rate limit reached (free tier quota), retry shortly"
    if exc.code in {401, 403} or "api key" in message:
        return "invalid GEMINI_API_KEY"
    if exc.code == 404:
        return "unknown GEMINI_MODEL"
    return f"Gemini API error {exc.code}"
