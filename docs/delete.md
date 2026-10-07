# `digline delete` — removing a run

`delete` removes one run from the store: its document, its journal legs, and
every replay chained from it anywhere in the tenant. It is the one way digline
has to forget a run. It is **not an erasure**, and the limits below say exactly
what it does not reach. ([ADR 0044](adr/0044-the-run-delete.md))

```console
$ digline delete --suite suite_qa.py --run 2026-10-07T07-00-58-179965-00-00-c8a84850c6fd7289
removed run 2026-10-07T07-00-58-179965-00-00-c8a84850c6fd7289 in suite qa, tenant acme-bank: its document.
$ digline delete --suite suite_qa.py --run 2026-10-07T07-00-58-179965-00-00-c8a84850c6fd7289
nothing is filed under 2026-10-07T07-00-58-179965-00-00-c8a84850c6fd7289 in suite qa, tenant acme-bank: no document, no legs, no replay. Nothing was removed.
```

## What it takes and what it answers

- **A key, written out.** `--run latest` is refused: `latest` names the newest
  readable run, so the same command would remove a different run each time it
  was repeated. `digline list` shows the keys.
- **Exit 0 when something was removed and when nothing was**, and the words say
  which. A repeated delete succeeds and says *nothing is filed*. The cost is
  stated with it: a mistyped key and a removed one read the same, because
  nothing remembers a removal.
- **Exit 64 for a refusal**, as every refusal. Nothing is removed before a
  refusal: the delete reads everything it will touch first, and refuses there.
- **No confirmation and no force flag.**
- **Not on the MCP server.** An agent has no `delete` tool: the server is
  [absent by construction](mcp.md) for what it must not do, and a delete
  removes files nobody reviews, with no way back.

## What it removes

- **The run's document and its journal legs**, the legs first. A run made only
  of legs, one that was killed or is still running, is removed too.
- **Every replay of it, across the tenant**, and every replay of those. A
  replay carries the removed run's answers, or verdicts that judged them, and
  the library's `rejudge` can file one under another suite of the same tenant.
  Replays are removed from the leaves towards the run, so a delete cut off part
  way is finished by the same command.
- **A replay filed under the wrong name, or declaring a tenant or suite other
  than the directory it sits in**, is removed like any other, and the command
  names the file and what it declared: a document filed otherwise than it says
  is a fact about the store, not only about the delete.

## What it refuses

- **The run the suite's current baseline was promoted from.** The baseline is
  the run without its answers, so it would outlive the run with its verdicts,
  reasons and artifacts, and a delete that reached it would pull a reference
  from under a gate. Promote another run first, with
  `digline promote --suite … --run <key> --replacing <this key>`, then delete.
  The refusal holds even when the run under the baseline is already gone.
- **A file under the key that cannot be shown to be that run**: not JSON, not
  a document, without `created_at` or `config_hash`, or filed under a name that
  is not its key. Removing by name could remove the wrong document.
- **A replay on the chain with no key of its own.** What cannot be named is not
  removed.
- **A directory of the tenant that cannot be listed**, and a path to remove
  that leads out of the store.

## The limits

- **A delete racing anything that writes loses.** There is no lock. A run
  still running writes its document at the end and comes back whole.
  `promote` can read the run, and write a baseline from it after the delete
  checked. `rejudge` can file a replay after the delete looked, and that replay
  keeps the run's answers.
- **A document the delete cannot read is not reached**, and nobody learns
  whether it was a replay. The command says how many there were: *"N documents
  in tenant T could not be read. Whether any of them was a replay of K is not
  known, and none of them was removed."* Never silent.
- **Two documents under one key.** When a replay filed under the wrong name
  holds the key of another document that stays, only the misfiled one goes,
  and the command says beside that key that it still names a document. The
  journal legs under that key are left: they are the document's that stays.
- **Two suites can share a key**: the same configuration and the same
  `created_at`, to the microsecond. Replays are matched by key, so the delete
  then reaches the other suite's replays too.
- **Git history.** The delete touches nothing committed: not the baseline, not
  the register, not the projection. A run somebody committed by overriding the
  store's `.gitignore` stays in history.
- **What was never the store's.** A report written with `report --out` is
  recorded nowhere, so nothing reaches it. Backups, snapshots and copy-on-write
  blocks keep what was removed.
- **No trace of the gesture.** A delete leaves no record, and afterwards a key
  removed and a key never filed read the same.

From a program, the same gesture is `ResultStore.delete_run`
([API](api.md#deleting-delete_run)).
