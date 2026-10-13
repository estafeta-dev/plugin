# Installation

Requires Python 3.9+ for the deterministic runtime. Its scripts use only the
standard library. Native plugin installation also requires a host that supports
that plugin format. The repository is public, so cloning needs no login.

```sh
git clone https://github.com/pashbel/estafeta.git
cd estafeta
python3 scripts/workflow.py check
```

Windows may use `py -3` instead of `python3`.
Choose one installation route per provider to avoid duplicate skill discovery.

## Agent installation

These steps are for an agent asked in a chat to install the skills. Follow them
in order. At the first blocker, stop and say what remains. Answer in the user's
language.

1. **Where you run.** Name the machine, OS, agent and active profile. If this is
   not the user's own machine (for example a cloud sandbox), or you lack
   terminal and file access, say so before installing anything.
2. **Python.** Find Python 3.9+: `python3`, `python` or `py -3`.
3. **Source.** Reuse an existing clone and update it only by fast-forward.
   Otherwise run `git clone https://github.com/pashbel/estafeta.git`
   into a stable user directory outside any skills directory. No login is needed.
4. **Route.** If this profile already has the native plugin, update it through
   the host instead of adding a copy. Otherwise use the portable route below.
5. **Install.** Run `scripts/workflow.py check`, then `install --dry-run`,
   `install` and `status`, all with the same target: `--provider <this agent>`
   or `--dest <skills directory>`. Use `--all-detected` only if the user asked
   for all agents.

   `install` writes to the agent's own skills directory. Some hosts guard that
   directory, for example the auto mode of Claude Code. If the host blocks
   `install` and the user has not yet authorized this write, ask in the chat
   before you send them to a terminal. Quote the exact `install` command and
   destination, say that changed skills are backed up first, and ask for
   confirmation in their own words. After a direct confirmation, retry the
   same command once. Never edit host permissions or settings to get past the
   block. If it is blocked again, report the command for the user to run.
6. **Verify.**
   - `status` prints five MATCH lines per destination: session-start,
     plan-and-orchestrate, session-handover, session-end and session-guide.
   - There is no RETIRED-PRESENT line.
   - No other copy shadows these skills.
7. **Finish.** Reload skills if that is possible without ending the chat. Do
   not touch any project's session state. Report:
   - the version and destinations;
   - the verification result;
   - the backup location;
   - any reload step.

   Then suggest a first request: "Use session-guide. Explain how this works."

## Portable skills: any supported provider

This route installs five standalone skills with the same runtime and instructions.
It also works from an extracted full source ZIP.

```sh
python3 scripts/workflow.py install --all-detected --dry-run
python3 scripts/workflow.py install --all-detected
python3 scripts/workflow.py status --all-detected
```

Or choose providers explicitly:

```sh
python3 scripts/workflow.py install --provider codex --provider claude
python3 scripts/workflow.py install --provider gemini --provider opencode
python3 scripts/workflow.py install --provider copilot --provider hermes
python3 scripts/workflow.py install --dest /path/to/custom/profile/skills
```

| Provider option | Default destination |
| --- | --- |
| `codex` | Existing `~/.codex/skills`; otherwise `~/.agents/skills` |
| `claude` | `~/.claude/skills` |
| `gemini` | `~/.gemini/skills` |
| `antigravity` | `~/.gemini/config/skills` |
| `opencode` | `~/.config/opencode/skills` |
| `copilot` | `~/.copilot/skills` |
| `hermes` | `~/.hermes/skills` |
| `kimi` | `~/.kimi/skills` |
| `agents` | `~/.agents/skills` |

The installer respects configured provider homes and detects existing Claude
and Hermes profiles. It changes only these five skills. A changed directory is
backed up intact outside the discovery root before its replacement. Updates are
atomic per skill; rerunning the installer converges after a partial failure.
`status` compares complete directory hashes. Reload skills or start a new host
session afterward. Higher-priority project/plugin copies can shadow global skills.

### Claude Code auto mode

The auto mode classifier treats writes to `~/.claude/skills` as
self-modification. It allows them only when your own message names the change.
To let agents install and update estafeta without asking each time, add an
exception to `~/.claude/settings.json`. The classifier ignores `autoMode` in
project settings.

```json
{
  "autoMode": {
    "allow": [
      "$defaults",
      "Installing or updating the estafeta skill pack (github.com/pashbel/estafeta) with its own `scripts/workflow.py install` and `status` into ~/.claude/skills is allowed: the installer backs up replaced skills."
    ]
  }
}
```

Keep `"$defaults"` or the built-in exceptions are replaced. Check the result
with `claude auto-mode config`.

## Codex plugin

The repo contains an OpenAI marketplace catalog, a portable `plugin.json`, and a
Codex compatibility manifest. On a CLI with the plugin commands below:

```sh
codex plugin marketplace add pashbel/estafeta
codex plugin add estafeta@pashbel-estafeta
codex plugin list --marketplace pashbel-estafeta --json
```

If Git access is configured differently for the host, add the authenticated local
clone with `codex plugin marketplace add .` instead. Open the desktop plugin
browser to install from that marketplace when the installed client uses the UI
for installation. Start a new session and verify the five skills are available.
See [OpenAI packaging documentation](https://developers.openai.com/plugins/build/plugins).

## Claude Code plugin

```sh
claude plugin marketplace add pashbel/estafeta
claude plugin install estafeta@pashbel-estafeta
claude plugin details estafeta
```

The local-clone alternative is `claude plugin marketplace add .`. Reload plugins
or start a new session. Plugin skills use namespaced commands:

```text
/estafeta:session-start
/estafeta:plan-and-orchestrate
/estafeta:session-handover
/estafeta:session-end
/estafeta:session-guide
```

See [Claude marketplace documentation](https://code.claude.com/docs/en/plugin-marketplaces).
Do not enable a duplicate standalone copy alongside the plugin unless you
intentionally select its distinct source. Existing standalone installations can
keep using the portable route without migration.

## Naming compatibility

estafeta is the plugin's new name. Its native plugin ID is `estafeta`, and the
marketplace ID is `pashbel-estafeta`. If the old `session-workflow` native plugin
is enabled, disable it through the host's plugin manager before enabling
estafeta, so the same skills are discovered from one source.

Existing standalone installations can update through the portable installer.
Skill names and saved project records remain compatible: the runtime continues
to use `.agent-state/session-workflow` and the existing handover markers.

## Upgrading from 2.x

`install` backs up and removes the old `handover-changelog` directory only when it
came from this pack; a same-named skill from another pack stays. `status` prints
`RETIRED-PRESENT` while an old copy remains. Native plugin users update the plugin
through the host. Project state written by 2.x is upgraded on its first write and
the original is kept as `.agent-state/session-workflow/state.v1.json`; the removed
operation ledger's unresolved IDs are reported once.

## Updates and other devices

For a clean cloned source checkout:

```sh
git pull --ff-only
python3 scripts/workflow.py check
python3 scripts/workflow.py install --all-detected
python3 scripts/workflow.py status --all-detected
```

Preserve local source edits before pulling. Native plugin users refresh their
marketplace and update/reload the installed plugin through the host. For a local
marketplace, keep its clone at a stable location.

Installing the plugin transfers instructions and scripts. Project files,
uncommitted changes and `.agent-state/session-workflow` evidence need their own
authorized transfer. See [usage](USAGE.md) for session handoff and parallel work.

For copy-route rollback, move the current skill directory aside, then restore its
saved directory from `skill-backups/`; preserve any newer customizations first.
The receipt `.session-workflow-install.json` beside the skill root identifies the
backup. Native plugin installations use the host's plugin manager for removal.
