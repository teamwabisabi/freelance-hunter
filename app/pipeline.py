"""
Main pipeline — runs daily via APScheduler.
Collect → Dedup → Score → Notify
"""

import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

from app.collectors import collect_all
from app.database import (
    get_known_external_ids,
    insert_job_listing,
    update_job_listing,
    update_outreach_target,
)
from app.scorer import score_and_draft, draft_outreach_email
from app.notifier import send_digest

MIN_SCORE = int(os.environ.get("MIN_SCORE", "7"))

RELEVANT_KEYWORDS = [
    "agile coach",
    "scrum master",
    "agile master",
    "coach agile",
    "agiliste",
    "servant leader",
    "scrum coach",
]

def is_relevant(listing: dict) -> bool:
    """Require agile/scrum-specific phrases, not just any agile keyword."""
    text = (
        (listing.get("title") or "") + " " +
        (listing.get("description") or "")
    ).lower()
    return any(kw in text for kw in RELEVANT_KEYWORDS)



def run_pipeline():
    """Full pipeline run. Called by scheduler and can be triggered manually."""
    print(f"\n{'='*50}")
    print(f"Pipeline started at {datetime.now(timezone.utc).isoformat()}")
    print(f"{'='*50}")

    # 1. Collect
    collected = collect_all()
    raw_listings = collected["listings"]
    outreach_targets = collected["outreach_targets"]

    print(f"Collected {len(raw_listings)} raw listings, {len(outreach_targets)} outreach targets")

    # 2. Dedup job listings
    known_ids = get_known_external_ids()
    new_listings = [l for l in raw_listings if l["external_id"] not in known_ids]
    print(f"New (unseen) listings: {len(new_listings)}")

    # 2b. Quick keyword pre-filter to avoid scoring irrelevant listings
    relevant = [l for l in new_listings if is_relevant(l)]
    skipped = len(new_listings) - len(relevant)
    print(f"After keyword filter: {len(relevant)} relevant, {skipped} skipped")

    # Insert irrelevant listings without scoring (so we don't re-process them)
    for listing in new_listings:
        if not is_relevant(listing):
            listing["match_score"] = 0
            listing["match_reasoning"] = "Filtered out by keyword pre-check"
            listing["status"] = "skipped"
            try:
                insert_job_listing(listing)
            except Exception:
                pass

    # 3. Score relevant listings
    high_score_listings = []
    for listing in relevant:
        print(f"  Scoring: {listing['title']} @ {listing.get('company', '?')}")
        try:
            score_result = score_and_draft(listing)
            listing.update(score_result)
            saved = insert_job_listing(listing)
            listing["id"] = saved.get("id")

            if score_result.get("match_score", 0) >= MIN_SCORE:
                high_score_listings.append(listing)
                print(f"    ✓ Score: {score_result['match_score']}/10 — queued for digest")
            else:
                print(f"    ✗ Score: {score_result['match_score']}/10 — below threshold")

        except Exception as e:
            print(f"    Error scoring listing: {e}")
            # Still insert without score so we don't re-process
            listing["match_score"] = None
            insert_job_listing(listing)

    # 4. Draft outreach emails for un-contacted targets
    new_outreach_drafts = 0
    for target in outreach_targets:
        print(f"  Drafting outreach for: {target['company_name']}")
        try:
            email_draft = draft_outreach_email(target)
            update_outreach_target(target["id"], {
                "draft_email": f"Subject: {email_draft['subject']}\n\n{email_draft['body']}",
                "status": "draft_ready",
            })
            new_outreach_drafts += 1
        except Exception as e:
            print(f"    Error drafting outreach: {e}")

    # 5. Send digest
    if high_score_listings or new_outreach_drafts > 0:
        send_digest(high_score_listings, new_outreach_drafts)
    else:
        print("Nothing to notify about today.")

    print(f"\nPipeline complete. {len(high_score_listings)} matches surfaced, {new_outreach_drafts} outreach drafts.")
    return {
        "new_listings_found": len(new_listings),
        "high_score_matches": len(high_score_listings),
        "outreach_drafts": new_outreach_drafts,
    }
