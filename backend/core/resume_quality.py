"""
Resume Quality Checker — T-009
────────────────────────────────────────────────────────
Validates an AI-generated resume against a quality checklist
BEFORE sending to PDF generation.

Blocks PDFs for resumes that are:
  - Too short (< 150 words → probably truncated)
  - Missing key sections (Summary, Experience, Skills, Education)
  - Containing forbidden phrases (hallucinations, template artifacts)
  - Identical to the original resume (optimizer did nothing)

Returns a QualityResult with pass/fail and a list of issues.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ── Required resume sections ──────────────────────────────────────────────────
REQUIRED_SECTIONS = ["summary", "experience", "skills", "education"]

# ── Forbidden phrases — hallucinations / template artifacts ───────────────────
FORBIDDEN_PHRASES = [
    "[your name]",
    "[company name]",
    "[insert",
    "lorem ipsum",
    "as an ai",
    "i cannot",
    "i'm sorry",
    "i apologize",
    "unfortunately, i",
    "as a language model",
    "i don't have information",
]

# ── Thresholds ────────────────────────────────────────────────────────────────
MIN_WORD_COUNT   = 150    # below this → probably truncated
MIN_CHANGED_PCT  = 10.0   # resume must differ by at least 10% from original


@dataclass
class QualityResult:
    passed: bool
    score: int               # 0-100
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        status = "✅ PASS" if self.passed else "❌ FAIL"
        lines = [f"{status} (score: {self.score}/100)"]
        for issue in self.issues:
            lines.append(f"  ✗ {issue}")
        for warning in self.warnings:
            lines.append(f"  ⚠ {warning}")
        return "\n".join(lines)


def _word_count(text: str) -> int:
    return len(text.split())


def _similarity_pct(original: str, optimized: str) -> float:
    """Rough word-level overlap percentage (0=totally different, 100=identical)."""
    orig_words  = set(original.lower().split())
    opt_words   = set(optimized.lower().split())
    if not orig_words:
        return 0.0
    overlap = orig_words & opt_words
    return round(len(overlap) / len(orig_words) * 100, 1)


def check_resume_quality(
    optimized_resume: str,
    original_resume: str = "",
    job_title: str = "",
) -> QualityResult:
    """
    Run the quality checklist on an AI-generated resume.

    Args:
        optimized_resume: The AI output to check
        original_resume:  The user's original resume (for similarity check)
        job_title:        Used in log messages only

    Returns:
        QualityResult with passed=True/False and list of issues
    """
    issues: list[str]   = []
    warnings: list[str] = []
    score = 100

    text_lower = optimized_resume.lower().strip()
    tag = f"[{job_title}] " if job_title else ""

    # ── Check 1: Minimum word count ───────────────────────────────────────────
    wc = _word_count(optimized_resume)
    if wc < MIN_WORD_COUNT:
        issues.append(f"Too short: only {wc} words (minimum {MIN_WORD_COUNT})")
        score -= 40
    elif wc < 200:
        warnings.append(f"Resume is short ({wc} words) — may be truncated")
        score -= 10

    # ── Check 2: Required sections present ───────────────────────────────────
    missing = [s for s in REQUIRED_SECTIONS if s not in text_lower]
    if missing:
        issues.append(f"Missing sections: {', '.join(missing).upper()}")
        score -= len(missing) * 10

    # ── Check 3: No forbidden phrases (hallucinations / template junk) ────────
    found_forbidden = [p for p in FORBIDDEN_PHRASES if p in text_lower]
    if found_forbidden:
        issues.append(f"Forbidden phrases detected: {found_forbidden}")
        score -= 30

    # ── Check 4: Resume actually changed from original ────────────────────────
    if original_resume:
        similarity = _similarity_pct(original_resume, optimized_resume)
        change_pct = 100 - similarity
        if change_pct < MIN_CHANGED_PCT:
            issues.append(
                f"Resume unchanged (only {change_pct:.1f}% different from original)"
            )
            score -= 20
        elif change_pct < 20:
            warnings.append(f"Resume only {change_pct:.1f}% different — minimal optimization")
            score -= 5

    # ── Check 5: No markdown artifacts ───────────────────────────────────────
    if re.search(r"\*{2,}|\#{2,}|```", optimized_resume):
        warnings.append("Contains markdown formatting (**, ##, ```) — may look bad in PDF")
        score -= 5

    # ── Check 6: Not empty ───────────────────────────────────────────────────
    if not optimized_resume.strip():
        issues.append("Resume is completely empty")
        score = 0

    score = max(0, min(100, score))
    passed = len(issues) == 0 and score >= 50

    result = QualityResult(passed=passed, score=score, issues=issues, warnings=warnings)

    if passed:
        logger.info(f"   {tag}✅ Quality check passed (score={score}/100)")
    else:
        logger.warning(f"   {tag}❌ Quality check FAILED (score={score}/100): {issues}")

    return result


def gate_pdf_generation(
    optimized_resume: str,
    original_resume: str = "",
    job_title: str = "",
    strict: bool = True,
) -> tuple[bool, QualityResult]:
    """
    Convenience wrapper used by pdf_generator.py before rendering.

    Returns (should_proceed: bool, result: QualityResult)
    In strict mode: blocks PDF if quality check fails.
    In lenient mode: logs warning but still proceeds.
    """
    result = check_resume_quality(optimized_resume, original_resume, job_title)

    if not result.passed and strict:
        logger.warning(f"   🚫 PDF generation blocked by quality gate: {result.issues}")
        return False, result

    return True, result


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    # Test: good resume
    good = """
    SUMMARY
    Experienced UI/UX Designer with 4 years at fintech companies, expert in Figma and user research.

    PROFESSIONAL EXPERIENCE
    Senior Designer at Paytm (2022-2024)
    - Led redesign of checkout flow reducing drop-off by 23%
    - Conducted 50+ user interviews to validate design decisions

    SKILLS
    Figma, Adobe XD, Sketch, Prototyping, User Research, Usability Testing

    EDUCATION
    B.Des Product Design, NID Ahmedabad, 2020
    """

    result = check_resume_quality(good, "Original resume text here", "UI Designer @ Paytm")
    print("Good resume:", result)

    # Test: bad resume
    bad = "Summary: [Your name] is a designer. Skills: design."
    result2 = check_resume_quality(bad, "Original resume text", "Designer")
    print("\nBad resume:", result2)
