# Validation - estafeta 3.1.0

## Cross-provider relay, 3.1.0 (2026-10-15)

macOS, Python 3.9.6, orchestrator Claude Opus 5.5 in T3 Code.

**Deterministic suites.** These run on every change and in CI.

| Suite | Result |
| --- | --- |
| runtime (`test_session.py`) | 70/70 |
| installer (`test_workflow.py`) | 21/21 |
| golden paths (`test_relay.py`, stub worker) | 5/5 scenarios, 79 steps |
| `workflow.py check` (6 skills) | passed |
| `claude plugin validate`, plugin and marketplace | passed |

Four deliberate runtime regressions were each caught by a golden step:

- false check claims no longer detected;
- no supervisor timeout;
- a worker's check not stopped with its worker;
- equal grace periods for the supervisor and nested check runners.

**Live golden paths.** Host transport: T3 Code `delegate_task`, provider
instance `codex`.

| Scenario | Model | Result |
| --- | --- | --- |
| write-worktree, disposable fixture | gpt-6.1-sol, medium | PASS. The worker followed the packet: it began its parallel session, claimed P1, ran the required check through the runtime, moved to VERIFY, ended, and returned a valid block. `collect` found no discrepancies. The integrator reviewed and merged the change, reran the check and accepted P1. `--live-verify` passed 2/2 steps. |
| review-host, this change, round 1 | gpt-6.1-sol, high | PASS (`--live-verify` 1/1). The verdict was CHANGES_REQUIRED with 12 findings, 5 of them high. All 12 were fixed, and each fix has a unit test or golden step. |
| review-host, fix delta, round 2 | gpt-6.1-sol, high | PASS (`--live-verify` 1/1). 10 of 12 fixes were confirmed. The verdict was CHANGES_REQUIRED with 5 reproduced findings, 3 of them high, about nested kill grace, non-final JSON events, a same-checkout writer, stale check evidence and duplicate JSON keys. All 5 were fixed with tests; the grace fix was mutation-tested. |

**Live CLI transport.** `claude -p` 2.1.300 ran as a supervised `delegate`
worker, started from inside a Claude Code session.

| Scenario | Model | Result |
| --- | --- | --- |
| consult-cli | claude-haiku-5-5 | PASS (`--live-verify` 1/1). The worker read the code and answered correctly. `collect` took the block from the JSON `result` field. |
| write-worktree, disposable fixture | claude-sonnet-5-5 | PASS (`--live-verify` 2/2). 10 turns, $0.14, OS sandbox with `failIfUnavailable`. No discrepancies; the integrator merged the change, reran the check and accepted the phase. |

The sandbox denied the worker's file tool a write to the state directory, as
intended: only Bash may write there. The packet template now runs checks
inline after `--`, so a worker needs no file outside its worktree.

The first live write exposed a real ordering race: the host worker began and
claimed its phase before the orchestrator recorded the task. The runtime now
accepts that case, and the `write-host-fast-worker` scenario covers it.

**Not verified:**

- live `codex exec` and `gemini -p` CLI transports (not installed here) and
  the Gemini/Antigravity host route;
- the first CI run on GitHub;
- native Linux and Windows.

## estafeta rename (2026-10-13)

The public name, plugin ID (`estafeta`) and marketplace ID
(`pashbel-estafeta`) were synchronized across packaging and documentation.
The existing project state paths, handover markers and skill ownership markers
remain compatible with earlier installations.

Rechecked on macOS with Python 3.9.6: runtime 57/57, installer 19/19, benchmark
ordering 3/3, `workflow.py check`, and both Claude plugin validators passed.
Installer checks include the renamed plugin-only archive and installing from a
relocated full source archive. Codex native discovery was not exercised because
the Codex CLI is unavailable on this host.

The remaining results, including instruction byte counts, describe the original
3.0.0 payload tested before the public rename.

## Original 3.0.0 review (2026-10-12)

Executed on macOS on 2026-10-12 from the source checkout. Runtime and installer
checks use disposable repositories and profile directories. No model or API
call was made, and no existing installation or project was modified.

## Executed checks

| Check | Result |
| --- | --- |
| `python3 scripts/workflow.py check` (versions, shared copies, links, stale version strings) | pass |
| `scripts/test_session.py` runtime suite, Python 3.9.6, 3.12.13 and 3.14.7 | 57/57 on each |
| Runtime suite repeated (flakiness) | Final runtime: 3 consecutive passes on 3.9.6 and 1 each on 3.12.13 and 3.14.7. The revision before the parallel-mode change: 10 consecutive passes on 3.9.6 |
| `scripts/test_workflow.py` installer suite, Python 3.9.6, 3.12.13 and 3.14.7 | 19/19 on each |
| `benchmarks/test_order.py` (seeded order, Latin-square positions, arm prompts) | 3/3 |
| `claude plugin validate .` and `claude plugin validate packs/session-workflow` | pass, no warnings |
| `git diff --check` | clean |

The 2.4.1 runtime test `test_two_processes_can_begin_unique_sessions...` failed
in 5 of 7 runs during the review: the lock did not wait, so contention returned
`busy` at once. It now passes consistently, because the lock waits up to 10
seconds.

## Review scenarios as regression tests

Every 2.4.1 failure reproduced during the review has a runtime test. Each was
also re-run through the real CLI, in subprocesses, exactly as the quickstart
documents it:

- **Crashed chat:** a chat closed without session-end. The next solo `begin`
  supersedes it and takes over its phase claim and preview server. A session
  running a check counts as alive, and `begin` and `release` refuse to take
  over from it.
- **Parallel and other-machine sessions:** these are never superseded. They are
  visible in `other_active_sessions` and can be released with confirmation.
- **Parallel mode:** one `--parallel` marks the sessions already active in the
  folder as parallel. A chat opened later without the flag joins with a warning
  instead of taking over. Solo takeover resumes once every session there has
  ended.
- **Folder rename and hostname change:** the project keeps working; a vanished
  checkout path is superseded.
- **Dependent phases:** a phase editing the same files as its DONE dependency
  reaches VERIFY and DONE with a warning, and `next` reports the stale
  dependency.
- **Commits and narrative documents:** a commit, HANDOVER.md or PROJECT.md does
  not stale whole-checkout evidence; a product file change does.
- **Checks that write files:** a check writing a timestamped file into its scope
  reports `changed_during_check`. DONE names the file, and `exclude` fixes it.
- **No Git:** a project with 12,000 files in `node_modules` begins in 0.15 s.
  Oversized workspaces degrade with a warning; an untracked dependency tree in
  Git gets a .gitignore hint.
- **Git status:** the state directory stays out of `git status` unless the
  project already versions it.
- **Process groups:** stopping a runtime ends its descendants; checks run in
  their own process group.
- **Bounded output:** after 30 chats, `begin` output stays within 200 bytes of
  the second chat's, and the facts block stays under 15 lines. Events and check history are bounded.
- **Unicode:** output is readable UTF-8 even with an ASCII console encoding.
- **session-guide is read-only:** its `status` call leaves an initialized
  project byte-for-byte unchanged and creates nothing in a project without
  state. Checked through the CLI.
- **Commands after `--`:** a command is accepted only by `check run` and
  `runtime launch`, and never together with `--argv-file`.
- **Schema 1 state:** read-only commands upgrade it in memory, warn, and leave
  the file untouched. The first write keeps an identical `state.v1.json` and
  reports the dropped operation IDs once.

The suite keeps the earlier guarantees as well:

- atomic batches with rollback, and revision guards;
- one owner under concurrent processes;
- overlap and alias rejection;
- the fresh-evidence and acceptance gates, with tampered and missing logs
  rejected;
- linked worktrees sharing one coordinator, and long checks outside the lock;
- `handover_after_end`, prose-preserving markers, symlink and traversal
  rejection, and the last good state kept after a failed write.

## Installer

The 19 installer tests cover:

- dry run, backups, idempotence, drift detection, staging and replacement
  rollback;
- overlap rejection, Unicode profiles, CRLF sources, moved archives and the
  plugin-only archive;
- Codex location selection and link-mode migration.

New in 3.0:

- The retired `handover-changelog` is backed up and removed only when it came
  from this pack, including links into this repository. Same-named skills from
  other packs are kept.
- `status` reports `RETIRED-PRESENT` while an old copy remains.
- Stale version strings in skill files block installation.

## Instruction size

These are byte counts of the shipped Markdown, not model tokens.

| Material | 2.4.1 | 3.0.0 |
| --- | ---: | ---: |
| One skill as loaded (SKILL.md + contract + quickstart) | 11,183-12,055 | 8,595-8,968 |
| The four working SKILL.md files + contract + quickstart | 18,060 | 15,247 |
| session-guide SKILL.md (loaded only when asked) | - | 3,491 |
| Cold references (runtime, recovery, efficiency, delegation) | 26,198 | 8,498 |
| Templates | 5,372 | 2,354 |
| Total instruction material | 49,630 | 26,099 |

## Not verified

- **Model behaviour:** no model session has run the 3.0 instructions. The three-arm
  harness (baseline, lite conventions, workflow) is prepared but not executed:
  it needs the Codex CLI, which is not installed on this host, and paid usage.
- **Platforms:** native Windows and Linux runs were not executed. Process-group
  cleanup is POSIX; the Windows `taskkill /T` path and the hardware-ID lookups
  for Windows and Linux are untested.
- **Native plugins:** Codex native plugin discovery was not re-verified for 3.0.
- **Installation:** nothing was installed into the user's profiles, and existing
  2.4.1 copies are unchanged.
- **Coordination limits:** claims rely on cooperating agents, and the local lock
  does not coordinate separate machines. Unicode tests check that data is
  preserved, not that the model writes fluently.

Reproduce:

```sh
python3 scripts/workflow.py check
python3 scripts/test_session.py
python3 scripts/test_workflow.py
python3 benchmarks/test_order.py
```
