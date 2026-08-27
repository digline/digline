"""The report: a comparison rendered for the reader who does not read code.

Pure functions — the caller writes the file. Depends on `digline.core` and on
nothing else in digline.
"""

from digline.report import pages
from digline.report.history import CaseEntry, CaseHistory, case_history
from digline.report.pages import (
    VIEW_CSS,
    case_page,
    compare_page,
    fmt3,
    human_time,
    runs_page,
    suspend_page,
    suspension_snippet,
)
from digline.report.render import (
    SECTIONS,
    SUMMARY_OUTCOMES,
    Headline,
    Section,
    artifact_lines,
    diff_lines,
    diff_tally,
    headline,
    render_html,
    summary_lines,
)
from digline.report.text import LOCALES, TEXT, Locale, phrase

__all__ = [
    "LOCALES",
    "VIEW_CSS",
    "CaseEntry",
    "CaseHistory",
    "SECTIONS",
    "SUMMARY_OUTCOMES",
    "TEXT",
    "Headline",
    "Locale",
    "Section",
    "case_history",
    "case_page",
    "compare_page",
    "fmt3",
    "artifact_lines",
    "diff_lines",
    "diff_tally",
    "headline",
    "human_time",
    "pages",
    "phrase",
    "render_html",
    "runs_page",
    "summary_lines",
    "suspend_page",
    "suspension_snippet",
]
