"""
Job collectors for each source.
Uses httpx+BeautifulSoup where possible, Playwright for JS-heavy sites.
All sites tested to be reachable from Railway (not from Claude sandbox).
"""

import hashlib
import httpx
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timezone

# ─── Shared browser headers ───────────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "nl-BE,nl;q=0.9,fr;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

SEARCH_TERMS = [
    "agile coach",
    "scrum master",
    "agile coach freelance",
    "scrum master freelance",
]

SEARCH_TERMS_FR = [
    "agile coach",
    "scrum master",
    "coach agile freelance",
]


def _make_id(source: str, value: str) -> str:
    return f"{source}_{hashlib.md5(value.encode()).hexdigest()}"


# ─── LinkedIn ─────────────────────────────────────────────────────────────────

def collect_linkedin() -> list[dict]:
    """
    Scrape LinkedIn public job listings.
    Uses their public /jobs/search page which doesn't require auth.
    Falls back gracefully if blocked.
    """
    listings = []
    seen = set()

    searches = [
        # f_JT=C = Contract, f_JT=T = Temporary — both relevant for freelance
        ("Agile Coach", "Belgium", "C"),
        ("Scrum Master", "Belgium", "C"),
        ("Agile Coach", "Belgium", "T"),
        ("Scrum Master freelance", "Belgium", "C"),
        ("Coach Agile", "Belgique", "C"),
    ]

    with httpx.Client(headers=HEADERS, timeout=20, follow_redirects=True) as client:
        for keyword, location, job_type in searches:
            url = (
                f"https://www.linkedin.com/jobs/search/"
                f"?keywords={keyword.replace(' ', '+')}"
                f"&location={location}"
                f"&f_JT={job_type}"
                f"&f_TPR=r86400"  # last 24h
                f"&position=1&pageNum=0"
            )
            try:
                r = client.get(url)
                if r.status_code != 200:
                    print(f"LinkedIn {keyword}: HTTP {r.status_code}")
                    continue

                soup = BeautifulSoup(r.text, "html.parser")
                cards = soup.select("div.base-card, li.jobs-search-results__list-item")

                for card in cards:
                    title_el = card.select_one("h3.base-search-card__title, h3, .job-result-card__title")
                    company_el = card.select_one("h4.base-search-card__subtitle, .job-result-card__company-name")
                    location_el = card.select_one("span.job-search-card__location, .job-result-card__location")
                    link_el = card.select_one("a.base-card__full-link, a[href*='/jobs/view/']")

                    if not title_el or not link_el:
                        continue

                    url_raw = link_el.get("href", "").split("?")[0]
                    if url_raw in seen:
                        continue
                    seen.add(url_raw)

                    listings.append({
                        "external_id": _make_id("linkedin", url_raw),
                        "source": "linkedin",
                        "title": title_el.get_text(strip=True),
                        "company": company_el.get_text(strip=True) if company_el else None,
                        "location": location_el.get_text(strip=True) if location_el else "Belgium",
                        "description": card.get_text(separator=" ", strip=True)[:1000],
                        "url": url_raw,
                        "raw_data": {"search": keyword},
                    })

                print(f"LinkedIn '{keyword}': {len(cards)} cards found")

            except Exception as e:
                print(f"LinkedIn error for '{keyword}': {e}")

    return listings


# ─── Freelance.be ─────────────────────────────────────────────────────────────

def collect_freelance_be() -> list[dict]:
    """
    Scrape freelance.be project listings.
    """
    listings = []
    seen = set()

    with httpx.Client(headers=HEADERS, timeout=20, follow_redirects=True) as client:
        for term in ["agile+coach", "scrum+master"]:
            # Try both URL patterns
            for url in [
                f"https://www.freelance.be/nl/opdrachten?zoekterm={term}",
                f"https://www.freelance.be/fr/missions?terme={term}",
                f"https://www.freelance.be/en/projects?keyword={term}",
            ]:
                try:
                    r = client.get(url)
                    if r.status_code == 404:
                        continue
                    if r.status_code != 200:
                        print(f"freelance.be '{url}': HTTP {r.status_code}")
                        continue

                    soup = BeautifulSoup(r.text, "html.parser")
                    cards = soup.select(
                        "div.project-item, article.project, .col-project, "
                        "h2 a[href*='opdracht'], h2 a[href*='mission'], h3 a"
                    )

                    for card in cards:
                        link_el = card if card.name == "a" else card.select_one("a")
                        if not link_el:
                            continue
                        href = link_el.get("href", "")
                        if not href or href in seen:
                            continue
                        seen.add(href)
                        full_url = href if href.startswith("http") else f"https://www.freelance.be{href}"
                        title = link_el.get_text(strip=True) or card.get_text(strip=True)[:80]
                        listings.append({
                            "external_id": _make_id("freelance_be", full_url),
                            "source": "freelance_be",
                            "title": title,
                            "company": None,
                            "location": "Belgium",
                            "description": card.get_text(separator=" ", strip=True)[:800],
                            "url": full_url,
                            "raw_data": {"search": term},
                        })

                    if cards:
                        print(f"freelance.be '{url}': {len(cards)} cards")
                        break  # found working URL pattern, stop trying others

                except Exception as e:
                    print(f"freelance.be error for {url}: {e}")

    return listings


# ─── Références.be ────────────────────────────────────────────────────────────

def collect_references_be() -> list[dict]:
    """
    Scrape références.be job listings.
    """
    listings = []
    seen = set()

    with httpx.Client(headers=HEADERS, timeout=20, follow_redirects=True) as client:
        for term in ["agile coach", "scrum master"]:
            url = f"https://www.references.be/jobs?q={term.replace(' ', '+')}&l=Belgique"
            try:
                r = client.get(url)
                if r.status_code != 200:
                    print(f"references.be '{term}': HTTP {r.status_code}")
                    continue

                soup = BeautifulSoup(r.text, "html.parser")
                cards = soup.select("article.job-ad, div.job-item, li.job-result, .job-listing")

                for card in cards:
                    title_el = card.select_one("h2 a, h3 a, .job-title a, a.job-link")
                    if not title_el:
                        continue

                    href = title_el.get("href", "")
                    if href in seen:
                        continue
                    seen.add(href)

                    full_url = href if href.startswith("http") else f"https://www.references.be{href}"
                    company_el = card.select_one(".company-name, .employer, h4")

                    listings.append({
                        "external_id": _make_id("references_be", full_url),
                        "source": "references_be",
                        "title": title_el.get_text(strip=True),
                        "company": company_el.get_text(strip=True) if company_el else None,
                        "location": "Belgium",
                        "description": card.get_text(separator=" ", strip=True)[:800],
                        "url": full_url,
                        "raw_data": {"search": term},
                    })

                print(f"references.be '{term}': {len(cards)} cards")

            except Exception as e:
                print(f"references.be error: {e}")

    return listings


# ─── Malt.be ─────────────────────────────────────────────────────────────────

def collect_malt() -> list[dict]:
    """
    Scrape Malt.be project listings using async Playwright
    run via asyncio to avoid conflict with FastAPI's event loop.
    """
    import asyncio

    async def _scrape():
        listings = []
        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox",
                          "--disable-dev-shm-usage"],
                )
                page = await browser.new_page(
                    user_agent=HEADERS["User-Agent"],
                    extra_http_headers={"Accept-Language": "nl-BE,nl;q=0.9,en;q=0.8"},
                )
                seen = set()
                for term in ["agile-coach", "scrum-master"]:
                    try:
                        url = f"https://www.malt.be/s/{term}?maxDailyRate=0"
                        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                        await page.wait_for_timeout(3000)
                        html = await page.content()
                        soup = BeautifulSoup(html, "html.parser")
                        cards = soup.select(
                            "article, .mission-card, [data-testid='mission-card'], "
                            ".sc-mission-card, div[class*='MissionCard']"
                        )
                        for card in cards:
                            link_el = card.select_one(
                                "a[href*='/project/'], a[href*='/mission/']"
                            )
                            title_el = card.select_one("h2, h3, [class*='title']")
                            if not link_el and not title_el:
                                continue
                            href = link_el.get("href", "") if link_el else ""
                            title = (title_el.get_text(strip=True) if title_el
                                     else card.get_text(strip=True)[:60])
                            uid = href or title
                            if uid in seen:
                                continue
                            seen.add(uid)
                            full_url = (href if href.startswith("http")
                                        else f"https://www.malt.be{href}")
                            listings.append({
                                "external_id": _make_id("malt", uid),
                                "source": "malt",
                                "title": title,
                                "company": None,
                                "location": "Belgium",
                                "description": card.get_text(separator=" ", strip=True)[:800],
                                "url": full_url,
                                "raw_data": {"search": term},
                            })
                        print(f"Malt '{term}': {len(cards)} cards")
                    except Exception as e:
                        print(f"Malt page error for '{term}': {e}")
                await browser.close()
        except ImportError:
            print("Playwright not installed — skipping Malt")
        except Exception as e:
            print(f"Malt collector error: {e}")
        return listings

    # Run async scraper in a fresh event loop (avoids conflict with FastAPI)
    try:
        loop = asyncio.new_event_loop()
        return loop.run_until_complete(_scrape())
    finally:
        loop.close()


# ─── Stepstone.be ─────────────────────────────────────────────────────────────

def collect_stepstone() -> list[dict]:
    """
    Scrape Stepstone.be listings.
    """
    listings = []
    seen = set()

    with httpx.Client(headers=HEADERS, timeout=20, follow_redirects=True) as client:
        for term in ["agile coach", "scrum master"]:
            url = f"https://www.stepstone.be/jobs/{term.replace(' ', '-')}?radius=30&sort=2"
            try:
                r = client.get(url)
                if r.status_code != 200:
                    print(f"Stepstone '{term}': HTTP {r.status_code}")
                    continue

                soup = BeautifulSoup(r.text, "html.parser")

                # Stepstone uses various selectors across versions
                cards = soup.select(
                    "article[data-at='job-item'], "
                    "article.sc-bYUMXS, "
                    "li[class*='JobListItem'], "
                    "div[class*='jobCard'], "
                    "article"
                )

                for card in cards:
                    title_el = card.select_one(
                        "h2[data-at='job-item-title'], h2, h3, "
                        "[class*='title'], [class*='Title']"
                    )
                    link_el = card.select_one("a[href*='/jobs/'], a[href*='/job/'], a")
                    company_el = card.select_one(
                        "[data-at='job-item-company-name'], "
                        "[class*='company'], [class*='Company']"
                    )

                    if not title_el or not link_el:
                        continue

                    href = link_el.get("href", "")
                    if href in seen:
                        continue
                    seen.add(href)

                    full_url = (href if href.startswith("http")
                                else f"https://www.stepstone.be{href}")

                    listings.append({
                        "external_id": _make_id("stepstone", full_url),
                        "source": "stepstone",
                        "title": title_el.get_text(strip=True),
                        "company": company_el.get_text(strip=True) if company_el else None,
                        "location": "Belgium",
                        "description": card.get_text(separator=" ", strip=True)[:800],
                        "url": full_url,
                        "raw_data": {"search": term},
                    })

                print(f"Stepstone '{term}': {len(cards)} cards")

            except Exception as e:
                print(f"Stepstone error: {e}")

    return listings


# ─── Direct outreach ──────────────────────────────────────────────────────────

def collect_outreach_targets() -> list[dict]:
    from app.database import get_outreach_targets
    return get_outreach_targets(status="not_contacted")


# ─── Master collector ─────────────────────────────────────────────────────────

def collect_all() -> dict:
    print("Starting collection from all sources...")
    all_listings = []

    for name, fn in [
        ("LinkedIn", collect_linkedin),
        ("Freelance.be", collect_freelance_be),
        ("Références.be", collect_references_be),
        ("Malt", collect_malt),
        ("Stepstone", collect_stepstone),
    ]:
        try:
            results = fn()
            print(f"  {name}: {len(results)} listings")
            all_listings.extend(results)
        except Exception as e:
            print(f"  {name}: FAILED — {e}")

    return {
        "listings": all_listings,
        "outreach_targets": collect_outreach_targets(),
    }
