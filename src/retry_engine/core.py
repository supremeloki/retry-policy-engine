from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class RetryError(Exception):
    pass


class ExhaustedRetriesError(RetryError):
    def __init__(self, attempts: int, last_error: Exception) -> None:
        super().__init__(f"gave up after {attempts} attempt(s): {last_error}")
        self.attempts = attempts
        self.last_error = last_error


class PolicyDefinitionError(RetryError):
    pass


@dataclass(frozen=True)
class Attempt:
    index: int
    delay_before: float
    outcome: str
    error_type: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.outcome == "success"


@dataclass(frozen=True)
class RetryOutcome(Generic[T]):
    value: T | None
    total_attempts: int
    total_delay: float
    attempts: tuple[Attempt, ...]

    @property
    def ok(self) -> bool:
        return self.value is not None or (self.attempts and self.attempts[-1].succeeded)


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay: float = 0.1
    max_delay: float = 2.0
    exponential_base: float = 2.0
    jitter_ratio: float = 0.25
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,)
    fatal_exceptions: tuple[type[Exception], ...] = ()

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise PolicyDefinitionError("max_attempts must be >= 1")
        if self.base_delay < 0 or self.max_delay < self.base_delay:
            raise PolicyDefinitionError("invalid delay bounds")
        if not 0 <= self.jitter_ratio <= 1:
            raise PolicyDefinitionError("jitter_ratio must be within [0, 1]")

    def compute_delay(self, failed_attempt_index: int, rng: random.Random) -> float:
        raw = min(
            self.base_delay * (self.exponential_base ** failed_attempt_index),
            self.max_delay,
        )
        jitter_span = raw * self.jitter_ratio
        return max(0.0, raw - jitter_span + rng.random() * jitter_span * 2)

    def classify(self, error: Exception) -> str:
        if isinstance(error, self.fatal_exceptions):
            return "fatal"
        for retryable in self.retryable_exceptions:
            if retryable is not Exception and isinstance(error, retryable):
                return "retryable"
        if self.retryable_exceptions == (Exception,) and not isinstance(error, (KeyboardInterrupt, SystemExit)):
            return "retryable"
        return "non-retryable"


DEFAULT_POLICY = RetryPolicy()


def execute_with_retries(
    action: Callable[[], T],
    policy: RetryPolicy = DEFAULT_POLICY,
    sleep_fn: Callable[[float], None] = time.sleep,
    rng: random.Random | None = None,
) -> RetryOutcome[T]:
    active_rng = rng or random.Random()
    trace: list[Attempt] = []
    total_delay = 0.0
    for attempt_index in range(policy.max_attempts):
        try:
            value = action()
            trace.append(Attempt(index=attempt_index + 1, delay_before=total_delay,
                                 outcome="success"))
            return RetryOutcome(value=value, total_attempts=attempt_index + 1,
                                total_delay=total_delay, attempts=tuple(trace))
        except Exception as exc:
            classification = policy.classify(exc)
            if classification in {"fatal", "non-retryable"} or attempt_index == policy.max_attempts - 1:
                trace.append(Attempt(index=attempt_index + 1,
                                     delay_before=total_delay,
                                     outcome="abandoned",
                                     error_type=type(exc).__name__))
                raise ExhaustedRetriesError(attempt_index + 1, exc) from exc
            delay = policy.compute_delay(attempt_index, active_rng)
            sleep_fn(delay)
            total_delay += delay
            trace.append(Attempt(index=attempt_index + 1,
                                 delay_before=total_delay,
                                 outcome="retried",
                                 error_type=type(exc).__name__))
    raise ExhaustedRetriesError(policy.max_attempts, RuntimeError("unreachable"))


async def execute_with_retries_async(
    action: Callable[[], Any],
    policy: RetryPolicy = DEFAULT_POLICY,
    rng: random.Random | None = None,
) -> RetryOutcome[Any]:
    import asyncio

    async def null_sleep(_: float) -> None:
        await asyncio.sleep(0)

    sync_action_calls: list[Any] = []

    class AsyncAdapter:
        def __call__(self) -> Any:
            result = action()
            sync_action_calls.append(result)
            if hasattr(result, "__await__"):
                raise TypeError("use run_sync wrapper for coroutines")
            return result

    return execute_with_retries(AsyncAdapter(), policy, sleep_fn=lambda d: None, rng=rng)


def with_policy(
    policy: RetryPolicy,
    **runner_kwargs: Any,
) -> Callable[[Callable[[], T]], RetryOutcome[T]]:
    def decorator(action: Callable[[], T]) -> RetryOutcome[T]:
        return execute_with_retries(action, policy, **runner_kwargs)

    return decorator
