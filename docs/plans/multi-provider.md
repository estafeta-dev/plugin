# Multi-provider relay plan

- Context: [PROJECT.md](../../PROJECT.md)
- Goal and acceptance: one project can be worked on by several AI providers at
  once. An orchestrator in any provider can use another provider as a subagent:
  it can consult it, request a review or delegate a phase as a writer. Every
  delegation is recorded, resumable without native agent IDs, and judged by the
  orchestrator against fresh checks.
- Scope and non-goals: one new portable skill `agent-relay` with per-provider
  adapters, a provider-neutral `delegate` command in the bundled runtime, and
  integration into the existing skills and docs. Not in scope: storing
  credentials, installing provider CLIs, a long-running broker or daemon,
  pairwise provider skills, or automatic merging without the integrator.
- Execution: authorized by the user on 2026-10-15, including one or two paid
  child tasks through T3 (Codex as worker and/or reviewer). No commit or push
  without a separate request.
- Constraints: Python 3.9+ standard library only; state schema 2 stays
  readable by estafeta 3.0.0 runtimes; safety-bypass flags of provider CLIs are
  never used by default; follow docs/MAINTAINING.md for versioning.
- Base: main @ 8559853e8949b0ef51d5ffb9c2351158fba23ff2, with the uncommitted
  generated facts block in HANDOVER.md from the previous session.

## Decisions

| ID | Question and recommendation | Answer or open impact | Date |
| --- | --- | --- | --- |
| D1 | One generic skill with adapters, pairwise "X talk to Y" skills, or instructions only? Recommended: one skill. | One skill `agent-relay` + adapter references + runtime support. | 2026-10-15 |
| D2 | Transports? Recommended: headless CLI as the portable baseline plus host-native orchestration where available. | Both. Locally only `claude` is on PATH; T3 exposes Codex and Gemini (Antigravity) as child tasks. | 2026-10-15 |
| D3 | Collaboration modes for v1? | All four: consult, review, write (delegated phase), peer sessions. | 2026-10-15 |
| D4 | Where to record delegations? | A ledger under the state directory (`delegations/`), not in `state.json`. Schema 2 is unchanged, so a 3.0.0 worker on another provider can still join as a parallel session. CLI workers reuse the supervised `runtime` machinery, so `end` stops them. | 2026-10-15 |
| D5 | How does a result come back regardless of transport? | The worker ends its final answer with one `RELAY-RESULT` block; `delegate collect` extracts it from the CLI log or from a file holding the host tool's reply. | 2026-10-15 |
| D6 | Version | 3.1.0: additive skill and command, no schema change. | 2026-10-15 |
| D7 | How to test a sequence of agent interactions? | Golden path tests: a few representative scenarios in `scripts/golden/relay-scenarios.json`, each a sequence of steps with an expected result per step; any failed step fails the whole scenario. Cheap mode replaces the LLM with a deterministic stub worker and runs with the integration tests on every change (`scripts/test_relay.py`). Live mode runs the same scenario with a real provider at release time and verifies the same step expectations from the recorded state. | 2026-10-15 |

| D8 | How to catch regressions when providers or models change? | Every delegation records provider and model. Deterministic golden paths run in CI (new GitHub Actions workflow: `check`, unit tests, stub golden paths) on every push and pull request. Live golden paths need provider credentials and cost money, so they run manually per provider × model before a release; VALIDATION.md records which pairs passed and when. Measuring the value of cross-provider work (cost, review catch rate) belongs in the benchmark roadmap, not in v1. | 2026-10-15 |

## Phases

Runtime facts (state, owner, checks) appear in the handover's generated block.
All phases run sequentially in this checkout with one integrator: they share
the runtime source, skill copies and manifests. P4 uses cross-provider child
tasks only for verification and review.

### P1: Relay runtime

- Scope and anchors: `shared/runtime/session.py` (`command_parser`,
  `launch_runtime`, `end`, `brief`, `dispatch`), `shared/runtime.md`,
  `shared/quickstart.md`, `scripts/test_session.py`; synced copies in every skill.
- Acceptance: `delegate providers|start|status|collect|cancel` work for the
  `cli` transport (supervised process, log, exit) and the `host` transport
  (recorded host reference only); write mode requires an existing phase and a
  worker session ID; results are parsed and hashed; `end` reports open
  delegations and stops CLI workers it owns; state schema stays 2.
- Golden paths (D7): consult, review, delegated write in a linked worktree with
  integration, and an interrupted worker that is cancelled. Each involves
  sessions, claims, a supervised worker, recorded checks, the ledger and
  collect, and states the expected result of every step.
- Checks and review: `unit-session`, `golden-relay`, `pack-check`.

### P2: agent-relay skill

- Scope and anchors: `skills/agent-relay/` (SKILL.md, agents/openai.yaml,
  provider and host adapters, packet and result templates), `skills.list`,
  `scripts/workflow.py`, `scripts/test_workflow.py`.
- Acceptance: the skill covers the four modes, chooses a transport, builds a
  packet, never uses bypass flags by default, and states authorization rules;
  it installs and validates like the other skills.
- Checks and review: `pack-check`, `unit-workflow`.

### P3: Integration and release docs

- Scope and anchors: delegation.md in plan-and-orchestrate, session-end and
  session-guide wording, README files, docs/USAGE.md, docs/INSTALL.md,
  docs/MAINTAINING.md, VALIDATION.md, manifests and VERSION, PROJECT.md,
  `.github/workflows/ci.yml` (D8), docs/BENCHMARK-ROADMAP.md follow-up.
- Acceptance: users can find and invoke cross-provider work from the README and
  the guide; version 3.1.0 is consistent everywhere; CI runs the deterministic
  suites including the stub golden paths.
- Checks and review: `pack-check`, `unit-workflow`, `unit-session`.

### P4: Live cross-provider proof

- Scope and anchors: a disposable fixture project outside the repository;
  evidence summary in this plan and VALIDATION.md.
- Acceptance: the live golden path passes: a Codex child task launched through
  T3 completes the delegated-write scenario in the fixture following an
  `agent-relay` packet, and `scripts/test_relay.py --live-verify` confirms
  every step expectation from the recorded state. A Codex review of this change
  returns a verdict and its findings are resolved or recorded.
- Checks and review: `live-relay` (live-verify run), re-run of unit and golden checks.

## Results

- P4 live golden path: Codex gpt-6.1-sol through T3 passed the write scenario
  in /private/tmp/relay-live and the review scenario on this change; both
  pass `--live-verify`. See packs/session-workflow/VALIDATION.md.
- The live write exposed a recording race: the worker began before the
  orchestrator recorded the task. It is fixed and has a golden scenario.
- Codex review `review-codex-1` returned CHANGES_REQUIRED with 12 findings.
  All are fixed with tests:
  - check processes outlived a timed-out worker;
  - an unknown runtime was treated as stopped;
  - results could be extracted from tool output;
  - lexical scope checks allowed traversal;
  - ledger transfer was not ordered after the state save;
  - adoption left the process with the old session;
  - required-check provenance was not checked;
  - `collect --from` worked while a worker ran;
  - a malformed blocked result crashed `collect`;
  - the Claude writer had no sandbox;
  - Gemini ran without `--model`;
  - `--live-verify` could pass without checks.

- P5 (user request 2026-10-15): live `claude -p` CLI transport passed
  consult-cli (Haiku 5.5) and write-worktree (Sonnet 5.5 under the OS sandbox,
  $0.14). The packet template now runs checks inline after `--`.
- Codex review round 2 (`review-codex-2`) confirmed 10 of 12 round 1 fixes and
  returned CHANGES_REQUIRED with 5 reproduced findings. All are fixed with
  tests:
  - a check ignoring SIGTERM outlived the timeout; nested and supervisor grace
    periods now differ;
  - non-final JSON events with `result`/`response` were accepted; event types
    are now required;
  - a writer in the orchestrator checkout was not inspected; changes are now
    compared with a baseline;
  - stale required-check evidence was accepted; the DONE gate is now applied
    in the worker workspace;
  - duplicate JSON keys were resolved silently.

## Follow-ups and accepted limitations

- Real `codex exec`, `claude -p` and `gemini` CLI runs are not yet verified.
  Codex and Gemini CLIs are not installed on this machine, and a `claude -p`
  run was not authorized. The adapters cite official documentation.
- A second Codex review round on the fix delta would need another paid run
  and was not started.
- CI runs only after a push. Linux and Windows have not been run natively.
