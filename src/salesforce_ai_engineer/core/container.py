"""Lightweight dependency injection container."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")
Factory = Callable[["Container"], Any]


class DependencyNotFoundError(KeyError):
    """Raised when a dependency is requested before registration."""


class Container:
    """Small service registry with singleton and factory lifetimes."""

    def __init__(self) -> None:
        self._singletons: dict[str, Any] = {}
        self._factories: dict[str, Factory] = {}

    def register_instance(self, key: str, instance: Any) -> None:
        self._singletons[key] = instance

    def register_factory(self, key: str, factory: Factory, *, singleton: bool = False) -> None:
        if singleton:
            self._factories[key] = self._singleton_factory(key, factory)
        else:
            self._factories[key] = factory

    def resolve(self, key: str, expected_type: type[T] | None = None) -> T:
        if key in self._singletons:
            value = self._singletons[key]
        elif key in self._factories:
            value = self._factories[key](self)
        else:
            raise DependencyNotFoundError(key)

        if expected_type is not None and not isinstance(value, expected_type):
            raise TypeError(f"Dependency {key!r} is not a {expected_type.__name__}")
        return value

    def has(self, key: str) -> bool:
        return key in self._singletons or key in self._factories

    def _singleton_factory(self, key: str, factory: Factory) -> Factory:
        def wrapped(container: Container) -> Any:
            if key not in self._singletons:
                self._singletons[key] = factory(container)
            return self._singletons[key]

        return wrapped

