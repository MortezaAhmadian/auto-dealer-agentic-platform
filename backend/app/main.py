from decimal import Decimal

from fastapi import FastAPI, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.database import get_db
from shared import models
from shared.embeddings import embed

app = FastAPI(title="AutoMarket — Agentic Car Dealer Platform")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.get("/health")
def health():
    """Polled by ops-mcp's check_service_health tool."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Web UI (server-rendered — deliberately simple so the agentic layer, not
# frontend plumbing, stays the centerpiece of this project)
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    listings = (
        db.query(models.CarListing)
        .filter(models.CarListing.status == models.ListingStatus.available)
        .order_by(models.CarListing.created_at.desc())
        .limit(24)
        .all()
    )
    return templates.TemplateResponse(
        "index.html", {"request": request, "listings": listings}
    )


@app.get("/listings/{listing_id}", response_class=HTMLResponse)
def listing_detail(listing_id: str, request: Request, db: Session = Depends(get_db)):
    listing = db.get(models.CarListing, listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    return templates.TemplateResponse(
        "listing_detail.html", {"request": request, "listing": listing}
    )


@app.get("/sell", response_class=HTMLResponse)
def sell_form(request: Request):
    return templates.TemplateResponse("sell.html", {"request": request})


@app.post("/sell")
def sell_submit(
    request: Request,
    db: Session = Depends(get_db),
    seller_name: str = Form(...),
    seller_email: str = Form(...),
    make: str = Form(...),
    model: str = Form(...),
    year: int = Form(...),
    mileage: int = Form(...),
    price: Decimal = Form(...),
    condition: str = Form(...),
    description: str = Form(""),
):
    """
    Direct listing creation from the web form.

    Note: the *agentic* version of this flow is the listing_intake_agent
    (see /agents), which additionally moderates free-text descriptions,
    extracts structured attributes from messy input, and calls the pricing
    agent for a suggested price before the listing goes live. This endpoint
    is the plain CRUD path used by the web app itself and by seed data.
    """
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
        price=price,
        condition=models.ListingCondition(condition),
        description=description,
    )
    listing.embedding = embed(listing.embedding_text())
    db.add(listing)
    db.commit()
    db.refresh(listing)

    return RedirectResponse(url=f"/listings/{listing.id}", status_code=303)


@app.get("/search", response_class=HTMLResponse)
def search(request: Request, q: str = "", db: Session = Depends(get_db)):
    """
    Semantic (RAG) search over listings, e.g. "reliable family SUV under
    30k miles" — matches on meaning, not just keyword overlap. This is the
    same retrieval step the buyer_assistant_agent's MCP tool performs; this
    endpoint exposes it directly to the plain web UI too.
    """
    results = []
    if q.strip():
        query_vector = embed(q)
        results = (
            db.query(models.CarListing)
            .filter(models.CarListing.status == models.ListingStatus.available)
            .order_by(models.CarListing.embedding.cosine_distance(query_vector))
            .limit(12)
            .all()
        )
    return templates.TemplateResponse(
        "search_results.html", {"request": request, "query": q, "listings": results}
    )


# ---------------------------------------------------------------------------
# JSON API (used by tests / external clients; the MCP server talks to
# Postgres directly rather than through this API, see mcp-servers/postgres_mcp)
# ---------------------------------------------------------------------------

@app.get("/api/listings")
def api_list_listings(db: Session = Depends(get_db)):
    listings = db.query(models.CarListing).all()
    return [
        {
            "id": l.id,
            "make": l.make,
            "model": l.model,
            "year": l.year,
            "price": float(l.price),
            "status": l.status.value,
        }
        for l in listings
    ]
