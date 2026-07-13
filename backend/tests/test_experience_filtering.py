"""
Experience filtering — regex coverage, seniority inference, and the
end-to-end gate + soft-demotion behavior.

2026-07 production report: a user who selected "0-1 Year Experience"
still saw jobs requiring "7+ years". The gate math itself was already
correct (fresher/entry cap = 12 months + 12 months tolerance = 24-month
ceiling — matcher.py); the leak was upstream, in how often a job's real
experience requirement never got recognized at all:

1. experience_months_from_text only counted a "N years" mention with the
   literal word "experience"/"exp" nearby — missed "5+ years in a similar
   role", "minimum 5 years", spelled-out numbers, etc.
2. seniority_level was only ever set by ONE of five job sources, and that
   source defaulted every title without "senior"/"lead" to a fake "mid" —
   which matcher.py's band-distance check treats as close enough to pass
   a fresher through.

These tests cover the fix at each layer.
"""
from __future__ import annotations

from core.matcher import _apply_experience_penalty, _experience_ok
from jobs.fetchers import experience_months_from_text, infer_seniority_level, normalize_job


# ── experience_months_from_text — widened phrasing coverage ───────────────────
def test_parses_years_without_the_word_experience_nearby():
    assert experience_months_from_text("5+ years in a similar role") == 60
    assert experience_months_from_text("3-5 years building production systems") == 36
    assert experience_months_from_text("Minimum 5 years required for this role") == 60
    assert experience_months_from_text("Must have 2+ years hands-on with AWS") == 24
    assert experience_months_from_text("candidates with 4 years background in fintech preferred") == 48


def test_parses_spelled_out_numbers():
    assert experience_months_from_text("at least three years of professional software development") == 36


def test_parses_years_separated_from_experience_by_more_than_60_chars():
    text = "Requirements:\n- 5+ years\n- Strong communication\n- Prior experience with distributed systems"
    assert experience_months_from_text(text) == 60


def test_still_parses_original_supported_phrasings():
    assert experience_months_from_text("7+ years of experience required") == 84
    assert experience_months_from_text("5+ yrs exp needed") == 60


def test_still_rejects_company_age_and_version_numbers():
    assert experience_months_from_text("We are a company founded 25 years ago serving clients worldwide") is None
    assert experience_months_from_text("This product has been trusted by customers for 15 years") is None
    assert experience_months_from_text("React 18 and Python 3.10 required") is None


def test_empty_and_no_match():
    assert experience_months_from_text("") is None
    assert experience_months_from_text("Great team, great culture, fully remote.") is None


# ── infer_seniority_level — honest inference, no fake defaults ────────────────
def test_infers_senior_from_various_signals():
    for title in ["Senior Software Engineer", "Sr. Backend Developer", "Staff Engineer",
                  "Principal Architect", "Software Engineer III"]:
        assert infer_seniority_level(title) == "senior", title


def test_infers_lead():
    assert infer_seniority_level("Tech Lead") == "lead"


def test_infers_entry_from_various_signals():
    for title in ["Junior Developer", "Jr. Frontend Developer", "Software Engineer Intern",
                  "Fresher - Backend Developer", "Entry Level Software Engineer", "Software Engineer I"]:
        assert infer_seniority_level(title) == "entry", title


def test_returns_none_not_a_fake_mid_for_plain_titles():
    """The actual root cause: a previous version defaulted every
    unmatched title to "mid", and matcher.py's band-distance check
    treats "mid" as close enough to pass a fresher through — an honest
    None correctly falls to the (still permissive, but at least
    documented) unknown-data policy instead of asserting false data."""
    for title in ["Software Engineer", "Backend Developer", "Software Engineer II", "Product Designer"]:
        assert infer_seniority_level(title) is None, title


def test_infer_seniority_handles_empty():
    assert infer_seniority_level("") is None
    assert infer_seniority_level(None) is None


# ── normalize_job — universal wiring, not just JSearch ─────────────────────────
def test_normalize_job_infers_seniority_for_every_source():
    job = normalize_job(
        source="adzuna", external_id="1", title="Senior Backend Developer",
        company="Acme", location="Remote", description="", source_url="http://x",
    )
    assert job["seniority_level"] == "senior"


def test_normalize_job_leaves_seniority_none_when_title_has_no_signal():
    job = normalize_job(
        source="remotive", external_id="2", title="Backend Developer",
        company="Acme", location="Remote", description="", source_url="http://x",
    )
    assert job["seniority_level"] is None


def test_normalize_job_respects_explicit_seniority_override():
    job = normalize_job(
        source="jsearch", external_id="3", title="Backend Developer",
        company="Acme", location="Remote", description="", source_url="http://x",
        seniority_level="mid",
    )
    assert job["seniority_level"] == "mid"


# ── End-to-end gate: the exact reported scenario ───────────────────────────────
def test_plainly_titled_high_experience_job_now_rejected_for_fresher():
    """The reported bug, reproduced and fixed: a job that requires 7 years
    but phrases it without "experience" nearby, titled plainly (no
    "senior" in the title) — previously invisible to both the months
    parser and the seniority fallback, now caught by the widened regex."""
    description = "You'll thrive here with 7+ years in a similar engineering role, owning systems end to end."
    job = normalize_job(
        source="adzuna", external_id="4", title="Backend Developer",
        company="Acme", location="Remote", description=description, source_url="http://x",
    )
    assert job["required_experience_months"] == 84
    assert _experience_ok(job, "fresher") is False


def test_plainly_titled_job_with_truly_no_signal_still_passes_but_is_demoted():
    """Genuinely unrecoverable case (no years mentioned anywhere, generic
    title) — matcher.py's documented "unknown is not disqualified" policy
    still applies (never hard-excluded), but it should no longer rank
    equally with jobs we're confident are in-band."""
    job = normalize_job(
        source="remotive", external_id="5", title="Backend Developer",
        company="Acme", location="Remote", description="Great team, fully remote, flexible hours.",
        source_url="http://x",
    )
    assert job["required_experience_months"] is None
    assert job["seniority_level"] is None
    assert _experience_ok(job, "fresher") is True  # not excluded

    confirmed_inband = {**job, "id": "inband", "match_score": 0.9, "required_experience_months": 6}
    unknown = {**job, "id": "unknown", "match_score": 0.9}
    result = _apply_experience_penalty([confirmed_inband, unknown], "fresher")
    by_id = {j["id"]: j["match_score"] for j in result}
    assert by_id["inband"] == 0.9  # untouched
    assert by_id["unknown"] < by_id["inband"]  # demoted, still present


def test_unknown_penalty_does_not_apply_to_senior_users():
    """The soft demotion is specifically for the bottom band — a senior
    user's own jobs shouldn't be penalized just for lacking data."""
    job = {"id": "unknown", "match_score": 0.9, "required_experience_months": None, "seniority_level": None}
    result = _apply_experience_penalty([dict(job)], "senior")
    assert result[0]["match_score"] == 0.9


# ── Tolerance boundary (2026-07 follow-up report) ──────────────────────────────
# The gate math was correct but too generous: with the old 12-month
# tolerance, a fresher's ceiling was top(12) + tolerance(12) = 24 months —
# exactly a "2-5 years" job's parsed FLOOR (experience_months_from_text
# takes the lowest number in a range). That's not a parsing bug like the
# three previous rounds (regex gaps / missing seniority data / no AI
# fallback) — the number was being read correctly and the gate was doing
# exactly the math it's written to do; the tolerance itself was just too
# loose. Tightened to 0: the ceiling is now exactly each band's own top.
def test_two_to_five_year_job_rejected_for_fresher():
    """The exact reported symptom: a 0-1 year user still seeing '2-5
    year' postings. Floor = 24 months (min of the range)."""
    job = {"required_experience_months": 24}
    assert _experience_ok(job, "fresher") is False
    assert _experience_ok(job, "entry") is False


def test_one_to_two_year_job_still_passes_for_fresher():
    """Zero tolerance must not become negative tolerance — a job whose
    floor exactly equals the user's own band top ("1-2 years" = 12-month
    floor for a fresher, whose top is also 12) still passes."""
    job = {"required_experience_months": 12}
    assert _experience_ok(job, "fresher") is True


def test_tolerance_boundary_also_tightened_for_junior_and_mid():
    # junior top=36: a job requiring exactly 36 months still passes; one
    # requiring 42 (previously inside the old 12-month tolerance) no longer does.
    assert _experience_ok({"required_experience_months": 36}, "junior") is True
    assert _experience_ok({"required_experience_months": 42}, "junior") is False
    # mid top=60: same pattern.
    assert _experience_ok({"required_experience_months": 60}, "mid") is True
    assert _experience_ok({"required_experience_months": 66}, "mid") is False
