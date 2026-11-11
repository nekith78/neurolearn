from __future__ import annotations

import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "plugins" / "neurolearn" / "skills" / "neurolearn" / "scripts" / "run_neurolearn.py"


def load_launcher():
    spec = importlib.util.spec_from_file_location("run_neurolearn", LAUNCHER)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load Codex launcher")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CodexAdapterTest(unittest.TestCase):
    def test_finds_plugin_root_from_nested_skill_script(self) -> None:
        module = load_launcher()
        self.assertEqual(module.find_plugin_root(LAUNCHER), ROOT)

    def test_invokes_uv_without_shell_interpolation(self) -> None:
        module = load_launcher()
        completed = subprocess.CompletedProcess([], 0)
        with patch.object(module.subprocess, "run", return_value=completed) as run:
            result = module.main(["transcribe", "https://youtu.be/a;b"])

        self.assertEqual(result, 0)
        command = run.call_args.args[0]
        self.assertEqual(command[:4], ["uv", "run", "--project", str(ROOT)])
        self.assertEqual(command[4:], ["neurolearn", "transcribe", "https://youtu.be/a;b"])
        self.assertNotIn("shell", run.call_args.kwargs)

    def test_missing_project_fails_clearly(self) -> None:
        module = load_launcher()
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_script = Path(temp_dir) / "codex" / "skills" / "x" / "run.py"
            fake_script.parent.mkdir(parents=True)
            fake_script.touch()
            with self.assertRaisesRegex(RuntimeError, "pyproject.toml"):
                module.find_plugin_root(fake_script, home=Path(temp_dir) / "empty-home")

    def test_explicit_project_overrides_unrelated_ancestor(self) -> None:
        module = load_launcher()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            unrelated = temp / "unrelated"
            unrelated.mkdir()
            (unrelated / "pyproject.toml").write_text('[project]\nname = "unrelated"\n', encoding="utf-8")
            fake_script = unrelated / "cache" / "run.py"
            fake_script.parent.mkdir()
            fake_script.touch()
            project = temp / "neurolearn"
            project.mkdir()
            (project / "pyproject.toml").write_text('[project]\nname = "neurolearn"\n', encoding="utf-8")
            with patch.dict(os.environ, {"NEUROLEARN_PROJECT_DIR": str(project)}):
                self.assertEqual(module.find_plugin_root(fake_script), project)

    def test_cached_plugin_finds_personal_source_project(self) -> None:
        module = load_launcher()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            fake_script = temp / "cache" / "skills" / "neurolearn" / "run.py"
            fake_script.parent.mkdir(parents=True)
            fake_script.touch()
            project = temp / "home" / "youtube-transcribe"
            project.mkdir(parents=True)
            (project / "pyproject.toml").write_text(
                '[project]\nname = "neurolearn"\n', encoding="utf-8"
            )

            self.assertEqual(
                module.find_plugin_root(fake_script, home=temp / "home"), project
            )


if __name__ == "__main__":
    unittest.main()
