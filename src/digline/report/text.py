"""Every visible string of the report, in one place, per locale.

This is the declared exception to the English-everywhere rule. The rule is about
code and runtime strings; the report is a *document with a recipient*, and the
recipient — an end company that does not read code — did not choose English.

Two things are deliberately **not** localized, and the reason is the same for
both: a report is a committed artifact, and two reports of the same run in two
languages must remain comparable line by line.

- **Dates** stay ISO 8601, exactly as they were recorded.
- **Numbers** keep the dot as decimal separator.

Localizing either would produce documents that say the same thing and cannot be
diffed against each other.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

__all__ = ["LOCALES", "MONTHS", "TEXT", "Locale", "phrase", "strings"]

type Locale = Literal["en", "it"]

LOCALES: tuple[Locale, ...] = ("en", "it")

#: Abbreviated month names, per locale, for the *view* only.
#:
#: The report keeps ISO dates and always will: it is a committed artifact and two
#: renderings of one run must diff line by line. A screen is not that. `26 ago
#: 08:51` is what a developer reads at a glance, and the full key underneath —
#: which begins with the ISO instant — is still the fact.
#:
#: A table rather than the `locale` module: `locale.setlocale` is process-global,
#: depends on what the operating system has installed, and would make one
#: function's output depend on state nothing here set.
MONTHS: Mapping[Locale, tuple[str, ...]] = {
    "en": (
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ),
    "it": (
        "gen", "feb", "mar", "apr", "mag", "giu",
        "lug", "ago", "set", "ott", "nov", "dic",
    ),
}  # fmt: skip

TEXT: Mapping[Locale, Mapping[str, str]] = {
    "en": {
        "document.title": "Evaluation report — {suite}",
        "header.tenant": "Customer",
        "header.suite": "Suite",
        "header.environment": "This run",
        "header.baseline_environment": "Reference",
        "header.commit": "Code version",
        "header.dirty": (
            " — uncommitted changes were present, so this run cannot be "
            "reproduced from the repository"
        ),
        "header.redacted": "Contents omitted",
        "header.redacted.value": "This report was produced from redacted data.",
        "answer.question": "Did it get worse?",
        "answer.yes": "Yes",
        "answer.no": "No",
        "fact.worse.none": "Nothing got worse compared with the reference.",
        "fact.worse.one": "1 check got worse compared with the reference.",
        "fact.worse.many": "{count} checks got worse compared with the reference.",
        "fact.unjudged.none": "Every case could be judged.",
        "fact.unjudged.one": "1 case could not be judged.",
        "fact.unjudged.many": "{count} cases could not be judged.",
        "fact.suspended.none": "No case is suspended.",
        "fact.suspended.one": "1 case is suspended.",
        "fact.suspended.many": "{count} cases are suspended.",
        "fact.config.changed": (
            "The configuration changed since the reference, so these numbers "
            "compare different rules."
        ),
        "fact.config.unchanged": "The configuration is the same as the reference.",
        "aggregates.title": "Overall",
        "aggregate.counted": (
            "{considered} counted · {suspended} suspended · {errored} not judged"
        ),
        "column.measure": "Measure",
        "column.result": "Result",
        "scope.run": "whole run",
        "section.regressions": "What got worse",
        "section.unjudged": "What could not be judged",
        "section.suspended": "What is set aside",
        "section.changes": "What was added or removed",
        "section.improvements": "What got better",
        "section.unchanged": "What stayed the same",
        "section.empty": "Nothing in this section.",
        "summary.truncated": (
            "showing the first {shown} of {total}; the full list is in the report"
        ),
        "column.case": "Case",
        "column.check": "Check",
        "column.detail": "What happened",
        "column.reason": "Why",
        "detail.dropped": "Score fell from {before} to {now}.",
        "detail.rose": "Score rose from {before} to {now}.",
        "detail.unchanged": "Score unchanged at {now}.",
        "detail.flipped.worse": "Went from passing to failing ({before} → {now}).",
        "detail.flipped.better": "Went from failing to passing ({before} → {now}).",
        "detail.threshold_moved": (
            " The bar moved from {before_threshold} to {now_threshold}, so this is "
            "a change of rule rather than of behaviour."
        ),
        "detail.new": "Checked here, not present in the reference.",
        "detail.new.errored": ("New here, and the check could not run."),
        "detail.missing": "Present in the reference, not checked here.",
        "detail.errored": "The check could not run.",
        "reason.unavailable": "Not included in this report.",
        "view.title.runs": "Runs — {suite}",
        "view.title.case": "Case {case_id} — {suite}",
        "view.title.suspend": "Suspend {case_id} — {suite}",
        "view.nav.runs": "Runs",
        "view.nav.report": "Report",
        "view.baseline": "baseline",
        "view.column.key": "Run",
        "view.column.aggregate_note": "change against the baseline",
        "view.commit.dirty": "uncommitted changes",
        "view.commit.none": "no git repository",
        "view.promote.selected": "Make the selected run the baseline",
        "view.promote.is_baseline": "already the baseline",
        "view.promote.errored": (
            "{count} case(s) could not be judged, so this run cannot become a "
            "baseline: an error is not a reference."
        ),
        "view.copy_hint": "click the key to select it",
        "view.chip.errored": "{count} not judged",
        "view.copy_snippet": "click the line to select it",
        "view.column.created": "Recorded",
        "view.column.env": "Environment",
        "view.column.commit": "Code version",
        "view.column.cases": "Cases",
        "view.column.run": "Run",
        "view.column.votes": "Votes",
        "view.no_runs": "No run has been recorded yet.",
        "view.no_aggregates": "This suite declares no aggregate.",
        "view.ignored": "Not shown: {note}. Run `digline migrate`.",
        "view.compare.pick": "Compare",
        "view.compare.against": "against",
        "view.compare.go": "Show",
        "view.compare.same": "A run compared with itself has nothing to report.",
        "view.case.absent": "not in this run",
        "view.case.suspended": "set aside",
        "view.case.title": "How {case_id} was judged, oldest first",
        "view.case.votes_note": (
            "For a sampled check the raw votes are shown beneath the combined "
            "score: that is where judge noise is visible."
        ),
        "view.promote.button": "Make this the baseline",
        "view.promote.done": "Baseline set to {run_key}.",
        "view.promote.refused": "Refused: {why}",
        "view.suspend.title": "Set {case_id} aside",
        "view.suspend.reason": "Why is it set aside?",
        "view.suspend.show": "Show the edit",
        "view.suspend.explain": (
            "A suspension lives in the suite, which is code. This page writes "
            "nothing: it produces the line to add, and you commit it — so the "
            "reason travels with the case in the same review as everything else."
        ),
        "view.suspend.needs_reason": (
            "A suspension without a stated reason is a case that disappears "
            "quietly. Write why."
        ),
    },
    "it": {
        "document.title": "Rapporto di valutazione — {suite}",
        "header.tenant": "Cliente",
        "header.suite": "Suite",
        "header.environment": "Questa esecuzione",
        "header.baseline_environment": "Riferimento",
        "header.commit": "Versione del codice",
        "header.dirty": (
            " — erano presenti modifiche non committate, quindi questa "
            "esecuzione non è riproducibile dal repository"
        ),
        "header.redacted": "Contenuti omessi",
        "header.redacted.value": "Questo rapporto è prodotto da dati redatti.",
        "answer.question": "È peggiorato?",
        "answer.yes": "Sì",
        "answer.no": "No",
        "fact.worse.none": "Nulla è peggiorato rispetto al riferimento.",
        "fact.worse.one": "1 controllo è peggiorato rispetto al riferimento.",
        "fact.worse.many": "{count} controlli sono peggiorati rispetto al riferimento.",
        "fact.unjudged.none": "Tutti i casi sono stati giudicati.",
        "fact.unjudged.one": "1 caso non è stato possibile giudicarlo.",
        "fact.unjudged.many": "{count} casi non è stato possibile giudicarli.",
        "fact.suspended.none": "Nessun caso è sospeso.",
        "fact.suspended.one": "1 caso è sospeso.",
        "fact.suspended.many": "{count} casi sono sospesi.",
        "fact.config.changed": (
            "La configurazione è cambiata rispetto al riferimento, quindi questi "
            "numeri confrontano regole diverse."
        ),
        "fact.config.unchanged": "La configurazione è la stessa del riferimento.",
        "aggregates.title": "Nel complesso",
        "aggregate.counted": (
            "{considered} contati · {suspended} sospesi · {errored} non giudicabili"
        ),
        "column.measure": "Misura",
        "column.result": "Risultato",
        "scope.run": "intera esecuzione",
        "section.regressions": "Che cosa è peggiorato",
        "section.unjudged": "Che cosa non è stato possibile giudicare",
        "section.suspended": "Che cosa è messo da parte",
        "section.changes": "Che cosa è stato aggiunto o tolto",
        "section.improvements": "Che cosa è migliorato",
        "section.unchanged": "Che cosa è rimasto uguale",
        "section.empty": "Niente in questa sezione.",
        "summary.truncated": (
            "mostrate le prime {shown} di {total}; l'elenco completo è nel rapporto"
        ),
        "column.case": "Caso",
        "column.check": "Controllo",
        "column.detail": "Che cosa è successo",
        "column.reason": "Perché",
        "detail.dropped": "Il punteggio è sceso da {before} a {now}.",
        "detail.rose": "Il punteggio è salito da {before} a {now}.",
        "detail.unchanged": "Punteggio invariato a {now}.",
        "detail.flipped.worse": "Da superato a non superato ({before} → {now}).",
        "detail.flipped.better": "Da non superato a superato ({before} → {now}).",
        "detail.threshold_moved": (
            " La soglia si è spostata da {before_threshold} a {now_threshold}, "
            "quindi è un cambio di regola e non di comportamento."
        ),
        "detail.new": "Controllato qui, assente nel riferimento.",
        "detail.new.errored": (
            "Nuovo qui, e il controllo non ha potuto essere eseguito."
        ),
        "detail.missing": "Presente nel riferimento, non controllato qui.",
        "detail.errored": "Il controllo non ha potuto essere eseguito.",
        "reason.unavailable": "Non inclusa in questo rapporto.",
        "view.title.runs": "Esecuzioni — {suite}",
        "view.title.case": "Caso {case_id} — {suite}",
        "view.title.suspend": "Sospendi {case_id} — {suite}",
        "view.nav.runs": "Esecuzioni",
        "view.nav.report": "Rapporto",
        "view.baseline": "riferimento",
        "view.column.key": "Esecuzione",
        "view.column.aggregate_note": "variazione rispetto al riferimento",
        "view.commit.dirty": "modifiche non committate",
        "view.commit.none": "nessun repository git",
        "view.promote.selected": "Rendi riferimento l'esecuzione selezionata",
        "view.promote.is_baseline": "è già il riferimento",
        "view.promote.errored": (
            "{count} caso/i non è stato possibile giudicarli, quindi questa "
            "esecuzione non può diventare un riferimento: un errore non è un "
            "riferimento."
        ),
        "view.copy_hint": "clicca la chiave per selezionarla",
        "view.chip.errored": "{count} non giudicati",
        "view.copy_snippet": "clicca la riga per selezionarla",
        "view.column.created": "Registrata",
        "view.column.env": "Ambiente",
        "view.column.commit": "Versione del codice",
        "view.column.cases": "Casi",
        "view.column.run": "Esecuzione",
        "view.column.votes": "Voti",
        "view.no_runs": "Nessuna esecuzione registrata.",
        "view.no_aggregates": "Questa suite non dichiara aggregati.",
        "view.ignored": "Non mostrate: {note}. Esegui `digline migrate`.",
        "view.compare.pick": "Confronta",
        "view.compare.against": "con",
        "view.compare.go": "Mostra",
        "view.compare.same": "Una run confrontata con se stessa non ha nulla da dire.",
        "view.case.absent": "assente in questa run",
        "view.case.suspended": "messo da parte",
        "view.case.title": "Come è stato giudicato {case_id}, dal più vecchio",
        "view.case.votes_note": (
            "Per un controllo campionato i voti grezzi stanno sotto al punteggio "
            "combinato: è lì che il rumore del giudice si vede."
        ),
        "view.promote.button": "Rendi questa il riferimento",
        "view.promote.done": "Riferimento impostato su {run_key}.",
        "view.promote.refused": "Rifiutato: {why}",
        "view.suspend.title": "Metti da parte {case_id}",
        "view.suspend.reason": "Perché viene messo da parte?",
        "view.suspend.show": "Mostra la modifica",
        "view.suspend.explain": (
            "Una sospensione vive nella suite, che è codice. Questa pagina non "
            "scrive nulla: produce la riga da aggiungere, e la committi tu — "
            "così il motivo viaggia col caso nella stessa revisione di tutto "
            "il resto."
        ),
        "view.suspend.needs_reason": (
            "Una sospensione senza motivo dichiarato è un caso che sparisce in "
            "silenzio. Scrivi perché."
        ),
    },
}


def strings(locale: Locale) -> Mapping[str, str]:
    """The table for `locale`, or `ValueError` naming what is available.

    Checked **at the call**, before any markup is produced: a document that
    fails halfway is worse than one that never starts, because a truncated
    report still looks like a report.
    """
    table = TEXT.get(locale)
    if table is None:
        available = ", ".join(sorted(TEXT))
        raise ValueError(f"unknown locale {locale!r}; available: {available}")
    return table


def phrase(locale: Locale, key: str, **params: object) -> str:
    """One localized string. A missing key is a programming error and says so
    with the key, rather than rendering an empty cell nobody notices."""
    table = strings(locale)
    template = table.get(key)
    if template is None:
        raise KeyError(f"no text for {key!r} in locale {locale!r}")
    return template.format(**params) if params else template
