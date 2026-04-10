"""
Base repository class providing generic CRUD operations.
All repository classes should extend this.
"""

from typing import Any, Generic, List, Optional, Type, TypeVar

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """
    Generic base repository with common CRUD operations.
    All specific repositories should extend this class.
    """

    def __init__(self, model: Type[ModelType], session: AsyncSession):
        """
        Initialize repository with model class and database session.

        Args:
            model: The SQLAlchemy model class
            session: Async database session
        """
        self.model = model
        self.session = session

    async def get_by_id(self, id: Any) -> Optional[ModelType]:
        """
        Get a single record by primary key.

        Args:
            id: Primary key value

        Returns:
            Model instance or None if not found
        """
        result = await self.session.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()

    async def get_one_by(self, **filters: Any) -> Optional[ModelType]:
        """
        Get a single record by arbitrary filters.

        Args:
            **filters: Column=value pairs to filter by

        Returns:
            Model instance or None if not found
        """
        query = select(self.model)
        for key, value in filters.items():
            query = query.where(getattr(self.model, key) == value)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_many_by(
        self,
        skip: int = 0,
        limit: int = 100,
        **filters: Any,
    ) -> List[ModelType]:
        """
        Get multiple records with pagination and filters.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
            **filters: Column=value pairs to filter by

        Returns:
            List of model instances
        """
        query = select(self.model)
        for key, value in filters.items():
            query = query.where(getattr(self.model, key) == value)
        query = query.offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create(self, **values: Any) -> ModelType:
        """
        Create a new record.

        Args:
            **values: Column=value pairs for the new record

        Returns:
            Created model instance
        """
        instance = self.model(**values)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def update(self, id: Any, **values: Any) -> Optional[ModelType]:
        """
        Update an existing record.

        Args:
            id: Primary key of record to update
            **values: Column=value pairs to update

        Returns:
            Updated model instance or None if not found
        """
        await self.session.execute(
            update(self.model).where(self.model.id == id).values(**values)
        )
        await self.session.flush()
        return await self.get_by_id(id)

    async def delete(self, id: Any) -> bool:
        """
        Delete a record by primary key.

        Args:
            id: Primary key of record to delete

        Returns:
            True if deleted, False if not found
        """
        result = await self.session.execute(
            delete(self.model).where(self.model.id == id)
        )
        await self.session.flush()
        return result.rowcount > 0

    async def count(self, **filters: Any) -> int:
        """
        Count records matching filters.

        Args:
            **filters: Column=value pairs to filter by

        Returns:
            Number of matching records
        """
        query = select(self.model)
        for key, value in filters.items():
            query = query.where(getattr(self.model, key) == value)
        result = await self.session.execute(query)
        return len(list(result.scalars().all()))
