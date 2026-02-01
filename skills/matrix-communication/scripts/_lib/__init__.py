"""Matrix Skill shared library.

This module provides common functionality for all Matrix scripts.
All modules use ONLY stdlib to ensure non-E2EE scripts work without dependencies.

Usage:
    # At the top of each script, add:
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    # Then import what you need:
    from _lib import load_config, matrix_request, find_room_by_name
"""

# Config
from _lib.config import load_config

# HTTP API
from _lib.http import matrix_request

# Room operations
from _lib.rooms import (
    resolve_room_alias,
    get_room_info,
    list_joined_rooms,
    find_room_by_name,
)

# Formatting
from _lib.formatting import (
    shorten_service_urls,
    markdown_to_html,
    add_bot_prefix,
)

# Utilities
from _lib.utils import (
    clean_message,
    format_timestamp,
)

# E2EE (only used by E2EE scripts, but still stdlib-only)
from _lib.e2ee import (
    get_store_path,
    get_credentials_path,
    load_credentials,
    save_credentials,
    delete_credentials,
)

__all__ = [
    # Config
    "load_config",
    # HTTP
    "matrix_request",
    # Rooms
    "resolve_room_alias",
    "get_room_info",
    "list_joined_rooms",
    "find_room_by_name",
    # Formatting
    "shorten_service_urls",
    "markdown_to_html",
    "add_bot_prefix",
    # Utils
    "clean_message",
    "format_timestamp",
    # E2EE
    "get_store_path",
    "get_credentials_path",
    "load_credentials",
    "save_credentials",
    "delete_credentials",
]
