"""Utility functions for Matrix scripts.

All functions use ONLY stdlib.
"""

import logging
import socket
from datetime import datetime


def clean_message(message: str) -> str:
    """Clean message from bash escaping artifacts.

    Bash history expansion in interactive shells can escape ! to \\!
    when using double quotes. This removes those artifacts.
    """
    # Remove backslash before ! (bash history expansion artifact)
    return message.replace("\\!", "!")


def prefer_ipv4():
    """Monkey-patch socket.getaddrinfo to prefer IPv4 results.

    Workaround for WSL2 environments where IPv6 routes are often
    unreachable while IPv4 works fine.  Call once at script startup.
    """
    _orig = socket.getaddrinfo
    socket.getaddrinfo = lambda *a, **kw: sorted(
        _orig(*a, **kw), key=lambda r: r[0] != socket.AF_INET
    )


def suppress_nio_logging():
    """Suppress noisy matrix-nio crypto/sync warnings.

    Sets nio and peewee loggers to ERROR level to hide megolm session
    warnings that clutter output during normal operation.
    """
    for name in ("nio", "nio.crypto", "nio.responses", "peewee"):
        logging.getLogger(name).setLevel(logging.ERROR)


def format_timestamp(ts: int) -> str:
    """Format Matrix timestamp to readable string.

    Args:
        ts: Unix timestamp in milliseconds

    Returns:
        Formatted string like "2024-01-15 14:30"
    """
    if ts == 0:
        return "unknown"
    dt = datetime.fromtimestamp(ts / 1000)
    return dt.strftime("%Y-%m-%d %H:%M")
