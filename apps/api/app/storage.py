from __future__ import annotations

from app.repositories import DatabaseStorageError, SQLAlchemyStore, StoreRepository


class SQLiteStore(SQLAlchemyStore):
    """Compatibility name for the SQLAlchemy repository used by existing callers."""


store: StoreRepository = SQLiteStore()


__all__ = ["DatabaseStorageError", "SQLAlchemyStore", "SQLiteStore", "StoreRepository", "store"]
