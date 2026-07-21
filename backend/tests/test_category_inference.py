"""
infer_category_from_roles / resolve_user_category — the fix for a user
reaching the pipeline with an EMPTY job_category but real target_roles
(2026-07: Vini Jain, category "(none set)", HR roles, zero matches). An
empty category used to default every downstream step to ui_ux_designer.
"""
from __future__ import annotations

from core.skill_maps import infer_category_from_roles, resolve_user_category
from core.matcher import _user_categories


def test_infer_hr_from_roles():
    assert infer_category_from_roles(["HR Executive", "Recruiter", "HR Generalist"]) == "hr_recruiter"


def test_infer_backend_from_roles():
    assert infer_category_from_roles(["Backend Developer", "Python Developer"]) == "backend_developer"


def test_infer_none_when_ambiguous_or_empty():
    # No roles -> None (never guess). A lone generic word can't decide it.
    assert infer_category_from_roles([]) is None
    assert infer_category_from_roles(["Manager"]) is None


def test_resolve_prefers_stored_category():
    # A real stored category always wins over inference.
    user = {"job_category": "backend_developer", "target_roles": ["HR Executive"]}
    assert resolve_user_category(user) == "backend_developer"


def test_resolve_infers_when_category_blank():
    user = {"job_category": "", "target_roles": ["HR Executive", "Recruiter"]}
    assert resolve_user_category(user) == "hr_recruiter"


def test_user_categories_uses_inference_for_blank_category():
    # The matcher's gate must see HR for a blank-category HR user, not an
    # empty set (which passes zero jobs).
    user = {"job_category": "", "target_roles": ["HR Executive", "Recruiter"], "secondary_categories": []}
    assert _user_categories(user) == {"hr_recruiter"}


def test_user_categories_blank_and_no_roles_is_empty():
    user = {"job_category": "", "target_roles": [], "secondary_categories": []}
    assert _user_categories(user) == set()
