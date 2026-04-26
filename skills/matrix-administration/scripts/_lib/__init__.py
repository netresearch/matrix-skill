"""matrix-administration shared library.

Stdlib only.  At the top of each script:

    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _lib import load_config, admin_request, client_request
"""

from _lib.admin_http import admin_request, client_request, quote
from _lib.colors import bold, cyan, gray, green, red, yellow
from _lib.condensing import Room, condense
from _lib.config import load_config
from _lib.pretty_bytes import pretty_bytes
from _lib.rating import RoomRating, format_rating, rate_room, rating_emoji

__all__ = [
    "admin_request",
    "client_request",
    "quote",
    "bold",
    "cyan",
    "gray",
    "green",
    "red",
    "yellow",
    "Room",
    "condense",
    "load_config",
    "pretty_bytes",
    "RoomRating",
    "format_rating",
    "rate_room",
    "rating_emoji",
]
