# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Tests for `_lib.secret_input`: secrets come from the environment or a prompt.

Run directly (stdlib only):

    python3 skills/matrix-communication/scripts/_lib/test_secret_input.py
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from secret_input import SecretInputError, read_secret

ENV = "MATRIX_TEST_SECRET"


def never_ask(prompt):
    raise AssertionError("must not prompt")


class ReadSecretTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop(ENV, None)

    def test_value_on_the_command_line_is_refused(self):
        with self.assertRaises(SecretInputError) as caught:
            read_secret("hunter2", ENV, "p: ", ask=never_ask)
        self.assertIn(ENV, str(caught.exception))
        self.assertIn("--allow-secret-argument", str(caught.exception))

    def test_value_on_the_command_line_accepted_with_the_explicit_flag(self):
        self.assertEqual(
            read_secret("hunter2", ENV, "p: ", allow_argument=True, ask=never_ask),
            "hunter2",
        )

    def test_environment_variable_used_without_prompt(self):
        os.environ[ENV] = "from-env"
        self.assertEqual(read_secret("", ENV, "p: ", ask=never_ask), "from-env")

    def test_option_without_value_prompts(self):
        self.assertEqual(
            read_secret("", ENV, "p: ", interactive=True, ask=lambda p: "typed"),
            "typed",
        )

    def test_option_without_value_and_no_terminal_fails_clearly(self):
        with self.assertRaises(SecretInputError) as caught:
            read_secret("", ENV, "p: ", interactive=False, ask=never_ask)
        self.assertIn(ENV, str(caught.exception))

    def test_option_absent_and_no_environment_means_no_secret(self):
        self.assertIsNone(read_secret(None, ENV, "p: ", ask=never_ask))

    def test_empty_prompt_answer_is_refused(self):
        with self.assertRaises(SecretInputError):
            read_secret("", ENV, "p: ", interactive=True, ask=lambda p: "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
