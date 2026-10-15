"""Integration checks for preservation, reproducibility and relocation."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

SPEC = importlib.util.spec_from_file_location("workflow", Path(__file__).with_name("workflow.py"))
w = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(w)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="workflow-test-")
        self.base = Path(self.temp.name)
        self.target = self.base / "profile with spaces/skills"

    def tearDown(self):
        self.temp.cleanup()

    def run_command(self, *args):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return w.main(list(args))

    def install(self, *args):
        return self.run_command("install", "--dest", str(self.target), *args)

    def test_dry_run_has_no_writes(self):
        self.assertEqual(self.install("--dry-run"), 0)
        self.assertFalse(self.target.parent.exists())

    def test_installation_in_a_unicode_profile_directory(self):
        self.target = self.base / "Práce-日本語-العربية" / "skills"
        self.assertEqual(self.install(), 0)
        self.assertEqual(self.run_command("status", "--dest", str(self.target)), 0)

    def test_plugin_manifest_drift_blocks_installation(self):
        isolated = self.base / "pack"
        shutil.copytree(w.PACK, isolated)
        manifest = isolated / ".claude-plugin/plugin.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["version"] = "0.0.0"
        manifest.write_text(json.dumps(data), encoding="utf-8")
        with patch.object(w, "PACK", isolated):
            self.assertEqual(self.install(), 1)
        self.assertFalse(self.target.exists())

    def test_plugin_archive_is_self_contained_and_runs_after_relocation(self):
        archive = self.base / "plugin.zip"
        self.assertEqual(self.run_command("bundle", "--plugin-only", "--output", str(archive)), 0)
        unpacked = self.base / "移動済み plugin"
        with zipfile.ZipFile(archive) as z:
            self.assertIsNone(z.testzip())
            z.extractall(unpacked)
        plugin = unpacked / "estafeta"
        self.assertEqual((plugin / "LICENSE").read_bytes(), (w.ROOT / "LICENSE").read_bytes())
        self.assertIn("](assets/cover.webp)", (plugin / "README.md").read_text(encoding="utf-8"))
        self.assertEqual((plugin / "assets/cover.webp").read_bytes(), (w.PACK / "assets/cover.webp").read_bytes())
        for manifest in w.PLUGIN_MANIFESTS:
            data = json.loads((plugin / manifest).read_text(encoding="utf-8"))
            self.assertEqual(data["name"], "estafeta")
            self.assertEqual(data["version"], w.version())
        for name in w.names():
            self.assertEqual(w.tree_digest(plugin / "skills" / name), w.tree_digest(w.PACK / "skills" / name))
        project = self.base / "fresh project"
        project.mkdir()
        result = subprocess.run([sys.executable, str(plugin / "skills/session-start/scripts/session.py"),
            "--root", str(project), "snapshot"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["ok"])
        self.assertFalse((project / ".agent-state").exists())

    def test_codex_uses_current_location_on_new_host_and_preserves_legacy(self):
        with patch.dict(w.os.environ, {}, clear=True):
            self.assertEqual(w.provider_path("codex", self.base), self.base / ".agents/skills")
            legacy = self.base / ".codex/skills"
            legacy.mkdir(parents=True)
            self.assertEqual(w.provider_path("codex", self.base), legacy)

    def test_backup_idempotence_and_unrelated_skill_preserved(self):
        old = self.target / "session-start"
        old.mkdir(parents=True)
        (old / "personal.txt").write_text("keep original")
        unrelated = self.target / "other-skill"
        unrelated.mkdir()
        (unrelated / "SKILL.md").write_text("leave alone")
        self.assertEqual(self.install(), 0)
        backups = list(self.target.parent.glob("skill-backups/*/session-start/personal.txt"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), "keep original")
        self.assertEqual((unrelated / "SKILL.md").read_text(), "leave alone")
        receipt = self.target.parent / ".session-workflow-install.json"
        before = receipt.read_bytes()
        self.assertEqual(self.install(), 0)
        self.assertEqual(receipt.read_bytes(), before)
        self.assertEqual(len(list(self.target.parent.glob("skill-backups/*"))), 1)
        self.assertEqual(self.run_command("status", "--dest", str(self.target)), 0)

    def test_drift_is_detected_and_preserved_on_reinstall(self):
        self.assertEqual(self.install(), 0)
        p = self.target / "session-end/SKILL.md"
        p.write_text(p.read_text(encoding="utf-8") + "\nLocal customization\n", encoding="utf-8")
        self.assertEqual(self.run_command("status", "--dest", str(self.target)), 1)
        self.assertEqual(self.install(), 0)
        backup = next(self.target.parent.glob("skill-backups/*/session-end/SKILL.md"))
        self.assertIn("Local customization", backup.read_text(encoding="utf-8"))

    def test_staging_failure_leaves_existing_install_untouched(self):
        old = self.target / "plan-and-orchestrate"
        old.mkdir(parents=True)
        (old / "SKILL.md").write_text("old version")
        with patch.object(w.shutil, "copytree", side_effect=OSError("simulated disk failure")):
            self.assertEqual(self.install(), 1)
        self.assertEqual((old / "SKILL.md").read_text(), "old version")
        self.assertFalse(list(self.target.parent.glob(".workflow-stage-*")))

    def test_replacement_failure_restores_old_directory(self):
        old = self.target / "plan-and-orchestrate"
        old.mkdir(parents=True)
        (old / "SKILL.md").write_text("old version")
        original = Path.rename

        def fail_staged(source, dest):
            if source.parent.name.startswith(".workflow-stage-"):
                raise OSError("simulated rename failure")
            return original(source, dest)

        with patch.object(Path, "rename", fail_staged):
            self.assertEqual(self.install(), 1)
        self.assertEqual((old / "SKILL.md").read_text(), "old version")

    def test_source_and_nested_destinations_are_rejected(self):
        self.assertEqual(self.run_command("install", "--dest", str(w.PACK / "skills")), 1)
        self.assertEqual(self.run_command("install", "--dest", str(self.target),
                                         "--dest", str(self.target / "nested")), 1)
        self.assertFalse(self.target.exists())

    def test_contract_drift_blocks_installation(self):
        isolated = self.base / "pack"
        shutil.copytree(w.PACK, isolated)
        (isolated / "skills/session-start/references/workflow-contract.md").write_text("stale")
        with patch.object(w, "PACK", isolated):
            self.assertEqual(self.install(), 1)
        self.assertFalse(self.target.exists())

    def test_conditional_references_reject_drift_and_sync_from_one_source(self):
        isolated = self.base / "pack"
        shutil.copytree(w.PACK, isolated)
        with patch.object(w, "PACK", isolated):
            for resource in ("quickstart.md", "runtime.md"):
                with self.subTest(resource=resource):
                    dest = isolated / "skills/session-end/references" / resource
                    dest.write_text("stale", encoding="utf-8")
                    self.assertEqual(self.install(), 1)
                    self.assertFalse(self.target.exists())
                    self.assertEqual(self.run_command("sync-contract"), 0)
                    expected = (isolated / "shared" / resource).read_bytes()
                    for name in w.names():
                        self.assertEqual((isolated / "skills" / name / "references" / resource).read_bytes(),
                                         expected)
            self.assertEqual(self.install(), 0)

    def test_runtime_drift_is_rejected_and_synced_before_install(self):
        isolated = self.base / "pack"
        shutil.copytree(w.PACK, isolated)
        payload = isolated / "skills/session-start/scripts/session.py"
        payload.write_text("stale runtime", encoding="utf-8")
        with patch.object(w, "PACK", isolated):
            self.assertEqual(self.install(), 1)
            self.assertFalse(self.target.exists())
            self.assertEqual(self.run_command("sync-contract"), 0)
            self.assertEqual(payload.read_bytes(), (isolated / "shared/runtime/session.py").read_bytes())
            self.assertEqual(self.install(), 0)

    def test_relocated_bundle_installs_without_source_checkout(self):
        archive = self.base / "bundle.zip"
        self.assertEqual(self.run_command("bundle", "--output", str(archive)), 0)
        extracted = self.base / "another device"
        with zipfile.ZipFile(archive) as z:
            z.extractall(extracted)
        script = extracted / "estafeta/scripts/workflow.py"
        source = extracted / "estafeta"
        self.assertIn("](packs/session-workflow/assets/cover.webp)",
                      (source / "README.md").read_text(encoding="utf-8"))
        self.assertEqual((source / "packs/session-workflow/assets/cover.webp").read_bytes(),
                         (w.PACK / "assets/cover.webp").read_bytes())
        result = subprocess.run([sys.executable, str(script), "install", "--dest", str(self.target)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in w.names():
            self.assertEqual(w.tree_digest(self.target / name), w.tree_digest(w.PACK / "skills" / name))
        self.assertTrue(archive.with_suffix(".zip.sha256").is_file())
        project = self.base / "standalone project"
        project.mkdir()
        runtime = self.target / "session-start/scripts/session.py"
        started = subprocess.run([sys.executable, str(runtime), "--root", str(project), "begin", "--session", "standalone"],
                                 capture_output=True, text=True)
        self.assertEqual(started.returncode, 0, started.stderr + started.stdout)
        self.assertEqual(json.loads(started.stdout)["result"]["session_id"], "standalone")

    def test_retired_pack_skill_is_backed_up_but_same_name_from_another_pack_is_kept(self):
        old = self.target / "handover-changelog"
        old.mkdir(parents=True)
        (old / "SKILL.md").write_text("---\nname: handover-changelog\nmetadata:\n  workflow-pack: session-workflow\n---\nold\n")
        self.assertEqual(self.run_command("status", "--dest", str(self.target)), 1)
        self.assertEqual(self.install(), 0)
        self.assertFalse(old.exists())
        backup = next(self.target.parent.glob("skill-backups/*/handover-changelog/SKILL.md"))
        self.assertIn("workflow-pack: session-workflow", backup.read_text())
        self.assertEqual(self.run_command("status", "--dest", str(self.target)), 0)
        other = self.base / "other profile/skills"
        foreign = other / "handover-changelog"
        foreign.mkdir(parents=True)
        (foreign / "SKILL.md").write_text("---\nname: handover-changelog\n---\nAnother pack's skill\n")
        self.assertEqual(self.run_command("install", "--dest", str(other)), 0)
        self.assertEqual((foreign / "SKILL.md").read_text(), "---\nname: handover-changelog\n---\nAnother pack's skill\n")

    @unittest.skipIf(sys.platform == "win32", "Windows symlinks require optional OS privilege")
    def test_retired_link_into_this_repository_is_removed_from_link_installs(self):
        self.target.mkdir(parents=True)
        (self.target / "handover-changelog").symlink_to(w.PACK / "skills/handover-changelog", target_is_directory=True)
        self.assertEqual(self.install("--mode", "link"), 0)
        self.assertFalse((self.target / "handover-changelog").is_symlink())

    def test_stale_version_text_blocks_installation(self):
        isolated = self.base / "pack"
        shutil.copytree(w.PACK, isolated)
        template = isolated / "skills/session-start/templates/project-context.md"
        original = template.read_text(encoding="utf-8")
        for product in ("estafeta", "session-workflow"):
            with self.subTest(product=product):
                template.write_text(original + f"\n- Workflow: {product} 2.3.0\n", encoding="utf-8")
                with patch.object(w, "PACK", isolated):
                    self.assertEqual(self.install(), 1)
                self.assertFalse(self.target.exists())

    def test_copy_mode_accepts_crlf_source_after_relocation(self):
        isolated = self.base / "crlf-pack"
        shutil.copytree(w.PACK, isolated)
        for p in isolated.rglob("*"):
            if p.is_file() and p.suffix in (".md", ".list", ".yaml"):
                p.write_bytes(p.read_bytes().replace(b"\n", b"\r\n"))
        with patch.object(w, "PACK", isolated):
            self.assertEqual(self.install(), 0)
            self.assertEqual(self.run_command("status", "--dest", str(self.target)), 0)

    @unittest.skipIf(sys.platform == "win32", "Windows symlinks require optional OS privilege")
    def test_link_mode_is_idempotent_and_copy_migration_keeps_source(self):
        self.assertEqual(self.install("--mode", "link"), 0)
        self.assertTrue((self.target / "session-start").is_symlink())
        self.assertEqual(self.install("--mode", "link"), 0)
        self.assertFalse((self.target.parent / "skill-backups").exists())
        self.assertEqual(self.install("--mode", "copy"), 0)
        self.assertFalse((self.target / "session-start").is_symlink())
        self.assertTrue((w.PACK / "skills/session-start/SKILL.md").is_file())

    def test_relay_packet_template_matches_runtime_and_golden_worker(self):
        base = w.PACK / "skills/agent-relay"
        text = (base / "templates/packet.md").read_text(encoding="utf-8")
        spec = importlib.util.spec_from_file_location("relay_runtime", base / "scripts/session.py")
        runtime = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runtime)
        self.assertIn(runtime.RELAY_OPEN, text)
        self.assertIn(runtime.RELAY_CLOSE, text)
        for outcome in runtime.RELAY_OUTCOMES:
            self.assertIn(outcome, text)
        header = text.split("```relay-packet", 1)[1].split("```", 1)[0]
        stub = (Path(__file__).with_name("golden") / "stub_worker.py").read_text(encoding="utf-8")
        for key in ("mode", "workspace", "runtime", "phase", "worker_session", "required_checks"):
            self.assertIn(f'"{key}"', header)
            self.assertIn(f'packet["{key}"]', stub)
        adapters = (base / "references/adapters.md").read_text(encoding="utf-8")
        for token in ("{packet_text}", "{reply_file}", "{workspace}", "{state_dir}"):
            self.assertIn(token, adapters)

    def test_live_verify_refuses_a_scenario_without_verify_steps(self):
        spec = importlib.util.spec_from_file_location("relay_golden", Path(__file__).with_name("test_relay.py"))
        golden = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(golden)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            golden.main(["--live-verify", "failures", "--root", str(self.base)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
