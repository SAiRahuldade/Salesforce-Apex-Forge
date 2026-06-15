"""
SQLite implementation of MemoryStore.

Provides persistent storage for memory records with full-text search,
versioning, relationships, and analytics support.
"""

import json
import sqlite3
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple
import asyncio
from contextlib import asynccontextmanager

from salesforce_ai_engineer.models.domain.memory import (
    MemoryRecord,
    MemoryCategory,
    MemoryStatus,
    MemorySearchQuery,
    MemoryFilter,
    MemoryRelationship,
    MemoryVersion,
    MemoryMetadata,
    MemoryTag,
    ProjectMemory,
    WorkflowHistory,
    ExecutionHistory,
    AgentInteraction,
    CompletedTask,
    RecoveryHistory,
    DeploymentHistory,
    ArchitectureDecision,
    KnownError,
    SuccessfulFix,
    UserPreference,
    CodingPattern,
    RewardRecord,
    ExecutionMetric,
)
from salesforce_ai_engineer.memory.store import (
    BaseMemoryStore,
    MemoryStoreError,
    RecordNotFoundError,
    RecordAlreadyExistsError,
    MemoryStoreConnectionError,
    MemoryStoreOperationError,
)


logger = logging.getLogger(__name__)


class AsyncRLock:
    """A reentrant lock for asyncio."""
    
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._owner = None
        self._count = 0

    async def acquire(self) -> None:
        current_task = asyncio.current_task()
        if self._owner == current_task:
            self._count += 1
            return
        await self._lock.acquire()
        self._owner = current_task
        self._count = 1

    def release(self) -> None:
        current_task = asyncio.current_task()
        if self._owner != current_task:
            raise RuntimeError("Cannot release a lock you don't own")
        self._count -= 1
        if self._count == 0:
            self._owner = None
            self._lock.release()

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.release()


class SQLiteMemoryStore(BaseMemoryStore):
    """SQLite-based implementation of MemoryStore."""
    
    def __init__(self, db_path: Path):
        """
        Initialize SQLite memory store.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._transaction_active = False
        self._lock = AsyncRLock()
    
    async def open(self) -> None:
        """Open database connection and initialize schema."""
        try:
            # Create connection in thread pool
            loop = asyncio.get_event_loop()
            self._conn = await loop.run_in_executor(
                None,
                lambda: sqlite3.connect(
                    str(self.db_path),
                    check_same_thread=False,
                    timeout=30.0
                )
            )
            self._conn.row_factory = sqlite3.Row
            
            # Enable foreign keys
            self._conn.execute("PRAGMA foreign_keys = ON")
            
            # Initialize schema
            await self._initialize_schema()
            logger.info(f"Connected to memory store: {self.db_path}")
        except Exception as e:
            raise MemoryStoreConnectionError(f"Failed to connect to SQLite: {e}")
    
    async def close(self) -> None:
        """Close database connection."""
        if self._conn:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._conn.close)
            self._conn = None
            logger.info("Closed memory store connection")
    
    async def health_check(self) -> bool:
        """Check if storage is accessible."""
        try:
            if not self._conn:
                return False
            cursor = await self._execute("SELECT 1")
            return cursor is not None
        except Exception:
            return False
    
    async def _initialize_schema(self) -> None:
        """Initialize database schema."""
        statements = [
            # Main records table
            """CREATE TABLE IF NOT EXISTS memory_records (
                id TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                content TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                created_by TEXT NOT NULL,
                
                metadata_source TEXT NOT NULL,
                metadata_confidence REAL DEFAULT 1.0,
                metadata_relevance REAL DEFAULT 1.0,
                metadata_priority INTEGER DEFAULT 5,
                metadata_ttl_seconds INTEGER,
                metadata_custom TEXT,
                
                CHECK(status IN ('active', 'archived', 'deprecated', 'deleted'))
            )""",
            
            # Indexes on memory_records
            "CREATE INDEX IF NOT EXISTS idx_category ON memory_records(category)",
            "CREATE INDEX IF NOT EXISTS idx_status ON memory_records(status)",
            "CREATE INDEX IF NOT EXISTS idx_created_by ON memory_records(created_by)",
            "CREATE INDEX IF NOT EXISTS idx_created_at ON memory_records(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_updated_at ON memory_records(updated_at)",
            
            # Tags table
            """CREATE TABLE IF NOT EXISTS memory_tags (
                id TEXT PRIMARY KEY,
                record_id TEXT NOT NULL,
                tag_name TEXT NOT NULL,
                tag_value TEXT,
                created_at TEXT NOT NULL,
                
                FOREIGN KEY(record_id) REFERENCES memory_records(id) ON DELETE CASCADE,
                UNIQUE(record_id, tag_name)
            )""",
            
            # Tag indexes
            "CREATE INDEX IF NOT EXISTS idx_tag_name ON memory_tags(tag_name)",
            "CREATE INDEX IF NOT EXISTS idx_tag_record ON memory_tags(record_id)",
            
            # Versions table
            """CREATE TABLE IF NOT EXISTS memory_versions (
                id TEXT PRIMARY KEY,
                record_id TEXT NOT NULL,
                version_number INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                created_by TEXT NOT NULL,
                content_before TEXT NOT NULL,
                content_after TEXT NOT NULL,
                change_description TEXT,
                change_type TEXT NOT NULL,
                
                FOREIGN KEY(record_id) REFERENCES memory_records(id) ON DELETE CASCADE,
                UNIQUE(record_id, version_number)
            )""",
            
            "CREATE INDEX IF NOT EXISTS idx_version_record ON memory_versions(record_id)",
            
            # Relationships table
            """CREATE TABLE IF NOT EXISTS memory_relationships (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                relationship_type TEXT NOT NULL,
                bidirectional BOOLEAN DEFAULT 0,
                metadata TEXT,
                created_at TEXT NOT NULL,
                
                FOREIGN KEY(source_id) REFERENCES memory_records(id) ON DELETE CASCADE,
                FOREIGN KEY(target_id) REFERENCES memory_records(id) ON DELETE CASCADE
            )""",
            
            # Relationship indexes
            "CREATE INDEX IF NOT EXISTS idx_rel_source ON memory_relationships(source_id)",
            "CREATE INDEX IF NOT EXISTS idx_rel_target ON memory_relationships(target_id)",
            "CREATE INDEX IF NOT EXISTS idx_rel_type ON memory_relationships(relationship_type)",
            
            # FTS5 virtual table
            """CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                id,
                title,
                description,
                content_text
            )""",
            
            # FTS5 triggers
            """CREATE TRIGGER IF NOT EXISTS memory_fts_ai AFTER INSERT ON memory_records BEGIN
                INSERT INTO memory_fts(id, title, description, content_text)
                VALUES (new.id, new.title, new.description, new.content);
            END""",
            
            """CREATE TRIGGER IF NOT EXISTS memory_fts_ad AFTER DELETE ON memory_records BEGIN
                DELETE FROM memory_fts WHERE id = old.id;
            END""",
            
            """CREATE TRIGGER IF NOT EXISTS memory_fts_au AFTER UPDATE ON memory_records BEGIN
                DELETE FROM memory_fts WHERE id = old.id;
                INSERT INTO memory_fts(id, title, description, content_text)
                VALUES (new.id, new.title, new.description, new.content);
            END""",
        ]
        
        loop = asyncio.get_event_loop()
        for statement in statements:
            await loop.run_in_executor(
                None,
                lambda s=statement: self._conn.execute(s)
            )
        self._conn.commit()
        logger.debug("Database schema initialized")
    
    async def _execute(self, query: str, params: tuple = ()) -> Optional[sqlite3.Cursor]:
        """Execute query in thread pool."""
        async with self._lock:
            loop = asyncio.get_event_loop()
            try:
                return await loop.run_in_executor(
                    None,
                    lambda: self._conn.execute(query, params)
                )
            except Exception as e:
                logger.error(f"Query execution failed: {query}, error: {e}")
                raise MemoryStoreOperationError(f"Database query failed: {e}")
    
    async def _fetch_one(self, query: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        """Fetch one row."""
        cursor = await self._execute(query, params)
        return cursor.fetchone() if cursor else None
    
    async def _fetch_all(self, query: str, params: tuple = ()) -> List[sqlite3.Row]:
        """Fetch all rows."""
        cursor = await self._execute(query, params)
        return cursor.fetchall() if cursor else []
    
    async def _record_from_row(self, row: sqlite3.Row) -> MemoryRecord:
        """Convert database row to MemoryRecord object."""
        content = json.loads(row["content"])
        metadata_custom = json.loads(row["metadata_custom"] or "{}")

        from salesforce_ai_engineer.models.domain.memory import (
            MemoryMetadata,
            create_memory_record,
            MemoryTag,
        )

        metadata = MemoryMetadata(
            source=row["metadata_source"],
            confidence=row["metadata_confidence"],
            relevance=row["metadata_relevance"],
            priority=row["metadata_priority"],
            ttl_seconds=row["metadata_ttl_seconds"],
            custom=metadata_custom,
        )

        tag_rows = await self._fetch_all(
            "SELECT tag_name, tag_value FROM memory_tags WHERE record_id = ?",
            (row["id"],),
        )
        tags = [MemoryTag(name=t["tag_name"], value=t["tag_value"]) for t in tag_rows]

        return create_memory_record(
            category=MemoryCategory(row["category"]),
            title=row["title"],
            created_by=row["created_by"],
            id=row["id"],
            description=row["description"],
            tags=tags,
            metadata=metadata,
            status=MemoryStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            **content,  # Unpack category-specific fields
        )


    
    def _extract_content_for_storage(self, record: MemoryRecord) -> Dict[str, Any]:
        """Extract category-specific content from record for storage."""
        # Base field names that shouldn't be in content
        base_fields = {
            "id", "category", "title", "description", "content", "tags", 
            "metadata", "status", "created_at", "updated_at", "created_by"
        }
        
        # Get all fields from the model dump
        all_fields = record.model_dump(mode="json")
        
        # Extract only category-specific fields
        category_fields = {k: v for k, v in all_fields.items() if k not in base_fields}
        
        return category_fields
    
    async def create(self, record: MemoryRecord) -> str:
        """Create a new memory record."""
        # Serialize all writes to ensure persistence under concurrent load.
        async with self._lock:
            try:
                # Check if already exists
                existing = await self._fetch_one(
                    "SELECT id FROM memory_records WHERE id = ?",
                    (record.id,),
                )
                if existing:
                    raise RecordAlreadyExistsError(f"Record with ID {record.id} already exists")

                # Insert main record
                query = """
                INSERT INTO memory_records (
                    id, category, title, description, content, status,
                    created_at, updated_at, created_by,
                    metadata_source, metadata_confidence, metadata_relevance,
                    metadata_priority, metadata_ttl_seconds, metadata_custom
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """

                params = (
                    record.id,
                    record.category.value,
                    record.title,
                    record.description,
                    json.dumps(self._extract_content_for_storage(record)),
                    record.status.value if hasattr(record.status, "value") else record.status,
                    record.created_at.isoformat(),
                    record.updated_at.isoformat(),
                    record.created_by,
                    record.metadata.source,
                    record.metadata.confidence,
                    record.metadata.relevance,
                    record.metadata.priority,
                    record.metadata.ttl_seconds,
                    json.dumps(record.metadata.custom),
                )

                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, lambda: self._conn.execute(query, params))

                # Insert tags
                for tag in record.tags:
                    await self._execute(
                        """
                        INSERT OR IGNORE INTO memory_tags (id, record_id, tag_name, tag_value, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            f"{record.id}:{tag.name}",
                            record.id,
                            tag.name,
                            tag.value,
                            tag.created_at.isoformat(),
                        ),
                    )

                # Commit under the same lock.
                self._conn.commit()


                logger.info(f"Created memory record: {record.id}")
                return record.id

            except RecordAlreadyExistsError:
                raise
            except Exception as e:
                logger.error(f"Failed to create record: {e}")
                raise MemoryStoreOperationError(f"Failed to create record: {e}")

    
    async def read(self, record_id: str) -> Optional[MemoryRecord]:
        """Read a memory record by ID."""
        try:
            row = await self._fetch_one(
                "SELECT * FROM memory_records WHERE id = ?",
                (record_id,)
            )
            if not row:
                return None
            return await self._record_from_row(row)
        except Exception as e:
            logger.error(f"Failed to read record {record_id}: {e}")
            raise MemoryStoreOperationError(f"Failed to read record: {e}")
    
    async def read_many(self, record_ids: List[str]) -> List[MemoryRecord]:
        """Read multiple memory records."""
        if not record_ids:
            return []
        
        try:
            placeholders = ",".join("?" * len(record_ids))
            rows = await self._fetch_all(
                f"SELECT * FROM memory_records WHERE id IN ({placeholders})",
                tuple(record_ids)
            )
            records = [await self._record_from_row(row) for row in rows]
            
            # Preserve the order of requested IDs
            id_to_record = {r.id: r for r in records}
            return [id_to_record[id] for id in record_ids if id in id_to_record]
        except Exception as e:
            logger.error(f"Failed to read multiple records: {e}")
            raise MemoryStoreOperationError(f"Failed to read records: {e}")
    
    async def update(
        self,
        record_id: str,
        updates: Dict[str, Any],
        change_description: str = "",
        created_by: str = "system"
    ) -> MemoryRecord:
        """Update an existing memory record."""
        try:
            # Get existing record
            existing = await self.read(record_id)
            if not existing:
                raise RecordNotFoundError(f"Record {record_id} not found")
            
            # Create version entry
            old_content = existing.model_dump(mode="json")
            
            # Update fields - handle dict to object conversions for complex fields
            for key, value in updates.items():
                if hasattr(existing, key):
                    # Handle complex field reconstruction from dicts
                    if key == "metadata" and isinstance(value, dict):
                        value = MemoryMetadata(**value)
                    elif key == "tags" and isinstance(value, list):
                        # Tags are list of dicts, reconstruct them
                        value = [MemoryTag(**t) if isinstance(t, dict) else t for t in value]
                    
                    setattr(existing, key, value)
            
            existing.updated_at = datetime.utcnow()
            
            # Update in database
            query = """
            UPDATE memory_records SET
                title = ?, description = ?, content = ?,
                status = ?, updated_at = ?,
                metadata_confidence = ?, metadata_relevance = ?,
                metadata_priority = ?, metadata_ttl_seconds = ?,
                metadata_custom = ?
            WHERE id = ?
            """
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._conn.execute(
                    query,
                    (
                        existing.title,
                        existing.description,
                        json.dumps(self._extract_content_for_storage(existing)),
                        existing.status.value if hasattr(existing.status, 'value') else existing.status,
                        existing.updated_at.isoformat(),
                        existing.metadata.confidence,
                        existing.metadata.relevance,
                        existing.metadata.priority,
                        existing.metadata.ttl_seconds,
                        json.dumps(existing.metadata.custom),
                        record_id,
                    )
                )
            )
            
            # Store version
            version_number = len(await self.get_history(record_id)) + 1
            version = MemoryVersion(
                record_id=record_id,
                version_number=version_number,
                created_by=created_by,
                content_before=old_content,
                content_after=existing.model_dump(mode="json"),
                change_description=change_description,
                change_type="update"
            )
            
            await self._execute(
                """
                INSERT INTO memory_versions
                (id, record_id, version_number, created_at, created_by,
                 content_before, content_after, change_description, change_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version.id,
                    version.record_id,
                    version.version_number,
                    version.created_at.isoformat(),
                    version.created_by,
                    json.dumps(version.content_before),
                    json.dumps(version.content_after),
                    version.change_description,
                    version.change_type,
                )
            )
            
            self._conn.commit()
            logger.info(f"Updated memory record: {record_id}")
            return existing
        
        except (RecordNotFoundError, MemoryStoreOperationError):
            raise
        except Exception as e:
            logger.error(f"Failed to update record {record_id}: {e}")
            raise MemoryStoreOperationError(f"Failed to update record: {e}")
    
    async def delete(self, record_id: str, soft: bool = True) -> None:
        """Delete a memory record."""
        try:
            existing = await self.read(record_id)
            if not existing:
                raise RecordNotFoundError(f"Record {record_id} not found")
            
            if soft:
                # Mark as deleted
                await self._execute(
                    "UPDATE memory_records SET status = ? WHERE id = ?",
                    (MemoryStatus.DELETED.value, record_id)
                )
            else:
                # Hard delete
                await self._execute(
                    "DELETE FROM memory_records WHERE id = ?",
                    (record_id,)
                )
            
            self._conn.commit()
            logger.info(f"Deleted memory record: {record_id}")
        
        except RecordNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to delete record {record_id}: {e}")
            raise MemoryStoreOperationError(f"Failed to delete record: {e}")
    
    async def exists(self, record_id: str) -> bool:
        """Check if a record exists."""
        try:
            row = await self._fetch_one(
                "SELECT 1 FROM memory_records WHERE id = ?",
                (record_id,)
            )
            return row is not None
        except Exception:
            return False
    
    async def search(self, query: MemorySearchQuery) -> List[MemoryRecord]:
        """Search memory records by keywords and metadata."""
        try:
            sql = "SELECT * FROM memory_records WHERE status != ?"
            params: List[Any] = [MemoryStatus.DELETED.value]
            
            # Full-text search
            if query.keywords:
                keywords_str = " AND ".join(query.keywords)
                sql += " AND id IN (SELECT id FROM memory_fts WHERE memory_fts MATCH ?)"
                params.append(keywords_str)
            
            # Category filter
            if query.category:
                sql += " AND category = ?"
                params.append(query.category.value)
            
            # Status filter
            if query.status:
                sql += " AND status = ?"
                params.append(query.status.value)
            
            # Date range
            if query.created_after:
                sql += " AND created_at >= ?"
                params.append(query.created_after.isoformat())
            
            if query.created_before:
                sql += " AND created_at <= ?"
                params.append(query.created_before.isoformat())
            
            # Creator filter
            if query.created_by:
                sql += " AND created_by = ?"
                params.append(query.created_by)
            
            # Confidence filter
            if query.min_confidence > 0:
                sql += " AND metadata_confidence >= ?"
                params.append(query.min_confidence)
            
            # Tags filter
            if query.tags:
                placeholders = ",".join("?" * len(query.tags))
                sql += f" AND id IN (SELECT DISTINCT record_id FROM memory_tags WHERE tag_name IN ({placeholders}))"
                params.extend(query.tags)
            
            # Sorting and pagination
            sql += " ORDER BY metadata_relevance DESC, updated_at DESC"
            sql += " LIMIT ? OFFSET ?"
            params.extend([query.limit, query.offset])
            
            rows = await self._fetch_all(sql, tuple(params))
            return [await self._record_from_row(row) for row in rows]
        
        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise MemoryStoreOperationError(f"Search failed: {e}")
    
    async def filter(
        self,
        filters: List[MemoryFilter],
        operator: str = "and"
    ) -> List[MemoryRecord]:
        """Filter records by complex criteria."""
        try:
            sql = "SELECT * FROM memory_records WHERE 1=1"
            params: List[Any] = []
            
            for f in filters:
                if f.operator == "eq":
                    sql += f" AND {f.field} = ?"
                    params.append(f.value)
                elif f.operator == "ne":
                    sql += f" AND {f.field} != ?"
                    params.append(f.value)
                elif f.operator == "gt":
                    sql += f" AND {f.field} > ?"
                    params.append(f.value)
                elif f.operator == "lt":
                    sql += f" AND {f.field} < ?"
                    params.append(f.value)
                elif f.operator == "gte":
                    sql += f" AND {f.field} >= ?"
                    params.append(f.value)
                elif f.operator == "lte":
                    sql += f" AND {f.field} <= ?"
                    params.append(f.value)
                elif f.operator == "in":
                    placeholders = ",".join("?" * len(f.value))
                    sql += f" AND {f.field} IN ({placeholders})"
                    params.extend(f.value)
                elif f.operator == "contains":
                    sql += f" AND {f.field} LIKE ?"
                    params.append(f"%{f.value}%")
                elif f.operator == "regex":
                    sql += f" AND {f.field} REGEXP ?"
                    params.append(f.value)
            
            rows = await self._fetch_all(sql, tuple(params))
            return [await self._record_from_row(row) for row in rows]
        
        except Exception as e:
            logger.error(f"Filter failed: {e}")
            raise MemoryStoreOperationError(f"Filter failed: {e}")
    
    async def list_by_category(
        self,
        category: MemoryCategory,
        status: Optional[MemoryStatus] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[MemoryRecord], int]:
        """List records by category."""
        try:
            sql = "SELECT * FROM memory_records WHERE category = ?"
            count_sql = "SELECT COUNT(*) as cnt FROM memory_records WHERE category = ?"
            params: List[Any] = [category.value]
            
            if status:
                sql += " AND status = ?"
                count_sql += " AND status = ?"
                params.append(status.value)
            
            # Get count
            count_row = await self._fetch_one(count_sql, tuple(params))
            total = count_row["cnt"] if count_row else 0
            
            # Get records
            sql += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
            rows = await self._fetch_all(sql, tuple(params) + (limit, offset))
            records = [await self._record_from_row(row) for row in rows]
            
            return records, total
        
        except Exception as e:
            logger.error(f"List by category failed: {e}")
            raise MemoryStoreOperationError(f"List by category failed: {e}")
    
    async def list_by_creator(
        self,
        created_by: str,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[MemoryRecord], int]:
        """List records created by specific agent."""
        try:
            sql = "SELECT * FROM memory_records WHERE created_by = ?"
            count_sql = "SELECT COUNT(*) as cnt FROM memory_records WHERE created_by = ?"
            
            # Get count
            count_row = await self._fetch_one(count_sql, (created_by,))
            total = count_row["cnt"] if count_row else 0
            
            # Get records
            sql += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
            rows = await self._fetch_all(sql, (created_by, limit, offset))
            records = [await self._record_from_row(row) for row in rows]
            
            return records, total
        
        except Exception as e:
            logger.error(f"List by creator failed: {e}")
            raise MemoryStoreOperationError(f"List by creator failed: {e}")
    
    async def add_tags(self, record_id: str, tags: List[str]) -> None:
        """Add tags to a record."""
        try:
            if not await self.exists(record_id):
                raise RecordNotFoundError(f"Record {record_id} not found")
            
            for tag in tags:
                await self._execute(
                    """
                    INSERT OR IGNORE INTO memory_tags
                    (id, record_id, tag_name, tag_value, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        f"{record_id}:{tag}",
                        record_id,
                        tag,
                        None,
                        datetime.utcnow().isoformat(),
                    )
                )
            
            self._conn.commit()
        
        except RecordNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to add tags: {e}")
            raise MemoryStoreOperationError(f"Failed to add tags: {e}")
    
    async def remove_tags(self, record_id: str, tags: List[str]) -> None:
        """Remove tags from a record."""
        try:
            placeholders = ",".join("?" * len(tags))
            await self._execute(
                f"DELETE FROM memory_tags WHERE record_id = ? AND tag_name IN ({placeholders})",
                (record_id, *tags)
            )
            self._conn.commit()
        except Exception as e:
            logger.error(f"Failed to remove tags: {e}")
            raise MemoryStoreOperationError(f"Failed to remove tags: {e}")
    
    async def find_by_tags(
        self,
        tags: List[str],
        operator: str = "and"
    ) -> List[MemoryRecord]:
        """Find records with specific tags."""
        try:
            if not tags:
                return []
            
            placeholders = ",".join("?" * len(tags))
            
            if operator == "and":
                sql = f"""
                SELECT * FROM memory_records WHERE id IN (
                    SELECT record_id FROM memory_tags
                    WHERE tag_name IN ({placeholders})
                    GROUP BY record_id
                    HAVING COUNT(DISTINCT tag_name) = ?
                )
                """
                params = tuple(tags) + (len(tags),)
            else:  # or
                sql = f"""
                SELECT DISTINCT mr.* FROM memory_records mr
                INNER JOIN memory_tags mt ON mr.id = mt.record_id
                WHERE mt.tag_name IN ({placeholders})
                """
                params = tuple(tags)
            
            rows = await self._fetch_all(sql, params)
            return [await self._record_from_row(row) for row in rows]
        
        except Exception as e:
            logger.error(f"Find by tags failed: {e}")
            raise MemoryStoreOperationError(f"Find by tags failed: {e}")
    
    async def list_all_tags(self) -> List[str]:
        """List all tags in use."""
        try:
            rows = await self._fetch_all(
                "SELECT DISTINCT tag_name FROM memory_tags ORDER BY tag_name"
            )
            return [row["tag_name"] for row in rows]
        except Exception as e:
            logger.error(f"List tags failed: {e}")
            raise MemoryStoreOperationError(f"List tags failed: {e}")
    
    async def get_history(
        self,
        record_id: str,
        limit: int = 100
    ) -> List[MemoryVersion]:
        """Get version history for a record."""
        try:
            rows = await self._fetch_all(
                """
                SELECT * FROM memory_versions
                WHERE record_id = ?
                ORDER BY version_number DESC
                LIMIT ?
                """,
                (record_id, limit)
            )
            
            versions = []
            for row in rows:
                version = MemoryVersion(
                    id=row["id"],
                    record_id=row["record_id"],
                    version_number=row["version_number"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    created_by=row["created_by"],
                    content_before=json.loads(row["content_before"]),
                    content_after=json.loads(row["content_after"]),
                    change_description=row["change_description"],
                    change_type=row["change_type"],
                )
                versions.append(version)
            
            return versions
        
        except Exception as e:
            logger.error(f"Get history failed: {e}")
            raise MemoryStoreOperationError(f"Get history failed: {e}")
    
    async def restore_version(
        self,
        record_id: str,
        version_number: int
    ) -> MemoryRecord:
        """Restore a record to a previous version."""
        try:
            # Get the version record
            row = await self._fetch_one(
                """
                SELECT content_before FROM memory_versions
                WHERE record_id = ? AND version_number = ?
                """,
                (record_id, version_number)
            )
            
            if not row:
                raise RecordNotFoundError(
                    f"Version {version_number} not found for record {record_id}"
                )
            
            # Extract all fields from version (content_before contains the state before this version's update)
            content_before = json.loads(row["content_before"])
            
            # Build updates with all restorable fields (exclude id and timestamps)
            updates = {k: v for k, v in content_before.items() 
                      if k not in {"id", "created_at", "updated_at"}}
            
            return await self.update(
                record_id,
                updates,
                change_description=f"Restored to version {version_number}",
                created_by="system"
            )
        
        except RecordNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Restore version failed: {e}")
            raise MemoryStoreOperationError(f"Restore version failed: {e}")
    
    async def create_relationship(
        self,
        relationship: MemoryRelationship
    ) -> str:
        """Create a relationship between two records."""
        try:
            await self._execute(
                """
                INSERT INTO memory_relationships
                (id, source_id, target_id, relationship_type, bidirectional, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    relationship.id,
                    relationship.source_id,
                    relationship.target_id,
                    relationship.relationship_type,
                    1 if relationship.bidirectional else 0,
                    json.dumps(relationship.metadata),
                    relationship.created_at.isoformat(),
                )
            )
            self._conn.commit()
            return relationship.id
        except Exception as e:
            logger.error(f"Create relationship failed: {e}")
            raise MemoryStoreOperationError(f"Create relationship failed: {e}")
    
    async def get_relationships(
        self,
        record_id: str,
        direction: str = "outgoing"
    ) -> List[MemoryRelationship]:
        """Get relationships for a record."""
        try:
            if direction == "outgoing":
                sql = "SELECT * FROM memory_relationships WHERE source_id = ?"
            elif direction == "incoming":
                sql = "SELECT * FROM memory_relationships WHERE target_id = ?"
            else:  # both
                sql = """
                SELECT * FROM memory_relationships
                WHERE source_id = ? OR target_id = ?
                """
                rows = await self._fetch_all(sql, (record_id, record_id))
                relationships = []
                for row in rows:
                    rel = MemoryRelationship(
                        id=row["id"],
                        source_id=row["source_id"],
                        target_id=row["target_id"],
                        relationship_type=row["relationship_type"],
                        bidirectional=bool(row["bidirectional"]),
                        metadata=json.loads(row["metadata"] or "{}"),
                        created_at=datetime.fromisoformat(row["created_at"]),
                    )
                    relationships.append(rel)
                return relationships
            
            rows = await self._fetch_all(sql, (record_id,))
            relationships = []
            for row in rows:
                rel = MemoryRelationship(
                    id=row["id"],
                    source_id=row["source_id"],
                    target_id=row["target_id"],
                    relationship_type=row["relationship_type"],
                    bidirectional=bool(row["bidirectional"]),
                    metadata=json.loads(row["metadata"] or "{}"),
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
                relationships.append(rel)
            return relationships
        
        except Exception as e:
            logger.error(f"Get relationships failed: {e}")
            raise MemoryStoreOperationError(f"Get relationships failed: {e}")
    
    async def delete_relationship(self, relationship_id: str) -> None:
        """Delete a relationship."""
        try:
            await self._execute(
                "DELETE FROM memory_relationships WHERE id = ?",
                (relationship_id,)
            )
            self._conn.commit()
        except Exception as e:
            logger.error(f"Delete relationship failed: {e}")
            raise MemoryStoreOperationError(f"Delete relationship failed: {e}")
    
    async def find_related_records(
        self,
        record_id: str,
        relationship_type: Optional[str] = None,
        depth: int = 1
    ) -> List[MemoryRecord]:
        """Find records related to a given record."""
        try:
            related_ids: Set[str] = set()
            current_level = {record_id}
            
            for _ in range(depth):
                next_level = set()
                for rid in current_level:
                    relationships = await self.get_relationships(rid, "both")
                    for rel in relationships:
                        if relationship_type and rel.relationship_type != relationship_type:
                            continue
                        
                        # Add related IDs
                        if rel.source_id == rid:
                            next_level.add(rel.target_id)
                        else:
                            next_level.add(rel.source_id)
                
                related_ids.update(next_level)
                current_level = next_level
            
            # Remove the original record
            related_ids.discard(record_id)
            
            if not related_ids:
                return []
            
            return await self.read_many(list(related_ids))
        
        except Exception as e:
            logger.error(f"Find related records failed: {e}")
            raise MemoryStoreOperationError(f"Find related records failed: {e}")
    
    async def count_by_category(self) -> Dict[str, int]:
        """Count records by category."""
        try:
            rows = await self._fetch_all(
                "SELECT category, COUNT(*) as cnt FROM memory_records GROUP BY category"
            )
            return {row["category"]: row["cnt"] for row in rows}
        except Exception as e:
            logger.error(f"Count by category failed: {e}")
            raise MemoryStoreOperationError(f"Count by category failed: {e}")
    
    async def count_by_status(self) -> Dict[str, int]:
        """Count records by status."""
        try:
            rows = await self._fetch_all(
                "SELECT status, COUNT(*) as cnt FROM memory_records GROUP BY status"
            )
            return {row["status"]: row["cnt"] for row in rows}
        except Exception as e:
            logger.error(f"Count by status failed: {e}")
            raise MemoryStoreOperationError(f"Count by status failed: {e}")
    
    async def count_by_creator(self) -> Dict[str, int]:
        """Count records by creator."""
        try:
            rows = await self._fetch_all(
                "SELECT created_by, COUNT(*) as cnt FROM memory_records GROUP BY created_by"
            )
            return {row["created_by"]: row["cnt"] for row in rows}
        except Exception as e:
            logger.error(f"Count by creator failed: {e}")
            raise MemoryStoreOperationError(f"Count by creator failed: {e}")
    
    async def get_total_records(self) -> int:
        """Get total count of all records."""
        try:
            row = await self._fetch_one(
                "SELECT COUNT(*) as cnt FROM memory_records"
            )
            return row["cnt"] if row else 0
        except Exception as e:
            logger.error(f"Get total records failed: {e}")
            raise MemoryStoreOperationError(f"Get total records failed: {e}")
    
    async def get_storage_stats(self) -> Dict[str, Any]:
        """Get storage statistics."""
        try:
            stats = {
                "total_records": await self.get_total_records(),
                "by_category": await self.count_by_category(),
                "by_status": await self.count_by_status(),
                "by_creator": await self.count_by_creator(),
            }
            
            # Get file size
            if self.db_path.exists():
                stats["file_size_bytes"] = self.db_path.stat().st_size
            
            return stats
        except Exception as e:
            logger.error(f"Get storage stats failed: {e}")
            raise MemoryStoreOperationError(f"Get storage stats failed: {e}")
    
    async def clear_expired(self) -> int:
        """Clear records with expired TTL."""
        try:
            now = datetime.utcnow().isoformat()
            
            # Find expired records
            rows = await self._fetch_all(
                """
                SELECT id, created_at, metadata_ttl_seconds
                FROM memory_records
                WHERE metadata_ttl_seconds IS NOT NULL
                """
            )
            
            expired_ids = []
            for row in rows:
                created_at = datetime.fromisoformat(row["created_at"])
                ttl = row["metadata_ttl_seconds"]
                expiry = created_at.timestamp() + ttl
                
                if datetime.utcnow().timestamp() > expiry:
                    expired_ids.append(row["id"])
            
            # Delete expired records
            for rid in expired_ids:
                await self.delete(rid, soft=True)
            
            logger.info(f"Cleared {len(expired_ids)} expired records")
            return len(expired_ids)
        
        except Exception as e:
            logger.error(f"Clear expired failed: {e}")
            raise MemoryStoreOperationError(f"Clear expired failed: {e}")
    
    async def begin_transaction(self) -> None:
        """Begin a transaction."""
        try:
            self._conn.execute("BEGIN TRANSACTION")
            self._transaction_active = True
        except Exception as e:
            raise MemoryStoreOperationError(f"Begin transaction failed: {e}")
    
    async def commit_transaction(self) -> None:
        """Commit current transaction."""
        try:
            self._conn.commit()
            self._transaction_active = False
        except Exception as e:
            raise MemoryStoreOperationError(f"Commit transaction failed: {e}")
    
    async def rollback_transaction(self) -> None:
        """Rollback current transaction."""
        try:
            self._conn.rollback()
            self._transaction_active = False
        except Exception as e:
            raise MemoryStoreOperationError(f"Rollback transaction failed: {e}")
