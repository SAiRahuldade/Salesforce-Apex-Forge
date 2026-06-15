"""
Comprehensive test suite for the Memory System.

Tests all functionality including CRUD, search, versioning, relationships,
and concurrent operations.
"""

import pytest
import asyncio
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from typing import List

from salesforce_ai_engineer.models.domain.memory import (
    MemoryCategory,
    MemoryStatus,
    MemoryTag,
    MemoryMetadata,
    ProjectMemory,
    WorkflowHistory,
    ExecutionHistory,
    CompletedTask,
    KnownError,
    SuccessfulFix,
    MemoryRelationship,
)
from salesforce_ai_engineer.memory import (
    SQLiteMemoryStore,
    MemoryManager,
    RecordNotFoundError,
    RecordAlreadyExistsError,
    MemoryStoreOperationError,
)


@pytest.fixture
async def memory_store():
    """Create temporary SQLite memory store."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "memory.db"
        store = SQLiteMemoryStore(db_path)
        await store.open()
        yield store
        await store.close()


@pytest.fixture
async def memory_manager(memory_store):
    """Create memory manager."""
    return MemoryManager(memory_store)


@pytest.fixture
def sample_project_memory():
    """Sample project memory record."""
    return ProjectMemory(
        category=MemoryCategory.PROJECT_MEMORY,
        title="AI Agent System",
        description="Multi-agent AI system with memory",
        content={"type": "project"},
        created_by="test_agent",
        metadata=MemoryMetadata(source="test"),
        key_insights=["Modular design", "Event-driven"],
        technical_stack=["Python", "SQLite", "asyncio"],
        architecture_components=["Agent", "Memory", "Tools"],
        constraints=["Thread-safe"],
        goals=["Production-ready", "Extensible"]
    )


@pytest.fixture
def sample_execution_history():
    """Sample execution history record."""
    return ExecutionHistory(
        category=MemoryCategory.EXECUTION_HISTORY,
        title="Task Execution",
        description="Agent execution record",
        content={"type": "execution"},
        created_by="orchestrator",
        metadata=MemoryMetadata(source="orchestrator"),
        agent_name="test_agent",
        execution_id="exec-001",
        task_description="Process data",
        duration_seconds=1.5,
        success=True,
        error=None,
        input_data={"query": "test"},
        output_data={"result": "success"},
        resource_usage={"cpu": 0.2, "memory": 50}
    )


# ===== CRUD Tests =====

class TestMemoryCRUD:
    """Test CRUD operations."""
    
    @pytest.mark.asyncio
    async def test_create_record(self, memory_store, sample_project_memory):
        """Test creating a memory record."""
        record_id = await memory_store.create(sample_project_memory)
        assert record_id == sample_project_memory.id
        
        # Verify it was stored
        retrieved = await memory_store.read(record_id)
        assert retrieved is not None
        assert retrieved.title == sample_project_memory.title
    
    @pytest.mark.asyncio
    async def test_create_duplicate_fails(self, memory_store, sample_project_memory):
        """Test that creating duplicate record fails."""
        await memory_store.create(sample_project_memory)
        
        with pytest.raises(RecordAlreadyExistsError):
            await memory_store.create(sample_project_memory)
    
    @pytest.mark.asyncio
    async def test_read_nonexistent(self, memory_store):
        """Test reading nonexistent record."""
        record = await memory_store.read("nonexistent")
        assert record is None
    
    @pytest.mark.asyncio
    async def test_read_many(self, memory_store, sample_project_memory, sample_execution_history):
        """Test reading multiple records."""
        id1 = await memory_store.create(sample_project_memory)
        id2 = await memory_store.create(sample_execution_history)
        
        records = await memory_store.read_many([id1, id2])
        assert len(records) == 2
        assert records[0].id == id1
        assert records[1].id == id2
    
    @pytest.mark.asyncio
    async def test_update_record(self, memory_store, sample_project_memory):
        """Test updating a record."""
        record_id = await memory_store.create(sample_project_memory)
        
        updated = await memory_store.update(
            record_id,
            {"title": "Updated Title", "description": "Updated description"},
            change_description="Updated title and description",
            created_by="test"
        )
        
        assert updated.title == "Updated Title"
        assert updated.description == "Updated description"
        
        # Verify in storage
        retrieved = await memory_store.read(record_id)
        assert retrieved.title == "Updated Title"
    
    @pytest.mark.asyncio
    async def test_update_nonexistent_fails(self, memory_store):
        """Test updating nonexistent record fails."""
        with pytest.raises(RecordNotFoundError):
            await memory_store.update("nonexistent", {"title": "new"})
    
    @pytest.mark.asyncio
    async def test_delete_record(self, memory_store, sample_project_memory):
        """Test soft deleting a record."""
        record_id = await memory_store.create(sample_project_memory)
        
        await memory_store.delete(record_id, soft=True)
        
        # Should still exist but marked deleted
        retrieved = await memory_store.read(record_id)
        assert retrieved is not None
        assert retrieved.status == MemoryStatus.DELETED
    
    @pytest.mark.asyncio
    async def test_exists(self, memory_store, sample_project_memory):
        """Test checking record existence."""
        record_id = await memory_store.create(sample_project_memory)
        
        assert await memory_store.exists(record_id)
        assert not await memory_store.exists("nonexistent")


# ===== Search & Filter Tests =====

class TestMemorySearch:
    """Test search and filter operations."""
    
    @pytest.mark.asyncio
    async def test_search_by_keywords(self, memory_manager):
        """Test searching by keywords."""
        id1 = await memory_manager.store_project_memory(
            title="Python Development",
            key_insights=["Async programming", "Type hints"],
            technical_stack=["Python", "asyncio"],
            created_by="test"
        )
        
        results = await memory_manager.search_memory(keywords=["Python"])
        assert len(results) > 0
        assert any(r.id == id1 for r in results)
    
    @pytest.mark.asyncio
    async def test_search_by_category(self, memory_manager):
        """Test filtering search by category."""
        id1 = await memory_manager.store_execution_history(
            agent_name="agent1",
            task_description="Task A",
            success=True,
            duration_seconds=1.0,
            created_by="test"
        )
        
        results = await memory_manager.search_memory(
            category=MemoryCategory.EXECUTION_HISTORY
        )
        assert len(results) > 0
        assert any(r.id == id1 for r in results)
    
    @pytest.mark.asyncio
    async def test_search_by_creator(self, memory_manager):
        """Test filtering by creator."""
        id1 = await memory_manager.store_completed_task(
            task_type="DataProcessing",
            task_id="task-001",
            agent_responsible="agent1",
            approach_used="MapReduce",
            result_summary="Success",
            success=True,
            duration_seconds=5.0,
            created_by="agent1"
        )
        
        results = await memory_manager.search_memory(created_by="agent1")
        assert len(results) > 0
        assert any(r.id == id1 for r in results)


# ===== Tagging Tests =====

class TestMemoryTags:
    """Test tagging operations."""
    
    @pytest.mark.asyncio
    async def test_add_tags(self, memory_store, sample_project_memory):
        """Test adding tags to a record."""
        record_id = await memory_store.create(sample_project_memory)
        
        await memory_store.add_tags(record_id, ["important", "production"])
        
        retrieved = await memory_store.read(record_id)
        tag_names = [t.name for t in retrieved.tags]
        assert "important" in tag_names
        assert "production" in tag_names
    
    @pytest.mark.asyncio
    async def test_find_by_tags(self, memory_store, sample_project_memory, sample_execution_history):
        """Test finding records by tags."""
        id1 = await memory_store.create(sample_project_memory)
        id2 = await memory_store.create(sample_execution_history)
        
        await memory_store.add_tags(id1, ["critical", "system"])
        await memory_store.add_tags(id2, ["critical"])
        
        # Find records with "critical" tag
        results = await memory_store.find_by_tags(["critical"])
        assert len(results) == 2
    
    @pytest.mark.asyncio
    async def test_list_all_tags(self, memory_store, sample_project_memory, sample_execution_history):
        """Test listing all tags."""
        id1 = await memory_store.create(sample_project_memory)
        id2 = await memory_store.create(sample_execution_history)
        
        await memory_store.add_tags(id1, ["tag1", "tag2"])
        await memory_store.add_tags(id2, ["tag2", "tag3"])
        
        all_tags = await memory_store.list_all_tags()
        assert "tag1" in all_tags
        assert "tag2" in all_tags
        assert "tag3" in all_tags


# ===== Versioning Tests =====

class TestMemoryVersioning:
    """Test versioning operations."""
    
    @pytest.mark.asyncio
    async def test_get_history(self, memory_store, sample_project_memory):
        """Test getting version history."""
        record_id = await memory_store.create(sample_project_memory)
        
        # Make updates
        await memory_store.update(
            record_id,
            {"title": "Updated 1"},
            change_description="First update",
            created_by="test"
        )
        await memory_store.update(
            record_id,
            {"title": "Updated 2"},
            change_description="Second update",
            created_by="test"
        )
        
        history = await memory_store.get_history(record_id)
        assert len(history) >= 2
        assert history[0].change_type == "update"
    
    @pytest.mark.asyncio
    async def test_restore_version(self, memory_store, sample_project_memory):
        """Test restoring to previous version."""
        record_id = await memory_store.create(sample_project_memory)
        original_title = sample_project_memory.title
        
        await memory_store.update(
            record_id,
            {"title": "New Title"},
            change_description="Changed title",
            created_by="test"
        )
        
        # Get history and restore
        history = await memory_store.get_history(record_id)
        # Should be at version 1 (the first update)
        restored = await memory_store.restore_version(record_id, 1)
        
        assert restored.title == original_title


# ===== Relationship Tests =====

class TestMemoryRelationships:
    """Test relationship operations."""
    
    @pytest.mark.asyncio
    async def test_create_relationship(self, memory_store, sample_project_memory, sample_execution_history):
        """Test creating relationships."""
        id1 = await memory_store.create(sample_project_memory)
        id2 = await memory_store.create(sample_execution_history)
        
        rel_id = await memory_store.create_relationship(
            MemoryRelationship(
                source_id=id1,
                target_id=id2,
                relationship_type="related_to"
            )
        )
        
        assert rel_id is not None
    
    @pytest.mark.asyncio
    async def test_get_relationships(self, memory_store, sample_project_memory, sample_execution_history):
        """Test retrieving relationships."""
        id1 = await memory_store.create(sample_project_memory)
        id2 = await memory_store.create(sample_execution_history)
        
        await memory_store.create_relationship(
            MemoryRelationship(
                source_id=id1,
                target_id=id2,
                relationship_type="related_to"
            )
        )
        
        rels = await memory_store.get_relationships(id1, direction="outgoing")
        assert len(rels) == 1
        assert rels[0].target_id == id2
    
    @pytest.mark.asyncio
    async def test_find_related_records(self, memory_store, sample_project_memory, sample_execution_history):
        """Test finding related records."""
        id1 = await memory_store.create(sample_project_memory)
        id2 = await memory_store.create(sample_execution_history)
        
        await memory_store.create_relationship(
            MemoryRelationship(
                source_id=id1,
                target_id=id2,
                relationship_type="related_to"
            )
        )
        
        related = await memory_store.find_related_records(id1)
        assert len(related) == 1
        assert related[0].id == id2


# ===== Analytics Tests =====

class TestMemoryAnalytics:
    """Test analytics operations."""
    
    @pytest.mark.asyncio
    async def test_count_by_category(self, memory_manager):
        """Test counting records by category."""
        await memory_manager.store_execution_history(
            agent_name="agent1",
            task_description="Task A",
            success=True,
            duration_seconds=1.0,
            created_by="test"
        )
        
        await memory_manager.store_execution_history(
            agent_name="agent2",
            task_description="Task B",
            success=False,
            duration_seconds=2.0,
            created_by="test"
        )
        
        store = memory_manager.store
        counts = await store.count_by_category()
        
        assert MemoryCategory.EXECUTION_HISTORY.value in counts
        assert counts[MemoryCategory.EXECUTION_HISTORY.value] == 2
    
    @pytest.mark.asyncio
    async def test_get_total_records(self, memory_manager):
        """Test getting total record count."""
        await memory_manager.store_execution_history(
            agent_name="agent1",
            task_description="Task A",
            success=True,
            duration_seconds=1.0,
            created_by="test"
        )
        
        await memory_manager.store_execution_history(
            agent_name="agent2",
            task_description="Task B",
            success=False,
            duration_seconds=2.0,
            created_by="test"
        )
        
        store = memory_manager.store
        total = await store.get_total_records()
        assert total >= 2
    
    @pytest.mark.asyncio
    async def test_get_storage_stats(self, memory_manager):
        """Test getting storage statistics."""
        await memory_manager.store_execution_history(
            agent_name="agent1",
            task_description="Task A",
            success=True,
            duration_seconds=1.0,
            created_by="test"
        )
        
        store = memory_manager.store
        stats = await store.get_storage_stats()
        
        assert "total_records" in stats
        assert "by_category" in stats
        assert "by_status" in stats
        assert "by_creator" in stats


# ===== Manager API Tests =====

class TestMemoryManager:
    """Test high-level memory manager API."""
    
    @pytest.mark.asyncio
    async def test_store_project_memory(self, memory_manager):
        """Test storing project memory."""
        record_id = await memory_manager.store_project_memory(
            title="AI System",
            key_insights=["Modular", "Extensible"],
            technical_stack=["Python"],
            created_by="test"
        )
        
        assert record_id is not None
        record = await memory_manager.get_record(record_id)
        assert record.title == "AI System"
    
    @pytest.mark.asyncio
    async def test_store_workflow_history(self, memory_manager):
        """Test storing workflow history."""
        record_id = await memory_manager.store_workflow_history(
            workflow_id="wf-001",
            workflow_type="DataProcessing",
            workflow_status="completed",
            duration_seconds=10.0,
            steps_executed=["step1", "step2"],
            created_by="test"
        )
        
        assert record_id is not None
    
    @pytest.mark.asyncio
    async def test_find_similar_tasks(self, memory_manager):
        """Test finding similar tasks."""
        id1 = await memory_manager.store_completed_task(
            task_type="DataProcessing",
            task_id="task-001",
            agent_responsible="agent1",
            approach_used="MapReduce",
            result_summary="Success",
            success=True,
            duration_seconds=5.0,
            created_by="agent1"
        )
        
        id2 = await memory_manager.store_completed_task(
            task_type="DataProcessing",
            task_id="task-002",
            agent_responsible="agent2",
            approach_used="Streaming",
            result_summary="Success",
            success=True,
            duration_seconds=3.0,
            created_by="agent2"
        )
        
        similar = await memory_manager.find_similar_tasks("DataProcessing")
        assert len(similar) >= 2
    
    @pytest.mark.asyncio
    async def test_find_past_errors(self, memory_manager):
        """Test finding past errors."""
        id1 = await memory_manager.store_known_error(
            error_type="TimeoutError",
            error_message="Request timed out",
            severity="high",
            created_by="test"
        )
        
        errors = await memory_manager.find_past_errors("TimeoutError")
        assert len(errors) >= 1
        assert any(e.id == id1 for e in errors)
    
    @pytest.mark.asyncio
    async def test_find_fixes_for_error(self, memory_manager):
        """Test finding fixes for errors."""
        fix_id = await memory_manager.store_successful_fix(
            error_type="TimeoutError",
            error_description="Request timed out",
            fix_description="Increased timeout value",
            fix_steps=["Update config", "Restart service"],
            time_to_fix_minutes=15.0,
            who_fixed="engineer1",
            created_by="test"
        )
        
        fixes = await memory_manager.find_fixes_for_error("TimeoutError")
        assert len(fixes) >= 1
    
    @pytest.mark.asyncio
    async def test_relate_records(self, memory_manager):
        """Test creating record relationships."""
        id1 = await memory_manager.store_project_memory(
            title="Project A",
            key_insights=["insight1"],
            technical_stack=["Python"],
            created_by="test"
        )
        
        id2 = await memory_manager.store_execution_history(
            agent_name="agent1",
            task_description="Execute",
            success=True,
            duration_seconds=1.0,
            created_by="test"
        )
        
        rel_id = await memory_manager.relate_records(
            id1,
            id2,
            "implemented_in"
        )
        
        assert rel_id is not None
    
    @pytest.mark.asyncio
    async def test_get_related_records(self, memory_manager):
        """Test retrieving related records."""
        id1 = await memory_manager.store_project_memory(
            title="Project A",
            key_insights=["insight1"],
            technical_stack=["Python"],
            created_by="test"
        )
        
        id2 = await memory_manager.store_execution_history(
            agent_name="agent1",
            task_description="Execute",
            success=True,
            duration_seconds=1.0,
            created_by="test"
        )
        
        await memory_manager.relate_records(id1, id2, "executed_in")
        
        related = await memory_manager.get_related_records(id1)
        assert len(related) >= 1
        assert any(r.id == id2 for r in related)
    
    @pytest.mark.asyncio
    async def test_tag_record(self, memory_manager):
        """Test tagging records."""
        record_id = await memory_manager.store_project_memory(
            title="Project A",
            key_insights=["insight1"],
            technical_stack=["Python"],
            created_by="test"
        )
        
        await memory_manager.tag_record(record_id, ["important", "system"])
        
        record = await memory_manager.get_record(record_id)
        tag_names = [t.name for t in record.tags]
        assert "important" in tag_names
        assert "system" in tag_names
    
    @pytest.mark.asyncio
    async def test_get_agent_stats(self, memory_manager):
        """Test getting agent statistics."""
        await memory_manager.store_execution_history(
            agent_name="agent1",
            task_description="Task A",
            success=True,
            duration_seconds=1.0,
            created_by="agent1"
        )
        
        await memory_manager.store_execution_history(
            agent_name="agent1",
            task_description="Task B",
            success=False,
            duration_seconds=2.0,
            created_by="agent1"
        )
        
        stats = await memory_manager.get_agent_stats("agent1")
        
        assert stats["agent_name"] == "agent1"
        assert stats["total_records"] >= 2
    
    @pytest.mark.asyncio
    async def test_get_system_stats(self, memory_manager):
        """Test getting system statistics."""
        await memory_manager.store_execution_history(
            agent_name="agent1",
            task_description="Task A",
            success=True,
            duration_seconds=1.0,
            created_by="test"
        )
        
        stats = await memory_manager.get_system_stats()
        
        assert "total_records" in stats
        assert stats["total_records"] >= 1


# ===== Concurrent Access Tests =====

class TestMemoryConcurrency:
    """Test concurrent memory operations."""
    
    @pytest.mark.asyncio
    async def test_concurrent_writes(self, memory_store):
        """Test concurrent record creation."""
        async def create_record(i):
            record = ProjectMemory(
                category=MemoryCategory.PROJECT_MEMORY,
                title=f"Project {i}",
                content={"index": i},
                created_by=f"agent_{i}",
                metadata=MemoryMetadata(source="test"),
                key_insights=[],
                technical_stack=[],
                architecture_components=[],
                constraints=[],
                goals=[]
            )
            return await memory_store.create(record)
        
        # Create 10 records concurrently
        tasks = [create_record(i) for i in range(10)]
        record_ids = await asyncio.gather(*tasks)
        
        assert len(record_ids) == 10
        assert len(set(record_ids)) == 10  # All unique
    
    @pytest.mark.asyncio
    async def test_concurrent_reads(self, memory_store, sample_project_memory):
        """Test concurrent record reading."""
        record_id = await memory_store.create(sample_project_memory)
        
        async def read_record():
            return await memory_store.read(record_id)
        
        # Read same record concurrently
        tasks = [read_record() for _ in range(10)]
        records = await asyncio.gather(*tasks)
        
        assert len(records) == 10
        assert all(r is not None for r in records)
        assert all(r.id == record_id for r in records)


# ===== Error Handling Tests =====

class TestMemoryErrorHandling:
    """Test error handling."""
    
    @pytest.mark.asyncio
    async def test_invalid_category(self):
        """Test handling invalid category."""
        with pytest.raises(ValueError):
            from salesforce_ai_engineer.models.domain.memory import create_memory_record
            create_memory_record(
                category="invalid_category",  # type: ignore
                title="Test",
                created_by="test"
            )
    
    @pytest.mark.asyncio
    async def test_health_check(self, memory_store):
        """Test health check."""
        health = await memory_store.health_check()
        assert health is True
    
    @pytest.mark.asyncio
    async def test_cleanup_expired(self, memory_store):
        """Test clearing expired records."""
        # Create record with TTL
        record = ProjectMemory(
            category=MemoryCategory.PROJECT_MEMORY,
            title="Temp Project",
            content={},
            created_by="test",
            metadata=MemoryMetadata(
                source="test",
                ttl_seconds=1  # 1 second TTL
            ),
            key_insights=[],
            technical_stack=[],
            architecture_components=[],
            constraints=[],
            goals=[]
        )
        
        record_id = await memory_store.create(record)
        
        # Wait for expiry
        await asyncio.sleep(2)
        
        # Clear expired
        cleared = await memory_store.clear_expired()
        assert cleared >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
