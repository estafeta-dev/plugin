#!/usr/bin/env python3
"""Live golden path with a real orchestrator outside T3: the agent itself follows agent-relay.

Each case builds a disposable project with project-local copies of the estafeta
skills and an AI providers table, then gives an orchestrator CLI a plain user
request: consult another agent through agent-relay. The run passes when the
recorded state meets the consult-cli golden expectations (`--live-verify`).
These are paid runs; use them only with the user's authorization.

    python3 scripts/golden/live_orchestrator.py --case codex-to-claude
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
PACK = HERE.parents[1] / "packs/session-workflow"
RUNNER = HERE.parent / "test_relay.py"
QUESTION = 'Which file defines `greet`, and what exactly does `greet("Ada")` return?'
CASES = {
    "codex-to-claude": ("codex", "claude", "claude-haiku-5-5",
                        "Run Claude through its CLI (`claude -p`, model claude-haiku-5-5) as a supervised delegate "
                        "worker."),
    "codex-to-native": ("codex", "codex", "gpt-6.1-sol",
                        "Use your own native subagent (a spawned Codex agent) and record it as a host task."),
    "claude-to-codex": ("claude", "codex", "gpt-6.1-sol",
                        "Run Codex through its CLI (`codex exec`, model gpt-6.1-sol) as a supervised delegate worker."),
    "claude-to-native": ("claude", "claude", "claude-haiku-5-5",
                         "Use your own native subagent (the Agent tool, model haiku) and record it as a host task."),
}


def orchestrator_argv(host, root, prompt, sandbox):
    if host == "codex":
        argv = ["codex", "exec", "--cd", str(root), "-m", "gpt-6.1-sol", "--output-last-message",
                str(root.parent / "orchestrator-reply.txt")]
        if sandbox == "workspace-write":
            # Nested worker CLIs need the network and their own config directories.
            argv += ["--sandbox", "workspace-write", "-c", "sandbox_workspace_write.network_access=true"]
            for env, default in (("CLAUDE_CONFIG_DIR", "~/.claude"), ("CODEX_HOME", "~/.codex")):
                argv += ["--add-dir", str(Path(os.environ.get(env, default)).expanduser())]
        elif sandbox != "user-config":
            argv += ["--sandbox", sandbox]
        return argv + [prompt]
    return ["claude", "-p", prompt, "--permission-mode", "acceptEdits", "--allowedTools", "Bash", "Read", "Write",
            "Edit", "Glob", "Grep", "Agent", "--output-format", "json", "--model", "claude-sonnet-5-5",
            "--max-budget-usd", "3"]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case", choices=sorted(CASES), required=True)
    parser.add_argument("--orchestrator-sandbox", default="workspace-write",
                        choices=("workspace-write", "user-config", "read-only"),
                        help="Codex orchestrator only: sandbox to run the orchestrator in")
    parser.add_argument("--timeout", type=int, default=1200)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()
    host, worker, model, hint = CASES[args.case]
    base = Path(tempfile.mkdtemp(prefix=f"relay-orch-{args.case}-")).resolve()
    root = base / "project"
    root.mkdir()
    git = ["git", "-C", str(root), "-c", "user.name=Live Golden", "-c", "user.email=live@example.invalid",
           "-c", "commit.gpgsign=false"]
    subprocess.run([*git, "init", "-q"], check=True)
    (root / ".gitignore").write_text(".agent-state/\n.agents/\n.claude/\n__pycache__/\n")
    (root / "greet.py").write_text('def greet(name: str) -> str:\n    return f"Hello, {name}!"\n')
    rows = {host: "orchestrate, consult", worker: "consult"} if host != worker else {host: "orchestrate, consult"}
    (root / "PROJECT.md").write_text(
        "# Greeter\n\nA one-function fixture project.\n\n## AI providers\n\n<!-- estafeta:providers:start -->\n"
        "| Provider | Allowed | Models | Notes |\n| --- | --- | --- | --- |\n"
        + "".join(f"| {p} | {uses} | any | |\n" for p, uses in rows.items())
        + "<!-- estafeta:providers:end -->\n", encoding="utf-8")
    pointer = "Read PROJECT.md. Use session-start to begin or resume work.\n"
    (root / "AGENTS.md").write_text(pointer)
    (root / "CLAUDE.md").write_text(pointer)
    for skills in (root / ".agents/skills", root / ".claude/skills"):
        shutil.copytree(PACK / "skills", skills)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-qm", "fixture"], check=True)
    prompt = (
        "Use the estafeta skills installed in this project.\n"
        f"1. Start with session-start; use session ID orch-{host}.\n"
        f"2. With agent-relay, consult {worker} and ask: {QUESTION} Name the delegation ask-1. {hint}\n"
        "3. The project's AI providers table allows this, and I authorize this one consult run.\n"
        "4. Collect the result with the runtime, end the session with session-end, then reply with the answer.")
    argv = orchestrator_argv(host, root, prompt, args.orchestrator_sandbox)
    print(f"case {args.case}: orchestrator {host}, worker {worker} ({model}); fixture {base}", flush=True)
    try:
        done = subprocess.run(argv, cwd=root, capture_output=True, text=True, timeout=args.timeout,
                              stdin=subprocess.DEVNULL)
        (base / "orchestrator.out").write_text(done.stdout + "\n--- stderr ---\n" + done.stderr)
        print(f"orchestrator exit {done.returncode}; output in {base / 'orchestrator.out'}")
    except subprocess.TimeoutExpired:
        print("orchestrator timed out")
    status = subprocess.run([sys.executable, str(PACK / "shared/runtime/session.py"), "--root", str(root),
                             "delegate", "status"], capture_output=True, text=True)
    for record in (json.loads(status.stdout).get("result") or {}).get("delegations", []):
        print("delegation:", json.dumps({k: record.get(k) for k in ("name", "provider", "model", "transport",
                                                                     "status", "host_ref", "error")}))
    passed = subprocess.run([sys.executable, str(RUNNER), "--live-verify", "consult-cli", "--root", str(root),
                             "--map", "ask-1=ask-1"]).returncode == 0
    print(("PASS" if passed else "FAIL") + f" {args.case}")
    if passed and not args.keep:
        shutil.rmtree(base, ignore_errors=True)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
