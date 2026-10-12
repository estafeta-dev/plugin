# Session Workflow development benchmark

A repeated, fresh-chat comparison of the same coding agent on three small
offline scenarios: a website, a browser game and a web application. Each case
has an initial implementation and a requirement change in a fresh chat that
receives only project files.

**Status:** prepared for Session Workflow 3.0.0, not executed. The 3.0 runtime
and instructions (`session-handover`, `HANDOVER.md` for new projects, no
`operation` commands) have not been measured by any model run yet.

## Arms

| Arm | Enabled skills | Block at the activation slot of the prompt |
| --- | --- | --- |
| `baseline` | none | none; common prompt only |
| `lite` | none (same isolation as baseline) | frozen text of [`prompts/lite.md`](prompts/lite.md): continuity conventions without tools or runtime |
| `workflow` | exactly four project-local copies: `session-start`, `plan-and-orchestrate`, `session-handover`, `session-end` | `Use $session-start, $plan-and-orchestrate, $session-handover and $session-end as the session workflow…` |

Common prompt, starter, briefs and limits are identical in all arms. `workflow`
versus `lite` is the decisive comparison: does the runtime earn its cost over the
same conventions given as plain instructions? Each arm is also compared with
`baseline`.

## Protocol

- Model `gpt-6.1-sol`, reasoning `max`, one local Codex CLI installation.
- Case = scenario × arm × repetition in `cases/<scenario>-<arm>-r<rep>`. Defaults:
  3 × 3 × 3 = 27 cases, 54 fresh `codex exec` processes; no chat resume.
- Order: `random.Random(seed)` draws one arm sequence per scenario and rotates it
  per repetition (a cyclic Latin square), so with 3 repetitions each arm runs
  first, second and third exactly once per scenario. The scenario blocks are
  shuffled per repetition, and each scenario/repetition block runs every arm once,
  back to back. The seed defaults to the UTC date (`YYYYMMDD`).
  `protocol.json` records `seed`, `arms`, `scenarios`, `repetitions` and the full
  `order` (`[scenario, arm, rep]`); `execute` and `summarize` follow that record.
- Isolation is verified per case at `prepare`: `workflow` has exactly the four
  skills enabled, `baseline` and `lite` none. Unrelated plugins, personal memory,
  apps, hooks, web search and subagents are disabled in all arms. Do not edit
  global settings or authentication.
- Agents may write their own tests and project notes. Evaluator source is outside
  their workspace: procedural test hiding, not a security boundary.
- Maximum 12 minutes per stage, sequential execution. A timeout/failure is
  retained; never silently replace an unsuccessful observation. No repair after
  evaluator feedback.
- Prompts, fixtures, evaluator and plugin are hashed at `prepare`; `execute`
  refuses to start after any change. Log infrastructure repairs separately from
  agent defects.

## Measurements

`turn.completed.usage` supplies input, cached input and output tokens. Cached
input is a subset of input: total = input + output; uncached = input − cached.
Missing usage is unknown, never zero. These are aggregate model-token counters,
not monetary charges or unique context length.

Per stage: process wall time (startup, tools and checks included), tool commands,
failed commands, commands containing `session.py` and skill file reads; a case
sums its two stages. Independent grading time is recorded separately and not
charged to any arm. Provider TTFT is not measured.

Functional effectiveness is requirement groups passed / total after phase 1 and
after the change. Failed assertions are not bugs: reviewed failures are grouped
into distinct reproducible defects; evaluator/infrastructure limitations are
reported separately. The report gives each arm's median, minimum and maximum
across repetitions and compares medians with `baseline`; a median is shown only
when every planned repetition has a value. Inspect handover separately; more
documentation earns no product points.

## Run

Prerequisites: authenticated Codex CLI, Python 3.9+, Node, Playwright with a
local Chrome. Execution reuses existing authentication and consumes paid account
usage: the default plan is 54 sessions of up to 12 minutes each.

```sh
python3 benchmarks/run.py prepare --output /abs/run \
  [--arms baseline,lite,workflow] [--scenarios website,game,app] \
  [--repetitions 3] [--seed N] [--playwright /abs/node_modules/playwright]
python3 benchmarks/run.py execute --output /abs/run    # resumable
python3 benchmarks/run.py summarize --output /abs/run
python3 benchmarks/audit.py --output /abs/run          # before changing the harness
python3 benchmarks/report.py --output /abs/run         # REPORT.ru.md, report.html
python3 benchmarks/test_order.py                       # offline self-check, no Codex
```

`prepare` refuses an existing output and missing lite text or skill sources.
`execute` skips stages that have metrics and refuses a partial attempt until it
is reconciled explicitly. Raw JSONL, stderr, exact prompts, snapshots, isolation
audit, per-stage metrics and grades are retained; review/redact personal paths
and logs before committing evidence.

`audit.py` checks frozen sources, that the order covers every case once, matches
its seed and was the start order, distinct chats overall and identical starters
per scenario. Per case: skill isolation, arm prompts (lite text only in `lite`,
activation only in `workflow`), completion, native usage, one fresh chat per
stage and no skill file reads outside `workflow`. For `workflow` only: all four
skills read, exact plugin copies, and ended sessions with released phases in
`.agent-state/session-workflow/state.json`. `report.py` needs a reviewed
`review.json` to count confirmed defects; otherwise they are labeled unreviewed.

`extra_checks.mjs OUTPUT PLAYWRIGHT [channel]` reads the cases from
`protocol.json`. It uses the corrected v3 keyboard-discovery check from the 2.4
rerun and takes an optional browser channel (default `chrome`, for example
`msedge`). `adjudicate.py` is for historical regrading: with `grade-v2.mjs` and
`evaluator-correction.json` in the output directory it regrades both snapshots of
every case and keeps the original scores. New runs use the corrected evaluator
directly.

The coding jobs share the workspace-write sandbox without network. On the
original host it blocked local preview binds and browser launch; the external
grader used system Chrome outside the sandbox. Keep conditions identical across
arms and record any change as a new protocol. Project-local skill copies are
untracked; results do not estimate a preinstalled user-level plugin or Eco mode.

## Scope

One model/provider/device and deliberately small offline projects. Repetitions
show spread; no significance test is built in, and the harness cannot establish
production quality, cross-provider portability, distributed concurrency or
automatic activation from an unqualified prompt. `workflow` measures explicitly
invoked skills plus their runtime as a package. Long, interrupted and concurrent
projects need the [long-project protocol](../docs/BENCHMARK-ROADMAP.md).

## Historical results

[`results/`](results/) holds frozen evidence from the old two-arm harness
(baseline/workflow, one sample per cell, fixed order, skill name
`handover-changelog`): the [2.3.0 pilot](results/2026-10-12-pilot/README.md) and
the [2.4.0 rerun](results/2026-10-12-optimized/README.md). Commit hashes in that
evidence (for example `plugin_commit`) refer to the original private history,
which the owner keeps archived. The public repository starts at 3.0.0, and the
measured files are identified by content in each run's `source-hashes.json`.
The current `run.py` and `audit.py` reject that layout (`report.py` and
`adjudicate.py` still read it).
The pilot record documents the two evaluator corrections included in the current
`grade.mjs`.

Instrumentation follows the official [non-interactive CLI documentation](https://learn.chatgpt.com/docs/non-interactive-mode)
and [skill eval guidance](https://developers.openai.com/blog/eval-skills).
Skill disabling uses [the documented per-skill configuration](https://learn.chatgpt.com/docs/build-skills).
