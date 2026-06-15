import pytest

from salesforce_ai_engineer.core import Container, DependencyNotFoundError


def test_container_resolves_singleton_factory_once() -> None:
    container = Container()
    calls = 0

    def factory(_: Container) -> object:
        nonlocal calls
        calls += 1
        return object()

    container.register_factory("service", factory, singleton=True)

    first = container.resolve("service")
    second = container.resolve("service")

    assert first is second
    assert calls == 1


def test_container_raises_for_missing_dependency() -> None:
    container = Container()

    with pytest.raises(DependencyNotFoundError):
        container.resolve("missing")

