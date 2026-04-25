"""Minimal ANSI colour helpers.

Disabled automatically when stdout is not a TTY or ``NO_COLOR`` is set.
"""

from __future__ import annotations

import os
import sys


def _enabled() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


_CODES = {
    "reset": "\x1b[0m",
    "bold": "\x1b[1m",
    "gray": "\x1b[90m",
    "red": "\x1b[31m",
    "green": "\x1b[32m",
    "yellow": "\x1b[33m",
    "blue": "\x1b[34m",
    "magenta": "\x1b[35m",
    "cyan": "\x1b[36m",
}


def _wrap(text: str, name: str) -> str:
    if not _enabled():
        return text
    return f"{_CODES[name]}{text}{_CODES['reset']}"


def bold(text: str) -> str:
    return _wrap(text, "bold")


def gray(text: str) -> str:
    return _wrap(text, "gray")


def red(text: str) -> str:
    return _wrap(text, "red")


def green(text: str) -> str:
    return _wrap(text, "green")


def yellow(text: str) -> str:
    return _wrap(text, "yellow")


def blue(text: str) -> str:
    return _wrap(text, "blue")


def cyan(text: str) -> str:
    return _wrap(text, "cyan")
