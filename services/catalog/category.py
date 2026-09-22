from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload
from typing import Optional, List, Tuple
from uuid import UUID

from core.utils.uuid_utils import uuid7
from models.catalog.category import Category
from models.catalog.product import Product
from schemas.catalog.category import Create as CategoryCreate, Update as CategoryUpdate
from core.exceptions import APIException
from core.logging import get_structured_logger

logger = get_structured_logger(__name__)


class CategoryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, category_id: UUID) -> Optional[Category]:
        result = await self.db.execute(select(Category).where(Category.id == category_id))
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Optional[Category]:
        result = await self.db.execute(select(Category).where(Category.slug == slug))
        return result.scalar_one_or_none()

    async def list(
        self,
        page: int = 1,
        limit: int = 50,
        active_only: bool = False,
        parent_id: Optional[UUID] = None,
    ) -> Tuple[List[Category], int]:
        """List categories flat (no children nesting), with pagination."""
        conditions = []
        if active_only:
            conditions.append(Category.is_active.is_(True))
        if parent_id is not None:
            conditions.append(Category.parent_id == parent_id)

        query = select(Category)
        count_query = select(func.count(Category.id))
        if conditions:
            query = query.where(and_(*conditions))
            count_query = count_query.where(and_(*conditions))

        total = await self.db.scalar(count_query) or 0

        query = query.order_by(Category.sort_order, Category.name).offset((page - 1) * limit).limit(limit)
        result = await self.db.execute(query)
        return result.scalars().all(), total

    async def tree(self, active_only: bool = True) -> List[Category]:
        """Top-level categories with children eagerly loaded (up to 3 levels deep)."""
        query = select(Category).where(Category.parent_id.is_(None))
        if active_only:
            query = query.where(Category.is_active.is_(True))

        query = query.options(
            selectinload(Category.children).selectinload(Category.children).selectinload(Category.children)
        ).order_by(Category.sort_order, Category.name)

        result = await self.db.execute(query)
        return result.scalars().unique().all()

    async def create(self, data: CategoryCreate) -> Category:
        existing = await self.get_by_slug(data.slug)
        if existing:
            raise APIException(status_code=400, message="A category with this slug already exists")

        if data.parent_id:
            parent = await self.get(data.parent_id)
            if not parent:
                raise APIException(status_code=404, message="Parent category not found")

        category = Category(id=uuid7(), **data.model_dump())
        self.db.add(category)
        await self.db.commit()
        await self.db.refresh(category)
        return category

    async def update(self, category_id: UUID, data: CategoryUpdate) -> Optional[Category]:
        category = await self.get(category_id)
        if not category:
            return None

        update_dict = data.model_dump(exclude_unset=True)

        if update_dict.get("slug") and update_dict["slug"] != category.slug:
            existing = await self.get_by_slug(update_dict["slug"])
            if existing:
                raise APIException(status_code=400, message="A category with this slug already exists")

        new_parent_id = update_dict.get("parent_id")
        if new_parent_id is not None:
            if new_parent_id == category_id:
                raise APIException(status_code=400, message="A category cannot be its own parent")
            parent = await self.get(new_parent_id)
            if not parent:
                raise APIException(status_code=404, message="Parent category not found")

        for field, value in update_dict.items():
            setattr(category, field, value)

        await self.db.commit()
        await self.db.refresh(category)
        return category

    async def delete(self, category_id: UUID) -> bool:
        category = await self.get(category_id)
        if not category:
            return False

        product_count = await self.db.scalar(
            select(func.count(Product.id)).where(Product.category_id == category_id)
        )
        if product_count:
            raise APIException(
                status_code=400,
                message=f"Cannot delete category: {product_count} product(s) are still assigned to it"
            )

        children_count = await self.db.scalar(
            select(func.count(Category.id)).where(Category.parent_id == category_id)
        )
        if children_count:
            raise APIException(status_code=400, message="Cannot delete a category that has subcategories")

        await self.db.delete(category)
        await self.db.commit()
        return True
