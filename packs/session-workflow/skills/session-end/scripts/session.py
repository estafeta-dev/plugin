#!/usr/bin/env python3
"""Deterministic session facts and state. Python 3.9+, standard library only.

No model/API calls of its own (a delegated worker is a command the caller
supplies), no Git writes, no project migration and no kills outside a process
group this runtime supervises. Run --help or a subcommand --help for
the JSON CLI. See references/runtime.md.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import platform
import posixpath
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid

SCHEMA_VERSION = 2
MAX_JSON = 8 * 1024 * 1024
MAX_GIT_OUTPUT = 64 * 1024 * 1024
MAX_FILES = 10000
MAX_HASH_BYTES = 128 * 1024 * 1024
MAX_EVENTS = 500
MAX_CHECK_HISTORY = 10
LOCK_WAIT = float(os.environ.get("SESSION_WORKFLOW_LOCK_WAIT", "10"))
HEARTBEAT_SECONDS = 1.0
HEARTBEAT_EXPIRY = 10.0
BEGIN = "<!-- session-workflow:facts:start -->"
END = "<!-- session-workflow:facts:end -->"
STATES = ("TODO", "IN_PROGRESS", "VERIFY", "DONE", "BLOCKED", "NEEDS_DECISION", "DEFERRED")
TRANSITIONS = {
    "TODO": {"IN_PROGRESS", "BLOCKED", "NEEDS_DECISION", "DEFERRED"},
    "IN_PROGRESS": {"VERIFY", "BLOCKED", "NEEDS_DECISION", "DEFERRED"},
    "VERIFY": {"IN_PROGRESS", "DONE", "BLOCKED", "NEEDS_DECISION", "DEFERRED"},
    "DONE": {"IN_PROGRESS"},
    "BLOCKED": {"TODO", "IN_PROGRESS", "NEEDS_DECISION", "DEFERRED"},
    "NEEDS_DECISION": {"TODO", "IN_PROGRESS", "BLOCKED", "DEFERRED"},
    "DEFERRED": {"TODO"},
}
# Dependency, cache and build output skipped when a project has no Git index.
SKIP_NAMES = frozenset({
    ".git", ".hg", ".svn", ".agent-state", "node_modules", ".venv", "venv", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".next", ".nuxt", ".svelte-kit",
    ".cache", ".parcel-cache", ".turbo", ".gradle", ".idea", "dist", "build", "coverage",
    "target", ".DS_Store"})
LOCK_ERRORS = (OSError,) if os.name == "nt" else (BlockingIOError,)
SUPERVISORS = {}
_SCHEMAS = []


class Problem(Exception):
    def __init__(self, code, message, exit_code=2):
        super().__init__(message)
        self.code, self.exit_code = code, exit_code


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def emit(value):
    # Readable UTF-8 keeps non-English facts compact for the model reading them.
    stream = sys.stdout
    if hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            pass
    print(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False), file=stream)


def object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Problem("invalid_json", f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path):
    if str(path) == "-":
        raw = sys.stdin.read(MAX_JSON + 1)
    else:
        p = Path(path)
        if p.stat().st_size > MAX_JSON:
            raise Problem("too_large", f"JSON exceeds {MAX_JSON} bytes: {p}")
        raw = p.read_text(encoding="utf-8")
    if len(raw.encode("utf-8")) > MAX_JSON:
        raise Problem("too_large", "JSON input exceeds limit")
    try:
        return json.loads(raw, object_pairs_hook=object_pairs,
                          parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    except (ValueError, UnicodeError) as exc:
        raise Problem("invalid_json", str(exc)) from exc


def validate(value, definition):
    """Validate the documented schema subset; reject malformed inputs before effects."""
    if not _SCHEMAS:
        _SCHEMAS.append(read_json(Path(__file__).with_name("session.schema.json")))
    schemas = _SCHEMAS[0]

    def visit(item, rule, path):
        if "$ref" in rule:
            return visit(item, schemas["$defs"][rule["$ref"].split("/")[-1]], path)
        types = {"object": dict, "array": list, "string": str, "integer": int,
                 "number": (int, float), "boolean": bool, "null": type(None)}
        typ = rule.get("type")
        if typ and (not isinstance(item, types[typ]) or
                    typ in ("integer", "number") and isinstance(item, bool)):
            raise Problem("schema", f"{path}: expected {typ}")
        if "enum" in rule and item not in rule["enum"] or "const" in rule and item != rule["const"]:
            raise Problem("schema", f"{path}: unsupported value")
        if isinstance(item, str):
            if len(item) < rule.get("minLength", 0) or len(item) > rule.get("maxLength", 100000):
                raise Problem("schema", f"{path}: invalid string length")
            if "pattern" in rule and not re.fullmatch(rule["pattern"], item):
                raise Problem("schema", f"{path}: invalid format")
        if typ in ("integer", "number"):
            if item < rule.get("minimum", -float("inf")) or item > rule.get("maximum", float("inf")):
                raise Problem("schema", f"{path}: outside allowed range")
        if isinstance(item, dict):
            missing = set(rule.get("required", [])) - item.keys()
            if missing:
                raise Problem("schema", f"{path}: missing {sorted(missing)}")
            props = rule.get("properties", {})
            extra = rule.get("additionalProperties", True)
            for key, val in item.items():
                if key in props:
                    visit(val, props[key], path + "." + key)
                elif extra is False:
                    raise Problem("schema", f"{path}: unknown field {key}")
                elif isinstance(extra, dict):
                    visit(val, extra, path + "." + key)
        if isinstance(item, list):
            if not rule.get("minItems", 0) <= len(item) <= rule.get("maxItems", 10000):
                raise Problem("schema", f"{path}: invalid list length")
            for i, val in enumerate(item):
                visit(val, rule.get("items", {}), f"{path}[{i}]")
    visit(value, schemas["$defs"][definition], definition)


def relative_path(root, value):
    p = Path(value)
    if p.is_absolute() or ".." in p.parts or not p.parts:
        raise Problem("path", f"Expected a project-relative path: {value}")
    target = root / p
    # Refuse symlink components, including the last component; never follow them for writes.
    current = root
    for part in p.parts:
        current = current / part
        if current.is_symlink():
            raise Problem("path", f"Symlink path is not a runtime destination: {value}")
    if root not in target.resolve().parents:
        raise Problem("path", f"Path escapes project: {value}")
    return target


def atomic_write(path, text, durable=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    old_mode = path.stat().st_mode & 0o777 if path.exists() else None
    fd, name = tempfile.mkstemp(prefix=".session-write-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            if durable:
                f.flush()
                os.fsync(f.fileno())
        if old_mode is not None:
            os.chmod(name, old_mode)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@contextmanager
def file_lock(path, wait=None):
    """Wait briefly for a local OS lock; the OS releases it after a crash."""
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + (LOCK_WAIT if wait is None else wait)
    f = open(path, "a+b")
    locked = False
    try:
        while not locked:
            try:
                if os.name == "nt":
                    import msvcrt
                    if f.seek(0, 2) == 0:
                        f.write(b"0"); f.flush()
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except LOCK_ERRORS as exc:
                if time.monotonic() >= deadline:
                    raise Problem("busy", "Another runtime writer holds the local lock; retry shortly", 4) from exc
                time.sleep(0.05)
        yield
    finally:
        if locked and os.name == "nt":
            import msvcrt
            f.seek(0); msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        f.close()


def platform_machine_id():
    if sys.platform.startswith("linux"):
        for name in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            try:
                value = Path(name).read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if value:
                return value
    elif sys.platform == "darwin":
        try:
            out = subprocess.run(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"], capture_output=True,
                                 text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            out = ""
        match = re.search(r'"IOPlatformUUID" = "([^"]+)"', out)
        if match:
            return match.group(1)
    elif os.name == "nt":
        try:
            import winreg
            access = winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0)
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0, access) as key:
                return str(winreg.QueryValueEx(key, "MachineGuid")[0])
        except OSError:
            pass
    return None


def machine_id():
    """Pseudonymous, stable machine identity: hostnames change with networks, hardware IDs do not."""
    raw = os.environ.get("SESSION_WORKFLOW_MACHINE_ID") or platform_machine_id() or "host:" + platform.node()
    return "m-" + hashlib.sha256(("session-workflow/" + raw).encode("utf-8")).hexdigest()[:16]


def git(root, *args, optional=False, limit=MAX_JSON, stdin=None):
    try:
        result = subprocess.run(["git", "-C", str(root), *args], input=stdin, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=60,
                                env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
    except FileNotFoundError:
        if optional:
            return None
        raise Problem("environment", "Git is unavailable", 6)
    except subprocess.TimeoutExpired:
        if optional:
            return None
        raise Problem("git", "Git did not answer within 60 seconds", 6)
    if result.returncode:
        if optional:
            return None
        raise Problem("git", result.stderr.decode("utf-8", "replace")[:1000], 6)
    if len(result.stdout) > limit:
        raise Problem("too_large", "Git output exceeds the bounded snapshot limit", 6)
    return result.stdout


def state_prefix(root, state_dir):
    return state_dir.relative_to(root).as_posix() if root in state_dir.parents else None


def under(name, prefix):
    return prefix is not None and (name == prefix or name.startswith(prefix.rstrip("/") + "/"))


def ignore_patterns(root):
    """Simple patterns from a root .gitignore, for projects that have no Git index yet."""
    try:
        lines = (root / ".gitignore").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return [line.strip().strip("/") for line in lines
            if line.strip() and not line.strip().startswith(("#", "!")) and line.strip().strip("/")]


def skipped(relative, name, patterns):
    if name in SKIP_NAMES:
        return True
    return any(fnmatch.fnmatch(relative if "/" in pattern else name, pattern) for pattern in patterns)


def walk_files(root, start, state_dir, patterns):
    names = []
    for directory, dirs, files in os.walk(start, followlinks=False):
        base = Path(directory)
        kept = []
        for d in sorted(dirs):
            full = base / d
            if full != state_dir and not full.is_symlink() and not skipped(full.relative_to(root).as_posix(), d, patterns):
                kept.append(d)
        dirs[:] = kept
        names.extend(rel for rel in ((base / f).relative_to(root).as_posix() for f in files)
                     if not skipped(rel, rel.rsplit("/", 1)[-1], patterns))
        if len(names) > MAX_FILES:
            raise Problem("too_large", f"More than {MAX_FILES} files outside dependency/build directories; "
                          "run 'git init' with a .gitignore or narrow the phase paths", 6)
    return names


def file_facts(root, names, prefix):
    items, total = {}, 0
    for name in sorted(set(names)):
        if under(name, prefix):
            continue
        if len(items) >= MAX_FILES:
            raise Problem("too_large", f"More than {MAX_FILES} files to fingerprint", 6)
        p = root / name
        # Hash symlinks as links, without traversing targets.
        if p.is_symlink():
            items[name] = {"link": os.readlink(p)}
        elif not p.exists():
            items[name] = {"missing": True}
        elif p.is_file():
            before = p.stat()
            total += before.st_size
            if total > MAX_HASH_BYTES:
                raise Problem("too_large", "Changed files exceed the hash budget", 6)
            content = p.read_bytes()
            after = p.stat()
            if (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
                raise Problem("workspace_changed", f"File changed during snapshot: {name}", 3)
            items[name] = {"sha256": hashlib.sha256(content).hexdigest(),
                           "executable": bool(after.st_mode & 0o111)}
        else:
            # Submodules and nested repositories are recorded, not traversed.
            items[name] = {"directory": True}
    return items


def file_digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_status(raw, prefix):
    chunks, changes, index = raw.split(b"\0"), [], 0
    while index < len(chunks) and chunks[index]:
        entry = chunks[index]
        code, name = entry[:2].decode(), os.fsdecode(entry[3:])
        index += 1
        if not under(name, prefix):
            changes.append({"status": code, "path": name})
        if "R" in code or "C" in code:
            old = os.fsdecode(chunks[index]); index += 1
            if not under(old, prefix):
                changes.append({"status": "source", "path": old})
    return changes


def compact_snapshot(value):
    # Full inventories remain in active checkpoints and explicit --full reads.
    total = value.get("total_paths", len(value["changes"]))
    return {**value, "changes": value["changes"][:5], "total_paths": total, "truncated": total > 5}


def snapshot(root, state_dir):
    # Agents and dev servers write while we read; retry a moving workspace briefly.
    for attempt in range(3):
        try:
            return snapshot_once(root, state_dir)
        except Problem as exc:
            if exc.code != "workspace_changed" or attempt == 2:
                raise
            time.sleep(0.2)


def snapshot_once(root, state_dir):
    prefix = state_prefix(root, state_dir)
    top = git(root, "rev-parse", "--show-toplevel", optional=True)
    if top is None:
        try:
            files = file_facts(root, walk_files(root, root, state_dir, ignore_patterns(root)), prefix)
        except Problem as exc:
            if exc.code != "too_large":
                raise
            return {"kind": "files", "head": None, "branch": None, "changes": [], "fingerprint": None,
                    "limited": True, "coverage": "not fingerprinted: " + str(exc)}
        return {"kind": "files", "head": None, "branch": None, "changes": sorted(files),
                "fingerprint": digest(files),
                "coverage": "regular files; dependency/build directories and simple .gitignore patterns skipped"}
    if Path(os.fsdecode(top).strip()).resolve() != root:
        raise Problem("workspace", "Use --root at the Git repository root", 6)
    head_raw = git(root, "rev-parse", "--verify", "HEAD", optional=True)
    head = head_raw.decode().strip() if head_raw else None
    branch_raw = git(root, "symbolic-ref", "--short", "HEAD", optional=True)
    branch = branch_raw.decode().strip() if branch_raw else None
    status = git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all", limit=MAX_GIT_OUTPUT)
    changes = parse_status(status, prefix)
    staged = git(root, "diff", "--cached", "--raw", "-z", "--no-renames", "--no-abbrev",
                 optional=True, limit=MAX_GIT_OUTPUT)
    if staged is None:
        staged = git(root, "ls-files", "--stage", "-z", limit=MAX_GIT_OUTPUT)
    basis = {"head": head, "status": hashlib.sha256(status).hexdigest(),
             "staged": hashlib.sha256(staged).hexdigest()}
    try:
        if len(changes) > MAX_FILES:
            raise Problem("too_large", f"{len(changes)} changed or untracked paths", 6)
        files = file_facts(root, [x["path"] for x in changes], prefix)
    except Problem as exc:
        if exc.code != "too_large":
            raise
        return {"kind": "git", "head": head, "branch": branch, "changes": changes[:20],
                "total_paths": len(changes), "fingerprint": digest(basis), "limited": True,
                "coverage": "status only, contents not hashed: " + str(exc)}
    if status != git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all", limit=MAX_GIT_OUTPUT):
        raise Problem("workspace_changed", "Git status changed during snapshot; retry the read", 3)
    return {"kind": "git", "head": head, "branch": branch, "changes": changes,
            "fingerprint": digest({**basis, "files": files}),
            "coverage": "Git index and nonignored changed/untracked files"}


def snapshot_warnings(live):
    if not live or not live.get("limited"):
        return []
    if live["kind"] == "git":
        return [f"{live.get('total_paths')} changed or untracked paths: add generated or dependency "
                "directories (for example node_modules/) to .gitignore; drift detection is reduced"]
    return ["Workspace too large to fingerprint without Git: run 'git init' with a .gitignore; "
            "drift detection is off"]


def blob_hashes(root, names):
    """Git blob IDs after clean filters, so unchanged content matches its index entry."""
    if not names:
        return []
    if any("\n" in n or "\r" in n for n in names):
        result = []
        for name in names:
            content = (root / name).read_bytes()
            result.append(hashlib.sha1(b"blob %d\0" % len(content) + content).hexdigest())
        return result
    out = git(root, "hash-object", "--stdin-paths", stdin=b"\n".join(os.fsencode(n) for n in names) + b"\n",
              limit=MAX_GIT_OUTPUT).decode().split()
    if len(out) != len(names):
        raise Problem("git", "Unexpected git hash-object output", 6)
    return out


def scope_inventory(store, state, p):
    """Content identities of non-ignored files in a phase scope. Commits alone do not change it."""
    root, prefix = store.root, state_prefix(store.root, store.directory)
    whole = "*" in p["paths"]
    skip = list(p.get("exclude", []))
    if whole:
        # Narrative documents change at every milestone; they are not product inputs.
        skip += [value for value in state["documents"].values() if value]
    if store.is_git:
        spec = [] if whole else ["--", *p["paths"]]
        inventory, changed = {}, set()
        listed = git(root, "--literal-pathspecs", "ls-files", "-s", "-z", *spec, limit=MAX_GIT_OUTPUT)
        for entry in listed.split(b"\0"):
            if entry:
                meta, raw_name = entry.split(b"\t", 1)
                mode, sha, stage = meta.decode().split()
                name = os.fsdecode(raw_name)
                if stage == "0":
                    inventory[name] = mode + ":" + sha
                else:
                    changed.add(name)
        status = git(root, "--literal-pathspecs", "status", "--porcelain=v1", "-z", "--untracked-files=all",
                     *spec, limit=MAX_GIT_OUTPUT)
        changed.update(x["path"] for x in parse_status(status, prefix))
        hashable = []
        for name in sorted(changed):
            target = root / name
            if target.is_symlink():
                inventory[name] = "link:" + os.readlink(target)
            elif target.is_file():
                hashable.append(name)
            elif not target.exists():
                inventory.pop(name, None)
            else:
                inventory[name] = "directory"
        if len(hashable) > MAX_FILES:
            raise Problem("too_large", f"{len(hashable)} changed or untracked files in the phase scope; add "
                          "generated directories to .gitignore or narrow the phase paths", 6)
        for name, sha in zip(hashable, blob_hashes(root, hashable)):
            if os.name == "nt":
                # Windows reports every file as executable and Git there ignores file modes: keep the index mode.
                mode = inventory[name].split(":")[0] if name in inventory else "100644"
            else:
                mode = "100755" if os.access(root / name, os.X_OK) else "100644"
            inventory[name] = mode + ":" + sha
    else:
        patterns, names = ignore_patterns(root), []
        for value in (["*"] if whole else p["paths"]):
            target = root if value == "*" else relative_path(root, value)
            if target.is_dir() and not target.is_symlink():
                names += walk_files(root, target, store.directory, patterns)
            elif target.exists() or target.is_symlink():
                names.append(target.relative_to(root).as_posix())
        inventory = file_facts(root, names, prefix)
    return {name: value for name, value in inventory.items()
            if not under(name, prefix) and not any(under(name, s) for s in skip)}


def phase_fingerprint(store, state, p, inventory=None):
    if inventory is None:
        inventory = scope_inventory(store, state, p)
    return digest({"inputs": inventory, "paths": p["paths"], "exclude": p.get("exclude", []),
                   "acceptance": p["acceptance"], "required_checks": p["required_checks"]})


def check_plan(phases):
    by_id = {p["id"]: p for p in phases}
    if len(by_id) != len(phases):
        raise Problem("plan", "Duplicate phase ID")
    pending = {pid: set(p["depends_on"]) for pid, p in by_id.items()}
    for pid, deps in pending.items():
        if deps - by_id.keys():
            raise Problem("plan", f"Unknown dependencies in {pid}: {sorted(deps - by_id.keys())}")
    while pending:
        available = {pid for pid, deps in pending.items() if not deps}
        if not available:
            raise Problem("plan", "Dependency cycle")
        pending = {pid: deps - available for pid, deps in pending.items() if pid not in available}
    for p in phases:
        for value in p["paths"] + p.get("exclude", []):
            path = Path(value)
            if value != "*" and (path.is_absolute() or ".." in path.parts or
                                 any(c in value for c in "*?[]") or not path.parts):
                raise Problem("plan", "Phase paths must be relative file/directory names, or '*'")
        if "*" in p.get("exclude", []):
            raise Problem("plan", "exclude lists generated files or directories, not '*'")


def phase(state, pid):
    try:
        return next(p for p in state["phases"] if p["id"] == pid)
    except StopIteration:
        raise Problem("phase", "Unknown phase: " + pid)


def paths_overlap(left, right):
    for a in left:
        for b in right:
            a, b = a.rstrip("/").casefold(), b.rstrip("/").casefold()
            if a == "*" or b == "*" or a == b or a.startswith(b + "/") or b.startswith(a + "/"):
                return True
    return False


def claim_conflicts(state, candidate, session_id):
    actor = state["sessions"][session_id]
    conflicts = []
    for p in state["phases"]:
        owner = p["owner"]
        if owner and owner != session_id:
            other = state["sessions"][owner]
            same_checkout = actor["machine"] == other["machine"] and actor["root"] == other["root"]
            if p["id"] == candidate["id"] or same_checkout and paths_overlap(candidate["paths"], p["paths"]):
                conflicts.append({"phase": p["id"], "owner": owner, "paths": p["paths"]})
    return conflicts


def dependency_ids(state, p):
    seen, stack = [], list(p["depends_on"])
    while stack:
        pid = stack.pop()
        if pid not in seen:
            seen.append(pid)
            stack.extend(phase(state, pid)["depends_on"])
    return seen


def ready(state, session_id=None):
    done = {p["id"] for p in state["phases"] if p["state"] == "DONE"}
    candidates = [p for p in state["phases"] if p["state"] in ("TODO", "IN_PROGRESS", "VERIFY")
                  and set(dependency_ids(state, p)) <= done
                  and (session_id is None or not claim_conflicts(state, p, session_id))]
    return sorted(candidates, key=lambda p: ({"IN_PROGRESS": 0, "VERIFY": 1, "TODO": 2}[p["state"]],
                                            p["priority"], p["id"]))


def prune_checks(state):
    # Keep recent history per check name; older logs are superseded evidence.
    groups = {}
    for check in state["checks"].values():
        if check["result"] != "running":
            groups.setdefault((check["phase"], check["name"]), []).append(check)
    removed = []
    for records in groups.values():
        records.sort(key=lambda c: c["sequence"])
        for old in records[:-MAX_CHECK_HISTORY]:
            del state["checks"][old["id"]]
            if old["provenance"] == "executed":
                removed.append(old["evidence"])
    return removed


def migrate_v1(state, store):
    """One-way upgrade from schema 1. The original file is kept as state.v1.json on the next save."""
    here = platform.node()

    def machine_of(host):
        return store.machine if host == here else "legacy-" + hashlib.sha256(host.encode("utf-8")).hexdigest()[:12]
    try:
        for s in state["sessions"].values():
            s["machine"] = machine_of(s["host"])
            s["parallel"] = False
            s["ended_reason"] = "" if s["status"] == "active" else "ended"
        for p in state["phases"]:
            p.setdefault("exclude", [])
        for record in state["processes"].values():
            record["machine"] = machine_of(record.pop("host"))
        dropped = sorted(op["id"] for op in state.pop("operations").values()
                         if op["status"] in ("pending", "outcome-unknown", "prepared", "known-not-applied"))
        state.pop("source_key")
        state["events"] = state["events"][-MAX_EVENTS:]
    except (KeyError, TypeError, AttributeError) as exc:
        raise Problem("state", f"Cannot upgrade schema 1 state ({exc}); it was not modified")
    state["schema_version"] = SCHEMA_VERSION
    note = "Upgraded state schema 1 to 2; the operation ledger was removed"
    if dropped:
        note += "; unresolved operations to check manually: " + ", ".join(dropped)
    return state, note


class Store:
    def __init__(self, root, directory=None):
        self.root = Path(root).expanduser().resolve()
        if not self.root.is_dir():
            raise Problem("workspace", "Workspace does not exist", 6)
        self.machine = machine_id()
        common = git(self.root, "rev-parse", "--git-common-dir", optional=True)
        self.is_git = common is not None
        self.main = self.root
        if directory is not None:
            path = Path(directory).expanduser()
            self.directory = path.resolve() if path.is_absolute() else relative_path(self.root, directory)
        else:
            # Git lists the main checkout first; linked worktrees use its one coordinator.
            worktrees = git(self.root, "worktree", "list", "--porcelain", "-z", optional=True) if common else None
            if worktrees:
                self.main = Path(os.fsdecode(worktrees.split(b"\0")[0][9:])).resolve()
            self.directory = relative_path(self.main, ".agent-state/session-workflow")
        self.path = self.directory / "state.json"
        self.migration = None

    def load(self):
        if not self.path.exists():
            raise Problem("not_initialized", "No session state yet; run begin first")
        if self.path.is_symlink():
            raise Problem("path", "State must not be a symlink")
        state = read_json(self.path)
        if not isinstance(state, dict) or state.get("schema_version") not in (1, SCHEMA_VERSION):
            raise Problem("version", "Unsupported state schema; it was not modified")
        if state["schema_version"] == 1:
            state, self.migration = migrate_v1(state, self)
        validate(state, "state")
        check_plan(state["phases"])
        for p in state["phases"]:
            if p["owner"] and (p["owner"] not in state["sessions"] or
                              state["sessions"][p["owner"]]["status"] != "active"):
                raise Problem("state", "Phase owner must identify an active session")
        return state

    def save(self, state, event):
        state["revision"] += 1
        state["updated_at"] = now()
        if self.migration:
            state["events"].append({"revision": state["revision"], "at": state["updated_at"], "event": self.migration})
        state["events"].append({"revision": state["revision"], "at": state["updated_at"], "event": event})
        state["events"] = state["events"][-MAX_EVENTS:]
        stale_logs = prune_checks(state)
        validate(state, "state")
        text = json.dumps(state, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False) + "\n"
        if len(text.encode()) > MAX_JSON:
            raise Problem("too_large", "State is full; defer or remove finished phases before extending the plan")
        if self.path.exists():
            previous = self.path.read_text(encoding="utf-8")
            if self.migration and not (self.directory / "state.v1.json").exists():
                atomic_write(self.directory / "state.v1.json", previous)
            atomic_write(self.directory / "state.previous.json", previous)
        atomic_write(self.path, text)
        self.migration = None
        for name in stale_logs:
            try:
                (self.directory / name).unlink()
            except OSError:
                pass
        ensure_ignored(self)

    def expect(self, state, revision, required=False):
        if revision is None:
            if required:
                raise Problem("arguments", "--expect-revision is required for this command")
            return
        if state["revision"] != revision:
            raise Problem("stale_revision", f"Expected revision {revision}; current is {state['revision']}. Read status and reconcile.", 3)

    def observe(self):
        return snapshot(self.root, self.directory)


def ensure_ignored(store):
    """Keep runtime logs and machine facts out of commits unless the project already versions them."""
    marker = store.directory / ".gitignore"
    if marker.exists() or store.main not in store.directory.parents:
        return
    if store.is_git:
        tracked = git(store.main, "ls-files", "-z", "--", store.directory.relative_to(store.main).as_posix(),
                      optional=True)
        if tracked is None or tracked:
            return
    atomic_write(marker, "# estafeta runtime state: local logs and machine facts.\n*\n")


def location(s, store):
    if s["machine"] != store.machine:
        return "other machine"
    if s["root"] == str(store.root):
        return "this checkout"
    return "other checkout" if Path(s["root"]).exists() else "missing checkout"


def session(state, store, session_id, require_active=True):
    actor = state["sessions"].get(session_id)
    if not actor:
        raise Problem("session", "Unknown session ID; begin a new session")
    if require_active and actor["status"] != "active":
        raise Problem("session_ended", f"Session {session_id} has ended ({actor['ended_reason']}). If another chat "
                      "took over, stop editing and tell the user; to keep working alongside it, begin a new "
                      "session with --parallel.", 3)
    if actor["machine"] != store.machine or actor["root"] != str(store.root):
        raise Problem("session_foreign", "This session belongs to another machine or checkout path; begin a new "
                      "session here and release the old one once the user confirms it stopped", 3)
    return actor


def brief(state, store, session_id=None, live=None):
    actor = state["sessions"].get(session_id) or {}
    checkpoint = actor.get("checkpoint") or {}
    others, ended = [], 0
    for sid, s in sorted(state["sessions"].items()):
        if sid == session_id:
            continue
        if s["status"] != "active":
            ended += 1
            continue
        others.append({"id": sid, "where": location(s, store), "parallel": s["parallel"],
                       "claims": [p["id"] for p in state["phases"] if p["owner"] == sid],
                       "next_action": s["checkpoint"].get("next_action", "")})
    recorded = (checkpoint.get("workspace") or {}).get("fingerprint")
    observed = (live or {}).get("fingerprint")
    result = {"project_id": state["project_id"], "revision": state["revision"], "session_id": session_id,
              "next_action": checkpoint.get("next_action", ""), "checkpoint": checkpoint.get("id"),
              "documents": state["documents"], "phase_count": len(state["phases"]),
              "phases": [{"id": p["id"], "state": p["state"], "owner": p["owner"]} for p in state["phases"][:50]],
              "ready": [p["id"] for p in ready(state, session_id if actor.get("status") == "active" else None)[:20]],
              "other_active_sessions": others, "ended_sessions": ended,
              "workspace_changed": None if recorded is None or observed is None else recorded != observed,
              "live_workspace": compact_snapshot(live) if live is not None else None}
    if actor and actor["status"] != "active":
        result["session_status"] = "ended: " + actor["ended_reason"]
    delegations = relay_open(store)
    if delegations:
        result["open_delegations"] = [{"name": r["name"], "provider": r["provider"], "mode": r["mode"],
                                       "status": r["status"], "orchestrator": r["session_id"]} for r in delegations[:20]]
    warnings = snapshot_warnings(live)
    if warnings:
        result["warnings"] = warnings
    return result


def initial_state(store, args):
    for value in (args.context, args.plan, args.handover):
        if value:
            relative_path(store.root, value)
    return {"schema_version": SCHEMA_VERSION, "project_id": uuid.uuid4().hex,
            "revision": 0, "created_at": now(), "updated_at": now(),
            "documents": {"context": args.context, "plan": args.plan, "handover": args.handover},
            "sessions": {}, "phases": [], "checks": {}, "processes": {}, "events": []}


def new_checkpoint(store, state, session_id, next_action, note="", workspace=None):
    state["sessions"][session_id]["checkpoint"] = {
        "id": f"{session_id}-{state['revision'] + 1}", "at": now(), "next_action": next_action, "note": note,
        "workspace": workspace if workspace is not None else store.observe()}


def compact_checkpoint(s):
    # Ended sessions keep their resume point and fingerprint, not a full path inventory.
    workspace = s["checkpoint"].get("workspace")
    if workspace and len(workspace.get("changes", [])) > 5:
        s["checkpoint"]["workspace"] = compact_snapshot(workspace)


def live_checks(store, state, session_id):
    """A held runner lock proves that a session's check is still executing."""
    alive = []
    for check in state["checks"].values():
        if check["session_id"] == session_id and check["result"] == "running":
            try:
                with file_lock(store.directory / "checks" / (check["id"] + ".lock"), wait=0):
                    pass
            except Problem:
                alive.append(check["id"])
    return alive


def retire(store, state, session_id, reason, successor=None):
    s = state["sessions"][session_id]
    s.update(status="ended", ended_at=now(), ended_reason=reason)
    compact_checkpoint(s)
    transferred, released, runtimes = [], [], []
    for p in state["phases"]:
        if p["owner"] == session_id:
            p["owner"] = ""
            if successor and not claim_conflicts(state, p, successor):
                p["owner"] = successor
                transferred.append(p["id"])
            else:
                released.append(p["id"])
    for check in state["checks"].values():
        if check["session_id"] == session_id and check["result"] == "running":
            check["result"] = "abandoned"
            check["evidence"] += "; " + reason
    if successor:
        for key, record in list(state["processes"].items()):
            name = key.split("/", 1)[1]
            if record["session_id"] == session_id and record["machine"] == store.machine \
                    and successor + "/" + name not in state["processes"]:
                record["session_id"] = successor
                state["processes"][successor + "/" + name] = state["processes"].pop(key)
                runtimes.append(name)
    return {"transferred": transferred, "released": released, "runtimes": runtimes}


def prior_checkpoint(state, store):
    """The most relevant previous resume point: this checkout, then a moved one, then other machines."""
    tiers = {"this checkout": 0, "missing checkout": 1, "other machine": 2, "other checkout": 3}
    best = None
    for sid, s in state["sessions"].items():
        if s["checkpoint"]:
            key = (-tiers[location(s, store)], s["checkpoint"].get("at", ""))
            if best is None or key > best[0]:
                best = (key, sid, s)
    return best


def parse_time(value):
    try:
        return datetime.fromisoformat(value).timestamp()
    except (TypeError, ValueError):
        return 0.0


def last_activity(store, state, session_id):
    """Latest moment the runtime saw this session act: begin, checkpoints, its events, checks and delegations."""
    s = state["sessions"][session_id]
    times = [parse_time(s["started_at"]), parse_time((s.get("checkpoint") or {}).get("at"))]
    runs = {c["id"] for c in state["checks"].values() if c["session_id"] == session_id}
    for event in state["events"]:
        target = event.get("event", "").split(":", 1)[-1]
        if target == session_id or target in runs:
            times.append(parse_time(event.get("at")))
    for record in relay_records(store):
        if record["session_id"] == session_id:
            times += [parse_time(record.get("started_at")), parse_time(record.get("finished_at"))]
    return max(times)


def takeover_blockers(store, state, candidates):
    """Sessions a solo begin must not take over: recently active ones, or those with open delegations."""
    idle = 60 * float(os.environ.get("SESSION_WORKFLOW_TAKEOVER_IDLE_MINUTES", "30"))
    delegating = {r["session_id"] for r in relay_open(store)}
    blockers = []
    for sid in candidates:
        quiet = time.time() - last_activity(store, state, sid)
        if sid in delegating:
            blockers.append(f"{sid} has open delegations")
        elif quiet < idle:
            blockers.append(f"{sid} was active {int(quiet // 60)} min ago")
    return blockers


def begin(store, args):
    with file_lock(store.directory / ".lock"):
        state = store.load() if store.path.exists() else initial_state(store, args)
        session_id = args.session or "s-" + uuid.uuid4().hex[:8]
        validate(session_id, "id")
        if session_id in state["sessions"]:
            raise Problem("session_exists", "Session ID already used; omit --session to get a new unique ID", 3)
        live = store.observe()
        prior = prior_checkpoint(state, store)
        here = sorted(sid for sid, s in state["sessions"].items()
                      if s["status"] == "active" and location(s, store) == "this checkout")
        # One --parallel puts the checkout in parallel mode until every session here has ended or
        # been released: nobody here is taken over, and new sessions join instead of superseding.
        parallel_here = [sid for sid in here if state["sessions"][sid]["parallel"]]
        joined = bool(parallel_here) and not args.parallel
        # Another thread or agent may still be working here (T3 runs several threads in one folder):
        # a solo begin does not take over a recently active session; it joins in parallel instead.
        guarded = [] if args.parallel or joined else takeover_blockers(
            store, state, [sid for sid in here if live_checks(store, state, sid) == []])
        if guarded:
            joined = True
            for sid in here:
                state["sessions"][sid]["parallel"] = True
        if args.parallel:
            for sid in here:
                state["sessions"][sid]["parallel"] = True
        state["sessions"][session_id] = {"status": "active", "machine": store.machine, "host": platform.node(),
            "root": str(store.root), "started_at": now(), "ended_at": "", "ended_reason": "",
            "parallel": args.parallel or joined, "checkpoint": {}}
        superseded = []
        if not args.parallel and not joined:
            # Solo mode: one writer per checkout, so earlier non-parallel chats here have stopped.
            for sid, s in sorted(state["sessions"].items()):
                if sid == session_id or s["status"] != "active" or s["parallel"] or \
                        location(s, store) not in ("this checkout", "missing checkout"):
                    continue
                alive = live_checks(store, state, sid)
                if alive:
                    raise Problem("session_alive", f"Session {sid} is running check {alive[0]} right now. Wait "
                                  "for it, or begin with --parallel to work alongside it.", 3)
                superseded.append({"id": sid, **retire(store, state, sid, "superseded by " + session_id, session_id)})
        next_action = args.next_action or (prior[2]["checkpoint"].get("next_action", "") if prior else "") or \
            "Inspect the plan and choose a ready phase"
        new_checkpoint(store, state, session_id, next_action, workspace=live)
        store.save(state, "begin:" + session_id)
        for item in superseded:
            relay_transfer(store, item["id"], session_id)
        result = brief(state, store, session_id, live)
        if superseded:
            result["superseded"] = superseded
        if guarded:
            result["warnings"] = result.get("warnings", []) + [
                "Another session here may still be working (" + "; ".join(guarded) + "), so this session joined "
                "in parallel and took over nothing. Claim paths no one else claims. If that chat has stopped, "
                "confirm with the user and release it."]
        elif joined:
            result["warnings"] = result.get("warnings", []) + [
                "Parallel work is in progress in this checkout (" + ", ".join(parallel_here) + "); this session "
                "joined it and took over nothing. Claim paths no one else claims; release a session only after "
                "the user confirms its chat stopped."]
        if prior:
            _, sid, s = prior
            recorded = (s["checkpoint"].get("workspace") or {}).get("fingerprint")
            result["prior_checkpoint"] = {"id": s["checkpoint"].get("id"), "session": sid, "where": location(s, store),
                "next_action": s["checkpoint"].get("next_action", ""), "note": s["checkpoint"].get("note", ""),
                "workspace_changed": None if recorded is None or live.get("fingerprint") is None
                else recorded != live["fingerprint"]}
        return state, result


def verification_gaps(store, state, p):
    """Explain why fresh evidence does not cover a phase; an empty list satisfies the DONE gate."""
    try:
        fingerprint = phase_fingerprint(store, state, p)
    except Problem as exc:
        return ["phase inputs cannot be fingerprinted: " + str(exc)]
    latest = {}
    for c in sorted((c for c in state["checks"].values() if c["phase"] == p["id"]), key=lambda c: c["sequence"]):
        latest[c["name"]] = c

    def gap(c):
        if c["result"] != "pass":
            return "latest result is " + c["result"]
        if not c["stable_inputs"]:
            changed = ", ".join(c.get("changed_during_check") or []) or "unknown files"
            return ("the check modified files in the phase scope while running (" + changed + "); list generated "
                    "outputs in the phase 'exclude' or .gitignore, then run it again")
        if c["fingerprint"] != fingerprint:
            return "phase files or contract changed after this check; run it again"
        if c["provenance"] == "executed":
            log = store.directory / c["evidence"]
            if not log.is_file() or file_digest(log) != c["evidence_sha256"]:
                return "evidence log is missing or was modified"
        return None
    gaps = []
    for name in p["required_checks"]:
        c = latest.get(name)
        if c is None:
            gaps.append(name + ": not run yet")
        elif c["provenance"] != "executed":
            gaps.append(name + ": needs an executed check; reported evidence cannot replace it")
        elif gap(c):
            gaps.append(name + ": " + gap(c))
    if not p["required_checks"] and not any(gap(c) is None for c in latest.values()):
        gaps.append("no fresh passing check; use 'check run', or 'check record' for manual evidence")
    return gaps


def facts_markdown(store, state, live):
    def cell(value):
        return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ").replace("<", "&lt;")
    latest = {}
    for check in sorted(state["checks"].values(), key=lambda item: item["sequence"]):
        latest[(check["phase"], check["name"])] = check
    rows = []
    for p in state["phases"]:
        items = []
        try:
            fingerprint = phase_fingerprint(store, state, p) if any(k[0] == p["id"] for k in latest) else None
        except Problem:
            fingerprint = None
        for (pid, name), check in latest.items():
            if pid == p["id"]:
                fresh = "inputs match" if check["fingerprint"] == fingerprint else \
                    "inputs unknown" if fingerprint is None else "inputs changed"
                items.append(f"{name}: {check['result']} ({check['provenance']}, {fresh})")
        rows.append(f"| {cell(p['id'])} | {p['state']} | {cell(p['owner'] or '-')} | {cell('; '.join(items) or '-')} |")
    active = [(sid, s) for sid, s in sorted(state["sessions"].items()) if s["status"] == "active"]
    ended = [(sid, s) for sid, s in state["sessions"].items() if s["status"] != "active"]
    lines = [BEGIN, "## Session facts (generated)", "",
             f"State revision {state['revision']}; HEAD {cell(live.get('head') or 'non-Git/unborn')}.", "",
             "| Phase | State | Owner | Latest checks |", "| --- | --- | --- | --- |", *rows, "",
             "Active sessions: " + ("; ".join(f"{cell(sid)} (next: {cell(s['checkpoint'].get('next_action', ''))})"
                                              for sid, s in active) or "none") + "."]
    delegations = relay_open(store)
    if delegations:
        lines.append("Open delegations: " + "; ".join(f"{cell(r['name'])} ({cell(r['provider'])} {r['mode']}, "
                                                      f"{r['status']})" for r in delegations[:10]) + ".")
    if ended:
        sid, s = max(ended, key=lambda item: item[1]["ended_at"])
        lines.append(f"Ended sessions: {len(ended)}; latest {cell(sid)} "
                     f"(next: {cell(s['checkpoint'].get('next_action', ''))}).")
    lines += ["", "Generated facts do not establish acceptance, explain intent or prove delivery.", END]
    return "\n".join(lines) + "\n"


def render_target(store, output):
    target = relative_path(store.root, output)
    if target == store.path or target.name in ("state.previous.json", "state.v1.json", ".lock"):
        raise Problem("path", "Cannot render over runtime state")
    text = target.read_text(encoding="utf-8") if target.exists() else ""
    if BEGIN in text or END in text:
        if text.count(BEGIN) != 1 or text.count(END) != 1 or text.index(BEGIN) > text.index(END):
            raise Problem("markers", "Ambiguous generated markers; preserve file and fix the boundary")
    return target, text


def render(store, state, output):
    target, text = render_target(store, output)
    block = facts_markdown(store, state, store.observe())
    if BEGIN in text or END in text:
        updated = text[:text.index(BEGIN)] + block.rstrip("\n") + text[text.index(END) + len(END):]
    else:
        updated = text + ("\n\n" if text and not text.endswith("\n\n") else "") + block
    if updated != text:
        atomic_write(target, updated)
    return {"output": output, "changed": updated != text}


def group_alive(pgid):
    if os.name == "nt":
        return False
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


class WindowsJob:
    """A Windows Job Object: the counterpart of a POSIX process group for descendants of one child."""

    def __init__(self, pid):
        import ctypes
        from ctypes import wintypes
        self.ctypes, self.wintypes = ctypes, wintypes
        self.kernel = k = ctypes.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "CreateJobObjectW": ([wintypes.LPVOID, wintypes.LPCWSTR], wintypes.HANDLE),
            "OpenProcess": ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            "AssignProcessToJobObject": ([wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
            "QueryInformationJobObject": ([wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD,
                                           ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
            "TerminateJobObject": ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
            "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
        }
        for name, (args, result) in signatures.items():
            getattr(k, name).argtypes, getattr(k, name).restype = args, result
        self.handle = self.kernel.CreateJobObjectW(None, None)
        process = self.kernel.OpenProcess(0x0101, False, pid)  # PROCESS_TERMINATE | PROCESS_SET_QUOTA
        try:
            if not self.handle or not process or not self.kernel.AssignProcessToJobObject(self.handle, process):
                raise OSError(ctypes.get_last_error(), "Cannot assign the process to a job object")
        finally:
            if process:
                self.kernel.CloseHandle(process)

    def active(self):
        ctypes, wintypes = self.ctypes, self.wintypes

        class Accounting(ctypes.Structure):
            _fields_ = [("user", ctypes.c_int64), ("kernel", ctypes.c_int64), ("period_user", ctypes.c_int64),
                        ("period_kernel", ctypes.c_int64), ("page_faults", wintypes.DWORD),
                        ("total", wintypes.DWORD), ("active", wintypes.DWORD), ("terminated", wintypes.DWORD)]
        info = Accounting()
        if not self.kernel.QueryInformationJobObject(self.handle, 1, ctypes.byref(info), ctypes.sizeof(info), None):
            return 0
        return info.active

    def terminate(self):
        self.kernel.TerminateJobObject(self.handle, 1)


def terminate_group(child, grace=4.0, job=None):
    """Stop the direct child and every descendant in the process group it leads."""
    if os.name == "nt":
        # Ask the group to stop first: CTRL_BREAK reaches every process in it, and a running check records
        # itself as abandoned. Then force whatever remains: the whole job, or the tree under a live leader.
        def alive():
            return child.poll() is None or (job is not None and job.active() > 0)
        if alive():
            try:
                os.kill(child.pid, signal.CTRL_BREAK_EVENT)
            except OSError:
                pass
            deadline = time.monotonic() + grace
            while alive() and time.monotonic() < deadline:
                time.sleep(0.1)
        if job is not None and job.active() > 0:
            job.terminate()
        elif child.poll() is None:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(child.pid)], capture_output=True)
        return
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        child.poll()
        if not group_alive(child.pid):
            return
        time.sleep(0.1)
    try:
        os.killpg(child.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def group_kwargs():
    return {"start_new_session": True} if os.name != "nt" else {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}


class Interrupted(Exception):
    pass


STOP_FILE = "SESSION_WORKFLOW_STOP_FILE"


def wait_for_check(child, timeout):
    """Wait like Popen.wait, but also stop when the supervisor of an enclosing worker asks for it.

    Signals cannot reach a check started by a worker everywhere (a Windows process without a console gets no
    CTRL_BREAK), so the supervisor also writes the file named in SESSION_WORKFLOW_STOP_FILE.
    """
    stop_file, deadline = os.environ.get(STOP_FILE), time.monotonic() + timeout
    while True:
        try:
            return child.wait(timeout=min(0.2, max(0.0, deadline - time.monotonic())))
        except subprocess.TimeoutExpired:
            if stop_file and os.path.exists(stop_file):
                raise Interrupted()
            if time.monotonic() >= deadline:
                raise


@contextmanager
def interrupt_guard():
    """Turn SIGTERM/SIGHUP into Interrupted while a check runs, so its separate process group is not orphaned."""
    names = [n for n in ("SIGTERM", "SIGHUP", "SIGBREAK") if hasattr(signal, n)]
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    def handler(signum, frame):
        raise Interrupted()
    previous = {n: signal.signal(getattr(signal, n), handler) for n in names}
    try:
        yield
    finally:
        for n, h in previous.items():
            signal.signal(getattr(signal, n), h)


def run_check(store, state, p, args, run_id, command, before):
    log = store.directory / "checks" / (run_id + ".log")
    log.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with open(log, "wb") as output:
        try:
            child = subprocess.Popen(command, cwd=store.root, stdout=output, stderr=subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL, shell=False, **group_kwargs())
            try:
                with interrupt_guard():
                    code = wait_for_check(child, args.timeout)
                outcome = "pass" if code == 0 else "fail"
            except subprocess.TimeoutExpired:
                terminate_group(child)
                child.wait()
                code, outcome = None, "timeout"
            except Interrupted:
                # The caller was stopped (for example a timed-out delegated worker): stop the check's own group too,
                # with a short grace so this finishes well inside the supervisor's longer relay grace period.
                terminate_group(child, grace=1.0)
                child.wait()
                output.write(b"\n[session-workflow] check stopped because its caller was terminated\n")
                code, outcome = None, "abandoned"
        except OSError as exc:
            output.write(str(exc).encode("utf-8", "replace"))
            code, outcome = None, "error"
    after = scope_inventory(store, state, p)
    changed = sorted(name for name in set(before) | set(after) if before.get(name) != after.get(name))
    return {"id": run_id, "phase": p["id"], "name": args.name, "result": outcome,
            "provenance": "executed", "at": now(), "fingerprint": phase_fingerprint(store, state, p, after),
            "stable_inputs": not changed, "changed_during_check": changed[:10], "exit_code": code,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "session_id": args.session, "root": str(store.root), "sequence": 0,
            "evidence": log.relative_to(store.directory).as_posix(), "evidence_sha256": file_digest(log)}


def runtime_view(store, record):
    handle = SUPERVISORS.get(record["run_id"])
    if handle is not None and handle.poll() is not None:
        del SUPERVISORS[record["run_id"]]
    if record["machine"] != store.machine:
        return {"status": "foreign", "reason": "Launched on another machine; no remote process action"}
    path = relative_path(store.directory, record["directory"]) / "receipt.json"
    if not path.is_file():
        return {"status": "unknown", "reason": "No supervisor receipt"}
    try:
        value = read_json(path)
        valid = isinstance(value, dict) and value.get("status") in ("running", "exited", "unknown")
        if not valid or value["status"] == "running" and not isinstance(value.get("heartbeat"), (int, float)):
            raise ValueError("Invalid supervisor receipt")
    except (Problem, OSError, ValueError):
        return {"status": "unknown", "reason": "Invalid or unreadable supervisor receipt; no PID fallback"}
    if value.get("run_id") != record["run_id"]:
        return {"status": "unknown", "reason": "Supervisor identity mismatch"}
    if value["status"] == "running" and time.time() - value.get("heartbeat", 0) > HEARTBEAT_EXPIRY:
        return {"status": "unknown", "reason": "Supervisor heartbeat expired; never fall back to PID kill"}
    return value


def stop_runtime(store, record):
    status = runtime_view(store, record)
    if status["status"] != "running":
        return status
    directory = relative_path(store.directory, record["directory"])
    atomic_write(directory / "stop.json", canonical({"run_id": record["run_id"]}) + "\n")
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        status = runtime_view(store, record)
        if status["status"] != "running":
            handle = SUPERVISORS.pop(record["run_id"], None)
            if handle is not None:
                try:
                    handle.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    SUPERVISORS[record["run_id"]] = handle
            return status
        time.sleep(0.1)
    return {"status": "unknown", "reason": "Stop receipt unavailable; process was not killed by PID"}


def request_stop(stop_request, running, grace):
    """Tell nested check runners to stop their checks before any signal: they record the run as abandoned."""
    atomic_write(stop_request, "stop\n")
    deadline = time.monotonic() + min(3.0, grace / 2)
    while running() and time.monotonic() < deadline:
        time.sleep(0.1)


def supervise(spec_path):
    """Private supervisor: owns one process group through a live Popen handle; accepts no PID."""
    spec_path = Path(spec_path).resolve()
    spec, child = read_json(spec_path), None
    directory = spec_path.parent
    receipt_path = directory / "receipt.json"
    try:
        # A delegated worker's stderr (progress, tool output) stays apart from its final answer on stdout.
        stop_request = directory / "stop-request"
        with open(directory / "output.log", "ab") as output, \
                open(directory / spec.get("stderr", "output.log"), "ab") as errors:
            child = subprocess.Popen(spec["argv"], cwd=spec["root"], stdout=output,
                                     stderr=errors if spec.get("stderr") else subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL, shell=False,
                                     env={**os.environ, STOP_FILE: str(stop_request)}, **group_kwargs())
            stop, beat = directory / "stop.json", 0.0
            started, limit, timed_out = time.monotonic(), spec.get("timeout"), False
            job = None
            if os.name == "nt":
                try:
                    job = WindowsJob(child.pid)
                except OSError:
                    job = None  # Fall back to the leader and taskkill /T

            def running():
                if os.name == "nt":
                    return child.poll() is None or (job is not None and job.active() > 0)
                # Descendants keep the group alive after the leader exits.
                return child.poll() is None or group_alive(child.pid)
            # Supervise until the leader and all of its descendants are gone.
            while running():
                if time.monotonic() - beat >= HEARTBEAT_SECONDS:
                    atomic_write(receipt_path, canonical({"run_id": spec["run_id"], "status": "running",
                                 "heartbeat": time.time(), "pid": child.pid,
                                 "leader_exited": child.returncode is not None}) + "\n", durable=False)
                    beat = time.monotonic()
                if stop.exists() and read_json(stop).get("run_id") == spec["run_id"]:
                    request_stop(stop_request, running, spec.get("grace", 4.0))
                    terminate_group(child, spec.get("grace", 4.0), job)
                    break
                if limit and time.monotonic() - started > limit:
                    request_stop(stop_request, running, spec.get("grace", 4.0))
                    terminate_group(child, spec.get("grace", 4.0), job)
                    timed_out = True
                    break
                time.sleep(0.2)
            child.poll()
            receipt = {"run_id": spec["run_id"], "status": "exited", "exit_code": child.returncode,
                       "scope": "supervised process group" if os.name != "nt" else "supervised process tree"}
            if timed_out:
                receipt["timed_out"] = True
    except Exception as exc:
        receipt = {"run_id": spec["run_id"], "status": "unknown", "reason": str(exc)[:500]}
    atomic_write(receipt_path, canonical(receipt) + "\n")


def launch_runtime(store, state, session_id, name, command, keep=False, cwd=None, timeout=None, run_id=None,
                   split_stderr=False):
    key = session_id + "/" + name
    if key in state["processes"]:
        raise Problem("runtime", "Runtime name already recorded; inspect it before creating a new name")
    run_id = run_id or uuid.uuid4().hex
    directory = store.directory / "runtime" / run_id
    directory.mkdir(parents=True)
    spec = {"run_id": run_id, "argv": command, "root": str(cwd or store.root)}
    if timeout:
        spec["timeout"] = timeout
    if split_stderr:
        # A delegated worker: its nested check runners need time to stop their own groups first.
        spec.update(stderr="stderr.log", grace=10.0)
    spec_path = directory / "spec.json"
    atomic_write(spec_path, canonical(spec) + "\n")
    record = {"run_id": run_id, "session_id": session_id, "machine": store.machine,
              "root": str(store.root), "directory": directory.relative_to(store.directory).as_posix(),
              "keep": keep}
    # Persist identity before launch; a crash cannot produce an unrecorded child.
    state["processes"][key] = record
    store.save(state, "runtime-prepared:" + name)
    SUPERVISORS[run_id] = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "_supervise", str(spec_path)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **group_kwargs())
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        status = runtime_view(store, record)
        if status["status"] != "unknown":
            return {"name": name, **status}
        time.sleep(0.05)
    return {"name": name, **runtime_view(store, record)}


# --- Delegation ledger -------------------------------------------------------
# One record per delegated task under <state>/delegations/<name>/. It lives outside
# state.json so schema 2 is unchanged and a 3.0 runtime can still join as a worker.
RELAY_OPEN, RELAY_CLOSE = "<<<RELAY-RESULT", "RELAY-RESULT>>>"
RELAY_OPEN_STATES = ("running", "malformed")
RELAY_OUTCOMES = ("completed", "blocked", "failed")
PROVIDER_CLIS = ("claude", "codex", "gemini")
MAX_RELAY_TEXT = 4 * 1024 * 1024


def relay_dir(store, name=""):
    base = store.directory / "delegations"
    return base / name if name else base


def relay_load(store, name):
    path = relay_dir(store, name) / "record.json"
    if not path.is_file():
        raise Problem("delegation", "Unknown delegation name; list them with delegate status")
    return read_json(path)


def relay_save(store, record):
    atomic_write(relay_dir(store, record["name"]) / "record.json", canonical(record) + "\n")


def relay_records(store):
    base = relay_dir(store)
    records = []
    if base.is_dir():
        for directory in sorted(base.iterdir()):
            try:
                records.append(read_json(directory / "record.json"))
            except (Problem, OSError):
                continue
    return records


def relay_owned(store, state, args):
    """The caller's record. A record whose orchestrator has ended is adopted together with its CLI process."""
    record = relay_load(store, require(args.name, "--name"))
    owner, adopted = record["session_id"], False
    if owner != args.session:
        if state["sessions"].get(owner, {}).get("status") == "active":
            raise Problem("ownership", f"Delegation {record['name']} belongs to active session {owner}", 3)
        record["adopted_from"], record["session_id"] = owner, args.session
        key, process = relay_process(state, record)
        if process and process["session_id"] != args.session and \
                state["sessions"].get(process["session_id"], {}).get("status") != "active":
            new_key = args.session + "/" + key.split("/", 1)[1]
            if new_key in state["processes"]:
                raise Problem("runtime", "This session already has a runtime with that name", 3)
            process["session_id"] = args.session
            state["processes"][new_key] = state["processes"].pop(key)
            adopted = True
    return record, adopted


def relay_transfer(store, retired, successor):
    """Called after the superseding begin was saved; a crash before it leaves adoption as the fallback."""
    for record in relay_records(store):
        if record["session_id"] == retired and record["status"] in RELAY_OPEN_STATES:
            record["session_id"] = successor
            relay_save(store, record)


def relay_process(state, record):
    for key, process in state["processes"].items():
        if record.get("run_id") and process["run_id"] == record["run_id"]:
            return key, process
    return None, None


def relay_runtime(store, state, record):
    _, process = relay_process(state, record)
    return runtime_view(store, process) if process else {"status": "unknown", "reason": "No runtime record"}


def relay_providers():
    found = []
    for name in PROVIDER_CLIS:
        path = shutil.which(name)
        item = {"provider": name, "cli": path or "", "version": ""}
        if path:
            try:
                done = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=15,
                                      stdin=subprocess.DEVNULL)
                item["version"] = (done.stdout or done.stderr).strip().splitlines()[0][:200] if \
                    (done.stdout or done.stderr).strip() else ""
            except (OSError, subprocess.TimeoutExpired):
                item["version"] = "unknown"
        found.append(item)
    return {"cli": found, "note": "Host-native subagents (for example T3 delegate_task) are discovered by the agent, "
            "not by this runtime"}


def relay_start(store, state, args):
    name = require(args.name, "--name")
    validate(name, "id")
    validate(require(args.provider, "--provider"), "id")
    mode = require(args.mode, "--mode")
    cli = args.inline is not None or bool(args.argv_file)
    if relay_dir(store, name).exists():
        raise Problem("delegation", "Delegation name already used; choose a new name", 3)
    packet = Path(require(args.packet, "--packet")).expanduser()
    text = packet.read_text(encoding="utf-8")
    if not text.strip():
        raise Problem("arguments", "The packet is empty")
    workspace = Path(args.workspace).expanduser().resolve() if args.workspace else store.root
    if not workspace.is_dir():
        raise Problem("workspace", "The worker workspace does not exist")
    if mode == "write":
        worker = require(args.worker_session, "--worker-session")
        validate(worker, "id")
        p = phase(state, require(args.phase, "--phase"))
        if p["state"] == "DONE":
            raise Problem("transition", f"Phase {p['id']} is DONE; reopen it before delegating", 3)
        # A host task can start, and its worker begin, before the orchestrator records it.
        started = state["sessions"].get(worker)
        if p["owner"] and p["owner"] != worker:
            raise Problem("ownership", f"Phase {p['id']} is claimed by {p['owner']}; the worker must claim it. "
                          "Release it first with a transition to TODO", 3)
        if worker == args.session or started and (cli or not started["parallel"] or
                                                  started["started_at"] < record_floor(state, args.session)):
            raise Problem("session_exists", "The worker session ID is already used; choose a new one", 3)
        if Store(workspace).directory != store.directory:
            raise Problem("workspace", "A writer's workspace must share this coordinator: this checkout or a "
                          "linked Git worktree of it", 3)
    elif args.phase:
        phase(state, args.phase)
    if not cli and args.timeout:
        raise Problem("arguments", "--timeout applies only to a CLI worker command")
    if args.timeout is not None and not 0 < args.timeout <= 86400:
        raise Problem("arguments", "Timeout must be greater than 0 and at most 86400 seconds")
    directory = relay_dir(store, name)
    command = []
    if cli:
        values = {"{packet}": str(directory / "packet.md"), "{packet_text}": text,
                  "{reply_file}": str(directory / "reply.txt"), "{workspace}": str(workspace),
                  "{state_dir}": str(store.directory)}
        for item in command_of(args):
            for token, value in values.items():
                item = item.replace(token, value)
            command.append(item)
        try:
            validate(command, "argv")
        except Problem:
            raise Problem("arguments", "Worker command is too long; pass {packet} (a path) instead of {packet_text}")
    directory.mkdir(parents=True)
    atomic_write(directory / "packet.md", text)
    record = {"name": name, "session_id": args.session, "machine": store.machine, "provider": args.provider,
              "model": args.model or "", "mode": mode, "transport": "cli" if cli else "host",
              "phase": args.phase or "", "worker_session": args.worker_session or "",
              "workspace": str(workspace) if cli or args.workspace else "", "host_ref": args.host_ref or "",
              "run_id": uuid.uuid4().hex if cli else "",
              "packet": (directory / "packet.md").relative_to(store.directory).as_posix(),
              "packet_sha256": file_digest(directory / "packet.md"), "status": "running",
              "started_at": now(), "finished_at": ""}
    if mode == "write" and state["sessions"].get(record["worker_session"]):
        record["recorded_after_worker_began"] = True
    if mode == "write" and record["workspace"]:
        # Changes already present are not the worker's; collect compares against this baseline.
        baseline = relay_changes(workspace, store.directory)
        if baseline is not None:
            atomic_write(directory / "baseline.json", canonical(baseline) + "\n")
    relay_save(store, record)
    result = {"name": name, "transport": record["transport"], "packet": str(directory / "packet.md"),
              "reply_file": str(directory / "reply.txt")}
    if cli:
        result["runtime"] = launch_runtime(store, state, args.session, "relay-" + name, command, keep=args.keep,
                                           cwd=workspace, timeout=args.timeout, run_id=record["run_id"],
                                           split_stderr=True)
    return result


def record_floor(state, session_id):
    """A worker that began before its orchestrator did cannot belong to this delegation."""
    return state["sessions"][session_id]["started_at"]


def relay_latest_checks(state, record):
    latest = {}
    for check in sorted(state["checks"].values(), key=lambda item: item["sequence"]):
        if check["phase"] == record["phase"] and check["session_id"] == record["worker_session"]:
            latest[check["name"]] = check
    return latest


def relay_worker_facts(state, record):
    latest = {name: c["result"] if c["provenance"] == "executed" else c["result"] + " (" + c["provenance"] + ")"
              for name, c in relay_latest_checks(state, record).items()}
    worker = state["sessions"].get(record["worker_session"])
    try:
        p = phase(state, record["phase"])
    except Problem:
        p = {"state": "missing", "owner": ""}
    return {"session": worker["status"] + (": " + worker["ended_reason"] if worker["ended_reason"] else "")
            if worker else "not started", "root": worker["root"] if worker else "", "phase_state": p["state"],
            "phase_owner": p["owner"], "recorded_checks": latest}


def relay_view(store, state, record):
    view = {key: record[key] for key in ("name", "session_id", "provider", "model", "mode", "transport", "phase",
                                         "worker_session", "host_ref", "status", "started_at", "finished_at")}
    if record["transport"] == "cli":
        runtime = relay_runtime(store, state, record)
        view["runtime"] = {key: runtime[key] for key in ("status", "exit_code", "timed_out", "reason") if key in runtime}
        if record["status"] == "running" and runtime["status"] == "exited":
            view["status"] = "exited"
    if record["mode"] == "write":
        view["worker"] = relay_worker_facts(state, record)
    if record.get("result"):
        view["result"] = record["result"]
    for key in ("error", "discrepancies", "reason", "adopted_from", "recorded_after_worker_began"):
        if record.get(key):
            view[key] = record[key]
    return view


def relay_final_texts(value):
    """Final-answer fields of known agent JSON output; tool and progress events are ignored."""
    if not isinstance(value, dict):
        return []
    kind = value.get("type")
    if kind == "result" and isinstance(value.get("result"), str):  # Claude Code json / stream-json result
        return [value["result"]]
    if kind is None and isinstance(value.get("response"), str):  # Gemini CLI json, which has no event type
        return [value["response"]]
    item = value.get("item")
    if value.get("type") == "item.completed" and isinstance(item, dict) and item.get("type") == "agent_message" \
            and isinstance(item.get("text"), str):  # Codex exec --json
        return [item["text"]]
    return []


def relay_blocks(text):
    found, start = [], text.find(RELAY_OPEN)
    while start >= 0:
        end = text.find(RELAY_CLOSE, start)
        if end < 0:
            break
        body = text[start + len(RELAY_OPEN):end].strip()
        if body.startswith("```"):
            body = body.split("\n", 1)[1] if "\n" in body else ""
            body = body.rsplit("```", 1)[0]
        found.append(body.strip())
        start = text.find(RELAY_OPEN, end)
    return found


def relay_extract(text):
    """The last RELAY-RESULT block in the final answer: plain text, or a known JSON final-answer field."""
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            whole = json.loads(stripped)
        except ValueError:
            whole = None
        if whole is not None:
            blocks = [b for t in relay_final_texts(whole) for b in relay_blocks(t)]
            return blocks[-1] if blocks else None
    candidates, raw, inside = [], [], False
    for line in text.splitlines():
        decoded = None
        if not inside and line.lstrip().startswith("{"):
            try:
                decoded = json.loads(line)
            except ValueError:
                decoded = None
        if isinstance(decoded, dict):
            candidates += relay_blocks("\n".join(raw))
            raw = []
            for final in relay_final_texts(decoded):
                candidates += relay_blocks(final)
            continue
        raw.append(line)
        # Lines inside an open block are its body, even when they look like JSON events.
        opened = line.rfind(RELAY_OPEN)
        if opened >= 0:
            inside = RELAY_CLOSE not in line[opened:]
        elif inside and RELAY_CLOSE in line:
            inside = False
    candidates += relay_blocks("\n".join(raw))
    return candidates[-1] if candidates else None


def relay_problems(record, result):
    if not isinstance(result, dict):
        return ["The result must be a JSON object"]
    problems = []
    if result.get("outcome") not in RELAY_OUTCOMES:
        problems.append("outcome must be one of " + ", ".join(RELAY_OUTCOMES))
    if not isinstance(result.get("summary"), str) or not result["summary"].strip():
        problems.append("summary is required")
    if "checks" in result and (not isinstance(result["checks"], list) or not all(
            isinstance(c, dict) and isinstance(c.get("name"), str) for c in result["checks"])):
        problems.append("checks must be [{name, result}]")
    for field in ("changed_files", "findings", "gaps"):
        if field in result and not isinstance(result[field], list):
            problems.append(field + " must be a list")
    if "changed_files" in result and isinstance(result["changed_files"], list) and \
            not all(isinstance(f, str) for f in result["changed_files"]):
        problems.append("changed_files must list paths")
    if result.get("outcome") == "completed":
        if record["mode"] == "consult" and not isinstance(result.get("answer"), str):
            problems.append("a consult result needs answer")
        if record["mode"] == "review":
            if result.get("verdict") not in ("APPROVE", "CHANGES_REQUIRED"):
                problems.append("a review needs verdict APPROVE or CHANGES_REQUIRED")
            if not isinstance(result.get("findings"), list):
                problems.append("a review needs a findings list")
        if record["mode"] == "write":
            for field in ("changed_files", "checks"):
                if field not in result:
                    problems.append("a write result needs " + field)
    return problems


def relay_in_scope(name, allowed):
    """One-directional containment after normalization; traversal and absolute paths are never in scope."""
    raw = name.replace("\\", "/")
    if raw.startswith("/") or re.match(r"^[A-Za-z]:", raw) or ".." in raw.split("/"):
        return False
    clean = posixpath.normpath(raw).casefold()
    for scope in allowed:
        scope = posixpath.normpath(scope.replace("\\", "/")).casefold()
        if scope in ("*", ".") or clean == scope or clean.startswith(scope + "/"):
            return True
    return False


def relay_changes(root, state_dir):
    """Changed and untracked paths of a workspace with content facts, or None when they cannot be read."""
    try:
        snap = snapshot(root, state_dir)
        if snap.get("limited"):
            return None
        names = [c["path"] if isinstance(c, dict) else c for c in snap["changes"]]
        return file_facts(root, names, state_prefix(root, state_dir))
    except Problem:
        return None


def relay_discrepancies(store, state, record, result):
    """Compare a writer's claims with what the runtime recorded and the workspace shows; claims prove nothing."""
    facts = relay_worker_facts(state, record)
    found = []
    if result.get("worker_session", record["worker_session"]) != record["worker_session"]:
        found.append("Result names another worker session")
    if facts["session"] == "not started":
        found.append("The worker session never began in this coordinator")
    latest = relay_latest_checks(state, record)
    for check in result.get("checks") or []:
        recorded = latest.get(check["name"])
        if check.get("result") == "pass" and (not recorded or recorded["result"] != "pass"):
            found.append(f"Check {check['name']} is claimed to pass but the worker recorded "
                         f"{recorded['result'] if recorded else 'no run'}")
    try:
        p = phase(state, record["phase"])
    except Problem:
        p = {"id": "", "paths": [], "required_checks": []}
    root = Path(facts["root"]) if facts["root"] else None
    if result.get("outcome") == "completed":
        overall = {}
        for c in sorted((c for c in state["checks"].values() if c["phase"] == p["id"]), key=lambda c: c["sequence"]):
            overall[c["name"]] = c
        for name in p["required_checks"]:
            if name not in latest or overall[name]["id"] != latest[name]["id"]:
                found.append(f"Required check {name} has no latest run by the worker")
        if root and root.is_dir() and p["id"]:
            # The same gate DONE uses, judged in the worker's workspace: fresh fingerprint and intact log.
            found += ["Worker evidence would not satisfy DONE: " + gap
                      for gap in verification_gaps(Store(root, store.directory), state, p)]
    claimed = [f for f in result.get("changed_files") or []]
    outside = [f for f in claimed if not relay_in_scope(f, p["paths"])]
    if outside:
        found.append("Reported files outside the phase paths: " + ", ".join(outside[:10]))
    if root and root.is_dir():
        now = relay_changes(root, store.directory)
        baseline_path = relay_dir(store, record["name"]) / "baseline.json"
        baseline = read_json(baseline_path) if baseline_path.is_file() and str(root) == record["workspace"] else None
        if now is None:
            found.append("Could not inspect the worker workspace")
        elif baseline is None and root == store.root:
            found.append("The worker used the orchestrator checkout without a recorded baseline; its changes "
                         "could not be told apart from others")
        else:
            base = baseline or {}
            observed = sorted(f for f in set(now) | set(base) if now.get(f) != base.get(f))
            stray = [f for f in observed if not relay_in_scope(f, p["paths"])]
            if stray:
                found.append("Workspace changes outside the phase paths: " + ", ".join(stray[:10]))
            unreported = [f for f in observed if f not in claimed and f not in stray]
            if unreported:
                found.append("Changed but not reported: " + ", ".join(unreported[:10]))
    return found


def relay_collect(store, state, args):
    record, adopted = relay_owned(store, state, args)
    if record["status"] not in RELAY_OPEN_STATES:
        raise Problem("delegation", f"Delegation {record['name']} is already {record['status']}", 3)
    directory = relay_dir(store, record["name"])
    sources = [directory / "reply.txt"]
    if record["transport"] == "cli":
        runtime = relay_runtime(store, state, record)
        if runtime["status"] == "running":
            raise Problem("delegation_running", "The worker is still running; wait for it or cancel it", 3)
        if runtime["status"] != "exited" and not args.confirm_stopped:
            raise Problem("delegation_unknown", f"Worker runtime is {runtime['status']}: "
                          f"{runtime.get('reason', '')}. Confirm the worker stopped, then pass --confirm-stopped", 3)
        _, process = relay_process(state, record)
        if process:
            sources.append(relay_path(store, process["directory"]) / "output.log")
    if args.from_file:
        sources = [Path(args.from_file).expanduser()]
    body, used = None, ""
    for source in sources:
        if source.is_file():
            with open(source, "rb") as handle:
                handle.seek(max(0, source.stat().st_size - MAX_RELAY_TEXT))
                body = relay_extract(handle.read().decode("utf-8", "replace"))
            if body is not None:
                used = str(source)
                break
    if body is None:
        error = "No " + RELAY_OPEN + " ... " + RELAY_CLOSE + " block in the final answer"
        if record["transport"] == "cli" and not args.from_file:
            # Diagnose a CLI that failed before answering, such as missing authentication.
            runtime = relay_runtime(store, state, record)
            _, process = relay_process(state, record)
            tail = ""
            log = relay_path(store, process["directory"]) / "stderr.log" if process else None
            if log and log.is_file():
                with open(log, "rb") as handle:
                    handle.seek(max(0, log.stat().st_size - 600))
                    tail = " ".join(handle.read().decode("utf-8", "replace").split())
            error += f"; worker exit code {runtime.get('exit_code')}" + (f"; stderr ends: {tail}" if tail else "")
        record.update(status="malformed", error=error)
        relay_save(store, record)
        return relay_view(store, state, record), adopted
    try:
        result = json.loads(body, object_pairs_hook=object_pairs)
        problems = relay_problems(record, result)
    except (ValueError, Problem) as exc:
        result, problems = None, ["The block is not valid, unambiguous JSON: " + str(exc)[:200]]
    if problems:
        record.update(status="malformed", error="; ".join(problems))
        relay_save(store, record)
        return relay_view(store, state, record), adopted
    discrepancies = relay_discrepancies(store, state, record, result) if record["mode"] == "write" else []
    atomic_write(directory / "result.json", canonical(result) + "\n")
    record.update(status="returned", finished_at=now(), result=result, source=used,
                  result_sha256=file_digest(directory / "result.json"), error="", discrepancies=discrepancies)
    relay_save(store, record)
    return relay_view(store, state, record), adopted


def relay_cancel(store, state, args):
    record, adopted = relay_owned(store, state, args)
    if record["status"] not in RELAY_OPEN_STATES:
        raise Problem("delegation", f"Delegation {record['name']} is already {record['status']}", 3)
    if record["transport"] == "cli":
        _, process = relay_process(state, record)
        stopped = stop_runtime(store, process) if process else {"status": "unknown", "reason": "No runtime record"}
        if stopped["status"] == "running":
            raise Problem("delegation_running", "The worker did not stop; inspect it before retrying", 3)
        if stopped["status"] != "exited" and not args.confirm_stopped:
            raise Problem("delegation_unknown", f"Worker runtime is {stopped['status']}: {stopped.get('reason', '')}. "
                          "Stop it yourself, then pass --confirm-stopped", 3)
    elif not args.confirm_stopped:
        raise Problem("arguments", "Cancel the host task first (for example with the host's cancel tool), then "
                      "pass --confirm-stopped")
    record.update(status="cancelled", finished_at=now(), reason=args.reason or "cancelled by orchestrator")
    relay_save(store, record)
    view = relay_view(store, state, record)
    if record["mode"] == "write" and state["sessions"].get(record["worker_session"], {}).get("status") == "active":
        view["next"] = (f"Worker session {record['worker_session']} is still active; release it with release "
                        "--confirm-stopped once you have confirmed its agent stopped")
    return view, adopted


def relay_path(store, relative):
    return relative_path(store.directory, relative)


def relay_open(store, session_id=None):
    return [r for r in relay_records(store) if r["status"] in RELAY_OPEN_STATES and
            (session_id is None or r["session_id"] == session_id)]


def running_checks(state, session_id, pid=None):
    return [c for c in state["checks"].values() if c["result"] == "running" and
            c["session_id"] == session_id and (pid is None or c["phase"] == pid)]


def command_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=os.getcwd(), help="Project/worktree root")
    parser.add_argument("--state-dir", help="Explicit shared coordinator directory; absolute or project-relative")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("snapshot", help="Read workspace facts without creating project state")
    p.add_argument("--full", action="store_true", help="Include every observed path; default shows at most 5")
    for name in ("init", "begin"):
        p = sub.add_parser(name, help="Create state once" if name == "init" else
                           "Initialize if needed and register a NEW session; supersedes stopped solo sessions here")
        p.add_argument("--context", default="PROJECT.md")
        p.add_argument("--plan", default="")
        p.add_argument("--handover", default="HANDOVER.md")
        if name == "begin":
            p.add_argument("--session", help="New unique ID; omit to generate one")
            p.add_argument("--parallel", action="store_true",
                           help="Work alongside other live sessions in this checkout; never supersede them")
            p.add_argument("--next-action")
    p = sub.add_parser("status", help="Compact shared state and live local facts")
    p.add_argument("--session")
    p.add_argument("--full", action="store_true", help="Return complete machine state; avoid loading it into prompts by default")
    p = sub.add_parser("next", help="Deterministic eligible phase and stale evidence")
    p.add_argument("--session", required=True)
    for name in ("checkpoint", "end"):
        p = sub.add_parser(name)
        p.add_argument("--session", required=True)
        p.add_argument("--expect-revision", type=int)
        p.add_argument("--next-action", required=True)
        p.add_argument("--note", default="")
        if name == "end":
            p.add_argument("--keep-runtimes", action="store_true")
            p.add_argument("--handover-output", help="Render one marked factual block after this session ends")
    p = sub.add_parser("release", help="End a stopped session that cannot end itself (crashed chat, other machine)")
    p.add_argument("--session", required=True, help="The stopped session to release")
    p.add_argument("--expect-revision", type=int, required=True)
    p.add_argument("--confirm-stopped", action="store_true", help="The user confirmed that session's agent stopped")
    p.add_argument("--reason", required=True)
    p.add_argument("--by", help="Your active session ID, recorded for audit")
    p = sub.add_parser("plan", help="Import declarative phase definitions; preserve runtime states")
    p.add_argument("--input", required=True, help="JSON plan file, or - for stdin")
    p.add_argument("--session", required=True)
    p.add_argument("--expect-revision", type=int, required=True)
    p.add_argument("--merge", action="store_true", help="Upsert supplied definitions without resending recorded phases")
    p = sub.add_parser("batch", help="One atomic revision-checked plan/transition/checkpoint transaction; no subprocesses")
    p.add_argument("--input", required=True, help="JSON {steps:[...]}; stdin is -")
    p.add_argument("--session", required=True)
    p.add_argument("--expect-revision", type=int, required=True)
    p = sub.add_parser("transition")
    p.add_argument("--session", required=True)
    p.add_argument("--expect-revision", type=int)
    p.add_argument("--phase", required=True)
    p.add_argument("--to", choices=STATES, required=True)
    p.add_argument("--reason", default="")
    p.add_argument("--acceptance-note", default="")
    p = sub.add_parser("handover", help="Render only the marked factual block, preserving surrounding prose")
    p.add_argument("--output", help="Default: handover.md in the shared state directory")
    p.add_argument("--expect-revision", type=int)
    p = sub.add_parser("check", help="Record executed checks or explicitly reported evidence; command after --")
    p.add_argument("action", choices=("run", "record", "abandon"))
    p.add_argument("--session", required=True)
    p.add_argument("--expect-revision", type=int)
    p.add_argument("--phase")
    p.add_argument("--name")
    p.add_argument("--argv-file", help="JSON argv array instead of a command after --; shell=False either way")
    p.add_argument("--timeout", type=float, default=30)
    p.add_argument("--evidence")
    p.add_argument("--result", choices=("pass", "fail"))
    p.add_argument("--id")
    p.add_argument("--confirm-stopped", action="store_true", help="For abandon: caller verified the interrupted command is no longer running")
    p = sub.add_parser("runtime", help="Own only process groups launched by this runtime; command after --")
    p.add_argument("action", choices=("launch", "status", "stop"))
    p.add_argument("--session", required=True)
    p.add_argument("--expect-revision", type=int)
    p.add_argument("--name", required=True)
    p.add_argument("--argv-file", help="JSON argv array instead of a command after --")
    p.add_argument("--keep", action="store_true")
    p = sub.add_parser("delegate", help="Record and supervise work delegated to another agent; worker command after --")
    p.add_argument("action", choices=("providers", "start", "status", "collect", "cancel"))
    p.add_argument("--session")
    p.add_argument("--expect-revision", type=int)
    p.add_argument("--name", help="Unique delegation ID")
    p.add_argument("--provider", help="Worker provider ID, for example codex, claude or gemini")
    p.add_argument("--model", default="")
    p.add_argument("--mode", choices=("consult", "review", "write"))
    p.add_argument("--phase", help="Required for write: the phase the worker claims")
    p.add_argument("--worker-session", help="Required for write: the new session ID the worker begins")
    p.add_argument("--workspace", help="Worker checkout; a writer needs this checkout or a linked worktree")
    p.add_argument("--packet", help="Instruction packet file given to the worker")
    p.add_argument("--host-ref", help="Host task reference when no CLI command is given")
    p.add_argument("--argv-file", help="JSON argv array instead of a command after --")
    p.add_argument("--timeout", type=float, help="CLI worker: stop its process group after this many seconds")
    p.add_argument("--keep", action="store_true", help="CLI worker: keep running when this session ends")
    p.add_argument("--from", dest="from_file", help="collect: file holding the worker's final reply")
    p.add_argument("--confirm-stopped", action="store_true",
                   help="cancel/collect: you verified the worker stopped (host task, or a CLI worker in unknown state)")
    p.add_argument("--reason", default="")
    return parser


def require(value, label):
    if value is None or isinstance(value, str) and not value.strip():
        raise Problem("arguments", label + " is required")
    return value


def command_of(args):
    if args.inline is not None and args.argv_file:
        raise Problem("arguments", "Give the command after -- or with --argv-file, not both")
    command = args.inline if args.inline is not None else read_json(require(args.argv_file, "A command after -- (or --argv-file)"))
    validate(command, "argv")
    return command


def apply_plan(state, args):
    data = read_json(args.input)
    return apply_plan_data(state, data, args.session, getattr(args, "merge", False))


def apply_plan_data(state, data, session_id, merge=False):
    validate(data, "plan")
    definitions = []
    for item in data["phases"]:
        definitions.append({"depends_on": [], "priority": 0, "paths": ["*"], "required_checks": [], "exclude": [], **item})
        for field in ("paths", "exclude"):
            definitions[-1][field] = [Path(x).as_posix() for x in definitions[-1][field]]
    if len({p["id"] for p in definitions}) != len(definitions):
        raise Problem("plan", "Duplicate phase IDs")
    old = {p["id"]: p for p in state["phases"]}
    if merge:
        fields = ("id", "title", "acceptance", "depends_on", "priority", "paths", "required_checks", "exclude")
        by_id = {p["id"]: {k: p[k] for k in fields} for p in state["phases"]}
        by_id.update({p["id"]: p for p in definitions})
        definitions = list(by_id.values())
    check_plan(definitions)
    if set(old) - {p["id"] for p in definitions}:
        raise Problem("plan", "Do not remove recorded phases; explicitly defer them")
    result = []
    for item in definitions:
        prior = old.get(item["id"])
        metadata = {k: prior[k] for k in item} if prior else None
        if prior and metadata != item:
            if prior["owner"] not in ("", session_id):
                raise Problem("ownership", "Another session owns phase " + item["id"], 3)
            if prior["state"] == "DONE" or running_checks(state, session_id, item["id"]):
                raise Problem("plan", "Reopen a completed phase / finish active checks before changing its contract")
        result.append({**item, "state": prior["state"] if prior else "TODO",
                       "owner": prior["owner"] if prior else "",
                       "reason": prior["reason"] if prior else "", "acceptance_note": prior["acceptance_note"] if prior else ""})
    proposed = {**state, "phases": result}
    for item in result:
        if item["owner"] and claim_conflicts(proposed, item, item["owner"]):
            raise Problem("ownership", "Plan change would overlap another session's active claim", 3)
    state["phases"] = result
    return {"phases": len(result)}


def batch(store, state, args):
    data = read_json(args.input)
    validate(data, "batch")
    fields = {"plan": {"command", "phases"},
              "transition": {"command", "phase", "to", "reason", "acceptance_note"},
              "checkpoint": {"command", "next_action", "note"}}
    required = {"plan": {"phases"}, "transition": {"phase", "to"}, "checkpoint": {"next_action"}}
    for step in data["steps"]:
        command = step["command"]
        if set(step) - fields[command] or required[command] - set(step):
            raise Problem("schema", "Invalid fields for batch " + command)
    results, live = [], None
    for step in data["steps"]:
        command = step["command"]
        if command == "plan":
            result = apply_plan_data(state, {"phases": step["phases"]}, args.session, merge=True)
        elif command == "transition":
            params = argparse.Namespace(session=args.session, phase=step["phase"], to=step["to"],
                                        reason=step.get("reason", ""), acceptance_note=step.get("acceptance_note", ""))
            result = transition(store, state, params)
        else:
            require(step["next_action"], "next_action")
            live = live if live is not None else store.observe()
            new_checkpoint(store, state, args.session, step["next_action"], step.get("note", ""), live)
            result = {"checkpoint": state["sessions"][args.session]["checkpoint"]["id"]}
        results.append({"command": command, **result})
    return {"steps": results}


def transition(store, state, args):
    p = phase(state, args.phase)
    target = args.to
    if p["owner"] not in ("", args.session):
        raise Problem("ownership", f"Phase {p['id']} belongs to session {p['owner']}; work on unclaimed phases, "
                      "or release that session after the user confirms it stopped", 3)
    claiming = target == p["state"] and p["owner"] == "" and target in ("IN_PROGRESS", "VERIFY")
    if target == p["state"] and not claiming:
        return {"phase": p["id"], "state": p["state"], "unchanged": True}
    if not claiming and target not in TRANSITIONS[p["state"]]:
        raise Problem("transition", f"Invalid transition {p['state']} -> {target}")
    if running_checks(state, args.session, p["id"]):
        raise Problem("check_running", "Finish or explicitly abandon the in-flight check first", 3)
    warnings = []
    if target in ("IN_PROGRESS", "VERIFY", "DONE"):
        pending = [d for d in dependency_ids(state, p) if phase(state, d)["state"] != "DONE"]
        if pending:
            raise Problem("dependency", "Dependencies are not DONE: " + ", ".join(sorted(pending)), 3)
        conflicts = claim_conflicts(state, p, args.session)
        if conflicts:
            raise Problem("ownership", "Conflicting phase/file claim: " + canonical(conflicts) + "; choose "
                          "unclaimed work, or release a session the user confirmed stopped", 3)
    if target in ("BLOCKED", "NEEDS_DECISION", "DEFERRED") or p["state"] in ("DONE", "BLOCKED", "NEEDS_DECISION", "DEFERRED"):
        require(args.reason, "--reason")
    if target == "DONE":
        require(args.acceptance_note, "--acceptance-note (an explicit acceptance judgment)")
        gaps = verification_gaps(store, state, p)
        if gaps:
            raise Problem("verification", "Cannot mark DONE: " + "; ".join(gaps), 3)
        p["acceptance_note"] = args.acceptance_note
    if target in ("VERIFY", "DONE"):
        # Later phases legitimately edit shared files; stale dependency evidence is a warning, not a lock.
        warnings = [f"Dependency {d} evidence is no longer fresh; re-run its checks before delivery"
                    for d in p["depends_on"] if verification_gaps(store, state, phase(state, d))]
    if p["state"] == "DONE":
        p["acceptance_note"] = ""
        affected = {p["id"]}
        while True:
            expanded = affected | {item["id"] for item in state["phases"] if set(item["depends_on"]) & affected}
            if expanded == affected:
                break
            affected = expanded
        for dependent in state["phases"]:
            if dependent["id"] in affected - {p["id"]}:
                if dependent["owner"] not in ("", args.session) or running_checks(state, args.session, dependent["id"]):
                    raise Problem("dependency_owned", "Coordinate with the dependent phase owner before reopening", 3)
                if dependent["state"] == "DONE":
                    dependent.update(state="VERIFY", owner="", acceptance_note="", reason="Dependency reopened: " + p["id"])
    p["state"], p["reason"] = target, args.reason
    p["owner"] = args.session if target in ("IN_PROGRESS", "VERIFY") else ""
    result = {"phase": p["id"], "state": p["state"], "owner": p["owner"]}
    if warnings:
        result["warnings"] = warnings
    return result


def release(store, state, args):
    target = state["sessions"].get(args.session)
    if not target:
        raise Problem("session", "Unknown session ID")
    if target["status"] != "active":
        raise Problem("session_ended", f"Session {args.session} has already ended ({target['ended_reason']})", 3)
    if not args.confirm_stopped:
        raise Problem("arguments", "Confirm with the user that this session's agent has stopped, then pass --confirm-stopped")
    reason = require(args.reason, "--reason")
    if args.by:
        session(state, store, args.by)
    alive = live_checks(store, state, args.session) if target["machine"] == store.machine else []
    if alive:
        raise Problem("session_alive", f"Session {args.session} is running check {alive[0]} right now; it has not stopped", 3)
    label = "released" + (" by " + args.by if args.by else "") + ": " + reason
    return {"session_id": args.session, **retire(store, state, args.session, label)}


def end(store, state, args):
    if running_checks(state, args.session):
        raise Problem("check_running", "This session has an in-flight check; reconcile it before ending", 3)
    if args.handover_output:
        render_target(store, args.handover_output)
        if claim_conflicts(state, {"id": "", "paths": [args.handover_output]}, args.session):
            raise Problem("ownership", "Another session owns the requested handover output", 3)
    new_checkpoint(store, state, args.session, args.next_action, args.note)
    for p in state["phases"]:
        if p["owner"] == args.session:
            p["owner"] = ""
    s = state["sessions"][args.session]
    s.update(status="ended", ended_at=now(), ended_reason="ended")
    compact_checkpoint(s)
    store.save(state, "end-checkpoint:" + args.session)
    processes = {}
    for name, record in state["processes"].items():
        if record["session_id"] == args.session:
            processes[name] = runtime_view(store, record) if args.keep_runtimes or record["keep"] else stop_runtime(store, record)
    result = {"session_id": args.session, "processes": processes}
    still_open = []
    for record in relay_open(store, args.session):
        key, _ = relay_process(state, record)
        stopped = processes.get(key)
        if record["transport"] == "cli" and stopped and stopped["status"] == "exited" and record["status"] == "running":
            record.update(status="cancelled", finished_at=now(), reason="orchestrator session ended")
            relay_save(store, record)
        else:
            still_open.append(record["name"])
    if still_open:
        result["open_delegations"] = still_open
        result["warning"] = ("Delegations stay open: a later session adopts them with delegate status, collect "
                             "or cancel. Cancel host tasks you no longer need.")
    return result


def check_command(store, state, args):
    if args.action == "abandon":
        check = state["checks"].get(require(args.id, "--id"))
        if not check or check["session_id"] != args.session or check["result"] != "running":
            raise Problem("check", "Only this session's unresolved check can be abandoned")
        if not args.confirm_stopped:
            raise Problem("check", "Verify the interrupted command has stopped, then use --confirm-stopped")
        try:
            with file_lock(store.directory / "checks" / (args.id + ".lock"), wait=0):
                pass
        except Problem:
            raise Problem("check_running", "This check is still executing; it cannot be abandoned", 3)
        check["result"] = "abandoned"
        check["evidence"] += "; " + require(args.evidence, "--evidence explaining interruption")
        return check
    p = phase(state, require(args.phase, "--phase"))
    if p["owner"] != args.session:
        raise Problem("ownership", "Only the phase owner can record evidence; claim the phase first", 3)
    rid = uuid.uuid4().hex
    record = {"id": rid, "phase": p["id"], "name": require(args.name, "--name"),
              "result": require(args.result, "--result"), "provenance": "reported", "at": now(),
              "fingerprint": phase_fingerprint(store, state, p), "stable_inputs": True, "changed_during_check": [],
              "evidence": require(args.evidence, "--evidence"), "session_id": args.session,
              "root": str(store.root), "exit_code": None, "elapsed_seconds": 0,
              "sequence": state["revision"] + 1, "evidence_sha256": ""}
    state["checks"][rid] = record
    return record


def mutate(store, state, args):
    """Apply one locked mutation; returns (result, event) where event None means already saved/unchanged."""
    command = args.command
    if command == "release":
        return release(store, state, args), "release:" + args.session
    session(state, store, args.session, require_active=not (command == "runtime" and args.action == "stop"))
    if command == "plan":
        return apply_plan(state, args), "plan:" + args.session
    if command == "batch":
        return batch(store, state, args), "batch:" + args.session
    if command == "transition":
        return transition(store, state, args), "transition:" + args.session
    if command == "checkpoint":
        new_checkpoint(store, state, args.session, args.next_action, args.note)
        return {"checkpoint": state["sessions"][args.session]["checkpoint"]["id"]}, "checkpoint:" + args.session
    if command == "end":
        return end(store, state, args), None
    if command == "delegate":
        if args.action == "start":
            return relay_start(store, state, args), None
        result, adopted = (relay_collect if args.action == "collect" else relay_cancel)(store, state, args)
        return result, "delegate-adopt:" + args.session if adopted else None
    if command == "runtime":
        if args.action == "launch":
            return launch_runtime(store, state, args.session, args.name, command_of(args), args.keep), None
        record = state["processes"].get(args.session + "/" + args.name)
        if not record:
            raise Problem("runtime", "No runtime with this name belongs to this session")
        return stop_runtime(store, record), None
    if command == "check":
        return check_command(store, state, args), "check-" + args.action + ":" + args.session
    raise Problem("command", "Unsupported command")


def recorded_check(store, args):
    require(args.name, "--name"); require(args.phase, "--phase")
    command = command_of(args)
    if not 0 < args.timeout <= 3600:
        raise Problem("arguments", "Timeout must be greater than 0 and at most 3600 seconds")
    run_id = uuid.uuid4().hex
    with file_lock(store.directory / "checks" / (run_id + ".lock"), wait=0):
        with file_lock(store.directory / ".lock"):
            state = store.load(); store.expect(state, args.expect_revision)
            session(state, store, args.session)
            p = phase(state, args.phase)
            if p["owner"] != args.session or p["state"] not in ("IN_PROGRESS", "VERIFY"):
                raise Problem("ownership", "Only the session that owns an IN_PROGRESS or VERIFY phase can run its "
                              "check; claim the phase first", 3)
            if running_checks(state, args.session, p["id"]):
                raise Problem("check_running", "A check is already in flight for this phase", 3)
            before = scope_inventory(store, state, p)
            state["checks"][run_id] = {"id": run_id, "phase": args.phase, "name": args.name,
                "result": "running", "provenance": "executed", "at": now(),
                "fingerprint": phase_fingerprint(store, state, p, before), "stable_inputs": False,
                "changed_during_check": [], "evidence": "checks/" + run_id + ".log", "session_id": args.session,
                "root": str(store.root), "exit_code": None, "elapsed_seconds": 0,
                "sequence": state["revision"] + 1, "evidence_sha256": ""}
            store.save(state, "check-start:" + run_id)
        # Long work happens outside the coordinator lock; other disjoint sessions can progress.
        result = run_check(store, state, p, args, run_id, command, before)
        with file_lock(store.directory / ".lock"):
            current = store.load()
            saved = current["checks"].get(run_id)
            if not saved or saved["result"] != "running":
                raise Problem("check_conflict", "Check was abandoned or changed; its completion was not promoted", 3)
            result["sequence"] = current["revision"] + 1
            current["checks"][run_id] = result
            store.save(current, "check-result:" + run_id)
    shown = dict(result)
    if not shown["stable_inputs"]:
        shown["warning"] = ("The check changed files in the phase scope; this run cannot satisfy DONE. List "
                            "generated outputs in the phase 'exclude' or .gitignore and run it again.")
    return current, shown


def read_only(store, args):
    state = store.load()
    if args.command == "status":
        if args.session and args.session not in state["sessions"]:
            raise Problem("session", "Unknown session ID")
        return state, state if args.full else brief(state, store, args.session, store.observe())
    if args.command == "next":
        session(state, store, args.session)
        choices = ready(state, args.session)
        stale = [p["id"] for p in state["phases"] if p["state"] == "DONE" and verification_gaps(store, state, p)]
        action = "continue" if choices else "recheck" if stale else \
            "complete" if state["phases"] and all(p["state"] == "DONE" for p in state["phases"]) else "decision"
        return state, {"action": action, "phase": choices[0] if choices else None, "stale_done_evidence": stale,
                       "not_done": [p["id"] for p in state["phases"] if p["state"] != "DONE"]}
    if args.command == "delegate":
        records = [relay_load(store, args.name)] if args.name else relay_records(store)
        return state, {"delegations": [relay_view(store, state, r) for r in records
                                       if args.name or not args.session or r["session_id"] == args.session]}
    record = state["processes"].get(args.session + "/" + args.name)
    if not record:
        raise Problem("runtime", "Unknown session runtime")
    return state, runtime_view(store, record)


def dispatch(store, args):
    command = args.command
    accepts_command = command == "check" and args.action == "run" or command == "runtime" and args.action == "launch" \
        or command == "delegate" and args.action == "start"
    if args.inline is not None and not accepts_command:
        raise Problem("arguments", "Only 'check run', 'runtime launch' and 'delegate start' accept a command after --")
    if command == "delegate" and args.action == "providers":
        return None, relay_providers()
    if command == "delegate" and args.action != "status":
        require(args.session, "--session")
    if command == "snapshot":
        result = store.observe()
        return None, result if args.full else compact_snapshot(result)
    if command in ("status", "next") or command in ("runtime", "delegate") and args.action == "status":
        return read_only(store, args)
    if command == "check" and args.action == "run":
        return recorded_check(store, args)
    if command == "begin":
        return begin(store, args)
    with file_lock(store.directory / ".lock"):
        if command == "init":
            if store.path.exists():
                return store.load(), {"existing": True}
            state = initial_state(store, args)
            store.save(state, "init")
            return state, {"created": True}
        state = store.load()
        store.expect(state, args.expect_revision, required=command in ("plan", "batch", "release"))
        if command == "handover":
            if args.output:
                return state, render(store, state, args.output)
            target = store.directory / "handover.md"
            content = facts_markdown(store, state, store.observe())
            changed = not target.exists() or target.read_text(encoding="utf-8") != content
            if changed:
                atomic_write(target, content)
            return state, {"output": str(target), "changed": changed}
        result, event = mutate(store, state, args)
        if event:
            store.save(state, event)
        if command == "end" and args.handover_output:
            try:
                result["handover"] = render(store, state, args.handover_output)
            except (Problem, OSError, UnicodeError) as exc:
                raise Problem("handover_after_end", f"Session ended at revision {state['revision']}; handover failed: {exc}. Reconcile and retry only handover.", 6)
        return state, result


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "_supervise":
        supervise(argv[1]); return 0
    inline = None
    if "--" in argv:
        index = argv.index("--")
        argv, inline = argv[:index], argv[index + 1:]
    args = command_parser().parse_args(argv)
    args.inline = inline
    try:
        store = Store(args.root, args.state_dir)
        state, result = dispatch(store, args)
        output = {"ok": True, "schema_version": SCHEMA_VERSION, "state_directory": str(store.directory),
                  "revision": state["revision"] if state else None, "result": result}
        if store.migration:
            output["warnings"] = [store.migration]
        emit(output)
        return 0
    except Problem as exc:
        emit({"ok": False, "error": {"code": exc.code, "message": str(exc)}})
        return exc.exit_code
    except (OSError, UnicodeError, subprocess.TimeoutExpired) as exc:
        emit({"ok": False, "error": {"code": "io", "message": str(exc)}})
        return 6


if __name__ == "__main__":
    sys.exit(main())
