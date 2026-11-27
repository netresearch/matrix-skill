#!/usr/bin/env -S uv run --script
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Run any matrix-e2ee-cli command, arguments passed through unchanged.

For the commands no other script wraps: `logout`, `migrate-nio`,
`verify --hand-over` / `--confirm` / `--cancel`, `status`, `react`, `redact`.
The binary is found as for every E2EE script (see _lib/cli.py).

Usage:
    matrix-e2ee-cli.py COMMAND [ARGS...]
    matrix-e2ee-cli.py --help
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.wrapper import exit_with

if __name__ == "__main__":
    exit_with(sys.argv[1:] or ["--help"])
