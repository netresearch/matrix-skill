#!/usr/bin/env python3
"""Deactivate a Matrix user.

Calls ``POST /_synapse/admin/v1/deactivate/{user_id}``.  The user is
unable to log in again afterwards and joined-rooms membership is severed.
**Not reversible** without direct database intervention.

Prints the user's profile and joined-rooms list before and after, so the
console transcript serves as an audit trail.

Usage:
    synapse-deactivate-user.py <USER_ID> [--erase] [--yes]
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib import admin_request, bold, load_config, quote, red, yellow


def _user_info(config: dict, user_id: str) -> dict:
    return admin_request(config, "GET", f"/v2/users/{quote(user_id)}")


def _joined_rooms(config: dict, user_id: str) -> list[str]:
    res = admin_request(config, "GET", f"/v2/users/{quote(user_id)}/joined_rooms")
    return res.get("joined_rooms", []) if isinstance(res, dict) else []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("user_id")
    parser.add_argument(
        "--erase",
        action="store_true",
        help="GDPR erase: also remove the user's messages from rooms.",
    )
    parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation.")
    args = parser.parse_args()

    config = load_config()

    print(bold("Before:"))
    print(json.dumps(_user_info(config, args.user_id), indent=2))
    print(json.dumps(_joined_rooms(config, args.user_id), indent=2))

    if not args.yes:
        if sys.stdin.isatty():
            print(
                bold(
                    red(f"⚠ About to deactivate {args.user_id}. This cannot be undone.")
                )
            )
            try:
                answer = input("Type 'YES' to continue: ").strip()
            except EOFError:
                answer = ""
            if answer != "YES":
                print(yellow("Aborted."))
                return 1
        else:
            print(
                bold(red("Refusing to run non-interactively without --yes.")),
                file=sys.stderr,
            )
            return 2

    body = {"erase": True} if args.erase else None
    res = admin_request(config, "POST", f"/v1/deactivate/{quote(args.user_id)}", body)
    print(bold("Deactivate response:"))
    print(json.dumps(res, indent=2))

    print(bold("After:"))
    print(json.dumps(_user_info(config, args.user_id), indent=2))
    print(json.dumps(_joined_rooms(config, args.user_id), indent=2))

    return 0 if "error" not in res else 1


if __name__ == "__main__":
    sys.exit(main())
