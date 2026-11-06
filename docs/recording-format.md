# The recording document

A recording is one call an application made to a model, or one turn of an
agent made of several calls ([an episode](#what-is-fixed)), kept as a JSON file.
digline's recorder writes these files, and so may a program in another
language. The import, `digline record compare` and `digline record status`
read the files and nothing else, so a file written to this page is read like
one digline wrote. This page is the contract, as
[ADR 0062](adr/0062-the-recorder-out-of-process-and-in-other-processes.md) §2
fixes it.

## Where a file goes

```text
.digline/<tenant>/recordings/<process>/<name>.json
```

- **`<tenant>`** is the tenant the call was made for. The file says it again,
  in `source_tenant`, and a file whose tenant is not its directory's is
  refused.
- **`<process>`** is a directory of the writing process's own, one per
  process. Its name is free. digline's recorder writes `p<pid>-<8 hex>`.
- **`<name>`** is free, ends in `.json` and does not start with a dot. Files
  are read in the order their paths sort, so name them to sort in the order
  they were written: digline writes `000001.json`, `000002.json` and so on.
- **Write a file whole.** Write it under a name that starts with a dot, which
  no reader reads, and rename it to its name when it is complete.

## The smallest recording

```json
{
  "app": "support",
  "case": {
    "messages": [
      {
        "content": "Where is my refund?",
        "role": "user"
      }
    ]
  },
  "recorded_at": "2026-11-04T08:00:00.123456+00:00",
  "recording_version": 1,
  "response": {
    "input": "[{\"content\":\"Where is my refund?\",\"role\":\"user\"}]",
    "kind": "text",
    "latency_ms": 812.0,
    "output": "It was sent on Monday.",
    "usage": {
      "input_tokens": 14,
      "output_tokens": 7
    }
  },
  "setup": {
    "model": "gpt-4o-mini",
    "temperature": 0.2
  },
  "setup_digest": "fce37866a724540f",
  "source_tenant": "acme",
  "suite": "refunds"
}
```

## What is fixed

- **`recording_version`** is the integer `1`. A reader refuses a file at any
  other version, by name, and never reads it as this one.
- **`source_tenant`**, **`app`** and **`suite`** are non-empty strings. A call
  that names no suite is filed under `_unassigned`.
- **`case`** is a JSON object, with the call's conversation under
  `messages`: the messages after any leading instructions, which belong to
  the setup. The import makes it the case's `vars`, and two recordings with
  the same `case` are the same case.
- **`setup`** is a JSON object: everything else that decided how the call
  answered, such as the model, its parameters and the instructions.
- **`setup_digest`** is the first 16 hexadecimal characters of the SHA-256 of
  `setup`, written with:
  - keys sorted;
  - the separators `,` and `:`, with no spaces;
  - every non-ASCII character escaped as `\uXXXX`;
  - **each float written as a string**: the shortest digits that read back as
    the same number, in positional notation, without trailing zeros or a
    trailing point. So `0.7` is `"0.7"`, `1e-05` is `"0.00001"`, `100.0` is
    `"100"`, and both zeros are `"0"`. In Java that is
    `new BigDecimal(Double.toString(d)).stripTrailingZeros().toPlainString()`,
    with `"0"` for a zero.

  The floats are strings only in the text that is hashed: `setup` itself
  keeps them as numbers. Two languages write one float as different text,
  for example `1.0E-5` and `1e-05`, and this form is what both can write.
- **`response`** is the answer:
  - `output`, the answer's text;
  - `kind`, which is `text`, `structured` or `conversation`;
  - `input`, the case's `messages` as JSON text, with keys sorted and no
    spaces. It is the question the judge reads beside the answer, and the
    import refuses an answer recorded without one;
  - `latency_ms`, a number;
  - `usage`, with `input_tokens` and `output_tokens`, where the provider
    reported them.

  A key with nothing to say is left out, never written empty.
- **`recorded_at`** is the time the file was written, in UTC with its offset
  written `+00:00`, to the second, with up to six digits of fraction. Any
  other form is refused by name, `Z` included, which is what Java's
  `Instant.toString()` writes. Readers compare two as instants, never as
  text.
- **An episode**, a turn of an agent written as one recording, adds `id`,
  32 hexadecimal characters, which only an episode carries. Its `input` is
  its whole `case` as JSON text, and each call made inside it carries the
  episode's `id` in `episode`. An episode whose case nobody gave, as
  `digline record proxy` writes one, takes its first call's and says so with
  `case_from_first_call`, written `true` or not at all.
- **Steps**, a trajectory, are the response's, in `response.steps`, for an
  episode and a single call alike. A step has an `index` from 0, an `actor`
  (`model` or `tool`), the `finish` of a model step where one was reported,
  and a tool step's call in the run document's keys. A file with `steps`
  beside its response is refused by name. The recorder's steps are in
  [`record.md`](record.md#steps-live).

## The switch

A writer reads the tenant's switch, `.digline/<tenant>/recorder.toml`, with
the rules of [`record.md`](record.md#switching-it-on), and a root that holds
no `.digline/` has no switch: the writer is off, as digline's own is, unless
`DIGLINE_RECORD=1` switches it on in development.

## A run in progress: the gate's calls

*Added 2026-11-05 (ADR 0058, ADR 0062, as amended that day).* While
`digline run` is in progress it leaves a marker in its tenant's directory:

```text
.digline/<tenant>/runs/.gate/<pid>-<run_id>.json
{"run_id": "<the run's key>", "pid": 4242, "started_at": "...", "suite": "refunds"}
```

A call made then, with a `[target] http` pointed at an application that
records itself, is the gate's and not the application's traffic. So a writer,
for each call, and **while the call still waits on it** — when the call
begins, or at the latest before its reply reaches the application, never
after:

- **lists that directory**, skipping a name that starts with a dot or does
  not end in `.json`. No directory is no run, and neither is a directory, or
  a marker, that resolves outside `.digline/`, or outside the directory: a
  link out of the store is not read;
- **takes a marker as live** when its modification time is at most 120
  seconds old. The run touches it every 30 seconds and removes it when it
  ends. An older one was left by a run that was killed: it is ignored, and
  `digline record status` names it;
- **still writes the file** where a marker is live, and adds `origin`,
  written `"gate"`, and `run_id`, the marker's `run_id`. Where more than one
  marker is live, or the one live marker cannot be read as JSON with a
  non-empty string `run_id`, it writes `origin` alone.

A writer that answers the application first and writes the file after, as
`digline record proxy` does, reads the marker as the call begins: by the time
it writes, the run that made the call may have ended and removed its marker.
An episode is the gate's where any of its calls was.

Absent, `origin` means the application. A file with `run_id` and no `origin`
is refused, and so is any other `origin`. Two optional keys, so
`recording_version` stays 1. The readers keep such a file apart: no list,
import, compare or *since the last import* reads it, and `digline record
status` and the recorder page of `digline view` count it as *from gate
runs*. Nothing deletes it.

`recorders/fixtures/gates.json` holds what digline answers for a set of
markers, and the Java writer is tested against it.

## What is free

What a writer puts inside `setup`, beyond its being JSON; the `app` name; the
names of the process directory and of the file.

## What is not part of the contract

- **`label`.** A file written with one is still read, and the key ignored.
- **The `.counts` file** that digline's recorder keeps in its process
  directory, with what it did not record and why. A writer in another
  language keeps none, and `digline record status` then says *not counted*
  for that process, rather than *nothing was left out*.
