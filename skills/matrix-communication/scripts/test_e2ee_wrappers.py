# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Tests for the E2EE wrapper scripts: old flags in, matrix-e2ee-cli command out.

Run directly (stdlib only):

    python3 skills/matrix-communication/scripts/test_e2ee_wrappers.py

Each wrapper runs as a subprocess against a fake CLI named by MATRIX_E2EE_CLI,
which records its argv and the secret variables it received. HOME,
XDG_DATA_HOME and XDG_CONFIG_HOME point at a temporary directory, so no real
store is read and nothing is downloaded or contacted.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent

FAKE_CLI = """#!{python}
import json, os, sys
with open(os.environ["FAKE_CLI_LOG"], "a") as log:
    log.write(json.dumps({{
        "argv": sys.argv[1:],
        "env": {{k: os.environ.get(k) for k in (
            "MATRIX_PASSWORD", "MATRIX_RECOVERY_KEY", "MATRIX_RECOVERY_PASSPHRASE")}},
    }}) + "\\n")
if sys.argv[1:2] == ["migrate-nio"] and os.environ.get("FAKE_MIGRATE_SESSION"):
    session = os.environ["FAKE_MIGRATE_SESSION"]
    os.makedirs(os.path.dirname(session), exist_ok=True)
    with open(session, "w") as handle:
        handle.write("{{}}")
print("Event ID: $fake:example.org" if sys.argv[1:2] != ["migrate-nio"] else "Migrated device DEV")
sys.exit(int(os.environ.get("FAKE_CLI_RC", "0")))
"""


class WrapperTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.log = self.root / "calls.jsonl"
        fake = self.root / "fake-cli"
        fake.write_text(FAKE_CLI.format(python=sys.executable))
        fake.chmod(0o755)
        self.env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(self.root / "home"),
            "XDG_DATA_HOME": str(self.root / "data"),
            "XDG_CONFIG_HOME": str(self.root / "config"),
            "XDG_RUNTIME_DIR": str(self.root / "run"),
            "MATRIX_E2EE_CLI": str(fake),
            "FAKE_CLI_LOG": str(self.log),
        }

    def run_script(self, script, *args, **env):
        return subprocess.run(
            [sys.executable, str(HERE / script), *args],
            capture_output=True,
            text=True,
            env={**self.env, **env},
            timeout=60,
            check=False,
        )

    def calls(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def assertTranslates(self, script, args, expected):
        result = self.run_script(script, *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([c["argv"] for c in self.calls()], [expected])
        return result

    def assertRefused(self, script, args, text):
        result = self.run_script(script, *args)
        self.assertEqual(result.returncode, 2)
        self.assertIn(text, result.stderr)
        self.assertEqual(self.calls(), [])


class TranslationTests(WrapperTestCase):
    def test_send_every_flag_and_debug_dropped(self):
        self.assertTranslates(
            "matrix-send-e2ee.py",
            [
                "ops",
                "hi \\!",
                "--notice",
                "--thread",
                "$t",
                "--reply",
                "$r",
                "--mention",
                "@a:e",
                "--mention",
                "@b:e",
                "--mention-room",
                "--no-prefix",
                "--trust-unverified-devices",
                "--json",
                "-q",
                "--debug",
            ],
            [
                "send",
                "--notice",
                "--no-prefix",
                "--mention-room",
                "--trust-unverified-devices",
                "--json",
                "--quiet",
                "--thread",
                "$t",
                "--reply",
                "$r",
                "--mention",
                "@a:e",
                "--mention",
                "@b:e",
                "ops",
                "--",
                "hi !",
            ],
        )

    def test_send_to_a_direct_chat_has_no_room(self):
        self.assertTranslates(
            "matrix-send-e2ee.py",
            ["--to", "@jane:e", "-1 is fine", "--emote"],
            ["send", "--to", "@jane:e", "--emote", "--", "-1 is fine"],
        )

    def test_send_takes_a_matrix_to_link(self):
        self.assertTranslates(
            "matrix-send-e2ee.py",
            ["https://matrix.to/#/%23ops:e?via=e", "x"],
            ["send", "#ops:e", "--", "x"],
        )

    def test_send_needs_exactly_one_target(self):
        self.assertRefused(
            "matrix-send-e2ee.py", ["--to", "@a:e", "room", "x"], "exactly one"
        )

    def test_send_refuses_a_room_that_reads_as_a_flag(self):
        self.assertRefused(
            "matrix-send-e2ee.py",
            ["--", "--trust-unverified-devices", "hi"],
            "starts with '-'",
        )

    def test_read(self):
        self.assertTranslates(
            "matrix-read-e2ee.py",
            ["ops", "--limit", "5", "-k", "--json", "--debug"],
            ["read", "--limit", "5", "--request-keys", "--json", "--", "ops"],
        )

    def test_edit(self):
        self.assertTranslates(
            "matrix-edit-e2ee.py",
            ["!r:e", "$e", "new", "--no-prefix", "--quiet", "--debug"],
            ["edit", "--no-prefix", "--quiet", "--", "!r:e", "$e", "new"],
        )

    def test_download(self):
        self.assertTranslates(
            "matrix-download-e2ee.py",
            ["ops", "$e", "--output", "d", "--filename", "f", "--debug"],
            ["download", "--output", "d", "--filename", "f", "--", "ops", "$e"],
        )

    def test_download_overwrite_is_refused(self):
        self.assertRefused(
            "matrix-download-e2ee.py", ["ops", "$e", "--overwrite"], "--overwrite"
        )

    def test_fetch_keys(self):
        self.assertTranslates(
            "matrix-fetch-keys.py",
            ["ops", "--limit", "50", "--sync-time", "9", "--debug"],
            ["fetch-keys", "--limit", "50", "--sync-time", "9", "--", "ops"],
        )

    def test_verify(self):
        self.assertTranslates(
            "matrix-e2ee-verify.py",
            ["--request", "DEV", "--timeout", "30", "--debug"],
            ["verify", "--request", "DEV", "--timeout", "30"],
        )

    def test_verify_without_a_mode_or_with_accept_from_is_refused(self):
        self.assertRefused("matrix-e2ee-verify.py", [], "exactly one of")
        self.assertRefused(
            "matrix-e2ee-verify.py",
            ["--listen", "--accept-from", "@x:e"],
            "--accept-from",
        )

    def test_setup_logs_in(self):
        self.assertTranslates("matrix-e2ee-setup.py", ["--debug"], ["login"])

    def session_file(self):
        return self.root / "data" / "matrix-e2ee-cli" / "session.json"

    def test_setup_with_a_session_shows_status_instead_of_logging_in(self):
        self.session_file().parent.mkdir(parents=True)
        self.session_file().write_text("{}")
        result = self.assertTranslates("matrix-e2ee-setup.py", [], ["status"])
        self.assertIn("already set up", result.stdout)
        self.assertIn("--force", result.stdout)

    def test_setup_force_replaces_an_existing_session(self):
        self.session_file().parent.mkdir(parents=True)
        self.session_file().write_text("{}")
        self.assertTranslates("matrix-e2ee-setup.py", ["--force"], ["login", "--force"])

    def test_setup_force_with_status_is_refused(self):
        self.assertRefused("matrix-e2ee-setup.py", ["--force", "--status"], "--force")

    def test_setup_status(self):
        self.assertTranslates(
            "matrix-e2ee-setup.py", ["--status", "--json"], ["status", "--json"]
        )

    def test_setup_logout_is_refused_never_mapped_to_a_server_logout(self):
        self.assertRefused(
            "matrix-e2ee-setup.py", ["--logout"], "logs the device out on the server"
        )
        self.assertRefused(
            "matrix-e2ee-setup.py", ["--logout", "--purge-all"], "--purge-all"
        )

    def test_key_backup(self):
        self.assertTranslates(
            "matrix-key-backup.py", ["--import-keys"], ["backup-restore"]
        )
        self.log.unlink()
        self.assertTranslates("matrix-key-backup.py", ["--status"], ["status"])

    def test_key_backup_display_only_is_refused(self):
        self.assertRefused("matrix-key-backup.py", ["--recovery-key"], "--import-keys")

    def test_watchd(self):
        self.assertTranslates(
            "matrix-watchd.py", ["--status"], ["watch-daemon", "--status"]
        )

    def test_watch(self):
        self.assertTranslates(
            "matrix-watch.py",
            ["!r:e", "--cursor", "me", "--no-summary", "--once"],
            ["watch", "--cursor", "me", "--no-summary", "--once", "--", "!r:e"],
        )

    def test_react_status_swap_as_claiming_a_ticket_runs_it(self):
        self.assertTranslates(
            "matrix-react.py",
            ["#it:netresearch.de", "$eventId", "🩹", "--replace", "▶️", "✅"],
            [
                "react",
                "--replace",
                "▶️",
                "✅",
                "--",
                "#it:netresearch.de",
                "$eventId",
                "🩹",
            ],
        )

    def test_react_every_flag_and_debug_dropped(self):
        self.assertTranslates(
            "matrix-react.py",
            [
                "https://matrix.to/#/%23it:e",
                "$e",
                "✅",
                "🤖",
                "--remove",
                "--trust-unverified-devices",
                "--json",
                "-q",
                "--debug",
            ],
            [
                "react",
                "--remove",
                "--trust-unverified-devices",
                "--json",
                "--quiet",
                "--",
                "#it:e",
                "$e",
                "✅",
                "🤖",
            ],
        )

    def test_react_list(self):
        self.assertTranslates(
            "matrix-react.py",
            ["!r:e", "$e", "--list"],
            ["react", "--list", "--", "!r:e", "$e"],
        )

    def test_react_list_with_emoji_or_no_emoji_is_refused(self):
        self.assertRefused(
            "matrix-react.py", ["!r:e", "$e", "✅", "--list"], "--list takes no EMOJI"
        )
        self.assertRefused("matrix-react.py", ["!r:e", "$e"], "EMOJI is required")

    def test_react_output_reaches_ticket_flows_parser(self):
        result = self.run_script(
            "matrix-react.py", "!r:e", "$e", "✅", "--trust-unverified-devices"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout + result.stderr, r"Event ID: (\$\S+)")

    def test_redact(self):
        self.assertTranslates(
            "matrix-redact.py",
            ["!r:e", "$e", "--reason", "abgeschlossen", "--json", "-q", "--debug"],
            [
                "redact",
                "--reason",
                "abgeschlossen",
                "--json",
                "--quiet",
                "--",
                "!r:e",
                "$e",
            ],
        )

    def test_redact_without_reason(self):
        self.assertTranslates(
            "matrix-redact.py", ["#r:e", "$e"], ["redact", "--", "#r:e", "$e"]
        )

    def test_passthrough(self):
        self.assertTranslates(
            "matrix-e2ee-cli.py",
            ["verify", "--hand-over", "--listen"],
            ["verify", "--hand-over", "--listen"],
        )


class OutputAndSecretTests(WrapperTestCase):
    def test_stdout_and_exit_code_pass_through(self):
        result = self.run_script("matrix-send-e2ee.py", "ops", "hi", FAKE_CLI_RC="3")
        self.assertEqual(result.returncode, 3)
        self.assertEqual(result.stdout, "Event ID: $fake:example.org\n")

    def test_a_password_argument_goes_into_the_environment_not_argv(self):
        result = self.run_script(
            "matrix-e2ee-setup.py", "--allow-secret-argument", "s3cret"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        (call,) = self.calls()
        self.assertEqual(call["argv"], ["login"])
        self.assertEqual(call["env"]["MATRIX_PASSWORD"], "s3cret")
        self.assertNotIn("s3cret", result.stdout + result.stderr)

    def test_a_password_argument_without_the_opt_in_is_refused(self):
        self.assertRefused(
            "matrix-e2ee-setup.py", ["s3cret"], "--allow-secret-argument"
        )

    def test_a_recovery_key_and_passphrase_argument_go_into_the_environment(self):
        self.run_script(
            "matrix-key-backup.py",
            "--recovery-key",
            "EsT k3y",
            "--allow-secret-argument",
            "--import-keys",
        )
        self.run_script(
            "matrix-key-backup.py",
            "--passphrase",
            "pass",
            "--allow-secret-argument",
            "--import-keys",
        )
        first, second = self.calls()
        self.assertEqual(
            (first["argv"], first["env"]["MATRIX_RECOVERY_KEY"]),
            (["backup-restore"], "EsT k3y"),
        )
        self.assertEqual(second["env"]["MATRIX_RECOVERY_PASSPHRASE"], "pass")


class TakeoverTests(WrapperTestCase):
    def setUp(self):
        super().setUp()
        store = self.root / "data" / "matrix-skill" / "store"
        store.mkdir(parents=True)
        (store / "credentials.json").write_text(
            json.dumps({"user_id": "@u:e", "device_id": "DEV", "access_token": "syt_x"})
        )

    def test_the_first_command_takes_the_nio_device_over_first(self):
        result = self.run_script("matrix-read-e2ee.py", "ops", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        argvs = [c["argv"] for c in self.calls()]
        self.assertEqual(argvs[0][:2], ["migrate-nio", "--yes"])
        self.assertEqual(argvs[1], ["read", "--json", "--", "ops"])
        # migrate-nio's report goes to stderr; stdout carries the command alone.
        self.assertEqual(result.stdout, "Event ID: $fake:example.org\n")
        self.assertIn("Migrated device DEV", result.stderr)

        self.log.unlink()
        self.run_script("matrix-read-e2ee.py", "ops")
        self.assertEqual([c["argv"][0] for c in self.calls()], ["read"])

    def test_setup_right_after_the_takeover_keeps_the_migrated_device(self):
        session = self.root / "data" / "matrix-e2ee-cli" / "session.json"
        result = self.run_script(
            "matrix-e2ee-setup.py", FAKE_MIGRATE_SESSION=str(session)
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        argvs = [c["argv"] for c in self.calls()]
        self.assertEqual(argvs[0][0], "migrate-nio")
        self.assertEqual(argvs[1:], [["status"]])
        self.assertIn("already set up", result.stdout)

    def test_a_failed_takeover_runs_no_command(self):
        result = self.run_script("matrix-e2ee-setup.py", FAKE_CLI_RC="1")
        self.assertEqual(result.returncode, 1)
        self.assertEqual([c["argv"][0] for c in self.calls()], ["migrate-nio"])

    def test_a_message_or_room_named_like_a_command_still_takes_over(self):
        self.run_script("matrix-send-e2ee.py", "logout", "help")
        argvs = [c["argv"] for c in self.calls()]
        self.assertEqual(argvs[0][0], "migrate-nio")
        self.assertEqual(argvs[1], ["send", "logout", "--", "help"])

    def test_logout_and_help_never_trigger_a_takeover(self):
        self.run_script("matrix-e2ee-cli.py", "logout")
        self.run_script("matrix-e2ee-cli.py", "send", "--help")
        self.assertEqual([c["argv"][0] for c in self.calls()], ["logout", "send"])


if __name__ == "__main__":
    unittest.main()
