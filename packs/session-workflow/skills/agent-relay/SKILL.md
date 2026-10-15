---
name: agent-relay
description: >-
  Work on one estafeta project with several AI providers: ask another agent a
  question, get a cross-review, delegate a phase to a worker of another
  provider (Claude Code, Codex, Gemini, or host-native subagents such as T3
  Code tasks), or coordinate peer agents the user opened. Use for "ask Codex",
  "have Claude review this", "delegate this phase to Gemini", "second
  opinion", «спроси Codex», «пусть Claude проверит», «отдай фазу другому
  агенту». Every delegation is recorded and judged against fresh checks.
license: Apache-2.0
metadata:
  workflow-pack: session-workflow
  workflow-version: "3.1.0"
---

# Agent relay

Read the [contract](references/workflow-contract.md) and
[quickstart](references/quickstart.md) once per chat; delegation commands are
in [runtime](references/runtime.md), section Delegations. If this chat has no
session yet, run session-start first. You are the orchestrator and the only
integrator: workers never change the plan, handover or Git history.

## Modes

| Mode | Use for | Worker may write | Returns |
| --- | --- | --- | --- |
| `consult` | Question, design option, second opinion | Nothing | `answer` |
| `review` | Exact diff or revision | Nothing | `verdict`, `findings` |
| `write` | One planned phase | Only that phase's paths, in its own workspace | changed files, recorded checks |
| peer | Agents the user opened in the same project | Their own claimed phases | Their own sessions |

## Delegate

1. **Authorize.**
   - **The project table.** The AI providers table in PROJECT.md is the
     user's standing choice of providers, modes and models for this project,
     and the runtime refuses anything outside it. If it is missing, ask the
     user and record it first (session-start, step 5). Change it only when
     the user asks.
   - **Cost.** Each run of another provider still costs money: follow the
     user's request for this task and say what you start.
   - **Secrets.** Never put secrets in a packet.
2. **Pick the transport** (details and exact commands: [adapters](references/adapters.md)):
   1. a host-native cross-provider task, if this host offers one;
   2. otherwise the provider's CLI (`delegate providers` lists them);
   3. a same-provider subagent, when only another model is needed.

   Without any of these, do the work yourself and say the review is self-review.
   Never use a flag that bypasses the worker's sandbox or approvals.
3. **Prepare a write.** The phase must be unclaimed, not DONE and
   disjoint from other live claims. Give the worker its own linked worktree
   on a `relay/<phase>` branch from the current commit, unless the host
   creates the worktree itself. Uncommitted changes do not reach a new
   worktree.
4. **Write the packet** from the [template](templates/packet.md) into the
   state directory's `inputs/<session>/`. A packet is self-contained: the
   worker may not have estafeta installed, so give it the absolute runtime
   path, IDs, allowed paths, required checks with exact argv, and stop
   conditions. Later rounds send only the changes.
5. **Start and record.**
   - CLI: `delegate start --session ID --name N --provider P --model M --mode
     MODE --packet F [--phase P --worker-session W --workspace DIR]
     --timeout S -- <adapter argv>`.
   - Host: launch the host task with the packet text, then record it at once
     with `delegate start ... --host-ref <task id>`. A fast writer may already
     have begun and claimed its phase; the runtime accepts that. If recording
     fails for another reason, cancel the host task.
6. **Wait without busy polling.** Host tasks notify; for a CLI worker, check
   `delegate status --name N` at sensible intervals and continue other
   unclaimed work meanwhile.
7. **Collect.** Run `delegate collect --name N`. For a host task, save the
   reply text to the `reply_file` that `start` returned, or pass `--from FILE`.
   If the result is `malformed`, ask the same worker to resend only the
   RELAY-RESULT block, then collect again.
8. **Judge.** A worker's words are claims.
   - consult: weigh the answer like any source and say where it came from.
   - review: fix or record every finding. Let the same reviewer check the fix
     delta when possible. A verdict is not a passed test.
   - write: `discrepancies` must be empty. Read the diff in the worker
     workspace and commit it on the relay branch yourself. Merge it, claim the
     phase (VERIFY), then rerun the required checks in the integrated checkout.
     Only then go to DONE.
9. **Clean up.** Cancel tasks you no longer need. After a successful merge,
   remove the worker worktree. `end` stops your CLI workers and lists open
   delegations; a later session adopts them through `delegate status`,
   `collect` or `cancel`.

## Peer agents

When the user runs agents of several providers on the project at once, each
starts with session-start in parallel mode and claims phases with disjoint
paths, ideally in its own worktree. Name one integrator for the plan, handover
and Git history. The others report changed files, checks and gaps to the
integrator instead of editing shared records. Claims need cooperation: a
provider without estafeta must be given the same rules in its prompt.

## Worker side

If you received a relay packet, follow it exactly. Use the runtime path it
names, begin only the session it names, stay inside its paths, never commit,
push or change shared records, and end with exactly one RELAY-RESULT block.

## Model and provider changes

The ledger records provider and model for every delegation. Results from one
model do not carry over to another. The first time you use a provider and
model pair, start with consult or review rather than write, and judge the
first results especially carefully.
