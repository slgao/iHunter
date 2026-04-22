import aiosqlite
import json
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "ihunters.db"

CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,  -- 'b2b' or 'b2c'
    company_name TEXT,
    contact_name TEXT,
    email TEXT,
    phone TEXT,
    city TEXT,
    industry TEXT,
    description TEXT,
    status TEXT DEFAULT 'new',  -- new, contacted, replied, qualified, closed
    product_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT,
    description TEXT,
    price_range TEXT,
    moq TEXT,
    origin_city TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS outreaches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER,
    subject_de TEXT,
    subject_en TEXT,
    body_de TEXT,
    body_en TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (lead_id) REFERENCES leads(id)
);
"""


async def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    for stmt in CREATE_TABLES.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            await db.execute(stmt)
    # Migrations
    for col, definition in [
        ("email_status", "TEXT DEFAULT 'unverified'"),
        ("source", "TEXT DEFAULT 'ai_generated'"),
        ("website", "TEXT"),
        ("all_emails", "TEXT"),
        ("size", "TEXT"),
        ("scrape_error", "TEXT"),
    ]:
        try:
            await db.execute(f"ALTER TABLE leads ADD COLUMN {col} {definition}")
        except Exception:
            pass
    try:
        await db.execute("ALTER TABLE products ADD COLUMN analysis TEXT")
    except Exception:
        pass
    await db.commit()
    return db


async def init_db():
    db = await get_db()
    await db.close()
