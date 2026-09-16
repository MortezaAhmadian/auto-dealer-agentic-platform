"""
Creates the schema (idempotent) and, if the database is empty, seeds a
handful of demo listings so the app and RAG search have something to show
on first run.

Not a substitute for real migrations in a production system — see the
README "What I'd improve" section for the Alembic note.
"""
import sys
from pathlib import Path

# Repo root (contains both shared/ and backend/) must be importable, since
# this script runs with cwd=/app inside the container (see backend/Dockerfile).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from shared.database import engine, SessionLocal, Base
from shared import models
from shared.embeddings import embed

SEED_LISTINGS = [
    dict(make="Toyota", model="RAV4", year=2021, mileage=28000, price=24500,
         condition="excellent",
         description="One owner, all service records, great for families, AWD."),
    dict(make="Honda", model="Civic", year=2019, mileage=41000, price=17800,
         condition="good",
         description="Reliable commuter car, excellent fuel economy, minor door ding."),
    dict(make="Ford", model="F-150", year=2018, mileage=65000, price=27900,
         condition="good",
         description="Work truck, tow package, some bed wear, runs strong."),
    dict(make="Tesla", model="Model 3", year=2022, mileage=15000, price=32900,
         condition="excellent",
         description="Long range battery, autopilot, still under warranty."),
    dict(make="Subaru", model="Outback", year=2020, mileage=33000, price=23400,
         condition="excellent",
         description="AWD wagon, great in snow, family owned, no accidents."),
    dict(make="Chevrolet", model="Malibu", year=2017, mileage=72000, price=11900,
         condition="fair",
         description="Budget commuter, needs new brakes soon, otherwise reliable."),
    dict(make="BMW", model="3 Series", year=2020, mileage=25000, price=28900,
         condition="excellent",
         description="Sport package, leather interior, low mileage luxury sedan."),
    dict(make="Jeep", model="Wrangler", year=2019, mileage=38000, price=26500,
         condition="good",
         description="Off-road capable, removable top, some trail scratches."),
    dict(make="Honda", model="CR-V", year=2021, mileage=19000, price=25900,
         condition="excellent",
         description="Small SUV, spacious trunk, great for a young family, like new."),
    dict(make="Nissan", model="Altima", year=2016, mileage=88000, price=9800,
         condition="fair",
         description="High mileage but well maintained, cheap and dependable."),
]

DEMO_SELLER = dict(name="Demo Seller", email="demo-seller@automarket.test")


def main():
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()

    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        if db.query(models.CarListing).count() > 0:
            print("Listings already exist — skipping seed.")
            return

        seller = models.User(**DEMO_SELLER)
        db.add(seller)
        db.flush()

        for row in SEED_LISTINGS:
            listing = models.CarListing(
                seller_id=seller.id,
                condition=models.ListingCondition(row.pop("condition")),
                **row,
            )
            listing.embedding = embed(listing.embedding_text())
            db.add(listing)

        db.commit()
        print(f"Seeded {len(SEED_LISTINGS)} listings.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
