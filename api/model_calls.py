"""The shared, text-only Gemini call boundary for production and evaluation."""
from email.utils import parsedate_to_datetime
import json
import logging
import math
import re

from google import genai
from google.genai import errors, types
import httpx

from api.model_budget import BudgetError, DailyQuotaExceeded, RateLimited
from api.settings import GEMINI_MAX_ATTEMPTS, GEMINI_MODEL, GEMINI_TIMEOUT_MS

logger = logging.getLogger(__name__)
SYSTEM_INSTRUCTION = "You are a helpful assistant."


class InvalidModelResponse(RuntimeError):
    """Provider returned no usable text; any known usage is still charged."""


class ModelUnavailable(RuntimeError):
    """A bounded provider attempt failed, with unknown usage reserved."""


def create_client(api_key):
    # Explicit Developer API selection avoids environment-based Vertex routing.
    return genai.Client(
        api_key=api_key, vertexai=False,
        http_options=types.HttpOptions(
            timeout=GEMINI_TIMEOUT_MS,
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )


def _feedback(error, now):
    """Extract only retry timing/quota identity; never log provider prompt echoes."""
    detail_text = json.dumps(error.details).lower()
    daily = bool(re.search(r"per[_ -]?day|daily|requestsperday", detail_text))
    delays = []
    body = error.details if isinstance(error.details, dict) else {}
    nested = body.get("error", body)
    details = nested.get("details", []) if isinstance(nested, dict) else []
    for detail in details if isinstance(details, list) else []:
        if not isinstance(detail, dict):
            continue
        delay = detail.get("retryDelay")
        if isinstance(delay, str) and re.fullmatch(r"\d+(?:\.\d+)?s", delay):
            delays.append(float(delay[:-1]))
    headers = getattr(error.response, "headers", {})
    retry_after = headers.get("retry-after")
    if retry_after:
        try:
            delays.append(float(retry_after))
        except ValueError:
            try:
                delays.append(parsedate_to_datetime(retry_after).timestamp() - now)
            except (ValueError, TypeError, OverflowError):
                pass
    return daily, max([0] + [value for value in delays if math.isfinite(value) and value >= 0])


def _usage(response):
    usage = response.usage_metadata
    if usage is None:
        raise BudgetError("Missing usage metadata; maximum reservation retained")
    prompt = usage.prompt_token_count
    candidates = usage.candidates_token_count
    thoughts = usage.thoughts_token_count or 0
    total = usage.total_token_count
    if not all(type(value) is int and value >= 0 for value in (prompt, candidates, thoughts, total)):
        raise BudgetError("Incomplete usage metadata; maximum reservation retained")
    if total != prompt + candidates + thoughts or usage.tool_use_prompt_token_count:
        raise BudgetError("Inconsistent usage metadata; maximum reservation retained")
    return prompt, candidates + thoughts


def generate_text(client, budget, prompt, max_tokens=5000, *, purpose="production", keep_nanodollars=0):
    """Count, reserve, dispatch and reconcile each explicit model attempt.

    Args:
        client: Gemini Developer API client, with hidden retries disabled.
        budget: Open ModelBudget context shared by all publishing paths.
        prompt: Text prompt; no tools, media or arbitrary generation options.
        max_tokens: Output cap including thinking tokens.
        purpose: Production or explicitly enabled evaluation.
        keep_nanodollars: Budget left untouched for later summary work.
    Returns:
        Nonempty text from a completed response.
    """
    if not isinstance(prompt, str) or not prompt.strip() or type(max_tokens) is not int or not 1 <= max_tokens <= 65536:
        raise ValueError("Nonempty text and an output limit between 1 and 65536 are required")
    # Per-call options enforce this boundary even for an injected evaluation client.
    options = types.HttpOptions(timeout=GEMINI_TIMEOUT_MS, retry_options=types.HttpRetryOptions(attempts=1))
    contents = [{"role": "user", "parts": [{"text": prompt}]}]
    system = {"role": "user", "parts": [{"text": SYSTEM_INSTRUCTION}]}
    input_tokens = None
    last_error = None
    for attempt in range(GEMINI_MAX_ATTEMPTS):
        try:
            if input_tokens is None:
                budget.count_request(purpose)
                # SDK 2.7.0 rejects CountTokensConfig.system_instruction for the
                # Developer API. Its public extra_body escape hatch sends the
                # documented generateContentRequest to count the whole input.
                counted = client.models.count_tokens(
                    model=GEMINI_MODEL, contents=None,
                    config=types.CountTokensConfig(http_options=types.HttpOptions(
                        timeout=GEMINI_TIMEOUT_MS, retry_options=types.HttpRetryOptions(attempts=1),
                        extra_body={"generateContentRequest": {
                            "model": f"models/{GEMINI_MODEL}", "contents": contents, "systemInstruction": system,
                        }},
                    )),
                )
                if type(counted.total_tokens) is not int or counted.total_tokens < 1:
                    raise InvalidModelResponse("Invalid token count; generation not dispatched")
                # Conservative framing margin above provider's exact input count.
                input_tokens = counted.total_tokens + 32
            reservation = budget.reserve(
                input_tokens, max_tokens, purpose=purpose, keep_nanodollars=keep_nanodollars,
            )
            response = client.models.generate_content(
                model=GEMINI_MODEL, contents=contents,
                config=types.GenerateContentConfig(
                    http_options=options, system_instruction=SYSTEM_INSTRUCTION,
                    temperature=0.1, max_output_tokens=max_tokens, candidate_count=1,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
            prompt_tokens, output_tokens = _usage(response)
            budget.reconcile(reservation, prompt_tokens, output_tokens)
            candidates = response.candidates or []
            if len(candidates) != 1 or candidates[0].finish_reason != types.FinishReason.STOP:
                raise InvalidModelResponse("Gemini response did not complete")
            text = response.text
            if not isinstance(text, str) or not text.strip():
                raise InvalidModelResponse("Gemini returned empty text")
            logger.info("Gemini accounted: purpose=%s input=%d output_including_thoughts=%d",
                        purpose, prompt_tokens, output_tokens)
            return text
        except errors.APIError as err:
            # A failed request's reservation stays charged at its maximum: even
            # an error response is not proof of zero provider billing.
            daily, delay = _feedback(err, budget.clock())
            if err.code == 429 and daily:
                budget.provider_delay(delay, daily=True)
                raise DailyQuotaExceeded("Provider reports exhausted daily quota") from None
            if err.code not in (408, 429, 500, 502, 503, 504):
                raise ModelUnavailable(f"Gemini request rejected (HTTP {err.code})") from None
            budget.provider_delay(max(delay, 2 ** attempt))
            last_error = RateLimited("Gemini rate limit persists") if err.code == 429 else ModelUnavailable(
                f"Gemini temporarily unavailable (HTTP {err.code})"
            )
        except httpx.TransportError:
            budget.provider_delay(2 ** attempt)
            last_error = ModelUnavailable("Gemini transport failed; reservation retained")
        except (ValueError, InvalidModelResponse):
            # SDK JSON/schema decoding failures may follow a billable response.
            # Usage already reconciled for valid but empty/truncated responses.
            last_error = InvalidModelResponse("Invalid Gemini response")
            budget.provider_delay(2 ** attempt)
        logger.warning("Gemini attempt %d/%d failed: %s", attempt + 1, GEMINI_MAX_ATTEMPTS,
                       type(last_error).__name__)
    raise last_error
