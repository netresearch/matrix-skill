# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Tests for `_lib.reactions` and the status swap in `matrix-react.py`.

Run directly (stdlib only, no nio):

    python3 skills/matrix-communication/scripts/_lib/test_reactions.py
"""

import importlib.util
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
# The scripts directory, not _lib itself: _lib/http.py would shadow the stdlib
# `http` package that urllib.request imports.
sys.path.insert(0, os.path.dirname(HERE))
if sys.path[1:2] == [HERE]:
    del sys.path[1]  # a direct run puts the file's own directory there

from _lib.reactions import annotations, own_reactions

ME = "@agent:example.org"
TARGET = "$djnY5_1gyZe2Xkk-3xB437F_Sfwr0AaVhcDATMM40pE"

# A relations page as Synapse returned it for a test message carrying two
# reactions of one account (2026-11-04); only the user ID is replaced.
SYNAPSE_PAGE = {
    "chunk": [
        {
            "content": {
                "m.relates_to": {
                    "event_id": TARGET,
                    "key": "\U0001f916",
                    "rel_type": "m.annotation",
                }
            },
            "event_id": "$yBkEG80w7_Mw1QzR9TFPQUSvuOhpHAc1sGtMvevvdq4",
            "room_id": "!CkTNagkkIFSndMzpdc:netresearch.de",
            "sender": ME,
            "type": "m.reaction",
            "unsigned": {"membership": "join"},
        },
        {
            "content": {
                "m.relates_to": {
                    "event_id": TARGET,
                    "key": "▶️",
                    "rel_type": "m.annotation",
                }
            },
            "event_id": "$aSpdQ3N6_FzzWuJsjvf2VYSueIFWDmXOGJBSoSTbhzc",
            "room_id": "!CkTNagkkIFSndMzpdc:netresearch.de",
            "sender": ME,
            "type": "m.reaction",
            "unsigned": {"membership": "join"},
        },
    ]
}


def reaction(event_id, key, sender=ME, type_="m.reaction", **unsigned):
    return {
        "event_id": event_id,
        "sender": sender,
        "type": type_,
        "content": {"m.relates_to": {"rel_type": "m.annotation", "key": key}},
        "unsigned": unsigned,
    }


class OwnReactionsTest(unittest.TestCase):
    def test_synapse_page_yields_the_status_reaction(self):
        found = own_reactions(SYNAPSE_PAGE["chunk"], ME, {"▶️", "✅"})
        self.assertEqual(
            found,
            [{"event_id": "$aSpdQ3N6_FzzWuJsjvf2VYSueIFWDmXOGJBSoSTbhzc", "key": "▶️"}],
        )

    def test_other_senders_are_ignored(self):
        events = [reaction("$a", "x", sender="@human:example.org")]
        self.assertEqual(own_reactions(events, ME, {"x"}), [])

    def test_encrypted_reaction_counts(self):
        # m.relates_to stays in clear text on an encrypted event.
        events = [reaction("$a", "x", type_="m.room.encrypted")]
        self.assertEqual(
            own_reactions(events, ME, {"x"}), [{"event_id": "$a", "key": "x"}]
        )

    def test_redacted_reaction_is_skipped(self):
        events = [reaction("$a", "x", redacted_because={"type": "m.room.redaction"})]
        self.assertEqual(own_reactions(events, ME, {"x"}), [])

    def test_other_relation_types_are_skipped(self):
        event = reaction("$a", "x")
        event["content"]["m.relates_to"]["rel_type"] = "m.thread"
        self.assertEqual(own_reactions([event], ME, {"x"}), [])


class AnnotationsTest(unittest.TestCase):
    def test_follows_next_batch(self):
        pages = {
            None: {"chunk": [reaction("$a", "x")], "next_batch": "t/2"},
            "t%2F2": {"chunk": [reaction("$b", "y")]},
        }
        seen = []

        def request(path):
            seen.append(path)
            token = path.split("&from=")[1] if "&from=" in path else None
            return pages[token]

        events = annotations(request, "!room:example.org", "$ev")
        self.assertEqual([e["event_id"] for e in events], ["$a", "$b"])
        self.assertIn("/relations/%24ev/m.annotation?limit=100", seen[0])

    def test_error_is_returned_not_swallowed(self):
        # A failed lookup must never read as "no reactions there".
        result = annotations(lambda path: {"error": "boom"}, "!r", "$e")
        self.assertEqual(result, {"error": "boom"})

    def test_endless_paging_stops(self):
        result = annotations(
            lambda path: {"chunk": [], "next_batch": "again"}, "!r", "$e"
        )
        self.assertIn("error", result)


def load_react():
    spec = importlib.util.spec_from_file_location(
        "matrix_react", os.path.join(os.path.dirname(HERE), "matrix-react.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ApplyReactionTest(unittest.TestCase):
    """The swap order: new status first, old ones after, never twice."""

    def setUp(self):
        self.react = load_react()
        self.calls = []
        self.existing = []
        self.react.find_own = lambda config, room, event, keys: [
            r for r in self.existing if r["key"] in keys
        ]
        self.react.send_reaction = lambda config, room, event, key, trust=False: (
            self.calls.append(("send", key)) or {"event_id": f"$new-{key}"}
        )
        self.react.redact_reaction = lambda config, room, rid: (
            self.calls.append(("redact", rid)) or {"event_id": "$redaction"}
        )

    def apply(self, emoji, replace=(), remove=False):
        return self.react.apply_reaction({}, "!r", "$e", emoji, list(replace), remove)

    def test_swap_sends_new_then_redacts_old(self):
        self.existing = [
            {"event_id": "$old", "key": "A"},
            {"event_id": "$bot", "key": "R"},
        ]
        result = self.apply("B", replace=["A", "C"])
        self.assertEqual(self.calls, [("send", "B"), ("redact", "$old")])
        self.assertEqual(result, {"event_id": "$new-B", "removed": ["A"]})

    def test_existing_status_is_not_sent_again(self):
        self.existing = [{"event_id": "$have", "key": "B"}]
        result = self.apply("B", replace=["A"])
        self.assertEqual(self.calls, [])
        self.assertEqual(result["event_id"], "$have")

    def test_new_emoji_in_replace_list_is_kept(self):
        self.existing = [{"event_id": "$have", "key": "B"}]
        self.apply("B", replace=["A", "B"])
        self.assertEqual(self.calls, [])

    def test_failed_send_leaves_old_status(self):
        self.existing = [{"event_id": "$old", "key": "A"}]
        self.react.send_reaction = lambda *a, **k: {"error": "refused"}
        result = self.apply("B", replace=["A"])
        self.assertEqual(result, {"error": "refused"})
        self.assertEqual(self.calls, [])

    def test_remove_redacts_only_that_emoji(self):
        self.existing = [
            {"event_id": "$x", "key": "A"},
            {"event_id": "$bot", "key": "R"},
        ]
        result = self.apply("A", remove=True)
        self.assertEqual(self.calls, [("redact", "$x")])
        self.assertEqual(result, {"event_id": None, "removed": ["A"]})

    def test_failed_lookup_sends_nothing(self):
        self.react.find_own = lambda *a: {"error": "403"}
        result = self.apply("B", replace=["A"])
        self.assertIn("error", result)
        self.assertEqual(self.calls, [])

    def test_plain_react_skips_the_lookup(self):
        self.react.find_own = lambda *a: self.fail("plain react must not look up")
        self.apply("B")
        self.assertEqual(self.calls, [("send", "B")])


if __name__ == "__main__":
    unittest.main()
