# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Find, download and run the matrix-e2ee-cli binary.

Stdlib only. The E2EE scripts of this skill are thin wrappers around
netresearch/matrix-e2ee-cli (Rust, matrix-sdk). This module supplies the binary:

- ``MATRIX_E2EE_CLI=<path>`` uses that binary as it is: no download and no
  hash check (tests, a local or debug build).
- Otherwise the release asset for this platform is kept in a per-version
  directory under the user's data directory and checked against the SHA-256
  pinned in ``cli_release.json`` before every run. A missing or mismatching
  file is downloaded from the GitHub release again; a download whose hash does
  not match the pin is deleted and never run.

The pin is the trust anchor: a SHA256SUMS file fetched at run time comes from
the same place as the binary and proves nothing on its own. Regenerate the pin
with ``Build/Scripts/pin-cli-release.py SHA256SUMS VERSION``.
"""

import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ENV_OVERRIDE = "MATRIX_E2EE_CLI"
RELEASE_FILE = Path(__file__).with_name("cli_release.json")
DOWNLOAD_TIMEOUT = 120
CHUNK = 1 << 16

# (platform.system(), normalized machine) -> release asset name, as
# matrix-e2ee-cli's .github/workflows/release.yml stages them.
PLATFORM_ASSETS = {
    ("Linux", "x86_64"): "matrix-e2ee-cli-x86_64-unknown-linux-musl",
    ("Linux", "aarch64"): "matrix-e2ee-cli-aarch64-unknown-linux-musl",
    ("Darwin", "x86_64"): "matrix-e2ee-cli-x86_64-apple-darwin",
    ("Darwin", "aarch64"): "matrix-e2ee-cli-aarch64-apple-darwin",
    ("Windows", "x86_64"): "matrix-e2ee-cli-x86_64-pc-windows-msvc.exe",
}

_MACHINE_ALIASES = {
    "x86_64": "x86_64",
    "amd64": "x86_64",
    "aarch64": "aarch64",
    "arm64": "aarch64",
}


class CliError(Exception):
    """The binary could not be found, downloaded or verified."""


def asset_name(system: str | None = None, machine: str | None = None) -> str:
    """The release asset for a platform (default: this one)."""
    system = system if system is not None else platform.system()
    machine = machine if machine is not None else platform.machine()
    arch = _MACHINE_ALIASES.get(machine.lower())
    asset = PLATFORM_ASSETS.get((system, arch)) if arch else None
    if asset is None:
        raise CliError(
            f"no matrix-e2ee-cli release for {system} {machine}; build it from "
            f"https://github.com/netresearch/matrix-e2ee-cli and set {ENV_OVERRIDE} "
            "to the binary"
        )
    return asset


def load_release(path: Path = RELEASE_FILE) -> dict:
    """The pinned release: {"repository", "version", "assets": {name: sha256}}."""
    try:
        release = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CliError(f"cannot read the pinned CLI release {path}: {exc}") from exc
    for key in ("repository", "version", "assets"):
        if key not in release:
            raise CliError(f"{path} has no {key!r}")
    # The version names a directory and a download URL: X.Y.Z only.
    if not re.fullmatch(r"\d+\.\d+\.\d+", str(release["version"])):
        raise CliError(f"{path}: version {release['version']!r} is not X.Y.Z")
    return release


def data_dir(env=None, system: str | None = None) -> Path:
    """The user's data directory: XDG_DATA_HOME, else the platform default."""
    env = os.environ if env is None else env
    system = system if system is not None else platform.system()
    xdg = env.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg)
    home = env.get("HOME") or env.get("USERPROFILE")
    if system == "Windows" and env.get("LOCALAPPDATA"):
        return Path(env["LOCALAPPDATA"])
    if not home:
        raise CliError("neither XDG_DATA_HOME nor HOME is set")
    if system == "Darwin":
        return Path(home) / "Library" / "Application Support"
    return Path(home) / ".local" / "share"


def install_path(release: dict, asset: str, env=None, system=None) -> Path:
    """Where the pinned binary lives: <data dir>/matrix-skill/cli/<version>/<asset>."""
    return data_dir(env, system) / "matrix-skill" / "cli" / release["version"] / asset


def download_url(release: dict, asset: str) -> str:
    return (
        f"https://github.com/{release['repository']}/releases/download/"
        f"v{release['version']}/{asset}"
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(
    url: str, target: Path, expected: str, opener=urllib.request.urlopen
) -> None:
    """Download URL to TARGET if its SHA-256 equals EXPECTED; else raise.

    Written to a temporary file in the target directory and moved into place
    only after the hash matched, so a partial or tampered download never sits
    at TARGET.
    """
    try:
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        handle, tmp_name = tempfile.mkstemp(prefix=".download-", dir=target.parent)
    except OSError as exc:  # an unwritable data directory, like a failed download
        raise CliError(f"cannot download {url} into {target.parent}: {exc}") from exc
    tmp = Path(tmp_name)
    try:
        digest = hashlib.sha256()
        with (
            os.fdopen(handle, "wb") as out,
            opener(url, timeout=DOWNLOAD_TIMEOUT) as response,
        ):
            for chunk in iter(lambda: response.read(CHUNK), b""):
                digest.update(chunk)
                out.write(chunk)
        actual = digest.hexdigest()
        if actual != expected:
            raise CliError(
                f"downloaded {url} has SHA-256 {actual}, but the skill pins {expected}; "
                "the file was deleted and not run"
            )
        tmp.chmod(0o755)
        os.replace(tmp, target)
    except OSError as exc:
        raise CliError(f"cannot download {url}: {exc}") from exc
    finally:
        tmp.unlink(missing_ok=True)


def find_binary(env=None, release_path: Path = RELEASE_FILE, system=None, machine=None):
    """The binary to run without downloading anything, or None.

    The override when set (it must be an existing file), else the installed
    pinned asset when its hash matches the pin.
    """
    env = os.environ if env is None else env
    override = env.get(ENV_OVERRIDE)
    if override:
        # Absolute: run() would look a bare "matrix-e2ee-cli" up in PATH.
        path = Path(os.path.abspath(override))
        if not path.is_file():
            raise CliError(f"{ENV_OVERRIDE}={override} is not a file")
        return path
    release = load_release(release_path)
    asset = asset_name(system, machine)
    expected = release["assets"].get(asset)
    if not expected:
        raise CliError(
            f"the pinned release {release['version']} has no hash for {asset}"
        )
    path = install_path(release, asset, env, system)
    if path.is_file() and sha256_file(path) == expected:
        return path
    return None


def ensure_binary(
    env=None,
    release_path: Path = RELEASE_FILE,
    system=None,
    machine=None,
    opener=urllib.request.urlopen,
    log=None,
) -> Path:
    """The binary to run, downloaded and verified first when needed."""
    found = find_binary(env, release_path, system, machine)
    if found is not None:
        return found
    release = load_release(release_path)
    asset = asset_name(system, machine)
    path = install_path(release, asset, env, system)
    url = download_url(release, asset)
    if log is not None:
        log(
            f"Downloading matrix-e2ee-cli {release['version']} ({asset}) to {path.parent}"
        )
    download(url, path, release["assets"][asset], opener=opener)
    return path


def run(binary: Path, args: list, env=None) -> int:
    """Run the binary with inherited stdin, stdout and stderr; its exit code."""
    try:
        return subprocess.run([str(binary), *args], env=env, check=False).returncode
    except KeyboardInterrupt:
        return 130
    except OSError as exc:
        raise CliError(f"cannot run {binary}: {exc}") from exc


def run_captured(binary: Path, args: list, env=None) -> subprocess.CompletedProcess:
    """Run the binary with stdout and stderr captured (stdin inherited)."""
    try:
        return subprocess.run(
            [str(binary), *args], env=env, capture_output=True, text=True, check=False
        )
    except KeyboardInterrupt:
        return subprocess.CompletedProcess(args, 130, "", "")
    except OSError as exc:
        raise CliError(f"cannot run {binary}: {exc}") from exc


def stderr_log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)
