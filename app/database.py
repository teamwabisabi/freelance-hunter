"""
Database layer — Supabase (PostgreSQL)
Run setup_db() once on first deploy to create tables.
"""

import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

def get_client() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_KEY"]
    return create_client(url, key)


def setup_db():
    """Create tables via Supabase SQL editor — run this SQL in your Supabase dashboard."""
    sql = """
    -- Job listings collected from all sources
    CREATE TABLE IF NOT EXISTS job_listings (
        id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
        external_id TEXT UNIQUE NOT NULL,       -- platform-specific ID for dedup
        source TEXT NOT NULL,                    -- 'linkedin_rss', 'freelance_be', 'direct_outreach', etc.
        title TEXT NOT NULL,
        company TEXT,
        location TEXT,
        description TEXT,
        url TEXT,
        raw_data JSONB,
        collected_at TIMESTAMPTZ DEFAULT NOW(),
        
        -- Claude scoring
        match_score INTEGER,                     -- 0-10
        match_reasoning TEXT,
        relevant_experiences TEXT,
        concerns TEXT,
        draft_cover_letter TEXT,
        recommended_cv_variant TEXT,
        scored_at TIMESTAMPTZ,
        
        -- Your decision
        status TEXT DEFAULT 'pending',           -- pending | approved | skipped | submitted | saved
        your_notes TEXT,
        edited_cover_letter TEXT,
        decided_at TIMESTAMPTZ,
        submitted_at TIMESTAMPTZ
    );

    -- Direct outreach targets (loaded from CSV)
    CREATE TABLE IF NOT EXISTS outreach_targets (
        id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
        company_name TEXT NOT NULL,
        contact_email TEXT,
        contact_name TEXT,
        sector TEXT,
        notes TEXT,
        last_contacted TIMESTAMPTZ,
        status TEXT DEFAULT 'not_contacted',     -- not_contacted | contacted | responded | not_interested
        draft_email TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );

    -- Email log
    CREATE TABLE IF NOT EXISTS email_log (
        id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
        to_email TEXT,
        subject TEXT,
        sent_at TIMESTAMPTZ DEFAULT NOW(),
        type TEXT                                -- 'digest' | 'outreach'
    );
    """
    print("Copy and run this SQL in your Supabase SQL editor:")
    print(sql)
    return sql


# --- Job listing helpers ---

def get_known_external_ids(source: str = None) -> set:
    """Return all external_ids we've seen, optionally filtered by source."""
    client = get_client()
    query = client.table("job_listings").select("external_id")
    if source:
        query = query.eq("source", source)
    result = query.execute()
    return {row["external_id"] for row in result.data}


def insert_job_listing(listing: dict) -> dict:
    client = get_client()
    # Never pass an id — let Supabase generate it to avoid conflicts
    clean = {k: v for k, v in listing.items() if k != "id"}
    result = client.table("job_listings").insert(clean).execute()
    return result.data[0] if result.data else {}


def update_job_listing(listing_id: str, updates: dict):
    client = get_client()
    client.table("job_listings").update(updates).eq("id", listing_id).execute()


def get_pending_listings(min_score: int = 7) -> list:
    client = get_client()
    result = (
        client.table("job_listings")
        .select("*")
        .eq("status", "pending")
        .gte("match_score", min_score)
        .order("match_score", desc=True)
        .execute()
    )
    return result.data


def get_all_listings(limit: int = 50) -> list:
    client = get_client()
    result = (
        client.table("job_listings")
        .select("*")
        .order("collected_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data


def get_listing_by_id(listing_id: str) -> dict:
    client = get_client()
    result = (
        client.table("job_listings")
        .select("*")
        .eq("id", listing_id)
        .single()
        .execute()
    )
    return result.data


# --- Outreach helpers ---

def get_outreach_targets(status: str = "not_contacted") -> list:
    client = get_client()
    result = (
        client.table("outreach_targets")
        .select("*")
        .eq("status", status)
        .execute()
    )
    return result.data


def update_outreach_target(target_id: str, updates: dict):
    client = get_client()
    client.table("outreach_targets").update(updates).eq("id", target_id).execute()


def seed_outreach_targets():
    """Load outreach_targets.csv into Supabase (run once)."""
    import csv
    client = get_client()
    
    with open("app/outreach_targets.csv", "r") as f:
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            rows.append({
                "company_name": row["company_name"],
                "contact_email": row["contact_email"] or None,
                "contact_name": row["contact_name"] or None,
                "sector": row["sector"],
                "notes": row["notes"],
                "status": row["status"] or "not_contacted",
            })
    
    if rows:
        client.table("outreach_targets").upsert(rows, on_conflict="company_name").execute()
        print(f"Seeded {len(rows)} outreach targets.")
