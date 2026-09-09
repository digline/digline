"""The report: a comparison rendered for the reader who does not read code.

Pure functions — the caller writes the file. Depends on `digline.core` and on
nothing else in digline.
"""

from digline.report import diff, pages
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
    RUN_SECTIONS,
    SECTIONS,
    SUMMARY_OUTCOMES,
    ErroredVerdict,
    Headline,
    RunTally,
    Section,
    artifact_lines,
    config_changes,
    config_lines,
    diff_lines,
    diff_tally,
    errored_verdicts,
    headline,
    render_html,
    render_run_html,
    run_tally,
    summary_lines,
    suspended_cases,
    unjudged_cases,
)
from digline.report.text import LOCALES, TEXT, Locale, phrase

__all__ = [
    "LOCALES",
    "VIEW_CSS",
    "CaseEntry",
    "CaseHistory",
    "RUN_SECTIONS",
    "SECTIONS",
    "SUMMARY_OUTCOMES",
    "TEXT",
    "ErroredVerdict",
    "Headline",
    "Locale",
    "RunTally",
    "Section",
    "case_history",
    "diff",
    "case_page",
    "config_changes",
    "config_lines",
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
    "render_run_html",
    "errored_verdicts",
    "run_tally",
    "runs_page",
    "summary_lines",
    "suspend_page",
    "suspended_cases",
    "suspension_snippet",
    "unjudged_cases",
]
