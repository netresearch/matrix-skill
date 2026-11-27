# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Matrix Skill shared library.

This module provides common functionality for all Matrix scripts.
All modules use ONLY stdlib; end-to-end encryption is matrix-e2ee-cli's job
(see cli.py, cutover.py and wrapper.py).

Usage:
    # At the top of each script, add:
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    # Then import what you need:
    from _lib import load_config, matrix_request, find_room_by_name
"""

# Config
from _lib.config import get_config_path, load_config

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

# HTTP API
from _lib.http import matrix_request, path_segment

# Room operations
from _lib.rooms import (
    find_direct_room,
    find_room_by_name,
    get_room_info,
    list_joined_rooms,
    normalize_room_input,
    resolve_room_alias,
    resolve_room_cli,
    room_matches,
)

# Utilities
from _lib.utils import (
    clean_message,
    format_timestamp,
)

__all__ = [
    "add_bot_prefix",
    "build_mentions",
    "clean_message",
    "find_direct_room",
    "find_room_by_name",
    "format_timestamp",
    "get_config_path",
    "get_room_info",
    "inject_pills",
    "list_joined_rooms",
    "load_config",
    "markdown_to_html",
    "matrix_request",
    "mention_pill",
    "normalize_room_input",
    "path_segment",
    "resolve_room_alias",
    "resolve_room_cli",
    "rich_text_fields",
    "room_matches",
    "shorten_service_urls",
]
