"""Tests for `_lib.roomlog`.

Run directly: python3 skills/matrix-communication/scripts/_lib/test_roomlog.py

`roomlog` is imported directly, not as `_lib.roomlog`: running this file puts its
own directory on sys.path, where `_lib/http.py` shadows the stdlib `http` package
and breaks `urllib` on the way in.
"""

import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from roomlog import (
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

EVENT = {
    "event_id": "$abc",
    "sender": "@tobias.hein:example.org",
    "sender_display": "tobias.hein",
    "type": "m.text",
    "body": "Ihr seid cool",
    "ts": 1786568100000,
}


def record(seq, **overrides):
    return build_record(
        seq=seq,
        event={**EVENT, **overrides},
        own_user_id=overrides.pop("own_user_id", "@me:example.org"),
        own_display_name="me",
    )


class SlugTests(unittest.TestCase):
    def test_room_id_becomes_shell_safe(self):
        self.assertEqual(room_slug("!IyRWAMq:example.org"), "IyRWAMq_example.org")

    def test_slug_has_no_shell_metacharacters(self):
        slug = room_slug("!a+b/c:example.org")
        self.assertNotIn("!", slug)
        self.assertNotIn("/", slug)
        self.assertNotIn("+", slug)

    def test_distinct_rooms_keep_distinct_slugs(self):
        self.assertNotEqual(room_slug("!a:example.org"), room_slug("!b:example.org"))


class RecordTests(unittest.TestCase):
    def test_record_carries_seq_and_identity(self):
        rec = record(7)
        self.assertEqual(rec["seq"], 7)
        self.assertEqual(rec["event_id"], "$abc")
        self.assertFalse(rec["self"])
        self.assertFalse(rec["mentions_me"])

    def test_own_message_is_flagged(self):
        rec = build_record(
            seq=1,
            event={**EVENT, "sender": "@me:example.org"},
            own_user_id="@me:example.org",
            own_display_name="me",
        )
        self.assertTrue(rec["self"])

    def test_localpart_in_body_counts_as_mention(self):
        rec = build_record(
            seq=1,
            event={**EVENT, "body": "kann sebastian das sehen?"},
            own_user_id="@sebastian:example.org",
            own_display_name=None,
        )
        self.assertTrue(rec["mentions_me"])

    def test_display_name_in_body_counts_as_mention(self):
        rec = build_record(
            seq=1,
            event={**EVENT, "body": "Frag mal Basti"},
            own_user_id="@sebastian:example.org",
            own_display_name="Basti",
        )
        self.assertTrue(rec["mentions_me"])

    def test_substring_of_a_longer_word_is_not_a_mention(self):
        """'Basti' inside 'bastion' must not trigger."""
        rec = build_record(
            seq=1,
            event={**EVENT, "body": "der bastion host"},
            own_user_id="@sebastian:example.org",
            own_display_name="Basti",
        )
        self.assertFalse(rec["mentions_me"])

    def test_text_is_the_display_line(self):
        """Asserted by shape, not by the clock: %H:%M renders in local time, so
        pinning the digits would pass only on the machine that wrote the test."""
        rec = record(1)
        self.assertRegex(rec["text"], r"^\[\d{2}:\d{2}\] tobias\.hein: Ihr seid cool$")

    def test_long_body_is_truncated_in_text_only(self):
        rec = record(1, body="x" * 500)
        self.assertLess(len(rec["text"]), 260)
        self.assertTrue(rec["text"].endswith("…"))
        self.assertEqual(len(rec["body"]), 500)

    def test_newlines_are_folded_into_one_line(self):
        """The reader prints one record per line; a body with newlines must not
        become several lines that no longer parse as one record."""
        rec = record(1, body="erste\nzweite\n\ndritte")
        self.assertNotIn("\n", rec["text"])

    def test_undecryptable_event_still_renders(self):
        rec = record(1, type="encrypted", body=None, session_id="sess1")
        self.assertIn("[unable to decrypt]", rec["text"])
        self.assertEqual(rec["session_id"], "sess1")

    def test_emote_is_marked(self):
        rec = record(1, type="m.emote", body="winkt")
        self.assertIn("* winkt", rec["text"])


class AppendTests(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.path = log_path(self.dir, "!r:example.org")

    def _append(self, count, start=1, **kwargs):
        for i in range(start, start + count):
            append_record(self.path, record(i, event_id=f"$e{i}"), **kwargs)

    def test_next_seq_on_empty_log_is_one(self):
        self.assertEqual(next_seq(self.path), 1)

    def test_next_seq_continues_after_existing_records(self):
        self._append(3)
        self.assertEqual(next_seq(self.path), 4)

    def test_records_round_trip(self):
        self._append(2)
        got = list(read_records(self.path))
        self.assertEqual([r["seq"] for r in got], [1, 2])
        self.assertTrue(got[0]["text"].endswith("tobias.hein: Ihr seid cool"))

    def test_each_record_is_exactly_one_line(self):
        self._append(1)
        self.assertEqual(self.path.read_text().count("\n"), 1)

    def test_a_truncated_final_line_is_skipped_not_fatal(self):
        """A daemon killed mid-write leaves a partial line. The reader must get
        past it rather than dying on the whole log."""
        self._append(2)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write('{"seq": 3, "text": "hal')
        self.assertEqual([r["seq"] for r in read_records(self.path)], [1, 2])

    def test_rotation_keeps_seq_monotonic(self):
        """Rotation must not restart numbering: the cursor subtracts on it."""
        self._append(5)
        append_record(self.path, record(6, event_id="$e6"), max_bytes=10)
        self.assertTrue(self.path.with_name(self.path.name + ".1").exists())
        self.assertEqual(next_seq(self.path), 7)

    def test_unicode_survives_the_round_trip(self):
        append_record(self.path, record(1, body="Grüße 🎁"))
        self.assertIn("Grüße 🎁", next(iter(read_records(self.path)))["body"])


class CursorTests(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.log = log_path(self.dir, "!r:example.org")
        for i in range(1, 6):
            body = "hallo sebastian" if i in (2, 4) else "nichts"
            append_record(
                self.log,
                build_record(
                    seq=i,
                    event={**EVENT, "event_id": f"$e{i}", "body": body},
                    own_user_id="@sebastian:example.org",
                    own_display_name=None,
                ),
            )

    def test_missing_cursor_reads_as_zero(self):
        self.assertEqual(read_cursor(cursor_path(self.dir, "!r:example.org")), 0)

    def test_cursor_round_trips(self):
        path = cursor_path(self.dir, "!r:example.org")
        write_cursor(path, 3)
        self.assertEqual(read_cursor(path), 3)

    def test_named_cursors_are_independent(self):
        a = cursor_path(self.dir, "!r:example.org", "sessionA")
        b = cursor_path(self.dir, "!r:example.org", "sessionB")
        write_cursor(a, 4)
        self.assertNotEqual(a, b)
        self.assertEqual(read_cursor(b), 0)

    def test_summary_counts_total_and_mentions(self):
        summary = summarize_since(self.log, 0)
        self.assertEqual(summary["total"], 5)
        self.assertEqual(summary["mentions"], 2)
        self.assertEqual(summary["last_seq"], 5)
        self.assertFalse(summary["truncated"])

    def test_summary_counts_only_what_is_new(self):
        summary = summarize_since(self.log, 3)
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["mentions"], 1)

    def test_cursor_ahead_of_log_counts_nothing(self):
        self.assertEqual(summarize_since(self.log, 99)["total"], 0)

    def test_gap_older_than_the_log_is_marked_truncated(self):
        """Rotation dropped the records: report a lower bound, not a guess."""
        for i in range(6, 9):
            append_record(
                self.log,
                build_record(
                    seq=i,
                    event={**EVENT, "event_id": f"$e{i}"},
                    own_user_id="@sebastian:example.org",
                    own_display_name=None,
                ),
                max_bytes=1,
            )
        self.assertTrue(summarize_since(self.log, 2)["truncated"])

    def test_a_corrupt_cursor_file_reads_as_zero(self):
        path = cursor_path(self.dir, "!r:example.org")
        path.write_text("not a number")
        self.assertEqual(read_cursor(path), 0)


class JsonShapeTests(unittest.TestCase):
    def test_record_is_json_serialisable(self):
        """Every field has to survive json.dumps or the append silently fails."""
        json.dumps(record(1))


if __name__ == "__main__":
    unittest.main(verbosity=2)
