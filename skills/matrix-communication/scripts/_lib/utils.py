"""Utility functions for Matrix scripts.

All functions use ONLY stdlib.
"""

from datetime import datetime


def clean_message(message: str) -> str:
    """Clean message from bash escaping artifacts.

    Bash history expansion in interactive shells can escape ! to \\!
    when using double quotes. This removes those artifacts.
    """
    # Remove backslash before ! (bash history expansion artifact)
    return message.replace('\\!', '!')


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
