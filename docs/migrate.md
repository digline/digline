# `digline migrate` — stored runs across schema versions

A store outlives the schema that wrote into it. `migrate` brings the runs and
the baseline of a suite up to the version this release reads.

## What a scan does, and what a named key does

They behave differently on purpose.

- A **scan** — `digline list`, `--run latest`, `digline view` — steps over a
  document it cannot read and **says how many it stepped over**. A survey stops
  at nothing it merely fails to recognise. What it must never do is skip in
  silence, so the count is reported by schema version.
- A **key asked for by name** is refused instead. There the caller named that
  file, and must be told it cannot be read.

```console
$ digline list --suite suite.py
  KEY                                                CREATED                            ENV           COMMIT          CASES
  2026-08-26T15-44-09-492722-00-00-e7421ec503ccefe8  2026-08-26T15:44:09.492722+00:00   staging       b304442         2

* = current baseline

ignored: 1 run(s) at schema 5
run `digline migrate` to bring them up to date
```

The first version of the listing raised on the first foreign file, which made
`--run latest` fail the morning after a release for a reason that had nothing to
do with the run being asked for.

## Migrating

`--dry-run` says what would happen and writes nothing:

```console
$ digline migrate --suite suite.py --dry-run
would migrate 2026-08-26T15-44-09-282929-00-00-e7421ec503ccefe8.json from schema 5
1 would migrate, 2 already current, 0 refused
```

```console
$ digline migrate --suite suite.py
migrated 2026-08-26T15-44-09-282929-00-00-e7421ec503ccefe8.json from schema 5
1 migrated, 2 already current, 0 refused
```

Each file is rewritten in place **only after** it has been re-read with the new
schema: a document that does not parse back is not a document that was migrated.
The write goes through a temporary file and `os.replace`, so an interruption
never leaves half a run behind.

## Additive and non-additive

- **Additive** bumps — a field added with a defensible default — are carried
  forward.
- **Non-additive** ones are **refused**, and the refusal names what is missing.
  There is no `tenant` to invent for a file written before perimeters existed,
  and inventing one would put a run inside a perimeter nobody put it in.

A refused file is left exactly as it was. `0 refused` in the tally is the
ordinary case; anything else is a decision for a person, not for the tool.

**Additive does not mean empty.** Schema 9 added the raw per-sample scores and
the interval they span, and the step *derives* them from `metadata["scores"]` —
a list every sampled run has carried since sampling existed. Reading what is
already in the document is not inventing, and it is the difference between a
promoted baseline being a noise floor on the day you upgrade and being one after
you re-promote everything. A run at `samples=1` gains nothing but the version
number, because at one sample there is no interval: `[score, score]` would be a
noise floor of zero width dressed as a measurement.

One thing the step deliberately leaves alone: an **aggregate** — precision,
accuracy — records no interval on migration. Sizing one needs the marks and the
declared assertion, and a run file carries neither, so a migrated baseline sizes
the noise of its cases and reports the noise of its aggregates as not known. The
aggregate floors arrive when you promote a run produced under this release.

## See also

- [`api.md`](api.md) — the public API
- [`adr/0002-three-worlds-and-where-the-data-lives.md`](adr/0002-three-worlds-and-where-the-data-lives.md) — the tenant as a perimeter
