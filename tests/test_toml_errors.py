"""What a wrong suite file is told, checked as a catalogue.

ADR 0007 §6, and the reason it gets a test file of its own: *"a format whose
failure mode is a silent default is worse than no format."* The refusals are
the feature, so they are tested like one.

Two rules hold across the whole catalogue, and they are checked for every
message rather than case by case:

- **every refusal says where** — the file, and the entry inside it;
- **every boundary says where to go** — a suite.py, and the page that explains
  how to write one.

Beyond that, each message is checked for the one thing it exists to say. The
wording is free to change; the shape is not.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from digline import core
from digline.cli.errors import UsageError
from digline.cli.toml_errors import CUSTOM_DOCS, did_you_mean
from digline.cli.toml_suite import ASSERTIONS, PYTHON_ONLY, load_toml_suite

ROOT = Path(__file__).resolve().parents[1]

SUITE = """
[suite]
tenant = "northwind"
environment = "staging"
name = "support"
cases = "cases.json"
"""

TARGET = """
[target]
type = "http"
url = "http://localhost:8080/answer"
output_path = "data"

  [target.body]
  question = "case.vars.question"
"""

CONTAINS = """
[[assertions]]
type = "contains"
needle = "Northwind Support"
"""

CASES = json.dumps([{"id": "a", "vars": {"question": "?"}}])

#: Builds a suite file and returns whatever loading it raised.
Load = Callable[..., UsageError]


@pytest.fixture
def failing(tmp_path: Path, fake_provider: None) -> Load:
    def load(
        body: str = SUITE + TARGET + CONTAINS, *, cases: str = CASES
    ) -> UsageError:
        (tmp_path / "suite.toml").write_text(body, encoding="utf-8")
        (tmp_path / "cases.json").write_text(cases, encoding="utf-8")
        with pytest.raises(UsageError) as caught:
            load_toml_suite(tmp_path / "suite.toml")
        return caught.value

    return load


# --------------------------------------------------------------------------- #
# The two rules that hold everywhere
# --------------------------------------------------------------------------- #

#: One entry per message the catalogue can produce, as (label, document).
EVERY_REFUSAL: list[tuple[str, str]] = [
    ("misspelt parameter", SUITE + TARGET + CONTAINS + "treshold = 0.9\n"),
    ("unknown check", SUITE + TARGET + '\n[[assertions]]\ntype = "sentiment"\n'),
    ("no type", SUITE + TARGET + '\n[[assertions]]\nneedle = "x"\n'),
    ("misspelt suite key", SUITE + 'tenent = "n"\n' + TARGET + CONTAINS),
    ("stray table", SUITE + TARGET + CONTAINS + '\n[targets]\ntype = "http"\n'),
    ("no assertions", SUITE + TARGET),
    (
        "no cases key",
        '[suite]\ntenant = "n"\nenvironment = "s"\nname = "x"\n' + TARGET + CONTAINS,
    ),
    (
        "python-only check",
        SUITE + TARGET + '\n[[assertions]]\ntype = "from_autoevals"\n',
    ),
    (
        "custom pii pattern",
        SUITE + TARGET + '\n[[assertions]]\ntype = "pii_absent"\npatterns = ["x"]\n',
    ),
    (
        "judge as an import",
        SUITE + TARGET + '\n[[assertions]]\ntype = "llm_rubric"\nrubric = "r"\n'
        'judge = "digline_anthropic:AnthropicJudge"\nthreshold = 0.7\n'
        "tolerance = 0.05\n",
    ),
    (
        "judge with settings",
        SUITE + TARGET + '\n[[assertions]]\ntype = "llm_rubric"\nrubric = "r"\n'
        "threshold = 0.7\ntolerance = 0.05\n"
        '\n[assertions.judge]\nprovider = "fake/m"\n',
    ),
    (
        "computed body",
        SUITE + '\n[target]\ntype = "http"\nurl = "http://x"\noutput_path = "d"\n'
        'request = "build"\n' + CONTAINS,
    ),
    (
        "injected client",
        SUITE + '\n[target]\ntype = "provider"\nprovider = "fake/m"\n'
        'client = "stub"\n' + CONTAINS,
    ),
    ("third target form", SUITE + '\n[target]\ntype = "grpc"\n' + CONTAINS),
    ("disclosure in data", SUITE + 'disclosure = "everything"\n' + TARGET + CONTAINS),
    (
        "missing provider",
        SUITE + TARGET + '\n[[assertions]]\ntype = "llm_rubric"\n'
        'rubric = "r"\njudge = "nowhere/m"\nthreshold = 0.7\ntolerance = 0.05\n',
    ),
    ("sampling with no floor", SUITE + "samples = 3\n" + TARGET + CONTAINS),
]


#: The half of the catalogue that is about a real limit of the format rather
#: than a mistake in the file. Each one has to end somewhere a reader can go.
BOUNDARIES = [
    "python-only check",
    "custom pii pattern",
    "judge as an import",
    "judge with settings",
    "computed body",
    "injected client",
]


@pytest.mark.parametrize(("label", "document"), EVERY_REFUSAL)
def test_every_refusal_names_the_file(failing: Load, label: str, document: str) -> None:
    """A message a reader cannot locate is a message they cannot act on."""
    assert "suite.toml" in str(failing(document)), label


@pytest.mark.parametrize(("label", "document"), EVERY_REFUSAL)
def test_no_refusal_is_a_bare_python_error(
    failing: Load, label: str, document: str
) -> None:
    """No `TypeError: __init__() got an unexpected keyword argument`, and no
    `KeyError`. Every one of these is a sentence somebody wrote."""
    message = str(failing(document))
    assert "Traceback" not in message, label
    assert "__init__()" not in message, label
    assert message.strip() == message and len(message) > 40, label


@pytest.mark.parametrize("label", BOUNDARIES)
def test_each_boundary_names_suite_py_and_the_page(failing: Load, label: str) -> None:
    """A boundary that only says "no" is the one a user files a bug about."""
    document = dict(EVERY_REFUSAL)[label]
    message = str(failing(document))
    assert "suite.py" in message, label
    assert CUSTOM_DOCS in message, label


def test_the_page_every_boundary_points_at_exists() -> None:
    """A pointer at a page that moved is worse than no pointer."""
    assert (ROOT / CUSTOM_DOCS).is_file()


# --------------------------------------------------------------------------- #
# The near miss
# --------------------------------------------------------------------------- #


def test_a_misspelt_parameter_is_named_with_its_near_miss(failing: Load) -> None:
    message = str(failing(SUITE + TARGET + CONTAINS + "treshold = 0.9\n"))
    assert "has no parameter `treshold`" in message
    assert "Did you mean `threshold`?" in message


def test_the_yaml_habit_is_recognised(failing: Load) -> None:
    """`llm-rubric` for `llm_rubric` is not a guess, it is a certainty."""
    message = str(failing(SUITE + TARGET + '\n[[assertions]]\ntype = "llm-rubric"\n'))
    assert "Did you mean `llm_rubric`?" in message


def test_two_wrong_keys_are_both_named(failing: Load) -> None:
    """Fixing one and rerunning to find the next is a bad way to spend an
    afternoon."""
    message = str(
        failing(
            SUITE + TARGET + '\n[[assertions]]\ntype = "contains"\n'
            'neelde = "x"\ntolerence = 0.1\n'
        )
    )
    assert "`neelde`" in message and "`needle`" in message
    assert "`tolerence`" in message and "`tolerance`" in message


def test_a_check_that_resembles_nothing_gets_the_two_families(
    failing: Load,
) -> None:
    """No near miss, so the list is the only help there is — and it is split,
    because "which check" and "which aggregate" are different questions."""
    message = str(failing(SUITE + TARGET + '\n[[assertions]]\ntype = "sentiment"\n'))
    assert "per case:" in message and "per run:" in message
    assert "`contains`" in message and "`precision`" in message


def test_a_case_field_typo_is_caught_in_the_cases_file(failing: Load) -> None:
    message = str(failing(cases=json.dumps([{"identifier": "a"}])))
    assert "cases.json" in message
    assert "`identifier`" in message


@pytest.mark.parametrize(
    ("typed", "meant"),
    [
        ("treshold", "threshold"),
        ("tolerence", "tolerance"),
        ("neelde", "needle"),
        ("case-sensitive", "case_sensitive"),
        ("Threshold", "threshold"),
    ],
)
def test_the_near_miss_catches_what_people_actually_type(
    typed: str, meant: str
) -> None:
    assert meant in did_you_mean(typed, ["needle", "case_sensitive", *_common()])


def _common() -> list[str]:
    return ["name", "threshold", "tolerance", "accepts"]


def test_a_word_resembling_nothing_gets_no_suggestion() -> None:
    """A wrong guess is worse than none: it sends somebody to try a key that
    was never the one they wanted."""
    assert did_you_mean("elephant", ["needle", "threshold"]) == ""


# --------------------------------------------------------------------------- #
# What the catalogue must keep covering
# --------------------------------------------------------------------------- #


def test_every_python_only_token_is_a_real_check() -> None:
    """A token recognised only to be refused has to name something that
    exists, or the message is a lie about the package's own surface."""
    for token in PYTHON_ONLY:
        camel = "".join(part.title() for part in token.split("_"))
        assert hasattr(core, camel), token


def test_a_python_only_token_is_not_also_buildable() -> None:
    """The two tables must not overlap: a token in both would be built by one
    rule and refused by the other, and which one won would be an accident."""
    assert not set(PYTHON_ONLY) & set(ASSERTIONS)
