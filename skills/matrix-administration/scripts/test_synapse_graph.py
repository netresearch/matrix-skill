# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Tests for synapse-graph.py: room-supplied text stays inside its DOT string.

Run directly (stdlib only):

    python3 skills/matrix-administration/scripts/test_synapse_graph.py
"""

import importlib.util
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from _lib.condensing import Room

_spec = importlib.util.spec_from_file_location(
    "synapse_graph", os.path.join(HERE, "synapse-graph.py")
)
synapse_graph = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(synapse_graph)

# A double quote not preceded by a backslash would end the DOT string.
UNESCAPED_QUOTE = re.compile(r'(?<!\\)"')


class NodeLabelTests(unittest.TestCase):
    def test_space_names_in_the_join_policy_are_escaped(self):
        space = Room(id="!space:example.org", name='Ops", fillcolor="red', version=10)
        room = Room(
            id="!room:example.org",
            name="Room",
            version=10,
            join_policy=("in-space", [space.id]),
        )
        label = synapse_graph.node_label(room, {space.id: space, room.id: room})
        self.assertIn("members of Ops", label)
        self.assertIsNone(UNESCAPED_QUOTE.search(label), label)

    def test_room_name_creator_and_version_are_escaped(self):
        room = Room(
            id="!room:example.org",
            name='Na"me\\',
            version='1"',
            creator='@a"b:example.org',
            join_policy="invite-only",
        )
        label = synapse_graph.node_label(room, {room.id: room})
        self.assertIsNone(UNESCAPED_QUOTE.search(label.replace("\\\\", "")), label)


if __name__ == "__main__":
    unittest.main(verbosity=2)
