from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, EmailStr

from shared.models import ListingStatus, ListingCondition, TransactionStatus


class UserCreate(BaseModel):
    name: str
    email: EmailStr


class UserOut(BaseModel):
    id: str
    name: str
    email: str

    class Config:
        from_attributes = True


class ListingCreate(BaseModel):
    seller_id: str
    make: str
    model: str
    year: int
    mileage: int
    price: Decimal
    condition: ListingCondition
    description: str = ""


class ListingOut(BaseModel):
    id: str
    seller_id: str
    make: str
    model: str
    year: int
    mileage: int
    price: Decimal
    condition: ListingCondition
    description: str
    status: ListingStatus
    created_at: datetime

    class Config:
        from_attributes = True


class TransactionCreate(BaseModel):
    listing_id: str
    buyer_id: str
    sale_price: Decimal


class TransactionOut(BaseModel):
    id: str
    listing_id: str
    buyer_id: str
    sale_price: Decimal
    status: TransactionStatus
    created_at: datetime

    class Config:
        from_attributes = True
