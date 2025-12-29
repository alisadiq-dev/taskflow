"""Generic repository pattern for database operations."""

from typing import Any, Generic, Optional, TypeVar
from uuid import uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from taskflow.models.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """
    Generic repository with common CRUD operations.
    
    Provides a consistent interface for database operations
    across all models.
    """
    
    def __init__(self, model: type[ModelType], session: AsyncSession) -> None:
        """
        Initialize repository.
        
        Args:
            model: SQLAlchemy model class
            session: Async database session
        """
        self.model = model
        self.session = session
    
    async def get(
        self,
        id: str,
        load_relations: Optional[list[str]] = None,
    ) -> Optional[ModelType]:
        """
        Get a single record by ID.
        
        Args:
            id: Record primary key
            load_relations: List of relationship names to eagerly load
            
        Returns:
            Model instance or None
        """
        query = select(self.model).where(self.model.id == id)
        
        if load_relations:
            for relation in load_relations:
                query = query.options(selectinload(getattr(self.model, relation)))
        
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
    
    async def get_by(
        self,
        load_relations: Optional[list[str]] = None,
        **filters: Any,
    ) -> Optional[ModelType]:
        """
        Get a single record by filters.
        
        Args:
            load_relations: List of relationship names to eagerly load
            **filters: Column filters
            
        Returns:
            Model instance or None
        """
        query = select(self.model)
        
        for key, value in filters.items():
            query = query.where(getattr(self.model, key) == value)
        
        if load_relations:
            for relation in load_relations:
                query = query.options(selectinload(getattr(self.model, relation)))
        
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
    
    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        order_by: Optional[str] = None,
        descending: bool = False,
        load_relations: Optional[list[str]] = None,
        **filters: Any,
    ) -> list[ModelType]:
        """
        Get multiple records with pagination and filtering.
        
        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
            order_by: Column name to order by
            descending: Sort in descending order
            load_relations: List of relationship names to eagerly load
            **filters: Column filters
            
        Returns:
            List of model instances
        """
        query = select(self.model)
        
        for key, value in filters.items():
            if value is not None:
                query = query.where(getattr(self.model, key) == value)
        
        if order_by:
            col = getattr(self.model, order_by)
            query = query.order_by(col.desc() if descending else col)
        
        if load_relations:
            for relation in load_relations:
                query = query.options(selectinload(getattr(self.model, relation)))
        
        query = query.offset(skip).limit(limit)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def count(self, **filters: Any) -> int:
        """
        Count records matching filters.
        
        Args:
            **filters: Column filters
            
        Returns:
            Number of matching records
        """
        query = select(func.count(self.model.id))
        
        for key, value in filters.items():
            if value is not None:
                query = query.where(getattr(self.model, key) == value)
        
        result = await self.session.execute(query)
        return result.scalar() or 0
    
    async def create(self, **data: Any) -> ModelType:
        """
        Create a new record.
        
        Args:
            **data: Model field values
            
        Returns:
            Created model instance
        """
        if "id" not in data:
            data["id"] = str(uuid4())
        
        instance = self.model(**data)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance
    
    async def update(
        self,
        id: str,
        **data: Any,
    ) -> Optional[ModelType]:
        """
        Update an existing record.
        
        Args:
            id: Record primary key
            **data: Fields to update
            
        Returns:
            Updated model instance or None
        """
        # Remove None values
        data = {k: v for k, v in data.items() if v is not None}
        
        if not data:
            return await self.get(id)
        
        await self.session.execute(
            update(self.model)
            .where(self.model.id == id)
            .values(**data)
        )
        await self.session.flush()
        return await self.get(id)
    
    async def delete(self, id: str) -> bool:
        """
        Delete a record.
        
        Args:
            id: Record primary key
            
        Returns:
            True if record was deleted
        """
        result = await self.session.execute(
            delete(self.model).where(self.model.id == id)
        )
        await self.session.flush()
        return result.rowcount > 0
    
    async def bulk_create(self, items: list[dict[str, Any]]) -> list[ModelType]:
        """
        Create multiple records.
        
        Args:
            items: List of field dictionaries
            
        Returns:
            List of created instances
        """
        instances = []
        for data in items:
            if "id" not in data:
                data["id"] = str(uuid4())
            instance = self.model(**data)
            self.session.add(instance)
            instances.append(instance)
        
        await self.session.flush()
        return instances
    
    async def bulk_update(
        self,
        filters: dict[str, Any],
        **data: Any,
    ) -> int:
        """
        Update multiple records matching filters.
        
        Args:
            filters: Column filters
            **data: Fields to update
            
        Returns:
            Number of updated records
        """
        query = update(self.model)
        
        for key, value in filters.items():
            query = query.where(getattr(self.model, key) == value)
        
        result = await self.session.execute(query.values(**data))
        await self.session.flush()
        return result.rowcount
    
    async def exists(self, **filters: Any) -> bool:
        """
        Check if any record matches filters.
        
        Args:
            **filters: Column filters
            
        Returns:
            True if matching record exists
        """
        return await self.count(**filters) > 0
