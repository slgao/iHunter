import os
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from groq import AsyncGroq, RateLimitError
from dotenv import load_dotenv
from pathlib import Path

from typing import List
from database import init_db, get_db
from agents.market_analyst import analyze_market
from agents.lead_finder import find_b2b_leads, find_b2c_leads
from agents.outreach_agent import generate_outreach
from agents.email_verifier import verify_email
from agents.web_scraper import scrape_website_emails
from agents.hunter import hunter_find_email
from agents.company_suggester import suggest_real_companies

load_dotenv()

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="iHunters Germany", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.exception_handler(RateLimitError)
async def groq_rate_limit_handler(request, exc):
    from fastapi.responses import JSONResponse
    import re
    wait = re.search(r'try again in (.+?)\.', str(exc))
    wait_msg = f" Try again in {wait.group(1)}." if wait else ""
    return JSONResponse(
        status_code=429,
        content={"detail": f"Groq daily token limit reached.{wait_msg}"},
    )


def get_model() -> AsyncGroq:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY not set in .env")
    return AsyncGroq(api_key=api_key)


# --- Models ---
class ProductCreate(BaseModel):
    name: str
    category: str
    description: str
    price_range: str
    moq: str
    origin_city: str = "Shenzhen"


class LeadStatusUpdate(BaseModel):
    status: str
    notes: Optional[str] = None


class RealCompanyImport(BaseModel):
    company_name: str
    website: Optional[str] = None
    city: Optional[str] = None
    industry: Optional[str] = None
    contact_name: Optional[str] = None
    description: Optional[str] = None
    size: Optional[str] = None
    product_id: int


class BulkImport(BaseModel):
    # Each line: "Company Name | website.de | City | Industry"
    raw_text: str
    product_id: int


# --- Routes ---
@app.get("/")
async def root():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.post("/api/products")
async def create_product(product: ProductCreate):
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO products (name, category, description, price_range, moq, origin_city) VALUES (?,?,?,?,?,?)",
        (product.name, product.category, product.description, product.price_range, product.moq, product.origin_city),
    )
    await db.commit()
    product_id = cursor.lastrowid
    await db.close()
    return {"id": product_id, **product.model_dump()}


@app.delete("/api/products/{product_id}")
async def delete_product(product_id: int):
    db = await get_db()
    await db.execute("DELETE FROM leads WHERE product_id=?", (product_id,))
    await db.execute("DELETE FROM products WHERE id=?", (product_id,))
    await db.commit()
    await db.close()
    return {"ok": True}


@app.get("/api/products")
async def list_products():
    db = await get_db()
    cursor = await db.execute("SELECT * FROM products ORDER BY created_at DESC")
    rows = await cursor.fetchall()
    await db.close()
    return [dict(r) for r in rows]


@app.post("/api/products/{product_id}/analyze")
async def analyze_product(product_id: int):
    db = await get_db()
    cursor = await db.execute("SELECT * FROM products WHERE id=?", (product_id,))
    row = await cursor.fetchone()
    await db.close()
    if not row:
        raise HTTPException(404, "Product not found")
    p = dict(row)
    model = get_model()
    analysis = await analyze_market(model, p["name"], p["category"], p["description"])
    db2 = await get_db()
    await db2.execute("UPDATE products SET analysis=? WHERE id=?", (json.dumps(analysis), product_id))
    await db2.commit()
    await db2.close()
    return analysis


@app.post("/api/products/{product_id}/generate-leads")
async def generate_leads(
    product_id: int,
    b2b_count: int = 8,
    b2c_count: int = 6,
    cities: Optional[str] = None,  # comma-separated e.g. "Berlin,Munich,Hamburg"
):
    db = await get_db()
    cursor = await db.execute("SELECT * FROM products WHERE id=?", (product_id,))
    row = await cursor.fetchone()
    if not row:
        await db.close()
        raise HTTPException(404, "Product not found")
    p = dict(row)
    model = get_model()

    # First get market analysis for targeted lead gen
    analysis = await analyze_market(model, p["name"], p["category"], p["description"])
    sectors = analysis.get("target_sectors", ["Retail", "E-commerce", "Wholesale"])
    # Use user-specified cities if provided, else fall back to AI-suggested cities
    target_cities = [c.strip() for c in cities.split(",") if c.strip()] if cities else analysis.get("top_german_cities", ["Berlin", "Munich", "Hamburg"])

    b2b_count = max(1, min(b2b_count, 30))
    b2c_count = max(1, min(b2c_count, 30))
    b2b_leads = await find_b2b_leads(model, p["name"], p["category"], p["description"], sectors, target_cities, b2b_count)
    b2c_leads = await find_b2c_leads(model, p["name"], p["category"], p["description"], b2c_count, target_cities)

    # Fetch existing emails for this product to deduplicate
    cur = await db.execute("SELECT email FROM leads WHERE product_id=?", (product_id,))
    existing_emails = {row[0] for row in await cur.fetchall() if row[0]}

    all_leads = b2b_leads + b2c_leads
    inserted_ids = []
    skipped = 0
    for lead in all_leads:
        email = lead.get("email", "").strip().lower()
        if email and email in existing_emails:
            skipped += 1
            continue
        if email:
            existing_emails.add(email)
        cur = await db.execute(
            """INSERT INTO leads (type, company_name, contact_name, email, phone, city, industry, description, product_id)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                lead.get("type", "b2b"),
                lead.get("company_name"),
                lead.get("contact_name"),
                lead.get("email"),
                lead.get("phone"),
                lead.get("city"),
                lead.get("industry"),
                lead.get("description"),
                product_id,
            ),
        )
        inserted_ids.append(cur.lastrowid)
    await db.commit()
    await db.close()
    return {"generated": len(inserted_ids), "b2b": len(b2b_leads), "b2c": len(b2c_leads), "skipped_duplicates": skipped, "lead_ids": inserted_ids}


@app.get("/api/leads")
async def list_leads(product_id: Optional[int] = None, lead_type: Optional[str] = None, status: Optional[str] = None):
    db = await get_db()
    query = "SELECT * FROM leads WHERE 1=1"
    params = []
    if product_id:
        query += " AND product_id=?"
        params.append(product_id)
    if lead_type:
        query += " AND type=?"
        params.append(lead_type)
    if status:
        query += " AND status=?"
        params.append(status)
    query += " ORDER BY created_at DESC"
    cursor = await db.execute(query, params)
    rows = await cursor.fetchall()
    await db.close()
    return [dict(r) for r in rows]


@app.post("/api/leads/{lead_id}/verify-email")
async def verify_lead_email(lead_id: int):
    db = await get_db()
    cursor = await db.execute("SELECT id, email FROM leads WHERE id=?", (lead_id,))
    row = await cursor.fetchone()
    if not row:
        await db.close()
        raise HTTPException(404, "Lead not found")
    email = row["email"] or ""
    result = await verify_email(email)
    await db.execute("UPDATE leads SET email_status=? WHERE id=?", (result["status"], lead_id))
    await db.commit()
    await db.close()
    return result


@app.post("/api/products/{product_id}/verify-all-emails")
async def verify_all_emails(product_id: int):
    db = await get_db()
    cursor = await db.execute(
        "SELECT id, email FROM leads WHERE product_id=? AND (email_status IS NULL OR email_status='unverified')",
        (product_id,),
    )
    rows = await cursor.fetchall()
    results = []
    for row in rows:
        result = await verify_email(row["email"] or "")
        await db.execute("UPDATE leads SET email_status=? WHERE id=?", (result["status"], row["id"]))
        results.append({"lead_id": row["id"], "email": row["email"], **result})
    await db.commit()
    await db.close()
    return {"verified": len(results), "results": results}


@app.patch("/api/leads/{lead_id}")
async def update_lead(lead_id: int, update: LeadStatusUpdate):
    db = await get_db()
    await db.execute(
        "UPDATE leads SET status=?, notes=? WHERE id=?",
        (update.status, update.notes, lead_id),
    )
    await db.commit()
    await db.close()
    return {"ok": True}


@app.post("/api/leads/{lead_id}/outreach")
async def create_outreach(lead_id: int):
    db = await get_db()
    cursor = await db.execute(
        "SELECT l.*, p.name as pname, p.description as pdesc, p.price_range, p.moq, p.origin_city "
        "FROM leads l JOIN products p ON l.product_id=p.id WHERE l.id=?",
        (lead_id,),
    )
    row = await cursor.fetchone()
    if not row:
        await db.close()
        raise HTTPException(404, "Lead not found")
    data = dict(row)
    model = get_model()

    lead = {
        "type": data["type"],
        "company_name": data.get("company_name"),
        "contact_name": data.get("contact_name"),
        "city": data.get("city"),
        "industry": data.get("industry"),
        "description": data.get("description"),
    }
    email_content = await generate_outreach(
        model, lead, data["pname"], data["pdesc"], data["price_range"], data["moq"], data["origin_city"]
    )

    cur = await db.execute(
        "INSERT INTO outreaches (lead_id, subject_de, subject_en, body_de, body_en) VALUES (?,?,?,?,?)",
        (lead_id, email_content["subject_de"], email_content["subject_en"], email_content["body_de"], email_content["body_en"]),
    )
    outreach_id = cur.lastrowid
    await db.commit()
    await db.close()
    return {"id": outreach_id, **email_content}


@app.get("/api/leads/{lead_id}/outreaches")
async def get_outreaches(lead_id: int):
    db = await get_db()
    cursor = await db.execute("SELECT * FROM outreaches WHERE lead_id=? ORDER BY created_at DESC", (lead_id,))
    rows = await cursor.fetchall()
    await db.close()
    return [dict(r) for r in rows]


@app.post("/api/products/{product_id}/suggest-companies")
async def suggest_companies(product_id: int, count: int = 15, cities: Optional[str] = None):
    db = await get_db()
    cur = await db.execute("SELECT * FROM products WHERE id=?", (product_id,))
    row = await cur.fetchone()
    if not row:
        await db.close()
        raise HTTPException(404, "Product not found")
    p = dict(row)

    # Collect already-known companies so the AI won't repeat them
    cur = await db.execute(
        "SELECT company_name, website FROM leads WHERE product_id=?", (product_id,)
    )
    existing_rows = await cur.fetchall()
    await db.close()

    exclude = []
    for r in existing_rows:
        if r["company_name"]:
            exclude.append(r["company_name"])
        if r["website"]:
            exclude.append(r["website"])

    model = get_model()
    target_cities = [c.strip() for c in cities.split(",")] if cities else []
    suggestions = await suggest_real_companies(
        model, p["name"], p["category"], p["description"], target_cities, count, exclude=exclude
    )
    return suggestions


async def _find_email(website: str) -> dict:
    """
    Scrape website for email, fall back to Hunter.io.
    Returns: {email, source_page, all_emails_json, scrape_error, hunter_used, resolved_website}
    """
    email = source_page = all_emails_json = scrape_error = None
    hunter_used = False
    resolved_website = website

    result = await scrape_website_emails(website)
    resolved = result.get("resolved_base")
    if resolved:
        resolved_website = resolved.replace("https://", "").replace("http://", "")
    if result["emails"]:
        email = result["emails"][0]["email"]
        source_page = result["emails"][0]["source_page"]
        all_emails_json = json.dumps(result["emails"])
    else:
        scrape_error = result.get("error")
        hunter_key = os.getenv("HUNTER_API_KEY")
        if hunter_key:
            h = await hunter_find_email(website, hunter_key)
            if h["emails"]:
                email = h["emails"][0]["email"]
                hunter_used = True
                scrape_error = None

    return {
        "email": email,
        "source_page": source_page,
        "all_emails_json": all_emails_json,
        "scrape_error": scrape_error,
        "hunter_used": hunter_used,
        "resolved_website": resolved_website,
    }


@app.post("/api/real-leads/import")
async def import_real_company(data: RealCompanyImport):
    """Import a single real company and auto-find its email."""
    db = await get_db()

    # Deduplicate by website or company name
    if data.website:
        cur = await db.execute(
            "SELECT id FROM leads WHERE product_id=? AND website=?",
            (data.product_id, data.website.strip()),
        )
        if await cur.fetchone():
            await db.close()
            raise HTTPException(400, f"Company with website {data.website} already imported")

    found = await _find_email(data.website) if data.website else {}
    email = found.get("email")
    source_page = found.get("source_page")
    all_emails_json = found.get("all_emails_json")
    scrape_err = found.get("scrape_error")
    hunter_used = found.get("hunter_used", False)
    actual_website = found.get("resolved_website") or data.website
    cur = await db.execute(
        """INSERT INTO leads
           (type, company_name, contact_name, email, city, industry, description, product_id, source, website, email_status, all_emails, size, scrape_error)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "b2b",
            data.company_name,
            data.contact_name,
            email,
            data.city,
            data.industry,
            data.description,
            data.product_id,
            "real_import",
            actual_website,
            "unverified" if email else "not_found",
            all_emails_json,
            data.size,
            scrape_err,
        ),
    )
    lead_id = cur.lastrowid
    await db.commit()
    await db.close()

    return {
        "id": lead_id,
        "company_name": data.company_name,
        "email": email,
        "source_page": source_page,
        "hunter_used": hunter_used,
        "scrape_error": scrape_err,
    }


@app.post("/api/real-leads/bulk-import")
async def bulk_import_companies(data: BulkImport):
    """
    Bulk import companies from plain text.
    Each line: Company Name | website.de | City | Industry
    Website and other fields are optional.
    """
    lines = [l.strip() for l in data.raw_text.strip().splitlines() if l.strip()]
    results = []
    for line in lines:
        parts = [p.strip() for p in line.split("|")]
        company_name = parts[0] if len(parts) > 0 else ""
        website = parts[1] if len(parts) > 1 else None
        city = parts[2] if len(parts) > 2 else None
        industry = parts[3] if len(parts) > 3 else None
        description = parts[4] if len(parts) > 4 else None
        size = parts[5] if len(parts) > 5 else None
        if not company_name:
            continue
        try:
            result = await import_real_company(RealCompanyImport(
                company_name=company_name,
                website=website,
                city=city,
                industry=industry,
                description=description,
                size=size,
                product_id=data.product_id,
            ))
            results.append({"company": company_name, "status": "ok", **result})
        except HTTPException as e:
            results.append({"company": company_name, "status": "skipped", "reason": e.detail})
        except Exception as e:
            results.append({"company": company_name, "status": "error", "reason": str(e)})

    return {"total": len(lines), "imported": sum(1 for r in results if r["status"] == "ok"), "results": results}


@app.post("/api/leads/{lead_id}/find-email")
async def find_lead_email(lead_id: int):
    """Re-run email discovery for a specific lead (scrape + Hunter fallback)."""
    db = await get_db()
    cur = await db.execute("SELECT * FROM leads WHERE id=?", (lead_id,))
    row = await cur.fetchone()
    if not row:
        await db.close()
        raise HTTPException(404, "Lead not found")
    lead = dict(row)
    website = lead.get("website") or ""

    found = await _find_email(website) if website else {}
    email = found.get("email")
    all_emails_json = found.get("all_emails_json")
    scrape_err = found.get("scrape_error")
    hunter_used = found.get("hunter_used", False)
    source_page = found.get("source_page")

    if email:
        await db.execute(
            "UPDATE leads SET email=?, email_status='unverified', all_emails=?, scrape_error=NULL WHERE id=?",
            (email, all_emails_json, lead_id),
        )
    elif scrape_err:
        await db.execute("UPDATE leads SET scrape_error=? WHERE id=?", (scrape_err, lead_id))
    await db.commit()

    await db.close()
    return {"email": email, "source_page": source_page, "hunter_used": hunter_used}


@app.get("/api/stats")
async def get_stats():
    db = await get_db()
    stats = {}
    for label, query in [
        ("total_leads", "SELECT COUNT(*) FROM leads"),
        ("b2b_leads", "SELECT COUNT(*) FROM leads WHERE type='b2b'"),
        ("b2c_leads", "SELECT COUNT(*) FROM leads WHERE type='b2c'"),
        ("contacted", "SELECT COUNT(*) FROM leads WHERE status='contacted'"),
        ("qualified", "SELECT COUNT(*) FROM leads WHERE status='qualified'"),
        ("total_products", "SELECT COUNT(*) FROM products"),
        ("total_outreaches", "SELECT COUNT(*) FROM outreaches"),
    ]:
        cursor = await db.execute(query)
        row = await cursor.fetchone()
        stats[label] = row[0]
    await db.close()
    return stats
