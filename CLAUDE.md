# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A personal automated job-hunting pipeline for Dries Bellen, a Belgian freelance Agile Coach / Scrum Master. It scrapes job boards, scores listings against his profile with Claude, drafts cover letters and cold outreach emails, and serves a small password-protected dashboard to review/approve/skip them. Deployed on Railway, single Python/FastAPI process.

## Commands

```bash
# Install deps
pip install -r requirements.txt
playwright install chromium   # only needed for the Malt collector

# Run locally (requires .env — see README.md Setup Guide for required vars)
uvicorn main:app --reload --port 8000

# One-off: load app/outreach_targets.csv into Supabase
python -c "from app.database import seed_outreach_targets; seed_outreach_targets()"

# Manually trigger the full pipeline (also reachable via POST /admin/run-pipeline
# in the dashboard, or by clicking "↻ Run now")
python -c "from app.pipeline import run_pipeline; run_pipeline()"
```

There is no test suite, linter, or CI config in this repo.

Required env vars (loaded via `.env` / `python-dotenv`): `ANTHROPIC_API_KEY`, `RESEND_API_KEY`, `EMAIL_FROM`, `EMAIL_TO`, `SUPABASE_URL`, `SUPABASE_KEY`, `DASHBOARD_PASSWORD`, `BASE_URL`, and optionally `MIN_SCORE` (default 7).

## Architecture

Single FastAPI app (`main.py`) that does two things: serves the dashboard, and runs a daily APScheduler cron job (07:00 UTC) that calls `app/pipeline.py:run_pipeline()`. The same function is also triggered manually via `POST /admin/run-pipeline`.

Pipeline flow (`app/pipeline.py`):
1. **Collect** — `app/collectors.py:collect_all()` scrapes each source (LinkedIn, Freelance.be, Références.be, Malt via Playwright, Stepstone) independently; failures in one source don't block others. Each collector returns dicts with a deterministic `external_id` (md5 hash) used for dedup.
2. **Dedup** — drop listings whose `external_id` is already in `job_listings` (via `get_known_external_ids()`).
3. **Keyword pre-filter** — `is_relevant()` requires the title/description to contain an actual agile/scrum phrase (not just any generic "agile" mention), to cut down on Claude API calls.
4. **Location filter** — `is_acceptable_location()` checks against a hardcoded multilingual list of accepted Belgian/nearby cities + remote; unknown/empty location is let through. Listings failing either filter are inserted with `status="filtered"`, `match_score=0`, and never scored.
5. **Score** — surviving listings go to `app/scorer.py:score_and_draft()`, which sends the listing + `app/profile.md` (Dries's profile, hand-maintained) to Claude and asks for a strict JSON response: `match_score` (0-10), reasoning, relevant experience, concerns, a drafted cover letter in the job's language, and a recommended CV variant. Listings scoring ≥ `MIN_SCORE` are queued for the digest; all scored listings are persisted regardless of score (`status="pending"`).
6. **Outreach drafting** — for any `outreach_targets` row still `not_contacted`, `app/scorer.py:draft_outreach_email()` drafts a cold email and flips status to `draft_ready`.
7. **Notify** — `app/notifier.py:send_digest()` emails an HTML digest (via Resend) listing new high-score matches and outreach draft counts, linking back to the dashboard.

Persistence is entirely Supabase/Postgres via `app/database.py`, which wraps three tables: `job_listings`, `outreach_targets`, `email_log`. There is no ORM — every function builds a fresh client (`get_client()`) and calls the Supabase query builder directly. Table DDL lives only in `README.md` / `database.py:setup_db()` docstring (run manually in the Supabase SQL editor) — there are no migrations.

Dashboard (FastAPI + Jinja2, templates in `templates/`):
- Auth is a single shared-password cookie check (`check_auth` in `main.py`), not per-user sessions.
- `/dashboard` lists listings with status counts; `filtered` listings are always hidden, `skipped` ones hidden unless `?show_skipped=true`.
- `/dashboard/listing/{id}` lets you edit the draft cover letter / notes and submit a decision (`approved`, `skipped`, `applied`, `interviewing`, `selected`, etc. — see `valid_actions` in `main.py`).
- `/dashboard/outreach` shows outreach drafts ready for review/approval.

## Key things to know when editing

- **Job listing status** is a free-form string state machine, not an enum in the DB: `pending → approved/skipped/filtered → applied → interviewing → selected/rejected`, plus `saved`/`submitted`. Valid transitions are enforced only in `main.py`'s `valid_actions` set.
- **Collectors are scraping public pages with hand-picked CSS selectors** and no test coverage — they are expected to silently degrade (return fewer/no results) as target sites change markup, rather than crash the pipeline. New sources should follow the existing pattern: a `collect_<source>()` function returning a list of dicts with `external_id`, `source`, `title`, `company`, `location`, `description`, `url`, `raw_data`, added to the `collect_all()` loop.
- **`app/profile.md`** is the single source of truth Claude uses for scoring/drafting — keep edits to Dries's profile there, not hardcoded in `scorer.py`.
- Per the README, scraper testing must happen from a deployed (Railway) environment — sites are not necessarily reachable from a local/sandboxed dev environment.
