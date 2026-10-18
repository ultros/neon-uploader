"""Start Neon Uploader, installing missing Python dependencies in a local venv.

This launcher intentionally never installs into the system Python or runs sudo.
"""

import hashlib
import os
import subprocess
import sys
import venv
from pathlib import Path


ROOT = Path(__file__).resolve().parent
APP = ROOT / "neon-uploader.py"
REQUIREMENTS = ROOT / "requirements.txt"
ENV_DIR = ROOT / ".venv"
STAMP = ENV_DIR / ".neon-requirements.sha256"

# Run the check in the actual environment used to launch the application.
# pip's bundled packaging parser understands Python package version constraints.
CHECK_CODE = r'''
import sys
from importlib.metadata import version
from pathlib import Path
try:
    from packaging.requirements import Requirement
except ImportError:
    from pip._vendor.packaging.requirements import Requirement

try:
    for raw in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
        line = raw.split(" #", 1)[0].strip()
        if not line or line.startswith("#"):
            continue
        requirement = Requirement(line)
        if requirement.marker is not None and not requirement.marker.evaluate():
            continue
        if not requirement.specifier.contains(version(requirement.name), prereleases=False):
            raise RuntimeError("Unsatisfied requirement: " + line)
    from flask import Flask
    from werkzeug.utils import secure_filename
except Exception as error:
    print(error, file=sys.stderr)
    sys.exit(1)
'''


def environment_python():
    """Path to the isolated interpreter, on Windows or POSIX."""
    return ENV_DIR / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def requirements_hash():
    if not REQUIREMENTS.is_file():
        raise RuntimeError(f"Missing requirements file: {REQUIREMENTS}")
    return hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()


def environment_healthy(python):
    """Offline check: all declared requirements, imports and transitive deps."""
    check = subprocess.run(
        [str(python), "-c", CHECK_CODE, str(REQUIREMENTS)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    )
    if check.returncode:
        return False
    deps = subprocess.run(
        [str(python), "-m", "pip", "check"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    )
    return deps.returncode == 0


def prepare_environment():
    """Create venv if needed; install only when dependencies changed or broke."""
    if sys.version_info < (3, 9):
        raise RuntimeError("Neon Uploader requires Python 3.9 or newer.")
    fingerprint = requirements_hash()
    python = environment_python()

    if not python.is_file():
        print("[neon] Creating isolated Python environment (.venv)...", flush=True)
        try:
            venv.EnvBuilder(with_pip=True).create(str(ENV_DIR))
        except Exception as error:
            raise RuntimeError(
                "Could not create .venv. Install Python's venv/ensurepip support "
                "(on Debian/Ubuntu: python3-venv), then retry."
            ) from error
        if not python.is_file():
            raise RuntimeError("Virtual environment did not provide a Python interpreter.")

    # Probe *even without a marker*: an existing venv may already contain
    # everything needed, in which case running pip again would be wasteful.
    if environment_healthy(python):
        if not STAMP.is_file() or STAMP.read_text(encoding="ascii").strip() != fingerprint:
            STAMP.write_text(fingerprint + "\n", encoding="ascii")
        print("[neon] Dependencies detected. Skipping installation.", flush=True)
        return python

    print("[neon] Installing or repairing missing/outdated packages from requirements.txt...", flush=True)
    try:
        subprocess.run(
            [str(python), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(REQUIREMENTS)],
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise RuntimeError(
            "Dependency installation failed. Check network access and pip output above. "
            "The application was not started."
        ) from error

    if not environment_healthy(python):
        raise RuntimeError(
            "Installed packages failed verification. Inspect .venv with "
            f"'{python} -m pip check'."
        )
    STAMP.write_text(fingerprint + "\n", encoding="ascii")
    print("[neon] Dependencies verified.", flush=True)
    return python


def main():
    try:
        python = prepare_environment()
        environment = os.environ.copy()
        environment["NEON_BOOTSTRAPPED"] = "1"
        return subprocess.call([str(python), str(APP), *sys.argv[1:]], env=environment)
    except (RuntimeError, OSError) as error:
        print(f"[neon] ERROR: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
