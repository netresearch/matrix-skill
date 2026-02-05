#!/usr/bin/env python3
"""Matrix Skill health check and dependency installer.

Checks all dependencies and configuration, installs missing packages,
and reports on E2EE setup status.

Usage:
    matrix-doctor.py [--install] [--json] [--quiet]
    matrix-doctor.py --help

Options:
    --install   Automatically install missing dependencies
    --json      Output as JSON
    --quiet     Only show errors
    --help      Show this help
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def check_command_exists(cmd: str) -> bool:
    """Check if a command exists in PATH."""
    return shutil.which(cmd) is not None


def get_pip_command() -> str | None:
    """Get the best available pip command. Priority: uvx, pip, pip3."""
    # Check uvx first (preferred)
    if check_command_exists("uvx"):
        return "uvx pip"
    if check_command_exists("uv"):
        return "uv pip"
    if check_command_exists("pip"):
        return "pip"
    if check_command_exists("pip3"):
        return "pip3"
    return None


def run_pip_command(pip_cmd: str, args: list[str]) -> tuple[bool, str]:
    """Run a pip command and return success status and output."""
    if pip_cmd.startswith("uvx"):
        full_cmd = ["uvx", "pip"] + args
    elif pip_cmd.startswith("uv"):
        full_cmd = ["uv", "pip"] + args
    else:
        full_cmd = [pip_cmd] + args

    try:
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=120
        )
        return result.returncode == 0, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return False, "Command timed out"
    except Exception as e:
        return False, str(e)


def check_python_package(package: str) -> bool:
    """Check if a Python package is importable."""
    try:
        __import__(package)
        return True
    except ImportError:
        return False


def check_matrix_nio_e2ee() -> tuple[bool, str]:
    """Check if matrix-nio with E2EE support is installed."""
    try:
        import nio
        # Try to get version
        try:
            from importlib.metadata import version
            nio_version = version("matrix-nio")
        except Exception:
            nio_version = "unknown"

        # Check for E2EE support by trying to import olm
        try:
            from nio.crypto import Olm  # noqa: F401
            return True, f"matrix-nio {nio_version} with E2EE support"
        except ImportError:
            return False, f"matrix-nio {nio_version} installed but E2EE deps missing"
    except ImportError:
        return False, "matrix-nio not installed"


def check_libolm() -> tuple[bool, str]:
    """Check if libolm system library is installed."""
    try:
        import _libolm  # noqa: F401
        return True, "libolm available"
    except ImportError:
        pass

    # Try loading the shared library
    import ctypes.util
    lib = ctypes.util.find_library("olm")
    if lib:
        return True, f"libolm found: {lib}"
    return False, "libolm not found (required for E2EE)"


def check_config() -> tuple[bool, str, dict]:
    """Check Matrix configuration file."""
    config_path = Path.home() / ".config" / "matrix" / "config.json"
    if not config_path.exists():
        return False, f"Config not found at {config_path}", {}

    try:
        with open(config_path) as f:
            config = json.load(f)

        required = ["homeserver", "user_id"]
        missing = [k for k in required if k not in config]
        if missing:
            return False, f"Config missing required fields: {', '.join(missing)}", config

        return True, f"Config OK: {config.get('user_id')}", config
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON in config: {e}", {}
    except Exception as e:
        return False, f"Error reading config: {e}", {}


def check_e2ee_setup() -> tuple[bool, str]:
    """Check E2EE device setup status."""
    store_dir = Path.home() / ".local" / "share" / "matrix-skill" / "store"
    creds_file = store_dir / "credentials.json"

    if not store_dir.exists():
        return False, "E2EE not set up (no store directory)"

    if not creds_file.exists():
        return False, "E2EE not set up (no credentials)"

    try:
        with open(creds_file) as f:
            creds = json.load(f)
        device_id = creds.get("device_id", "unknown")
        return True, f"E2EE device configured: {device_id}"
    except Exception as e:
        return False, f"Error reading E2EE credentials: {e}"


def install_dependencies(pip_cmd: str, quiet: bool = False) -> tuple[bool, list[str]]:
    """Install missing dependencies."""
    messages = []

    # Install matrix-nio with E2EE support
    if not quiet:
        messages.append("Installing matrix-nio[e2e]...")

    success, output = run_pip_command(pip_cmd, ["install", "matrix-nio[e2e]"])
    if success:
        messages.append("matrix-nio[e2e] installed successfully")
    else:
        messages.append(f"Failed to install matrix-nio[e2e]: {output}")
        return False, messages

    return True, messages


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Matrix Skill health check and setup")
    parser.add_argument("--install", action="store_true",
                        help="Automatically install missing dependencies")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--quiet", "-q", action="store_true", help="Only show errors")

    args = parser.parse_args()

    checks = {
        "pip_available": {"ok": False, "message": "", "critical": True},
        "matrix_nio": {"ok": False, "message": "", "critical": True},
        "libolm": {"ok": False, "message": "", "critical": False},
        "config": {"ok": False, "message": "", "critical": True},
        "e2ee_setup": {"ok": False, "message": "", "critical": False},
    }

    # Check pip availability
    pip_cmd = get_pip_command()
    if pip_cmd:
        checks["pip_available"]["ok"] = True
        checks["pip_available"]["message"] = f"Using: {pip_cmd}"
    else:
        checks["pip_available"]["message"] = "No pip command found (tried: uvx, uv pip, pip, pip3)"

    # Check matrix-nio
    nio_ok, nio_msg = check_matrix_nio_e2ee()
    checks["matrix_nio"]["ok"] = nio_ok
    checks["matrix_nio"]["message"] = nio_msg

    # Check libolm
    olm_ok, olm_msg = check_libolm()
    checks["libolm"]["ok"] = olm_ok
    checks["libolm"]["message"] = olm_msg

    # Check config
    config_ok, config_msg, config_data = check_config()
    checks["config"]["ok"] = config_ok
    checks["config"]["message"] = config_msg

    # Check E2EE setup
    e2ee_ok, e2ee_msg = check_e2ee_setup()
    checks["e2ee_setup"]["ok"] = e2ee_ok
    checks["e2ee_setup"]["message"] = e2ee_msg

    # Auto-install if requested
    if args.install and pip_cmd:
        if not checks["matrix_nio"]["ok"]:
            success, messages = install_dependencies(pip_cmd, args.quiet)
            if success:
                # Re-check after install
                nio_ok, nio_msg = check_matrix_nio_e2ee()
                checks["matrix_nio"]["ok"] = nio_ok
                checks["matrix_nio"]["message"] = nio_msg
                checks["install_messages"] = messages

    # Output
    if args.json:
        print(json.dumps(checks, indent=2))
        sys.exit(0 if all(c["ok"] for c in checks.values() if c.get("critical")) else 1)

    # Pretty output
    all_ok = True
    critical_ok = True

    if not args.quiet:
        print("=" * 60)
        print("Matrix Skill Health Check")
        print("=" * 60)
        print()

    for name, check in checks.items():
        if name == "install_messages":
            continue

        icon = "OK" if check["ok"] else "FAIL"
        critical = " (required)" if check.get("critical") else ""

        if not check["ok"]:
            all_ok = False
            if check.get("critical"):
                critical_ok = False

        if not args.quiet or not check["ok"]:
            print(f"[{icon}] {name}{critical}")
            print(f"     {check['message']}")
            print()

    # Summary
    if not args.quiet:
        print("=" * 60)

    if all_ok:
        print("All checks passed! Matrix Skill is ready to use.")
    elif critical_ok:
        print("Core functionality OK. Some optional features may be limited.")
    else:
        print("Some required checks failed. See above for details.")
        print()
        print("Quick fix:")
        if not checks["pip_available"]["ok"]:
            print("  - Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh")
        if not checks["matrix_nio"]["ok"]:
            print(f"  - Run: matrix-doctor.py --install")
        if not checks["config"]["ok"]:
            print("  - Set up Matrix: see SKILL.md Setup Guide")
        if not checks["e2ee_setup"]["ok"] and checks["config"]["ok"]:
            print("  - Run: matrix-e2ee-setup.py")

    sys.exit(0 if critical_ok else 1)


if __name__ == "__main__":
    main()
