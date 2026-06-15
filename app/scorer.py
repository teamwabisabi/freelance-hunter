"""
Claude-powered job matching and application drafting.
"""

import os
import json
from datetime import datetime, timezone
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

client = Anthropic()

# Load profile once at module level
_profile_path = os.path.join(os.path.dirname(__file__), "profile.md")
with open(_profile_path, "r") as f:
    PROFILE = f.read()


def score_and_draft(listing: dict) -> dict:
    """
    Given a job listing dict, return scoring + draft application from Claude.
    Returns a dict with: match_score, match_reasoning, relevant_experiences,
    concerns, draft_cover_letter, recommended_cv_variant
    """

    job_text = f"""
Title: {listing.get('title', 'Unknown')}
Company: {listing.get('company', 'Unknown')}
Location: {listing.get('location', 'Unknown')}
Source: {listing.get('source', 'Unknown')}

Description:
{listing.get('description', 'No description available')}
"""

    prompt = f"""You are helping Dries Bellen, a Belgian freelance Agile Coach and Scrum Master, 
evaluate a job listing and draft a tailored application.

## Dries's Profile
{PROFILE}

## Job Listing
{job_text}

## Your Task
Analyse the fit between Dries and this role. Respond ONLY with a valid JSON object 
(no markdown, no preamble) with exactly these fields:

{{
  "match_score": <integer 0-10>,
  "match_reasoning": "<2-3 sentences explaining the score>",
  "relevant_experiences": "<which specific missions/skills from Dries's profile are most relevant>",
  "concerns": "<honest gaps or mismatches, or 'None' if none>",
  "draft_cover_letter": "<a tailored, natural cover letter in the language of the job posting (Dutch/French/English). 3-4 paragraphs. First person. Do not be generic.>",
  "recommended_cv_variant": "<which CV variant to use: 'AgileCoach' for coaching-heavy roles, 'ScrumMaster' for team-level SM roles, 'Transformation' for large-scale change roles>"
}}

Scoring guide:
- 9-10: Near-perfect fit, sector match, right seniority level
- 7-8: Strong fit, minor gaps
- 5-6: Partial fit, worth reviewing but weaker match
- Below 5: Poor fit, do not surface
"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text.strip()
    
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback if Claude adds markdown fences despite instructions
        import re
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            result = json.loads(match.group())
        else:
            result = {
                "match_score": 0,
                "match_reasoning": "Failed to parse Claude response",
                "relevant_experiences": "",
                "concerns": "Parsing error",
                "draft_cover_letter": "",
                "recommended_cv_variant": "AgileCoach"
            }

    result["scored_at"] = datetime.now(timezone.utc).isoformat()
    return result


def draft_outreach_email(target: dict) -> str:
    """
    Draft a proactive cold outreach email for a direct target company.
    """
    prompt = f"""You are helping Dries Bellen write a proactive cold outreach email 
to a company he wants to approach for a freelance Agile Coach / Scrum Master mission.

## Dries's Profile
{PROFILE}

## Target Company
Company: {target.get('company_name')}
Sector: {target.get('sector')}
Contact name: {target.get('contact_name') or 'Unknown (address generically)'}
Notes: {target.get('notes') or 'No specific notes'}

## Instructions
Write a concise, professional cold outreach email in Dutch (default for Belgian companies 
unless the company is clearly French-speaking). 
- 3 short paragraphs maximum
- Do not be generic or salesy
- Reference Dries's relevant sector experience where applicable
- End with a low-friction call to action (e.g. a brief call)
- Subject line included

Respond with ONLY a JSON object:
{{
  "subject": "<email subject>",
  "body": "<email body, use \\n for line breaks>"
}}
"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text.strip()
    try:
        result = json.loads(raw)
        return result
    except json.JSONDecodeError:
        return {
            "subject": f"Freelance Agile Coach / Scrum Master — Dries Bellen",
            "body": "Error generating email. Please draft manually."
        }
