"""
Job collectors for each source.
Phase 1: LinkedIn RSS feed + direct outreach targets
Phase 2 (future): Freelance.be, Références.be, Malt.be scrapers
"""

import feedparser
import hashlib
import httpx
from datetime import datetime, timezone


# ─── LinkedIn RSS ────────────────────────────────────────────────────────────

LINKEDIN_RSS_FEEDS = [
    # LinkedIn job search RSS — adjust keywords and location as needed
    "https://www.linkedin.com/jobs/search/?keywords=Agile+Coach&location=Belgium&f_WT=2&f_JT=C&f_E=4%2C5&f_TPR=r86400",
    "https://www.linkedin.com/jobs/search/?keywords=Scrum+Master&location=Belgium&f_WT=2&f_JT=C&f_E=4%2C5&f_TPR=r86400",
    "https://www.linkedin.com/jobs/search/?keywords=Agile+Coach+freelance&location=Belgium&f_TPR=r86400",
    "https://www.linkedin.com/jobs/search/?keywords=Scrum+Master+freelance&location=Belgium&f_TPR=r86400",
]

# LinkedIn RSS endpoint (more stable than scraping)
LINKEDIN_RSS_TEMPLATE = (
    "https://www.linkedin.com/jobs/search.rss?"
    "keywords={keywords}&location=Belgium&f_JT=C&f_TPR=r86400"
)


def collect_linkedin_rss() -> list[dict]:
    """
    Collect jobs from LinkedIn RSS feeds.
    LinkedIn's RSS is rate-limited but doesn't require auth.
    Returns list of raw listing dicts.
    """
    listings = []
    search_terms = [
        "Agile Coach Belgium",
        "Scrum Master freelance Belgium",
        "Agile Coach freelance Belgique",
    ]

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; job-collector/1.0)"
    }

    for term in search_terms:
        url = LINKEDIN_RSS_TEMPLATE.format(keywords=term.replace(" ", "+"))
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                external_id = hashlib.md5(
                    entry.get("link", entry.get("id", "")).encode()
                ).hexdigest()

                listings.append({
                    "external_id": f"linkedin_{external_id}",
                    "source": "linkedin_rss",
                    "title": entry.get("title", "Unknown title"),
                    "company": _extract_company_from_linkedin(entry),
                    "location": entry.get("location", "Belgium"),
                    "description": entry.get("summary", ""),
                    "url": entry.get("link", ""),
                    "raw_data": {
                        "search_term": term,
                        "published": entry.get("published", ""),
                    },
                })
        except Exception as e:
            print(f"LinkedIn RSS error for '{term}': {e}")

    return listings


def _extract_company_from_linkedin(entry: dict) -> str:
    """LinkedIn RSS sometimes puts company in the title as 'Role - Company'."""
    title = entry.get("title", "")
    if " - " in title:
        parts = title.split(" - ")
        if len(parts) >= 2:
            return parts[-1].strip()
    return entry.get("author", "Unknown")


# ─── Freelance.be placeholder ─────────────────────────────────────────────────

def collect_freelance_be() -> list[dict]:
    """
    Phase 2: Scrape freelance.be for Agile Coach / Scrum Master missions.
    Placeholder — returns empty list in Phase 1.
    """
    # TODO Phase 2: implement Playwright scraper
    print("freelance.be collector: not yet implemented (Phase 2)")
    return []


# ─── Malt.be placeholder ──────────────────────────────────────────────────────

def collect_malt() -> list[dict]:
    """
    Phase 2: Malt.be missions.
    Placeholder — returns empty list in Phase 1.
    """
    print("Malt collector: not yet implemented (Phase 2)")
    return []


# ─── Direct outreach (generate drafts for un-contacted targets) ───────────────

def collect_outreach_targets() -> list[dict]:
    """
    Returns outreach targets that haven't been contacted yet.
    These go through Claude for email drafting, not scoring.
    """
    from app.database import get_outreach_targets
    return get_outreach_targets(status="not_contacted")


# ─── Master collector ─────────────────────────────────────────────────────────

def collect_all() -> dict:
    """
    Run all collectors. Returns dict with listings and outreach targets.
    """
    return {
        "listings": collect_linkedin_rss() + collect_freelance_be() + collect_malt(),
        "outreach_targets": collect_outreach_targets(),
    }
