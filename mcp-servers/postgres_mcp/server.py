"""
MCP server exposing the car dealer's Postgres data as tools for agents.

This is the "hands" of the business-logic agents (buyer assistant, listing
intake, pricing): they never touch SQL directly, they call these tools.
Runs over streamable-http so it's reachable from the agents container.
"""
import os
import sys
from pathlib import Path
from decimal import Decimal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from mcp.server.fastmcp import FastMCP
from sqlalchemy import func

from shared.database import SessionLocal
from shared import models
from shared.embeddings import embed

mcp = FastMCP("postgres-dealer-tools", host="0.0.0.0", port=8001)


def _listing_to_dict(listing: models.CarListing) -> dict:
    return {
        "id": listing.id,
        "seller_id": listing.seller_id,
        "make": listing.make,
        "model": listing.model,
        "year": listing.year,
        "mileage": listing.mileage,
        "price": float(listing.price),
        "condition": listing.condition.value,
        "description": listing.description,
        "status": listing.status.value,
    }


@mcp.tool()
def search_listings_semantic(query: str, top_k: int = 5) -> list[dict]:
    """
    Search available car listings by natural-language meaning (RAG), e.g.
    "reliable family SUV under 30k miles" or "cheap first car for a teenager".
    Returns the top_k most semantically similar available listings.
    """
    db = SessionLocal()
    try:
        query_vector = embed(query)
        rows = (
            db.query(models.CarListing)
            .filter(models.CarListing.status == models.ListingStatus.available)
            .order_by(models.CarListing.embedding.cosine_distance(query_vector))
            .limit(top_k)
            .all()
        )
        return [_listing_to_dict(r) for r in rows]
    finally:
        db.close()


@mcp.tool()
def search_listings_filtered(
    make: str | None = None,
    model: str | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    price_max: float | None = None,
    max_mileage: int | None = None,
) -> list[dict]:
    """Search available listings with exact structured filters (all optional)."""
    db = SessionLocal()
    try:
        q = db.query(models.CarListing).filter(
            models.CarListing.status == models.ListingStatus.available
        )
        if make:
            q = q.filter(func.lower(models.CarListing.make) == make.lower())
        if model:
            q = q.filter(func.lower(models.CarListing.model) == model.lower())
        if year_min:
            q = q.filter(models.CarListing.year >= year_min)
        if year_max:
            q = q.filter(models.CarListing.year <= year_max)
        if price_max:
            q = q.filter(models.CarListing.price <= price_max)
        if max_mileage:
            q = q.filter(models.CarListing.mileage <= max_mileage)
        rows = q.order_by(models.CarListing.created_at.desc()).limit(20).all()
        return [_listing_to_dict(r) for r in rows]
    finally:
        db.close()


@mcp.tool()
def get_listing(listing_id: str) -> dict:
    """Fetch a single listing by id."""
    db = SessionLocal()
    try:
        listing = db.get(models.CarListing, listing_id)
        if not listing:
            return {"error": f"No listing with id {listing_id}"}
        return _listing_to_dict(listing)
    finally:
        db.close()


@mcp.tool()
def get_comparable_listings(make: str, model: str, year: int, year_tolerance: int = 2) -> list[dict]:
    """
    Fetch comparable listings (same make/model, similar year, any status) for
    the pricing agent to estimate a fair market price from.
    """
    db = SessionLocal()
    try:
        rows = (
            db.query(models.CarListing)
            .filter(
                func.lower(models.CarListing.make) == make.lower(),
                func.lower(models.CarListing.model) == model.lower(),
                models.CarListing.year >= year - year_tolerance,
                models.CarListing.year <= year + year_tolerance,
            )
            .all()
        )
        return [_listing_to_dict(r) for r in rows]
    finally:
        db.close()


@mcp.tool()
def create_listing(
    seller_email: str,
    seller_name: str,
    make: str,
    model: str,
    year: int,
    mileage: int,
    price: float,
    condition: str,
    description: str = "",
) -> dict:
    """
    Create a new car listing, creating the seller user if they don't exist
    yet. Used by the listing_intake_agent after it has validated and
    enriched the seller's raw input. `condition` must be one of: new,
    excellent, good, fair, needs_work.
    """
    db = SessionLocal()
    try:
        seller = db.query(models.User).filter(models.User.email == seller_email).first()
        if not seller:
            seller = models.User(name=seller_name, email=seller_email)
            db.add(seller)
            db.flush()

        listing = models.CarListing(
            seller_id=seller.id,
            make=make,
            model=model,
            year=year,
            mileage=mileage,
            price=Decimal(str(price)),
            condition=models.ListingCondition(condition),
            description=description,
        )
        listing.embedding = embed(listing.embedding_text())
        db.add(listing)
        db.commit()
        db.refresh(listing)
        return _listing_to_dict(listing)
    finally:
        db.close()


@mcp.tool()
def update_listing_status(listing_id: str, status: str) -> dict:
    """Update a listing's status. Must be one of: available, pending, sold, removed."""
    db = SessionLocal()
    try:
        listing = db.get(models.CarListing, listing_id)
        if not listing:
            return {"error": f"No listing with id {listing_id}"}
        listing.status = models.ListingStatus(status)
        db.commit()
        db.refresh(listing)
        return _listing_to_dict(listing)
    finally:
        db.close()


@mcp.tool()
def get_user_listings(email: str) -> list[dict]:
    """List all listings posted by a given user's email."""
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        if not user:
            return []
        return [_listing_to_dict(l) for l in user.listings]
    finally:
        db.close()


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
