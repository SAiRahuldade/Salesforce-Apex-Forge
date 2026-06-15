from salesforce_ai_engineer.core import RetryPolicy, retry


def test_retry_retries_until_success() -> None:
    calls = 0

    @retry(RetryPolicy(attempts=3, initial_delay=0, jitter=0))
    def flaky() -> str:
        nonlocal calls
        calls += 1
        if calls < 2:
            raise ValueError("not yet")
        return "ok"

    assert flaky() == "ok"
    assert calls == 2

