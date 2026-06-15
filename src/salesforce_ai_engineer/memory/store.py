"""
Abstract interface for memory storage.

Defines the contract for all memory store implementations, enabling
pluggable backends (SQLite, Vector DB, Graph DB, etc.) without
changing agent code.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Set, Tuple
from datetime import datetime

from salesforce_ai_engineer.models.domain.memory import (
    MemoryRecord,
    MemoryCategory,
    MemoryStatus,
    MemorySearchQuery,
    MemoryFilter,
    MemoryRelationship,
    MemoryVersion,
)


class MemoryStoreError(Exception):
    """Base exception for memory store errors."""
    pass


class RecordNotFoundError(MemoryStoreError):
    """Raised when a record is not found."""
    pass


class RecordAlreadyExistsError(MemoryStoreError):
    """Raised when trying to create a record that already exists."""
    pass


class MemoryStoreConnectionError(MemoryStoreError):
    """Raised when unable to connect to storage backend."""
    pass


class MemoryStoreOperationError(MemoryStoreError):
    """Raised when an operation fails."""
    pass


class BaseMemoryStore(ABC):
    """
    Abstract base class for memory storage implementations.
    
    All memory stores must implement CRUD operations, search, versioning,
    and relationship tracking. Implementations should be:
    - Thread-safe
    - Async-compatible
    - Transactional
    - Support data migrations
    """
    
    # ===== CRUD Operations =====
    
    @abstractmethod
    async def create(self, record: MemoryRecord) -> str:
        """
        Create a new memory record.
        
        Args:
            record: Memory record to create
        
        Returns:
            ID of created record
        
        Raises:
            RecordAlreadyExistsError: If record with same ID exists
            MemoryStoreOperationError: If creation fails
        """
        pass
    
    @abstractmethod
    async def read(self, record_id: str) -> Optional[MemoryRecord]:
        """
        Read a memory record by ID.
        
        Args:
            record_id: ID of record to read
        
        Returns:
            MemoryRecord if found, None otherwise
        
        Raises:
            MemoryStoreOperationError: If read fails
        """
        pass
    
    @abstractmethod
    async def read_many(self, record_ids: List[str]) -> List[MemoryRecord]:
        """
        Read multiple memory records.
        
        Args:
            record_ids: List of record IDs to read
        
        Returns:
            List of found records (in order of input, with None for missing)
        """
        pass
    
    @abstractmethod
    async def update(
        self,
        record_id: str,
        updates: Dict[str, Any],
        change_description: str = "",
        created_by: str = "system"
    ) -> MemoryRecord:
        """
        Update an existing memory record.
        
        Args:
            record_id: ID of record to update
            updates: Dictionary of fields to update
            change_description: Description of what changed
            created_by: Who is making this update
        
        Returns:
            Updated MemoryRecord
        
        Raises:
            RecordNotFoundError: If record doesn't exist
            MemoryStoreOperationError: If update fails
        """
        pass
    
    @abstractmethod
    async def delete(self, record_id: str, soft: bool = True) -> None:
        """
        Delete a memory record.
        
        Args:
            record_id: ID of record to delete
            soft: If True, mark as deleted; if False, hard delete
        
        Raises:
            RecordNotFoundError: If record doesn't exist
            MemoryStoreOperationError: If deletion fails
        """
        pass
    
    @abstractmethod
    async def exists(self, record_id: str) -> bool:
        """
        Check if a record exists.
        
        Args:
            record_id: ID to check
        
        Returns:
            True if record exists, False otherwise
        """
        pass
    
    # ===== Search & Filter Operations =====
    
    @abstractmethod
    async def search(self, query: MemorySearchQuery) -> List[MemoryRecord]:
        """
        Search memory records by keywords and metadata.
        
        Args:
            query: Search query with keywords, category, filters, etc.
        
        Returns:
            List of matching records (ordered by relevance)
        
        Raises:
            MemoryStoreOperationError: If search fails
        """
        pass
    
    @abstractmethod
    async def filter(
        self,
        filters: List[MemoryFilter],
        operator: str = "and"
    ) -> List[MemoryRecord]:
        """
        Filter records by complex criteria.
        
        Args:
            filters: List of filters to apply
            operator: "and" or "or" to combine filters
        
        Returns:
            List of matching records
        """
        pass
    
    @abstractmethod
    async def list_by_category(
        self,
        category: MemoryCategory,
        status: Optional[MemoryStatus] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[MemoryRecord], int]:
        """
        List records by category.
        
        Args:
            category: Category to filter by
            status: Optional status filter
            limit: Max records to return
            offset: Offset for pagination
        
        Returns:
            Tuple of (records, total_count)
        """
        pass
    
    @abstractmethod
    async def list_by_creator(
        self,
        created_by: str,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[MemoryRecord], int]:
        """
        List records created by specific agent/user.
        
        Args:
            created_by: Who created the records
            limit: Max records to return
            offset: Offset for pagination
        
        Returns:
            Tuple of (records, total_count)
        """
        pass
    
    # ===== Tagging Operations =====
    
    @abstractmethod
    async def add_tags(self, record_id: str, tags: List[str]) -> None:
        """
        Add tags to a record.
        
        Args:
            record_id: Record ID
            tags: Tags to add
        
        Raises:
            RecordNotFoundError: If record doesn't exist
        """
        pass
    
    @abstractmethod
    async def remove_tags(self, record_id: str, tags: List[str]) -> None:
        """
        Remove tags from a record.
        
        Args:
            record_id: Record ID
            tags: Tags to remove
        """
        pass
    
    @abstractmethod
    async def find_by_tags(
        self,
        tags: List[str],
        operator: str = "and"
    ) -> List[MemoryRecord]:
        """
        Find records with specific tags.
        
        Args:
            tags: Tags to search for
            operator: "and" or "or" to combine tags
        
        Returns:
            List of matching records
        """
        pass
    
    @abstractmethod
    async def list_all_tags(self) -> List[str]:
        """
        List all tags in use.
        
        Returns:
            List of all tags
        """
        pass
    
    # ===== Versioning Operations =====
    
    @abstractmethod
    async def get_history(
        self,
        record_id: str,
        limit: int = 100
    ) -> List[MemoryVersion]:
        """
        Get version history for a record.
        
        Args:
            record_id: Record ID
            limit: Max versions to return
        
        Returns:
            List of MemoryVersion entries (newest first)
        """
        pass
    
    @abstractmethod
    async def restore_version(
        self,
        record_id: str,
        version_number: int
    ) -> MemoryRecord:
        """
        Restore a record to a previous version.
        
        Args:
            record_id: Record ID
            version_number: Version to restore to
        
        Returns:
            Restored MemoryRecord
        
        Raises:
            RecordNotFoundError: If record or version doesn't exist
        """
        pass
    
    # ===== Relationship Operations =====
    
    @abstractmethod
    async def create_relationship(
        self,
        relationship: MemoryRelationship
    ) -> str:
        """
        Create a relationship between two records.
        
        Args:
            relationship: Relationship to create
        
        Returns:
            ID of created relationship
        """
        pass
    
    @abstractmethod
    async def get_relationships(
        self,
        record_id: str,
        direction: str = "outgoing"
    ) -> List[MemoryRelationship]:
        """
        Get relationships for a record.
        
        Args:
            record_id: Record ID
            direction: "outgoing", "incoming", or "both"
        
        Returns:
            List of relationships
        """
        pass
    
    @abstractmethod
    async def delete_relationship(self, relationship_id: str) -> None:
        """
        Delete a relationship.
        
        Args:
            relationship_id: Relationship ID to delete
        """
        pass
    
    @abstractmethod
    async def find_related_records(
        self,
        record_id: str,
        relationship_type: Optional[str] = None,
        depth: int = 1
    ) -> List[MemoryRecord]:
        """
        Find records related to a given record.
        
        Args:
            record_id: Record ID
            relationship_type: Optional filter by relationship type
            depth: How many hops to search
        
        Returns:
            List of related records
        """
        pass
    
    # ===== Statistics & Analytics =====
    
    @abstractmethod
    async def count_by_category(self) -> Dict[str, int]:
        """
        Count records by category.
        
        Returns:
            Dictionary mapping category to count
        """
        pass
    
    @abstractmethod
    async def count_by_status(self) -> Dict[str, int]:
        """
        Count records by status.
        
        Returns:
            Dictionary mapping status to count
        """
        pass
    
    @abstractmethod
    async def count_by_creator(self) -> Dict[str, int]:
        """
        Count records by creator.
        
        Returns:
            Dictionary mapping creator to count
        """
        pass
    
    @abstractmethod
    async def get_total_records(self) -> int:
        """
        Get total count of all records.
        
        Returns:
            Total record count
        """
        pass
    
    @abstractmethod
    async def get_storage_stats(self) -> Dict[str, Any]:
        """
        Get storage statistics.
        
        Returns:
            Dictionary with stats (size, record count, etc.)
        """
        pass
    
    # ===== Lifecycle & Maintenance =====
    
    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if storage is healthy and accessible.
        
        Returns:
            True if healthy, False otherwise
        """
        pass
    
    @abstractmethod
    async def clear_expired(self) -> int:
        """
        Clear records with expired TTL.
        
        Returns:
            Number of records cleared
        """
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """
        Close storage connection and cleanup resources.
        """
        pass
    
    @abstractmethod
    async def open(self) -> None:
        """
        Open storage connection.
        
        Raises:
            MemoryStoreConnectionError: If unable to connect
        """
        pass
    
    # ===== Transaction Support =====
    
    @abstractmethod
    async def begin_transaction(self) -> None:
        """Begin a transaction."""
        pass
    
    @abstractmethod
    async def commit_transaction(self) -> None:
        """Commit current transaction."""
        pass
    
    @abstractmethod
    async def rollback_transaction(self) -> None:
        """Rollback current transaction."""
        pass
