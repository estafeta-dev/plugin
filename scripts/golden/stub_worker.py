#!/usr/bin/env python3
"""Deterministic stand-in for an LLM worker in golden path tests.

It reads an agent-relay packet, performs the steps the packet asks a real agent
to perform, and ends with a RELAY-RESULT block. Behaviors simulate the failure
modes the orchestrator must catch: a hung worker, a garbled reply and a worker
that claims checks it never ran.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time


def packet_header(path):
    text = Path(path).read_text(encoding="utf-8")
    start = text.index("```relay-packet") + len("```relay-packet")
    return json.loads(text[start:text.index("```", start)])


def runtime(packet, *args):
    done = subprocess.run([*packet["runtime"], "--root", packet["workspace"], *args],
                          capture_output=True, text=True)
    value = json.loads(done.stdout)
    if not value["ok"]:
        raise SystemExit("runtime refused: " + done.stdout)
    return value


def reply(result):
    print("Worker finished; result follows.")
    print("<<<RELAY-RESULT")
    print(json.dumps(result, indent=2))
    print("RELAY-RESULT>>>")


def write(packet, args):
    sid, pid = packet["worker_session"], packet["phase"]
    rev = runtime(packet, "begin", "--parallel", "--session", sid)["revision"]
    rev = runtime(packet, "transition", "--session", sid, "--expect-revision", str(rev),
                  "--phase", pid, "--to", "IN_PROGRESS")["revision"]
    changed = []
    for item in args.edit:
        name, text = item.split("=", 1)
        target = Path(packet["workspace"]) / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + "\n", encoding="utf-8")
        changed.append(name)
    reported = changed[:1] if args.behavior == "lie" else changed
    checks = []
    for name, argv in packet["required_checks"].items():
        if args.behavior == "lie":
            checks.append({"name": name, "result": "pass"})
            continue
        done = runtime(packet, "check", "run", "--session", sid, "--expect-revision", str(rev),
                       "--phase", pid, "--name", name, "--timeout", "900", "--", *argv)
        rev = done["revision"]
        checks.append({"name": name, "result": done["result"]["result"]})
    rev = runtime(packet, "transition", "--session", sid, "--expect-revision", str(rev),
                  "--phase", pid, "--to", "VERIFY")["revision"]
    runtime(packet, "end", "--session", sid, "--expect-revision", str(rev),
            "--next-action", "Orchestrator integrates " + pid)
    reply({"outcome": "completed", "summary": "Edited " + ", ".join(reported), "worker_session": sid,
           "phase": pid, "changed_files": reported, "checks": checks, "gaps": []})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("packet")
    parser.add_argument("--behavior", choices=("normal", "hang", "garbage", "lie"), default="normal")
    parser.add_argument("--answer", default="")
    parser.add_argument("--verdict", default="APPROVE")
    parser.add_argument("--finding", action="append", default=[])
    parser.add_argument("--edit", action="append", default=[], help="path=text inside the workspace")
    args = parser.parse_args()
    packet = packet_header(args.packet)
    if args.behavior == "hang":
        time.sleep(600)
    if args.behavior == "garbage":
        print("I think the task is done.")
        return 0
    if packet["mode"] == "consult":
        reply({"outcome": "completed", "summary": "Answered", "answer": args.answer})
    elif packet["mode"] == "review":
        reply({"outcome": "completed", "summary": "Reviewed", "verdict": args.verdict,
               "findings": [{"location": f, "scenario": "stub", "impact": "stub"} for f in args.finding]})
    else:
        write(packet, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
