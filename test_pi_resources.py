import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import pi_resources


class PiResourcesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.agent = self.home / ".pi/agent"
        self.agent.mkdir(parents=True)
        self.env = patch.dict(os.environ, {"HOME": str(self.home), "PI_CODING_AGENT_DIR": str(self.agent)})
        self.env.start()
        self.addCleanup(self.env.stop)

    def put(self, path, content="fixture"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def test_snapshot_resolves_links_and_keeps_secrets_out_of_project(self):
        extension = self.put(self.home / "external/tool.ts")
        (self.agent / "extensions").mkdir()
        (self.agent / "extensions/tool.ts").symlink_to(extension)
        skill = self.put(self.home / "external/skill/SKILL.md")
        (self.agent / "skills").mkdir()
        (self.agent / "skills/linked").symlink_to(skill.parent, target_is_directory=True)
        self.put(self.agent / "extensions/key.json", "secret")
        self.put(self.agent / "extensions/browser/node_modules/native.node")
        self.put(self.agent / "extensions/browser/.profile/Cookies")
        self.put(self.agent / "skills/linked/.venv/bin/python")
        self.put(self.agent / "auth.json", "auth-secret")
        self.put(self.agent / "sessions/session.jsonl")
        self.put(self.agent / "npm/package.json", '{"dependencies":{"some-package":"1.0.0"}}')
        self.put(self.agent / "npm/package-lock.json", '{}')
        self.put(self.agent / "npm/node_modules/some-package/native.node")
        settings = {"extensions": ["./extensions", "-builtin:mcp"], "packages": ["npm:some-package@1.0.0"]}
        self.put(self.agent / "settings.json", json.dumps(settings))
        root = pi_resources.snapshot()
        snapshot = root / "agent"
        self.assertEqual(root.stat().st_mode & 0o777, 0o700)
        self.assertEqual((snapshot / "extensions/tool.ts").read_text(), "fixture")
        self.assertFalse((snapshot / "extensions/tool.ts").is_symlink())
        self.assertTrue((snapshot / "skills/linked/SKILL.md").is_file())
        self.assertEqual((snapshot / "extensions/key.json").read_text(), "secret")
        self.assertTrue((snapshot / "npm/package-lock.json").is_file())
        for name in ("node_modules", ".venv", ".profile", "auth.json", "sessions"):
            self.assertFalse(list(snapshot.rglob(name)), name)
        self.assertEqual(json.loads((snapshot / "settings.json").read_text()), settings)

    def test_configured_paths_and_shared_skills(self):
        self.put(self.agent / "custom/SKILL.md")
        extension = self.put(self.home / "outside/tool.ts")
        package = self.put(self.home / "package/package.json", '{}').parent
        self.put(self.home / ".agents/skills/shared/SKILL.md")
        settings = {
            "extensions": ["+" + str(extension), "-" + str(extension)],
            "skills": [str(self.agent / "custom")],
            "packages": [{"source": str(package), "skills": []}],
        }
        self.put(self.agent / "settings.json", json.dumps(settings))
        root = pi_resources.snapshot() / "agent"
        result = json.loads((root / "settings.json").read_text())
        self.assertEqual(result["extensions"][0][1:], result["extensions"][1][1:])
        self.assertTrue((root / result["extensions"][0][1:]).is_file())
        self.assertTrue((root / "custom/SKILL.md").is_file())
        self.assertTrue((root / "host-agent-skills/shared/SKILL.md").is_file())
        self.assertEqual(result["packages"][0]["skills"], [])
        self.assertTrue((root / result["packages"][0]["source"] / "package.json").is_file())

    def test_create_refresh_decline_and_failed_snapshot(self):
        script = Path(__file__).parent / "devcontainer-tool.sh"
        project = self.home / "project with spaces"
        command = ["bash", str(script), "create", str(project)]
        self.put(self.agent / "extensions/tool.ts")
        subprocess.run(command, check=True, capture_output=True)
        config_file = project / ".devcontainer/devcontainer.json"
        config = json.loads(config_file.read_text())
        mount = next(m for m in config["mounts"] if isinstance(m, str) and f"target={pi_resources.MOUNT}" in m)
        self.assertIn(",readonly", mount)
        self.assertNotIn(str(project), mount)
        self.assertIn(pi_resources.SETUP, config["postCreateCommand"])
        subprocess.run(["bash", "-n", "-c", config["postCreateCommand"]], check=True)
        self.assertEqual(list(config_file.parent.iterdir()), [config_file])
        subprocess.run(command, input="n\n", text=True, check=True, capture_output=True)
        self.assertEqual(json.loads(config_file.read_text()), config)
        subprocess.run(command, input="y\n", text=True, check=True, capture_output=True)
        refreshed = json.loads(config_file.read_text())
        self.assertEqual(refreshed["postCreateCommand"].count(pi_resources.SETUP), 1)
        self.assertEqual(json.loads(config_file.with_suffix(".json.bak").read_text()), config)
        self.assertNotEqual(refreshed["mounts"], config["mounts"])
        self.put(self.agent / "settings.json", "not json")
        failed = subprocess.run(command, input="y\n", text=True, capture_output=True)
        self.assertNotEqual(failed.returncode, 0)
        self.assertEqual(json.loads(config_file.read_text()), refreshed)

    def test_create_through_symlinks_on_path(self):
        script = Path(__file__).resolve().parent / "devcontainer-tool.sh"
        bin_dir = self.home / "bin with spaces"
        bin_dir.mkdir()
        (bin_dir / "absolute-tool").symlink_to(script)
        (bin_dir / "relative-tool").symlink_to("absolute-tool")
        env = {**os.environ, "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"]}
        for name in ("absolute-tool", "relative-tool"):
            with self.subTest(name=name):
                project = self.home / name
                subprocess.run([name, "create", str(project)], cwd=self.home, env=env, check=True, capture_output=True)
                config = json.loads((project / ".devcontainer/devcontainer.json").read_text())
                self.assertIn(pi_resources.SETUP, config["postCreateCommand"])

    def test_merge_migrates_legacy_mounts_and_preserves_hooks(self):
        for hook in ("echo custom", ["echo", "custom arg"], {"one": "echo one", "two": ["echo", "two"]}):
            with self.subTest(hook=hook):
                existing = {
                    "name": "Custom",
                    "postCreateCommand": hook,
                    "mounts": [
                        {"source": "old", "target": "/home/vscode/.pi/agent/extensions/kagi-websearch.json", "type": "bind"},
                        "source=old,target=/opt/pi-host,type=bind",
                        {"source": "keep", "target": "/data", "type": "bind"},
                    ],
                }
                config = pi_resources.configure({"name": "Base", "forwardPorts": [4000]}, existing)
                self.assertEqual(config["name"], "Custom")
                self.assertEqual(config["forwardPorts"], [4000])
                self.assertEqual(len(config["mounts"]), 2)
                self.assertIn(pi_resources.shell_command(hook), config["postCreateCommand"])
                self.assertTrue(config["postCreateCommand"].endswith(pi_resources.SETUP))

    def test_install_replaces_dotfiles_without_touching_auth_and_installs_dependencies(self):
        self.put(self.agent / "extensions/browser/package.json", '{}')
        self.put(self.agent / "extensions/browser/package-lock.json", '{}')
        self.put(self.agent / "skills/pdf/requirements.txt", "PyMuPDF")
        root = pi_resources.snapshot()
        self.put(self.agent / "extensions/obsolete.ts")
        outside = self.put(self.home / "dotfiles/tool.ts", "untouched")
        (self.agent / "extensions/tool.ts").symlink_to(outside)
        self.put(self.agent / "auth.json", "untouched")
        self.put(root / "agent/extensions/tool.ts", "host version")
        def installed(command, **kwargs):
            if command[0] == "npm":
                self.put(self.agent / "extensions/browser/node_modules/playwright-core/cli.js")

        with patch.object(pi_resources, "__file__", str(root / "pi_resources.py")), patch.object(pi_resources.subprocess, "run", side_effect=installed) as run:
            pi_resources.install()
        self.assertFalse((self.agent / "extensions/obsolete.ts").exists())
        self.assertEqual((self.agent / "extensions/tool.ts").read_text(), "host version")
        self.assertEqual(outside.read_text(), "untouched")
        self.assertEqual((self.agent / "auth.json").read_text(), "untouched")
        self.assertTrue(list((self.home / ".pi").glob("host-backup-*/extensions/obsolete.ts")))
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(commands[0], ["npm", "ci", "--omit=dev", "--legacy-peer-deps"])
        self.assertEqual(commands[1][2:], ["install", "--with-deps", "chromium"])
        self.assertEqual(commands[2][:3], ["python3", "-m", "venv"])
        self.assertEqual(commands[3][1:3], ["install", "-r"])
        self.assertTrue(all(call.kwargs["check"] for call in run.call_args_list))

    def test_dependency_failure_stops_setup(self):
        self.put(self.agent / "extensions/tool/package.json", '{}')
        self.put(self.agent / "skills/pdf/requirements.txt")
        root = pi_resources.snapshot()
        failure = subprocess.CalledProcessError(1, "npm")
        with patch.object(pi_resources, "__file__", str(root / "pi_resources.py")), patch.object(pi_resources.subprocess, "run", side_effect=failure) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                pi_resources.install()
        self.assertEqual(run.call_count, 1)


if __name__ == "__main__":
    unittest.main()
