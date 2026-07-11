"""
Suggestions API — backs the search-select fields in onboarding
────────────────────────────────────────────────────────────────
Static-taxonomy lookups (core/skill_maps.py) — no AI call, no DB
query, just an in-memory prefix/substring search. Fast enough to hit
on every keystroke.
"""
from fastapi import APIRouter, Query

from core.locations import suggest_locations
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


@router.get("/locations")
async def suggest_locations_route(q: str = Query("", max_length=100)):
    """Powers 'Preferred locations' — cities/countries/Remote variants
    from the same taxonomy jobs/fetchers.py uses to steer actual fetching,
    so a suggestion picked here is guaranteed resolvable at fetch time."""
    return {"results": suggest_locations(q)}
