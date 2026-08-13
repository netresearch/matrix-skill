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
    SUBJECT_LIMIT,
    append_record,
    build_record,
    cursor_path,
    excerpt,
    log_path,
    next_seq,
    read_cursor,
    read_records,
    remember_subject,
    room_slug,
    subject_index,
    summarize_since,
    target_of,
    write_cursor,
    write_room_bundle,
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


class RoomBundleTests(unittest.TestCase):
    """The bundle is OKF: typed frontmatter per room, an index without any."""

    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        write_room_bundle(
            self.dir,
            {"!a:example.org": "#ops:example.org", "!b:example.org": "#it:example.org"},
        )

    def test_one_file_per_room(self):
        self.assertTrue((self.dir / "a_example.org.md").exists())
        self.assertTrue((self.dir / "b_example.org.md").exists())

    def test_room_page_carries_the_mandatory_type(self):
        text = (self.dir / "a_example.org.md").read_text()
        self.assertTrue(text.startswith("---\n"))
        self.assertIn("type: matrix-room", text)

    def test_room_page_carries_the_recommended_fields(self):
        text = (self.dir / "a_example.org.md").read_text()
        for field in ("title:", "description:", "resource:", "tags:", "timestamp:"):
            self.assertIn(field, text)

    def test_index_has_no_frontmatter(self):
        """OKF: 'an index.md contains no frontmatter'."""
        text = (self.dir / "index.md").read_text()
        self.assertFalse(text.startswith("---"))

    def test_index_lists_every_room_with_its_description(self):
        text = (self.dir / "index.md").read_text()
        self.assertIn("(a_example.org.md)", text)
        self.assertIn("(b_example.org.md)", text)
        self.assertIn("watched by matrix-watchd", text)

    def test_rewriting_the_bundle_does_not_duplicate_entries(self):
        write_room_bundle(self.dir, {"!a:example.org": "#ops:example.org"})
        text = (self.dir / "index.md").read_text()
        self.assertEqual(text.count("(a_example.org.md)"), 1)
        self.assertNotIn("(b_example.org.md)", text)


class SelfIsTheDeviceTests(unittest.TestCase):
    """`self` has to mean "this device", not "this account".

    Regression for #93: an agent and the person it works for share one Matrix
    account, so comparing the sender alone marks the human's messages as the
    agent's own. An agent that skips its own messages then skips the person
    addressing it; one that does not risks answering itself.
    """

    MINE = "curve25519-of-my-device"
    THEIRS = "curve25519-of-their-element"
    USER = "@shared:example.org"

    def _record(self, sender_key, **extra):
        return build_record(
            seq=1,
            event={**EVENT, "sender": self.USER, "sender_key": sender_key, **extra},
            own_user_id=self.USER,
            own_display_name=None,
            own_sender_key=self.MINE,
        )

    def test_our_own_device_is_self(self):
        rec = self._record(self.MINE)
        self.assertTrue(rec["self"])
        self.assertEqual(rec["self_basis"], "device")

    def test_the_humans_device_on_the_same_account_is_not_self(self):
        rec = self._record(self.THEIRS)
        self.assertFalse(rec["self"])
        self.assertEqual(rec["self_basis"], "device")

    def test_another_account_is_never_self(self):
        rec = build_record(
            seq=1,
            event={**EVENT, "sender": "@someone:example.org", "sender_key": self.MINE},
            own_user_id=self.USER,
            own_display_name=None,
            own_sender_key=self.MINE,
        )
        self.assertFalse(rec["self"])

    def test_without_a_sender_key_it_falls_back_to_the_account_and_says_so(self):
        """An unencrypted room carries no sender_key. The account comparison is
        then the only answer available, and the record must not pretend it is
        the device one."""
        rec = build_record(
            seq=1,
            event={**EVENT, "sender": self.USER},
            own_user_id=self.USER,
            own_display_name=None,
            own_sender_key=self.MINE,
        )
        self.assertTrue(rec["self"])
        self.assertEqual(rec["self_basis"], "account")

    def test_without_our_own_key_it_falls_back_too(self):
        rec = build_record(
            seq=1,
            event={**EVENT, "sender": self.USER, "sender_key": self.THEIRS},
            own_user_id=self.USER,
            own_display_name=None,
            own_sender_key=None,
        )
        self.assertTrue(rec["self"])
        self.assertEqual(rec["self_basis"], "account")

    def test_own_device_lines_are_marked_in_the_text(self):
        """The log is read by the agent that wrote half of it."""
        mine = self._record(self.MINE)
        theirs = self._record(self.THEIRS)
        self.assertIn("(agent)", mine["text"])
        self.assertNotIn("(agent)", theirs["text"])


class DisplayNameFallbackTests(unittest.TestCase):
    """Regression for #92: an unknown display name showed the whole MXID.

    Line width is what makes a busy room affordable to follow, and
    `@bjoern.marten:netresearch.de` costs 18 characters more than the name it
    stands for. Member state arrives lazily in large rooms, so "no display name
    yet" is the normal case there, not an edge one.
    """

    def test_display_name_is_used_when_known(self):
        rec = record(1, sender_display="Björn Marten")
        self.assertIn("Björn Marten:", rec["text"])

    def test_unknown_display_name_falls_back_to_the_localpart(self):
        rec = record(1, sender="@bjoern.marten:netresearch.de", sender_display=None)
        self.assertIn("bjoern.marten:", rec["text"])
        self.assertNotIn("@bjoern.marten:netresearch.de", rec["text"])

    def test_the_full_mxid_stays_in_the_record(self):
        """Only the rendered line is shortened - the data keeps the identity."""
        rec = record(1, sender="@bjoern.marten:netresearch.de", sender_display=None)
        self.assertEqual(rec["sender"], "@bjoern.marten:netresearch.de")


REACTED_TO = "$target"
REACTION = {
    "event_id": "$reaction",
    "sender": "@sebastian.mendel:example.org",
    "sender_display": "Sebastian Mendel",
    "type": "reaction",
    "body": "\u2705",
    "ts": 1786568100000,
    "relates_to": REACTED_TO,
}
REDACTION = {
    "event_id": "$redaction",
    "sender": "@sebastian.mendel:example.org",
    "sender_display": "Sebastian Mendel",
    "type": "redaction",
    "body": None,
    "ts": 1786568100000,
    "redacts": REACTED_TO,
}


class ExcerptTests(unittest.TestCase):
    def test_newlines_are_folded(self):
        self.assertEqual(excerpt("zwei\nzeilen"), "zwei zeilen")

    def test_long_body_is_truncated_to_the_limit(self):
        self.assertEqual(len(excerpt("x" * 200)), SUBJECT_LIMIT)

    def test_short_body_is_untouched(self):
        self.assertEqual(excerpt("so bin beim RA"), "so bin beim RA")

    def test_missing_body_is_empty_not_an_error(self):
        self.assertEqual(excerpt(None), "")


class RelationTargetTests(unittest.TestCase):
    """What a reaction reacts to and what a redaction redacted."""

    def _rec(self, event, subject=None):
        return build_record(
            seq=1,
            event=event,
            own_user_id="@me:example.org",
            own_display_name="me",
            subject=subject,
        )

    def test_reaction_keeps_its_target(self):
        self.assertEqual(self._rec(REACTION)["relates_to"], REACTED_TO)

    def test_redaction_keeps_its_target(self):
        self.assertEqual(self._rec(REDACTION)["redacts"], REACTED_TO)

    def test_redaction_keeps_its_reason(self):
        rec = self._rec({**REDACTION, "reason": "Tippfehler"})
        self.assertEqual(rec["reason"], "Tippfehler")

    def test_a_plain_message_gains_no_relation_keys(self):
        """The keys are conditional, like session_id - no always-null columns."""
        rec = record(1)
        self.assertNotIn("relates_to", rec)
        self.assertNotIn("redacts", rec)
        self.assertNotIn("reason", rec)

    def test_target_of_reads_either_relation(self):
        self.assertEqual(target_of(self._rec(REACTION)), REACTED_TO)
        self.assertEqual(target_of(self._rec(REDACTION)), REACTED_TO)

    def test_target_of_is_none_for_a_plain_message(self):
        self.assertIsNone(target_of(record(1)))

    def test_reaction_line_names_the_message(self):
        rec = self._rec(REACTION, subject="so bin beim RA")
        self.assertIn('reacted \u2705 to "so bin beim RA"', rec["text"])

    def test_redaction_line_names_the_message(self):
        rec = self._rec(REDACTION, subject="so bin beim RA")
        self.assertIn('removed "so bin beim RA"', rec["text"])

    def test_redaction_line_appends_the_reason(self):
        rec = self._rec({**REDACTION, "reason": "Tippfehler"}, subject="ups")
        self.assertIn('removed "ups" (Tippfehler)', rec["text"])

    def test_unresolvable_target_falls_back_instead_of_printing_an_id(self):
        """An event id in the line identifies the target to nobody reading."""
        for event, expected in (
            (REACTION, "reacted \u2705"),
            (REDACTION, "removed a message"),
        ):
            with self.subTest(type=event["type"]):
                text = self._rec(event)["text"]
                self.assertTrue(text.endswith(expected), text)
                self.assertNotIn(REACTED_TO, text)

    def test_two_redactions_of_different_messages_read_differently(self):
        """The case this was built for.

        Two reactions and two redactions from one sender, seconds apart, used to
        render as four interchangeable lines - so a reader concluded the sender
        had taken back what they had just set. They had not.
        """
        first = self._rec({**REDACTION, "redacts": "$one"}, subject="erste Nachricht")
        second = self._rec({**REDACTION, "redacts": "$two"}, subject="zweite Nachricht")
        self.assertNotEqual(first["text"], second["text"])
        self.assertNotEqual(first["redacts"], second["redacts"])


class SubjectIndexTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = pathlib.Path(self.dir.name) / "room.jsonl"

    def test_index_resolves_a_body_written_earlier(self):
        append_record(self.path, record(1, event_id="$one", body="so bin beim RA"))
        self.assertEqual(subject_index(self.path)["$one"], "so bin beim RA")

    def test_bodiless_events_are_not_indexed(self):
        append_record(self.path, record(1, event_id="$r", type="redaction", body=None))
        self.assertEqual(subject_index(self.path), {})

    def test_index_survives_a_restart(self):
        """A daemon restarted mid-conversation still names the target."""
        append_record(self.path, record(1, event_id="$one", body="so bin beim RA"))
        index = subject_index(self.path)
        rec = build_record(
            seq=2,
            event={**REACTION, "relates_to": "$one"},
            own_user_id="@me:example.org",
            own_display_name="me",
            subject=index.get("$one"),
        )
        self.assertIn('to "so bin beim RA"', rec["text"])

    def test_the_index_is_bounded_and_drops_the_oldest(self):
        index = {}
        for n in range(5):
            remember_subject(index, record(n, event_id=f"$e{n}", body=f"m{n}"), limit=3)
        self.assertEqual(len(index), 3)
        self.assertNotIn("$e0", index)
        self.assertIn("$e4", index)


if __name__ == "__main__":
    unittest.main(verbosity=2)
