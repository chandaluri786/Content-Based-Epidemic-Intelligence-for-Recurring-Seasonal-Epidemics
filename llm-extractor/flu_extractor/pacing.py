"""Keep the run under the API's rate limit, shared by all worker threads.

The NVIDIA API sends no rate-limit headers, so the limit cannot be read; it has to be respected
from our side. Two rules:

1. A sliding window: at most `calls_per_minute` calls may start in any 60 seconds.
2. After a 429 (rate limited), every worker pauses together. The pause starts at
   RATE_LIMIT_FIRST_PAUSE_SECONDS and doubles up to RATE_LIMIT_MAX_PAUSE_SECONDS, and the window
   is halved (never below MIN_CALLS_PER_MINUTE). A successful call resets the pause length.

If no call has succeeded for RATE_LIMIT_GIVE_UP_SECONDS while rate limited, the pacer stops the
run (RateLimitStop) instead of waiting forever; the run can then be resumed with --run-dir.
"""

import threading
import time
from collections import deque
from collections.abc import Callable

from flu_extractor import config

WINDOW_SECONDS = 60.0


class RateLimitStop(Exception):
    """The API kept refusing calls for too long; stop the run and resume it later."""


class Pacer:
    """Decides when the next call may start. Safe to share between threads."""

    def __init__(self, calls_per_minute: int,
                 first_pause: float = config.RATE_LIMIT_FIRST_PAUSE_SECONDS,
                 max_pause: float = config.RATE_LIMIT_MAX_PAUSE_SECONDS,
                 give_up_after: float = config.RATE_LIMIT_GIVE_UP_SECONDS,
                 min_calls_per_minute: int = config.MIN_CALLS_PER_MINUTE,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep,
                 log: Callable[[str], None] = print):
        if calls_per_minute < 1:
            raise ValueError("calls_per_minute must be at least 1")
        self.calls_per_minute = calls_per_minute
        self._first_pause, self._max_pause = first_pause, max_pause
        self._give_up_after = give_up_after
        self._min_calls = min(min_calls_per_minute, calls_per_minute)
        self._clock, self._sleep, self._log = clock, sleep, log
        self._lock = threading.Lock()
        self._starts: deque[float] = deque()   # start times of calls in the current window
        self._paused_until = 0.0
        self._next_pause = first_pause
        self._limited_since: float | None = None  # first 429 since the last successful call
        self.stopped = False

    def _seconds_to_wait(self, now: float) -> float:
        """0 if a call may start now, else how long to wait. Called with the lock held."""
        while self._starts and now - self._starts[0] >= WINDOW_SECONDS:
            self._starts.popleft()
        waits = [self._paused_until - now]
        if len(self._starts) >= self.calls_per_minute:
            waits.append(self._starts[0] + WINDOW_SECONDS - now)
        return max(0.0, *waits)

    def wait_turn(self) -> None:
        """Block until a call may start, then count it as started. Raises RateLimitStop once stopped."""
        while True:
            with self._lock:
                if self.stopped:
                    raise RateLimitStop("the run was stopped after a long rate limit")
                now = self._clock()
                wait = self._seconds_to_wait(now)
                if wait == 0:
                    self._starts.append(now)
                    return
            self._sleep(min(wait, WINDOW_SECONDS))

    def report_success(self) -> None:
        with self._lock:
            self._next_pause = self._first_pause
            self._limited_since = None

    def report_rate_limit(self) -> None:
        """Pause every worker and slow down. Raises RateLimitStop if the limit has lasted too long."""
        with self._lock:
            now = self._clock()
            if self._limited_since is None:
                self._limited_since = now
            if now - self._limited_since >= self._give_up_after:
                self.stopped = True
                raise RateLimitStop(f"rate limited for {now - self._limited_since:.0f} s without a "
                                    "successful call")
            if now < self._paused_until:
                return  # another worker already started this pause
            pause = self._next_pause
            self._paused_until = now + pause
            self._next_pause = min(self._next_pause * 2, self._max_pause)
            self.calls_per_minute = max(self._min_calls, self.calls_per_minute // 2)
            self._log(f"  rate limited: all workers pause {pause:.0f} s, then at most "
                      f"{self.calls_per_minute} calls per minute")
