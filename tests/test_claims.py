"""The gate on absolute claims, on the repository and on each way it must fail.

Every refusal is tested next to the case it must let through: a gate that
fails everything passes each "must fail" test, and one that fails nothing
passes each "must pass" test, so only the pair says the gate discriminates.
"""

from __future__ import annotations

from pathlib import Path

from claims import REGISTER, Claim, check, covered, load_register, tracked

ROOT = Path(__file__).resolve().parents[1]

_ANCHOR = "suite.py"
_EVIDENCE = 'LIVE = os.environ.get("DIGLINE_LIVE") == "1"\n'


def _claim(quote: str) -> Claim:
    return Claim(
        file="README.md",
        quote=quote,
        anchor_path=_ANCHOR,
        anchor_contains=_EVIDENCE.strip(),
        why="the switch",
        since="test",
    )


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    for name, text in {_ANCHOR: _EVIDENCE, **files}.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path


def _check(root: Path, register: list[Claim] | None = None) -> list[str]:
    paths = [p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()]
    return check(root, paths, register or [])


def test_the_repository_passes() -> None:
    assert check(ROOT, tracked(ROOT), load_register(ROOT / REGISTER)) == []


def test_every_entry_of_the_register_is_anchored_in_this_repository() -> None:
    register = load_register(ROOT / REGISTER)
    assert register
    for claim in register:
        assert (ROOT / claim.anchor_path).is_file(), claim


# Tier 1: never admitted.


def test_a_tier_1_phrase_in_a_covered_file_fails(tmp_path: Path) -> None:
    root = _repo(tmp_path, {"README.md": "Nothing leaves your machine.\n"})
    assert _check(root) == [
        "README.md:1: tier 1, 'nothing leaves your machine' "
        "is never admitted — rewrite it"
    ]


def test_the_same_file_without_it_passes(tmp_path: Path) -> None:
    root = _repo(tmp_path, {"README.md": "Nothing is uploaded by the CLI itself.\n"})
    assert _check(root) == []


def test_a_tier_1_phrase_fails_even_inside_a_registered_quote(tmp_path: Path) -> None:
    root = _repo(tmp_path, {"README.md": "The payload never leaves.\n"})
    assert _check(root, [_claim("The payload never leaves.")]) != []


def test_a_phrase_wrapped_across_lines_and_set_in_bold_is_the_same_phrase(
    tmp_path: Path,
) -> None:
    root = _repo(
        tmp_path, {"README.md": "Intro.\n\n- **Data never\n  leaves.** Ever.\n"}
    )
    assert _check(root) == [
        "README.md:3: tier 1, 'data never leaves' is never admitted — rewrite it"
    ]


def test_a_phrase_matches_on_word_boundaries(tmp_path: Path) -> None:
    root = _repo(tmp_path, {"README.md": "Its metadata never leaves a trace.\n"})
    assert _check(root) == []


def test_a_docstring_is_read_and_a_comment_is_not(tmp_path: Path) -> None:
    source = '"""Module.\n\nNo data ever leaves.\n"""\n\n# no data ever leaves\n'
    root = _repo(tmp_path, {"src/pkg/mod.py": source})
    assert _check(root) == [
        "src/pkg/mod.py:3: tier 1, 'no data ever leaves' is never admitted — rewrite it"
    ]


# Tier 2: admitted with an anchored entry.


def test_a_tier_2_phrase_with_no_entry_fails(tmp_path: Path) -> None:
    root = _repo(tmp_path, {"README.md": "No data leaves.\n"})
    assert _check(root) == [
        f"README.md:1: tier 2, 'no data leaves' with no entry in {REGISTER} "
        "— rewrite it, or anchor it"
    ]


def test_a_tier_2_phrase_with_an_entry_passes(tmp_path: Path) -> None:
    root = _repo(
        tmp_path, {"README.md": "- **No data leaves.** Only your suite calls.\n"}
    )
    assert _check(root, [_claim("No data leaves. Only your suite calls.")]) == []


def test_an_entry_covers_its_own_file_only(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        {"README.md": "No data leaves.\n", "docs/guide.md": "No data leaves.\n"},
    )
    assert _check(root, [_claim("No data leaves.")]) == [
        f"docs/guide.md:1: tier 2, 'no data leaves' with no entry in {REGISTER} "
        "— rewrite it, or anchor it"
    ]


def test_an_entry_whose_quote_is_gone_fails(tmp_path: Path) -> None:
    root = _repo(tmp_path, {"README.md": "Runs stay on disk.\n"})
    assert _check(root, [_claim("No data leaves.")]) == [
        f"{REGISTER}: README.md: the quote is no longer there — 'No data leaves.'"
    ]


def test_an_entry_whose_anchor_lost_its_evidence_fails(tmp_path: Path) -> None:
    root = _repo(tmp_path, {"README.md": "No data leaves.\n"})
    (root / _ANCHOR).write_text("LIVE = True\n", encoding="utf-8")
    assert _check(root, [_claim("No data leaves.")]) == [
        f"{REGISTER}: README.md: the anchor suite.py no longer contains "
        f"{_EVIDENCE.strip()!r}"
    ]


def test_an_entry_whose_anchor_file_is_gone_fails(tmp_path: Path) -> None:
    root = _repo(tmp_path, {"README.md": "No data leaves.\n"})
    (root / _ANCHOR).unlink()
    assert _check(root, [_claim("No data leaves.")]) == [
        f"{REGISTER}: README.md: the anchor suite.py does not exist"
    ]


# What is not read.


def test_the_changelog_the_adrs_and_the_tests_are_not_read(tmp_path: Path) -> None:
    sentence = "The payload never leaves the perimeter.\n"
    root = _repo(
        tmp_path,
        {
            "CHANGELOG.md": sentence,
            "packages/digline-openai/CHANGELOG.md": sentence,
            "docs/adr/0002-the-three-worlds.md": sentence,
            "tests/test_something.py": f'"""{sentence}"""\n',
            "tests/fixtures/page.md": sentence,
        },
    )
    assert _check(root) == []


def test_the_same_sentence_in_a_covered_file_fails(tmp_path: Path) -> None:
    root = _repo(
        tmp_path, {"docs/guide.md": "The payload never leaves the perimeter.\n"}
    )
    assert _check(root) != []


def test_what_is_covered() -> None:
    for path in (
        "README.md",
        "SECURITY.md",
        "AGENTS.md",
        "packages/digline-openai/README.md",
        "examples/langchain/README.md",
        "docs/guide.md",
        "src/digline/store/file_store.py",
        "packages/digline-openai/src/digline_openai/target.py",
        "examples/langchain/suite.py",
    ):
        assert covered(path), path
    for path in (
        "CHANGELOG.md",
        "docs/adr/0002-the-three-worlds.md",
        "tests/test_claims.py",
        "packages/digline-openai/tests/test_target.py",
        "tools/claims.py",
        "tools/claims_register.toml",
    ):
        assert not covered(path), path


def test_an_entry_for_a_file_the_gate_does_not_read_fails(tmp_path: Path) -> None:
    root = _repo(tmp_path, {"CHANGELOG.md": "No data leaves.\n"})
    claim = Claim(
        file="CHANGELOG.md",
        quote="No data leaves.",
        anchor_path=_ANCHOR,
        anchor_contains=_EVIDENCE.strip(),
        why="the switch",
        since="test",
    )
    assert _check(root, [claim]) == [
        f"{REGISTER}: CHANGELOG.md: this file is not read by the gate"
    ]


def test_an_entry_without_its_anchor_is_refused(tmp_path: Path) -> None:
    register = tmp_path / "register.toml"
    register.write_text(
        '[[claim]]\nfile = "README.md"\nquote = "No data leaves."\n'
        'why = "harmless"\nsince = "test"\n',
        encoding="utf-8",
    )
    try:
        load_register(register)
    except ValueError as error:
        assert "`anchor` is missing" in str(error)
    else:
        raise AssertionError("an entry with no anchor was loaded")
