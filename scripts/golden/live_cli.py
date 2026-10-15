#!/usr/bin/env python3
"""Play the consult-cli and write-worktree golden paths live with a provider CLI.

This is the paid, manual half of the golden path tests: a real model replaces
the stub worker. The script builds a disposable fixture, delegates through
the runtime's `delegate` command with the agent-relay adapter for the chosen
provider, integrates the writer's change as the orchestrator would, and then
checks the recorded state with `test_relay.py --live-verify`. It never uses
sandbox-bypass flags. Run it only when the user authorized the cost.

    python3 scripts/golden/live_cli.py --provider codex --model gpt-6.1-sol
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
RUNTIME = HERE.parents[1] / "packs/session-workflow/skills/agent-relay/scripts/session.py"
RUNNER = HERE.parent / "test_relay.py"
SANDBOX = json.dumps({"sandbox": {"enabled": True, "failIfUnavailable": True, "allowUnsandboxedCommands": False,
                                  "filesystem": {"allowWrite": ["{state_dir}"]}}})
# Adapter commands from skills/agent-relay/references/adapters.md; MODEL is replaced below.
PRESETS = {
    "codex": {
        "consult": ["codex", "exec", "--sandbox", "read-only", "--cd", "{workspace}",
                    "--output-last-message", "{reply_file}", "-m", "MODEL", "{packet_text}"],
        "write": ["codex", "exec", "--sandbox", "workspace-write", "--add-dir", "{state_dir}", "--cd", "{workspace}",
                  "--output-last-message", "{reply_file}", "-m", "MODEL", "{packet_text}"],
    },
    "claude": {
        "consult": ["claude", "-p", "{packet_text}", "--permission-mode", "dontAsk", "--tools", "Read,Grep,Glob",
                    "--output-format", "json", "--model", "MODEL", "--max-budget-usd", "1"],
        "write": ["claude", "-p", "{packet_text}", "--permission-mode", "acceptEdits", "--settings", SANDBOX,
                  "--output-format", "json", "--model", "MODEL", "--max-budget-usd", "3"],
    },
    "gemini": {
        "consult": ["gemini", "-m", "MODEL", "-p", "{packet_text}", "--output-format", "json",
                    "--approval-mode", "plan"],
        "write": ["gemini", "-m", "MODEL", "-p", "{packet_text}", "--output-format", "json",
                  "--approval-mode", "auto_edit", "--include-directories", "{state_dir}"],
    },
}
REPLY_RULES = """## Reply

End your final message with exactly one block, valid JSON inside:

```text
<<<RELAY-RESULT
{fields}
RELAY-RESULT>>>
```
"""


def call(root, *args):
    done = subprocess.run([sys.executable, str(RUNTIME), "--root", str(root), *args], capture_output=True, text=True)
    value = json.loads(done.stdout)
    if not value["ok"]:
        raise SystemExit(f"runtime refused {args[:2]}: {json.dumps(value['error'])}")
    return value


def git(root, *args):
    subprocess.run(["git", "-C", str(root), "-c", "user.name=Live Golden", "-c", "user.email=live@example.invalid",
                    "-c", "commit.gpgsign=false", *args], check=True, capture_output=True)


def wait(root, name, limit):
    deadline = time.monotonic() + limit + 30
    while time.monotonic() < deadline:
        view = call(root, "delegate", "status", "--name", name)["result"]["delegations"][0]
        if view["status"] != "running":
            return view
        time.sleep(5)
    raise SystemExit(f"{name} still running")


def packet(header, task, rules, fields):
    return (f"# Relay packet: {header['name']}\n\n```relay-packet\n{json.dumps(header, indent=2)}\n```\n\n"
            "You are a worker for another agent, which orchestrates this project.\n\n"
            f"## Task\n\n{task}\n\n## Rules\n\n{rules}\n\n" + REPLY_RULES.format(fields=fields))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--provider", choices=sorted(PRESETS), required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--mode", choices=("consult", "write", "both"), default="both")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--keep", action="store_true", help="Keep the fixture for inspection")
    args = parser.parse_args()
    if not shutil.which(args.provider):
        raise SystemExit(f"{args.provider} CLI is not on PATH")
    base = Path(tempfile.mkdtemp(prefix=f"relay-live-{args.provider}-")).resolve()
    root, worktree = base / "project", base / "worker wt"
    root.mkdir()
    git(root, "init", "-q")
    (root / ".gitignore").write_text(".agent-state/\n__pycache__/\n")
    (root / "greet.py").write_text('def greet(name: str) -> str:\n    return f"Hello, {name}!"\n')
    git(root, "add", ".")
    git(root, "commit", "-qm", "fixture")
    orch, results = "orch-" + args.provider, {}
    call(root, "begin", "--session", orch)

    def start(name, mode, text, extra):
        (base / (name + ".md")).write_text(text, encoding="utf-8")
        argv = [item.replace("MODEL", args.model) for item in PRESETS[args.provider][mode]]
        (base / (name + ".json")).write_text(json.dumps(argv), encoding="utf-8")
        rev = call(root, "status")["revision"]
        call(root, "delegate", "start", "--session", orch, "--expect-revision", str(rev), "--name", name,
             "--provider", args.provider, "--model", args.model, "--mode", "consult" if mode == "consult" else "write",
             "--packet", str(base / (name + ".md")), "--timeout", str(args.timeout),
             "--argv-file", str(base / (name + ".json")), *extra)
        print(f"{name}: {wait(root, name, args.timeout)['runtime']}")
        view = call(root, "delegate", "collect", "--session", orch, "--name", name)["result"]
        print(f"{name}: {view['status']} {json.dumps(view.get('result') or view.get('error'))[:400]}")
        print(f"{name}: discrepancies {view.get('discrepancies')}")
        return view

    if args.mode in ("consult", "both"):
        header = {"version": 1, "name": "ask-live", "mode": "consult", "orchestrator": orch, "workspace": str(root)}
        start("ask-live", "consult", packet(
            header, 'Which file defines `greet`, and what exactly does `greet("Ada")` return? Read the code.',
            "- Read only. Change no files.",
            '{"outcome": "completed | blocked | failed", "summary": "one sentence", "answer": "the answer"}'), [])
        results["consult-cli"] = ["orch=" + orch, "ask-1=ask-live"]
    if args.mode in ("write", "both"):
        plan = {"phases": [{"id": "P1", "title": "Shout", "acceptance": "shout(name) returns NAME! and rejects empty names",
                            "paths": ["shout.py", "test_shout.py"], "required_checks": ["unit"]}]}
        (base / "plan.json").write_text(json.dumps(plan))
        call(root, "plan", "--session", orch, "--expect-revision", str(call(root, "status")["revision"]),
             "--input", str(base / "plan.json"))
        git(root, "worktree", "add", "-q", "-b", "relay/P1", str(worktree))
        check = [sys.executable, "-m", "unittest", "-q", "test_shout"]
        header = {"version": 1, "name": "write-live", "mode": "write", "orchestrator": orch,
                  "workspace": str(worktree), "runtime": [sys.executable, str(RUNTIME)], "phase": "P1",
                  "worker_session": args.provider + "-w1", "allowed_paths": ["shout.py", "test_shout.py"],
                  "required_checks": {"unit": check}}
        rt = f'{sys.executable} {RUNTIME} --root "{worktree}"'
        rules = f"""- Work only in the workspace above. Do not commit, push, install, publish or change any other file.
- Change only `allowed_paths`. Record your work with the runtime above (quote the workspace path):
  1. `{rt} begin --parallel --session {header['worker_session']}`
  2. `{rt} transition --session {header['worker_session']} --expect-revision R --phase P1 --to IN_PROGRESS`
  3. make the change
  4. `{rt} check run --session {header['worker_session']} --expect-revision R --phase P1 --name unit --timeout 120 -- {' '.join(check)}`
  5. `{rt} transition --session {header['worker_session']} --expect-revision R --phase P1 --to VERIFY`, then
     `{rt} end --session {header['worker_session']} --expect-revision R --next-action "Orchestrator integrates P1"`

  R is the `revision` returned by your previous runtime call. An `ownership` refusal means stop and report blocked.
- Stop and report `blocked` instead of guessing when access, a decision or a dependency is missing."""
        view = start("write-live", "write", packet(
            header, "Create `shout.py` with `shout(name: str) -> str` returning the name upper-cased plus `!` "
            "(`shout(\"ada\") == \"ADA!\"`); it raises `ValueError` for an empty or whitespace-only name. Add "
            "`test_shout.py` (standard-library unittest) covering both. Acceptance: the required check `unit` passes.",
            rules, '{"outcome": "completed | blocked | failed", "summary": "one or two sentences", '
                   f'"worker_session": "{header["worker_session"]}", "changed_files": ["paths"], '
                   '"checks": [{"name": "unit", "result": "pass | fail"}], "gaps": []}'),
            ["--phase", "P1", "--worker-session", header["worker_session"], "--workspace", str(worktree)])
        if view["status"] == "returned" and not view.get("discrepancies"):
            git(worktree, "add", "shout.py", "test_shout.py")
            git(worktree, "commit", "-qm", "P1 by " + header["worker_session"])
            git(root, "merge", "-q", "--ff-only", "relay/P1")
            call(root, "transition", "--session", orch, "--expect-revision", str(call(root, "status")["revision"]),
                 "--phase", "P1", "--to", "VERIFY")
            ran = call(root, "check", "run", "--session", orch, "--expect-revision",
                       str(call(root, "status")["revision"]), "--phase", "P1", "--name", "unit", "--", *check)
            print("integrated check:", ran["result"]["result"])
            call(root, "transition", "--session", orch, "--expect-revision", str(ran["revision"]), "--phase", "P1",
                 "--to", "DONE", "--acceptance-note", "Live worker change reviewed, merged and rechecked")
            git(root, "worktree", "remove", str(worktree))
        results["write-worktree"] = ["orch=" + orch, "write-1=write-live"]
    call(root, "end", "--session", orch, "--expect-revision", str(call(root, "status")["revision"]),
         "--next-action", "Live golden run finished")
    passed = True
    for scenario, mapping in results.items():
        argv = [sys.executable, str(RUNNER), "--live-verify", scenario, "--root", str(root)]
        for item in mapping:
            argv += ["--map", item]
        passed = subprocess.run(argv).returncode == 0 and passed
    print(("PASS" if passed else "FAIL") + f" {args.provider} {args.model}; fixture {base}")
    if not args.keep and passed:
        shutil.rmtree(base, ignore_errors=True)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
