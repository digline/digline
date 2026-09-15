"""The declared price, held to ADR 0022.

The rule that shapes every test here: a price the suite **declared** is part of
the suite's identity, because it is the ruler a `CostBudget` reads cost on; a
price a plugin **shipped** is not, and neither is anything about the system that
answered. Most of these come in pairs, because only the pair shows which of the
two decided the hash.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from tests._helpers import cli, run_key, write_suite

from digline.cli import EXIT_OK, EXIT_USAGE
from digline.core import SystemConfig, pricing_digest
from digline.host import UsageError
from digline.host.toml_suite import load_toml_suite
from digline.run import Suite, Target, price_digest_of
from digline.targets import ModelPrice, Pricing, Usage, free
from digline_openai.pricing import OPENAI_PRICING
from digline_openai.target import OpenAITarget

ROOT = Path(__file__).resolve().parents[1]
GATEWAY = "https://api.aggregator.example/v1"
MODEL = "gpt-5"

SUITE = """\
[suite]
tenant = "acme"
environment = "staging"
name = "priced"
cases = "cases.json"

[target]
type = "provider"
provider = "openai/{model}"
prompt_file = "prompt.md"
max_tokens = 100
{base_url}
{pricing}

[[assertions]]
type = "cost_budget"
max_usd = 0.02
tolerance = 0.05
"""

DECLARED = """
  [target.pricing]
  input_per_mtok = 1.10
  output_per_mtok = 4.40
"""


def load(
    tmp_path: Path, *, pricing: str = DECLARED, base_url: str | None = GATEWAY
) -> tuple[Suite, Target]:
    (tmp_path / "prompt.md").write_text("Answer the question.\n", encoding="utf-8")
    (tmp_path / "cases.json").write_text('[{"id": "one"}]', encoding="utf-8")
    path = tmp_path / "suite.toml"
    path.write_text(
        SUITE.format(
            model=MODEL,
            base_url="" if base_url is None else f'base_url = "{base_url}"',
            pricing=pricing,
        ),
        encoding="utf-8",
    )
    return load_toml_suite(path, root=tmp_path)


def python_twin(tmp_path: Path, pricing: Pricing, **options: object) -> OpenAITarget:
    (tmp_path / "prompt.md").write_text("Answer the question.\n", encoding="utf-8")
    return OpenAITarget(
        tmp_path / "prompt.md",
        MODEL,
        100,
        base_url=GATEWAY,
        pricing=pricing,
        **options,  # pyright: ignore[reportArgumentType]
    )


# --------------------------------------------------------------------------- #
# §1–§2 — the shape, and declared wins
# --------------------------------------------------------------------------- #


def test_a_declared_price_replaces_the_list_entry_and_is_recorded(
    tmp_path: Path,
) -> None:
    _suite, target = load(tmp_path)
    assert isinstance(target, OpenAITarget)
    # The plugin's list knows gpt-5 at another rate; the declared one is used.
    assert OPENAI_PRICING.per_model[MODEL].input_per_mtok != 1.10
    assert target.pricing.cost(MODEL, Usage(1_000_000, 0)) == pytest.approx(1.10)
    config = target.config
    assert config["pricing"] == "declared"
    assert (config["input_per_mtok"], config["output_per_mtok"]) == (1.10, 4.40)
    # An absent cache rate is not zero, and it is not recorded as one.
    assert "cache_read_per_mtok" not in config
    assert target.price_digest == pricing_digest(MODEL, ModelPrice(1.10, 4.40).rates())


def test_no_declared_price_records_nothing_and_hashes_as_before(
    tmp_path: Path,
) -> None:
    suite, target = load(tmp_path, pricing="")
    assert price_digest_of(target) == ""
    assert isinstance(target, OpenAITarget)
    assert "pricing" not in target.config
    assert suite.config_hash() == suite.config_hash(pricing="")


def test_a_suite_that_declares_nothing_keeps_its_committed_hash() -> None:
    """The byte-identity promise, against a baseline that is in the repository."""
    import json

    suite_path = ROOT / "examples" / "quickstart-toml" / "suite.toml"
    baseline = ROOT / "examples" / "quickstart-toml" / ".digline" / "northwind"
    stored = json.loads(
        (baseline / "baselines" / "support.json").read_text(encoding="utf-8")
    )
    suite, target = load_toml_suite(suite_path, root=suite_path.parent)
    assert stored["config_hash"] == suite.config_hash(pricing=price_digest_of(target))


@pytest.mark.parametrize(
    ("pricing", "refusal"),
    [
        ("\n  [target.pricing]\n  input_per_mtok = 1.0\n", "output_per_mtok"),
        (
            "\n  [target.pricing]\n  input_per_mtok = 1.0\n  output_per_mtok = 2.0\n"
            "  input = 1.0\n",
            "input",
        ),
        (
            "\n  [target.pricing]\n  input_per_mtok = -1.0\n  output_per_mtok = 2.0\n",
            "negative",
        ),
        (
            '\n  [target.pricing]\n  input_per_mtok = "1.10"\n'
            "  output_per_mtok = 2.0\n",
            "a number",
        ),
        (
            "\n  [target.pricing]\n  input_per_mtok = true\n  output_per_mtok = 2.0\n",
            "a number",
        ),
        ('pricing = "cheap"', "table of per-million rates"),
    ],
)
def test_a_price_that_is_not_four_numbers_is_refused(
    tmp_path: Path, pricing: str, refusal: str
) -> None:
    with pytest.raises(UsageError, match=refusal):
        load(tmp_path, pricing=pricing)


def test_an_http_target_refuses_a_price(tmp_path: Path) -> None:
    (tmp_path / "cases.json").write_text('[{"id": "one"}]', encoding="utf-8")
    path = tmp_path / "suite.toml"
    path.write_text(
        "[suite]\n"
        'tenant = "acme"\nenvironment = "staging"\nname = "priced"\n'
        'cases = "cases.json"\n\n'
        "[target]\n"
        'type = "http"\nurl = "http://127.0.0.1:1/answer"\n'
        'output_path = "answer"\ncost_path = "cost"\n'
        "\n  [target.pricing]\n  input_per_mtok = 1.0\n  output_per_mtok = 2.0\n\n"
        '[[assertions]]\ntype = "cost_budget"\nmax_usd = 0.02\ntolerance = 0.05\n',
        encoding="utf-8",
    )
    with pytest.raises(UsageError, match="cost_path"):
        load_toml_suite(path, root=tmp_path)


# --------------------------------------------------------------------------- #
# §3–§4 — the ruler, and both forms
# --------------------------------------------------------------------------- #


def test_the_two_forms_carry_the_same_declared_price_and_hash(tmp_path: Path) -> None:
    suite, data_form = load(tmp_path)
    code_form = python_twin(
        tmp_path, OPENAI_PRICING.override(MODEL, ModelPrice(1.10, 4.40))
    )
    assert price_digest_of(data_form) == price_digest_of(code_form) != ""
    declared = suite.config_hash(pricing=price_digest_of(code_form))
    assert declared == suite.config_hash(pricing=price_digest_of(data_form))
    assert declared != suite.config_hash()


def test_a_price_built_without_declaring_stays_out_of_the_hash(tmp_path: Path) -> None:
    """The escape ADR 0022 §6 names: a Python suite may price without declaring,
    at the cost that changing that rate no longer reads as the rules changing."""
    undeclared = python_twin(
        tmp_path, Pricing(per_model={MODEL: ModelPrice(1.10, 4.40)})
    )
    assert price_digest_of(undeclared) == ""
    assert "pricing" not in undeclared.config


def test_the_rate_moves_the_hash_and_the_temperature_does_not(tmp_path: Path) -> None:
    declared = OPENAI_PRICING.override(MODEL, ModelPrice(1.10, 4.40))
    cooler = python_twin(tmp_path, declared, temperature=0.2)
    warmer = python_twin(tmp_path, declared, temperature=0.7)
    dearer = python_twin(
        tmp_path, OPENAI_PRICING.override(MODEL, ModelPrice(1.20, 4.40))
    )
    assert cooler.price_digest == warmer.price_digest
    assert cooler.price_digest != dearer.price_digest
    # A plugin's shipped list moving is the plugin's, and moves nothing here.
    shipped = python_twin(tmp_path, OPENAI_PRICING)
    assert shipped.price_digest == ""


def test_free_is_a_declaration() -> None:
    hosted = free("llama3.2")
    price = hosted.declared_price("llama3.2")
    assert price is not None
    assert price.rates() == dict.fromkeys(price.rates(), 0.0)


# --------------------------------------------------------------------------- #
# §6 — withheld at a named endpoint, and declared a latch
# --------------------------------------------------------------------------- #


def test_the_rates_are_withheld_at_a_named_endpoint_and_clear_elsewhere(
    tmp_path: Path,
) -> None:
    (tmp_path / "named").mkdir()
    (tmp_path / "first").mkdir()
    _suite, named = load(tmp_path / "named")
    assert isinstance(named, OpenAITarget)
    reduced = SystemConfig(values=named.config).redacted()
    assert {"input_per_mtok", "output_per_mtok"} <= reduced.withheld
    assert "input_per_mtok" not in reduced.values
    # That a price was declared is not the rate, and it travels.
    assert reduced.values["pricing"] == "declared"

    _suite, first_party = load(tmp_path / "first", base_url=None)
    assert isinstance(first_party, OpenAITarget)
    clear = SystemConfig(values=first_party.config).redacted()
    assert clear.values["input_per_mtok"] == 1.10


LATCH = (
    "withholding a declared rate is a latch, not a constraint — the value never "
    "prints, but the hash narrows it; a rate you cannot afford to narrow belongs "
    "in a python suite, or at an unnamed endpoint"
)


@pytest.mark.parametrize("document", ["SECURITY.md", "docs/declarative.md"])
def test_the_latch_is_declared_where_it_is_read(document: str) -> None:
    """The weakness cannot be edited out of the documentation while it remains in
    the code."""
    text = (ROOT / document).read_text(encoding="utf-8")
    flat = re.sub(r"[\s>*]+", " ", text).lower()
    assert LATCH in flat, f"{document} no longer declares the latch"


# --------------------------------------------------------------------------- #
# §5 — promote names the target it signs
# --------------------------------------------------------------------------- #

PRICED_TARGET = '''
class Priced:
    """A second target whose price was declared."""

    price_digest = "feedbeefcafe0000"

    def __call__(self, case):
        return target(case)


other = Priced()
'''


def test_promote_names_the_target_it_signs(repo: Path) -> None:
    write_suite(repo, preamble=PRICED_TARGET)
    key = run_key(repo, "--target", "suite_qa.py:other")

    unnamed = cli(repo, "promote", "--suite", "suite_qa.py", "--run", key)
    assert unnamed.returncode == EXIT_USAGE
    assert "config_hash" in unnamed.stderr

    named = cli(
        repo, "promote", "--suite", "suite_qa.py", "--run", key,
        "--target", "suite_qa.py:other",
    )  # fmt: skip
    assert named.returncode == EXIT_OK, named.stderr


def test_a_suite_with_no_target_still_promotes(repo: Path) -> None:
    """A `suite.py` whose module defines no `target` has no price to have declared,
    and is promoted as it always was."""
    key = run_key(repo)
    source = (repo / "suite_qa.py").read_text(encoding="utf-8")
    (repo / "suite_qa.py").write_text(
        source.replace("def target(case):", "def _target(case):"), encoding="utf-8"
    )
    done = cli(repo, "promote", "--suite", "suite_qa.py", "--run", key)
    assert done.returncode == EXIT_OK, done.stderr
