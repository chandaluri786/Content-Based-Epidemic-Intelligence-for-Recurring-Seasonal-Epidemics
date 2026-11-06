"""The only module that talks to the model API (NVIDIA's OpenAI-compatible endpoint).

The API allows at most REQUESTS_PER_MINUTE requests per minute. Every request, including each
retry, first takes a turn from one RateLimiter shared by all worker threads, so the limit holds
whatever `--workers` is. Retries are done here, not by the OpenAI library, because the library's
own retries would bypass the limiter.
"""

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable

import openai
from openai import OpenAI

from flu_extractor import config

# Errors worth another attempt: rate limit (429), timeouts, lost connections and server errors (5xx).
RETRYABLE_ERRORS = (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError,
                    openai.InternalServerError)


@dataclass(frozen=True)
class ModelReply:
    """What came back from one model call."""

    text: str                     # the model's answer, unparsed
    finish_reason: str            # "stop" = finished normally, "length" = cut off at MAX_TOKENS
    prompt_tokens: int | None     # tokens the server counted in our request
    completion_tokens: int | None # tokens the model wrote
    seconds: float                # wall-clock time for the call, including waits and retries
    attempts: int = 1             # requests sent for this reply (1 = no retry)


class RateLimiter:
    """At most `limit` request starts in any `window` seconds, shared by all threads.

    Keeps the start times of the last `limit` requests. A new request waits until the oldest of
    them is more than `window` seconds old. `clock` and `sleep` are replaced in the tests.
    """

    def __init__(self, limit: int, window: float = 60.0,
                 clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep):
        if limit < 1:
            raise ValueError("limit must be at least 1")
        self._limit, self._window, self._clock, self._sleep = limit, window, clock, sleep
        self._starts: deque[float] = deque()
        self._lock = threading.Lock()

    def wait_for_turn(self) -> float:
        """Block until a request may start; record its start. Returns the seconds waited."""
        waited = 0.0
        while True:
            with self._lock:
                now = self._clock()
                while self._starts and now - self._starts[0] >= self._window:
                    self._starts.popleft()
                if len(self._starts) < self._limit:
                    self._starts.append(now)
                    return waited
                pause = self._window - (now - self._starts[0])
            self._sleep(pause)  # outside the lock, so other threads are not blocked meanwhile
            waited += pause


# One limiter for the whole process: every worker thread shares it.
_LIMITER = RateLimiter(config.REQUESTS_PER_MINUTE, window=config.RATE_WINDOW_SECONDS)


def create_client() -> OpenAI:
    """Create the API client. NVIDIA's API follows OpenAI's format, so we reuse OpenAI's library."""
    return OpenAI(
        base_url=config.BASE_URL,
        api_key=config.get_api_key(),
        timeout=config.REQUEST_TIMEOUT_SECONDS,
        max_retries=0,  # retries go through ask_model, so each one is counted by the rate limiter
    )


def _seconds_before_retry(error: Exception, attempt: int) -> float:
    """The server's Retry-After if it sent one, otherwise 5, 10, 20, 40 ... seconds, at most 60."""
    response = getattr(error, "response", None)
    retry_after = response.headers.get("retry-after") if response is not None else None
    try:
        return min(float(retry_after), 120.0)
    except (TypeError, ValueError):
        return min(5.0 * 2 ** (attempt - 1), 60.0)


def ask_model(client: OpenAI, messages: list[dict], limiter: RateLimiter = _LIMITER,
              sleep: Callable[[float], None] = time.sleep) -> ModelReply:
    """Send one request (a list of chat messages) and return the reply.

    Every request uses the same decoding settings (config.TEMPERATURE, TOP_P, SEED, EXTRA_BODY).
    Retries rate-limit, timeout, connection and server errors up to MAX_RETRIES times, each
    attempt waiting for its turn under the rate limit. Raises openai.OpenAIError when all
    attempts fail, or at once for errors that a retry cannot fix (e.g. a request that is too long).
    """
    started = time.time()
    for attempt in range(1, config.MAX_RETRIES + 2):
        limiter.wait_for_turn()
        try:
            response = client.chat.completions.create(
                model=config.MODEL_ID,
                messages=messages,
                temperature=config.TEMPERATURE,
                top_p=config.TOP_P,
                max_tokens=config.MAX_TOKENS,
                seed=config.SEED,
                extra_body=config.EXTRA_BODY,
            )
        except RETRYABLE_ERRORS as error:
            if attempt > config.MAX_RETRIES:
                raise
            sleep(_seconds_before_retry(error, attempt))
            continue
        choice = response.choices[0]
        usage = response.usage
        return ModelReply(
            text=choice.message.content or "",
            finish_reason=choice.finish_reason or "",
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else None,
            seconds=round(time.time() - started, 2),
            attempts=attempt,
        )
    raise AssertionError("unreachable: the loop returns or raises")
