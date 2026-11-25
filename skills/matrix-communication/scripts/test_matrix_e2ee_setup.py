# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Test for `matrix-e2ee-setup.py`: no device is created with a refused nio.

The script imports matrix-nio at module level, which the stdlib-only test job
does not install. `setup_device` is therefore read with `ast` and executed on
its own, with stand-ins for the names it uses. Run the file directly:

    python3 skills/matrix-communication/scripts/test_matrix_e2ee_setup.py

Stdlib only.
"""

import ast
import asyncio
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPT = os.path.join(_HERE, "matrix-e2ee-setup.py")


def _setup_device(namespace):
    with open(_SCRIPT, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "setup_device":
            module = ast.Module(body=[node], type_ignores=[])
            exec(compile(module, _SCRIPT, "exec"), namespace)  # noqa: S102
            return namespace["setup_device"]
    raise AssertionError("setup_device not found in matrix-e2ee-setup.py")


class FakeClient:
    async def login(self, **_kwargs):
        return "login refused"

    async def close(self):
        pass


class SetupDeviceGuardTests(unittest.TestCase):
    def run_setup(self, guard):
        opened = []

        def client(**kwargs):
            opened.append(kwargs)
            return FakeClient()

        setup_device = _setup_device(
            {
                "refuse_unsupported_nio": guard,
                "get_store_path": lambda: "/nonexistent",
                "AsyncClientConfig": lambda **kwargs: kwargs,
                "AsyncClient": client,
                "LoginResponse": dict,
            }
        )
        config = {"user_id": "@u:example.org", "homeserver": "https://example.org"}
        try:
            asyncio.run(setup_device(config, "pw"))
        except SystemExit:
            return opened, True
        return opened, False

    def test_a_refused_nio_never_creates_a_client(self):
        def refuse():
            raise SystemExit("refused")

        self.assertEqual(self.run_setup(refuse), ([], True))

    def test_a_supported_nio_creates_the_client(self):
        opened, stopped = self.run_setup(lambda: None)
        self.assertEqual((len(opened), stopped), (1, False))


if __name__ == "__main__":
    unittest.main()
