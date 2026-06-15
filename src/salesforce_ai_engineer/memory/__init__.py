"""Memory module - Persistent knowledge repository for the autonomous system."""

from salesforce_ai_engineer.memory.store import (
    BaseMemoryStore,
    MemoryStoreError,
    RecordNotFoundError,
    RecordAlreadyExistsError,
    MemoryStoreConnectionError,
    MemoryStoreOperationError,
)
from salesforce_ai_engineer.memory.sqlite_store import SQLiteMemoryStore
from salesforce_ai_engineer.memory.manager import MemoryManager

__all__ = [
    "BaseMemoryStore",
    "MemoryStoreError",
    "RecordNotFoundError",
    "RecordAlreadyExistsError",
    "MemoryStoreConnectionError",
    "MemoryStoreOperationError",
    "SQLiteMemoryStore",
    "MemoryManager",
]
