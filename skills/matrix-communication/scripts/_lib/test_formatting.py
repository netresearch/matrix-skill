"""Tests for `_lib.formatting` markdown→HTML conversion.

The skill directory contains a hyphen (`matrix-communication`) so it is
not importable as a Python package; run the file directly or use unittest
discovery:

    python3 skills/matrix-communication/scripts/_lib/test_formatting.py
    python3 -m unittest discover \\
        -s skills/matrix-communication/scripts/_lib -p 'test_formatting.py'

Stdlib only.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))

from formatting import markdown_to_html, shorten_service_urls  # noqa: E402


class ShortenServiceUrlsTests(unittest.TestCase):
    def test_jira_bare_url_is_shortened(self):
        out = shorten_service_urls("see https://jira.example.com/browse/PROJ-42")
        self.assertIn("[PROJ-42](https://jira.example.com/browse/PROJ-42)", out)

    def test_gitlab_bare_url_is_shortened(self):
        out = shorten_service_urls(
            "see https://gitlab.example.com/grp/proj/-/merge_requests/7"
        )
        self.assertIn(
            "[grp/proj#7](https://gitlab.example.com/grp/proj/-/merge_requests/7)",
            out,
        )

    def test_existing_gitlab_markdown_link_is_preserved(self):
        """Regression: pre-wrapped markdown links must NOT be re-wrapped.

        Before the fix this produced `[mytext]([grp/proj#7](url))` which
        confused the link parser and leaked literal `)` into the rendered
        message.
        """
        src = "[mytext](https://gitlab.example.com/grp/proj/-/merge_requests/7) — note"
        out = shorten_service_urls(src)
        self.assertEqual(out, src)

    def test_existing_jira_markdown_link_is_preserved(self):
        src = "[NRS-1](https://jira.example.com/browse/NRS-1) — note"
        out = shorten_service_urls(src)
        self.assertEqual(out, src)

    def test_existing_github_markdown_link_is_preserved(self):
        src = "[my pr](https://github.com/owner/repo/pull/9) — note"
        out = shorten_service_urls(src)
        self.assertEqual(out, src)

    def test_mixed_protected_and_bare_urls(self):
        src = (
            "see [my mr](https://gitlab.example.com/grp/proj/-/merge_requests/7) "
            "and https://gitlab.example.com/grp/proj/-/issues/12"
        )
        out = shorten_service_urls(src)
        # First link untouched
        self.assertIn(
            "[my mr](https://gitlab.example.com/grp/proj/-/merge_requests/7)", out
        )
        # Second link auto-shortened
        self.assertIn(
            "[grp/proj#12](https://gitlab.example.com/grp/proj/-/issues/12)", out
        )

    def test_forged_placeholder_does_not_raise(self):
        """A user-supplied `\\x00MDLINK<n>\\x00` sequence must not crash the
        restore step with IndexError. Unknown placeholders are left as-is."""
        # No real markdown link in the input, but a forged placeholder is.
        src = "literal placeholder \x00MDLINK99\x00 should pass through"
        out = shorten_service_urls(src)
        self.assertIn("\x00MDLINK99\x00", out)


class MarkdownToHtmlListTests(unittest.TestCase):
    def test_dash_bullets_render_as_ul(self):
        html = markdown_to_html("- one\n- two")
        self.assertIn("<ul>", html)
        self.assertIn("<li>one</li>", html)
        self.assertIn("<li>two</li>", html)

    def test_asterisk_bullets_render_as_ul(self):
        """Regression: `* ` bullets must render as a list, not as italic."""
        html = markdown_to_html("* one\n* two")
        self.assertIn("<ul>", html)
        self.assertIn("<li>one</li>", html)
        self.assertIn("<li>two</li>", html)
        self.assertNotIn("<em>", html)

    def test_plus_bullets_render_as_ul(self):
        html = markdown_to_html("+ one\n+ two")
        self.assertIn("<ul>", html)
        self.assertIn("<li>one</li>", html)
        self.assertIn("<li>two</li>", html)

    def test_asterisk_bullet_with_inline_italic(self):
        """A bullet line may still contain an italic span elsewhere."""
        html = markdown_to_html("* item *emph* tail")
        self.assertIn("<li>item <em>emph</em> tail</li>", html)

    def test_asterisk_inside_word_still_italicises(self):
        """Mid-line `*pairs*` still emit <em>."""
        html = markdown_to_html("hello *world*")
        self.assertIn("<em>world</em>", html)


class EmphasisFlankingTests(unittest.TestCase):
    """CommonMark left/right-flanking rules for `*…*`, `**…**`, `~~…~~`.

    Opening delimiter must NOT be followed by whitespace; closing delimiter
    must NOT be preceded by whitespace. Without these guards the italic
    regex used to swallow bullet `*` markers and produce broken output.
    """

    def test_italic_open_followed_by_space_does_not_match(self):
        # `*` immediately followed by space is not a valid italic opener.
        html = markdown_to_html("* one and *two*")
        self.assertNotIn("<em> one and </em>", html)
        self.assertIn("<em>two</em>", html)

    def test_italic_close_preceded_by_space_does_not_match(self):
        # `*` immediately preceded by space is not a valid italic closer.
        html = markdown_to_html("a *foo *bar")
        self.assertNotIn("<em>foo </em>", html)

    def test_bold_open_followed_by_space_does_not_match(self):
        html = markdown_to_html("** not bold ** but **bold**")
        self.assertNotIn("<strong> not bold </strong>", html)
        self.assertIn("<strong>bold</strong>", html)

    def test_strikethrough_open_followed_by_space_does_not_match(self):
        html = markdown_to_html("~~ not strike ~~ but ~~strike~~")
        self.assertNotIn("<del> not strike </del>", html)
        self.assertIn("<del>strike</del>", html)

    def test_italic_single_char(self):
        # `*x*` is a valid italic: opener followed by non-ws, closer
        # preceded by non-ws.
        html = markdown_to_html("*x*")
        self.assertIn("<em>x</em>", html)


class MarkdownToHtmlLinkTests(unittest.TestCase):
    def test_pre_wrapped_gitlab_link_renders_clean_anchor(self):
        """Regression: no stray `)` after the anchor."""
        src = "[my mr](https://gitlab.example.com/grp/proj/-/merge_requests/7)"
        html = markdown_to_html(src)
        self.assertIn(
            '<a href="https://gitlab.example.com/grp/proj/-/merge_requests/7">'
            "my mr</a>",
            html,
        )
        # Critical: no leaked closing paren after the anchor
        self.assertNotIn("</a>)", html)

    def test_pre_wrapped_jira_link_renders_clean_anchor(self):
        src = "[NRS-1](https://jira.example.com/browse/NRS-1)"
        html = markdown_to_html(src)
        self.assertIn('<a href="https://jira.example.com/browse/NRS-1">NRS-1</a>', html)
        self.assertNotIn("</a>)", html)

    def test_bullet_list_with_pre_wrapped_links(self):
        """End-to-end regression: a bullet list of pre-wrapped GitLab + Jira
        links must produce a clean `<ul><li><a>…</a></li>…</ul>` tree, with
        the pre-wrapped link text preserved (not replaced by the auto-shortener).
        """
        src = (
            "- [proj#7](https://gitlab.example.com/grp/proj/-/merge_requests/7) "
            "— note ([NRS-1](https://jira.example.com/browse/NRS-1))\n"
            "- [proj#8](https://gitlab.example.com/grp/proj/-/merge_requests/8)"
        )
        html = markdown_to_html(src)
        self.assertIn("<ul>", html)
        # Caller-provided link text preserved (would have been clobbered to
        # `grp/proj#7` by the broken auto-shortener)
        self.assertIn(
            '<a href="https://gitlab.example.com/grp/proj/-/merge_requests/7">'
            "proj#7</a>",
            html,
        )
        self.assertIn('<a href="https://jira.example.com/browse/NRS-1">NRS-1</a>', html)
        # No nested `[…](…)` artefacts (the symptom of broken re-wrapping)
        self.assertNotIn("[", html)
        self.assertNotIn("](", html)
        # Sanity: no leftover bullet asterisks (would mean inline ate the bullet)
        self.assertNotIn("<li>*", html)


if __name__ == "__main__":
    unittest.main()
