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

import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from typing import ClassVar

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
if os.environ.get("FAKE_CLI_STDERR"):
    sys.stderr.write(os.environ["FAKE_CLI_STDERR"])
else:
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
            ["download", "--output=d", "--filename=f", "--", "ops", "$e"],
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
            ["watch", "--cursor=me", "--no-summary", "--once", "--", "!r:e"],
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
                "--reason=abgeschlossen",
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


class FlagValueTests(WrapperTestCase):
    def test_a_filename_starting_with_a_dash_stays_a_value(self):
        self.assertTranslates(
            "matrix-download-e2ee.py",
            ["ops", "$e", "--filename=--draft.pdf"],
            ["download", "--filename=--draft.pdf", "--", "ops", "$e"],
        )

    def test_status_wins_over_import_keys(self):
        # Read-only first: the old script printed the status in that case.
        self.assertTranslates(
            "matrix-key-backup.py", ["--status", "--import-keys"], ["status"]
        )

    def test_logout_names_the_resolved_store_and_says_to_keep_it(self):
        result = self.run_script("matrix-e2ee-setup.py", "--logout")
        self.assertEqual(result.returncode, 2)
        store = str(self.root / "data" / "matrix-skill" / "store")
        self.assertIn(store, result.stderr)
        self.assertIn("Keep that store until the takeover has succeeded", result.stderr)
        self.assertNotIn("~/.local/share", result.stderr)


class JsonErrorTests(WrapperTestCase):
    def test_a_failure_prints_the_old_error_object_on_stdout(self):
        for script, args in (
            ("matrix-send-e2ee.py", ["ops", "hi", "--json"]),
            ("matrix-edit-e2ee.py", ["!r:e", "$e", "new", "--json"]),
            ("matrix-redact.py", ["!r:e", "$e", "--json"]),
        ):
            with self.subTest(script=script):
                result = self.run_script(
                    script, *args, FAKE_CLI_RC="1", FAKE_CLI_STDERR="error: no room\n"
                )
                self.assertEqual(result.returncode, 1)
                self.assertTrue(result.stdout.strip(), "no JSON on stdout")
                self.assertEqual(json.loads(result.stdout), {"error": "no room"})
                self.assertIn("error: no room", result.stderr)

    def test_react_reports_the_keys_it_applied_before_the_error(self):
        result = self.run_script(
            "matrix-react.py",
            "!r:e",
            "$e",
            "✅",
            "🤖",
            "--json",
            FAKE_CLI_RC="1",
            FAKE_CLI_STDERR="Applied before the error: ✅\nerror: rate limited\n",
        )
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stdout.strip(), "no JSON on stdout")
        self.assertEqual(
            json.loads(result.stdout), {"error": "rate limited", "applied": ["✅"]}
        )

    def test_without_json_a_failure_prints_nothing_on_stdout(self):
        result = self.run_script(
            "matrix-send-e2ee.py",
            "ops",
            "hi",
            FAKE_CLI_RC="1",
            FAKE_CLI_STDERR="error: no room\n",
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")

    def test_success_output_is_not_wrapped(self):
        result = self.run_script("matrix-send-e2ee.py", "ops", "hi", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "Event ID: $fake:example.org\n")


class WatchInterruptTests(WrapperTestCase):
    def test_ctrl_c_ends_a_following_watch_with_success(self):
        result = self.run_script("matrix-watch.py", "!r:e", FAKE_CLI_RC="130")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_once_keeps_the_interrupted_exit_code(self):
        result = self.run_script("matrix-watch.py", "!r:e", "--once", FAKE_CLI_RC="130")
        self.assertEqual(result.returncode, 130)


class NoTakeoverTests(WrapperTestCase):
    def setUp(self):
        super().setUp()
        self.store = self.root / "data" / "matrix-skill" / "store"
        self.store.mkdir(parents=True)
        (self.store / "credentials.json").write_text(
            json.dumps({"user_id": "@u:e", "device_id": "DEV", "access_token": "syt_x"})
        )

    def first_commands(self, script, *args):
        self.run_script(script, *args)
        commands = [c["argv"][0] for c in self.calls()]
        self.log.unlink(missing_ok=True)
        return commands

    def test_watch_reads_the_log_and_takes_nothing_over(self):
        self.assertEqual(
            self.first_commands("matrix-watch.py", "!r:e", "--once"), ["watch"]
        )

    def test_daemon_status_and_stop_take_nothing_over(self):
        for flag in ("--status", "--stop"):
            with self.subTest(flag=flag):
                self.assertEqual(
                    self.first_commands("matrix-watchd.py", flag), ["watch-daemon"]
                )

    def test_daemon_start_takes_over_first(self):
        self.assertEqual(
            self.first_commands("matrix-watchd.py", "--start"),
            ["migrate-nio", "watch-daemon"],
        )

    def test_an_explicit_migrate_nio_is_backed_up_and_recorded(self):
        session = self.root / "data" / "matrix-e2ee-cli" / "session.json"
        result = self.run_script(
            "matrix-e2ee-cli.py",
            "migrate-nio",
            "--yes",
            FAKE_MIGRATE_SESSION=str(session),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([c["argv"] for c in self.calls()], [["migrate-nio", "--yes"]])
        backups = sorted(self.store.parent.glob("store.backup-*"))
        self.assertEqual(len(backups), 1)
        self.assertTrue((backups[0] / "credentials.json").is_file())
        self.assertTrue(
            (self.root / "data" / "matrix-skill" / "nio-migrated.json").exists()
        )

    def test_migrate_nio_help_copies_nothing(self):
        result = self.run_script("matrix-e2ee-cli.py", "migrate-nio", "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([c["argv"] for c in self.calls()], [["migrate-nio", "--help"]])
        self.assertEqual(list(self.store.parent.glob("store.backup-*")), [])


class StubHomeserver(http.server.BaseHTTPRequestHandler):
    """Joined rooms: !a:e (alias #ops:e, name Operations), !b:e (named ops),
    !c:e and !d:e (dev chat, dev talk)."""

    STATE: ClassVar[dict] = {
        "!a:e": {
            "m.room.name": {"name": "Operations"},
            "m.room.canonical_alias": {"alias": "#ops:e"},
        },
        "!b:e": {"m.room.name": {"name": "ops"}},
        "!c:e": {"m.room.name": {"name": "dev chat"}},
        "!d:e": {"m.room.name": {"name": "dev talk"}},
    }

    def do_GET(self):
        from urllib.parse import unquote

        path = unquote(self.path.split("?", 1)[0])
        body, status = {"errcode": "M_NOT_FOUND", "error": "not found"}, 404
        if self.headers.get("Authorization") != "Bearer syt_device":
            body, status = {"errcode": "M_UNKNOWN_TOKEN", "error": "token"}, 401
        elif path.endswith("/joined_rooms"):
            body, status = {"joined_rooms": list(self.STATE)}, 200
        elif "/rooms/" in path and "/state/" in path:
            room = path.split("/rooms/", 1)[1].split("/state/", 1)[0]
            event = path.split("/state/", 1)[1]
            if event in self.STATE.get(room, {}):
                body, status = self.STATE[room][event], 200
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


class RoomLookupTests(WrapperTestCase):
    def setUp(self):
        super().setUp()
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), StubHomeserver)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        session = self.root / "data" / "matrix-e2ee-cli" / "session.json"
        session.parent.mkdir(parents=True)
        session.write_text(
            json.dumps(
                {
                    "homeserver": f"http://127.0.0.1:{server.server_port}",
                    "user_id": "@u:e",
                    "access_token": "syt_device",
                }
            )
        )

    def test_a_shorthand_reaches_the_room_the_old_scripts_chose(self):
        cases = (
            ("matrix-send-e2ee.py", ["ops", "hi"], ["send", "!a:e", "--", "hi"]),
            ("matrix-send-e2ee.py", ["#ops", "hi"], ["send", "!a:e", "--", "hi"]),
            ("matrix-read-e2ee.py", ["ops"], ["read", "--", "!a:e"]),
            (
                "matrix-edit-e2ee.py",
                ["ops", "$e", "x"],
                ["edit", "--", "!a:e", "$e", "x"],
            ),
            (
                "matrix-react.py",
                ["#ops", "$e", "✅"],
                ["react", "--", "!a:e", "$e", "✅"],
            ),
            ("matrix-redact.py", ["ops", "$e"], ["redact", "--", "!a:e", "$e"]),
            (
                "matrix-download-e2ee.py",
                ["ops", "$e"],
                ["download", "--", "!a:e", "$e"],
            ),
            ("matrix-fetch-keys.py", ["ops"], ["fetch-keys", "--", "!a:e"]),
        )
        for script, args, expected in cases:
            with self.subTest(script=script, room=args[0]):
                self.log.unlink(missing_ok=True)
                self.assertTranslates(script, args, expected)

    def test_ids_and_full_aliases_reach_the_cli_unchanged(self):
        self.assertTranslates(
            "matrix-read-e2ee.py", ["#ops:e"], ["read", "--", "#ops:e"]
        )
        self.log.unlink()
        self.assertTranslates("matrix-read-e2ee.py", ["!b:e"], ["read", "--", "!b:e"])

    def test_an_ambiguous_shorthand_is_refused_before_the_cli_runs(self):
        result = self.run_script("matrix-send-e2ee.py", "dev", "hi", "--json")
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stdout.strip(), "no JSON on stdout")
        self.assertIn("several rooms", json.loads(result.stdout)["error"])
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
