"""Dependency checking for E2EE scripts.

All functions use ONLY stdlib.
"""

import os
import sys


def check_e2ee_dependencies() -> None:
    """Check that matrix-nio[e2e] dependencies are available.

    Prints helpful installation instructions and exits with code 1
    if dependencies are missing. Call this before importing nio.
    """
    try:
        from nio import AsyncClient  # noqa: F401
    except ImportError as e:
        error_msg = str(e).lower()
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        if "olm" in error_msg:
            print("Error: libolm library not found.", file=sys.stderr)
            print("", file=sys.stderr)
            print("Install libolm for your platform:", file=sys.stderr)
            print("  Debian/Ubuntu: sudo apt install libolm-dev", file=sys.stderr)
            print("  Fedora:        sudo dnf install libolm-devel", file=sys.stderr)
            print("  macOS:         brew install libolm", file=sys.stderr)
        elif "nio" in error_msg or "matrix" in error_msg:
            print("Error: matrix-nio library not found.", file=sys.stderr)
            print("", file=sys.stderr)
            print("Install with (try in order):", file=sys.stderr)
            print("  uvx pip install 'matrix-nio[e2e]'", file=sys.stderr)
            print("  pip install 'matrix-nio[e2e]'", file=sys.stderr)
            print("  pip3 install 'matrix-nio[e2e]'", file=sys.stderr)
        else:
            print(f"Error: Missing dependency: {e}", file=sys.stderr)

        print("", file=sys.stderr)
        print("Or run the health check to diagnose and fix:", file=sys.stderr)
        print(
            f"  python3 {script_dir}/matrix-doctor.py --install", file=sys.stderr
        )
        sys.exit(1)
