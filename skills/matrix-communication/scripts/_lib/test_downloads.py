# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Tests for `_lib.downloads`: a download never replaces an existing file unasked.

Run directly (stdlib only):

    python3 skills/matrix-communication/scripts/_lib/test_downloads.py
"""

import os
import pathlib
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from downloads import DEFAULT_NAME, download_target, write_download


class DownloadTargetTests(unittest.TestCase):
    def test_directory_parts_of_the_name_are_dropped(self):
        self.assertEqual(
            download_target("out", "../../etc/x.png"), pathlib.Path("out/x.png")
        )

    def test_empty_and_directory_names_are_replaced(self):
        for name in ("", ".", "..", None, "a/.."):
            self.assertEqual(
                download_target("out", name), pathlib.Path("out") / DEFAULT_NAME, name
            )


class WriteDownloadTests(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)

    def test_new_file_is_written_owner_only(self):
        target = self.dir / "a.bin"
        write_download(target, b"data")
        self.assertEqual(target.read_bytes(), b"data")
        self.assertEqual(os.stat(target).st_mode & 0o777, 0o600)

    def test_existing_file_is_kept(self):
        target = self.dir / "a.bin"
        target.write_bytes(b"mine")
        with self.assertRaises(FileExistsError):
            write_download(target, b"theirs")
        self.assertEqual(target.read_bytes(), b"mine")

    def test_existing_file_replaced_with_overwrite(self):
        target = self.dir / "a.bin"
        target.write_bytes(b"mine")
        write_download(target, b"new", overwrite=True)
        self.assertEqual(target.read_bytes(), b"new")

    def test_symlink_is_not_followed_even_with_overwrite(self):
        elsewhere = self.dir / "elsewhere"
        elsewhere.write_bytes(b"untouched")
        link = self.dir / "a.bin"
        link.symlink_to(elsewhere)
        for overwrite in (False, True):
            with self.assertRaises(OSError):
                write_download(link, b"x", overwrite=overwrite)
        self.assertEqual(elsewhere.read_bytes(), b"untouched")


if __name__ == "__main__":
    unittest.main(verbosity=2)
