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
if sys.argv[1:2] == ["rooms"] and "FAKE_ROOMS" in os.environ:
    sys.stderr.write(os.environ.get("FAKE_ROOMS_STDERR", ""))
    print(os.environ["FAKE_ROOMS"])
    sys.exit(int(os.environ.get("FAKE_ROOMS_RC", "0")))
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
                "!o:e",
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
                "!o:e",
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

    def test_read(self):
        self.assertTranslates(
            "matrix-read-e2ee.py",
            ["!o:e", "--limit", "5", "-k", "--json", "--debug"],
            ["read", "--limit", "5", "--request-keys", "--json", "--", "!o:e"],
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
            ["!o:e", "$e", "--output", "d", "--filename", "f", "--debug"],
            ["download", "--output=d", "--filename=f", "--", "!o:e", "$e"],
        )

    def test_download_overwrite_is_refused(self):
        self.assertRefused(
            "matrix-download-e2ee.py", ["!o:e", "$e", "--overwrite"], "--overwrite"
        )

    def test_fetch_keys(self):
        self.assertTranslates(
            "matrix-fetch-keys.py",
            ["!o:e", "--limit", "50", "--sync-time", "9", "--debug"],
            ["fetch-keys", "--limit", "50", "--sync-time", "9", "--", "!o:e"],
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

    def test_rooms(self):
        self.assertTranslates(
            "matrix-rooms.py",
            ["--json", "--search=-ops", "--debug"],
            ["rooms", "--json", "--search=-ops"],
        )

    def test_rooms_lookup(self):
        self.assertTranslates(
            "matrix-rooms.py", ["-l", "agent-work"], ["rooms", "--lookup=agent-work"]
        )

    def test_resolve(self):
        self.assertTranslates(
            "matrix-resolve.py",
            ["#ops:e", "--json", "--debug"],
            ["resolve", "--json", "--", "#ops:e"],
        )

    def test_create_room_every_flag_and_debug_dropped(self):
        self.assertTranslates(
            "matrix-create-room.py",
            [
                "--alias",
                "lsb",
                "--topic=-t",
                "--invite",
                "@a:e",
                "--invite",
                "@b:e",
                "--preset",
                "public_chat",
                "--json",
                "-q",
                "--debug",
                "--",
                "-Project",
            ],
            [
                "create-room",
                "--alias=lsb",
                "--topic=-t",
                "--invite=@a:e",
                "--invite=@b:e",
                "--preset=public_chat",
                "--json",
                "--quiet",
                "--",
                "-Project",
            ],
        )

    def test_create_room_defaults_to_a_private_chat(self):
        self.assertTranslates(
            "matrix-create-room.py",
            ["LSB"],
            ["create-room", "--preset=private_chat", "--", "LSB"],
        )

    def test_invite(self):
        self.assertTranslates(
            "matrix-invite.py",
            ["!r:e", "@a:e", "--json", "-q", "--debug"],
            ["invite", "--json", "--quiet", "--", "!r:e", "@a:e"],
        )

    def test_power_level_show_get_set(self):
        for args, expected in (
            (["!r:e", "--show", "-q"], ["power-level", "--show", "--quiet"]),
            (
                ["!r:e", "--get", "@a:e", "--json"],
                ["power-level", "--get=@a:e", "--json"],
            ),
            (
                ["!r:e", "--set", "@a:e", "-10", "--debug"],
                ["power-level", "--set", "@a:e", "-10"],
            ),
        ):
            with self.subTest(args=args):
                self.log.unlink(missing_ok=True)
                self.assertTranslates(
                    "matrix-power-level.py", args, [*expected, "--", "!r:e"]
                )

    def test_power_level_needs_exactly_one_action(self):
        for args in (["!r:e"], ["!r:e", "--show", "--get", "@a:e"]):
            with self.subTest(args=args):
                result = self.run_script("matrix-power-level.py", *args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(self.calls(), [])

    def test_room_commands_take_a_matrix_to_link(self):
        link = "https://matrix.to/#/%21r%3Ae?via=e"
        self.assertTranslates(
            "matrix-invite.py", [link, "@a:e"], ["invite", "--", "!r:e", "@a:e"]
        )

    def test_plain_send_every_flag_and_debug_dropped(self):
        self.assertTranslates(
            "matrix-send.py",
            [
                "!o:e",
                "hi \\!",
                "--emote",
                "--thread",
                "$t",
                "--reply",
                "$r",
                "--no-prefix",
                "--format",
                "markdown",
                "--json",
                "-q",
                "--debug",
            ],
            [
                "send",
                "--emote",
                "--no-prefix",
                "--json",
                "--quiet",
                "--thread",
                "$t",
                "--reply",
                "$r",
                "!o:e",
                "--",
                "hi !",
            ],
        )

    def test_plain_send_notice(self):
        self.assertTranslates(
            "matrix-send.py",
            ["!r:e", "x", "--notice"],
            ["send", "--notice", "!r:e", "--", "x"],
        )

    def test_plain_send_format_text_is_refused_not_sent_as_markdown(self):
        self.assertRefused(
            "matrix-send.py", ["!r:e", "*x*", "--format", "text"], "--format text"
        )

    def test_plain_read(self):
        self.assertTranslates(
            "matrix-read.py",
            ["!o:e", "-l", "5", "--json"],
            ["read", "--limit", "5", "--json", "--", "!o:e"],
        )

    def test_plain_read_default_limit_is_the_clis(self):
        self.assertTranslates("matrix-read.py", ["!r:e"], ["read", "--", "!r:e"])

    def test_plain_edit(self):
        self.assertTranslates(
            "matrix-edit.py",
            ["!r:e", "$e", "new \\!", "--no-prefix", "--json", "-q", "--debug"],
            ["edit", "--no-prefix", "--json", "--quiet", "--", "!r:e", "$e", "new !"],
        )

    def test_send_plaintext(self):
        for script in ("matrix-send-e2ee.py", "matrix-send.py"):
            with self.subTest(script=script):
                self.log.unlink(missing_ok=True)
                self.assertTranslates(
                    script,
                    ["!o:e", "!hookshot webhook x", "--no-prefix", "--plaintext"],
                    [
                        "send",
                        "--no-prefix",
                        "--plaintext",
                        "!o:e",
                        "--",
                        "!hookshot webhook x",
                    ],
                )

    def test_send_plaintext_with_trust_unverified_devices_is_refused(self):
        # The CLI refuses the pair (exit 2); the wrapper refuses it first, as
        # it does --emote with --notice.
        result = self.run_script(
            "matrix-send-e2ee.py",
            "!o:e",
            "hi",
            "--plaintext",
            "--trust-unverified-devices",
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("not allowed with argument", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_send_to_with_an_operand_after_the_separator(self):
        self.assertTranslates(
            "matrix-send-e2ee.py",
            ["--to", "@alice:e", "--", "-hello"],
            ["send", "--to", "@alice:e", "--", "-hello"],
        )

    def test_an_option_cannot_take_an_operand_after_the_separator(self):
        # --to has no value before "--"; "@alice:e" after it is an operand.
        result = self.run_script(
            "matrix-send-e2ee.py", "--to", "--", "@alice:e", "hello"
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("--to", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_passthrough(self):
        self.assertTranslates(
            "matrix-e2ee-cli.py",
            ["verify", "--hand-over", "--listen"],
            ["verify", "--hand-over", "--listen"],
        )


class OutputAndSecretTests(WrapperTestCase):
    def test_stdout_and_exit_code_pass_through(self):
        result = self.run_script("matrix-send-e2ee.py", "!o:e", "hi", FAKE_CLI_RC="3")
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

    def takeover_env(self, rooms):
        session = self.root / "data" / "matrix-e2ee-cli" / "session.json"
        return {"FAKE_MIGRATE_SESSION": str(session), "FAKE_ROOMS": json.dumps(rooms)}

    def test_the_first_command_takes_the_nio_device_over_first(self):
        # The takeover creates the session; the shorthand is looked up after it.
        env = self.takeover_env([{"room_id": "!a:e", "name": "ops", "alias": None}])
        result = self.run_script("matrix-read-e2ee.py", "ops", "--json", **env)
        self.assertEqual(result.returncode, 0, result.stderr)
        argvs = [c["argv"] for c in self.calls()]
        self.assertEqual(argvs[0][:2], ["migrate-nio", "--yes"])
        self.assertEqual(
            argvs[1:], [["rooms", "--json"], ["read", "--json", "--", "!a:e"]]
        )
        # migrate-nio's report goes to stderr; stdout carries the command alone.
        self.assertEqual(result.stdout, "Event ID: $fake:example.org\n")
        self.assertIn("Migrated device DEV", result.stderr)

        self.log.unlink()
        self.run_script("matrix-read-e2ee.py", "ops", **env)
        self.assertEqual([c["argv"][0] for c in self.calls()], ["rooms", "read"])

    def test_a_room_named_like_a_help_flag_still_takes_over(self):
        # send's ROOM stands before the child's "--"; it is no help request.
        for script in ("matrix-send.py", "matrix-send-e2ee.py"):
            with self.subTest(script=script):
                self.log.unlink(missing_ok=True)
                for name in ("marker", "session"):
                    path = (
                        self.root
                        / "data"
                        / (
                            "matrix-skill/nio-migrated.json"
                            if name == "marker"
                            else "matrix-e2ee-cli/session.json"
                        )
                    )
                    path.unlink(missing_ok=True)
                env = self.takeover_env(
                    [{"room_id": "!h:e", "name": "--help", "alias": None}]
                )
                result = self.run_script(script, "--", "--help", "hi", **env)
                self.assertEqual(result.returncode, 0, result.stderr)
                argvs = [c["argv"] for c in self.calls()]
                self.assertEqual(argvs[0][0], "migrate-nio")
                self.assertEqual(argvs[-1], ["send", "!h:e", "--", "hi"])

    def test_without_the_takeover_a_shorthand_needs_a_session(self):
        # A takeover that creates no session leaves nothing to look up with.
        result = self.run_script("matrix-read-e2ee.py", "ops")
        self.assertEqual(result.returncode, 1)
        self.assertIn("matrix-e2ee-setup.py", result.stderr)
        self.assertEqual([c["argv"][0] for c in self.calls()], ["migrate-nio"])

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

    def test_any_command_settles_a_takeover_that_was_killed(self):
        # migrate-nio wrote the session, then the process was killed before
        # the record was final; logout must not reopen the takeover.
        marker = self.root / "data" / "matrix-skill" / "nio-migrated.json"
        marker.write_text(json.dumps({"store": "s", "backup": None, "running": True}))
        session = self.root / "data" / "matrix-e2ee-cli" / "session.json"
        session.parent.mkdir(parents=True)
        session.write_text("{}")
        self.run_script("matrix-e2ee-cli.py", "logout")
        self.assertNotIn("running", json.loads(marker.read_text()))

    @unittest.skipIf(os.geteuid() == 0, "root opens a file of mode 000")
    def test_a_takeover_that_cannot_open_the_store_lock_is_an_error_not_a_trace(self):
        lock = self.root / "data" / "matrix-skill" / "store" / ".daemon.lock"
        lock.write_text("")
        lock.chmod(0)
        self.addCleanup(lock.chmod, 0o600)
        result = self.run_script("matrix-send-e2ee.py", "!r:e", "hi", "--json")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stderr)
        self.assertTrue(result.stdout.strip(), result.stderr)
        self.assertIn("takeover", json.loads(result.stdout)["error"])
        self.assertEqual(self.calls(), [])

    def test_a_failed_takeover_runs_no_command(self):
        result = self.run_script("matrix-e2ee-setup.py", FAKE_CLI_RC="1")
        self.assertEqual(result.returncode, 1)
        self.assertEqual([c["argv"][0] for c in self.calls()], ["migrate-nio"])

    def test_a_message_or_room_named_like_a_command_still_takes_over(self):
        env = self.takeover_env([{"room_id": "!l:e", "name": "logout", "alias": None}])
        self.run_script("matrix-send-e2ee.py", "logout", "help", **env)
        argvs = [c["argv"] for c in self.calls()]
        self.assertEqual(argvs[0][0], "migrate-nio")
        self.assertEqual(argvs[-1], ["send", "!l:e", "--", "help"])

    def test_logout_and_help_never_trigger_a_takeover(self):
        self.run_script("matrix-e2ee-cli.py", "logout")
        self.run_script("matrix-e2ee-cli.py", "send", "--help")
        self.assertEqual([c["argv"][0] for c in self.calls()], ["logout", "send"])


class FlagValueTests(WrapperTestCase):
    def test_a_filename_starting_with_a_dash_stays_a_value(self):
        self.assertTranslates(
            "matrix-download-e2ee.py",
            ["!o:e", "$e", "--filename=--draft.pdf"],
            ["download", "--filename=--draft.pdf", "--", "!o:e", "$e"],
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
            ("matrix-send-e2ee.py", ["!o:e", "hi", "--json"]),
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

    def react_failure(self, args, stderr):
        result = self.run_script(
            "matrix-react.py",
            "!r:e",
            "$e",
            *args,
            "--json",
            FAKE_CLI_RC="1",
            FAKE_CLI_STDERR=stderr,
        )
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stdout.strip(), "no JSON on stdout")
        return json.loads(result.stdout)

    def test_a_failed_removal_in_a_swap_reports_what_was_done(self):
        # react.rs v0.3.0 remove_reactions: the error names what already happened.
        payload = self.react_failure(
            ["🩹", "--replace", "▶️", "✅"],
            "error: could not remove ✅ ($r2) (already done: set 🩹 ($s1), "
            "removed ▶️ ($r1)): M_FORBIDDEN: denied\n",
        )
        self.assertEqual(payload.get("event_id"), "$s1")
        self.assertEqual(payload.get("removed"), ["▶️"])
        self.assertTrue(payload["error"].startswith("could not remove ✅ ($r2)"))
        self.assertNotIn("unparsed", payload)

    def test_keys_with_spaces_are_kept_whole(self):
        payload = self.react_failure(
            ["all good", "▶️"],
            "Applied before the error: all good\n"
            "error: sending the reaction failed: rate limited\n",
        )
        self.assertEqual(payload.get("applied"), ["all good"])
        self.assertNotIn("unparsed", payload)
        payload = self.react_failure(
            ["done", "--replace", "in progress"],
            "error: could not remove in progress ($r) (already done: set done ($s))"
            ": boom\n",
        )
        self.assertEqual((payload.get("event_id"), payload.get("removed")), ("$s", []))

    def test_a_report_that_does_not_fit_the_keys_is_passed_on_not_guessed(self):
        payload = self.react_failure(
            ["✅", "--replace", "▶️"],
            "Applied before the error: something else\n"
            "error: could not remove 🦆 ($r) (already done: set ✅ ($s)): boom\n",
        )
        self.assertNotIn("applied", payload)
        self.assertNotIn("event_id", payload)
        self.assertEqual(
            payload.get("unparsed"),
            [
                "Applied before the error: something else",
                "error: could not remove 🦆 ($r) (already done: set ✅ ($s)): boom",
            ],
        )

    def test_without_json_a_failure_prints_nothing_on_stdout(self):
        result = self.run_script(
            "matrix-send-e2ee.py",
            "!o:e",
            "hi",
            FAKE_CLI_RC="1",
            FAKE_CLI_STDERR="error: no room\n",
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")

    def test_success_output_is_not_wrapped(self):
        result = self.run_script("matrix-send-e2ee.py", "!o:e", "hi", "--json")
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


# The joined rooms as `matrix-e2ee-cli rooms --json` lists them: !a:e (alias
# #ops:e, name Operations), !b:e (named ops), !c:e and !d:e (dev chat, dev
# talk), !t:e and !ta:e (test, test-archive), !dm:e (named after its member).
LOOKUP_ROOMS = [
    {"room_id": "!a:e", "name": "Operations", "alias": "#ops:e"},
    {"room_id": "!b:e", "name": "ops", "alias": None},
    {"room_id": "!c:e", "name": "dev chat", "alias": None},
    {"room_id": "!d:e", "name": "dev talk", "alias": None},
    {"room_id": "!t:e", "name": "test", "alias": None},
    {"room_id": "!ta:e", "name": "test-archive", "alias": None},
    {"room_id": "!dm:e", "name": "Jane", "alias": None, "members": ["@jane:e"]},
]
LOOKUP = ["rooms", "--json"]


class RoomLookupTests(WrapperTestCase):
    def setUp(self):
        super().setUp()
        self.env["FAKE_ROOMS"] = json.dumps(LOOKUP_ROOMS)
        session = self.root / "data" / "matrix-e2ee-cli" / "session.json"
        session.parent.mkdir(parents=True)
        session.write_text(json.dumps({"homeserver": "http://127.0.0.1:9"}))

    def calls(self):
        # Without the lookup's own `rooms --json`: the commands it chose rooms for.
        return [c for c in super().calls() if c["argv"] != LOOKUP]

    def test_ctrl_c_during_the_lookup_exits_130_quietly(self):
        result = self.run_script(
            "matrix-send-e2ee.py", "ops", "hi", FAKE_ROOMS_RC="130"
        )
        self.assertEqual(result.returncode, 130, result.stderr)
        self.assertNotIn("Error", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_an_exact_name_starting_with_a_dash_is_resolved_first(self):
        rooms = [*LOOKUP_ROOMS, {"room_id": "!dash:e", "name": "-ops", "alias": None}]
        self.env["FAKE_ROOMS"] = json.dumps(rooms)
        for script in ("matrix-send.py", "matrix-send-e2ee.py"):
            with self.subTest(script=script):
                self.log.unlink(missing_ok=True)
                self.assertTranslates(
                    script, ["--", "-ops", "hi"], ["send", "!dash:e", "--", "hi"]
                )
        for script, args, expected in (
            (
                "matrix-edit.py",
                ["--", "-ops", "$e", "x"],
                ["edit", "--", "!dash:e", "$e", "x"],
            ),
            ("matrix-read.py", ["--", "-ops"], ["read", "--", "!dash:e"]),
            (
                "matrix-invite.py",
                ["--", "-ops", "@a:e"],
                ["invite", "--", "!dash:e", "@a:e"],
            ),
            (
                "matrix-power-level.py",
                ["--show", "--", "-ops"],
                ["power-level", "--show", "--", "!dash:e"],
            ),
        ):
            with self.subTest(script=script):
                self.log.unlink(missing_ok=True)
                self.assertTranslates(script, args, expected)

    def test_options_stay_intermixed_around_the_separator(self):
        # An option after ROOM, a message that starts with "-" after "--".
        self.assertTranslates(
            "matrix-send-e2ee.py",
            ["ops", "--notice", "--", "-hi"],
            ["send", "--notice", "!a:e", "--", "-hi"],
        )
        self.log.unlink()
        self.assertTranslates(
            "matrix-send-e2ee.py",
            ["--notice", "ops", "hi", "--json"],
            ["send", "--notice", "--json", "!a:e", "--", "hi"],
        )

    def test_the_rooms_are_listed_by_the_cli_once(self):
        self.assertTranslates("matrix-read-e2ee.py", ["ops"], ["read", "--", "!a:e"])
        lookups = [c for c in super().calls() if c["argv"] == LOOKUP]
        self.assertEqual(len(lookups), 1)

    def test_one_exact_name_wins_over_a_room_that_contains_it(self):
        # Rooms "test" and "test-archive": version 4's E2EE scripts took "test".
        cases = (
            ("matrix-send-e2ee.py", ["test", "hi"], ["send", "!t:e", "--", "hi"]),
            ("matrix-read-e2ee.py", ["test"], ["read", "--", "!t:e"]),
            (
                "matrix-edit-e2ee.py",
                ["test", "$e", "x"],
                ["edit", "--", "!t:e", "$e", "x"],
            ),
            (
                "matrix-react.py",
                ["test", "$e", "✅"],
                ["react", "--", "!t:e", "$e", "✅"],
            ),
            ("matrix-redact.py", ["test", "$e"], ["redact", "--", "!t:e", "$e"]),
            (
                "matrix-download-e2ee.py",
                ["test", "$e"],
                ["download", "--", "!t:e", "$e"],
            ),
            ("matrix-fetch-keys.py", ["test"], ["fetch-keys", "--", "!t:e"]),
        )
        for script, args, expected in cases:
            with self.subTest(script=script):
                self.log.unlink(missing_ok=True)
                self.assertTranslates(script, args, expected)

    def test_a_failed_room_listing_stops_reads_and_writes(self):
        for script, args in (
            ("matrix-send-e2ee.py", ["ops", "hi"]),
            ("matrix-read-e2ee.py", ["ops"]),
        ):
            with self.subTest(script=script):
                self.log.unlink(missing_ok=True)
                result = self.run_script(
                    script,
                    *args,
                    FAKE_ROOMS_RC="1",
                    FAKE_ROOMS_STDERR="error: not logged in\n",
                )
                self.assertEqual(result.returncode, 1)
                self.assertIn("not logged in", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(self.calls(), [])

    def test_a_room_without_alias_is_found_by_its_name(self):
        rooms = [
            dict(r, alias=None) if r["room_id"] == "!a:e" else r for r in LOOKUP_ROOMS
        ]
        self.env["FAKE_ROOMS"] = json.dumps(rooms)
        self.assertTranslates(
            "matrix-send-e2ee.py", ["ops", "hi"], ["send", "!b:e", "--", "hi"]
        )

    def test_a_room_named_after_its_member_is_found(self):
        self.assertTranslates("matrix-read-e2ee.py", ["Jane"], ["read", "--", "!dm:e"])

    def test_unreadable_members_stop_the_lookup(self):
        result = self.run_script(
            "matrix-read-e2ee.py",
            "ops",
            FAKE_ROOMS_STDERR="warning: cannot read the members of !g:e, listed "
            "under its room id: 403\n",
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot read the members of !g:e", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_a_listing_that_is_not_json_is_a_json_error(self):
        result = self.run_script(
            "matrix-send-e2ee.py", "ops", "hi", "--json", FAKE_ROOMS="<html>"
        )
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stdout.strip(), result.stderr)
        self.assertIn(
            "cannot list the joined rooms", json.loads(result.stdout)["error"]
        )
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(self.calls(), [])

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
            (
                "matrix-invite.py",
                ["ops", "@a:e"],
                ["invite", "--", "!a:e", "@a:e"],
            ),
            (
                "matrix-power-level.py",
                ["#ops", "--set", "@a:e", "50"],
                ["power-level", "--set", "@a:e", "50", "--", "!a:e"],
            ),
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

    def test_writes_refuse_a_partial_name_that_reads_accept(self):
        for script, args in (
            ("matrix-send-e2ee.py", ["Opera", "hi"]),
            ("matrix-edit-e2ee.py", ["Opera", "$e", "x"]),
            ("matrix-react.py", ["Opera", "$e", "✅"]),
            ("matrix-redact.py", ["Opera", "$e"]),
            ("matrix-invite.py", ["Opera", "@a:e"]),
            ("matrix-power-level.py", ["Opera", "--set", "@a:e", "50"]),
            ("matrix-send.py", ["Opera", "hi"]),
            ("matrix-edit.py", ["Opera", "$e", "x"]),
        ):
            with self.subTest(script=script):
                result = self.run_script(script, *args)
                self.assertEqual(result.returncode, 1)
                self.assertIn("exact name", result.stderr)
                self.assertEqual(self.calls(), [])
        self.assertTranslates("matrix-read-e2ee.py", ["Opera"], ["read", "--", "!a:e"])
        self.log.unlink()
        self.assertTranslates("matrix-read.py", ["Opera"], ["read", "--", "!a:e"])
        for args, expected in (
            (["Opera", "--show"], ["power-level", "--show", "--", "!a:e"]),
            (["Opera", "--get", "@a:e"], ["power-level", "--get=@a:e", "--", "!a:e"]),
        ):
            with self.subTest(args=args):
                self.log.unlink()
                self.assertTranslates("matrix-power-level.py", args, expected)

    def test_an_ambiguous_shorthand_is_refused_before_the_cli_runs(self):
        result = self.run_script("matrix-send-e2ee.py", "dev", "hi", "--json")
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stdout.strip(), "no JSON on stdout")
        self.assertIn("several rooms", json.loads(result.stdout)["error"])
        self.assertEqual(self.calls(), [])


class NoSessionTests(WrapperTestCase):
    """Without a matrix-e2ee-cli session no shorthand reaches the CLI."""

    def test_a_shorthand_stops_with_the_setup_hint(self):
        for script, args in (
            ("matrix-send.py", ["ops", "hi"]),
            ("matrix-send-e2ee.py", ["--", "-ops", "hi"]),
            ("matrix-read-e2ee.py", ["ops"]),
            ("matrix-invite.py", ["ops", "@a:e"]),
            ("matrix-power-level.py", ["ops", "--show"]),
        ):
            with self.subTest(script=script):
                self.log.unlink(missing_ok=True)
                result = self.run_script(script, *args)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn("matrix-e2ee-setup.py", result.stderr)
                self.assertEqual(self.calls(), [])

    def test_ids_and_full_aliases_still_pass(self):
        self.assertTranslates("matrix-read.py", ["#ops:e"], ["read", "--", "#ops:e"])

    def test_resolve_checks_the_hash_before_anything_runs(self):
        result = self.run_script("matrix-resolve.py", "ops")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, "Error: Alias must start with #\n")
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
