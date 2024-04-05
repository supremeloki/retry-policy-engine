import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from retry_engine import (
    ExhaustedRetriesError,
    PolicyDefinitionError,
    RetryPolicy,
    execute_with_retries,
    with_policy,
)


class Transient(Exception): ...
class Fatal(Exception): ...


def test_first_try_success_no_retries():
    outcome = execute_with_retries(lambda: 42)
    assert outcome.value == 42
    assert outcome.total_attempts == 1


def test_transient_then_success():
    state = {"calls": 0}
    def flaky():
        state["calls"] += 1
        if state["calls"] < 3:
            raise Transient()
        return "ok"
    outcome = execute_with_retries(flaky, sleep_fn=lambda d: None)
    assert outcome.value == "ok"
    assert outcome.total_attempts == 3
    assert not outcome.attempts[-1].error_type


def test_exhaustion_raises_with_last_error():
    def always_fails():
        raise Transient("down")
    with pytest.raises(ExhaustedRetriesError) as excinfo:
        execute_with_retries(always_fails, sleep_fn=lambda d: None)
    assert excinfo.value.attempts == 3
    assert isinstance(excinfo.value.last_error, Transient)


def test_fatal_exception_aborts_immediately():
    calls = {"n": 0}
    def fatal_only():
        calls["n"] += 1
        raise Fatal()
    policy = RetryPolicy(max_attempts=5, retryable_exceptions=(Transient,),
                         fatal_exceptions=(Fatal,))
    with pytest.raises(ExhaustedRetriesError):
        execute_with_retries(fatal_only, policy=policy, sleep_fn=lambda d: None)
    assert calls["n"] == 1


def test_non_retryable_exception_not_retried():
    calls = {"n": 0}
    def other_error():
        calls["n"] += 1
        raise ValueError("nope")
    policy = RetryPolicy(retryable_exceptions=(Transient,))
    with pytest.raises(ExhaustedRetriesError):
        execute_with_retries(other_error, policy=policy, sleep_fn=lambda d: None)
    assert calls["n"] == 1


def test_exponential_backoff_capped():
    policy = RetryPolicy(base_delay=0.1, exponential_base=2.0, max_delay=0.4, jitter_ratio=0.0)
    rng = random.Random(7)
    delays = [policy.compute_delay(i, rng) for i in range(6)]
    assert delays[0] == pytest.approx(0.1)
    assert delays[2] == pytest.approx(0.4)
    assert delays[5] == pytest.approx(0.4)


def test_jitter_keeps_delay_within_bounds():
    policy = RetryPolicy(base_delay=1.0, jitter_ratio=0.5, max_delay=10.0)
    rng = random.Random(11)
    for _ in range(50):
        delay = policy.compute_delay(0, rng)
        assert 0.5 <= delay <= 1.75


def test_invalid_policy_rejected():
    with pytest.raises(PolicyDefinitionError):
        RetryPolicy(max_attempts=0)
    with pytest.raises(PolicyDefinitionError):
        RetryPolicy(jitter_ratio=1.5)
    with pytest.raises(PolicyDefinitionError):
        RetryPolicy(base_delay=2.0, max_delay=1.0)


def test_total_delay_accumulates(monkeypatch):
    sleeps: list[float] = []
    state = {"n": 0}
    def twice_failing():
        state["n"] += 1
        if state["n"] < 3:
            raise Transient()
        return True
    policy = RetryPolicy(base_delay=0.5, jitter_ratio=0.0)
    outcome = execute_with_retries(twice_failing, policy=policy,
                                   sleep_fn=sleeps.append, rng=random.Random(1))
    assert len(sleeps) == 2
    assert sleeps[0] == pytest.approx(0.5)
    assert sleeps[1] == pytest.approx(1.0)
    assert outcome.total_delay == pytest.approx(1.5)


def test_decorator_form():
    policy = RetryPolicy(max_attempts=2, base_delay=0.01)
    runner = with_policy(policy, sleep_fn=lambda d: None)
    state = {"n": 0}
    def action():
        state["n"] += 1
        if state["n"] == 1:
            raise Transient()
        return "done"
    result = runner(action)
    assert result.value == "done"
