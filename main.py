"""
FastAPI app — serves the dashboard and API endpoints.
Also starts the APScheduler for daily pipeline runs.
"""

import os
import threading
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, Request, Form, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

load_dotenv()

from app.database import (
    get_pending_listings,
    get_all_listings,
    get_listing_by_id,
    update_job_listing,
    get_outreach_targets,
    update_outreach_target,
)
from app.pipeline import run_pipeline

DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "changeme")
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")

# ─── Pipeline run lock ────────────────────────────────────────────────────────
# Both the daily cron job and manual "Run now" calls can hit run_pipeline().
# Concurrent runs race on inserting the same newly-discovered listing (each
# snapshots known external_ids independently), which crashes with a duplicate
# key DB error. Only allow one run in flight at a time.

pipeline_lock = threading.Lock()

def run_pipeline_locked():
    if not pipeline_lock.acquire(blocking=False):
        print("Pipeline already running — skipping this trigger.")
        return {"new_listings_found": 0, "high_score_matches": 0, "outreach_drafts": 0, "skipped": True}
    try:
        return run_pipeline()
    finally:
        pipeline_lock.release()

# ─── Scheduler ───────────────────────────────────────────────────────────────

scheduler = BackgroundScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run pipeline daily at 07:00 UTC
    scheduler.add_job(run_pipeline_locked, "cron", hour=7, minute=0, id="daily_pipeline")
    scheduler.start()
    print("Scheduler started — pipeline runs daily at 07:00 UTC")
    yield
    scheduler.shutdown()

# ─── App ─────────────────────────────────────────────────────────────────────

app = FastAPI(title="Freelance Hunter", lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

# ─── Simple session-less auth (cookie-based) ─────────────────────────────────

def check_auth(request: Request):
    if request.cookies.get("auth") != DASHBOARD_PASSWORD:
        raise HTTPException(status_code=302, headers={"Location": "/login"})


# ─── Auth routes ─────────────────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(request: Request, password: str = Form(...)):
    if password == DASHBOARD_PASSWORD:
        response = RedirectResponse("/dashboard", status_code=302)
        response.set_cookie("auth", password, httponly=True, max_age=86400 * 30)
        return response
    return templates.TemplateResponse("login.html", {"request": request, "error": "Wrong password"})


@app.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie("auth")
    return response


# ─── Dashboard ───────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse("/dashboard")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, msg: str = "", show_skipped: bool = False, min_score: int = 6, _=Depends(check_auth)):
    pending = get_pending_listings(min_score=min_score)
    all_listings = get_all_listings(limit=100)

    # Counts
    total = len(all_listings)
    filtered_count = sum(1 for l in all_listings if l["status"] == "filtered")
    skipped_count = sum(1 for l in all_listings if l["status"] == "skipped")
    approved_count = sum(1 for l in all_listings if l["status"] == "approved")
    applied_count = sum(1 for l in all_listings if l["status"] == "applied")
    interviewing_count = sum(1 for l in all_listings if l["status"] == "interviewing")
    selected_count = sum(1 for l in all_listings if l["status"] == "selected")
    submitted_count = sum(1 for l in all_listings if l["status"] == "submitted")

    # Always hide auto-filtered; hide manually skipped unless toggled
    if show_skipped:
        all_listings = [l for l in all_listings if l["status"] != "filtered"]
    else:
        all_listings = [l for l in all_listings if l["status"] not in ("filtered", "skipped")]

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "pending": pending,
        "all_listings": all_listings,
        "now": datetime.now(timezone.utc),
        "msg": msg,
        "show_skipped": show_skipped,
        "min_score": min_score,
        "total": total,
        "filtered_count": filtered_count,
        "skipped_count": skipped_count,
        "approved_count": approved_count,
        "applied_count": applied_count,
        "interviewing_count": interviewing_count,
        "selected_count": selected_count,
    })


@app.get("/dashboard/listing/{listing_id}", response_class=HTMLResponse)
async def listing_detail(listing_id: str, request: Request, _=Depends(check_auth)):
    listing = get_listing_by_id(listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    return templates.TemplateResponse("listing_detail.html", {
        "request": request,
        "listing": listing,
    })


@app.post("/dashboard/listing/{listing_id}/decide")
async def decide_listing(
    listing_id: str,
    request: Request,
    action: str = Form(...),
    edited_cover_letter: str = Form(""),
    your_notes: str = Form(""),
    _=Depends(check_auth),
):
    """Handle approve / skip / save decisions."""
    valid_actions = {"approved", "skipped", "saved", "applied", "interviewing", "rejected", "selected", "filtered"}
    if action not in valid_actions:
        raise HTTPException(status_code=400, detail="Invalid action")

    update_job_listing(listing_id, {
        "status": action,
        "edited_cover_letter": edited_cover_letter or None,
        "your_notes": your_notes or None,
        "decided_at": datetime.now(timezone.utc).isoformat(),
    })

    return RedirectResponse("/dashboard", status_code=302)


# ─── Outreach dashboard ───────────────────────────────────────────────────────

@app.get("/dashboard/outreach", response_class=HTMLResponse)
async def outreach_dashboard(request: Request, _=Depends(check_auth)):
    drafts = get_outreach_targets(status="draft_ready")
    contacted = get_outreach_targets(status="contacted")
    return templates.TemplateResponse("outreach.html", {
        "request": request,
        "drafts": drafts,
        "contacted": contacted,
    })


@app.post("/dashboard/outreach/{target_id}/approve")
async def approve_outreach(
    target_id: str,
    request: Request,
    edited_email: str = Form(""),
    _=Depends(check_auth),
):
    update_outreach_target(target_id, {
        "draft_email": edited_email,
        "status": "approved_to_send",
    })
    return RedirectResponse("/dashboard/outreach", status_code=302)


@app.post("/dashboard/outreach/{target_id}/skip")
async def skip_outreach(target_id: str, _=Depends(check_auth)):
    update_outreach_target(target_id, {"status": "skipped"})
    return RedirectResponse("/dashboard/outreach", status_code=302)


# ─── Admin / manual triggers ─────────────────────────────────────────────────

@app.post("/admin/run-pipeline")
async def trigger_pipeline(request: Request, background_tasks: BackgroundTasks, _=Depends(check_auth)):
    """Manually trigger the pipeline — fires in background and returns immediately."""
    if pipeline_lock.locked():
        msg = "A pipeline run is already in progress — try again in a bit."
    else:
        background_tasks.add_task(run_pipeline_locked)
        msg = "Pipeline started — refresh in a few minutes to see new listings."
    return RedirectResponse(f"/dashboard?msg={msg}", status_code=302)


@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}
