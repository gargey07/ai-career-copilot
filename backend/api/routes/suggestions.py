"""
Suggestions API — backs the search-select fields in onboarding
────────────────────────────────────────────────────────────────
Static-taxonomy lookups (core/skill_maps.py) — no AI call, no DB
query, just an in-memory prefix/substring search. Fast enough to hit
on every keystroke.
"""
from fastapi import APIRouter, Query

from core.skill_maps import all_categories, suggest

router = APIRouter()


@router.get("/roles")
async def suggest_roles(q: str = Query("", max_length=100)):
    return {"results": suggest("roles", q)}


@router.get("/skills")
async def suggest_skills(q: str = Query("", max_length=100)):
    return {"results": suggest("skills", q)}


@router.get("/tools")
async def suggest_tools(q: str = Query("", max_length=100)):
    return {"results": suggest("tools", q)}


@router.get("/categories")
async def suggest_categories():
    """Powers the job-category tile grid on the onboarding form."""
    return {"results": all_categories()}
