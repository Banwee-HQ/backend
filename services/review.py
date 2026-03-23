from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, desc
from typing import Optional, List
from models.review import Review
from models.product import Product
from models.user import User
from schemas.review import ReviewCreate, ReviewUpdate, ReviewResponse
from core.errors import APIException
from core.utils.uuid_utils import uuid7
from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import selectinload, load_only


class ReviewService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_review(self, review_data: ReviewCreate, user_id: UUID):
        # Check if product exists
        product = await self.db.get(Product, review_data.product_id)
        if not product:
            raise APIException(status_code=404, message="Product not found")

        # Check if user has already reviewed this product
        existing_review = await self.db.execute(
            select(Review).where(
                (Review.product_id == review_data.product_id) & (Review.user_id == user_id))
        )
        if existing_review.scalars().first():
            raise APIException(
                status_code=400, message="You have already reviewed this product")

        # Create the review
        new_review = Review(
            id=uuid7(),
            user_id=user_id,
            product_id=review_data.product_id,
            rating=review_data.rating,
            comment=review_data.comment
        )
        self.db.add(new_review)
        await self.db.commit()
        await self.db.refresh(new_review)
        
        # Store the values before updating product rating
        review_id = str(new_review.id)
        rating = new_review.rating
        comment = new_review.comment
        created_at = new_review.created_at
        
        # Update product rating - don't fail if this has an issue
        try:
            print(f"DEBUG: About to update product rating for {review_data.product_id}")
            await self._update_product_rating(review_data.product_id)
            print(f"DEBUG: Product rating updated successfully")
        except Exception as e:
            print(f"WARNING: Could not update product rating: {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()

        # Return plain dict to avoid serialization issues
        return {
            "id": review_id,
            "rating": rating,
            "comment": comment,
            "created_at": created_at.isoformat() if created_at else None
        }

    def _parse_sort_by(self, sort_by: Optional[str]) -> tuple:
        """Parse sort_by parameter and return (field, order) tuple"""
        if not sort_by or '_' not in sort_by:
            return 'created_at', 'desc'
        
        # Split from the right to handle "created_at_desc" properly
        parts = sort_by.rsplit('_', 1)
        if len(parts) != 2:
            return 'created_at', 'desc'
        
        sort_field, sort_order = parts
        
        # Validate field exists on Review model
        if not hasattr(Review, sort_field):
            return 'created_at', 'desc'
        
        # Validate sort order
        if sort_order not in ['asc', 'desc']:
            return 'created_at', 'desc'
        
        return sort_field, sort_order

    async def get_all_reviews(self, page: int = 1, limit: int = 10, min_rating: Optional[int] = None, max_rating: Optional[int] = None, sort_by: Optional[str] = None) -> dict:
        """Get all reviews with pagination and filtering"""
        offset = (page - 1) * limit
        query = select(Review).options(
            selectinload(Review.user).load_only(
                User.id, User.firstname, User.lastname),
            selectinload(Review.product).load_only(
                Product.id, Product.name)
        )
        total_query = select(func.count()).select_from(Review)

        if min_rating is not None:
            query = query.filter(Review.rating >= min_rating)
            total_query = total_query.filter(Review.rating >= min_rating)
        if max_rating is not None:
            query = query.filter(Review.rating <= max_rating)
            total_query = total_query.filter(Review.rating <= max_rating)

        # Apply sorting
        sort_field, sort_order = self._parse_sort_by(sort_by)
        if sort_order == 'asc':
            query = query.order_by(getattr(Review, sort_field).asc())
        else:
            query = query.order_by(getattr(Review, sort_field).desc())

        total_reviews = (await self.db.execute(total_query)).scalar_one()
        reviews = (await self.db.execute(query.offset(offset).limit(limit))).scalars().all()

        return {
            "total": total_reviews,
            "page": page,
            "limit": limit,
            "data": [ReviewResponse.from_orm(r) for r in reviews]
        }

    async def get_reviews_for_product(self, product_id: UUID, page: int = 1, limit: int = 10, min_rating: Optional[int] = None, max_rating: Optional[int] = None, sort_by: Optional[str] = None) -> dict:
        offset = (page - 1) * limit
        query = select(Review).where(Review.product_id == product_id).options(
            selectinload(Review.user).load_only(
                User.id, User.firstname, User.lastname)
        )
        total_query = select(func.count()).select_from(
            Review).where(Review.product_id == product_id)

        if min_rating is not None:
            query = query.filter(Review.rating >= min_rating)
            total_query = total_query.filter(Review.rating >= min_rating)
        if max_rating is not None:
            query = query.filter(Review.rating <= max_rating)
            total_query = total_query.filter(Review.rating <= max_rating)

        # Apply sorting
        sort_field, sort_order = self._parse_sort_by(sort_by)
        if sort_order == 'asc':
            query = query.order_by(getattr(Review, sort_field).asc())
        else:
            query = query.order_by(getattr(Review, sort_field).desc())

        total_reviews = (await self.db.execute(total_query)).scalar_one()
        reviews = (await self.db.execute(query.offset(offset).limit(limit))).scalars().all()

        return {
            "total": total_reviews,
            "page": page,
            "limit": limit,
            "data": [ReviewResponse.from_orm(r) for r in reviews]
        }

    async def get_review_by_id(self, review_id: UUID) -> Optional[Review]:
        result = await self.db.execute(select(Review).where(Review.id == review_id))
        return result.scalars().first()

    async def update_review(self, review_id: UUID, review_data: ReviewUpdate, user_id: UUID) -> Review:
        review = await self.get_review_by_id(review_id)
        if not review:
            raise APIException(status_code=404, message="Review not found")

        if review.user_id != user_id:
            raise APIException(
                status_code=403, message="Not authorized to update this review")

        for key, value in review_data.dict(exclude_unset=True).items():
            setattr(review, key, value)
        review.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(review)

        # Update product rating
        await self._update_product_rating(review.product_id)

        return ReviewResponse.from_orm(review)

    async def delete_review(self, review_id: UUID, user_id: UUID):
        review = await self.get_review_by_id(review_id)
        if not review:
            raise APIException(status_code=404, message="Review not found")

        if review.user_id != user_id:
            raise APIException(
                status_code=403, message="Not authorized to delete this review")

        await self.db.delete(review)
        await self.db.commit()

        # Update product rating
        await self._update_product_rating(review.product_id)

    async def _update_product_rating(self, product_id: UUID):
        # Calculate new average rating and count
        try:
            print(f"DEBUG: _update_product_rating called with product_id={product_id}")
            result = await self.db.execute(
                select(func.avg(Review.rating), func.count(Review.id))
                .where(Review.product_id == product_id)
            )
            print(f"DEBUG: Query executed successfully")
            avg_rating, review_count = result.first()
            print(f"DEBUG: Got avg_rating={avg_rating}, review_count={review_count}")

            product = await self.db.get(Product, product_id)
            print(f"DEBUG: Got product, product={product}")
            if product:
                product.rating_average = avg_rating if avg_rating is not None else 0.0
                product.rating_count = review_count if review_count is not None else 0
                product.review_count = review_count if review_count is not None else 0
                product.updated_at = datetime.utcnow()
                await self.db.commit()
                print(f"DEBUG: About to call db.refresh on product")
                await self.db.refresh(product)
                print(f"DEBUG: refresh completed")
        except Exception as e:
            print(f"ERROR in _update_product_rating: {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
            raise

    async def recalculate_all_product_ratings(self):
        """Recalculate ratings for all products that have reviews"""
        # Get all products that have reviews
        products_with_reviews = await self.db.execute(
            select(Product.id, func.avg(Review.rating).label('avg_rating'), func.count(Review.id).label('review_count'))
            .join(Review, Product.id == Review.product_id)
            .where(Review.is_approved == True)
            .group_by(Product.id)
        )
        
        updated_count = 0
        for product_id, avg_rating, review_count in products_with_reviews:
            product = await self.db.get(Product, product_id)
            if product:
                product.rating_average = float(avg_rating) if avg_rating is not None else 0.0
                product.rating_count = int(review_count) if review_count is not None else 0
                product.review_count = int(review_count) if review_count is not None else 0
                product.updated_at = datetime.utcnow()
                await self.db.commit()
                updated_count += 1
        
        return updated_count