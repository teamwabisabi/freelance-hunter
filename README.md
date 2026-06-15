# 🎯 Freelance Hunter

Your personal automated freelance mission finder — built for Dries Bellen, Agile Coach / Scrum Master.

## What it does

1. **Collects** job listings daily from LinkedIn RSS and future sources
2. **Scores** each listing using Claude (0–10 match against your profile)
3. **Drafts** a tailored cover letter for high-scoring matches
4. **Emails** you a daily digest with links to your dashboard
5. **Dashboard** lets you review, edit, approve, or skip each application
6. **Outreach** module drafts cold emails to target companies

---

## Setup Guide

### Step 1 — Clone and configure locally

```bash
git clone https://github.com/YOUR_USERNAME/freelance-hunter.git
cd freelance-hunter
cp .env.example .env
```

Edit `.env` and fill in all values (see Step 4 for where to get them).

### Step 2 — Create a Supabase project

1. Go to [supabase.com](https://supabase.com) → New project
2. Copy your **Project URL** and **anon public key** into `.env`
3. Open the **SQL Editor** in your Supabase dashboard
4. Run this SQL to create the tables:

```sql
CREATE TABLE IF NOT EXISTS job_listings (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    external_id TEXT UNIQUE NOT NULL,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    company TEXT,
    location TEXT,
    description TEXT,
    url TEXT,
    raw_data JSONB,
    collected_at TIMESTAMPTZ DEFAULT NOW(),
    match_score INTEGER,
    match_reasoning TEXT,
    relevant_experiences TEXT,
    concerns TEXT,
    draft_cover_letter TEXT,
    recommended_cv_variant TEXT,
    scored_at TIMESTAMPTZ,
    status TEXT DEFAULT 'pending',
    your_notes TEXT,
    edited_cover_letter TEXT,
    decided_at TIMESTAMPTZ,
    submitted_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS outreach_targets (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    company_name TEXT UNIQUE NOT NULL,
    contact_email TEXT,
    contact_name TEXT,
    sector TEXT,
    notes TEXT,
    last_contacted TIMESTAMPTZ,
    status TEXT DEFAULT 'not_contacted',
    draft_email TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS email_log (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    to_email TEXT,
    subject TEXT,
    sent_at TIMESTAMPTZ DEFAULT NOW(),
    type TEXT
);
```

### Step 3 — Get your API keys

| Service | Where to get it | .env variable |
|---|---|---|
| **Anthropic** | [console.anthropic.com](https://console.anthropic.com) → API Keys | `ANTHROPIC_API_KEY` |
| **Resend** | [resend.com](https://resend.com) → API Keys (free tier: 100 emails/day) | `RESEND_API_KEY` |
| **Supabase URL** | Supabase dashboard → Settings → API | `SUPABASE_URL` |
| **Supabase key** | Supabase dashboard → Settings → API → anon public | `SUPABASE_KEY` |

For `EMAIL_FROM`: Resend requires a verified domain. Options:
- Use Resend's free shared domain: `onboarding@resend.dev` (works immediately)
- Or verify your own domain at resend.com/domains

### Step 4 — Create a Railway account and deploy

1. Go to [railway.app](https://railway.app) → Sign up with GitHub
2. Click **New Project** → **Deploy from GitHub repo**
3. Select your `freelance-hunter` repository
4. Railway will auto-detect the Python app

**Add environment variables in Railway:**
- Go to your service → **Variables** tab
- Add all variables from your `.env` file
- For `BASE_URL`: set it to your Railway app URL (visible after first deploy, e.g. `https://freelance-hunter-production.up.railway.app`)

5. Railway will deploy automatically. Check the **Deploy** tab for logs.

### Step 5 — Seed outreach targets

After deploying, call this once to load your target companies into Supabase:

```bash
# Locally (with your .env filled in):
python -c "from app.database import seed_outreach_targets; seed_outreach_targets()"
```

Or add companies directly in the Supabase table editor.

### Step 6 — Test it

1. Open your Railway app URL
2. Log in with your `DASHBOARD_PASSWORD`
3. Click **"↻ Run now"** to trigger the pipeline manually
4. Check your email for the digest
5. Click the link to open the dashboard

---

## Customisation

### Adjust your profile
Edit `app/profile.md` — this is what Claude uses to score matches. Keep it accurate and up to date.

### Adjust match threshold
In Railway Variables, set `MIN_SCORE=6` to see more results, `MIN_SCORE=8` for only strong matches.

### Add outreach targets
Edit `app/outreach_targets.csv` and re-run `seed_outreach_targets()`, or add rows directly in Supabase.

### Change pipeline schedule
In `main.py`, find `scheduler.add_job(run_pipeline, "cron", hour=7, minute=0)` and adjust.

---

## Phase 2 (coming)
- Freelance.be scraper
- Références.be scraper  
- Malt.be scraper
- Playwright-based auto-submission for approved applications

---

## Architecture

```
Railway (Python/FastAPI)
├── APScheduler → daily pipeline
│   ├── collectors.py → LinkedIn RSS + future scrapers
│   ├── scorer.py → Claude API scoring + drafting
│   ├── database.py → Supabase (PostgreSQL)
│   └── notifier.py → Resend email digest
└── Dashboard (FastAPI + Jinja2)
    ├── /dashboard → match overview
    ├── /dashboard/listing/{id} → review + edit + decide
    └── /dashboard/outreach → cold email drafts
```
