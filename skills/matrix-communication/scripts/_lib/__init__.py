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
from _lib.config import get_config_path, load_config

# E2EE (only used by E2EE scripts, but still stdlib-only)
from _lib.daemon_client import daemon_request, socket_path

# Dependency checking
from _lib.deps import check_e2ee_dependencies
from _lib.e2ee import (
    delete_credentials,
    explain_store_error,
    get_credentials_path,
    get_store_path,
    load_credentials,
    restore_login_checked,
    rooms_dir,
    save_credentials,
    store_files_for,
)

# Formatting
from _lib.formatting import (
    add_bot_prefix,
    markdown_to_html,
    shorten_service_urls,
)

# HTTP API
from _lib.http import matrix_request
from _lib.roomlog import (
    append_record,
    build_record,
    cursor_path,
    log_path,
    next_seq,
    read_cursor,
    read_records,
    room_slug,
    summarize_since,
    write_cursor,
)

# Room operations
from _lib.rooms import (
    find_room_by_name,
    find_room_in_nio_client,
    get_room_info,
    list_joined_rooms,
    resolve_room_alias,
    resolve_room_cli,
)

# Utilities
from _lib.utils import (
    clean_message,
    format_timestamp,
    prefer_ipv4,
    suppress_nio_logging,
)

__all__ = [
    "add_bot_prefix",
    "append_record",
    "build_record",
    "check_e2ee_dependencies",
    "clean_message",
    "cursor_path",
    "daemon_request",
    "delete_credentials",
    "explain_store_error",
    "find_room_by_name",
    "find_room_in_nio_client",
    "format_timestamp",
    "get_config_path",
    "get_credentials_path",
    "get_room_info",
    "get_store_path",
    "list_joined_rooms",
    "load_config",
    "load_credentials",
    "log_path",
    "markdown_to_html",
    "matrix_request",
    "next_seq",
    "prefer_ipv4",
    "read_cursor",
    "read_records",
    "resolve_room_alias",
    "resolve_room_cli",
    "restore_login_checked",
    "room_slug",
    "rooms_dir",
    "save_credentials",
    "shorten_service_urls",
    "socket_path",
    "store_files_for",
    "summarize_since",
    "suppress_nio_logging",
    "write_cursor",
]
