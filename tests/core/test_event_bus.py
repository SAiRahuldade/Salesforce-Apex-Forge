from salesforce_ai_engineer.core import (
    Event,
    EventBus,
    EventHistoryQuery,
    EventPriority,
    LifecycleEvent,
)


async def test_event_bus_publishes_to_named_and_wildcard_handlers() -> None:
    bus = EventBus()
    received: list[Event] = []

    async def named_handler(event: Event) -> None:
        received.append(event)

    def wildcard_handler(event: Event) -> None:
        received.append(event)

    await bus.subscribe("agent.started", named_handler)
    await bus.subscribe("*", wildcard_handler)

    event = await bus.publish("agent.started", {"agent": "architect"})

    assert event.name == "agent.started"
    assert event.payload == {"agent": "architect"}
    assert received == [event, event]


async def test_event_bus_supports_lifecycle_metadata_and_history() -> None:
    bus = EventBus()
    received: list[Event] = []
    await bus.subscribe(LifecycleEvent.TASK_COMPLETED, lambda event: received.append(event))

    event = await bus.emit_lifecycle(
        LifecycleEvent.TASK_COMPLETED,
        workflow_id="workflow-1",
        task_id="task-1",
        correlation_id="corr-1",
        priority=EventPriority.HIGH,
        payload={"result": "ok"},
        source="orchestrator",
    )
    await bus.publish(
        LifecycleEvent.MEMORY_UPDATED,
        {"key": "hospital"},
        workflow_id="workflow-1",
        correlation_id="corr-1",
        priority=EventPriority.NORMAL,
    )

    history = await bus.history(
        EventHistoryQuery(workflow_id="workflow-1", min_priority=EventPriority.HIGH)
    )

    assert received == [event]
    assert event.workflow_id == "workflow-1"
    assert event.task_id == "task-1"
    assert event.correlation_id == "corr-1"
    assert event.priority == EventPriority.HIGH
    assert history == [event]
