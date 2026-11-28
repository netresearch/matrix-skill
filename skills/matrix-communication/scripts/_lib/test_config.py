# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Tests for `_lib.config`: where the admin token comes from, and that the
config's access_token is no longer read.

The skill directory contains a hyphen (`matrix-communication`) so it is not
importable as a package; run the file directly or use unittest discovery:

    python3 skills/matrix-communication/scripts/_lib/test_config.py
    python3 -m unittest discover \\
        -s skills/matrix-communication/scripts/_lib -p 'test_config.py'

Stdlib only. `config` is imported directly rather than as `_lib.config`, for
the reason given in test_http.py: running this file puts its own directory on
sys.path, where `_lib/http.py` shadows the stdlib `http` package.

Every case runs against a config directory of its own (XDG_CONFIG_HOME) with
the MATRIX_* variables removed from the environment, so a token in the
developer's own environment cannot decide the outcome.
"""

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


class ResolveTokensTests(TokenSourceTestCase):
    def test_inline_token_is_used_when_nothing_else_is_set(self):
        resolved = config.resolve_tokens({**BASE, "admin_token": "syt_inline"})
        self.assertEqual(resolved["admin_token"], "syt_inline")

    def test_token_file_replaces_the_inline_token(self):
        path = self.write_token("token", "syt_from_file\n")
        resolved = config.resolve_tokens(
            {**BASE, "admin_token": "syt_inline", "admin_token_file": str(path)}
        )
        self.assertEqual(resolved["admin_token"], "syt_from_file")

    def test_relative_token_file_is_found_next_to_config_json(self):
        self.write_token("admin.token", "syt_relative")
        resolved = config.resolve_tokens({**BASE, "admin_token_file": "admin.token"})
        self.assertEqual(resolved["admin_token"], "syt_relative")

    def test_environment_wins_over_file_and_inline(self):
        path = self.write_token("token", "syt_from_file")
        os.environ["MATRIX_ADMIN_TOKEN"] = "syt_from_env"
        resolved = config.resolve_tokens(
            {**BASE, "admin_token": "syt_inline", "admin_token_file": str(path)}
        )
        self.assertEqual(resolved["admin_token"], "syt_from_env")

    def test_empty_environment_variable_is_ignored(self):
        os.environ["MATRIX_ADMIN_TOKEN"] = "  "
        resolved = config.resolve_tokens({**BASE, "admin_token": "syt_inline"})
        self.assertEqual(resolved["admin_token"], "syt_inline")

    def test_access_token_sources_are_not_read(self):
        """No script sends the config's access_token any more (one login: the
        matrix-e2ee-cli session), so neither its variable nor its file is read."""
        os.environ["MATRIX_ACCESS_TOKEN"] = "syt_user_env"
        original = {**BASE, "access_token": "syt_inline", "access_token_file": "gone"}
        resolved = config.resolve_tokens(original)
        self.assertEqual(resolved, original)

    def test_input_config_is_not_modified(self):
        original = {**BASE, "admin_token": "syt_inline"}
        os.environ["MATRIX_ADMIN_TOKEN"] = "syt_from_env"
        config.resolve_tokens(original)
        self.assertEqual(original["admin_token"], "syt_inline")

    def test_missing_file_names_the_path_not_a_token(self):
        with self.assertRaises(config.TokenSourceError) as ctx:
            config.resolve_tokens({**BASE, "admin_token_file": "absent.token"})
        self.assertIn("absent.token", str(ctx.exception))

    def test_empty_file_is_an_error(self):
        path = self.write_token("token", "\n")
        with self.assertRaises(config.TokenSourceError) as ctx:
            config.resolve_tokens({**BASE, "admin_token_file": str(path)})
        self.assertIn("is empty", str(ctx.exception))

    def test_only_the_named_keys_are_resolved(self):
        resolved = config.resolve_tokens(
            {**BASE, "admin_token_file": "absent.token"}, keys=()
        )
        self.assertEqual(resolved["admin_token_file"], "absent.token")
        self.assertNotIn("admin_token", resolved)

    def test_there_is_no_access_token_loader_left(self):
        # load_config() gave the HTTP scripts their access_token; they are gone.
        self.assertFalse(hasattr(config, "load_config"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
