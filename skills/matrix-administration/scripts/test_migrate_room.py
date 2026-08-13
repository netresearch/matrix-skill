"""Tests for `synapse-migrate-room.py`'s confirmation gate.

The script name contains a hyphen so it is not importable as a module; it is
loaded by path. Run the file directly:

    python3 skills/matrix-administration/scripts/test_migrate_room.py

Stdlib only. No homeserver is contacted - `client_request` and `admin_request`
are replaced by recorders, so a test that reaches past its stubs fails loudly
rather than reaching the network.
"""

import importlib.util
import io
import os
import sys
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "synapse_migrate_room", os.path.join(_HERE, "synapse-migrate-room.py")
)
migrate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrate)

ROOM = "!room:example.org"
SPACE = "!space:example.org"
USER = "@admin:example.org"

# A room that needs every step: public, version 10, unencrypted.
UNHARDENED = {"join_rules": "public", "version": "10", "encryption": None}
# A room that needs none of them.
HARDENED = {
    "join_rules": "restricted",
    "version": "10",
    "encryption": "m.megolm.v1.aes-sha2",
}


class PlanTestCase(unittest.TestCase):
    def _steps(self, already_child, room_info):
        return migrate.plan_steps(ROOM, SPACE, USER, already_child, room_info)

    def test_unhardened_room_has_every_step_pending(self):
        steps = self._steps(False, UNHARDENED)
        self.assertTrue(all(pending for pending, _, _ in steps))

    def test_encryption_step_is_marked_irreversible(self):
        steps = self._steps(False, UNHARDENED)
        notes = {text: note for _, text, note in steps}
        self.assertEqual(notes["Enable Megolm encryption"], migrate.IRREVERSIBLE)

    def test_only_the_encryption_step_is_irreversible(self):
        steps = self._steps(False, UNHARDENED)
        irreversible = [t for _, t, n in steps if n == migrate.IRREVERSIBLE]
        self.assertEqual(irreversible, ["Enable Megolm encryption"])

    def test_hardened_room_leaves_only_the_join_and_promote_step(self):
        steps = self._steps(True, HARDENED)
        pending = [text for pending, text, _ in steps if pending]
        self.assertEqual(pending, [f"Force-join {USER} and raise to PL 100"])

    def test_low_room_version_skips_the_restricted_step(self):
        steps = self._steps(False, {**UNHARDENED, "version": "9"})
        pending = [text for pending, text, _ in steps if pending]
        self.assertNotIn("Switch join rules public → restricted", pending)

    def test_unparseable_room_version_skips_the_restricted_step(self):
        steps = self._steps(False, {**UNHARDENED, "version": "not-a-number"})
        pending = [text for pending, text, _ in steps if pending]
        self.assertNotIn("Switch join rules public → restricted", pending)

    def test_plan_prints_one_line_per_step(self):
        steps = self._steps(False, UNHARDENED)
        buf = io.StringIO()
        with redirect_stdout(buf):
            migrate.print_plan(ROOM, steps)
        body = buf.getvalue().splitlines()
        self.assertEqual(len(body), len(steps) + 1)  # + the heading
        self.assertIn(ROOM, body[0])


class _Stdin:
    def __init__(self, tty):
        self._tty = tty

    def isatty(self):
        return self._tty


@contextmanager
def captured():
    """Both streams, so an expected refusal is asserted rather than printed."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        yield out, err


class ConfirmTestCase(unittest.TestCase):
    def _confirm(self, assume_yes, tty, answer=None):
        stack = [
            mock.patch.object(migrate.sys, "stdin", _Stdin(tty=tty)),
        ]
        if answer is not None:
            kwargs = (
                {"side_effect": answer}
                if isinstance(answer, type) and issubclass(answer, BaseException)
                else {"return_value": answer}
            )
            stack.append(mock.patch.object(migrate, "input", create=True, **kwargs))
        with captured() as (out, err):
            for patcher in stack:
                patcher.start()
            try:
                code = migrate.confirm(assume_yes)
            finally:
                for patcher in reversed(stack):
                    patcher.stop()
        return code, out.getvalue(), err.getvalue()

    def test_yes_flag_proceeds_without_reading_stdin(self):
        code, out, err = self._confirm(assume_yes=True, tty=False)
        self.assertIsNone(code)
        self.assertEqual((out, err), ("", ""))

    def test_pipe_without_yes_is_refused(self):
        code, _, err = self._confirm(assume_yes=False, tty=False)
        self.assertEqual(code, 2)
        self.assertIn("Refusing to run non-interactively without --yes", err)

    def test_terminal_accepts_the_exact_word(self):
        code, _, _ = self._confirm(assume_yes=False, tty=True, answer="YES")
        self.assertIsNone(code)

    def test_terminal_rejects_anything_else(self):
        for answer in ("yes", "y", "", "YES please", "no"):
            with self.subTest(answer=answer):
                code, out, _ = self._confirm(assume_yes=False, tty=True, answer=answer)
                self.assertEqual(code, 1)
                self.assertIn("Aborted", out)

    def test_closed_stdin_on_a_terminal_aborts(self):
        code, out, _ = self._confirm(assume_yes=False, tty=True, answer=EOFError)
        self.assertEqual(code, 1)
        self.assertIn("Aborted", out)


class GateOrderTestCase(unittest.TestCase):
    """The gate is worth nothing if it runs after the first write.

    Every request the script makes is recorded with its method, and the run is
    driven to the refusal. Anything other than a GET means the room was already
    changed by the time the operator was asked.
    """

    def setUp(self):
        self.calls = []
        self._real_client = migrate.client_request
        self._real_admin = migrate.admin_request
        migrate.client_request = self._record_client
        migrate.admin_request = self._record_admin
        self.addCleanup(self._restore)

    def _restore(self):
        migrate.client_request = self._real_client
        migrate.admin_request = self._real_admin

    def _record_client(self, config, method, endpoint, body=None):
        self.calls.append((method, endpoint))
        return {"state": []}

    def _record_admin(self, config, method, endpoint, body=None):
        self.calls.append((method, endpoint))
        return dict(UNHARDENED)

    def _run(self, argv):
        with (
            mock.patch.object(migrate, "load_config", create=True) as cfg,
            mock.patch.object(sys, "argv", ["synapse-migrate-room.py", *argv]),
            captured() as (out, _),
        ):
            cfg.return_value = {"homeserver": "https://matrix.example.org"}
            return migrate.main(), out.getvalue()

    def test_refusal_happens_before_any_write(self):
        with mock.patch.object(migrate.sys, "stdin", _Stdin(tty=False)):
            code, _ = self._run([ROOM, USER, SPACE])
        self.assertEqual(code, 2)
        self.assertEqual([m for m, _ in self.calls if m != "GET"], [])

    def test_abort_at_the_prompt_happens_before_any_write(self):
        with (
            mock.patch.object(migrate.sys, "stdin", _Stdin(tty=True)),
            mock.patch.object(migrate, "input", create=True, return_value="no"),
        ):
            code, _ = self._run([ROOM, USER, SPACE])
        self.assertEqual(code, 1)
        self.assertEqual([m for m, _ in self.calls if m != "GET"], [])

    def test_the_plan_is_printed_before_the_question(self):
        with mock.patch.object(migrate.sys, "stdin", _Stdin(tty=False)):
            _, out = self._run([ROOM, USER, SPACE])
        self.assertIn("Plan for", out)
        self.assertIn("Enable Megolm encryption", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
