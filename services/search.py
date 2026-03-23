from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text, and_, or_
from sqlalchemy.orm import selectinload
from typing import Optional, List, Dict, Any, Union
from uuid import UUID
from models.product import Product, Category
from models.user import User
from schemas.product import ProductResponse, CategoryResponse
from schemas.user import UserResponse
from core.logging import get_structured_logger

logger = get_structured_logger(__name__)


class SearchService:
    def __init__(self, db: AsyncSession):
        self.db = db
        
        # Similarity threshold for fuzzy matching (0.0 to 1.0)
        self.similarity_threshold = 0.3
        
        # Weights for different match types
        self.weights = {
            "exact": 1.0,
            "prefix": 0.8,
            "fuzzy": 0.5
        }
        
        # Field weights for product search
        self.product_field_weights = {
            "name": 1.0,
            "description": 0.6,
            "category": 0.4,
            "tags": 0.3
        }
        
        # Check if pg_trgm extension is available
        self.pg_trgm_available = None

    async def _check_pg_trgm_availability(self) -> bool:
        """Check if pg_trgm extension is available and enabled."""
        if self.pg_trgm_available is not None:
            return self.pg_trgm_available
            
        try:
            result = await self.db.execute(text("""
                SELECT EXISTS(
                    SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'
                );
            """))
            self.pg_trgm_available = result.scalar()
            if not self.pg_trgm_available:
                logger.warning("pg_trgm extension is not enabled. Falling back to basic text search.")
            return self.pg_trgm_available
        except Exception as e:
            logger.error(f"Error checking pg_trgm availability: {e}")
            self.pg_trgm_available = False
            return False

    async def autocomplete(
        self, 
        query: str, 
        search_type: str = "product", 
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Provide autocomplete suggestions based on prefix matching.
        
        Args:
            query: Search query string
            search_type: Type of search ("product", "user", "category")
            limit: Maximum number of suggestions (default 10)
            
        Returns:
            List of autocomplete suggestions with relevance scores
        """
        if not query or len(query.strip()) < 2:
            return []
            
        query = query.strip().lower()
        
        if search_type == "product":
            return await self._autocomplete_products(query, limit)
        elif search_type == "user":
            return await self._autocomplete_users(query, limit)
        elif search_type == "category":
            return await self._autocomplete_categories(query, limit)
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
                    c.name as category_name,
                    GREATEST(
                        CASE WHEN LOWER(p.name) LIKE :prefix_query THEN CAST(:exact_weight AS FLOAT)
                             WHEN LOWER(p.name) LIKE :fuzzy_query THEN CAST(:prefix_weight AS FLOAT)
                             ELSE similarity(LOWER(p.name), :query) * CAST(:fuzzy_weight AS FLOAT)
                        END,
                        CASE WHEN LOWER(p.description) LIKE :prefix_query THEN CAST(:exact_weight AS FLOAT) * CAST(:desc_weight AS FLOAT)
                             WHEN LOWER(p.description) LIKE :fuzzy_query THEN CAST(:prefix_weight AS FLOAT) * CAST(:desc_weight AS FLOAT)
                             ELSE similarity(LOWER(p.description), :query) * CAST(:fuzzy_weight AS FLOAT) * CAST(:desc_weight AS FLOAT)
                        END,
                        CASE WHEN LOWER(c.name) LIKE :prefix_query THEN CAST(:exact_weight AS FLOAT) * CAST(:cat_weight AS FLOAT)
                             WHEN LOWER(c.name) LIKE :fuzzy_query THEN CAST(:prefix_weight AS FLOAT) * CAST(:cat_weight AS FLOAT)
                             ELSE similarity(LOWER(c.name), :query) * CAST(:fuzzy_weight AS FLOAT) * CAST(:cat_weight AS FLOAT)
                        END
                    ) as relevance_score
                FROM products p
                LEFT JOIN categories c ON p.category_id = c.id
                WHERE p.is_active = true
                AND (
                    LOWER(p.name) LIKE :fuzzy_query
                    OR LOWER(p.description) LIKE :fuzzy_query
                    OR LOWER(c.name) LIKE :fuzzy_query
                    OR similarity(LOWER(p.name), :query) > CAST(:similarity_threshold AS FLOAT)
                    OR similarity(LOWER(p.description), :query) > CAST(:similarity_threshold AS FLOAT)
                    OR similarity(LOWER(c.name), :query) > CAST(:similarity_threshold AS FLOAT)
                )
                ORDER BY relevance_score DESC, p.rating DESC, p.review_count DESC
                LIMIT :limit
            """)
            
            params = {
                "query": query,
                "prefix_query": f"{query}%",
                "fuzzy_query": f"%{query}%",
                "exact_weight": float(self.weights["exact"]),
                "prefix_weight": float(self.weights["prefix"]),
                "fuzzy_weight": float(self.weights["fuzzy"]),
                "desc_weight": float(self.product_field_weights["description"]),
                "cat_weight": float(self.product_field_weights["category"]),
                "similarity_threshold": float(self.similarity_threshold),
                "limit": limit
            }
        else:
            # Fallback to basic ILIKE matching
            sql_query = text("""
                SELECT 
                    p.id,
                    p.name,
                    p.description,
                    c.name as category_name,
                    GREATEST(
                        CASE WHEN LOWER(p.name) LIKE :prefix_query THEN CAST(:exact_weight AS FLOAT)
                             WHEN LOWER(p.name) LIKE :fuzzy_query THEN CAST(:prefix_weight AS FLOAT)
                             ELSE 0.1
                        END,
                        CASE WHEN LOWER(p.description) LIKE :prefix_query THEN CAST(:exact_weight AS FLOAT) * CAST(:desc_weight AS FLOAT)
                             WHEN LOWER(p.description) LIKE :fuzzy_query THEN CAST(:prefix_weight AS FLOAT) * CAST(:desc_weight AS FLOAT)
                             ELSE 0.1 * CAST(:desc_weight AS FLOAT)
                        END,
                        CASE WHEN LOWER(c.name) LIKE :prefix_query THEN CAST(:exact_weight AS FLOAT) * CAST(:cat_weight AS FLOAT)
                             WHEN LOWER(c.name) LIKE :fuzzy_query THEN CAST(:prefix_weight AS FLOAT) * CAST(:cat_weight AS FLOAT)
                             ELSE 0.1 * CAST(:cat_weight AS FLOAT)
                        END
                    ) as relevance_score
                FROM products p
                LEFT JOIN categories c ON p.category_id = c.id
                WHERE p.is_active = true
                AND (
                    LOWER(p.name) LIKE :fuzzy_query
                    OR LOWER(p.description) LIKE :fuzzy_query
                    OR LOWER(c.name) LIKE :fuzzy_query
                )
                ORDER BY relevance_score DESC, p.rating DESC, p.review_count DESC
                LIMIT :limit
            """)
            
            params = {
                "prefix_query": f"{query}%",
                "fuzzy_query": f"%{query}%",
                "exact_weight": float(self.weights["exact"]),
                "prefix_weight": float(self.weights["prefix"]),
                "desc_weight": float(self.product_field_weights["description"]),
                "cat_weight": float(self.product_field_weights["category"]),
                "limit": limit
            }
        
        try:
            result = await self.db.execute(sql_query, params)
            
            suggestions = []
            for row in result:
                suggestions.append({
                    "id": str(row.id),
                    "name": row.name,
                    "description": row.description,
                    "category_name": row.category_name,
                    "type": "product",
                    "relevance_score": float(row.relevance_score)
                })
                
            return suggestions
        except Exception as e:
            logger.error(f"Error in _autocomplete_products: {e}")
            return []

    async def _autocomplete_users(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Autocomplete for users using simple text matching."""
        base_query = select(
            User.id,
            User.firstname,
            User.lastname,
            User.email
        ).where(
            and_(
                User.is_active == True,
                or_(
                    func.lower(User.firstname).like(f'{query}%'),
                    func.lower(User.lastname).like(f'{query}%'),
                    func.lower(User.email).like(f'{query}%'),
                    func.lower(User.firstname).like(f'%{query}%'),
                    func.lower(User.lastname).like(f'%{query}%')
                )
            )
        ).order_by(
            func.lower(User.firstname).like(f'{query}%').desc(),
            User.firstname,
            User.lastname
        ).limit(limit)
        
        try:
            result = await self.db.execute(base_query)
            users = result.fetchall()
            
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

    async def _autocomplete_categories(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Autocomplete for categories using simple text matching."""
        base_query = select(
            Category.id,
            Category.name,
            Category.description
        ).where(
            and_(
                Category.is_active == True,
                or_(
                    func.lower(Category.name).like(f'{query}%'),
                    func.lower(Category.name).like(f'%{query}%'),
                    func.lower(Category.description).like(f'%{query}%')
                )
            )
        ).order_by(
            func.lower(Category.name).like(f'{query}%').desc(),
            Category.name
        ).limit(limit)
        
        try:
            result = await self.db.execute(base_query)
            categories = result.fetchall()
            
            suggestions = []
            for category in categories:
                suggestions.append({
                    "id": str(category.id),
                    "name": category.name,
                    "description": category.description,
                    "type": "category"
                })
            
            return suggestions
        except Exception as e:
            logger.error(f"Error in _autocomplete_categories: {e}")
            return []
        """Autocomplete for categories using prefix matching and fuzzy search."""
        sql_query = text("""
            SELECT 
                c.id,
                c.name,
                c.description,
                GREATEST(
                    CASE WHEN LOWER(c.name) LIKE :prefix_query THEN CAST(:exact_weight AS FLOAT)
                         WHEN LOWER(c.name) LIKE :fuzzy_query THEN CAST(:prefix_weight AS FLOAT)
                         ELSE similarity(LOWER(c.name), :query) * CAST(:fuzzy_weight AS FLOAT)
                    END,
                    CASE WHEN LOWER(c.description) LIKE :prefix_query THEN CAST(:exact_weight AS FLOAT) * 0.5
                         WHEN LOWER(c.description) LIKE :fuzzy_query THEN CAST(:prefix_weight AS FLOAT) * 0.5
                         ELSE similarity(LOWER(c.description), :query) * CAST(:fuzzy_weight AS FLOAT) * 0.5
                    END
                ) as relevance_score
            FROM categories c
            WHERE c.is_active = true
            AND (
                LOWER(c.name) LIKE :fuzzy_query
                OR LOWER(c.description) LIKE :fuzzy_query
                OR similarity(LOWER(c.name), :query) > CAST(:similarity_threshold AS FLOAT)
                OR similarity(LOWER(c.description), :query) > CAST(:similarity_threshold AS FLOAT)
            )
            ORDER BY relevance_score DESC
            LIMIT :limit
        """)
        
        result = await self.db.execute(sql_query, {
            "query": query,
            "prefix_query": f"{query}%",
            "fuzzy_query": f"%{query}%",
            "exact_weight": self.weights["exact"],
            "prefix_weight": self.weights["prefix"],
            "fuzzy_weight": self.weights["fuzzy"],
            "similarity_threshold": self.similarity_threshold,
            "limit": limit
        })
        
        suggestions = []
        for row in result:
            suggestions.append({
                "id": str(row.id),
                "name": row.name,
                "description": row.description,
                "type": "category",
                "relevance_score": float(row.relevance_score)
            })
            
        return suggestions

    async def fuzzy_search_products(
        self, 
        query: str, 
        limit: int = 20,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform fuzzy search on products with spell correction and weighted ranking.
        
        Args:
            query: Search query string
            limit: Maximum number of results
            filters: Additional filters (price range, category, etc.)
            
        Returns:
            List of products with relevance scores
        """
        if not query or len(query.strip()) < 2:
            return []
            
        query = query.strip().lower()
        
        # Build base conditions
        base_conditions = ["p.is_active = true"]
        params = {
            "query": query,
            "similarity_threshold": float(self.similarity_threshold),
            "limit": limit,
            "exact_weight": float(self.weights["exact"]),
            "prefix_weight": float(self.weights["prefix"]),
            "fuzzy_weight": float(self.weights["fuzzy"]),
            "name_weight": float(self.product_field_weights["name"]),
            "desc_weight": float(self.product_field_weights["description"]),
            "cat_weight": float(self.product_field_weights["category"]),
            "tag_weight": float(self.product_field_weights["tags"])
        }
        
        # Add filters
        if filters:
            if filters.get("category_id"):
                base_conditions.append("p.category_id = :category_id")
                params["category_id"] = filters["category_id"]
                
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
        
        where_clause = " AND ".join(base_conditions)
        
        sql_query = text(f"""
            SELECT 
                p.id,
                p.name,
                p.description,
                p.rating,
                p.review_count,
                c.name as category_name,
                -- Calculate weighted relevance score
                (
                    -- Name matching (highest weight)
                    CASE WHEN LOWER(p.name) = :query THEN CAST(:exact_weight AS FLOAT) * CAST(:name_weight AS FLOAT)
                         WHEN LOWER(p.name) LIKE CONCAT(:query, '%') THEN CAST(:prefix_weight AS FLOAT) * CAST(:name_weight AS FLOAT) * 0.9
                         WHEN LOWER(p.name) LIKE CONCAT('%', :query, '%') THEN CAST(:prefix_weight AS FLOAT) * CAST(:name_weight AS FLOAT) * 0.7
                         ELSE similarity(LOWER(p.name), :query) * CAST(:fuzzy_weight AS FLOAT) * CAST(:name_weight AS FLOAT)
                    END +
                    -- Description matching
                    CASE WHEN LOWER(p.description) LIKE CONCAT('%', :query, '%') THEN CAST(:prefix_weight AS FLOAT) * CAST(:desc_weight AS FLOAT)
                         ELSE similarity(LOWER(p.description), :query) * CAST(:fuzzy_weight AS FLOAT) * CAST(:desc_weight AS FLOAT)
                    END +
                    -- Category matching
                    CASE WHEN LOWER(c.name) = :query THEN CAST(:exact_weight AS FLOAT) * CAST(:cat_weight AS FLOAT)
                         WHEN LOWER(c.name) LIKE CONCAT(:query, '%') THEN CAST(:prefix_weight AS FLOAT) * CAST(:cat_weight AS FLOAT)
                         WHEN LOWER(c.name) LIKE CONCAT('%', :query, '%') THEN CAST(:prefix_weight AS FLOAT) * CAST(:cat_weight AS FLOAT) * 0.7
                         ELSE similarity(LOWER(c.name), :query) * CAST(:fuzzy_weight AS FLOAT) * CAST(:cat_weight AS FLOAT)
                    END +
                    -- Dietary tags matching (if tags contain the query)
                    CASE WHEN p.dietary_tags::text ILIKE CONCAT('%', :query, '%') THEN CAST(:prefix_weight AS FLOAT) * CAST(:tag_weight AS FLOAT)
                         ELSE 0
                    END +
                    -- Boost for higher rated products
                    (COALESCE(p.rating, 0) / 5.0) * 0.1 +
                    -- Boost for products with more reviews
                    LEAST(COALESCE(p.review_count, 0) / 100.0, 0.1)
                ) as relevance_score
            FROM products p
            LEFT JOIN categories c ON p.category_id = c.id
            WHERE {where_clause}
            AND (
                LOWER(p.name) LIKE CONCAT('%', :query, '%')
                OR LOWER(p.description) LIKE CONCAT('%', :query, '%')
                OR LOWER(c.name) LIKE CONCAT('%', :query, '%')
                OR p.dietary_tags::text ILIKE CONCAT('%', :query, '%')
                OR similarity(LOWER(p.name), :query) > CAST(:similarity_threshold AS FLOAT)
                OR similarity(LOWER(p.description), :query) > CAST(:similarity_threshold AS FLOAT)
                OR similarity(LOWER(c.name), :query) > CAST(:similarity_threshold AS FLOAT)
            )
            ORDER BY relevance_score DESC, p.rating DESC, p.review_count DESC
            LIMIT :limit
        """)
        
        result = await self.db.execute(sql_query, params)
        
        products = []
        for row in result:
            products.append({
                "id": str(row.id),
                "name": row.name,
                "description": row.description,
                "rating": float(row.rating) if row.rating else 0.0,
                "review_count": row.review_count or 0,
                "category_name": row.category_name,
                "relevance_score": float(row.relevance_score),
                "type": "product"
            })
            
        return products

    async def search_users(
        self, 
        query: str, 
        limit: int = 20,
        role_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search users with prefix matching on name and email.
        
        Args:
            query: Search query string
            limit: Maximum number of results
            role_filter: Filter by user role (Customer, Supplier, Admin)
            
        Returns:
            List of users with relevance scores
        """
        if not query or len(query.strip()) < 2:
            return []
            
        query = query.strip().lower()
        
        # Build base conditions
        base_conditions = ["u.is_active = true"]
        params = {
            "query": query,
            "similarity_threshold": float(self.similarity_threshold),
            "limit": limit,
            "exact_weight": float(self.weights["exact"]),
            "prefix_weight": float(self.weights["prefix"]),
            "fuzzy_weight": float(self.weights["fuzzy"])
        }
        
        if role_filter:
            base_conditions.append("u.role = :role_filter")
            params["role_filter"] = role_filter
        
        where_clause = " AND ".join(base_conditions)
        
        sql_query = text(f"""
            SELECT 
                u.id,
                u.firstname,
                u.lastname,
                u.email,
                u.role,
                u.verified,
                (
                    -- First name matching
                    CASE WHEN LOWER(u.firstname) = :query THEN CAST(:exact_weight AS FLOAT)
                         WHEN LOWER(u.firstname) LIKE CONCAT(:query, '%') THEN CAST(:prefix_weight AS FLOAT)
                         WHEN LOWER(u.firstname) LIKE CONCAT('%', :query, '%') THEN CAST(:prefix_weight AS FLOAT) * 0.7
                         ELSE similarity(LOWER(u.firstname), :query) * CAST(:fuzzy_weight AS FLOAT)
                    END +
                    -- Last name matching
                    CASE WHEN LOWER(u.lastname) = :query THEN CAST(:exact_weight AS FLOAT)
                         WHEN LOWER(u.lastname) LIKE CONCAT(:query, '%') THEN CAST(:prefix_weight AS FLOAT)
                         WHEN LOWER(u.lastname) LIKE CONCAT('%', :query, '%') THEN CAST(:prefix_weight AS FLOAT) * 0.7
                         ELSE similarity(LOWER(u.lastname), :query) * CAST(:fuzzy_weight AS FLOAT)
                    END +
                    -- Email matching (lower weight)
                    CASE WHEN LOWER(u.email) LIKE CONCAT(:query, '%') THEN CAST(:prefix_weight AS FLOAT) * 0.8
                         WHEN LOWER(u.email) LIKE CONCAT('%', :query, '%') THEN CAST(:prefix_weight AS FLOAT) * 0.6
                         ELSE similarity(LOWER(u.email), :query) * CAST(:fuzzy_weight AS FLOAT) * 0.8
                    END +
                    -- Full name matching (concatenated)
                    CASE WHEN LOWER(CONCAT(u.firstname, ' ', u.lastname)) LIKE CONCAT('%', :query, '%') THEN CAST(:prefix_weight AS FLOAT) * 0.9
                         ELSE similarity(LOWER(CONCAT(u.firstname, ' ', u.lastname)), :query) * CAST(:fuzzy_weight AS FLOAT) * 0.9
                    END
                ) as relevance_score
            FROM users u
            WHERE {where_clause}
            AND (
                LOWER(u.firstname) LIKE CONCAT('%', :query, '%')
                OR LOWER(u.lastname) LIKE CONCAT('%', :query, '%')
                OR LOWER(u.email) LIKE CONCAT('%', :query, '%')
                OR LOWER(CONCAT(u.firstname, ' ', u.lastname)) LIKE CONCAT('%', :query, '%')
                OR similarity(LOWER(u.firstname), :query) > CAST(:similarity_threshold AS FLOAT)
                OR similarity(LOWER(u.lastname), :query) > CAST(:similarity_threshold AS FLOAT)
                OR similarity(LOWER(u.email), :query) > CAST(:similarity_threshold AS FLOAT)
            )
            ORDER BY relevance_score DESC, u.verified DESC
            LIMIT :limit
        """)
        
        result = await self.db.execute(sql_query, params)
        
        users = []
        for row in result:
            users.append({
                "id": str(row.id),
                "firstname": row.firstname,
                "lastname": row.lastname,
                "full_name": f"{row.firstname} {row.lastname}",
                "email": row.email,
                "role": row.role,
                "verified": row.verified,
                "relevance_score": float(row.relevance_score),
                "type": "user"
            })
            
        return users

    async def search_categories(
        self, 
        query: str, 
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search categories with prefix matching and fuzzy search.
        
        Args:
            query: Search query string
            limit: Maximum number of results
            
        Returns:
            List of categories with relevance scores
        """
        if not query or len(query.strip()) < 2:
            return []
            
        query = query.strip().lower()
        
        sql_query = text("""
            SELECT 
                c.id,
                c.name,
                c.description,
                c.image_url,
                COUNT(p.id) as product_count,
                (
                    -- Name matching (highest weight)
                    CASE WHEN LOWER(c.name) = :query THEN CAST(:exact_weight AS FLOAT)
                         WHEN LOWER(c.name) LIKE CONCAT(:query, '%') THEN CAST(:prefix_weight AS FLOAT)
                         WHEN LOWER(c.name) LIKE CONCAT('%', :query, '%') THEN CAST(:prefix_weight AS FLOAT) * 0.7
                         ELSE similarity(LOWER(c.name), :query) * CAST(:fuzzy_weight AS FLOAT)
                    END +
                    -- Description matching
                    CASE WHEN LOWER(c.description) LIKE CONCAT('%', :query, '%') THEN CAST(:prefix_weight AS FLOAT) * 0.5
                         ELSE similarity(LOWER(c.description), :query) * CAST(:fuzzy_weight AS FLOAT) * 0.5
                    END +
                    -- Boost for categories with more products
                    LEAST(COUNT(p.id) / 10.0, 0.2)
                ) as relevance_score
            FROM categories c
            LEFT JOIN products p ON c.id = p.category_id AND p.is_active = true
            WHERE c.is_active = true
            AND (
                LOWER(c.name) LIKE CONCAT('%', :query, '%')
                OR LOWER(c.description) LIKE CONCAT('%', :query, '%')
                OR similarity(LOWER(c.name), :query) > CAST(:similarity_threshold AS FLOAT)
                OR similarity(LOWER(c.description), :query) > CAST(:similarity_threshold AS FLOAT)
            )
            GROUP BY c.id, c.name, c.description, c.image_url
            ORDER BY relevance_score DESC, product_count DESC
            LIMIT :limit
        """)
        
        result = await self.db.execute(sql_query, {
            "query": query,
            "similarity_threshold": float(self.similarity_threshold),
            "limit": limit,
            "exact_weight": float(self.weights["exact"]),
            "prefix_weight": float(self.weights["prefix"]),
            "fuzzy_weight": float(self.weights["fuzzy"])
        })
        
        categories = []
        for row in result:
            categories.append({
                "id": str(row.id),
                "name": row.name,
                "description": row.description,
                "image_url": row.image_url,
                "product_count": row.product_count,
                "relevance_score": float(row.relevance_score),
                "type": "category"
            })
            
        return categories

    def calculate_levenshtein_distance(self, s1: str, s2: str) -> int:
        """
        Calculate Levenshtein distance between two strings.
        Used as fallback when PostgreSQL functions are not available.
        """
        if len(s1) < len(s2):
            return self.calculate_levenshtein_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = list(range(len(s2) + 1))
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        
        return previous_row[-1]

    def calculate_similarity_score(self, s1: str, s2: str) -> float:
        """
        Calculate similarity score between two strings (0.0 to 1.0).
        Higher score means more similar.
        """
        if not s1 or not s2:
            return 0.0
            
        max_len = max(len(s1), len(s2))
        if max_len == 0:
            return 1.0
            
        distance = self.calculate_levenshtein_distance(s1.lower(), s2.lower())
        return 1.0 - (distance / max_len)