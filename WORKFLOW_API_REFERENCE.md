# Workflow Execution Engine API Reference

This document outlines the public API for the `WorkflowExecutionEngine` and its associated models under the `salesforce_ai_engineer.workflow` module.

## Core API

### `WorkflowExecutionEngine`

The central class orchestrating execution of an `ExecutionPlan`.

#### `__init__(agent_registry, recovery_agent, event_bus, memory_manager=None, state_manager=None, scheduler=None, default_policy=None)`
Instantiates the engine with its dependencies.
- `agent_registry`: Resolves target execution agents via names.
- `recovery_agent`: Handler invoked when task failures occur.
- `event_bus`: Subsystem to publish `LifecycleEvent` telemetry.
- `memory_manager`: Optional persistence module to store workflow snapshots.

#### `async execute_plan(plan, request, workflow_id=None, policy=None, resume_from=None) -> WorkflowExecutionResult`
Runs the given `ExecutionPlan` through to a terminal status (Success, Escalate, Failed).
- Automatically triggers checkpoints, emits events, and delegates execution based on the plan DAG.

#### `async pause(workflow_id: str) -> WorkflowProgress`
Requests a pause of the running workflow at the next scheduling boundary. It does not forcefully terminate running tasks.

#### `async resume(workflow_id: str) -> WorkflowExecutionResult`
Resumes a persisted (or paused) workflow execution starting from its latest memory snapshot.

#### `async cancel(workflow_id: str) -> WorkflowProgress`
Requests the execution to halt and transitions running tasks and pending tasks to a cancelled state. 

#### `async restart(workflow_id: str) -> WorkflowExecutionResult`
Wipes the execution traces, resets the task status to pending, increments the snapshot version, and starts the workflow afresh.

#### `async status(workflow_id: str) -> WorkflowProgress`
Retrieves the real-time or latest persisted progress for the given workflow ID.

---

## Policies and Strategies

### `WorkflowExecutionPolicy`
Configures limits and constraints for a workflow run.
- `max_parallel_tasks`: Int. Max parallel concurrent executing nodes (default 4).
- `task_timeout_seconds`: Float/None. Optional timeout for individual task executions.
- `fail_fast`: Bool. Halt remaining tasks upon encountering a failure (default True).
- `rollback_on_failure`: Bool. Start running inverse actions for completed nodes on failure (default True).
- `retry_policy`: `WorkflowRetryPolicy`. Custom backoff configurations.

### `WorkflowRetryPolicy`
- `max_attempts`: Int (default 2).
- `initial_backoff_seconds`: Float.
- `max_backoff_seconds`: Float.
- `backoff_multiplier`: Float (default 2.0).

### `TopologicalSchedulingStrategy`
Default DAG scheduler provided under `salesforce_ai_engineer.workflow.scheduler`. Complies with the `SchedulingStrategy` protocol, exposing `ready_tasks(plan, running_task_ids)` which safely guarantees all prerequisites are met before task execution.

---

## Output Models

### `WorkflowExecutionResult`
Returned upon completion. Includes:
- `status`: Final `WorkflowStatus`.
- `successful_tasks`, `failed_tasks`, `skipped_tasks`, `cancelled_tasks`.
- `metrics`: Dictionary of engine execution metrics (e.g. `duration_seconds`, `total_retries`).
- `traces`: Comprehensive dictionary of `TaskExecutionTrace` containing retry bounds, durations, and dependencies for each task.

### `TaskExecutionTrace`
- `state_transitions`: Array of `StateTransition` marking start, retry, failure, and end times.
- `retry_history`: Array of `RetryAttempt` recording discrete attempts.
- `execution_context`: The explicit payload and input data presented to the agent.
