"""Tests for the rate-limit pacing (flu_extractor/pacing.py) and the paced call (extractor.py).

A fake clock stands in for time, so the tests run instantly. Run from the llm-extractor folder:

    python -m unittest discover tests
"""

import unittest
from unittest import mock

import openai

from flu_extractor import extractor
from flu_extractor.llm_client import ModelReply
from flu_extractor.pacing import Pacer, RateLimitStop


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.slept = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def make_pacer(clock: FakeClock, calls_per_minute: int = 3, give_up_after: float = 900) -> Pacer:
    return Pacer(calls_per_minute, first_pause=60, max_pause=300, give_up_after=give_up_after,
                 min_calls_per_minute=1, clock=clock, sleep=clock.sleep, log=lambda message: None)


def _error(cls):
    """An instance of an openai error class, made without an HTTP response (only its type matters here)."""
    return cls.__new__(cls)


REPLY = ModelReply(text='{"useful": false}', finish_reason="stop", prompt_tokens=1, completion_tokens=1, seconds=0.1)


class PacerTest(unittest.TestCase):
    def test_window_lets_n_calls_start_then_waits_for_the_oldest_to_leave(self):
        clock = FakeClock()
        pacer = make_pacer(clock, calls_per_minute=3)
        for _ in range(3):
            pacer.wait_turn()
        self.assertEqual(clock.slept, [])
        pacer.wait_turn()  # the 4th call waits until the 1st is 60 s old
        self.assertEqual(clock.now, 60)

    def test_rate_limit_pauses_everyone_halves_the_rate_and_doubles_the_next_pause(self):
        clock = FakeClock()
        pacer = make_pacer(clock, calls_per_minute=4)
        pacer.report_rate_limit()
        self.assertEqual(pacer.calls_per_minute, 2)
        pacer.wait_turn()
        self.assertEqual(clock.now, 60)
        pacer.report_rate_limit()
        pacer.wait_turn()
        self.assertEqual(clock.now, 180)  # second pause is 120 s
        self.assertEqual(pacer.calls_per_minute, 1)

    def test_a_second_429_during_a_pause_does_not_stack_pauses(self):
        clock = FakeClock()
        pacer = make_pacer(clock, calls_per_minute=4)
        pacer.report_rate_limit()
        pacer.report_rate_limit()  # another worker hits 429 while paused
        pacer.wait_turn()
        self.assertEqual(clock.now, 60)
        self.assertEqual(pacer.calls_per_minute, 2)

    def test_success_resets_the_pause_length(self):
        clock = FakeClock()
        pacer = make_pacer(clock)
        pacer.report_rate_limit()
        pacer.wait_turn()
        pacer.report_success()
        pacer.report_rate_limit()
        pacer.wait_turn()
        self.assertEqual(clock.now, 120)  # 60 + 60, not 60 + 120

    def test_gives_up_after_a_long_limit_and_stops_every_worker(self):
        clock = FakeClock()
        pacer = make_pacer(clock, give_up_after=200)
        pacer.report_rate_limit()
        clock.now = 250
        with self.assertRaises(RateLimitStop):
            pacer.report_rate_limit()
        with self.assertRaises(RateLimitStop):
            pacer.wait_turn()


class PacedCallTest(unittest.TestCase):
    def test_a_429_is_sat_out_and_the_same_call_retried(self):
        clock = FakeClock()
        pacer = make_pacer(clock)
        side_effects = [_error(openai.RateLimitError), REPLY]
        with mock.patch.object(extractor, "ask_model", side_effect=side_effects):
            reply = extractor.call_with_pacing(None, [], pacer, sleep=clock.sleep)
        self.assertEqual(reply, REPLY)
        self.assertEqual(clock.now, 60)

    def test_server_errors_are_retried_with_backoff_then_raised(self):
        clock = FakeClock()
        pacer = make_pacer(clock, calls_per_minute=100)
        errors = [_error(openai.InternalServerError)] * 10
        with mock.patch.object(extractor, "ask_model", side_effect=errors), \
                mock.patch.object(extractor.config, "MAX_RETRIES", 2):
            with self.assertRaises(openai.InternalServerError):
                extractor.call_with_pacing(None, [], pacer, sleep=clock.sleep)
        self.assertEqual(clock.slept, [extractor.config.RETRY_BASE_SECONDS, 2 * extractor.config.RETRY_BASE_SECONDS])

    def test_other_errors_are_not_retried(self):
        clock = FakeClock()
        pacer = make_pacer(clock)
        with mock.patch.object(extractor, "ask_model", side_effect=[_error(openai.BadRequestError)]) as ask:
            with self.assertRaises(openai.BadRequestError):
                extractor.call_with_pacing(None, [], pacer, sleep=clock.sleep)
        self.assertEqual(ask.call_count, 1)


if __name__ == "__main__":
    unittest.main()
