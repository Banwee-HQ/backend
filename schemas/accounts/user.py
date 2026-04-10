

from pydantic import BaseModel, EmailStr, ConfigDict, Field, model_validator
from typing import Optional
from datetime import datetime
from uuid import UUID
from enum import Enum

from models.accounts.user import UserRole, AccountStatus, VerificationStatus, AddressKind

class AddressBase(BaseModel):
    label: Optional[str] = None
    recipient_name: Optional[str] = None
    phone: Optional[str] = None
    street: Optional[str] = None
    street_address: Optional[str] = None
    apartment: Optional[str] = None
    city: str
    state: str
    country: str
    post_code: Optional[str] = None
    postal_code: Optional[str] = None
    is_default: Optional[bool] = False
    kind: AddressKind = AddressKind.SHIPPING

    @model_validator(mode="after")
    def normalize_fields(self):
        # Allow street_address as alias for street
        if not self.street and self.street_address:
            self.street = self.street_address
        if not self.street:
            self.street = ""
        # Allow postal_code as alias for post_code
        if not self.post_code and self.postal_code:
            self.post_code = self.postal_code
        if not self.post_code:
            self.post_code = ""
        return self


class AddressCreate(AddressBase):
    pass


class AddressUpdate(AddressBase):
    street: Optional[str] = None
    street_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    post_code: Optional[str] = None
    postal_code: Optional[str] = None
    kind: Optional[str] = None


class AddressResponse(AddressBase):
    id: UUID
    user_id: UUID
    is_default: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class Base(BaseModel):
    email: EmailStr
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: UserRole = UserRole.CUSTOMER

    @model_validator(mode="after")
    def normalize_names(self):
        if not self.firstname and self.first_name:
            self.firstname = self.first_name
        if not self.lastname and self.last_name:
            self.lastname = self.last_name
        if not self.firstname:
            self.firstname = ""
        if not self.lastname:
            self.lastname = ""
        return self


class Create(Base):
    password: str
    phone: Optional[str] = None


class Update(BaseModel):
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    country: Optional[str] = None
    language: Optional[str] = None
    timezone: Optional[str] = None
    is_active: Optional[bool] = None


class Response(BaseModel):
    id: UUID
    email: EmailStr
    firstname: str
    lastname: str
    full_name: Optional[str] = None
    phone: Optional[str] = None
    role: UserRole
    account_status: AccountStatus
    verification_status: VerificationStatus
    verified: bool
    is_active: bool
    age: Optional[int] = None
    gender: Optional[str] = None
    country: Optional[str] = None
    language: Optional[str] = None
    timezone: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={
            datetime: lambda v: v.isoformat() if v else None
        }
    )
