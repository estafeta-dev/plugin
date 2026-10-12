# Session Workflow commands

Run `python3 SCRIPT --root ROOT <command>` (`py -3` on Windows). SCRIPT is this
skill's `scripts/session.py`; ROOT is the project's Git root. Each call prints
one JSON object: check `ok`, read `result` and `warnings`, keep `revision`.
Never read the runtime source or state files.

| Step | Command |
| --- | --- |
| Start | `begin`; add `--parallel` when the user says, in any language, that another live agent works in this checkout. A checkout already in parallel mode is joined automatically (see `warnings`) |
| Plan, claim, checkpoint | `batch --session ID --expect-revision R --input -` with JSON on stdin |
| Verify | `check run --session ID --phase P1 --name unit --timeout 120 -- npm test` |
| Manual or UI evidence | `check record --session ID --phase P1 --name ui --result pass --evidence "..."` |
| Milestone facts | `handover --output HANDOVER.md` |
| Close | `end --session ID --next-action "..." --handover-output HANDOVER.md` |
| Read | `status --session ID`, `next --session ID`, `snapshot` |
| Preview server | `runtime launch --session ID --name preview -- npm run dev`; `runtime stop --session ID --name preview` |

A batch has up to 20 steps, applied all or none. Plan steps upsert whole phases
and keep omitted ones:

```json
{"steps":[
  {"command":"plan","phases":[{"id":"P1","title":"Filters","acceptance":"Filters combine and persist in the URL",
    "paths":["src","tests"],"required_checks":["unit"]}]},
  {"command":"transition","phase":"P1","to":"IN_PROGRESS"},
  {"command":"checkpoint","next_action":"Implement P1"}]}
```

To finish a phase, batch these steps:

1. `transition` to VERIFY.
2. `transition` to DONE with `acceptance_note`, saying what you compared with
   the acceptance.
3. `checkpoint`.

- Phase fields are `id`, `title` and `acceptance`. Optional fields:
  - `depends_on`;
  - `priority` (lower runs first);
  - `paths`, default `"*"`: the checkout without the narrative documents;
  - `exclude`: generated outputs inside `paths`;
  - `required_checks`.
- `plan`, `batch` and `release` need `--expect-revision`; for other commands it
  is an optional guard.
- A check command after `--` runs without a shell. `--argv-file FILE` takes a
  JSON array instead. Open the log only on failure. Reported evidence cannot
  replace a required executed check.
- `end` does all of the following:
  - saves the checkpoint and releases your claims;
  - renders the facts block once, keeping the prose around it;
  - stops your runtimes (`--keep-runtimes` keeps them).
- Stopping a runtime ends its whole process group.

## Recovery

| Error or field | Action |
| --- | --- |
| `verification` | Close each listed gap: run missing checks, re-run stale ones, put generated outputs in `exclude` or .gitignore |
| `ownership` | A live session owns that phase or those paths: take unclaimed work, never edit that scope |
| `dependency` | Finish the listed dependencies first |
| Transition `warnings` | A dependency's evidence went stale after later edits: continue, re-run its checks before delivery |
| `session_alive` | That session is running a check now: wait, or `begin --parallel` for intended parallel work |
| `session_ended` | Another chat took over this checkout, or the user released this session: stop editing and tell the user. If both chats should work, `begin --parallel` with disjoint paths |
| `session_foreign` | Your session was registered on another machine or path: `begin` a new session here |
| `stale_revision` | `status`, reconcile, retry with the new revision |
| `busy` | The lock was held for 10 seconds: retry once, then report |
| `handover_after_end` | The session already ended: fix the file, rerun only `handover --output` |
| Stopped session holds claims | After the user confirms it is gone: `release --session OLD --expect-revision R --confirm-stopped --reason "..." --by ID` |
| Interrupted check stays `running` | After verifying it stopped: `check abandon --session ID --id CHECK --confirm-stopped --evidence "..."` |
