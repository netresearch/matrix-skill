# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Tests for `_lib/cli.py` (finding, downloading, verifying the CLI binary) and
`Build/Scripts/pin-cli-release.py` (the pin it trusts).

Run directly (stdlib only, no network: downloads go through a fake opener):

    python3 skills/matrix-communication/scripts/_lib/test_cli.py

Running this file puts its own directory first on sys.path, where `http.py`
would shadow the stdlib `http` package: the directory is replaced by its parent
before any other import.
"""

import os
import sys

_LIB = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _LIB]
sys.path.insert(0, os.path.dirname(_LIB))

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

from _lib import cli

_HERE = Path(_LIB)

ROOT = _HERE.parents[3]
_spec = importlib.util.spec_from_file_location(
    "pin_cli_release", ROOT / "Build" / "Scripts" / "pin-cli-release.py"
)
pin = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pin)

PAYLOAD = b"#!/bin/sh\necho fake\n"


def sha(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


class FakeOpener:
    """Stands in for urllib.request.urlopen; counts the calls."""

    def __init__(self, data: bytes):
        self.data = data
        self.urls = []

    def __call__(self, url, timeout=None):
        self.urls.append(url)
        return io.BytesIO(self.data)


class AssetNameTests(unittest.TestCase):
    def test_each_supported_platform_maps_to_its_release_asset(self):
        cases = {
            ("Linux", "x86_64"): "matrix-e2ee-cli-x86_64-unknown-linux-musl",
            ("Linux", "amd64"): "matrix-e2ee-cli-x86_64-unknown-linux-musl",
            ("Linux", "aarch64"): "matrix-e2ee-cli-aarch64-unknown-linux-musl",
            ("Linux", "arm64"): "matrix-e2ee-cli-aarch64-unknown-linux-musl",
            ("Darwin", "arm64"): "matrix-e2ee-cli-aarch64-apple-darwin",
            ("Darwin", "x86_64"): "matrix-e2ee-cli-x86_64-apple-darwin",
            ("Windows", "AMD64"): "matrix-e2ee-cli-x86_64-pc-windows-msvc.exe",
        }
        for (system, machine), asset in cases.items():
            with self.subTest(system=system, machine=machine):
                try:
                    got = cli.asset_name(system, machine)
                except cli.CliError as exc:
                    self.fail(f"refused a supported platform: {exc}")
                self.assertEqual(got, asset)

    def test_an_unsupported_platform_is_refused_with_the_override_named(self):
        for system, machine in (
            ("Linux", "riscv64"),
            ("FreeBSD", "x86_64"),
            ("Windows", "ARM64"),
        ):
            with self.subTest(system=system, machine=machine):
                with self.assertRaises(cli.CliError) as ctx:
                    cli.asset_name(system, machine)
                self.assertIn(cli.ENV_OVERRIDE, str(ctx.exception))

    def test_the_committed_pin_has_a_hash_for_every_mapped_asset(self):
        release = cli.load_release()
        for asset in cli.PLATFORM_ASSETS.values():
            with self.subTest(asset=asset):
                self.assertRegex(release["assets"].get(asset, ""), r"^[0-9a-f]{64}$")


class DataDirTests(unittest.TestCase):
    def test_xdg_data_home_wins_everywhere(self):
        for system in ("Linux", "Darwin", "Windows"):
            with self.subTest(system=system):
                env = {
                    "XDG_DATA_HOME": "/x/data",
                    "HOME": "/home/u",
                    "LOCALAPPDATA": "C:/L",
                }
                self.assertEqual(cli.data_dir(env, system), Path("/x/data"))

    def test_platform_defaults(self):
        self.assertEqual(
            cli.data_dir({"HOME": "/home/u"}, "Linux"), Path("/home/u/.local/share")
        )
        self.assertEqual(
            cli.data_dir({"HOME": "/Users/u"}, "Darwin"),
            Path("/Users/u/Library/Application Support"),
        )
        self.assertEqual(
            cli.data_dir({"LOCALAPPDATA": "C:/L", "USERPROFILE": "C:/U"}, "Windows"),
            Path("C:/L"),
        )

    def test_the_binary_lives_in_a_per_version_directory(self):
        release = {"repository": "o/r", "version": "1.2.3", "assets": {}}
        path = cli.install_path(release, "asset", {"HOME": "/home/u"}, "Linux")
        self.assertEqual(
            path, Path("/home/u/.local/share/matrix-skill/cli/1.2.3/asset")
        )
        self.assertEqual(
            cli.download_url(release, "asset"),
            "https://github.com/o/r/releases/download/v1.2.3/asset",
        )


class EnsureBinaryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.env = {
            "HOME": str(self.dir / "home"),
            "XDG_DATA_HOME": str(self.dir / "data"),
        }
        self.asset = cli.asset_name("Linux", "x86_64")
        self.release_file = self.dir / "cli_release.json"
        self.pin(sha(PAYLOAD))

    def pin(self, digest):
        self.release_file.write_text(
            json.dumps(
                {
                    "repository": "o/r",
                    "version": "1.2.3",
                    "assets": {self.asset: digest},
                }
            )
        )

    def ensure(self, opener):
        return cli.ensure_binary(
            env=self.env,
            release_path=self.release_file,
            system="Linux",
            machine="x86_64",
            opener=opener,
        )

    def test_a_matching_download_is_installed_executable(self):
        opener = FakeOpener(PAYLOAD)
        path = self.ensure(opener)
        self.assertEqual(path.read_bytes(), PAYLOAD)
        self.assertTrue(os.access(path, os.X_OK))
        self.assertEqual(
            opener.urls,
            [f"https://github.com/o/r/releases/download/v1.2.3/{self.asset}"],
        )
        self.assertEqual(path.parent.name, "1.2.3")

    def test_a_wrong_hash_is_rejected_and_nothing_is_left_behind(self):
        self.pin("0" * 64)
        with self.assertRaises(cli.CliError) as ctx:
            self.ensure(FakeOpener(PAYLOAD))
        self.assertIn("0" * 64, str(ctx.exception))
        directory = self.dir / "data" / "matrix-skill" / "cli" / "1.2.3"
        self.assertEqual(list(directory.iterdir()), [])

    def test_an_installed_binary_is_not_downloaded_again(self):
        self.ensure(FakeOpener(PAYLOAD))
        opener = FakeOpener(PAYLOAD)
        self.ensure(opener)
        self.assertEqual(opener.urls, [])

    def test_a_modified_installed_binary_is_replaced(self):
        path = self.ensure(FakeOpener(PAYLOAD))
        path.write_bytes(b"tampered")
        opener = FakeOpener(PAYLOAD)
        self.ensure(opener)
        self.assertEqual(len(opener.urls), 1)
        self.assertEqual(path.read_bytes(), PAYLOAD)

    def test_the_override_is_used_as_is_without_download(self):
        own = self.dir / "own-cli"
        own.write_bytes(b"anything")
        self.env[cli.ENV_OVERRIDE] = str(own)
        opener = FakeOpener(PAYLOAD)
        self.assertEqual(self.ensure(opener), own)
        self.assertEqual(opener.urls, [])

    def test_an_override_that_is_no_file_is_refused(self):
        self.env[cli.ENV_OVERRIDE] = str(self.dir / "missing")
        with self.assertRaises(cli.CliError):
            self.ensure(FakeOpener(PAYLOAD))

    def test_a_relative_override_runs_the_file_it_names(self):
        # A bare name would be looked up in PATH by run(); the file in the
        # working directory is the one meant.
        script = self.dir / "own-cli"
        script.write_text("#!/bin/sh\nexit 7\n")
        script.chmod(0o755)
        cwd = os.getcwd()
        os.chdir(self.dir)
        self.addCleanup(os.chdir, cwd)
        self.env[cli.ENV_OVERRIDE] = "own-cli"
        path = cli.find_binary(self.env)
        self.assertTrue(path.is_absolute(), path)
        self.assertEqual(cli.run(path, [], env={"PATH": "/nonexistent"}), 7)

    def test_run_returns_the_exit_code(self):
        script = self.dir / "exit7"
        script.write_text("#!/bin/sh\nexit 7\n")
        script.chmod(0o755)
        self.assertEqual(cli.run(script, []), 7)


class PinScriptTests(unittest.TestCase):
    def sums(self, skip=None):
        return "".join(
            f"{sha(name.encode())}  {name}\n"
            for name in sorted(set(cli.PLATFORM_ASSETS.values()))
            if name != skip
        )

    def test_a_complete_sums_file_pins_every_asset(self):
        built = pin.build_pin(pin.parse_sums(self.sums()), "v0.3.0")
        self.assertEqual(built["version"], "0.3.0")
        self.assertEqual(built["repository"], "netresearch/matrix-e2ee-cli")
        self.assertEqual(set(built["assets"]), set(cli.PLATFORM_ASSETS.values()))

    def test_a_missing_asset_is_refused(self):
        sums = pin.parse_sums(self.sums(skip="matrix-e2ee-cli-x86_64-apple-darwin"))
        try:
            pin.build_pin(sums, "0.3.0")
        except ValueError as exc:
            self.assertIn("x86_64-apple-darwin", str(exc))
        except Exception as exc:  # noqa: BLE001  # anything else is the defect under test
            self.fail(f"refused with {exc!r} instead of naming the missing asset")
        else:
            self.fail("a SHA256SUMS without x86_64-apple-darwin was pinned")

    def test_a_malformed_line_is_refused(self):
        with self.assertRaises(ValueError):
            pin.parse_sums("not-a-hash  matrix-e2ee-cli-x86_64-unknown-linux-musl\n")

    def test_main_writes_what_load_release_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            sums = Path(tmp) / "SHA256SUMS"
            sums.write_text(self.sums())
            out = Path(tmp) / "pin.json"
            printed = io.StringIO()
            with contextlib.redirect_stdout(printed):
                self.assertEqual(
                    pin.main([str(sums), "0.3.0", "--output", str(out)]), 0
                )
            self.assertIn("Pinned matrix-e2ee-cli 0.3.0 (5 assets)", printed.getvalue())
            self.assertEqual(cli.load_release(out)["version"], "0.3.0")


if __name__ == "__main__":
    unittest.main()
