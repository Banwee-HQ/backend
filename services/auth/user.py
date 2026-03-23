from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, and_, func, text
from sqlalchemy.orm import selectinload
from typing import List, Optional, Dict, Any
from uuid import UUID
from core.utils.uuid_utils import uuid7
from models.user import Address, User
from models.orders import Order
from core.errors import APIException
from schemas.user import UserCreate, UserUpdate
from datetime import datetime, timedelta, timezone
import secrets
from core.utils.messages.email import send_email
import httpx
from core.config import settings
from core.utils.encryption import PasswordManager
from core.logging import get_structured_logger

logger = get_structured_logger(__name__)

class AddressService:

    """Service layer for managing user addresses."""



    def __init__(self, db: AsyncSession):

        self.db = db



    # -----------------------------------------------------------

    # CRUD OPERATIONS

    # -----------------------------------------------------------



    async def create_address(

        self,

        user_id: UUID,

        street: Optional[str] = None,

        city: Optional[str] = None,

        state: Optional[str] = None,

        country: Optional[str] = None,

        post_code: Optional[str] = None,

        kind: str = "Shipping",

    ) -> Address:

        """Create a new address for a user."""

        address = Address(
            id=uuid7(),
            user_id=user_id,

            street=street,

            city=city,

            state=state,

            country=country,

            post_code=post_code,

            kind=kind,

        )

        self.db.add(address)

        await self.db.commit()

        await self.db.refresh(address)

        return address



    async def get_address(self, address_id: UUID) -> Optional[Address]:

        """Retrieve an address by ID."""

        query = select(Address).where(Address.id == address_id)

        result = await self.db.execute(query)

        return result.scalars().first()



    async def get_user_addresses(self, user_id: UUID) -> List[Address]:

        """Fetch all addresses for a given user."""

        query = (

            select(Address)

            .where(Address.user_id == user_id)

            .order_by(Address.created_at.desc())

        )

        result = await self.db.execute(query)

        return result.scalars().all()



    async def update_address(self, address_id: UUID, user_id: UUID, **kwargs) -> Optional[Address]:

        """Update address fields dynamically."""

        query = update(Address)

        query = query.where(and_(Address.id == address_id,

                            Address.user_id == user_id))

        query = query.values(**kwargs)

        query = query.execution_options(synchronize_session="fetch")



        await self.db.execute(query)

        await self.db.commit()

        return await self.get_address(address_id)



    async def delete_address(self, address_id: UUID, user_id: UUID = None) -> bool:

        """Delete an address by ID."""

        if user_id:

            result = await self.db.execute(delete(Address).where(and_(Address.id == address_id, Address.user_id == user_id)))

        else:

            result = await self.db.execute(delete(Address).where(Address.id == address_id))

        await self.db.commit()

        return result.rowcount > 0



    # -----------------------------------------------------------

    # CUSTOM LOGIC

    # -----------------------------------------------------------



    async def get_default_shipping(self, user_id: UUID) -> Optional[Address]:

        """Get a user's default shipping address."""

        # First, try to find an address marked as default

        query = select(Address).where(

            Address.user_id == user_id,

            Address.is_default == True,

            Address.kind == "Shipping"

        )

        result = await self.db.execute(query)

        address = result.scalars().first()



        if address:

            return address



        # If no default is set, return the most recent shipping address

        query = select(Address).where(

            Address.user_id == user_id,

            Address.kind == "Shipping"

        ).order_by(Address.created_at.desc())

        result = await self.db.execute(query)

        return result.scalars().first()



    async def get_default_billing(self, user_id: UUID) -> Optional[Address]:

        """Get a user's default billing address."""

        query = select(Address).where(

            Address.user_id == user_id,

            Address.kind == "Billing"

        ).order_by(Address.created_at.desc())

        result = await self.db.execute(query)

        return result.scalars().first()
    
    

    
class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.password_manager = PasswordManager()
        
        # Search configuration
        self.similarity_threshold = 0.3
        self.weights = {
            "exact": 1.0,
            "prefix": 0.8,
            "fuzzy": 0.5
        }

    async def create_user(self, user_data: UserCreate, background_tasks: BackgroundTasks) -> User:
        hashed_password = self.password_manager.hash_password(
            user_data.password)
        verification_token = secrets.token_urlsafe(32)
        token_expiration = datetime.now(timezone.utc) + timedelta(hours=24)  # Token valid for 24 hours

        new_user = User(
            id=uuid7(),
            email=user_data.email,
            firstname=user_data.firstname,
            lastname=user_data.lastname,
            hashed_password=hashed_password,
            role=user_data.role,
            verified=False,
            verification_token=verification_token,
            token_expiration=token_expiration
        )
        self.db.add(new_user)
        await self.db.commit()
        await self.db.refresh(new_user)

        # Send verification email in background
        background_tasks.add_task(
            self.send_verification_email, 
            new_user.email, 
            new_user.firstname, 
            verification_token
        ) # User registration event handled by hybrid task system

        return new_user

    async def send_verification_email(self, email: str, firstname: str, token: str):
        """Sends a verification email using the send_email service."""
        if not settings.MAILJET_API_KEY or not settings.MAILJET_API_SECRET:
            print("Mailjet API key or secret not configured. Skipping email sending.")
            return

        verification_link = f"{settings.FRONTEND_URL}/verify-email?token={token}"

        context = {
            "customer_name": firstname,
            "verification_link": verification_link,
            "company_name": "Banwee",
            "expiry_time": "24 hours",
            "current_year": datetime.now(timezone.utc).year,
        }

        try:
            from core.utils.messages.email import send_email_mailjet_legacy
            await send_email_mailjet_legacy(
                to_email=email,
                mail_type='activation',
                context=context
            )
            print(f"Verification email sent to {email} successfully.")
        except Exception as e:
            print(
                f"Failed to send verification email to {email}. Error: {e}")

    async def send_welcome_email(self, user: User):
        """Sends a welcome email after email verification."""
        if not settings.MAILJET_API_KEY or not settings.MAILJET_API_SECRET:
            print("Mailjet API key or secret not configured. Skipping email sending.")
            return

        context = {
            "customer_name": user.firstname,
            "user_name": f"{user.firstname} {user.lastname}",
            "email": user.email,
            "store_url": settings.FRONTEND_URL,
            "company_name": "Banwee",
            "support_email": "support@banwee.com",
            "current_year": datetime.now(timezone.utc).year,
        }

        try:
            from core.utils.messages.email import send_email_mailjet_legacy
            await send_email_mailjet_legacy(
                to_email=user.email,
                mail_type='welcome',
                context=context
            )
            print(f"Welcome email sent to {user.email} successfully.")
        except Exception as e:
            print(
                f"Failed to send welcome email to {user.email}. Error: {e}")

    async def verify_email(self, token: str, background_tasks: BackgroundTasks):
        """Verify user email with token and send welcome email."""
        print(f"🔧 DEBUG: UserService.verify_email called with token: '{token}'")
        print(f"🔧 DEBUG: Token length: {len(token)}")
        
        result = await self.db.execute(
            select(User).where(User.verification_token == token)
        )
        user = result.scalar_one_or_none()

        print(f"🔧 DEBUG: Database query result: {user}")
        print(f"🔧 DEBUG: User found: {user is not None}")

        if not user:
            # Let's also check if there are any users with verification tokens at all
            all_users_result = await self.db.execute(
                select(User).where(User.verification_token.isnot(None))
            )
            all_users = all_users_result.scalars().all()
            print(f"🔧 DEBUG: Total users with verification tokens: {len(all_users)}")
            for u in all_users[:3]:  # Show first 3 for debugging
                print(f"🔧 DEBUG: User {u.email} has token: {u.verification_token[:20]}... (expires: {u.token_expiration})")
            
            logger.warning(f"Email verification failed: No user found with token {token[:20]}...")
            raise APIException(
                status_code=400,
                message="Invalid or expired verification token",
            )

        if user.token_expiration < datetime.now(timezone.utc):
            logger.warning(f"Email verification failed: Token expired for user {user.email}. Token expired: {user.token_expiration}")
            raise APIException(
                status_code=400,
                message="Invalid or expired verification token",
            )

        user.verified = True
        user.verification_token = None
        user.token_expiration = None
        await self.db.commit()

        # Send welcome email in the background
        background_tasks.add_task(self.send_welcome_email, user)

        # User verification event handled by hybrid task system

    async def get_users(self, page: int = 1, limit: int = 10, role: Optional[str] = None) -> dict:
        """Get paginated list of users with order count"""
        offset = (page - 1) * limit

        # Build base query with order count using SQL aggregation
        query = (
            select(
                User,
                func.count(Order.id).label('order_count')
            )
            .outerjoin(Order, User.id == Order.user_id)
            .group_by(User.id)
        )

        # Apply role filter if provided
        if role:
            query = query.where(User.role == role)

        # Get total count
        count_query = select(func.count()).select_from(User)
        if role:
            count_query = count_query.where(User.role == role)
        count_result = await self.db.execute(count_query)
        total = count_result.scalar()

        # Apply pagination and ordering
        query = query.offset(offset).limit(limit).order_by(User.created_at.desc())
        result = await self.db.execute(query)
        rows = result.all()

        # Convert to list of dicts with user and order_count
        users_with_counts = []
        for row in rows:
            user = row[0]
            order_count = row[1]
            # Add order_count as an attribute to the user object
            user.order_count = order_count
            users_with_counts.append(user)

        return {
            "users": users_with_counts,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "pages": (total + limit - 1) // limit
            }
        }

    async def get_user(self, user_id: UUID) -> Optional[User]:
        """Get user by ID"""
        query = select(User).where(User.id == user_id).options(
            selectinload(User.addresses)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def update_user(self, user_id: UUID, user_data: UserUpdate) -> Optional[User]:
        """Update user"""
        query = select(User).where(User.id == user_id)
        result = await self.db.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            return None

        # Update fields
        for field, value in user_data.model_dump(exclude_unset=True).items():
            if hasattr(user, field):
                setattr(user, field, value)

        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def delete_user(self, user_id: UUID) -> bool:
        """Delete user"""
        query = select(User).where(User.id == user_id)
        result = await self.db.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            return False

        await self.db.delete(user)
        await self.db.commit()
        return True

    async def search_users(
        self, 
        query: str, 
        limit: int = 20,
        role_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Advanced search for users with prefix matching on name and email.
        """
        if not query or len(query.strip()) < 2:
            return []
            
        query = query.strip().lower()
        
        # Build base conditions
        base_conditions = ["u.is_active = true"]
        params = {
            "query": query,
            "similarity_threshold": self.similarity_threshold,
            "limit": limit,
            "exact_weight": self.weights["exact"],
            "prefix_weight": self.weights["prefix"],
            "fuzzy_weight": self.weights["fuzzy"]
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
                    CASE WHEN LOWER(u.firstname) = :query THEN :exact_weight
                         WHEN LOWER(u.firstname) LIKE CONCAT(:query, '%') THEN :prefix_weight
                         WHEN LOWER(u.firstname) LIKE CONCAT('%', :query, '%') THEN :prefix_weight * 0.7
                         ELSE similarity(LOWER(u.firstname), :query) * :fuzzy_weight
                    END +
                    -- Last name matching
                    CASE WHEN LOWER(u.lastname) = :query THEN :exact_weight
                         WHEN LOWER(u.lastname) LIKE CONCAT(:query, '%') THEN :prefix_weight
                         WHEN LOWER(u.lastname) LIKE CONCAT('%', :query, '%') THEN :prefix_weight * 0.7
                         ELSE similarity(LOWER(u.lastname), :query) * :fuzzy_weight
                    END +
                    -- Email matching (lower weight)
                    CASE WHEN LOWER(u.email) LIKE CONCAT(:query, '%') THEN :prefix_weight * 0.8
                         WHEN LOWER(u.email) LIKE CONCAT('%', :query, '%') THEN :prefix_weight * 0.6
                         ELSE similarity(LOWER(u.email), :query) * :fuzzy_weight * 0.8
                    END +
                    -- Full name matching (concatenated)
                    CASE WHEN LOWER(CONCAT(u.firstname, ' ', u.lastname)) LIKE CONCAT('%', :query, '%') THEN :prefix_weight * 0.9
                         ELSE similarity(LOWER(CONCAT(u.firstname, ' ', u.lastname)), :query) * :fuzzy_weight * 0.9
                    END
                ) as relevance_score
            FROM users u
            WHERE {where_clause}
            AND (
                LOWER(u.firstname) LIKE CONCAT('%', :query, '%')
                OR LOWER(u.lastname) LIKE CONCAT('%', :query, '%')
                OR LOWER(u.email) LIKE CONCAT('%', :query, '%')
                OR LOWER(CONCAT(u.firstname, ' ', u.lastname)) LIKE CONCAT('%', :query, '%')
                OR similarity(LOWER(u.firstname), :query) > :similarity_threshold
                OR similarity(LOWER(u.lastname), :query) > :similarity_threshold
                OR similarity(LOWER(u.email), :query) > :similarity_threshold
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

    

    


