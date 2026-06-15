"""
Memory Manager - High-level API for agents to interact with memory.

Provides a clean, agent-friendly interface for creating, reading, updating,
searching, and analyzing memory records. Coordinates versioning, relationships,
and integration with the event system.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4

from salesforce_ai_engineer.models.domain.memory import (
    MemoryRecord,
    MemoryCategory,
    MemoryStatus,
    MemorySearchQuery,
    MemoryTag,
    MemoryRelationship,
    MemoryVersion,
    create_memory_record,
)
from salesforce_ai_engineer.memory.store import (
    BaseMemoryStore,
    RecordNotFoundError,
    MemoryStoreOperationError,
)
from salesforce_ai_engineer.core.events import EventBus, Event


logger = logging.getLogger(__name__)


class MemoryManager:
    """
    High-level interface for memory operations.
    
    All agents should use this manager instead of accessing the store directly.
    The manager handles:
    - Record creation with proper initialization
    - Relationship management
    - Event emission
    - Logging and tracing
    - Common query patterns
    """
    
    def __init__(
        self,
        store: BaseMemoryStore,
        event_bus: Optional[EventBus] = None,
        logger_instance: Optional[logging.Logger] = None
    ):
        """
        Initialize memory manager.
        
        Args:
            store: MemoryStore implementation
            event_bus: Optional event bus for lifecycle events
            logger_instance: Optional logger instance
        """
        self.store = store
        self.event_bus = event_bus
        self.logger = logger_instance or logger
    
    # ===== CRUD Operations =====
    
    async def store_project_memory(
        self,
        title: str,
        key_insights: List[str],
        technical_stack: List[str],
        created_by: str,
        **kwargs
    ) -> str:
        """Store project-level knowledge."""
        record = create_memory_record(
            category=MemoryCategory.PROJECT_MEMORY,
            title=title,
            created_by=created_by,
            key_insights=key_insights,
            technical_stack=technical_stack,
            **kwargs
        )
        
        record_id = await self.store.create(record)
        await self._emit_event("memory.record_created", {
            "record_id": record_id,
            "category": MemoryCategory.PROJECT_MEMORY.value
        })
        return record_id
    
    async def store_workflow_history(
        self,
        workflow_id: str,
        workflow_type: str,
        workflow_status: str,
        duration_seconds: float,
        steps_executed: List[str],
        created_by: str,
        **kwargs
    ) -> str:
        """Store completed workflow information."""
        record = create_memory_record(
            category=MemoryCategory.WORKFLOW_HISTORY,
            title=f"Workflow: {workflow_type}",
            created_by=created_by,
            workflow_id=workflow_id,
            workflow_type=workflow_type,
            workflow_status=workflow_status,
            duration_seconds=duration_seconds,
            start_time=kwargs.pop("start_time", datetime.utcnow()),
            end_time=datetime.utcnow(),
            steps_executed=steps_executed,
            **kwargs
        )
        
        record_id = await self.store.create(record)
        await self._emit_event("memory.workflow_recorded", {
            "record_id": record_id,
            "workflow_id": workflow_id,
            "workflow_type": workflow_type
        })
        return record_id
    
    async def store_execution_history(
        self,
        agent_name: str,
        task_description: str,
        success: bool,
        duration_seconds: float,
        created_by: str,
        **kwargs
    ) -> str:
        """Store agent execution information."""
        record = create_memory_record(
            category=MemoryCategory.EXECUTION_HISTORY,
            title=f"Execution: {task_description}",
            created_by=created_by,
            agent_name=agent_name,
            execution_id=kwargs.pop("execution_id", str(uuid4())),
            task_description=task_description,
            success=success,
            duration_seconds=duration_seconds,
            **kwargs
        )
        
        record_id = await self.store.create(record)
        await self._emit_event("memory.execution_recorded", {
            "record_id": record_id,
            "agent_name": agent_name,
            "success": success
        })
        return record_id
    
    async def store_agent_interaction(
        self,
        initiator_agent: str,
        target_agent: str,
        interaction_type: str,
        request_data: Dict[str, Any],
        response_data: Dict[str, Any],
        success: bool,
        duration_seconds: float,
        created_by: str,
        **kwargs
    ) -> str:
        """Store inter-agent communication."""
        record = create_memory_record(
            category=MemoryCategory.AGENT_INTERACTION,
            title=f"Interaction: {initiator_agent} → {target_agent}",
            created_by=created_by,
            initiator_agent=initiator_agent,
            target_agent=target_agent,
            interaction_type=interaction_type,
            request_data=request_data,
            response_data=response_data,
            success=success,
            duration_seconds=duration_seconds,
            **kwargs
        )
        
        record_id = await self.store.create(record)
        await self._emit_event("memory.interaction_recorded", {
            "record_id": record_id,
            "initiator": initiator_agent,
            "target": target_agent
        })
        return record_id
    
    async def store_completed_task(
        self,
        task_type: str,
        task_id: str,
        agent_responsible: str,
        approach_used: str,
        result_summary: str,
        success: bool,
        duration_seconds: float,
        created_by: str,
        **kwargs
    ) -> str:
        """Store completed task information."""
        record = create_memory_record(
            category=MemoryCategory.COMPLETED_TASK,
            title=f"Task: {task_type}",
            created_by=created_by,
            task_type=task_type,
            task_id=task_id,
            agent_responsible=agent_responsible,
            approach_used=approach_used,
            result_summary=result_summary,
            success=success,
            duration_seconds=duration_seconds,
            **kwargs
        )
        
        record_id = await self.store.create(record)
        await self._emit_event("memory.task_completed", {
            "record_id": record_id,
            "task_type": task_type,
            "agent": agent_responsible
        })
        return record_id
    
    async def store_recovery_history(
        self,
        failure_id: str,
        failure_type: str,
        failure_description: str,
        recovery_strategy: str,
        recovery_steps: List[str],
        success: bool,
        time_to_recovery_seconds: float,
        created_by: str,
        **kwargs
    ) -> str:
        """Store failure recovery information."""
        record = create_memory_record(
            category=MemoryCategory.RECOVERY_HISTORY,
            title=f"Recovery: {failure_type}",
            created_by=created_by,
            failure_id=failure_id,
            failure_type=failure_type,
            failure_description=failure_description,
            recovery_strategy=recovery_strategy,
            recovery_steps=recovery_steps,
            recovery_success=success,
            time_to_recovery_seconds=time_to_recovery_seconds,
            **kwargs
        )
        
        record_id = await self.store.create(record)
        await self._emit_event("memory.recovery_recorded", {
            "record_id": record_id,
            "failure_type": failure_type,
            "recovery_success": success
        })
        return record_id
    
    async def store_known_error(
        self,
        error_type: str,
        error_message: str,
        severity: str,
        created_by: str,
        **kwargs
    ) -> str:
        """Store known error information."""
        record = create_memory_record(
            category=MemoryCategory.KNOWN_ERROR,
            title=f"Error: {error_type}",
            created_by=created_by,
            error_type=error_type,
            error_message=error_message,
            severity=severity,
            **kwargs
        )
        
        record_id = await self.store.create(record)
        await self._emit_event("memory.error_recorded", {
            "record_id": record_id,
            "error_type": error_type,
            "severity": severity
        })
        return record_id
    
    async def store_successful_fix(
        self,
        error_type: str,
        error_description: str,
        fix_description: str,
        fix_steps: List[str],
        time_to_fix_minutes: float,
        who_fixed: str,
        created_by: str,
        **kwargs
    ) -> str:
        """Store successful fix information."""
        record = create_memory_record(
            category=MemoryCategory.SUCCESSFUL_FIX,
            title=f"Fix: {error_type}",
            created_by=created_by,
            fix_id=str(uuid4()),
            error_type=error_type,
            error_description=error_description,
            fix_description=fix_description,
            fix_steps=fix_steps,
            time_to_fix_minutes=time_to_fix_minutes,
            who_fixed=who_fixed,
            **kwargs
        )
        
        record_id = await self.store.create(record)
        await self._emit_event("memory.fix_recorded", {
            "record_id": record_id,
            "error_type": error_type,
            "who_fixed": who_fixed
        })
        return record_id
    
    async def store_architecture_decision(
        self,
        decision_id: str,
        status: str,
        context: str,
        decision: str,
        rationale: str,
        created_by: str,
        **kwargs
    ) -> str:
        """Store architectural decision (ADR)."""
        record = create_memory_record(
            category=MemoryCategory.ARCHITECTURE_DECISION,
            title=f"ADR: {decision_id}",
            created_by=created_by,
            decision_id=decision_id,
            status=status,
            context=context,
            decision=decision,
            rationale=rationale,
            **kwargs
        )
        
        record_id = await self.store.create(record)
        await self._emit_event("memory.adr_recorded", {
            "record_id": record_id,
            "decision_id": decision_id,
            "status": status
        })
        return record_id
    
    async def store_coding_pattern(
        self,
        pattern_name: str,
        pattern_description: str,
        code_example: str,
        use_cases: List[str],
        created_by: str,
        **kwargs
    ) -> str:
        """Store successful coding pattern."""
        record = create_memory_record(
            category=MemoryCategory.CODING_PATTERN,
            title=f"Pattern: {pattern_name}",
            created_by=created_by,
            pattern_name=pattern_name,
            pattern_description=pattern_description,
            code_example=code_example,
            use_cases=use_cases,
            **kwargs
        )
        
        record_id = await self.store.create(record)
        await self._emit_event("memory.pattern_recorded", {
            "record_id": record_id,
            "pattern_name": pattern_name
        })
        return record_id
    
    async def store_deployment_history(
        self,
        deployment_id: str,
        environment: str,
        status: str,
        version_id: str,
        components_count: int,
        deployment_time_seconds: float,
        test_success_rate: float,
        code_coverage_percentage: float,
        created_by: str,
        **kwargs
    ) -> str:
        """Store deployment history record."""
        record = create_memory_record(
            category=MemoryCategory.DEPLOYMENT_HISTORY,
            title=f"Deployment: {deployment_id}",
            created_by=created_by,
            deployment_id=deployment_id,
            environment=environment,
            status=status,
            version_id=version_id,
            components_count=components_count,
            deployment_time_seconds=deployment_time_seconds,
            test_success_rate=test_success_rate,
            code_coverage_percentage=code_coverage_percentage,
            **kwargs
        )
        
        record_id = await self.store.create(record)
        await self._emit_event("memory.deployment_recorded", {
            "record_id": record_id,
            "deployment_id": deployment_id,
            "status": status
        })
        return record_id
    
    # ===== Retrieval Operations =====
    
    async def get_record(self, record_id: str) -> Optional[MemoryRecord]:
        """Get a specific record."""
        try:
            record = await self.store.read(record_id)
            return record
        except Exception as e:
            self.logger.error(f"Failed to get record {record_id}: {e}")
            return None
    
    async def find_similar_tasks(
        self,
        task_type: str,
        limit: int = 5
    ) -> List[MemoryRecord]:
        """Find similar previously completed tasks."""
        try:
            records, _ = await self.store.list_by_category(
                MemoryCategory.COMPLETED_TASK,
                status=MemoryStatus.ACTIVE,
                limit=limit
            )
            
            # Filter by task type
            matching = [
                r for r in records
                if hasattr(r, "task_type") and r.task_type == task_type
            ]
            
            return matching
        except Exception as e:
            self.logger.error(f"Failed to find similar tasks: {e}")
            return []
    
    async def find_past_errors(
        self,
        error_type: str,
        limit: int = 10
    ) -> List[MemoryRecord]:
        """Find past occurrences of specific error type."""
        try:
            records, _ = await self.store.list_by_category(
                MemoryCategory.KNOWN_ERROR,
                status=MemoryStatus.ACTIVE,
                limit=limit
            )
            
            matching = [
                r for r in records
                if hasattr(r, "error_type") and r.error_type == error_type
            ]
            
            return matching
        except Exception as e:
            self.logger.error(f"Failed to find past errors: {e}")
            return []
    
    async def find_fixes_for_error(
        self,
        error_type: str,
        limit: int = 5
    ) -> List[MemoryRecord]:
        """Find successful fixes for specific error type."""
        try:
            records, _ = await self.store.list_by_category(
                MemoryCategory.SUCCESSFUL_FIX,
                status=MemoryStatus.ACTIVE,
                limit=limit
            )
            
            matching = [
                r for r in records
                if hasattr(r, "error_type") and r.error_type == error_type
            ]
            
            return sorted(
                matching,
                key=lambda r: getattr(r, "time_to_fix_minutes", float("inf"))
            )
        except Exception as e:
            self.logger.error(f"Failed to find fixes: {e}")
            return []
    
    async def search_memory(
        self,
        keywords: Optional[List[str]] = None,
        category: Optional[MemoryCategory] = None,
        tags: Optional[List[str]] = None,
        created_by: Optional[str] = None,
        limit: int = 50
    ) -> List[MemoryRecord]:
        """Search memory records."""
        try:
            query = MemorySearchQuery(
                keywords=keywords,
                category=category,
                tags=tags,
                created_by=created_by,
                limit=limit
            )
            
            return await self.store.search(query)
        except Exception as e:
            self.logger.error(f"Search failed: {e}")
            return []
    
    # ===== Relationship Operations =====
    
    async def relate_records(
        self,
        source_id: str,
        target_id: str,
        relationship_type: str,
        bidirectional: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create relationship between two records."""
        try:
            relationship = MemoryRelationship(
                source_id=source_id,
                target_id=target_id,
                relationship_type=relationship_type,
                bidirectional=bidirectional,
                metadata=metadata or {}
            )
            
            relationship_id = await self.store.create_relationship(relationship)
            
            await self._emit_event("memory.relationship_created", {
                "relationship_id": relationship_id,
                "source_id": source_id,
                "target_id": target_id,
                "type": relationship_type
            })
            
            return relationship_id
        except Exception as e:
            self.logger.error(f"Failed to create relationship: {e}")
            raise
    
    async def get_related_records(
        self,
        record_id: str,
        relationship_type: Optional[str] = None,
        depth: int = 1
    ) -> List[MemoryRecord]:
        """Get records related to a specific record."""
        try:
            return await self.store.find_related_records(
                record_id,
                relationship_type=relationship_type,
                depth=depth
            )
        except Exception as e:
            self.logger.error(f"Failed to get related records: {e}")
            return []
    
    # ===== Tagging Operations =====
    
    async def tag_record(
        self,
        record_id: str,
        tags: List[str]
    ) -> None:
        """Add tags to a record."""
        try:
            await self.store.add_tags(record_id, tags)
            await self._emit_event("memory.record_tagged", {
                "record_id": record_id,
                "tags": tags
            })
        except Exception as e:
            self.logger.error(f"Failed to tag record: {e}")
            raise
    
    async def find_by_tags(
        self,
        tags: List[str],
        operator: str = "and"
    ) -> List[MemoryRecord]:
        """Find records with specific tags."""
        try:
            return await self.store.find_by_tags(tags, operator=operator)
        except Exception as e:
            self.logger.error(f"Failed to find by tags: {e}")
            return []
    
    # ===== Analytics & Statistics =====
    
    async def get_agent_stats(self, agent_name: str) -> Dict[str, Any]:
        """Get statistics for a specific agent."""
        try:
            records, total = await self.store.list_by_creator(agent_name)
            
            stats = {
                "agent_name": agent_name,
                "total_records": total,
                "records_by_category": {},
                "success_rate": 0.0,
                "total_duration_seconds": 0.0
            }
            
            success_count = 0
            total_duration = 0.0
            
            for record in records:
                category = record.category.value
                stats["records_by_category"][category] = \
                    stats["records_by_category"].get(category, 0) + 1
                
                if hasattr(record, "success"):
                    if record.success:
                        success_count += 1
                
                if hasattr(record, "duration_seconds"):
                    total_duration += record.duration_seconds
            
            if total > 0:
                stats["success_rate"] = success_count / total
                stats["total_duration_seconds"] = total_duration
            
            return stats
        except Exception as e:
            self.logger.error(f"Failed to get agent stats: {e}")
            return {}
    
    async def get_system_stats(self) -> Dict[str, Any]:
        """Get overall system statistics."""
        try:
            return await self.store.get_storage_stats()
        except Exception as e:
            self.logger.error(f"Failed to get system stats: {e}")
            return {}
    
    async def get_task_success_rate(
        self,
        task_type: Optional[str] = None
    ) -> float:
        """Get success rate for tasks."""
        try:
            records, _ = await self.store.list_by_category(
                MemoryCategory.COMPLETED_TASK,
                limit=10000
            )
            
            if not records:
                return 0.0
            
            if task_type:
                records = [
                    r for r in records
                    if hasattr(r, "task_type") and r.task_type == task_type
                ]
            
            if not records:
                return 0.0
            
            success_count = sum(
                1 for r in records
                if hasattr(r, "success") and r.success
            )
            
            return success_count / len(records)
        except Exception as e:
            self.logger.error(f"Failed to get success rate: {e}")
            return 0.0
    
    # ===== Version Management =====
    
    async def get_record_history(
        self,
        record_id: str,
        limit: int = 10
    ) -> List[MemoryVersion]:
        """Get version history for a record."""
        try:
            return await self.store.get_history(record_id, limit=limit)
        except Exception as e:
            self.logger.error(f"Failed to get history: {e}")
            return []
    
    async def restore_record(
        self,
        record_id: str,
        version_number: int
    ) -> Optional[MemoryRecord]:
        """Restore record to previous version."""
        try:
            record = await self.store.restore_version(record_id, version_number)
            await self._emit_event("memory.record_restored", {
                "record_id": record_id,
                "version_number": version_number
            })
            return record
        except Exception as e:
            self.logger.error(f"Failed to restore record: {e}")
            raise
    
    # ===== Lifecycle =====
    
    async def health_check(self) -> bool:
        """Check if memory store is healthy."""
        try:
            return await self.store.health_check()
        except Exception:
            return False
    
    async def cleanup_expired(self) -> int:
        """Clean up expired records."""
        try:
            count = await self.store.clear_expired()
            await self._emit_event("memory.cleanup_completed", {
                "records_cleared": count
            })
            return count
        except Exception as e:
            self.logger.error(f"Cleanup failed: {e}")
            return 0
    
    # ===== Internal Helpers =====
    
    async def _emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Emit event if event bus is available."""
        if self.event_bus:
            try:
                event = Event(type=event_type, data=data)
                await self.event_bus.emit(event)
            except Exception as e:
                self.logger.warning(f"Failed to emit event: {e}")
