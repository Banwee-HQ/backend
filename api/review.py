from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID
from core.db import get_db
from core.utils.response import Response
from core.errors import APIException
from schemas.review import ReviewCreate, ReviewUpdate
from services.review import ReviewService
from models.user import User
from services.auth import AuthService

from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


async def get_current_auth_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> User:
    auth_service = AuthService(db)
    return await auth_service.get_current_user(token)

router = APIRouter(prefix="/reviews", tags=["Reviews"])


@router.get("/")
async def get_reviews(
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
            reviews = await review_service.get_reviews_for_product(
                product_id, page, limit, min_rating, max_rating, sort_by
            )
        else:
            # Get all reviews
            reviews = await review_service.get_all_reviews(
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
async def create_review(
    review_data: ReviewCreate,
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
        review = await review_service.create_review(review_data, current_user.id)
        
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
async def get_review(
    review_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific review by ID."""
    try:
        review_service = ReviewService(db)
        review = await review_service.get_review_by_id(review_id)
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
async def get_reviews_for_product(
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
        reviews = await review_service.get_reviews_for_product(
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


@router.put("/{review_id}")
async def update_review(
    review_id: UUID,
    review_data: ReviewUpdate,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Update an existing review."""
    try:
        review_service = ReviewService(db)
        review = await review_service.update_review(review_id, review_data, current_user.id)
        return Response.success(data=review, message="Review updated successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to update review: {str(e)}"
        )


@router.delete("/{review_id}")
async def delete_review(
    review_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a review."""
    try:
        review_service = ReviewService(db)
        await review_service.delete_review(review_id, current_user.id)
        return Response.success(message="Review deleted successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to delete review: {str(e)}"
        )
