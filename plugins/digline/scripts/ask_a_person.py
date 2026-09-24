"""Read a PreToolUse payload and ask a person before a person's decision:
`digline promote`, `digline register`, or `digline view --allow-promote`.

Started by `ask-a-person`, which has already decided that the project is a
digline project. Standard library only: it runs in the project's `.venv`, but
must not import the digline installed there, whose version is not the
plugin's to choose.

What is matched is the *command*, never a string: the line is split where the
shell would split it, and each simple command is read from its first word. So
`grep -r "digline register " notes/` is a grep and `git commit -m 'register
…'` is a commit, whatever their arguments say.

**One subcommand is read past its first word, and the principle does not
move.** Bare `digline view` is a reading tool and is not asked about — a hook
that interrupts reading is a hook people learn to dismiss without reading, and
it spends that credibility where there is no decision behind it.
`digline view --allow-promote` is not a smaller thing than `digline promote`
but a larger one: the same decision, taken once and made ambient for every run
in the store for as long as the server is up. So the reach changes from *the
first word* to *the first word and, for one subcommand, its flags*, and what is
matched is still a word of the parsed simple command — `grep -r "digline view
--allow-promote" notes/` is still a grep. (ADR 0032 §3)

The forms this does not read pass without asking — a command handed to another
program as a string (`bash -c`, `sh -c`, `xargs`, `eval`, `ssh`), or spelled
through a variable or an alias. That is "a preference, not a wall" being true:
the wall is the reviewed diff under `.digline/<tenant>/`.
"""

from __future__ import annotations

import json
import re
import shlex
import sys
from collections.abc import Iterator

REASONS = {
    "promote": (
        "digline promote makes a run the approved reference, committed under "
        ".digline/<tenant>/baselines/"
    ),
    "register": (
        "digline register records what a person decided about a comparison, "
        "committed under .digline/<tenant>/register/"
    ),
    "view --allow-promote": (
        "digline view --allow-promote serves a page that makes any run the "
        "approved reference, committed under .digline/<tenant>/baselines/ — "
        "the promote decision taken once and left standing for every run in "
        "the store, for as long as the server is up"
    ),
}

#: The subcommands decided by a flag rather than by their name alone. `view`
#: reads the store and is not asked about; the flag is what turns it into a
#: surface that writes the committed reference. (ADR 0032 §3)
FLAGGED = {"view": "--allow-promote"}

# The shell's own operators, plus a newline: each ends one simple command.
OPERATORS = "();<>|&\n"
ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
# The options of `uv run` and `uvx` that take their value as the next word.
# Without these, `uv run --project . digline promote` would read `.` as the
# command.
UV_VALUED = {
    "--project",
    "--directory",
    "--with",
    "--python",
    "-p",
    "--package",
    "--from",
}
MODULES = {"digline", "digline.cli"}


def simple_commands(line: str) -> Iterator[list[str]]:
    # `punctuation_chars` makes shlex hand back `&&`, `|`, `;` as words of
    # their own, which is what lets the line be cut where the shell cuts it.
    lexer = shlex.shlex(line, posix=True, punctuation_chars=OPERATORS)
    lexer.whitespace = " \t\r"  # the newline is an operator here, not a space
    lexer.whitespace_split = True
    words: list[str] = []
    for word in lexer:
        if word and all(c in OPERATORS for c in word):
            if words:
                yield words
            words = []
        else:
            words.append(word)
    if words:
        yield words


def after_digline(words: list[str]) -> list[str] | None:
    """The arguments digline would receive, or None if this is not digline."""
    while words and ASSIGNMENT.match(words[0]):
        words = words[1:]
    if not words:
        return None
    name = words[0].rsplit("/", 1)[-1]
    if name == "digline":
        return words[1:]
    if name == "uvx" or (name == "uv" and words[1:2] == ["run"]):
        rest = words[1:] if name == "uvx" else words[2:]
        while rest and rest[0].startswith("-"):
            rest = rest[2:] if rest[0] in UV_VALUED else rest[1:]
        return rest[1:] if rest[:1] == ["digline"] else None
    if name.startswith("python") and words[1:2] == ["-m"] and words[2:3]:
        return words[3:] if words[2] in MODULES else None
    return None


def subcommand(arguments: list[str]) -> tuple[str, list[str]] | None:
    """The subcommand and what follows it, with digline's own flags stepped
    over first. The rest is returned rather than dropped because one
    subcommand is decided by a flag of its own."""
    while arguments and arguments[0].startswith("-"):
        arguments = arguments[2:] if arguments[0] == "--root" else arguments[1:]
    return (arguments[0], arguments[1:]) if arguments else None


def key_for(arguments: list[str]) -> str | None:
    """The `REASONS` key this invocation deserves, or None.

    A flagged subcommand is watched only when its flag is present, and it is
    matched as a whole word: `--allow-promote=` is not a spelling argparse
    accepts for a `store_true`, so a prefix match would only ever widen this
    past what the CLI does.
    """
    found = subcommand(arguments)
    if found is None:
        return None
    name, rest = found
    if (flag := FLAGGED.get(name)) is not None:
        return f"{name} {flag}" if flag in rest else None
    return name


def watched(command: str) -> str | None:
    try:
        commands = list(simple_commands(command))
    except ValueError:  # unbalanced quotes: the shell would refuse it too
        return None
    for words in commands:
        arguments = after_digline(words)
        if arguments is not None and (name := key_for(arguments)) in REASONS:
            return name
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        command = payload["tool_input"]["command"]
    except (ValueError, KeyError, TypeError):
        return 0
    if not isinstance(command, str) or (name := watched(command)) is None:
        return 0
    reason = (
        f"{REASONS[name]}. That decision is a person's: approve this only if "
        "you made it. (A preference, not a wall - the wall is the reviewed diff.)"
    )
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": reason,
        }
    }
    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
