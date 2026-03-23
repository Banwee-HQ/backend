"""
Product Categories API Routes
Provides endpoints for managing product categories
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
from uuid import UUID

from core.db import get_db
from core.dependencies import get_current_auth_user, require_admin
from core.utils.response import Response
from core.errors import APIException
from core.logging import get_logger
from models.user import User
from models.product import Category

logger = get_logger(__name__)
router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("/")
async def list_categories(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db)
):
    """List all product categories with optional filtering"""
    try:
        from sqlalchemy import and_
        
        query = select(Category)
        
        if active_only:
            query = query.where(Category.is_active == True)
        
        # Pagination
        total_query = select(Category)
        if active_only:
            total_query = total_query.where(Category.is_active == True)
        
        total_result = await db.execute(select(func.count()).select_from(total_query.subquery()))
        total = total_result.scalar() or 0
        
        query = query.offset((page - 1) * limit).limit(limit)
        
        result = await db.execute(query)
        categories = result.scalars().all()
        
        return Response.success(
            data={
                "categories": [
                    {
                        "id": str(c.id),
                        "name": c.name,
                        "description": c.description,
                        "image_url": c.image_url,
                        "is_active": c.is_active,
                        "created_at": c.created_at.isoformat() if hasattr(c.created_at, 'isoformat') else str(c.created_at)
                    }
                    for c in categories
                ],
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total,
                    "pages": (total + limit - 1) // limit
                }
            },
            message="Categories retrieved successfully"
        )
    except Exception as e:
        logger.error(f"Error listing categories: {e}")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to list categories"
        )


@router.get("/{category_id}")
async def get_category(
    category_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific category by ID"""
    try:
        query = select(Category).where(Category.id == category_id)
        result = await db.execute(query)
        category = result.scalar_one_or_none()
        
        if not category:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Category not found"
            )
        
        return Response.success(
            data={
                "id": str(category.id),
                "name": category.name,
                "description": category.description,
                "image_url": category.image_url,
                "is_active": category.is_active,
                "created_at": category.created_at.isoformat() if hasattr(category.created_at, 'isoformat') else str(category.created_at)
            }
        )
    except APIException:
        raise
    except Exception as e:
        logger.error(f"Error getting category: {e}")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to get category"
        )


@router.post("/", dependencies=[Depends(require_admin)])
async def create_category(
    category_data: dict,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new category (Admin only)"""
    try:
        new_category = Category(
            name=category_data.get("name"),
            description=category_data.get("description"),
            image_url=category_data.get("image_url"),
            is_active=category_data.get("is_active", True)
        )
        
        db.add(new_category)
        await db.commit()
        await db.refresh(new_category)
        
        return Response.success(
            data={
                "id": str(new_category.id),
                "name": new_category.name,
                "description": new_category.description,
                "image_url": new_category.image_url,
                "is_active": new_category.is_active,
                "created_at": new_category.created_at.isoformat() if hasattr(new_category.created_at, 'isoformat') else str(new_category.created_at)
            },
            message="Category created successfully",
            status_code=status.HTTP_201_CREATED
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating category: {e}")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to create category"
        )


@router.put("/{category_id}", dependencies=[Depends(require_admin)])
async def update_category(
    category_id: UUID,
    category_data: dict,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a category (Admin only)"""
    try:
        query = select(Category).where(Category.id == category_id)
        result = await db.execute(query)
        category = result.scalar_one_or_none()
        
        if not category:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Category not found"
            )
        
        # Update fields
        for key, value in category_data.items():
            if value is not None and hasattr(category, key):
                setattr(category, key, value)
        
        await db.commit()
        await db.refresh(category)
        
        return Response.success(
            data={
                "id": str(category.id),
                "name": category.name,
                "description": category.description,
                "image_url": category.image_url,
                "is_active": category.is_active,
                "created_at": category.created_at.isoformat() if hasattr(category.created_at, 'isoformat') else str(category.created_at)
            },
            message="Category updated successfully"
        )
    except APIException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating category: {e}")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to update category"
        )


@router.delete("/{category_id}", dependencies=[Depends(require_admin)])
async def delete_category(
    category_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a category (Admin only)"""
    try:
        query = select(Category).where(Category.id == category_id)
        result = await db.execute(query)
        category = result.scalar_one_or_none()
        
        if not category:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Category not found"
            )
        
        await db.delete(category)
        await db.commit()
        
        return Response.success(
            message="Category deleted successfully"
        )
    except APIException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting category: {e}")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to delete category"
        )
