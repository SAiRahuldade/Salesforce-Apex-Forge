"""Memory-backed workflow persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from salesforce_ai_engineer.memory.manager import MemoryManager
from salesforce_ai_engineer.models.domain.memory import (
    MemoryCategory,
    MemoryMetadata,
    MemoryStatus,
    create_memory_record,
)
from salesforce_ai_engineer.workflow.models import TaskExecutionTrace, WorkflowSnapshot


class WorkflowPersistence:
    """Persists workflow snapshots and execution history through Memory Agent."""

    CREATED_BY = "workflow_execution_engine"

    def __init__(self, memory_manager: MemoryManager | None = None) -> None:
        self.memory_manager = memory_manager
        self._fallback_snapshots: dict[str, WorkflowSnapshot] = {}

    async def save_snapshot(self, snapshot: WorkflowSnapshot) -> None:
        """Save or update a workflow snapshot."""

        snapshot.updated_at = datetime.utcnow()
        if self.memory_manager is None:
            self._fallback_snapshots[snapshot.workflow_id] = snapshot.model_copy(deep=True)
            return

        await self._ensure_memory_open()
        existing_id = await self._find_snapshot_record_id(snapshot.workflow_id)
        payload = snapshot.model_dump(mode="json")
        if existing_id is None:
            record = create_memory_record(
                category=MemoryCategory.EXECUTION_METRIC,
                title=f"Workflow snapshot: {snapshot.workflow_id}",
                created_by=self.CREATED_BY,
                metric_name="workflow_snapshot",
                metric_value=float(snapshot.version),
                unit="version",
                agent_name=None,
                execution_id=snapshot.workflow_id,
                timewindow_start=snapshot.created_at,
                timewindow_end=snapshot.updated_at,
                tags_dict={
                    "workflow_id": snapshot.workflow_id,
                    "kind": "workflow_snapshot",
                },
                metadata=self._metadata(
                    {
                        "workflow_id": snapshot.workflow_id,
                        "snapshot": payload,
                    }
                ),
            )
            await self.memory_manager.store.create(record)
            return

        await self.memory_manager.store.update(
            existing_id,
            {
                "metric_value": float(snapshot.version),
                "timewindow_end": snapshot.updated_at,
                "metadata": self._metadata(
                    {
                        "workflow_id": snapshot.workflow_id,
                        "snapshot": payload,
                    }
                ).model_dump(mode="json"),
            },
            change_description=f"Workflow snapshot version {snapshot.version}",
            created_by=self.CREATED_BY,
        )

    async def load_snapshot(self, workflow_id: str) -> WorkflowSnapshot | None:
        """Load latest persisted snapshot for a workflow."""

        if self.memory_manager is None:
            snapshot = self._fallback_snapshots.get(workflow_id)
            return snapshot.model_copy(deep=True) if snapshot is not None else None

        await self._ensure_memory_open()
        records, _ = await self.memory_manager.store.list_by_category(
            MemoryCategory.EXECUTION_METRIC,
            status=MemoryStatus.ACTIVE,
            limit=10_000,
        )
        candidates = [
            record
            for record in records
            if getattr(record, "metric_name", None) == "workflow_snapshot"
            and getattr(record, "execution_id", None) == workflow_id
        ]
        if not candidates:
            return None
        latest = max(candidates, key=lambda record: getattr(record, "updated_at", datetime.min))
        raw = latest.metadata.custom.get("snapshot")
        if not isinstance(raw, dict):
            return None
        return WorkflowSnapshot.model_validate(raw)

    async def save_task_history(
        self,
        workflow_id: str,
        request: str,
        trace: TaskExecutionTrace,
        success: bool,
    ) -> None:
        """Append task execution history for analytics and recovery."""

        if self.memory_manager is None:
            return
        await self._ensure_memory_open()
        record = create_memory_record(
            category=MemoryCategory.EXECUTION_HISTORY,
            title=f"Task execution: {trace.task_id}",
            created_by=self.CREATED_BY,
            agent_name=trace.agent,
            execution_id=f"{workflow_id}:{trace.task_id}:{len(trace.retry_history)}",
            task_description=request,
            duration_seconds=trace.duration_seconds,
            success=success,
            error=trace.error,
            input_data=trace.execution_context,
            output_data=trace.output or {},
            resource_usage={},
            correlation_id=workflow_id,
            metadata=self._metadata(
                {
                    "workflow_id": workflow_id,
                    "task_trace": trace.model_dump(mode="json"),
                }
            ),
        )
        await self.memory_manager.store.create(record)

    async def archive_snapshot(self, workflow_id: str) -> None:
        """Mark a workflow snapshot archived."""

        if self.memory_manager is None:
            self._fallback_snapshots.pop(workflow_id, None)
            return
        existing_id = await self._find_snapshot_record_id(workflow_id)
        if existing_id is not None:
            await self.memory_manager.store.update(
                existing_id,
                {"status": MemoryStatus.ARCHIVED},
                change_description="Workflow archived",
                created_by=self.CREATED_BY,
            )

    async def _find_snapshot_record_id(self, workflow_id: str) -> str | None:
        if self.memory_manager is None:
            return None
        records, _ = await self.memory_manager.store.list_by_category(
            MemoryCategory.EXECUTION_METRIC,
            status=MemoryStatus.ACTIVE,
            limit=10_000,
        )
        for record in records:
            if (
                getattr(record, "metric_name", None) == "workflow_snapshot"
                and getattr(record, "execution_id", None) == workflow_id
            ):
                return record.id
        return None

    async def _ensure_memory_open(self) -> None:
        if self.memory_manager is not None and not await self.memory_manager.health_check():
            await self.memory_manager.store.open()

    def _metadata(self, custom: dict[str, Any]) -> MemoryMetadata:
        return MemoryMetadata(
            source=self.CREATED_BY,
            confidence=1.0,
            relevance=1.0,
            priority=8,
            custom=custom,
        )
