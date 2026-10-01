# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Tests for the admin `_lib.config`: where the admin token comes from.

The skill directory contains a hyphen (`matrix-administration`) so it is not
importable as a package; run the file directly or use unittest discovery:

    python3 skills/matrix-administration/scripts/_lib/test_config.py
    python3 -m unittest discover \\
        -s skills/matrix-administration/scripts/_lib -p 'test_config.py'

Stdlib only. Every case runs against a config directory of its own
(XDG_CONFIG_HOME) with the MATRIX_* variables removed from the environment.
"""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config

BASE = {"homeserver": "https://matrix.example.org"}


class AdminTokenSourceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        self.config_dir = self.home / "matrix"
        self.config_dir.mkdir()

        env = {k: v for k, v in os.environ.items() if not k.startswith("MATRIX_")}
        env["XDG_CONFIG_HOME"] = str(self.home)
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_config(self, data: dict) -> None:
        (self.config_dir / "config.json").write_text(json.dumps(data))

    def load(self, **kwargs) -> tuple[dict | None, str]:
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            try:
                return config.load_config(**kwargs), err.getvalue()
            except SystemExit:
                return None, err.getvalue()

    def test_inline_admin_token_still_works(self):
        self.write_config({**BASE, "admin_token": "syt_inline"})
        loaded, _ = self.load()
        self.assertEqual(loaded["admin_token"], "syt_inline")

    def test_admin_token_file_is_read(self):
        (self.config_dir / "admin.token").write_text("syt_admin_file\n")
        self.write_config({**BASE, "admin_token_file": "admin.token"})
        loaded, _ = self.load()
        self.assertEqual(loaded["admin_token"], "syt_admin_file")

    def test_environment_wins_over_file(self):
        (self.config_dir / "admin.token").write_text("syt_admin_file")
        self.write_config({**BASE, "admin_token_file": "admin.token"})
        os.environ["MATRIX_ADMIN_TOKEN"] = "syt_admin_env"
        loaded, _ = self.load()
        self.assertEqual(loaded["admin_token"], "syt_admin_env")

    def test_missing_admin_token_names_the_other_sources(self):
        self.write_config(BASE)
        loaded, err = self.load()
        self.assertIsNone(loaded)
        self.assertIn("MATRIX_ADMIN_TOKEN", err)
        self.assertIn("admin_token_file", err)

    def test_empty_token_file_exits(self):
        (self.config_dir / "admin.token").write_text("")
        self.write_config({**BASE, "admin_token_file": "admin.token"})
        loaded, err = self.load()
        self.assertIsNone(loaded)
        self.assertIn("is empty", err)

    def test_token_file_not_required_when_admin_is_not(self):
        self.write_config(BASE)
        loaded, _ = self.load(require_admin=False)
        self.assertEqual(loaded["homeserver"], BASE["homeserver"])

    def test_unused_access_token_file_does_not_stop_a_working_admin_token(self):
        """admin_token wins, so a broken access_token_file is never read."""
        self.write_config({**BASE, "access_token_file": "missing.token"})
        os.environ["MATRIX_ADMIN_TOKEN"] = "syt_admin_env"
        loaded, err = self.load()
        self.assertIsNotNone(loaded, err)
        self.assertEqual(loaded["admin_token"], "syt_admin_env")

    def test_access_token_file_is_the_fallback_without_an_admin_token(self):
        (self.config_dir / "access.token").write_text("syt_access_file")
        self.write_config({**BASE, "access_token_file": "access.token"})
        loaded, _ = self.load()
        self.assertEqual(loaded["access_token"], "syt_access_file")

    def test_broken_token_file_does_not_stop_a_command_without_admin(self):
        self.write_config({**BASE, "admin_token_file": "missing.token"})
        loaded, err = self.load(require_admin=False)
        self.assertIsNotNone(loaded, err)


if __name__ == "__main__":
    unittest.main(verbosity=2)
