"""Asynchronous centralized event system.

The event bus is intentionally small at the boundary and rich in the event
model. Components publish immutable :class:`DomainEvent` records and subscribe
by event name without knowing about each other. A wildcard subscription using
``"*"`` receives every event.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from salesforce_ai_engineer.models.domain import (
    DomainEvent,
    EventHistoryQuery,
    EventPriority,
    LifecycleEvent,
)

Event = DomainEvent
EventHandler = Callable[[DomainEvent], None | Awaitable[None]]


class EventBus:
    """Async pub/sub event bus with bounded in-memory event history.

    The bus provides process-local asynchronous communication. It is suitable
    for local autonomous agents, API handlers, CLIs, tools, and tests. Delivery
    is sequential per published event, which preserves handler ordering and
    avoids hidden concurrency hazards inside subscribers.
    """

    def __init__(self, history_limit: int = 10_000) -> None:
        if history_limit <= 0:
            raise ValueError("history_limit must be greater than zero")
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._history: deque[DomainEvent] = deque(maxlen=history_limit)
        self._lock = asyncio.Lock()

    async def subscribe(self, event_name: str | LifecycleEvent, handler: EventHandler) -> None:
        """Subscribe a handler to an event name or ``"*"`` wildcard."""

        normalized_name = self._normalize_name(event_name)
        async with self._lock:
            if handler not in self._handlers[normalized_name]:
                self._handlers[normalized_name].append(handler)

    async def unsubscribe(self, event_name: str | LifecycleEvent, handler: EventHandler) -> None:
        """Remove a previously registered handler."""

        normalized_name = self._normalize_name(event_name)
        async with self._lock:
            if handler in self._handlers[normalized_name]:
                self._handlers[normalized_name].remove(handler)

    async def publish(
        self,
        event: DomainEvent | LifecycleEvent | str,
        payload: dict[str, Any] | None = None,
        *,
        priority: EventPriority = EventPriority.NORMAL,
        workflow_id: str | None = None,
        task_id: str | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        source: str = "system",
    ) -> DomainEvent:
        """Publish an event and return the immutable event record.

        Passing a string keeps the API lightweight for future agents. Passing a
        :class:`LifecycleEvent` standardizes names for common lifecycle facts.
        Passing a fully constructed :class:`DomainEvent` gives advanced callers
        complete control over metadata.
        """

        event_obj = self._coerce_event(
            event,
            payload=payload,
            priority=priority,
            workflow_id=workflow_id,
            task_id=task_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            source=source,
        )
        async with self._lock:
            self._history.append(event_obj)
            handlers = [
                *self._handlers.get(event_obj.name, []),
                *self._handlers.get("*", []),
            ]

        for handler in handlers:
            result = handler(event_obj)
            if result is not None:
                await result
        return event_obj

    async def emit_lifecycle(
        self,
        event: LifecycleEvent,
        *,
        payload: dict[str, Any] | None = None,
        priority: EventPriority = EventPriority.NORMAL,
        workflow_id: str | None = None,
        task_id: str | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        source: str = "system",
    ) -> DomainEvent:
        """Publish one of the standard lifecycle events."""

        return await self.publish(
            event,
            payload,
            priority=priority,
            workflow_id=workflow_id,
            task_id=task_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            source=source,
        )

    async def history(self, query: EventHistoryQuery | None = None) -> list[DomainEvent]:
        """Return event history filtered by structured query fields."""

        async with self._lock:
            events = list(self._history)

        if query is None:
            return events

        filtered = events
        if query.name is not None:
            filtered = [event for event in filtered if event.name == query.name]
        if query.workflow_id is not None:
            filtered = [event for event in filtered if event.workflow_id == query.workflow_id]
        if query.correlation_id is not None:
            filtered = [event for event in filtered if event.correlation_id == query.correlation_id]
        if query.source is not None:
            filtered = [event for event in filtered if event.source == query.source]
        if query.min_priority is not None:
            filtered = [event for event in filtered if event.priority >= query.min_priority]
        if query.limit is not None:
            filtered = filtered[-query.limit :]
        return filtered

    async def clear_history(self) -> None:
        """Clear in-memory history while keeping subscriptions intact."""

        async with self._lock:
            self._history.clear()

    def _coerce_event(
        self,
        event: DomainEvent | LifecycleEvent | str,
        *,
        payload: dict[str, Any] | None,
        priority: EventPriority,
        workflow_id: str | None,
        task_id: str | None,
        correlation_id: str | None,
        causation_id: str | None,
        source: str,
    ) -> DomainEvent:
        if isinstance(event, DomainEvent):
            return event
        if isinstance(event, LifecycleEvent):
            return DomainEvent.lifecycle(
                event,
                payload=payload,
                priority=priority,
                workflow_id=workflow_id,
                task_id=task_id,
                correlation_id=correlation_id,
                causation_id=causation_id,
                source=source,
            )
        return DomainEvent(
            name=event,
            payload=payload or {},
            priority=priority,
            workflow_id=workflow_id,
            task_id=task_id,
            correlation_id=correlation_id or str(uuid4()),
            causation_id=causation_id,
            source=source,
        )

    def _normalize_name(self, event_name: str | LifecycleEvent) -> str:
        if isinstance(event_name, LifecycleEvent):
            return event_name.value
        normalized = event_name.strip()
        if not normalized:
            raise ValueError("event_name cannot be empty")
        return normalized
