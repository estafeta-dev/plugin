# Estafeta handover

## Current work

3.1.0 (`agent-relay` and runtime `delegate`) is merged to main through PR #3.

The 3.2.0 work (plan docs/plans/relay-hardening.md) was merged to main through
PR #5 on October 16, but 3.2.0 is not released: the version still reads 3.1.0
and the review findings below are open. Work continues on `main`. Done so far:

- **Windows.** Supported and verified in CI. Fixed: index file modes in
  fingerprints, job-object supervision, and a file-based stop request for
  nested checks.
- **Takeover guard.** A solo session-start no longer takes over a live thread
  in the same folder. This was observed live with a parallel Codex thread in
  T3.
- **Provider policy.** Projects get an "AI providers" table that session-start
  asks for on first use and `delegate` enforces. This project allows every
  available provider except the Claude (Pricefx) work account.
- **Live checks.** These passed:
  - `codex exec` as a worker;
  - Antigravity through T3;
  - orchestrators in Claude Code and in Codex, each with the other's CLI and
    with their own native subagents;
  - the Gemini CLI failure mode without an API key.
- **Drivers.** `scripts/golden/live_cli.py` and `live_orchestrator.py` replay
  the live golden paths.

## Next action

The work moves to another computer. There, follow docs/CONTINUING.md and use
session-start. The runtime state (phases, checks, the delegation ledger) stays
on this computer, so import the open phases R4 and R5 from the plan.

Then fix the 11 findings of Codex review round 3. They are listed in
docs/plans/relay-hardening.md, "Status at pause". Start with the
high-severity ones:

1. the policy parser;
2. the Windows job assignment race;
3. nested stop chaining;
4. the late-recorded host writer baseline.

Add a failing test for each, then rerun the suites and the affected live
paths. Have Codex re-review the fix delta. Then release 3.2.0 (R5).

## Validation

On October 15, 2026, on macOS with Python 3.9.6:

- runtime 76/76, installer 21/21 and golden 6/6 scenarios passed, and
  `workflow.py check` passed.
- PR #5 CI was green on Linux, macOS and Windows at 29fb17e, the last code
  change; this closed R1 on October 16.
- Live evidence for each transport and host is in
  packs/session-workflow/VALIDATION.md.

## Boundaries

- **Unverified:**
  - a live `gemini -p` answer (no API key);
  - Codex orchestrating without network access (not run);
  - native Windows beyond GitHub CI.
- **Machine-local:** the runtime state and the live-run fixtures under the
  temp directory stay on the first computer. VALIDATION.md keeps the live
  evidence.
- **Installs:** on this computer every detected provider profile carries the
  skills from main at c373020 (October 16, `status` all MATCH). Other
  computers are not updated yet: run `python3 scripts/workflow.py install
  --all-detected` there.

<!-- session-workflow:facts:start -->
## Session facts (generated)

State revision 164; HEAD c3730202691f656b19d8e16cfa39c4162cdf0996.

| Phase | State | Owner | Latest checks |
| --- | --- | --- | --- |
| P1 | DONE | - | unit-session: pass (executed, inputs changed); golden-relay: pass (executed, inputs changed); pack-check: pass (executed, inputs changed) |
| P2 | DONE | - | pack-check: pass (executed, inputs changed); unit-workflow: pass (executed, inputs changed) |
| P3 | DONE | - | pack-check: pass (executed, inputs changed); unit-workflow: pass (executed, inputs changed); unit-session: pass (executed, inputs changed); golden-relay: pass (executed, inputs changed) |
| P4 | DONE | - | live-relay: pass (executed, inputs changed); unit-session: pass (executed, inputs changed); golden-relay: pass (executed, inputs changed) |
| P5 | DONE | - | live-cli: pass (executed, inputs changed); live-review-2: pass (executed, inputs changed); golden-relay: pass (executed, inputs changed); pack-check: pass (executed, inputs changed) |
| R1 | DONE | - | unit-session: pass (executed, inputs match); unit-workflow: pass (executed, inputs match); golden-relay: pass (executed, inputs match); pack-check: pass (executed, inputs match); ci-windows: pass (executed, inputs match) |
| R2 | DONE | - | live-codex-cli: pass (executed, inputs match) |
| R3 | DONE | - | live-antigravity: pass (executed, inputs match); gemini-cli-failure: pass (executed, inputs match) |
| R4 | TODO | - | - |
| R5 | TODO | - | - |
| R6 | DONE | - | unit-session: pass (executed, inputs changed); golden-relay: pass (executed, inputs changed); pack-check: pass (executed, inputs changed) |
| R7 | DONE | - | unit-session: pass (executed, inputs match); golden-relay: pass (executed, inputs match) |
| R8 | DONE | - | live-orchestrators: pass (executed, inputs match) |

Active sessions: none.
Ended sessions: 11; latest s-22b1f0e8 (next: On another computer: follow docs/CONTINUING.md (branch main), use session-start, import open phases R4 and R5 from docs/plans/relay-hardening.md, then fix the 11 Codex review round 3 findings (high severity first, each with a failing test), have Codex re-review the fix delta and release 3.2.0 (R5)).

Generated facts do not establish acceptance, explain intent or prove delivery.
<!-- session-workflow:facts:end -->
