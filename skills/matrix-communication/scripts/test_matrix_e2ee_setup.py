# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Test for `matrix-e2ee-setup.py`: no device is created with a refused nio.

The script imports matrix-nio at module level, which the stdlib-only test job
does not install, so a stand-in module takes its place while the script loads.
Run the file directly:

    python3 skills/matrix-communication/scripts/test_matrix_e2ee_setup.py

Stdlib only.
"""

import asyncio
import importlib.util
import os
import sys
import types
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPT = os.path.join(_HERE, "matrix-e2ee-setup.py")


class FakeClient:
    async def login(self, **_kwargs):
        return "login refused"

    async def close(self):
        pass


def _load_script():
    nio = types.ModuleType("nio")
    nio.AsyncClient = FakeClient
    nio.AsyncClientConfig = dict
    nio.LoginResponse = dict
    spec = importlib.util.spec_from_file_location("matrix_e2ee_setup", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    streams = {name: mock.Mock() for name in ("stdout", "stderr")}
    with (
        mock.patch.dict(sys.modules, {"nio": nio}),
        mock.patch.multiple(sys, **streams),
    ):
        spec.loader.exec_module(module)
    return module


class SetupDeviceGuardTests(unittest.TestCase):
    def run_setup(self, guard):
        opened = []

        def client(**kwargs):
            opened.append(kwargs)
            return FakeClient()

        script = _load_script()
        config = {"user_id": "@u:example.org", "homeserver": "https://example.org"}
        with mock.patch.multiple(
            script,
            refuse_unsupported_nio=guard,
            get_store_path=lambda: "/nonexistent",
            AsyncClient=client,
        ):
            try:
                asyncio.run(script.setup_device(config, "pw"))
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
