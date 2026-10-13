---
name: session-handover
description: >-
  Create or update the developer handover of an estafeta project
  (HANDOVER.md by default): what changed and why, checks actually run,
  limitations and next steps, with runtime facts in a generated block. Use for
  session-handover, a milestone handover, «обнови handover» or passing Session
  Workflow work to another developer or agent. Does not end the session. Not for
  a CHANGELOG-handover.md owned by another workflow.
license: Apache-2.0
metadata:
  workflow-pack: session-workflow
  workflow-version: "3.0.0"
---

# Session handover

Read the [contract](references/workflow-contract.md) and
[quickstart](references/quickstart.md) once per chat.

1. **Find the handover** through `documents.handover` or the doc map. A new
   project gets HANDOVER.md from the [template](templates/handover.md). A
   handover owned by another workflow stays theirs.
2. **Inspect the delta** since its last update:
   - commits, staged and untracked files;
   - latest checks (`status`) and decisions.

   If the original base is unknown, name the base you compared against.
3. **Write the delta:**
   - what changed and why, with files or phase IDs;
   - checks with result and scope;
   - limitations and the next action.

   Correct stale statements instead of appending contradictions. Link logs
   instead of pasting them.
4. **Keep these apart:**
   - proof levels: code, automated, UI, device, delivery;
   - suspected and confirmed causes;
   - pre-existing and introduced issues.

   Claim savings only with measurements.
5. **Render facts once** with `handover --output <file>` at a milestone. When
   the session is closing, session-end renders them.
6. **Report** the path and remaining evidence gaps. A handover does not end the
   session, stop processes or authorize a commit.

On a `markers` error, fix the duplicated markers by hand and keep the prose. If
another session owns the handover path, leave rendering to the integrator.
