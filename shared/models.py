import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Column,
    String,
    Integer,
    Numeric,
    Text,
    DateTime,
    ForeignKey,
    Enum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from shared.database import Base

# Dimension of the sentence-transformers/all-MiniLM-L6-v2 embedding model.
# Chosen so the whole RAG pipeline runs locally with no embedding API key.
EMBEDDING_DIM = 384


class ListingStatus(str, enum.Enum):
    available = "available"
    pending = "pending"
    sold = "sold"
    removed = "removed"


class ListingCondition(str, enum.Enum):
    new = "new"
    excellent = "excellent"
    good = "good"
    fair = "fair"
    needs_work = "needs_work"


class TransactionStatus(str, enum.Enum):
    pending = "pending"
    completed = "completed"
    cancelled = "cancelled"


def gen_uuid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    listings = relationship("CarListing", back_populates="seller")
    purchases = relationship("Transaction", back_populates="buyer")


class CarListing(Base):
    __tablename__ = "car_listings"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    seller_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)

    make = Column(String, nullable=False, index=True)
    model = Column(String, nullable=False, index=True)
    year = Column(Integer, nullable=False, index=True)
    mileage = Column(Integer, nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    condition = Column(Enum(ListingCondition), nullable=False)
    description = Column(Text, nullable=False, default="")

    status = Column(Enum(ListingStatus), nullable=False, default=ListingStatus.available)

    # RAG: semantic embedding of "make model year condition description",
    # regenerated whenever the listing text changes. Cosine-searched by the
    # buyer assistant agent and the /search endpoint.
    embedding = Column(Vector(EMBEDDING_DIM), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    seller = relationship("User", back_populates="listings")
    transactions = relationship("Transaction", back_populates="listing")

    def embedding_text(self) -> str:
        """The canonical text this listing's embedding is derived from."""
        return (
            f"{self.year} {self.make} {self.model}, {self.condition.value} condition, "
            f"{self.mileage} miles. {self.description}"
        )


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    listing_id = Column(UUID(as_uuid=False), ForeignKey("car_listings.id"), nullable=False)
    buyer_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)

    sale_price = Column(Numeric(10, 2), nullable=False)
    status = Column(Enum(TransactionStatus), nullable=False, default=TransactionStatus.pending)
    created_at = Column(DateTime, default=datetime.utcnow)

    listing = relationship("CarListing", back_populates="transactions")
    buyer = relationship("User", back_populates="purchases")
