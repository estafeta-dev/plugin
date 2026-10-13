#!/usr/bin/env python3
"""Portable estafeta management. Python 3.9+, standard library only."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
# Preserve source paths and installed-skill ownership across the public rename.
PACK = ROOT / "packs/session-workflow"
PLUGIN_NAME = "estafeta"
MARKETPLACE_NAME = "pashbel-estafeta"
SHARED_RESOURCES = ("workflow-contract.md", "quickstart.md", "runtime.md")
RUNTIME_RESOURCES = ("session.py", "session.schema.json")
# Former names are removed from destinations only when they are copies of this pack.
RETIRED_SKILLS = ("handover-changelog",)
RETIRED_RESOURCES = ("efficiency.md", "recovery.md")
PLUGIN_MANIFESTS = ("plugin.json", ".codex-plugin/plugin.json", ".claude-plugin/plugin.json")
CATALOGS = (".agents/plugins/marketplace.json", ".claude-plugin/marketplace.json")
PROVIDERS = {
    "codex": ".codex/skills",
    "claude": ".claude/skills",
    "hermes": ".hermes/skills",
    "gemini": ".gemini/skills",
    "antigravity": ".gemini/config/skills",
    "opencode": ".config/opencode/skills",
    "copilot": ".copilot/skills",
    "kimi": ".kimi/skills",
    "agents": ".agents/skills",
}


def names():
    result = [x.strip() for x in (PACK / "skills.list").read_text(encoding="utf-8").splitlines()
              if x.strip() and not x.lstrip().startswith("#")]
    if not result or len(result) != len(set(result)):
        raise ValueError("Empty or duplicate skill manifest")
    if any(not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", x) for x in result):
        raise ValueError("Invalid skill name")
    return result


def version():
    return (PACK / "VERSION").read_text(encoding="utf-8").strip()


def tree_digest(path):
    """Compare the complete installed payload; missing/extra files count as drift."""
    if not path.is_dir():
        return None
    h = hashlib.sha256()
    for p in sorted(path.rglob("*")):
        if "__pycache__" in p.parts or p.name == ".DS_Store":
            continue
        if p.is_symlink():
            # Skill resources must be portable, not links to another machine.
            raise ValueError(f"Symlink resource is not portable: {p}")
        if p.is_file():
            h.update(p.relative_to(path).as_posix().encode("utf-8") + b"\0")
            h.update(p.read_bytes())
            h.update(b"\0")
    return h.hexdigest()


def check():
    common = {name: (PACK / "shared" / name).read_text(encoding="utf-8")
              for name in SHARED_RESOURCES}
    manifest = names()
    for resource in PLUGIN_MANIFESTS:
        metadata = json.loads((PACK / resource).read_text(encoding="utf-8"))
        if metadata.get("name") != PLUGIN_NAME or metadata.get("version") != version():
            raise ValueError(f"Plugin identity/version mismatch: {resource}")
        if not metadata.get("description") or not metadata.get("author", {}).get("name"):
            raise ValueError(f"Missing plugin description/author: {resource}")
        if resource == "plugin.json" and metadata.get("$schema") != "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json":
            raise ValueError("Unsupported portable plugin schema")
        if resource == ".codex-plugin/plugin.json" and metadata.get("skills") != "./skills/":
            raise ValueError("Codex manifest must reference the packaged skills directory")
    for resource in CATALOGS:
        catalog = json.loads((ROOT / resource).read_text(encoding="utf-8"))
        plugins = catalog.get("plugins", [])
        if catalog.get("name") != MARKETPLACE_NAME or len(plugins) != 1:
            raise ValueError(f"Marketplace identity/entry mismatch: {resource}")
        entry = plugins[0]
        source = entry.get("source")
        path = source.get("path") if isinstance(source, dict) else source
        if entry.get("name") != PLUGIN_NAME or path != "./packs/session-workflow":
            raise ValueError(f"Marketplace does not resolve the packaged plugin: {resource}")
        if not (ROOT / path / "plugin.json").is_file():
            raise ValueError(f"Missing marketplace plugin source: {resource}")
    # The plugin directory carries its own license copy for native installation.
    if (PACK / "LICENSE").read_bytes() != (ROOT / "LICENSE").read_bytes():
        raise ValueError("LICENSE copies differ: repository root and packs/session-workflow")
    actual = {p.name for p in (PACK / "skills").iterdir() if p.is_dir()}
    if actual != set(manifest):
        raise ValueError(f"Manifest/directory mismatch: {actual ^ set(manifest)}")
    for name in manifest:
        base = PACK / "skills" / name
        content = (base / "SKILL.md").read_text(encoding="utf-8")
        if not content.startswith("---\n") or len(content.split("---", 2)) != 3:
            raise ValueError(f"Invalid frontmatter: {name}")
        front = content.split("---", 2)[1]
        if not re.search(rf"^name: {re.escape(name)}$", front, re.M):
            raise ValueError(f"Name mismatch: {name}")
        if not re.search(r"^description: .+", front, re.M):
            raise ValueError(f"Missing description: {name}")
        if f'workflow-version: "{version()}"' not in front:
            raise ValueError(f"Version mismatch: {name}")
        for resource, expected in common.items():
            if (base / "references" / resource).read_text(encoding="utf-8") != expected:
                raise ValueError(f"Shared resource drift: {name}/{resource}; run sync-contract")
        for resource in RETIRED_RESOURCES:
            if (base / "references" / resource).exists():
                raise ValueError(f"Retired resource present: {name}/{resource}; run sync-contract")
        for doc in base.rglob("*"):
            if doc.is_file() and doc.suffix in (".md", ".yaml", ".json"):
                for found in re.findall(r"(?i)(?:estafeta|session[- ]workflow)\D{0,12}?(\d+\.\d+\.\d+)", doc.read_text(encoding="utf-8")):
                    if found != version():
                        raise ValueError(f"Stale version {found} in {doc.relative_to(PACK)}")
        for resource in RUNTIME_RESOURCES:
            if (base / "scripts" / resource).read_bytes() != (PACK / "shared/runtime" / resource).read_bytes():
                raise ValueError(f"Runtime drift: {name}/{resource}; run sync-contract")
        # Only check actual Markdown resource links, not placeholder templates.
        for doc in base.rglob("*.md"):
            for link in re.findall(r"\]\(([^\s)]+)\)", doc.read_text(encoding="utf-8")):
                if "://" in link or link.startswith(("#", "<")):
                    continue
                resource = (doc.parent / link.split("#")[0]).resolve()
                if base.resolve() not in resource.parents or not resource.is_file():
                    raise ValueError(f"Broken/nonportable resource link: {doc}: {link}")
        tree_digest(base)
    return manifest


def provider_path(name, home):
    env = {"codex": "CODEX_HOME", "claude": "CLAUDE_CONFIG_DIR", "hermes": "HERMES_HOME"}
    if name in env and os.environ.get(env[name]):
        return Path(os.environ[env[name]]).expanduser() / "skills"
    if name == "codex":
        legacy = home / ".codex/skills"
        # Preserve an existing proven installation; new hosts use current docs.
        return legacy if legacy.is_dir() else home / ".agents/skills"
    if name == "opencode" and os.environ.get("XDG_CONFIG_HOME"):
        return Path(os.environ["XDG_CONFIG_HOME"]).expanduser() / "opencode/skills"
    return home / PROVIDERS[name]


def destinations(args):
    home = Path.home()
    found = [provider_path(n, home) for n in args.provider]
    found += [Path(p).expanduser() for p in args.dest]
    if args.all_detected:
        for name in PROVIDERS:
            path = provider_path(name, home)
            # Antigravity uses its own config; do not infer it from Gemini alone.
            if path.parent.is_dir() or (name == "codex" and (home / ".codex").is_dir()):
                found.append(path)
        # Existing explicit Claude profiles and Hermes profiles remain isolated.
        for p in sorted(home.glob(".claude-*")):
            if p.is_dir() and ((p / "settings.json").is_file() or (p / "skills").is_dir()):
                found.append(p / "skills")
        profiles = home / ".hermes/profiles"
        if profiles.is_dir():
            found += [p / "skills" for p in sorted(profiles.iterdir())
                      if not p.name.startswith(".") and (p / "skills").is_dir()]
    if not found:
        raise ValueError("Choose --provider, --dest, or --all-detected (no implicit destination)")
    result = []
    for p in found:
        p = p.absolute()
        resolved = p.resolve()
        # Installation is never allowed to overwrite or recurse into its sources.
        if resolved == ROOT or ROOT in resolved.parents or resolved in ROOT.parents:
            raise ValueError(f"Destination overlaps source repository: {p}")
        if p.exists() and not p.is_dir():
            raise ValueError(f"Destination is not a directory: {p}")
        if not any(resolved == q.resolve() for q in result):
            result.append(p)
    # Reject nested destination roots: one must never contain another skill copy.
    for i, p in enumerate(result):
        for q in result[i + 1:]:
            if p.resolve() in q.resolve().parents or q.resolve() in p.resolve().parents:
                raise ValueError(f"Overlapping destinations: {p}, {q}")
    return result


def pack_copy(path):
    """True only for a skill installed from this pack, including a link into this repository."""
    if path.is_symlink():
        link = Path(os.readlink(path))
        link = link if link.is_absolute() else path.parent / link
        if ROOT in link.absolute().parents:
            return True
    try:
        front = (path / "SKILL.md").read_text(encoding="utf-8").split("---", 2)[1]
    except (OSError, IndexError, UnicodeError):
        return False
    return bool(re.search(r"^\s*workflow-pack:\s*session-workflow\s*$", front, re.M))


def retired_copies(target):
    return [target / name for name in RETIRED_SKILLS
            if ((target / name).exists() or (target / name).is_symlink()) and pack_copy(target / name)]


def install(args):
    manifest = check()
    targets = destinations(args)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    records = []
    for target in targets:
        backup = target.parent / "skill-backups" / ("session-workflow-" + stamp)
        changed = []
        for old in retired_copies(target):
            print(f"{'DRY RUN ' if args.dry_run else ''}retire: {old}")
            if not args.dry_run:
                backup.mkdir(parents=True, exist_ok=True)
                old.rename(backup / old.name)
                changed.append("retired:" + old.name)
        for name in manifest:
            source = PACK / "skills" / name
            dest = target / name
            if dest.is_symlink() and dest.resolve() == source.resolve() and args.mode == "link":
                state = "unchanged"
            elif not dest.is_symlink() and args.mode == "copy" and tree_digest(dest) == tree_digest(source):
                state = "unchanged"
            else:
                state = "install"
            print(f"{'DRY RUN ' if args.dry_run else ''}{state}: {dest}")
            if state == "unchanged" or args.dry_run:
                continue
            target.mkdir(parents=True, exist_ok=True)
            # Stage outside discovery root; only expose a complete skill directory.
            stage_root = Path(tempfile.mkdtemp(prefix=".workflow-stage-", dir=target.parent))
            stage = stage_root / name
            saved = backup / name
            replaced = False
            try:
                if args.mode == "link":
                    stage.symlink_to(source, target_is_directory=True)
                else:
                    shutil.copytree(source, stage, ignore=shutil.ignore_patterns("__pycache__", ".DS_Store"))
                if tree_digest(stage) != tree_digest(source):
                    raise ValueError(f"Staged copy differs: {name}")
                if dest.exists() or dest.is_symlink():
                    backup.mkdir(parents=True, exist_ok=True)
                    dest.rename(saved)
                    replaced = True
                try:
                    stage.rename(dest)
                except BaseException:
                    if replaced:
                        saved.rename(dest)
                    raise
                changed.append(name)
            finally:
                shutil.rmtree(stage_root)
        record = {"target": str(target), "version": version(), "mode": args.mode,
                  "changed": changed, "backup": str(backup) if backup.exists() else None,
                  "skills": {name: tree_digest(PACK / "skills" / name) for name in manifest}}
        records.append(record)
        if not args.dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            receipt = target.parent / ".session-workflow-install.json"
            if changed or not receipt.exists():
                receipt.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    if args.report and not args.dry_run:
        report = Path(args.report).expanduser()
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    print(f"{'Dry run' if args.dry_run else 'Installed'} {version()}: {len(manifest)} skills, {len(targets)} destinations")
    return 0


def status(args):
    manifest = check()
    mismatches = 0
    for target in destinations(args):
        for name in manifest:
            expected = tree_digest(PACK / "skills" / name)
            actual = tree_digest(target / name)
            good = actual == expected
            mismatches += not good
            print(f"{'MATCH' if good else 'MISSING/DRIFT'} {target / name}")
        for old in retired_copies(target):
            mismatches += 1
            print(f"RETIRED-PRESENT {old} (rerun install to back it up and remove it)")
    return 1 if mismatches else 0


def bundle(args):
    check()
    output = Path(args.output).expanduser().absolute()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as z:
        bases = [PACK / "skills", PACK / "assets"] if args.plugin_only else [ROOT / "packs", ROOT / "scripts", ROOT / "docs"]
        for base in bases:
            for p in sorted(base.rglob("*")):
                if p.is_file() and "__pycache__" not in p.parts and p.name != ".DS_Store":
                    z.write(p, PLUGIN_NAME + "/" + p.relative_to(PACK if args.plugin_only else ROOT).as_posix())
        extras = (*PLUGIN_MANIFESTS, "README.md", "LICENSE") if args.plugin_only else ("README.md", "LICENSE", ".gitattributes", ".gitignore", *CATALOGS)
        for name in extras:
            z.write((PACK if args.plugin_only else ROOT) / name, PLUGIN_NAME + "/" + name)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + ".sha256").write_text(f"{digest}  {output.name}\n", encoding="utf-8")
    print(f"Bundle: {output}\nSHA-256: {digest}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="Validate portable skills, shared contract and links")
    sub.add_parser("sync-contract", help="Copy shared contract and conditional references into each skill")
    for action in ["install", "status"]:
        p = sub.add_parser(action)
        p.add_argument("--provider", choices=sorted(PROVIDERS), action="append", default=[])
        p.add_argument("--dest", action="append", default=[], help="Exact skill root; repeat for profiles")
        p.add_argument("--all-detected", action="store_true", help="Existing provider roots and profiles only")
        if action == "install":
            p.add_argument("--mode", choices=["copy", "link"], default="copy")
            p.add_argument("--dry-run", action="store_true")
            p.add_argument("--report", help="Write installation receipts as JSON")
    p = sub.add_parser("bundle")
    p.add_argument("--output", required=True, help="Portable ZIP path")
    p.add_argument("--plugin-only", action="store_true", help="Package only native plugin manifests and self-contained skills")
    args = parser.parse_args(argv)
    try:
        if args.command == "sync-contract":
            for name in names():
                for resource in SHARED_RESOURCES:
                    source = PACK / "shared" / resource
                    dest = PACK / "skills" / name / "references" / resource
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, dest)
                for resource in RETIRED_RESOURCES:
                    stale = PACK / "skills" / name / "references" / resource
                    if stale.exists():
                        stale.unlink()
                for resource in RUNTIME_RESOURCES:
                    dest = PACK / "skills" / name / "scripts" / resource
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(PACK / "shared/runtime" / resource, dest)
            check()
            print(f"Synchronized contract {version()} into {len(names())} skills")
            return 0
        if args.command == "check":
            print(f"Verified estafeta {version()}: {len(check())} portable skills")
            return 0
        return {"install": install, "status": status, "bundle": bundle}[args.command](args)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
