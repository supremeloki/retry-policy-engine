# retry-policy-engine

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Declarative retry policies with exponential backoff, jitter, exception classification, and a full attempt trace — because "just retry it" is how 3 a.m. outages start.

## 🚀 Overview

Retrying blindly hides real failures; never retrying turns transient blips into incidents. `retry-policy-engine` makes the strategy explicit: a frozen `RetryPolicy` declares attempt count, backoff curve, jitter ratio, and which exceptions are *retryable* vs *fatal*. Execution returns a `RetryOutcome` with every attempt recorded — delays, error types, outcomes — so flaky integrations become debuggable instead of mysterious.

## ✨ Features

- **Frozen policy dataclass:** invalid configs (0 attempts, inverted delay bounds, bad jitter) raise at construction
- **Exponential backoff with cap:** `base × base^n` clamped to `max_delay`
- **Full-jitter support:** bounded randomization to avoid thundering-herd sync
- **Exception classification:** `fatal` aborts immediately · `retryable` retries · anything else is `non-retryable` and stops — no blanket `except Exception`
- **Attempt trace:** every try recorded as frozen `Attempt(index, delay_before, outcome, error_type)`
- **Injectable clock + RNG:** deterministic tests via `sleep_fn`/`rng` parameters
- **Decorator form:** `with_policy(policy)` wraps any callable
- **Zero dependencies**

## 🚧 Structure

```
retry-policy-engine/
├── src/retry_engine/
│   ├── __init__.py
│   └── core.py
├── tests/
│   └── test_core.py
├── README.md
└── pyproject.toml
```

## 📦 Installation

```bash
git clone https://github.com/supremeloki/retry-policy-engine.git
cd retry-policy-engine
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

## 📋 Requirements

- Python 3.11+
- No runtime dependencies

## 🏃 Quick Start

```python
from retry_engine import RetryPolicy, execute_with_retries

class Transient(Exception): ...
class Fatal(Exception): ...

policy = RetryPolicy(
    max_attempts=5,
    base_delay=0.2,
    max_delay=3.0,
    jitter_ratio=0.25,
    retryable_exceptions=(Transient,),
    fatal_exceptions=(Fatal,),
)

outcome = execute_with_retries(flaky_api_call, policy=policy)
if outcome.ok:
    print(f"got {outcome.value} after {outcome.total_attempts} tries")
```

### Decorator style

```python
from retry_engine import with_policy

@with_policy(RetryPolicy(max_attempts=3))
def send_webhook():
    ...
```

## 🔧 Error Handling

```text
RetryError
├── PolicyDefinitionError   # malformed policy (caught at construction)
└── ExhaustedRetriesError   # .attempts used + .last_error preserved
```

## 🧪 Testing

```bash
pytest tests/ -v
```

## 📝 Code Quality

- Full type hints (`X | None` style), generic `RetryOutcome[T]`, frozen dataclasses
- Zero comments — names carry the meaning
- Deterministic tests: inject fake sleep + seeded Random

## 📄 License

MIT — see [LICENSE](LICENSE).

## 👤 Author

**Kooroush Masoumi**

---

⭐ Star this repo if you find it useful!
