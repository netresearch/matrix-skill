# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Matrix Skill shared library.

This module provides common functionality for all Matrix scripts.
All modules use ONLY stdlib. Every script runs matrix-e2ee-cli and so logs in
with its session alone (see cli.py, cutover.py and wrapper.py); only
matrix-doctor.py talks to the homeserver itself, to check a token (http.py).

Usage:
    # At the top of each script, add:
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    # Then import what you need:
    from _lib.wrapper import exit_with, room_chooser
"""

# Config
from _lib.config import get_config_path

# Formatting
from _lib.formatting import (
    add_bot_prefix,
    build_mentions,
    inject_pills,
    markdown_to_html,
    mention_pill,
    rich_text_fields,
    shorten_service_urls,
)

# Room arguments
from _lib.rooms import normalize_room_input, room_matches

# Utilities
from _lib.utils import (
    clean_message,
    format_timestamp,
)

__all__ = [
    "add_bot_prefix",
    "build_mentions",
    "clean_message",
    "format_timestamp",
    "get_config_path",
    "inject_pills",
    "markdown_to_html",
    "mention_pill",
    "normalize_room_input",
    "rich_text_fields",
    "room_matches",
    "shorten_service_urls",
]
