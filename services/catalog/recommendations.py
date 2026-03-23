"""
Smart Product Recommendations Service
Uses complementary (cross-sell), similar (alternative), and behavioral (social proof) algorithms
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.orm import selectinload
from typing import List, Dict, Any, Tuple
from uuid import UUID
from datetime import datetime, timedelta, timezone
from core.logging import get_structured_logger

from models.product import Product, ProductVariant
from models.orders import Order, OrderItem
from models.cart import CartItem
from models.review import Review
from schemas.product import ProductResponse

logger = get_structured_logger(__name__)


class RecommendationService:
    """
    Smart recommendation engine using multiple algorithms:
    1. Complementary (Cross-sell): Products frequently bought together
    2. Similar (Alternative): Products in same category with similar attributes
    3. Behavioral (Social proof): Popular products based on orders and reviews
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        
        # Algorithm weights (sum should be 1.0)
        self.weights = {
            "complementary": 0.4,  # 40% weight for cross-sell
            "similar": 0.35,       # 35% weight for alternatives
            "behavioral": 0.25     # 25% weight for social proof
        }
        
        # Time window for behavioral data (days)
        self.behavioral_window_days = 90
    
    async def get_smart_recommendations(
        self, 
        product_id: UUID, 
        limit: int = 4
    ) -> List[ProductResponse]:
        """
        Get smart product recommendations using all three algorithms.
        Returns top N products ranked by combined score.
        """
        try:
            # Get the source product
            product_query = select(Product).where(Product.id == product_id)
            product_result = await self.db.execute(product_query)
            source_product = product_result.scalar_one_or_none()
            
            if not source_product:
                logger.warning(f"Product {product_id} not found for recommendations")
                return []
            
            # Run all three algorithms in parallel
            complementary_products = await self._get_complementary_products(product_id, limit * 2)
            similar_products = await self._get_similar_products(source_product, limit * 2)
            behavioral_products = await self._get_behavioral_products(product_id, limit * 2)
            
            # Combine and rank products
            ranked_products = self._combine_and_rank(
                complementary_products,
                similar_products,
                behavioral_products,
                limit
            )
            
            # Fetch full product data for top recommendations
            if not ranked_products:
                # Fallback to category-based recommendations
                return await self._get_fallback_recommendations(source_product, limit)
            
            product_ids = [p_id for p_id, _ in ranked_products]
            final_products = await self._fetch_products(product_ids)
            
            logger.info(f"Generated {len(final_products)} recommendations for product {product_id}")
            return final_products
            
        except Exception as e:
            logger.error(f"Error generating recommendations for product {product_id}: {e}")
            # Return fallback recommendations on error
            try:
                product_query = select(Product).where(Product.id == product_id)
                product_result = await self.db.execute(product_query)
                source_product = product_result.scalar_one_or_none()
                if source_product:
                    return await self._get_fallback_recommendations(source_product, limit)
            except:
                pass
            return []
    
    async def _get_complementary_products(
        self, 
        product_id: UUID, 
        limit: int
    ) -> List[Tuple[UUID, float]]:
        """
        Algorithm 1: Complementary Products (Cross-sell)
        Find products frequently bought together with this product.
        """
        try:
            # Find orders containing this product
            orders_with_product = (
                select(OrderItem.order_id)
                .join(ProductVariant, OrderItem.variant_id == ProductVariant.id)
                .where(ProductVariant.product_id == product_id)
                .distinct()
            )
            
            # Find other products in those orders
            query = (
                select(
                    ProductVariant.product_id,
                    func.count(OrderItem.id).label('frequency')
                )
                .join(ProductVariant, OrderItem.variant_id == ProductVariant.id)
                .where(
                    and_(
                        OrderItem.order_id.in_(orders_with_product),
                        ProductVariant.product_id != product_id
                    )
                )
                .group_by(ProductVariant.product_id)
                .order_by(desc('frequency'))
                .limit(limit)
            )
            
            result = await self.db.execute(query)
            products = result.all()
            
            if not products:
                return []
            
            # Normalize scores (0-1 range)
            max_frequency = max(p.frequency for p in products) if products else 1
            return [
                (p.product_id, float(p.frequency) / max_frequency)
                for p in products
            ]
            
        except Exception as e:
            logger.error(f"Error in complementary algorithm: {e}")
            return []
    
    async def _get_similar_products(
        self, 
        source_product: Product, 
        limit: int
    ) -> List[Tuple[UUID, float]]:
        """
        Algorithm 2: Similar Products (Alternative)
        Find products in same category with similar price range and attributes.
        """
        try:
            # Get source product's price range
            source_variants = await self.db.execute(
                select(ProductVariant).where(ProductVariant.product_id == source_product.id)
            )
            source_variants_list = source_variants.scalars().all()
            
            if not source_variants_list:
                return []
            
            avg_price = sum(v.base_price for v in source_variants_list) / len(source_variants_list)
            price_tolerance = avg_price * 0.3  # 30% price tolerance
            
            # Find similar products in same category
            query = (
                select(
                    Product.id,
                    func.avg(ProductVariant.base_price).label('avg_price')
                )
                .join(ProductVariant, Product.id == ProductVariant.product_id)
                .where(
                    and_(
                        Product.category_id == source_product.category_id,
                        Product.id != source_product.id,
                        Product.is_active == True
                    )
                )
                .group_by(Product.id)
                .having(
                    and_(
                        func.avg(ProductVariant.base_price) >= avg_price - price_tolerance,
                        func.avg(ProductVariant.base_price) <= avg_price + price_tolerance
                    )
                )
                .limit(limit)
            )
            
            result = await self.db.execute(query)
            products = result.all()
            
            if not products:
                return []
            
            # Calculate similarity scores based on price proximity
            scores = []
            for p in products:
                price_diff = abs(p.avg_price - avg_price)
                # Closer price = higher score
                similarity = 1.0 - (price_diff / price_tolerance) if price_tolerance > 0 else 1.0
                scores.append((p.id, max(0.0, min(1.0, similarity))))
            
            return sorted(scores, key=lambda x: x[1], reverse=True)
            
        except Exception as e:
            logger.error(f"Error in similar products algorithm: {e}")
            return []
    
    async def _get_behavioral_products(
        self, 
        product_id: UUID, 
        limit: int
    ) -> List[Tuple[UUID, float]]:
        """
        Algorithm 3: Behavioral Products (Social Proof)
        Find popular products based on recent orders and high ratings.
        """
        try:
            # Get source product's category
            product_query = select(Product.category_id).where(Product.id == product_id)
            product_result = await self.db.execute(product_query)
            category_id = product_result.scalar_one_or_none()
            
            if not category_id:
                return []
            
            # Time window for recent activity
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.behavioral_window_days)
            
            # Subquery for order counts
            order_counts = (
                select(
                    ProductVariant.product_id,
                    func.count(OrderItem.id).label('order_count')
                )
                .join(ProductVariant, OrderItem.variant_id == ProductVariant.id)
                .join(Order, OrderItem.order_id == Order.id)
                .where(Order.created_at >= cutoff_date)
                .group_by(ProductVariant.product_id)
                .subquery()
            )
            
            # Subquery for review scores
            review_scores = (
                select(
                    Review.product_id,
                    func.avg(Review.rating).label('avg_rating'),
                    func.count(Review.id).label('review_count')
                )
                .where(Review.created_at >= cutoff_date)
                .group_by(Review.product_id)
                .subquery()
            )
            
            # Combine metrics
            query = (
                select(
                    Product.id,
                    func.coalesce(order_counts.c.order_count, 0).label('orders'),
                    func.coalesce(review_scores.c.avg_rating, 0).label('rating'),
                    func.coalesce(review_scores.c.review_count, 0).label('reviews')
                )
                .outerjoin(order_counts, Product.id == order_counts.c.product_id)
                .outerjoin(review_scores, Product.id == review_scores.c.product_id)
                .where(
                    and_(
                        Product.category_id == category_id,
                        Product.id != product_id,
                        Product.is_active == True
                    )
                )
                .order_by(
                    desc('orders'),
                    desc('rating'),
                    desc('reviews')
                )
                .limit(limit)
            )
            
            result = await self.db.execute(query)
            products = result.all()
            
            if not products:
                return []
            
            # Calculate popularity scores
            max_orders = max(p.orders for p in products) if products else 1
            max_reviews = max(p.reviews for p in products) if products else 1
            
            scores = []
            for p in products:
                # Weighted popularity score
                order_score = (p.orders / max_orders) if max_orders > 0 else 0
                rating_score = (p.rating / 5.0) if p.rating > 0 else 0
                review_score = (p.reviews / max_reviews) if max_reviews > 0 else 0
                
                # Combined score: 50% orders, 30% rating, 20% review count
                popularity = (order_score * 0.5) + (rating_score * 0.3) + (review_score * 0.2)
                scores.append((p.id, popularity))
            
            return sorted(scores, key=lambda x: x[1], reverse=True)
            
        except Exception as e:
            logger.error(f"Error in behavioral algorithm: {e}")
            return []
    
    def _combine_and_rank(
        self,
        complementary: List[Tuple[UUID, float]],
        similar: List[Tuple[UUID, float]],
        behavioral: List[Tuple[UUID, float]],
        limit: int
    ) -> List[Tuple[UUID, float]]:
        """
        Combine scores from all algorithms and rank products.
        """
        # Collect all unique product IDs
        all_products = {}
        
        # Add complementary scores
        for product_id, score in complementary:
            all_products[product_id] = all_products.get(product_id, 0) + (score * self.weights["complementary"])
        
        # Add similar scores
        for product_id, score in similar:
            all_products[product_id] = all_products.get(product_id, 0) + (score * self.weights["similar"])
        
        # Add behavioral scores
        for product_id, score in behavioral:
            all_products[product_id] = all_products.get(product_id, 0) + (score * self.weights["behavioral"])
        
        # Sort by combined score
        ranked = sorted(all_products.items(), key=lambda x: x[1], reverse=True)
        
        return ranked[:limit]
    
    async def _fetch_products(self, product_ids: List[UUID]) -> List[ProductResponse]:
        """
        Fetch full product data for recommended products.
        """
        if not product_ids:
            return []
        
        query = select(Product).options(
            selectinload(Product.category),
            selectinload(Product.supplier),
            selectinload(Product.variants).selectinload(ProductVariant.images),
            selectinload(Product.variants).selectinload(ProductVariant.inventory)
        ).where(
            and_(
                Product.id.in_(product_ids),
                Product.is_active == True
            )
        )
        
        result = await self.db.execute(query)
        products = result.scalars().all()
        
        # Convert to response format
        from services.products import ProductService
        product_service = ProductService(self.db)
        
        # Maintain order from product_ids
        product_map = {p.id: p for p in products}
        ordered_products = [product_map[pid] for pid in product_ids if pid in product_map]
        
        return [product_service._convert_product_to_response(p) for p in ordered_products]
    
    async def _get_fallback_recommendations(
        self, 
        source_product: Product, 
        limit: int
    ) -> List[ProductResponse]:
        """
        Fallback: Simple category-based recommendations.
        """
        try:
            query = select(Product).options(
                selectinload(Product.category),
                selectinload(Product.supplier),
                selectinload(Product.variants).selectinload(ProductVariant.images),
                selectinload(Product.variants).selectinload(ProductVariant.inventory)
            ).where(
                and_(
                    Product.category_id == source_product.category_id,
                    Product.id != source_product.id,
                    Product.is_active == True
                )
            ).limit(limit)
            
            result = await self.db.execute(query)
            products = result.scalars().all()
            
            from services.products import ProductService
            product_service = ProductService(self.db)
            
            return [product_service._convert_product_to_response(p) for p in products]
            
        except Exception as e:
            logger.error(f"Error in fallback recommendations: {e}")
            return []
