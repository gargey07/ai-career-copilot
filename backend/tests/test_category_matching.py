"""
Category-relevance gate — systemic (all-pairs) regression coverage.

The 2026-07 production incident: a developer's dashboard (Kevin) showed
Product Designer jobs because the old `_GENERIC_ROLE_NOUNS` in
core/matcher.py was derived only from JOB_CATEGORIES' dict KEYS, so
"product" (only ever present inside target_roles labels like "Product
Designer"/"Product Manager") was never excluded. The exact same class of
bug had already been hand-patched once in jobs/fetchers.py's own
_QUALIFIER_WORDS list and never ported here — two independently
maintained word lists drifting apart.

The fix: GENERIC_ROLE_WORDS (core/skill_maps.py) is mechanically derived
from every category's real role vocabulary (label + target_roles) and
shared by both files — a word ambiguous across ANY two categories is
excluded automatically, with no hand-maintained list to keep in sync. The
first test below proves that holds for the ENTIRE taxonomy (every
category vs. every other category's own titles), not just the three
titles actually reported — the founder's explicit ask was "make sure this
never happens to any other profile." A narrower residual gap (a word only
ambiguous because of a user's own free-typed extra target_role, not
because the taxonomy itself considers it generic) is documented, not
silently left unexplained, in
test_word_not_yet_globally_generic_can_still_leak_via_extra_target_role
below — closing it was tried and reverted because it broke common,
correct single-role matches for a much larger population of users.
"""
from __future__ import annotations

import asyncio

import core.matcher as matcher
from core.matcher import _category_relevant, _tokenize, purge_miscategorized_matches
from core.skill_maps import JOB_CATEGORIES, GENERIC_ROLE_WORDS
from jobs.fetchers import _title_matches


def _category_terms_for(category_key: str) -> set[str]:
    """Mirror core.matcher._category_terms for a user whose only category
    and target_roles are this one category's own definition."""
    cat = JOB_CATEGORIES[category_key]
    terms: set[str] = set(_tokenize(category_key.replace("_", " ")))
    for role in cat["target_roles"]:
        terms |= _tokenize(role)
    return {t for t in terms if len(t) >= 2}


def test_no_category_leaks_via_another_categorys_target_role_title():
    """For every ordered pair of DIFFERENT categories (A, B): a job titled
    with one of B's own real target_role phrases must NOT satisfy A's
    category gate. 17 categories x ~5 roles each x 16 other categories =
    over 1,500 checks — a systemic guarantee, not a hand-picked example."""
    leaks = []
    for a_key in JOB_CATEGORIES:
        terms = _category_terms_for(a_key)
        for b_key, b_cat in JOB_CATEGORIES.items():
            if b_key == a_key:
                continue
            for role in b_cat["target_roles"]:
                job = {"title": role, "description": ""}
                if _category_relevant(job, {a_key}, terms):
                    leaks.append((a_key, b_key, role))
    assert leaks == [], f"{len(leaks)} cross-category leak(s), e.g. {leaks[:5]}"


def test_reported_production_leak_titles_rejected_for_developer_profile():
    """The exact three titles from the live bug report, against a plain
    developer profile (job_category=fullstack_developer)."""
    user_categories = {"fullstack_developer"}
    terms = _category_terms_for("fullstack_developer")
    leaked_titles = [
        "Product Designer, Design, Dev, & AI Tools",
        "Manager, Product Design",
        "Product Designer, AI Models",
    ]
    for title in leaked_titles:
        job = {"title": title, "description": "Figma, UX research, 3+ years of UX/UI design experience."}
        assert _category_relevant(job, user_categories, terms) is False, title


def test_legitimate_own_category_matches_unaffected_by_the_fix():
    """The fix must not cost single-role users their obvious, correct
    matches — these must all still pass on title alone."""
    terms = _category_terms_for("fullstack_developer")
    for title in ["Senior Fullstack Developer", "MERN Stack Developer", "Full Stack Developer (Node.js/React)"]:
        job = {"title": title, "description": "Node.js, React, MongoDB."}
        assert _category_relevant(job, {"fullstack_developer"}, terms) is True, title


def test_word_not_yet_globally_generic_can_still_leak_via_extra_target_role():
    """Known, narrower residual gap (documented, not silently accepted):
    GENERIC_ROLE_WORDS only flags a word ambiguous when it appears in 2+
    categories' OWN canonical vocabulary. A word that appears in only ONE
    category there (e.g. "ai", solely from data_scientist's "AI Engineer")
    isn't flagged — so if a user free-types an extra target_role from a
    DIFFERENT category into their profile (a supported feature; the
    target_roles autocomplete draws from every category), that word can
    still pass a single-term title match for an unrelated job that uses it
    decoratively ("... AI Tools"). Tightening the single-term rule to
    close this was tried and reverted: it broke common, obviously-correct
    single-role matches ("Senior Fullstack Developer", "AI Engineer" as an
    exact title) for the much more common case of a user with ONE
    profession — a materially worse trade than this narrower, rarer gap."""
    terms = _category_terms_for("fullstack_developer") | _tokenize("AI Engineer")
    job = {
        "title": "Product Designer, Design, Dev, & AI Tools",
        "description": "Figma, UX research, 3+ years of UX/UI design experience.",
    }
    assert _category_relevant(job, {"fullstack_developer"}, terms) is True  # documents the known gap


def test_own_category_titles_still_pass():
    """The fix must not become so strict it blocks genuinely relevant jobs
    — every category's own target_role phrases must still pass its own
    gate, given a realistic job description (real fetched jobs always have
    one; a real "Design Lead" posting would mention other design-role
    words in its body, same as this synthetic description does)."""
    for key, cat in JOB_CATEGORIES.items():
        terms = _category_terms_for(key)
        description = cat["label"] + " " + " ".join(cat["target_roles"])
        for role in cat["target_roles"]:
            job = {"title": role, "description": description}
            assert _category_relevant(job, {key}, terms) is True, (key, role)


def test_own_category_title_alone_may_need_description_for_generic_labels():
    """Known, narrow trade-off: a title that is ONLY a stopword ("lead")
    plus a single word that's correctly ambiguous across categories
    ("design" — shared by ui_ux_designer's "Design Lead" and
    graphic_designer's own label) has no safe bag-of-words signal left in
    the title alone. Accepting it would require either reintroducing a
    stopword into the discriminator set (recreates the "it"+"data" leak
    this gate already guards against) or trusting a single generic word
    (recreates the "product" leak this whole fix exists to close) — this
    documents the trade-off rather than silently regressing protection.
    A non-empty description (which every real fetched job has) resolves
    it, per test_own_category_titles_still_pass above."""
    terms = _category_terms_for("ui_ux_designer")
    job = {"title": "Design Lead", "description": ""}
    assert _category_relevant(job, {"ui_ux_designer"}, terms) is False


def test_generic_role_words_shared_between_matcher_and_fetchers():
    """The actual root cause was two independently hand-maintained word
    lists drifting apart. Assert there's only one mechanically-derived
    source now, and both modules use it."""
    assert matcher._GENERIC_ROLE_NOUNS is GENERIC_ROLE_WORDS
    assert "product" in GENERIC_ROLE_WORDS
    assert "manager" in GENERIC_ROLE_WORDS
    assert "designer" in GENERIC_ROLE_WORDS


def test_fetch_time_filter_rejects_leak_titles_for_product_manager_query():
    assert _title_matches("Product Designer, AI Models", "Product Manager") is False
    assert _title_matches("Product Designer, Design, Dev, & AI Tools", "Product Manager") is False


def test_fetch_time_filter_every_query_self_matches():
    """Every category's own search_queries must still match a job titled
    exactly that query — the AND-fallback (triggered when every query word
    is independently ambiguous, e.g. 'Product Manager') must never reject
    a job that IS the query."""
    for cat in JOB_CATEGORIES.values():
        for q in cat["search_queries"]:
            assert _title_matches(q, q) is True, q


def test_fetch_time_filter_rejects_unrelated_developer_role():
    assert _title_matches("Backend Developer", "React Developer") is False


# ── purge_miscategorized_matches — self-healing for HISTORICAL leaks ──────────
# The gate only filters NEW candidates; leaked rows that already progressed
# (pdf_failed/emailed, older digest dates) sat on the dashboard forever —
# exactly why Kevin still saw Product Designer cards after the gate fix.
class _Resp:
    def __init__(self, data):
        self.data = data


class _PurgeFakeSupabase:
    """Just enough of the query chain for purge_miscategorized_matches."""

    def __init__(self, rows, select_error=None, delete_error=None):
        self.rows = rows
        self.select_error = select_error
        self.delete_error = delete_error
        self.deleted_ids: list[str] | None = None

    def table(self, name):
        return self

    def select(self, *a, **k):
        self._op = "select"
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, col, val):
        return self

    def in_(self, col, ids):
        self._ids = ids
        return self

    def execute(self):
        if self._op == "select":
            if self.select_error:
                raise self.select_error
            return _Resp(self.rows)
        if self.delete_error:
            raise self.delete_error
        self.deleted_ids = list(self._ids)
        return _Resp([])


def _purge_rows():
    """One leaked design job in every protection state + two keepers."""
    design_job = {"title": "Product Designer, AI Models", "description": "Figma, UX research.", "search_category": "ui_ux_designer"}
    dev_job = {"title": "Senior Fullstack Developer", "description": "Node.js, React.", "search_category": "fullstack_developer"}
    return [
        {"id": "leak-plain", "status": "pdf_failed", "applied_at": None, "application_status": None, "feedback": None, "job_feedback": None, "jobs": design_job},
        {"id": "leak-applied-status", "status": "applied", "applied_at": None, "application_status": None, "feedback": None, "job_feedback": None, "jobs": design_job},
        {"id": "leak-applied-at", "status": "emailed", "applied_at": "2026-07-10", "application_status": None, "feedback": None, "job_feedback": None, "jobs": design_job},
        {"id": "leak-feedback", "status": "emailed", "applied_at": None, "application_status": None, "feedback": None, "job_feedback": "not_relevant", "jobs": design_job},
        {"id": "keep-in-category", "status": "pdf_ready", "applied_at": None, "application_status": None, "feedback": None, "job_feedback": None, "jobs": dev_job},
        {"id": "keep-no-job", "status": "matched", "applied_at": None, "application_status": None, "feedback": None, "job_feedback": None, "jobs": None},
    ]


def _run_purge(db):
    return asyncio.run(purge_miscategorized_matches(
        db, "kevin", {"fullstack_developer"}, _category_terms_for("fullstack_developer"),
    ))


def test_purge_removes_leaked_rows_but_keeps_protected_and_relevant_ones():
    db = _PurgeFakeSupabase(_purge_rows())
    removed = _run_purge(db)
    assert removed == 1
    # Only the plain leaked row goes: applied/feedback rows are protected
    # (user signals), the in-category row passes the gate, and a row whose
    # job can't be loaded is never judged.
    assert db.deleted_ids == ["leak-plain"]


def test_purge_never_blocks_matching_on_select_failure():
    db = _PurgeFakeSupabase([], select_error=RuntimeError("column does not exist"))
    assert _run_purge(db) == 0


def test_purge_never_blocks_matching_on_delete_failure():
    db = _PurgeFakeSupabase(_purge_rows(), delete_error=RuntimeError("permission denied"))
    assert _run_purge(db) == 0


def test_purge_noop_when_everything_is_relevant():
    dev_job = {"title": "Python Developer", "description": "FastAPI.", "search_category": "fullstack_developer"}
    db = _PurgeFakeSupabase([
        {"id": "m1", "status": "emailed", "applied_at": None, "application_status": None, "feedback": None, "job_feedback": None, "jobs": dev_job},
    ])
    assert _run_purge(db) == 0
    assert db.deleted_ids is None  # delete never called
