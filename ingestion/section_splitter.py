"""Detect PIL/SmPC section types from page text.

Works at the page level — each page is annotated with a section_type.
Section type propagates forward: if a page has no recognisable header it
inherits the type from the previous page (handled in annotate_pages).

Strategy
--------
For each page:
1. Detect and skip table-of-contents pages (return 'unknown').
2. Find ALL section-header matches across the page text.
3. Return the section_type of the header that appears FIRST (by character
   position) — so a page that ends with "5. How to store" but starts with
   side-effect content is correctly labelled as 'adverse_effect'.

Supported formats
-----------------
- US FDA OTC Drug Facts     (plain headers: Uses, Warnings, Directions …)
- US FDA Prescribing Info   (numbered ALL-CAPS: 1 INDICATIONS AND USAGE …)
- EMA Package Leaflet       (numbered prose:   1. What X is used for …)

Section types returned
----------------------
indication        — what the drug treats
contraindication  — when not to use
warning           — precautions, special warnings, boxed warnings
adverse_effect    — side effects, undesirable effects
dose              — dosing, administration
interaction       — drug interactions
patient_group     — use in specific populations
storage           — storage / handling
unknown           — no header detected / TOC page
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Table-of-contents detection
# ---------------------------------------------------------------------------
_TOC_MARKERS = re.compile(
    r"(FULL\s+PRESCRIBING\s+INFORMATION\s*:\s*CONTENTS"
    r"|TABLE\s+OF\s+CONTENTS"
    r"|PACKAGE\s+LEAFLET\s*:\s*INFORMATION\s+FOR"
    r"|CONTENTS\s+OF\s+THE\s+PACK\s+AND\s+OTHER\s+INFORMATION)",
    re.I,
)

# A TOC page typically lists ≥4 different numbered section titles in sequence.
_TOC_SECTION_LINE = re.compile(
    r"^\s*\d+[\.\s]+[A-Z][A-Za-z\s]+$", re.M
)


def _is_toc_page(text: str) -> bool:
    if _TOC_MARKERS.search(text):
        return True
    # Heuristic: ≥5 short numbered lines → likely a TOC
    numbered_lines = _TOC_SECTION_LINE.findall(text)
    return len(numbered_lines) >= 5


# ---------------------------------------------------------------------------
# Section header patterns
# Each entry: (compiled_regex, section_type)
# All patterns are searched; the one with the EARLIEST match position wins.
# ---------------------------------------------------------------------------

_ALL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # ---- EMA Package Leaflet (numbered prose) --------------------------------
    (re.compile(r"^\s*\d+[\.\)]\s+What\s+\S+\s+is\s+and\s+what\s+it\s+is\s+used\s+for\b", re.M | re.I), "indication"),
    (re.compile(r"^\s*\d+[\.\)]\s+What\s+you\s+need\s+to\s+know\b", re.M | re.I), "warning"),
    (re.compile(r"^\s*\d+[\.\)]\s+How\s+to\s+take\b", re.M | re.I), "dose"),
    (re.compile(r"^\s*\d+[\.\)]\s+Possible\s+side\s+effects?\b", re.M | re.I), "adverse_effect"),
    (re.compile(r"^\s*\d+[\.\)]\s+How\s+to\s+store\b", re.M | re.I), "storage"),
    (re.compile(r"^\s*\d+[\.\)]\s+Contents\s+of\s+the\s+pack\b", re.M | re.I), "storage"),

    # ---- US FDA OTC Drug Facts (plain headers on their own line) ------------
    (re.compile(r"^\s*Uses?\s*$", re.M | re.I), "indication"),
    (re.compile(r"^\s*Purpose[s:]?\s*$", re.M | re.I), "indication"),
    (re.compile(r"^\s*Directions?\s*$", re.M | re.I), "dose"),
    (re.compile(r"^\s*Do\s+not\s+use\b", re.M | re.I), "contraindication"),
    (re.compile(r"^\s*Warnings?\s*$", re.M | re.I), "warning"),
    (re.compile(r"^\s*Ask\s+a\s+doctor\s+before\s+use\b", re.M | re.I), "warning"),
    (re.compile(r"^\s*Stop\s+use\s+and\s+ask\b", re.M | re.I), "warning"),
    (re.compile(r"^\s*When\s+using\s+this\s+product\b", re.M | re.I), "warning"),
    (re.compile(r"^\s*Side\s+effects?\b", re.M | re.I), "adverse_effect"),
    (re.compile(r"^\s*Other\s+information\s*$", re.M | re.I), "storage"),
    (re.compile(r"^\s*Inactive\s+ingredients?\s*$", re.M | re.I), "storage"),

    # ---- US FDA Prescribing Information (numbered ALL-CAPS) -----------------
    (re.compile(r"^\s*\d+\s+INDICATIONS?\s+AND\s+USAGE\b", re.M | re.I), "indication"),
    (re.compile(r"^\s*\d+\s+DOSAGE\s+AND\s+ADMINISTRATION\b", re.M | re.I), "dose"),
    (re.compile(r"^\s*\d+\s+CONTRAINDICATIONS?\b", re.M | re.I), "contraindication"),
    (re.compile(r"^\s*\d+\s+WARNINGS?\s+AND\s+PRECAUTIONS?\b", re.M | re.I), "warning"),
    (re.compile(r"^\s*\d+\s+WARNINGS?\b", re.M | re.I), "warning"),
    (re.compile(r"^\s*\d+\s+PRECAUTIONS?\b", re.M | re.I), "warning"),
    (re.compile(r"^\s*\d+\s+ADVERSE\s+REACTIONS?\b", re.M | re.I), "adverse_effect"),
    (re.compile(r"^\s*\d+\s+UNDESIRABLE\s+EFFECTS?\b", re.M | re.I), "adverse_effect"),
    (re.compile(r"^\s*\d+\s+DRUG\s+INTERACTIONS?\b", re.M | re.I), "interaction"),
    (re.compile(r"^\s*\d+\s+USE\s+IN\s+SPECIFIC\s+POPULATIONS?\b", re.M | re.I), "patient_group"),
    (re.compile(r"^\s*\d+\s+SPECIAL\s+POPULATIONS?\b", re.M | re.I), "patient_group"),
    (re.compile(r"^\s*\d+\s+HOW\s+SUPPLIED\b", re.M | re.I), "storage"),
    (re.compile(r"^\s*\d+\s+STORAGE\s+AND\s+HANDLING\b", re.M | re.I), "storage"),

    # ---- Boxed WARNING (all formats) — only counts if in first 300 chars ----
    # handled separately below
]

_BOXED_WARNING = re.compile(r"\bWARNING\s*:", re.I)


def detect_page_section(text: str, doc_type: str = "") -> str:  # noqa: ARG001
    """Return the section_type for a single page of text.

    Uses earliest-match-wins strategy across all pattern sets.

    Args:
        text:     Raw page text as produced by PyPDFLoader.
        doc_type: Metadata doc_type ('PIL', 'SmPC', 'Unknown' …).
                  Accepted for API consistency; currently unused.

    Returns:
        One of: indication, contraindication, warning, adverse_effect,
                dose, interaction, patient_group, storage, unknown.
    """
    if not text or not text.strip():
        return "unknown"

    if _is_toc_page(text):
        return "unknown"

    # Collect (match_start_position, section_type) for every pattern that hits
    candidates: list[tuple[int, str]] = []

    for pattern, section_type in _ALL_PATTERNS:
        m = pattern.search(text)
        if m:
            candidates.append((m.start(), section_type))

    # Boxed WARNING only counts if it appears in the first 300 characters
    bw = _BOXED_WARNING.search(text[:300])
    if bw:
        candidates.append((bw.start(), "warning"))

    if not candidates:
        return "unknown"

    # Earliest header position wins
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def annotate_pages(
    pages: list,  # list[langchain_core.documents.Document]
    propagate: bool = True,
) -> list:
    """Annotate a list of page-level Documents with section_type metadata.

    Args:
        pages:     Output of load_single_pdf() or load_pdfs() — page-level Documents.
        propagate: If True, pages with 'unknown' section inherit the previous page's type.
                   Simulates sections spanning multiple pages.

    Returns:
        The same list with section_type added to each document's metadata (in-place).
    """
    last_known = "unknown"

    for doc in pages:
        section_type = detect_page_section(
            doc.page_content,
            doc.metadata.get("doc_type", ""),
        )

        if propagate and section_type == "unknown" and last_known != "unknown":
            section_type = last_known
        elif section_type != "unknown":
            last_known = section_type

        doc.metadata["section_type"] = section_type

    return pages
