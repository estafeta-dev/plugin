---
name: session-end
description: >-
  End an estafeta session with a resumable checkpoint: save the next
  action, render final facts into the handover and stop processes this session
  started. Use for session-end, pausing or finishing work on an estafeta
  project, or a device or agent handoff; «сохрани чекпоинт и заверши
  estafeta» or «заверши session-workflow». Finishing one task does not end the session. Not for
  projects already run by another end workflow.
license: Apache-2.0
metadata:
  workflow-pack: session-workflow
  workflow-version: "3.1.0"
---

# Session end

Read the [contract](references/workflow-contract.md) and
[quickstart](references/quickstart.md) once per chat.

1. **Settle evidence.** Let running checks finish, or abandon them after
   verifying they stopped. Unfinished phases stay IN_PROGRESS or VERIFY.
   Collect finished delegations and cancel unneeded ones (agent-relay). `end`
   stops your CLI workers and lists the rest as `open_delegations`: report
   them.
2. **Update the narrative:** the changed next action in PROJECT.md and the
   handover delta (session-handover steps 2-4), not whole documents.
3. **End once:** `end --session ID --next-action "<concrete next step>"
   --handover-output <handover file>`.
   - Add `--keep-runtimes` only if the user wants previews kept.
   - If another session owns the handover path, end without that option.
4. **Stop other processes you started** with the tool that started them. Leave
   anything of uncertain ownership running and say so.
5. **Report:**
   - the result, verification gaps and next action;
   - stopped and kept processes;
   - for a device or agent handoff, the branch, revision and uncommitted work to
     transfer. Installing the skills elsewhere transfers nothing.

If `end` returns an error:

- `handover_after_end`: the session already ended. Fix the file and rerun only
  `handover --output`.
- `session_ended`: another chat superseded or released this one. Report it and
  stop.

The next start must be able to work from files alone. Commits, pushes and
memory changes need a separate request.
