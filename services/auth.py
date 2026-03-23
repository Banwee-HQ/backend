from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from fastapi import HTTPException, Depends, status, BackgroundTasks

from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import secrets
from core.logging import get_structured_logger
from core.utils.uuid_utils import uuid7
from core.config import settings
from models.user import User
from schemas.auth import UserCreate, Token, UserResponse, AuthResponse
from services.user import UserService
from core.db import get_db
from core.utils.messages.email import send_email
from core.utils.encryption import PasswordManager

logger = get_structured_logger(__name__)


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.password_manager = PasswordManager()

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        return self.password_manager.verify_password(plain_password, hashed_password)

    def get_password_hash(self, password: str) -> str:
        """Hash a password."""
        return self.password_manager.hash_password(password)

    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """Create a JWT access token."""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode.update({
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "access",
            "jti": str(uuid7())  # JWT ID for token tracking
        })
        
        encoded_jwt = jwt.encode(
            to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        return encoded_jwt

    async def create_refresh_token(self, data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """Create a JWT refresh token."""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        
        to_encode.update({
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "refresh",
            "jti": str(uuid7())  # JWT ID for token tracking
        })
        
        encoded_jwt = jwt.encode(
            to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        
        return encoded_jwt



    def verify_token(self, token: str, token_type: str = "access") -> Dict[str, Any]:
        """Verify and decode JWT token."""
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            
            # Check token type
            if payload.get("type") != token_type:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Invalid token type. Expected {token_type}",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            
            # Check expiration
            exp = payload.get("exp")
            if exp is None or datetime.utcnow() > datetime.fromtimestamp(exp):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has expired",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            
            return payload
            
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

    async def refresh_access_token(self, refresh_token: str) -> Dict[str, str]:
        """Generate new access token using refresh token."""
        try:
            # Verify refresh token
            payload = self.verify_token(refresh_token, "refresh")
            jti = payload.get("jti")
            user_id_from_token = payload.get("sub")

            if not jti or not user_id_from_token:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid refresh token payload"
                )
            
            # Get user from token
            user = await self.get_user_by_id(user_id_from_token)
            if not user or not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found or inactive"
                )
            
            # Create new access token data
            access_token_data = {
                "sub": str(user.id),
                "email": user.email,
                "is_active": user.is_active,
                "role": getattr(user, 'role', 'user')
            }
            
            new_access_token = self.create_access_token(access_token_data)
            
            return {
                "access_token": new_access_token,
                "token_type": "bearer"
            }
            
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not refresh token"
            )

    async def revoke_refresh_token(self, refresh_token: str) -> bool:
        """Revoke a refresh token (add to blacklist)."""
        # With stateless JWTs, we can't truly revoke a token.
        # This method can be used to clear the token on the client side.
        return True

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get user by ID."""
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email."""
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def _send_verification_email(self, email: str, verification_code: str):
        """Placeholder for sending a verification email."""
        print(f"Sending verification email to {email} with code {verification_code}")
        # In a real application, integrate with an email service here

    async def _send_welcome_sms(self, phone_number: str):
        """Placeholder for sending a welcome SMS."""
        print(f"Sending welcome SMS to {phone_number}")
        # In a real application, integrate with an SMS service here

    async def create_user(self, user_data: UserCreate, background_tasks: BackgroundTasks) -> UserResponse:
        """Create a new user."""
        # Check if user already exists
        existing_user = await self.get_user_by_email(user_data.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        user_service = UserService(self.db)
        print(user_data, '---')
        new_user = await user_service.create_user(user_data, background_tasks)



        return UserResponse.from_orm(new_user)

    async def authenticate_user(self, email: str, password: str, background_tasks: BackgroundTasks) -> AuthResponse:
        """Authenticate user and return JWT tokens."""
        print(f"Attempting to authenticate user: {email}")
        user = await self.get_user_by_email(email)
        if not user:
            print(f"User {email} not found.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        password_verified = self.verify_password(password, user.hashed_password)
        print(f"Password verification for {email}: {password_verified}")

        if not password_verified:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check if user is active
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account is deactivated",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Update last_login timestamp
        user.last_login = func.now()
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)

        print(f"Password verified for {email}. Proceeding to token creation.")

        # Send login alert email
        context = {
            "customer_name": user.firstname,
            "login_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "company_name": "Banwee",
            "security_page_url": f"{settings.FRONTEND_URL}/account/security",
        }
        try:
            background_tasks.add_task(
                send_email,
                to_email=user.email,
                mail_type='login_alert',
                context=context
            )
            print(f"Login alert email task added for {user.email}.")
        except Exception as e:
            print(f"Failed to add login alert email task for {user.email}. Error: {e}")

        # Create token data
        token_data = {
            "sub": str(user.id),
            "email": user.email,
            "role": user.role,
            "is_active": user.is_active
        }

        # Create access and refresh tokens
        access_token = self.create_access_token(token_data)
        refresh_token = await self.create_refresh_token(token_data)
        
        print(f"Generated tokens for user {user.email}")

        auth_response = AuthResponse(
            access_token=access_token,
            token_type="bearer",
            refresh_token=refresh_token,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserResponse(
                id=user.id,
                email=user.email,
                firstname=user.firstname,
                lastname=user.lastname,
                phone=user.phone,
                role=user.role,
                verified=user.verified,
                is_active=user.is_active,
                created_at=user.created_at
            )
        )
        
        return auth_response

    async def get_current_user(
        self,
        token: str
    ) -> User:
        """Get current authenticated user using enhanced JWT verification."""
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

        try:
            # Decode and verify token
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            
            # Check token type
            token_type = payload.get("type")
            if token_type != "access":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token type",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            

            # Get user ID from token
            user_id: str = payload.get("sub")
            if user_id is None:
                raise credentials_exception
                
            # Check token expiration
            exp = payload.get("exp")
            if exp is None or datetime.utcnow() > datetime.fromtimestamp(exp):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has expired",
                    headers={"WWW-Authenticate": "Bearer"},
                )
                
        except JWTError:
            raise credentials_exception

        # Get user from database
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if user is None:
            raise credentials_exception
            
        # Check if user is still active
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is deactivated",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        return user



    async def send_password_reset(self, email: str, background_tasks: BackgroundTasks):
        """Send password reset email"""
        user = await self.get_user_by_email(email)
        if not user:
            # Return silently for security (don't reveal if email exists)
            logger.info(f"Password reset requested for non-existent email: {email}")
            return
        
        # Generate reset token (32 bytes = 43 characters in base64)
        reset_token = secrets.token_urlsafe(32)
        reset_link = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
        
        # Store token in user record with expiration (1 hour)
        user.reset_token = reset_token
        user.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
        await self.db.commit()
        
        logger.info(f"Password reset token generated for {email}")
        
        # Send password reset email
        context = {
            "customer_name": user.firstname,
            "reset_link": reset_link,
            "expiry_time": "1 hour",
            "company_name": "Banwee",
            "current_year": datetime.now().year,
        }
        
        try:
            from core.utils.messages.email import send_email_mailjet_legacy
            background_tasks.add_task(
                send_email_mailjet_legacy,
                to_email=user.email,
                mail_type='password_reset',
                context=context
            )
            logger.info(f"Password reset email queued for {user.email}")
        except Exception as e:
            logger.error(f"Failed to queue password reset email for {user.email}. Error: {e}")

    async def reset_password(self, token: str, new_password: str):
        """Reset password using reset token"""
        # Find user by reset token
        result = await self.db.execute(
            select(User).where(User.reset_token == token)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            logger.warning(f"Password reset attempted with invalid token")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired reset token"
            )
        
        # Check token expiration
        if not user.reset_token_expires or user.reset_token_expires < datetime.utcnow():
            logger.warning(f"Password reset attempted with expired token for user {user.email}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reset token has expired. Please request a new password reset link."
            )
        
        # Update password and clear reset token
        user.hashed_password = self.get_password_hash(new_password)
        user.reset_token = None
        user.reset_token_expires = None
        await self.db.commit()
        
        logger.info(f"Password reset successfully for user {user.email}")
