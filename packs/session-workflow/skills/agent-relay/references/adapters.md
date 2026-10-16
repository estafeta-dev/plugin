# Relay adapters

Load only the section for the transport you use. CLI flags change between
releases: when a command is refused, read that CLI's `--help` and adjust it
without loosening the sandbox. "Docs" marks commands taken from official
documentation that estafeta's own tests have not run yet.

## Orchestrator hosts

The orchestrator can run in any host that has a shell and the estafeta skills.
The cases below were verified live with `scripts/golden/live_orchestrator.py`,
the consult golden path, and `--live-verify`.

| Orchestrator | Worker | Transport | Verified |
| --- | --- | --- | --- |
| T3 Code (any provider) | Codex, Antigravity (Gemini) | T3 `delegate_task` | consult, review, write |
| Claude Code | Codex | `codex exec` | consult |
| Claude Code | Claude subagent | Agent tool, recorded as host | consult |
| Codex | Claude | `claude -p` | consult |
| Codex | Codex subagent | `multi_agent`, recorded as host | consult |
| any shell host | Claude, Codex | `claude -p`, `codex exec` | consult and write (`live_cli.py`) |

What each host needs:

- **Shell commands.** The orchestrator must run the runtime and the worker
  CLI.
  - **Claude Code:** allow Bash, either through your permission mode or with
    `--allowedTools Bash` headless.
  - **Codex:** its sandbox applies to everything it starts, including the
    supervised worker. A nested CLI needs the network and write access to its
    own config directory (`~/.claude` or `CLAUDE_CONFIG_DIR`, `~/.codex`).
    The verified setting was `--sandbox workspace-write -c
    sandbox_workspace_write.network_access=true` with `--add-dir` for those
    directories. Without network, a nested CLI cannot reach its API (not run
    live). A Codex orchestrator that cannot get these permissions should use
    its native subagents or a host such as T3.
- **Native subagents.** They do not run under the runtime, so record them as
  host tasks: `--host-ref` is the subagent's name or path, and `--model` is
  the model it ran, or the orchestrator's own when the host does not say.
  Save its final message to `reply_file`, then collect.
- **Skill copies.** Several copies can coexist: global per provider, project
  `.claude/skills` and `.agents/skills`. An older global copy can shadow a
  newer one. Seen live: Claude Code ran a global 2.4.1 `session-end`, which
  refused the newer state without changing it. Keep installs current with
  `python3 scripts/workflow.py install --all-detected`. The runtime's
  `version` error names the cause.

## Never by default

These flags remove the worker's sandbox or approvals. Use one only when the
user explicitly asks for it for this delegation.

| Provider | Forbidden |
| --- | --- |
| Codex | `--yolo`, `--dangerously-bypass-approvals-and-sandbox`, `--sandbox danger-full-access`, `--ignore-rules` |
| Claude Code | `--dangerously-skip-permissions`, `--allow-dangerously-skip-permissions`, `--permission-mode bypassPermissions` |
| Gemini CLI | `--approval-mode yolo`, `-y`/`--yolo`; `--skip-trust` only as described below |

## Provider IDs

`--provider` names what actually runs, and it must match a row of the
project's AI providers table. Use the plain provider ID (`claude`, `codex`,
`gemini`, `antigravity`). When a host has several accounts of one provider and
the project distinguishes them, use the host's instance ID, such as T3's
`claude-pricefx`.

## Host-native tasks

Prefer these when the host offers them: the host owns authentication,
visibility and cancellation.

- **T3 Code.** `orchestrator_capabilities` lists provider instances, models and
  whether `canRunCrossProviderChildTask` is true. Launch with `delegate_task`:
  the packet text as `task`, `target` = `{providerInstanceId, model}`,
  `mode: "async"`, and the delegation name as `clientRequestId`. For write,
  add `isolation: "worktree"`. T3 creates the worktree from the last local
  commit, so record the delegation without `--workspace`. The runtime learns
  the worker's root when the worker begins its session. Record the returned
  `taskId` as `--host-ref t3:<taskId>`. Use `task_status` and `task_cancel`
  to follow and stop it. For a new review round, start a new `delegate_task`
  with the earlier findings and replies, under a new delegation name.
- **Same-provider subagents** (Claude Code Agent tool, Codex subagents): use
  them when only another model or a fresh context is needed. Record them as
  host tasks with the subagent's ID as `--host-ref`.

## CLI workers

Run through `delegate start ... -- <argv>`. The runtime replaces
`{packet_text}`, `{packet}`, `{reply_file}`, `{workspace}` and `{state_dir}`.
The worker gets no shell and no stdin, and its working directory is
`--workspace`. Always pass `--timeout`. Pass the same model to the CLI that you
record with `--model`; the runtime cannot see which model actually ran.

`collect` reads `{reply_file}` first, then the worker's stdout. Stderr is kept
apart in `stderr.log` because it carries progress and tool output. In JSON
output, only final-answer fields count: Claude's `result`, Gemini's
`response`, and Codex's `agent_message` items. A block quoted inside tool
output is ignored.

A writer must write the shared state directory to record its session, claims
and checks. Grant exactly that directory (`{state_dir}`) in addition to its
workspace. Do not grant the repository's `.git`: the integrator commits.

### Codex (`codex exec`), verified live

| Mode | argv after `--` |
| --- | --- |
| consult, review | `codex exec --sandbox read-only --cd {workspace} --output-last-message {reply_file} -m MODEL {packet_text}` |
| write | `codex exec --sandbox workspace-write --add-dir {state_dir} --cd {workspace} --output-last-message {reply_file} -m MODEL {packet_text}` |

- **Always pass `--sandbox`.** A user's `~/.codex/config.toml` may default to
  `sandbox_mode = "danger-full-access"`, and only the flag overrides it.
  `approval_policy = "never"` is fine headless: a command needing escalation
  fails instead of waiting.
- **Reasoning effort:** `-c model_reasoning_effort="high"`.
- **Login:** Codex needs a Git checkout and an existing `codex login` or
  `CODEX_API_KEY`. The CLI reuses the desktop app's login in `~/.codex`.
- **Instructions and skills:** it reads AGENTS.md and finds skills in
  `.agents/skills` and `~/.agents/skills`.
- **Verified with codex-cli 0.162.1 and gpt-6.1-sol:** consult and a sandboxed
  write in a linked worktree. `collect` read the block from `{reply_file}`.

### Claude Code (`claude -p`), verified live

| Mode | argv after `--` |
| --- | --- |
| consult, review | `claude -p {packet_text} --permission-mode dontAsk --tools Read,Grep,Glob --output-format json --model MODEL --max-budget-usd N` |
| write | `claude -p {packet_text} --permission-mode acceptEdits --settings SANDBOX --output-format json --model MODEL --max-budget-usd N` |

SANDBOX is one argv item:

```json
{"sandbox": {"enabled": true, "failIfUnavailable": true, "allowUnsandboxedCommands": false, "filesystem": {"allowWrite": ["{state_dir}"]}}}
```

- **The OS sandbox is the boundary.** It confines Bash and every process Bash
  starts, and sandboxed commands run without prompts.
  - Writes are allowed only to the workspace, the temp directory and
    `{state_dir}`. A linked worktree also gets its shared `.git`.
  - Permission rules such as `Bash(python3:*)` are not a filesystem boundary,
    so do not use them for writers.
  - File tools follow `acceptEdits` and can write only inside the workspace.
- **When the sandbox fails.** `failIfUnavailable` makes the worker exit on
  native Windows or without the sandbox dependencies; prefer a host task
  there.
- **What `collect` can see.** It reports changes outside the phase paths
  inside the worktree, but not writes elsewhere.
- **Placement.** Put `{packet_text}` right after `-p`: `--tools` and
  `--add-dir` take several values and would swallow a trailing prompt.
- **Cost and denials.** The JSON reply has `result`, `session_id`, `usage`,
  `total_cost_usd` and `permission_denials`. `collect` finds the block in
  `result`.
- **Avoid `--bare` and `-w`.** `--bare` turns off CLAUDE.md and skills; with
  `-w` Claude would make its own worktree.
- **Nesting.** A worker started from inside a Claude Code session ran without
  changes in 2.1.300.
- Do not use `--bare`: it turns off CLAUDE.md and skills.
- Do not use `-w`: the runtime already chose the workspace.
- The JSON reply has `result`, `session_id`, `usage` and `total_cost_usd`;
  `collect` finds the block inside `result`.

### Gemini CLI (`gemini -p`), docs

| Mode | argv after `--` |
| --- | --- |
| consult, review | `gemini -m MODEL -p {packet_text} --output-format json --approval-mode plan` |
| write | `gemini -m MODEL -p {packet_text} --output-format json --approval-mode auto_edit --include-directories {state_dir}` |

- **Personal accounts.** Since June 2026, personal Google accounts use
  Antigravity instead. Gemini CLI keeps working with paid Gemini API, Vertex
  or enterprise keys.
- **Flags.** They match gemini 0.64.0 `--help`.
- **No login.** Without one, the CLI exits with code 41 and prints its error
  as JSON on stderr. `collect` records `malformed` with that exit code and
  stderr, never success (verified).
- **Untrusted folders.** A fresh worktree is an untrusted folder, and Gemini
  then lowers `--approval-mode` to `default`, so a headless writer cannot
  edit. Trusting the folder is the user's decision: add the repository to
  Gemini's trusted folders once, or pass `--skip-trust` for a worktree the
  orchestrator created from a commit it trusts.
- **Prefer Antigravity.** A host-native Antigravity task (for example in T3)
  needs no API key, so prefer it for Gemini models.
- **Exit codes:** 1 means an error, 41 no authentication, 42 bad input, 53 the
  turn limit.

## Resuming a worker

A follow-up round, such as "resend only the block" or a fix delta, goes to the
same worker session when the transport supports it:

- `codex exec resume <id> ...`;
- `claude -p --resume <session_id> ...`;
- a new T3 task carrying the earlier exchange.

Record every round as a new delegation name.
