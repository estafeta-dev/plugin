# Estafeta handover

## Current work

estafeta 3.1.0 adds cross-provider work (plan:
docs/plans/multi-provider.md).

- **Skill `agent-relay`.** Lets an orchestrator consult, cross-review with or
  delegate a phase to another provider, and coordinate peer agents. It covers
  T3 host tasks, Codex/Claude/Gemini CLIs and same-provider subagents.
- **Runtime command `delegate`.** Keeps a ledger beside the state, so schema 2
  is unchanged. CLI workers run as supervised processes with a timeout. The
  runtime checks a writer's claims against recorded checks and the observed
  workspace.
- **Integrated.** Existing skills, docs and the 3.1.0 manifests know about
  the skill. A CI workflow was added.
- **Testing approach (user request).** Golden path tests check a short
  sequence of agent interactions, with an expected result at each step:
  - every change, in CI: a deterministic stub worker
    (`scripts/test_relay.py`);
  - before a release or a provider/model change: live runs checked with
    `--live-verify`.

## Next action

Merge the 3.1.0 pull request after its CI run passes. Optional follow-ups:

- a third Codex review round;
- live `codex exec` and `gemini -p` runs where those CLIs are installed;
- the benchmark follow-up in docs/BENCHMARK-ROADMAP.md.

## Validation

On October 15, 2026, on macOS with Python 3.9.6:

- runtime 70/70, installer 21/21, golden 5/5 scenarios (79 steps), pack check
  and the Claude plugin validators passed;
- four deliberate regressions were caught by golden steps;
- live, all passing `--live-verify`:
  - Codex gpt-6.1-sol through T3: a delegated write and two cross-review
    rounds (12, then 5 findings, all fixed with tests);
  - `claude -p` as a CLI worker: consult on Haiku 5.5, write on Sonnet 5.5
    under the OS sandbox.

Details are in packs/session-workflow/VALIDATION.md.

## Boundaries

Not verified:

- live `codex exec` and `gemini -p` CLI transports;
- the Gemini/Antigravity route;
- native Linux and Windows.

The round 2 fixes were tested locally but not re-reviewed by Codex. The
fixtures in /private/tmp/relay-live and /private/tmp/relay-cli are disposable.

<!-- session-workflow:facts:start -->
## Session facts (generated)

State revision 109; HEAD 8559853e8949b0ef51d5ffb9c2351158fba23ff2.

| Phase | State | Owner | Latest checks |
| --- | --- | --- | --- |
| P1 | DONE | - | unit-session: pass (executed, inputs match); golden-relay: pass (executed, inputs match); pack-check: pass (executed, inputs match) |
| P2 | DONE | - | pack-check: pass (executed, inputs match); unit-workflow: pass (executed, inputs match) |
| P3 | DONE | - | pack-check: pass (executed, inputs match); unit-workflow: pass (executed, inputs match); unit-session: pass (executed, inputs match); golden-relay: pass (executed, inputs match) |
| P4 | DONE | - | live-relay: pass (executed, inputs match); unit-session: pass (executed, inputs match); golden-relay: pass (executed, inputs match) |
| P5 | DONE | - | live-cli: pass (executed, inputs match); live-review-2: pass (executed, inputs match); golden-relay: pass (executed, inputs match); pack-check: pass (executed, inputs match) |

Active sessions: none.
Ended sessions: 5; latest s-xprov-1015 (next: Watch CI of the agent-relay-3.1.0 pull request and merge it when green. Optional: Codex review round 3, live codex exec / gemini -p runs where installed, benchmark follow-up.).

Generated facts do not establish acceptance, explain intent or prove delivery.
<!-- session-workflow:facts:end -->
