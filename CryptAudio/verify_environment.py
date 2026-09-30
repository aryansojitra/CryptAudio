"""Environment verification for CryptAudio (Phase 1).

This script performs no cryptographic, audio, or steganographic work. It simply
confirms that the Python environment is ready for development by checking:

    * Python version
    * pip version
    * cryptography installation
    * numpy installation
    * matplotlib installation
    * pytest installation
    * Tkinter availability

Run it from inside the project's virtual environment:

    python verify_environment.py

The process exits with status code 0 if every check passes, or 1 otherwise.
"""

from __future__ import annotations

import sys
from importlib.metadata import PackageNotFoundError, version

# Minimum Python version required by the project.
MIN_PYTHON = (3, 9)

# Packages that must be installed via pip (Tkinter is checked separately
# because it ships with Python rather than being installed through pip).
REQUIRED_PACKAGES = ("cryptography", "numpy", "matplotlib", "pytest")


def check_python_version() -> bool:
    """Report the running Python version and whether it meets the minimum."""
    current = sys.version_info[:3]
    ok = current >= MIN_PYTHON
    print(f"[{'OK' if ok else 'FAIL'}] Python version: "
          f"{'.'.join(map(str, current))} "
          f"(required >= {'.'.join(map(str, MIN_PYTHON))})")
    return ok


def check_pip_version() -> bool:
    """Report the installed pip version."""
    try:
        pip_version = version("pip")
    except PackageNotFoundError:
        print("[FAIL] pip: not available")
        return False
    print(f"[OK] pip version: {pip_version}")
    return True


def check_package(name: str) -> bool:
    """Report whether a pip-installed package is available and its version."""
    try:
        pkg_version = version(name)
    except PackageNotFoundError:
        print(f"[FAIL] {name}: NOT installed")
        return False
    print(f"[OK] {name} version: {pkg_version}")
    return True


def check_tkinter() -> bool:
    """Report whether the Tkinter GUI toolkit is importable."""
    try:
        import tkinter  # noqa: F401
    except ImportError as exc:
        print(f"[FAIL] Tkinter: NOT available ({exc})")
        return False
    print(f"[OK] Tkinter available: Tcl/Tk {tkinter.TkVersion}")
    return True


def main() -> int:
    """Run all verification checks and print a summary."""
    print("=" * 60)
    print("CryptAudio — Environment Verification (Phase 1)")
    print("=" * 60)

    results: list[bool] = []
    results.append(check_python_version())
    results.append(check_pip_version())
    for package in REQUIRED_PACKAGES:
        results.append(check_package(package))
    results.append(check_tkinter())

    print("=" * 60)
    if all(results):
        print("RESULT: All checks PASSED — environment is ready.")
        print("=" * 60)
        return 0

    print("RESULT: One or more checks FAILED — see lines above.")
    print("=" * 60)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
