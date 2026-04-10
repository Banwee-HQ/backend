from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID
from core.db import get_db
from core.utils.response import Response
from core.exceptions import APIException
from schemas.catalog.review import Create, Update
from services.catalog.review import ReviewService
from models.accounts.user import User
from services.accounts.auth import AuthService

from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


async def get_current_auth_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> User:
    auth_service = AuthService(db)
    return await auth_service.current_user(token)

router = APIRouter(prefix="/reviews", tags=["Reviews"])


@router.get("/")
async def list(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    product_id: Optional[UUID] = Query(None, description="Filter by product ID"),
    min_rating: Optional[int] = Query(None, ge=1, le=5),
    max_rating: Optional[int] = Query(None, ge=1, le=5),
    sort_by: Optional[str] = Query("created_at_desc", pattern="^(created_at|rating)_(asc|desc)$"),
    db: AsyncSession = Depends(get_db)
):
    """Get all reviews with optional filtering and sorting."""
    try:
        review_service = ReviewService(db)
        
        if product_id:
            # Get reviews for specific product
            reviews = await review_service.for_product(
                product_id, page, limit, min_rating, max_rating, sort_by
            )
        else:
            # Get all reviews
            reviews = await review_service.list(
                page, limit, min_rating, max_rating, sort_by
            )
        
        return Response.success(data=reviews)
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch reviews: {str(e)}"
        )


@router.post("/")
async def create(
    review_data: Create,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new review for a product."""
    try:
        print(f"\n=== CREATE REVIEW START ===")
        print(f"User ID: {current_user.id}")
        print(f"Product ID: {review_data.product_id}")
        print(f"Rating: {review_data.rating}")
        
        review_service = ReviewService(db)
        review = await review_service.create(review_data, current_user.id)
        
        print(f"Review created: {review}")
        print(f"=== CREATE REVIEW SUCCESS ===\n")
        return Response.success(data=review, message="Review created successfully")
    except APIException as e:
        print(f"APIException in create_review: {e.message}")
        raise
    except Exception as e:
        print(f"\n=== CREATE REVIEW ERROR ===")
        print(f"Exception type: {type(e).__name__}")
        print(f"Exception message: {str(e)}")
        import traceback
        traceback.print_exc()
        print(f"=== END ERROR ===\n")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to create review: {str(e)}"
        )


@router.get("/{review_id}")
async def get(
    review_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific review by ID."""
    try:
        review_service = ReviewService(db)
        review = await review_service.get(review_id)
        if not review:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Review not found"
            )
        return Response.success(data=review)
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch review: {str(e)}"
        )


@router.get("/product/{product_id}")
async def for_product(
    product_id: UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    min_rating: Optional[int] = Query(None, ge=1, le=5),
    max_rating: Optional[int] = Query(None, ge=1, le=5),
    sort_by: Optional[str] = Query(
        None, pattern="^(created_at|rating)_(asc|desc)$"),
    db: AsyncSession = Depends(get_db)
):
    """Get all reviews for a specific product with optional filtering and sorting."""
    try:
        review_service = ReviewService(db)
        reviews = await review_service.for_product(
            product_id, page, limit, min_rating, max_rating, sort_by
        )
        return Response.success(data=reviews)
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch reviews for product: {str(e)}"
        )


