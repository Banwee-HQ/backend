from pydantic import BaseModel, EmailStr, ConfigDict
from typing import Optional
from datetime import datetime
from schemas.accounts.user import Base as UserBase, Response as UserResponse
from uuid import UUID


class UserCreate(UserBase):
    password: str
    phone: Optional[str] = None
    # Set when signup was triggered by an anonymous add-to-cart attempt, so the
    # item can be added to the new user's cart right after registration.
    variant_id: Optional[UUID] = None
    quantity: int = 1


class Login(BaseModel):
    email: EmailStr
    password: str
    # Set when login was triggered by an anonymous add-to-cart attempt, so the
    # item can be added to the user's cart right after authentication.
    variant_id: Optional[UUID] = None
    quantity: int = 1


class Response(BaseModel):
    id: UUID
    email: str
    firstname: str
    lastname: str
    phone: Optional[str] = None
    role: str
    account_status: Optional[str] = None
    verification_status: Optional[str] = None
    verified: bool = False
    is_active: bool = True
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    user: "UserResponse"


class Refresh(BaseModel):
    refresh_token: str


class Auth(BaseModel):
    access_token: str
    token_type: str
    refresh_token: Optional[str] = None
    expires_in: int
    user: "UserResponse"


class ResendVerification(BaseModel):
    email: EmailStr


class ForgotPassword(BaseModel):
    email: EmailStr


class ResetPassword(BaseModel):
    token: str
    new_password: str


class ChangePassword(BaseModel):
    current_password: str
    new_password: str
