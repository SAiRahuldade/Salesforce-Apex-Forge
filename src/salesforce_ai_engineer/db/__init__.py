"""Database engine, sessions, repositories, and migrations boundary."""

try:
    from salesforce_ai_engineer.db.base import Base
    from salesforce_ai_engineer.db.session import DatabaseManager, get_session
    __all__ = ["Base", "DatabaseManager", "get_session"]
except ImportError:
    # sqlalchemy not installed
    Base = None
    DatabaseManager = None
    get_session = None
    __all__ = []
