#!/usr/bin/env python3
"""Golden path integration tests for agent-relay delegation.

Each scenario in golden/relay-scenarios.json is a sequence of orchestrator and
worker interactions with an expected result at every step. The first failed
step fails the whole scenario. By default a deterministic stub stands in for
the LLM worker in a disposable Git repository, so the suite is cheap enough to
run on every change and in CI.

--live-verify SCENARIO runs only the read-only steps marked "verify" against a
project where a real provider performed that scenario, with --map replacing the
scenario's session and delegation IDs by the live ones.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "packs/session-workflow/shared/runtime/session.py"
SCENARIOS = HERE / "golden/relay-scenarios.json"
STUB = HERE / "golden/stub_worker.py"


class StepFailed(Exception):
    pass


def lookup(value, path):
    for part in path.split("."):
        if isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        elif isinstance(value, dict) and part in value:
            value = value[part]
        else:
            return KeyError
    return value


def judge(value, expectations):
    for rule in expectations:
        actual = lookup(value, rule["path"])
        missing = actual is KeyError
        if "equals" in rule and (missing or actual != rule["equals"]):
            raise StepFailed(f"{rule['path']} = {actual!r}, expected {rule['equals']!r}")
        if "in" in rule and (missing or actual not in rule["in"]):
            raise StepFailed(f"{rule['path']} = {actual!r}, expected one of {rule['in']!r}")
        if "contains" in rule and (missing or rule["contains"] not in str(actual)):
            raise StepFailed(f"{rule['path']} = {actual!r}, expected to contain {rule['contains']!r}")
        if rule.get("exists") and missing:
            raise StepFailed(f"{rule['path']} is missing")
        if rule.get("absent") and not missing:
            raise StepFailed(f"{rule['path']} = {actual!r}, expected absent")
        if rule.get("nonempty") and (missing or not actual):
            raise StepFailed(f"{rule['path']} is empty or missing")
        if rule.get("empty") and not missing and actual:
            raise StepFailed(f"{rule['path']} = {actual!r}, expected empty")


class Run:
    def __init__(self, base, root, mapping=None):
        self.root, self.wt, self.packets = root, base / "worker wt", base / "packets"
        self.packets.mkdir(exist_ok=True)
        self.rev, self.mapping = None, mapping or {}

    def fill(self, value):
        if isinstance(value, list):
            return [self.fill(item) for item in value]
        if isinstance(value, dict):
            return {key: self.fill(item) for key, item in value.items()}
        if not isinstance(value, str):
            return value
        value = self.mapping.get(value, value)
        for token, real in (("{root}", self.root), ("{wt}", self.wt), ("{packets}", self.packets),
                            ("{python}", sys.executable), ("{stub}", STUB), ("{rev}", self.rev)):
            value = value.replace(token, str(real))
        return value

    def runtime(self, args, where=None):
        root = self.wt if where == "wt" else self.root
        done = subprocess.run([sys.executable, str(SOURCE), "--root", str(root), *self.fill(args)],
                              capture_output=True, text=True, timeout=300)
        try:
            output = json.loads(done.stdout)
        except ValueError:
            raise StepFailed(f"runtime printed no JSON (exit {done.returncode}): {done.stderr[-500:]}")
        if output.get("revision") is not None:
            self.rev = output["revision"]
        return output

    def step(self, step):
        for name, data in step.get("files", {}).items():
            (self.packets / name).write_text(json.dumps(self.fill(data)), encoding="utf-8")
        action = step["do"]
        if action == "runtime":
            return self.runtime(step["args"], step.get("root"))
        if action == "git":
            where = self.wt if step.get("cwd") == "wt" else self.root
            done = subprocess.run(["git", "-C", str(where), *self.fill(step["args"])], capture_output=True, text=True)
            if done.returncode:
                raise StepFailed("git failed: " + done.stderr[-500:])
            return {"ok": True}
        if action == "packet":
            header = {**self.fill(step["header"]), "version": 1, "runtime": [sys.executable, str(SOURCE)]}
            text = (f"# Relay packet\n\n```relay-packet\n{json.dumps(header, indent=2)}\n```\n\n"
                    f"{self.fill(step['body'])}\n")
            (self.packets / step["file"]).write_text(text, encoding="utf-8")
            return {"ok": True}
        if action == "reply":
            text = f"Done.\n<<<RELAY-RESULT\n{json.dumps(step['result'], indent=2)}\nRELAY-RESULT>>>\n"
            if step.get("json_wrap"):
                text = json.dumps({"type": "result", "result": text, "session_id": "host-session"}) + "\n"
            (self.packets / step["file"]).write_text(text, encoding="utf-8")
            return {"ok": True}
        if action == "wait":
            deadline = time.monotonic() + step.get("timeout", 120)
            while time.monotonic() < deadline:
                view = self.runtime(["delegate", "status", "--name", step["delegation"]])
                if not view["ok"]:
                    raise StepFailed("status failed: " + json.dumps(view["error"]))
                current = view["result"]["delegations"][0]
                if current["status"] != "running":
                    return current
                time.sleep(0.2)
            raise StepFailed("delegation still running at the wait timeout")
        if action == "no_process":
            deadline = time.monotonic() + step.get("timeout", 10)
            while True:  # a stopped process may need a moment to be reaped
                done = subprocess.run(["pgrep", "-f", step["pattern"]], capture_output=True, text=True)
                if not done.stdout.strip() or time.monotonic() > deadline:
                    break
                time.sleep(0.2)
            if done.stdout.strip():
                ps = subprocess.run(["ps", "-o", "pid=,ppid=,pgid=,command=", "-p", ",".join(done.stdout.split())],
                                    capture_output=True, text=True)
                raise StepFailed("process still running: " + (ps.stdout.strip() or done.stdout.strip()))
            return {"ok": True}
        raise StepFailed("unknown action " + action)


def fixture(base):
    root = base / "project"
    root.mkdir()
    for args in (["init", "-q"], ):
        subprocess.run(["git", "-C", str(root), *args], check=True)
    (root / "a.txt").write_text("a\n")
    (root / ".gitignore").write_text(".agent-state/\n")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.name=Golden", "-c", "user.email=golden@example.invalid",
                    "-c", "commit.gpgsign=false", "commit", "-qm", "fixture"], check=True)
    return root


def play(scenario, run, only_verify=False):
    """Run steps in order; the first failure fails the scenario and skips the rest."""
    steps = [s for s in scenario["steps"] if s.get("verify") or not only_verify]
    for number, step in enumerate(steps, 1):
        try:
            result = run.step(step)
            judge(result, step.get("expect", [{"path": "ok", "equals": True}]))
        except (StepFailed, subprocess.TimeoutExpired) as exc:
            print(f"  FAIL step {number}/{len(steps)}: {step['name']}\n       {exc}")
            if len(steps) > number:
                print(f"  skipped {len(steps) - number} later steps")
            return False
        print(f"  ok   step {number}/{len(steps)}: {step['name']}")
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scenario", action="append", help="Run only these scenario IDs")
    parser.add_argument("--live-verify", metavar="SCENARIO", help="Check a live run's recorded state, read-only")
    parser.add_argument("--root", help="Project root for --live-verify")
    parser.add_argument("--map", action="append", default=[], metavar="SCENARIO_ID=LIVE_ID")
    args = parser.parse_args(argv)
    scenarios = json.loads(SCENARIOS.read_text(encoding="utf-8"))["scenarios"]
    if args.live_verify:
        if not args.root:
            parser.error("--live-verify needs --root")
        scenario = next((s for s in scenarios if s["id"] == args.live_verify), None)
        if scenario is None:
            parser.error("unknown scenario " + args.live_verify)
        if not any(step.get("verify") for step in scenario["steps"]):
            parser.error(f"scenario {scenario['id']} has no verify steps; a live run cannot be checked with it")
        mapping = dict(item.split("=", 1) for item in args.map)
        print(f"live verify {scenario['id']}: {scenario['description']}")
        with tempfile.TemporaryDirectory(prefix="relay-live-") as temp:
            passed = play(scenario, Run(Path(temp), Path(args.root).resolve(), mapping), only_verify=True)
        print("PASS" if passed else "FAIL")
        return 0 if passed else 1
    chosen = [s for s in scenarios if not args.scenario or s["id"] in args.scenario]
    env = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
           "SESSION_WORKFLOW_MACHINE_ID": "golden-relay"}
    saved = {key: os.environ.get(key) for key in env}
    os.environ.update(env)
    failed = []
    try:
        for scenario in chosen:
            print(f"scenario {scenario['id']}: {scenario['description']}")
            with tempfile.TemporaryDirectory(prefix="relay-golden-") as temp:
                base = Path(temp).resolve()
                run = Run(base, fixture(base))
                try:
                    if not play(scenario, run):
                        failed.append(scenario["id"])
                finally:
                    # Leave nothing running: cancel open CLI workers.
                    for record in (run.runtime(["delegate", "status"]).get("result") or {}).get("delegations", []):
                        if record["status"] == "running" and record["transport"] == "cli":
                            run.runtime(["delegate", "cancel", "--session", record["session_id"], "--name", record["name"]])
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    print(f"{len(chosen) - len(failed)}/{len(chosen)} golden scenarios passed" +
          (": failed " + ", ".join(failed) if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
