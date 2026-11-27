#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Pin a matrix-e2ee-cli release in the matrix-communication skill.

Usage:
    Build/Scripts/pin-cli-release.py SHA256SUMS VERSION [--output PATH]

SHA256SUMS is the file of that release (gh release download vVERSION
-R netresearch/matrix-e2ee-cli -p SHA256SUMS). Every asset the skill maps a
platform to must be listed; the result is written to
skills/matrix-communication/scripts/_lib/cli_release.json, the only place the
skill takes the version and the hashes from.
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills" / "matrix-communication" / "scripts"
DEFAULT_OUTPUT = SCRIPTS / "_lib" / "cli_release.json"
REPOSITORY = "netresearch/matrix-e2ee-cli"

sys.path.insert(0, str(SCRIPTS))
from _lib.cli import PLATFORM_ASSETS

LINE = re.compile(r"^([0-9a-f]{64}) [ *](\S+)$")
VERSION = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")


def parse_sums(text: str) -> dict:
    """{asset: sha256} from sha256sum output; any other line is an error."""
    sums = {}
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        match = LINE.match(line)
        if not match:
            raise ValueError(f"line {number} is not '<sha256>  <file>': {line!r}")
        digest, name = match.groups()
        if name in sums:
            raise ValueError(f"{name} is listed twice")
        sums[name] = digest
    return sums


def build_pin(sums: dict, version: str) -> dict:
    version = version.removeprefix("v")
    if not VERSION.match(version):
        raise ValueError(f"{version!r} is not a version (X.Y.Z)")
    wanted = sorted(set(PLATFORM_ASSETS.values()))
    missing = [name for name in wanted if name not in sums]
    if missing:
        raise ValueError(f"SHA256SUMS lacks {', '.join(missing)}")
    return {
        "repository": REPOSITORY,
        "version": version,
        "assets": {name: sums[name] for name in wanted},
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sums", type=Path, help="the release's SHA256SUMS file")
    parser.add_argument("version", help="the release version, e.g. 0.3.0")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    try:
        pin = build_pin(parse_sums(args.sums.read_text(encoding="utf-8")), args.version)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    args.output.write_text(json.dumps(pin, indent=2) + "\n", encoding="utf-8")
    print(
        f"Pinned matrix-e2ee-cli {pin['version']} ({len(pin['assets'])} assets) in {args.output}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
