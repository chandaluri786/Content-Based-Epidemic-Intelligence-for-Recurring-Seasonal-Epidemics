"""Tests for the rate limiter and the retries in llm_client. No API and no internet: the clock,
the sleep and the client are fakes.

Run from the llm-extractor folder:

    python -m unittest discover tests
"""

import threading
import time
import unittest
from types import SimpleNamespace

import openai

try:  # the HTTP library the installed openai version builds its errors from
    import httpx2 as httpx
except ImportError:
    import httpx

from flu_extractor import config
from flu_extractor.llm_client import RateLimiter, ask_model


class FakeClock:
    """A clock that only moves when something sleeps."""

    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def reply(text="{}"):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text), finish_reason="stop")],
                           usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5))


def api_error(kind, status, headers=None):
    response = httpx.Response(status, request=httpx.Request("POST", "http://test"), headers=headers or {})
    return kind("error", response=response, body=None)


class FakeClient:
    """Raises the given errors in turn, then answers."""

    def __init__(self, errors=()):
        self.errors, self.calls = list(errors), 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **_):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return reply()


class RateLimiterTest(unittest.TestCase):
    def test_limit_requests_start_at_once_and_the_next_waits_for_the_window(self):
        clock = FakeClock()
        limiter = RateLimiter(40, window=61, clock=clock, sleep=clock.sleep)
        self.assertEqual([limiter.wait_for_turn() for _ in range(40)], [0.0] * 40)
        self.assertEqual(clock.now, 0.0)
        limiter.wait_for_turn()  # the 41st
        self.assertEqual(clock.now, 61.0)

    def test_window_slides_with_evenly_spread_requests(self):
        clock = FakeClock()
        limiter = RateLimiter(2, window=10, clock=clock, sleep=clock.sleep)
        limiter.wait_for_turn()          # t=0
        clock.now = 4.0
        limiter.wait_for_turn()          # t=4
        clock.now = 6.0
        limiter.wait_for_turn()          # must wait until t=10, when the first leaves the window
        self.assertEqual(clock.now, 10.0)
        limiter.wait_for_turn()          # must wait until t=14
        self.assertEqual(clock.now, 14.0)

    def test_never_more_than_limit_starts_in_any_window_across_threads(self):
        limiter = RateLimiter(5, window=0.5)
        starts, lock = [], threading.Lock()

        def worker():
            for _ in range(3):
                limiter.wait_for_turn()
                with lock:
                    starts.append(time.monotonic())

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        starts.sort()
        self.assertEqual(len(starts), 12)
        for i in range(len(starts) - 5):
            self.assertGreaterEqual(starts[i + 5] - starts[i], 0.5 - 0.01)  # 6 starts never fit in one window

    def test_limit_must_be_positive(self):
        with self.assertRaises(ValueError):
            RateLimiter(0)


class RetryTest(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.limiter = RateLimiter(40, window=61, clock=self.clock, sleep=self.clock.sleep)
        self.slept = []

    def ask(self, client):
        return ask_model(client, [{"role": "user", "content": "x"}], limiter=self.limiter, sleep=self.slept.append)

    def test_rate_limit_error_is_retried_after_retry_after_and_every_attempt_takes_a_turn(self):
        client = FakeClient([api_error(openai.RateLimitError, 429, {"retry-after": "7"})])
        result = self.ask(client)
        self.assertEqual((client.calls, result.attempts, self.slept), (2, 2, [7.0]))
        self.assertEqual(len(self.limiter._starts), 2)  # both attempts counted against the limit

    def test_server_errors_back_off_5_10_20(self):
        errors = [api_error(openai.InternalServerError, 500) for _ in range(3)]
        result = self.ask(FakeClient(errors))
        self.assertEqual((result.attempts, self.slept), (4, [5.0, 10.0, 20.0]))

    def test_gives_up_after_max_retries(self):
        errors = [api_error(openai.InternalServerError, 503) for _ in range(config.MAX_RETRIES + 1)]
        client = FakeClient(errors)
        with self.assertRaises(openai.InternalServerError):
            self.ask(client)
        self.assertEqual(client.calls, config.MAX_RETRIES + 1)

    def test_errors_a_retry_cannot_fix_are_not_retried(self):
        client = FakeClient([api_error(openai.BadRequestError, 400)])  # e.g. over the context limit
        with self.assertRaises(openai.BadRequestError):
            self.ask(client)
        self.assertEqual((client.calls, self.slept), (1, []))


if __name__ == "__main__":
    unittest.main()
