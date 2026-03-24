from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text, and_, or_
from sqlalchemy.orm import selectinload
from typing import Optional, List, Dict, Any, Union
from uuid import UUID
from models.catalog.product import Product
from models.auth.user import User
from schemas.catalog.product import ProductResponse
from schemas.auth.user import UserResponse
from core.logging import get_structured_logger

logger = get_structured_logger(__name__)

class SearchService:
    def __init__(self, db: AsyncSession):
        self.db = db
        
    async def autocomplete(self, query: str, search_type: str = "product", limit: int = 10) -> List[Dict[str, Any]]:
        """
        Autocomplete search for products, users, and categories.
        
        Args:
            query: Search query string
            search_type: Type of search ("product", "user", "category")
            limit: Maximum number of suggestions (default 10)
            
        Returns:
            List of suggestions with id, name, and type
        """
        if not query or len(query.strip()) < 2:
            return []
            
        query = query.strip().lower()
        
        if search_type == "product":
            return await self._autocomplete_products(query, limit)
        elif search_type == "user":
            return await self._autocomplete_users(query, limit)
        elif search_type == "category":
            return []  # Return empty list since we don't have category table anymore
        else:
            return []

    async def _autocomplete_products(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Autocomplete for products using pg_trgm similarity matching."""
        pg_trgm_available = await self._check_pg_trgm_availability()
        
        if pg_trgm_available:
            # Use pg_trgm similarity function
            sql_query = text("""
                SELECT 
                    p.id,
                    p.name,
                    p.description,
                    p.category as category_name,
                    GREATEST(
                        CASE WHEN LOWER(p.name) LIKE :prefix_query THEN CAST(:exact_weight AS FLOAT)
                             WHEN LOWER(p.name) LIKE :fuzzy_query THEN CAST(:prefix_weight AS FLOAT)
                             ELSE similarity(LOWER(p.name), :query) * CAST(:fuzzy_weight AS FLOAT) * CAST(:desc_weight AS FLOAT)
                        END,
                        CASE WHEN LOWER(p.description) LIKE CONCAT('%', :query, '%') THEN CAST(:prefix_weight AS FLOAT) * CAST(:desc_weight AS FLOAT)
                         ELSE similarity(LOWER(p.description), :query) * CAST(:fuzzy_weight AS FLOAT) * CAST(:desc_weight AS FLOAT)
                    END
                ) as relevance_score
                FROM products p
                WHERE p.is_active = true
                AND (
                    LOWER(p.name) LIKE :fuzzy_query
                    OR LOWER(p.description) LIKE :fuzzy_query
                    OR similarity(LOWER(p.name), :query) > CAST(:similarity_threshold AS FLOAT)
                    OR similarity(LOWER(p.description), :query) > CAST(:similarity_threshold AS FLOAT)
                )
                ORDER BY relevance_score DESC
                LIMIT :limit
            """)
            
            params = {
                "query": f"%{query}%",
                "prefix_query": f"{query}%",
                "fuzzy_query": f"%{query}%",
                "exact_weight": 1.0,
                "prefix_weight": 0.9,
                "fuzzy_weight": 0.6,
                "desc_weight": 0.4,
                "similarity_threshold": 0.3,
                "limit": limit
            }
            
            result = await self.db.execute(sql_query, params)
            rows = result.fetchall()
            
            suggestions = []
            for row in rows:
                suggestions.append({
                    "id": str(row.id),
                    "name": row.name,
                    "description": row.description,
                    "category_name": row.category_name,
                    "relevance_score": float(row.relevance_score),
                    "type": "product"
                })
            
            return suggestions
        else:
            # Fallback to simple text matching
            base_query = (
                select(Product)
                .where(
                    and_(
                        Product.is_active == True,
                        or_(
                            func.lower(Product.name).like(f'%{query}%'),
                            func.lower(Product.description).like(f'%{query}%')
                        )
                    )
                )
                .order_by(
                    func.lower(Product.name).like(f'{query}%').desc(),
                    Product.name
                )
                .limit(limit)
            )
            
            result = await self.db.execute(base_query)
            products = result.scalars().all()
            
            suggestions = []
            for product in products:
                suggestions.append({
                    "id": str(product.id),
                    "name": product.name,
                    "description": product.description,
                    "category_name": product.category,
                    "type": "product"
                })
            
            return suggestions

    async def _autocomplete_users(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Autocomplete for users using simple text matching."""
        base_query = (
            select(User)
            .where(
                and_(
                    func.lower(User.email).like(f'{query}%'),
                    or_(
                        func.lower(User.firstname).like(f'{query}%'),
                        func.lower(User.lastname).like(f'{query}%')
                    )
                )
            )
            .order_by(User.lastname, User.firstname)
            .limit(limit)
        )
        
        try:
            result = await self.db.execute(base_query)
            users = result.scalars().all()
            
            suggestions = []
            for user in users:
                suggestions.append({
                    "id": str(user.id),
                    "name": f"{user.firstname} {user.lastname}",
                    "email": user.email,
                    "type": "user"
                })
            
            return suggestions
        except Exception as e:
            logger.error(f"Error in _autocomplete_users: {e}")
            return []

    async def _check_pg_trgm_availability(self) -> bool:
        """Check if pg_trgm extension is available."""
        try:
            result = await self.db.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'"))
            return result.scalar_one_or_none() is not None
        except Exception:
            return False

    async def search_products(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 20,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Advanced product search with multiple filtering options and relevance scoring.
        
        Args:
            query: Search query string
            filters: Additional filters (price range, category, etc.)
            limit: Maximum number of results
            offset: Number of results to skip
            
        Returns:
            List of products with relevance scores
        """
        if not query or len(query.strip()) < 2:
            return []
        
        pg_trgm_available = await self._check_pg_trgm_availability()
        
        # Build base conditions
        base_conditions = [Product.is_active == True]
        params = {
            "query": f"%{query}%",
            "prefix_query": f"{query}%",
            "fuzzy_query": f"%{query}%",
            "exact_weight": 1.0,
            "prefix_weight": 0.9,
            "fuzzy_weight": 0.6,
            "desc_weight": 0.4,
            "similarity_threshold": 0.3,
            "limit": limit,
            "offset": offset
        }
        
        # Add filters
        if filters:
            if filters.get("category"):
                base_conditions.append("p.category = :category")
                params["category"] = filters["category"]
                
            if filters.get("min_price") is not None:
                base_conditions.append("""
                    EXISTS (
                        SELECT 1 FROM product_variants pv 
                        WHERE pv.product_id = p.id 
                        AND pv.base_price >= :min_price
                    )
                """)
                params["min_price"] = filters["min_price"]
            
            if filters.get("max_price") is not None:
                base_conditions.append("""
                    EXISTS (
                        SELECT 1 FROM product_variants pv 
                        WHERE pv.product_id = p.id 
                        AND pv.base_price <= :max_price
                    )
                """)
                params["max_price"] = filters["max_price"]
        
        # Build WHERE clause
        where_clause = " AND ".join([str(cond) for cond in base_conditions])
        
        if pg_trgm_available:
            # Use similarity search
            sql_query = text(f"""
                SELECT 
                    p.id,
                    p.name,
                    p.description,
                    p.rating,
                    p.review_count,
                    p.category as category_name,
                    -- Calculate weighted relevance score
                    (
                        -- Name matching (highest weight)
                        CASE WHEN LOWER(p.name) = :query THEN CAST(:exact_weight AS FLOAT)
                             WHEN LOWER(p.name) LIKE :prefix_query THEN CAST(:prefix_weight AS FLOAT)
                             WHEN LOWER(p.name) LIKE :fuzzy_query THEN CAST(:prefix_weight AS FLOAT)
                             ELSE similarity(LOWER(p.name), :query) * CAST(:fuzzy_weight AS FLOAT) * CAST(:desc_weight AS FLOAT)
                        END +
                        -- Description matching
                        CASE WHEN LOWER(p.description) LIKE CONCAT('%', :query, '%') THEN CAST(:prefix_weight AS FLOAT) * CAST(:desc_weight AS FLOAT)
                         ELSE similarity(LOWER(p.description), :query) * CAST(:fuzzy_weight AS FLOAT) * CAST(:desc_weight AS FLOAT)
                    END
                ) as relevance_score
            FROM products p
            WHERE {where_clause}
            AND (
                LOWER(p.name) LIKE CONCAT('%', :query, '%')
                OR LOWER(p.description) LIKE CONCAT('%', :query, '%')
            )
            ORDER BY relevance_score DESC
            LIMIT :limit OFFSET :offset
            """)
            
            result = await self.db.execute(sql_query, params)
            rows = result.fetchall()
            
            suggestions = []
            for row in rows:
                suggestions.append({
                    "id": str(row.id),
                    "name": row.name,
                    "description": row.description,
                    "rating": float(row.rating) if row.rating else 0.0,
                    "review_count": row.review_count or 0,
                    "category_name": row.category_name,
                    "relevance_score": float(row.relevance_score),
                    "type": "product"
                })
            
            return suggestions
        else:
            # Build simple query without similarity function
            base_query = select(
                Product.id,
                Product.name,
                Product.description,
                Product.rating,
                Product.review_count,
                Product.category
            ).where(and_(*base_conditions))
            
            result = await self.db.execute(base_query)
            products = result.scalars().all()
            
            suggestions = []
            for product in products:
                suggestions.append({
                    "id": str(product.id),
                    "name": product.name,
                    "description": product.description,
                    "rating": float(product.rating_average) if product.rating_average else 0.0,
                    "review_count": product.review_count,
                    "category_name": product.category,
                    "type": "product"
                })
            
            return suggestions

    async def get_popular_categories(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get popular categories based on product count.
        Since we use string categories, return hardcoded list.
        """
        popular_categories = [
            {"name": "Grains, Cereals & Beans", "product_count": 15},
            {"name": "Fruits & Vegetables", "product_count": 12},
            {"name": "Meat, Poultry & Seafood", "product_count": 8},
            {"name": "Dairy, Eggs & Fats", "product_count": 6},
            {"name": "Spices, Herbs & Seasonings", "product_count": 10},
            {"name": "Pantry & Sweeteners", "product_count": 7},
            {"name": "Nuts, Seeds & Snacks", "product_count": 9},
            {"name": "Beverages, Tea & Coffee", "product_count": 11},
            {"name": "Bakery & Prepared Foods", "product_count": 5},
            {"name": "Fibers & Industrial Crops", "product_count": 3}
        ]
        
        return popular_categories[:limit]
