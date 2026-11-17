# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Wiring test for `matrix-read-e2ee.py`: every message branch passes on the
event's `format` / `formatted_body`.

The script imports matrix-nio at module level, which the stdlib-only test job
does not install, so the script is not executed. Its `process_event` function
is read with `ast` instead, and each dict it returns for a message is checked
for a `**rich_text_fields(...)` entry. `_lib/test_formatting.py` tests the
helper itself. Run the file directly:

    python3 skills/matrix-communication/scripts/test_matrix_read_e2ee.py

Stdlib only.
"""

import ast
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPT = os.path.join(_HERE, "matrix-read-e2ee.py")


def _process_event():
    with open(_SCRIPT, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "process_event":
            return node
    raise AssertionError("process_event not found in matrix-read-e2ee.py")


def _message_dicts(func):
    """Dict literals in `process_event` that build a message (they hold "body")."""
    for node in ast.walk(func):
        if isinstance(node, ast.Dict):
            keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
            if "body" in keys:
                yield node, keys


def _spreads_rich_text_fields(node):
    for key, value in zip(node.keys, node.values):
        if (
            key is None
            and isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "rich_text_fields"
        ):
            return True
    return False


class ProcessEventWiringTests(unittest.TestCase):
    def test_every_decrypted_message_branch_carries_rich_text_fields(self):
        func = _process_event()
        checked = 0
        for node, _keys in _message_dicts(func):
            body = next(
                v
                for k, v in zip(node.keys, node.values)
                if isinstance(k, ast.Constant) and k.value == "body"
            )
            # The undecryptable branch has a fixed placeholder body and no content.
            if isinstance(body, ast.Constant) and body.value == "[Unable to decrypt]":
                continue
            checked += 1
            self.assertTrue(
                _spreads_rich_text_fields(node),
                f"message dict at line {node.lineno} does not spread rich_text_fields(...)",
            )
        # m.text, m.emote and the generic m.room.message branch
        self.assertEqual(checked, 3)


if __name__ == "__main__":
    unittest.main()
