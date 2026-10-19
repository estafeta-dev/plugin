# Continue on another computer

The shared source of truth is https://github.com/estafeta-dev/plugin, branch `main`.
Git transfers source and handover documents. Installed agent skills, credentials,
and the ignored `.agent-state/` runtime are local to each computer.

For a new checkout:

```sh
git clone https://github.com/estafeta-dev/plugin.git estafeta
cd estafeta
```

For an existing checkout, first inspect `git status`. Preserve local changes in
a commit or backup before updating; do not reset or overwrite them.
When the checkout is clean:

```sh
git fetch origin
git switch main
git merge --ff-only origin/main
```

If fast-forward fails, stop and reconcile the divergent history with the agent.
Read PROJECT.md and HANDOVER.md, then ask the agent to use session-start.
Each computer starts its own local session; finish or explicitly release work
on the previous computer before taking over the same scope. The runtime is not
a distributed lock.

If the agent does not have the skills, follow docs/INSTALL.md for that provider.
The repository's runtime can also be invoked directly:

```sh
python3 packs/session-workflow/skills/session-start/scripts/session.py begin
```

Before changing computers again, save the next action in HANDOVER.md and commit
and push the authorized changes. A push makes the result available; each other
checkout still needs an update.
