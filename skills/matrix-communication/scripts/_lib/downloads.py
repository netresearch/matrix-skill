# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Where a downloaded attachment is written. Stdlib only."""

import os
from pathlib import Path

DEFAULT_NAME = "media_download"


def download_target(directory, name) -> Path:
    """The path a download is saved to: the last component of ``name`` only.

    The name usually comes from the message (its ``body``), so any directory
    part is dropped, and a name that is empty or a directory reference
    (``.``/``..``) is replaced by a fixed one.
    """
    base = Path(name or "").name
    if base in ("", ".", ".."):
        base = DEFAULT_NAME
    return Path(directory) / base


def write_download(path: Path, data: bytes, overwrite: bool = False) -> None:
    """Write ``data`` to ``path`` with mode 0600 without following a symlink.

    An existing file is kept (FileExistsError) unless ``overwrite`` is set.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW
    flags |= os.O_TRUNC if overwrite else os.O_EXCL
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
