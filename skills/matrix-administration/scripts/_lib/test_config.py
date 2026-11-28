# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Tests for the admin `_lib.config`: where the admin token comes from.

The skill directory contains a hyphen (`matrix-administration`) so it is not
importable as a package; run the file directly or use unittest discovery:

    python3 skills/matrix-administration/scripts/_lib/test_config.py
    python3 -m unittest discover \\
        -s skills/matrix-administration/scripts/_lib -p 'test_config.py'

Stdlib only. Every case runs against a config directory of its own
(XDG_CONFIG_HOME) with the MATRIX_* variables removed from the environment and the
matrix-e2ee-cli session looked up under a data directory of its own
(XDG_DATA_HOME).
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
        env["XDG_DATA_HOME"] = str(self.home / "data")
        env["HOME"] = str(self.home)
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

    def write_session(self, **fields) -> None:
        session = self.home / "data" / "matrix-e2ee-cli" / "session.json"
        session.parent.mkdir(parents=True, exist_ok=True)
        session.write_text(json.dumps(fields))

    def test_the_cli_session_token_is_the_fallback(self):
        self.write_config(BASE)
        self.write_session(
            homeserver=BASE["homeserver"], user_id="@a:e", access_token="syt_device"
        )
        loaded, err = self.load()
        self.assertIsNotNone(loaded, err)
        self.assertEqual(loaded["admin_token"], "syt_device")

    def test_the_session_follows_xdg_data_home(self):
        os.environ["XDG_DATA_HOME"] = str(self.home / "elsewhere")
        session = self.home / "elsewhere" / "matrix-e2ee-cli" / "session.json"
        session.parent.mkdir(parents=True)
        session.write_text(
            json.dumps({"access_token": "syt_xdg", "homeserver": BASE["homeserver"]})
        )
        self.write_config(BASE)
        loaded, err = self.load()
        self.assertIsNotNone(loaded, err)
        self.assertEqual(loaded["admin_token"], "syt_xdg")

    def test_the_session_token_goes_to_the_sessions_homeserver(self):
        self.write_config({"homeserver": "https://other.example.org"})
        self.write_session(homeserver=BASE["homeserver"], access_token="syt_device")
        loaded, err = self.load()
        self.assertIsNotNone(loaded, err)
        self.assertEqual(loaded["homeserver"], BASE["homeserver"])

    def test_a_session_without_homeserver_is_absent(self):
        # Its token must never be paired with config.json's homeserver.
        for homeserver in (None, ""):
            with self.subTest(homeserver=homeserver):
                fields = {"access_token": "syt_device"}
                if homeserver is not None:
                    fields["homeserver"] = homeserver
                self.write_config(BASE)
                self.write_session(**fields)
                loaded, err = self.load()
                self.assertIsNone(loaded, "the session token was used")
                self.assertIn("MATRIX_ADMIN_TOKEN", err)

    def test_a_set_admin_token_wins_over_the_session(self):
        for source in ("inline", "file", "env"):
            with self.subTest(source=source):
                os.environ.pop("MATRIX_ADMIN_TOKEN", None)
                config = dict(BASE)
                if source == "inline":
                    config["admin_token"] = "syt_admin"
                elif source == "file":
                    (self.config_dir / "admin.token").write_text("syt_admin")
                    config["admin_token_file"] = "admin.token"
                else:
                    os.environ["MATRIX_ADMIN_TOKEN"] = "syt_admin"
                self.write_config(config)
                self.write_session(
                    homeserver="https://other.example.org", access_token="syt_device"
                )
                loaded, err = self.load()
                self.assertIsNotNone(loaded, err)
                self.assertEqual(loaded["admin_token"], "syt_admin")
                self.assertEqual(loaded["homeserver"], BASE["homeserver"])

    def test_a_broken_admin_token_file_stops_even_with_a_session(self):
        self.write_config({**BASE, "admin_token_file": "missing.token"})
        self.write_session(homeserver=BASE["homeserver"], access_token="syt_device")
        loaded, err = self.load()
        self.assertIsNone(loaded)
        self.assertIn("missing.token", err)

    def test_access_token_sources_are_no_longer_read(self):
        (self.config_dir / "access.token").write_text("syt_access_file")
        for data, env in (
            ({**BASE, "access_token": "syt_access"}, {}),
            ({**BASE, "access_token_file": "access.token"}, {}),
            (BASE, {"MATRIX_ACCESS_TOKEN": "syt_access_env"}),
        ):
            with self.subTest(data=data, env=env), mock.patch.dict(os.environ, env):
                self.write_config(data)
                loaded, err = self.load()
                self.assertIsNone(loaded, "an access_token source was used")
                self.assertIn("matrix-e2ee-cli session", err)

    def test_missing_admin_token_names_every_source(self):
        self.write_config({**BASE, "access_token": "syt_access"})
        loaded, err = self.load()
        self.assertIsNone(loaded)
        for source in (
            "MATRIX_ADMIN_TOKEN",
            "admin_token_file",
            "'admin_token'",
            str(self.home / "data" / "matrix-e2ee-cli" / "session.json"),
        ):
            self.assertIn(source, err)
        self.assertIn("access_token in config.json is no longer read", err)

    def test_broken_token_file_does_not_stop_a_command_without_admin(self):
        self.write_config({**BASE, "admin_token_file": "missing.token"})
        loaded, err = self.load(require_admin=False)
        self.assertIsNotNone(loaded, err)


if __name__ == "__main__":
    unittest.main(verbosity=2)
