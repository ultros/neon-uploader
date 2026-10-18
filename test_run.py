"""Tests for the automatic, isolated dependency bootstrapper."""
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).with_name("run.py")
spec = importlib.util.spec_from_file_location("neon_runner", SCRIPT)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name)
        (self.root / "requirements.txt").write_text("Flask>=3.0,<4\n", encoding="utf-8")
        for attr, value in {
            "ROOT": self.root,
            "APP": self.root / "neon-uploader.py",
            "REQUIREMENTS": self.root / "requirements.txt",
            "ENV_DIR": self.root / ".venv",
            "STAMP": self.root / ".venv" / ".neon-requirements.sha256",
        }.items():
            patcher = mock.patch.object(runner, attr, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def make_python(self):
        target = runner.environment_python()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"fake interpreter")

    def test_first_run_installs_and_next_run_skips(self):
        self.make_python()
        with mock.patch.object(runner, "environment_healthy", side_effect=[False, True, True]) as healthy, \
             mock.patch.object(runner.subprocess, "run") as install:
            first = runner.prepare_environment()
            second = runner.prepare_environment()
        self.assertEqual(first, second)
        self.assertEqual(install.call_count, 1)
        args = install.call_args.args[0]
        self.assertEqual(args[1:4], ["-m", "pip", "install"])
        self.assertIn("-r", args)
        self.assertTrue(runner.STAMP.is_file())
        healthy.assert_called()

    def test_preexisting_complete_environment_skips_without_marker(self):
        self.make_python()
        with mock.patch.object(runner, "environment_healthy", return_value=True), \
             mock.patch.object(runner.subprocess, "run") as install:
            runner.prepare_environment()
        install.assert_not_called()
        self.assertTrue(runner.STAMP.exists())

    def test_changed_requirements_reinstalls(self):
        self.make_python()
        with mock.patch.object(runner, "environment_healthy", side_effect=[False, True, False, True]), \
             mock.patch.object(runner.subprocess, "run") as install:
            runner.prepare_environment()
            runner.REQUIREMENTS.write_text("Flask>=3.1,<4\n", encoding="utf-8")
            runner.prepare_environment()
            self.assertEqual(install.call_count, 2)

    def test_broken_environment_reinstalls_even_with_same_requirements(self):
        self.make_python()
        with mock.patch.object(runner, "environment_healthy", side_effect=[False, True, False, True]), \
             mock.patch.object(runner.subprocess, "run") as install:
            runner.prepare_environment()
            runner.prepare_environment()
            self.assertEqual(install.call_count, 2)

    def test_creates_environment_once(self):
        def make_env(*args, **kwargs):
            self.make_python()
        with mock.patch.object(runner.venv.EnvBuilder, "create", side_effect=make_env) as create, \
             mock.patch.object(runner, "environment_healthy", return_value=True), \
             mock.patch.object(runner.subprocess, "run"):
            runner.prepare_environment()
            runner.prepare_environment()
        self.assertEqual(create.call_count, 1)

    def test_failed_install_is_not_marked_successful(self):
        self.make_python()
        with mock.patch.object(runner, "environment_healthy", return_value=False), \
             mock.patch.object(runner.subprocess, "run", side_effect=subprocess.CalledProcessError(1, ["pip"])):
            with self.assertRaisesRegex(RuntimeError, "Dependency installation failed"):
                runner.prepare_environment()
        self.assertFalse(runner.STAMP.exists())

    def test_missing_requirements_fails_without_install(self):
        runner.REQUIREMENTS.unlink()
        with self.assertRaisesRegex(RuntimeError, "Missing requirements"):
            runner.prepare_environment()

    def test_environment_probe_checks_installs_and_pip_health(self):
        self.make_python()
        ok = subprocess.CompletedProcess(["python"], 0)
        fail = subprocess.CompletedProcess(["python"], 1)
        with mock.patch.object(runner.subprocess, "run", side_effect=[ok, ok, fail]) as run:
            self.assertTrue(runner.environment_healthy(runner.environment_python()))
            self.assertFalse(runner.environment_healthy(runner.environment_python()))
        self.assertEqual(run.call_count, 3)


if __name__ == "__main__":
    unittest.main()
