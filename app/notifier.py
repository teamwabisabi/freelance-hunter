"""
Email notifications via Resend.
Sends daily digest of new high-scoring matches.
"""

import os
import resend
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

resend.api_key = os.environ.get("RESEND_API_KEY", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "jobs@yourdomain.com")
EMAIL_TO = os.environ.get("EMAIL_TO", "")
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")


def send_digest(new_listings: list[dict], new_outreach_drafts: int = 0):
    """
    Send a digest email with new high-scoring job matches.
    """
    if not new_listings and new_outreach_drafts == 0:
        print("No new listings to notify about.")
        return

    subject = f"🎯 {len(new_listings)} new mission match{'es' if len(new_listings) != 1 else ''} — Freelance Hunter"

    html_listings = ""
    for listing in new_listings:
        score_color = "#22c55e" if listing.get("match_score", 0) >= 8 else "#f59e0b"
        html_listings += f"""
        <div style="border:1px solid #e5e7eb; border-radius:8px; padding:16px; margin-bottom:16px;">
            <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                <div>
                    <h3 style="margin:0 0 4px 0; font-size:16px;">{listing.get('title', 'Unknown')}</h3>
                    <p style="margin:0; color:#6b7280; font-size:14px;">
                        {listing.get('company', 'Unknown')} · {listing.get('location', '')} · {listing.get('source', '')}
                    </p>
                </div>
                <span style="background:{score_color}; color:white; padding:4px 10px; border-radius:20px; font-weight:bold; font-size:14px; white-space:nowrap;">
                    {listing.get('match_score', 0)}/10
                </span>
            </div>
            <p style="margin:12px 0 8px 0; font-size:14px; color:#374151;">
                {listing.get('match_reasoning', '')}
            </p>
            <a href="{BASE_URL}/dashboard/listing/{listing.get('id')}" 
               style="display:inline-block; background:#1d4ed8; color:white; padding:8px 16px; border-radius:6px; text-decoration:none; font-size:14px;">
                Review &amp; Edit Application →
            </a>
        </div>
        """

    outreach_section = ""
    if new_outreach_drafts > 0:
        outreach_section = f"""
        <div style="background:#f0fdf4; border:1px solid #bbf7d0; border-radius:8px; padding:16px; margin-bottom:16px;">
            <p style="margin:0; font-size:14px; color:#166534;">
                📬 <strong>{new_outreach_drafts} outreach email draft{'s' if new_outreach_drafts != 1 else ''}</strong> 
                ready for review in the dashboard.
            </p>
            <a href="{BASE_URL}/dashboard/outreach" 
               style="display:inline-block; margin-top:8px; background:#16a34a; color:white; padding:8px 16px; border-radius:6px; text-decoration:none; font-size:14px;">
                Review Outreach Drafts →
            </a>
        </div>
        """

    html = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width:600px; margin:0 auto; padding:24px; color:#111;">
        <h2 style="margin:0 0 8px 0;">🎯 Freelance Hunter — Daily Digest</h2>
        <p style="color:#6b7280; margin:0 0 24px 0;">{datetime.now().strftime('%A %d %B %Y')}</p>
        
        {outreach_section}
        
        <h3 style="margin:0 0 16px 0; font-size:15px; text-transform:uppercase; letter-spacing:0.05em; color:#6b7280;">
            New Matches (score ≥ 7)
        </h3>
        
        {html_listings if html_listings else '<p style="color:#6b7280;">No new matches today.</p>'}
        
        <hr style="border:none; border-top:1px solid #e5e7eb; margin:24px 0;">
        <p style="font-size:12px; color:#9ca3af;">
            <a href="{BASE_URL}/dashboard" style="color:#6b7280;">Open full dashboard</a> · 
            Freelance Hunter by Wabi Sabi Consulting
        </p>
    </body>
    </html>
    """

    try:
        params = {
            "from": EMAIL_FROM,
            "to": [EMAIL_TO],
            "subject": subject,
            "html": html,
        }
        resend.Emails.send(params)
        print(f"Digest sent to {EMAIL_TO} with {len(new_listings)} listings.")
    except Exception as e:
        print(f"Failed to send digest email: {e}")
