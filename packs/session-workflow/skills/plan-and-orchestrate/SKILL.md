---
name: plan-and-orchestrate
description: >-
  Turn a development, prototype or research task into a resumable phased plan
  with acceptance criteria, then execute the authorized phases with recorded
  checks across sessions, devices and agents. Use for planning or orchestrating
  multi-step work, continuing a plan or coordinating parallel sessions; «составь
  план», «разбей на этапы», «продолжи план», «запусти оркестратор». Planning
  alone does not authorize implementation or paid background runs.
license: Apache-2.0
metadata:
  workflow-pack: session-workflow
  workflow-version: "3.0.0"
---

# Plan and orchestrate

Read the [contract](references/workflow-contract.md) and
[quickstart](references/quickstart.md) once per chat. For parallel agents, also
read [delegation](references/delegation.md). If this chat has no session yet,
run session-start first.

1. **Frame** the outcome, acceptance, constraints and non-goals. Reuse an
   existing plan or tracker and its IDs; import only unfinished scope.
2. **Plan small.** Add a phase boundary only where it helps verification or
   handoff; a small task is one phase. Give each phase:
   - `acceptance`;
   - real write `paths`, including shared docs and generated files;
   - `required_checks`.
3. **Record** the plan, the first claim and a checkpoint in one `batch`. Keep
   reasons and decisions in the plan document ([template](templates/plan.md)).
4. **For a plan-only request,** present the plan and stop.
5. **Execute** authorized phases: claim first and stay inside the phase paths.
6. **Verify** with `check run ... -- <command>`, and judge the acceptance
   yourself. A passing exit code shows only that the command passed.
7. **Close** the phase in one batch: VERIFY, DONE with `acceptance_note`,
   checkpoint. If the runtime lists gaps, close them, or keep VERIFY and name
   the gaps.
8. **Continue** with the next ready phase. At milestones update the handover
   with session-handover; that does not end the session.

- **Stale-dependency `warnings` do not block.** Re-run that dependency's checks
  before delivery.
- **Review:** keep it proportional to risk, and say when it was self-review.
- **Economy:** if the user asks to economize, minimize reads and output and
  skip optional work, but never required checks.
