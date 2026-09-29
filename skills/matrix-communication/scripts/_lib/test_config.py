# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Tests for `_lib.config`: where the access and admin tokens come from.

The skill directory contains a hyphen (`matrix-communication`) so it is not
importable as a package; run the file directly or use unittest discovery:

    python3 skills/matrix-communication/scripts/_lib/test_config.py
    python3 -m unittest discover \\
        -s skills/matrix-communication/scripts/_lib -p 'test_config.py'

Stdlib only. `config` is imported directly rather than as `_lib.config`, for
the reason given in test_e2ee.py: running this file puts its own directory on
sys.path, where `_lib/http.py` shadows the stdlib `http` package.

Every case runs against a config directory of its own (XDG_CONFIG_HOME) with
MATRIX_ACCESS_TOKEN and MATRIX_ADMIN_TOKEN removed from the environment, so a
token in the developer's own environment cannot decide the outcome.
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

BASE = {"homeserver": "https://matrix.example.org", "user_id": "@bot:example.org"}


class TokenSourceTestCase(unittest.TestCase):
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

    def write_token(self, name: str, token: str) -> Path:
        path = self.config_dir / name
        path.write_text(token)
        return path

    def load(self, **kwargs) -> tuple[dict | None, str]:
        """Run load_config; return (config or None on exit, captured stderr)."""
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            try:
                return config.load_config(**kwargs), err.getvalue()
            except SystemExit:
                return None, err.getvalue()


class ResolveTokensTests(TokenSourceTestCase):
    def test_inline_token_is_used_when_nothing_else_is_set(self):
        resolved = config.resolve_tokens({**BASE, "access_token": "syt_inline"})
        self.assertEqual(resolved["access_token"], "syt_inline")

    def test_token_file_replaces_the_inline_token(self):
        path = self.write_token("token", "syt_from_file\n")
        resolved = config.resolve_tokens(
            {**BASE, "access_token": "syt_inline", "access_token_file": str(path)}
        )
        self.assertEqual(resolved["access_token"], "syt_from_file")

    def test_relative_token_file_is_found_next_to_config_json(self):
        self.write_token("access.token", "syt_relative")
        resolved = config.resolve_tokens({**BASE, "access_token_file": "access.token"})
        self.assertEqual(resolved["access_token"], "syt_relative")

    def test_environment_wins_over_file_and_inline(self):
        path = self.write_token("token", "syt_from_file")
        os.environ["MATRIX_ACCESS_TOKEN"] = "syt_from_env"
        resolved = config.resolve_tokens(
            {**BASE, "access_token": "syt_inline", "access_token_file": str(path)}
        )
        self.assertEqual(resolved["access_token"], "syt_from_env")

    def test_empty_environment_variable_is_ignored(self):
        os.environ["MATRIX_ACCESS_TOKEN"] = "  "
        resolved = config.resolve_tokens({**BASE, "access_token": "syt_inline"})
        self.assertEqual(resolved["access_token"], "syt_inline")

    def test_admin_token_has_its_own_sources(self):
        path = self.write_token("admin", "syt_admin_file")
        os.environ["MATRIX_ACCESS_TOKEN"] = "syt_user_env"
        resolved = config.resolve_tokens({**BASE, "admin_token_file": str(path)})
        self.assertEqual(resolved["admin_token"], "syt_admin_file")
        self.assertEqual(resolved["access_token"], "syt_user_env")

    def test_input_config_is_not_modified(self):
        original = {**BASE, "access_token": "syt_inline"}
        os.environ["MATRIX_ACCESS_TOKEN"] = "syt_from_env"
        config.resolve_tokens(original)
        self.assertEqual(original["access_token"], "syt_inline")

    def test_missing_file_names_the_path_not_a_token(self):
        with self.assertRaises(config.TokenSourceError) as ctx:
            config.resolve_tokens({**BASE, "access_token_file": "absent.token"})
        self.assertIn("absent.token", str(ctx.exception))

    def test_empty_file_is_an_error(self):
        path = self.write_token("token", "\n")
        with self.assertRaises(config.TokenSourceError) as ctx:
            config.resolve_tokens({**BASE, "access_token_file": str(path)})
        self.assertIn("is empty", str(ctx.exception))


class LoadConfigTests(TokenSourceTestCase):
    def test_config_without_token_loads_with_token_file(self):
        self.write_token("token", "syt_from_file")
        self.write_config({**BASE, "access_token_file": "token"})
        loaded, _ = self.load()
        self.assertEqual(loaded["access_token"], "syt_from_file")

    def test_config_without_token_loads_with_environment(self):
        self.write_config(BASE)
        os.environ["MATRIX_ACCESS_TOKEN"] = "syt_from_env"
        loaded, _ = self.load()
        self.assertEqual(loaded["access_token"], "syt_from_env")

    def test_missing_token_names_the_other_sources(self):
        self.write_config(BASE)
        loaded, err = self.load()
        self.assertIsNone(loaded)
        self.assertIn("access_token", err)
        self.assertIn("MATRIX_ACCESS_TOKEN", err)

    def test_unreadable_token_file_exits_without_printing_the_config(self):
        self.write_config(
            {**BASE, "access_token": "syt_secret_inline", "access_token_file": "gone"}
        )
        loaded, err = self.load()
        self.assertIsNone(loaded)
        self.assertIn("access_token_file", err)
        self.assertNotIn("syt_secret_inline", err)


if __name__ == "__main__":
    unittest.main(verbosity=2)
