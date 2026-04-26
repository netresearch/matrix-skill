"""Human-readable byte-size formatter.

Decimal units by default (``kB``, ``MB``, ``GB`` …); pass ``binary=True``
for IEC units (``KiB``, ``MiB`` …).  Stdlib only.
"""

from __future__ import annotations

_BYTE_UNITS = ["B", "kB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB"]
_BIBYTE_UNITS = ["B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB"]


def pretty_bytes(number: float, binary: bool = False, space: bool = True) -> str:
    """Format ``number`` of bytes with a human-readable unit.

    Examples
    --------
    >>> pretty_bytes(0)
    '0 B'
    >>> pretty_bytes(1500)
    '1.50 kB'
    >>> pretty_bytes(1500, binary=True)
    '1.46 KiB'
    """
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"Expected a finite number, got: {number!r}")

    units = _BIBYTE_UNITS if binary else _BYTE_UNITS
    sep = " " if space else ""

    sign = "-" if number < 0 else ""
    n = abs(number)

    if n < 1:
        return f"{sign}{n:.0f}{sep}{units[0]}"

    base = 1024 if binary else 1000
    exponent = 0
    while n >= base and exponent < len(units) - 1:
        n /= base
        exponent += 1

    if n >= 100:
        formatted = f"{n:.0f}"
    elif n >= 10:
        formatted = f"{n:.1f}"
    else:
        formatted = f"{n:.2f}"

    return f"{sign}{formatted}{sep}{units[exponent]}"
