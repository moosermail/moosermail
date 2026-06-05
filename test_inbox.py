#!/usr/bin/env python3
"""
Unit tests for inbox.py (moosermail CLI).
Run: python -m pytest test_inbox.py -v
No external dependencies required.
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

# inbox.py is a module, not a package
sys.path.insert(0, os.path.dirname(__file__))
import inbox


class TestConfigParsing(unittest.TestCase):
    """Tests for _parse_ini, load_config, save_config."""

    def _write(self, tmp, content):
        path = os.path.join(tmp, "config")
        with open(path, "w") as f:
            f.write(content)
        return path

    def test_parse_ini_empty_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "")
            result = inbox._parse_ini(path)
            self.assertEqual(result, {})

    def test_parse_ini_flat_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, 'from_address = "me@example.com"\nlist_limit = "25"\n')
            result = inbox._parse_ini(path)
            self.assertIn(None, result)
            self.assertEqual(result[None]["from_address"], "me@example.com")
            self.assertEqual(result[None]["list_limit"], "25")

    def test_parse_ini_single_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "[default]\nfrom_address = \"me@example.com\"\n")
            result = inbox._parse_ini(path)
            self.assertIn("default", result)
            self.assertEqual(result["default"]["from_address"], "me@example.com")

    def test_parse_ini_multiple_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            content = (
                "[default]\n"
                "from_address = \"default@example.com\"\n"
                "\n"
                "[work]\n"
                "from_address = \"work@company.com\"\n"
                "list_limit = \"100\"\n"
            )
            path = self._write(tmp, content)
            result = inbox._parse_ini(path)
            self.assertEqual(result["default"]["from_address"], "default@example.com")
            self.assertEqual(result["work"]["from_address"], "work@company.com")
            self.assertEqual(result["work"]["list_limit"], "100")

    def test_parse_ini_ignores_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "# this is a comment\n[default]\n# another comment\nfrom_address = \"a@b.com\"\n")
            result = inbox._parse_ini(path)
            self.assertNotIn(None, result)
            self.assertEqual(result["default"]["from_address"], "a@b.com")

    def test_parse_ini_missing_file(self):
        result = inbox._parse_ini("/nonexistent/path/config.conf")
        self.assertEqual(result, {})


class TestLoadSaveConfig(unittest.TestCase):
    """Tests for load_config and save_config with profile support."""

    def setUp(self):
        self.tmp    = tempfile.TemporaryDirectory()
        self.conf   = os.path.join(self.tmp.name, "test.conf")
        self._orig_file    = inbox.CONFIG_FILE
        self._orig_profile = inbox.PROFILE
        inbox.CONFIG_FILE  = self.conf

    def tearDown(self):
        inbox.CONFIG_FILE = self._orig_file
        inbox.PROFILE     = self._orig_profile
        self.tmp.cleanup()

    def test_load_defaults_when_no_file(self):
        cfg = inbox.load_config("default")
        self.assertEqual(cfg["list_limit"], "50")
        self.assertEqual(cfg["from_address"], "")

    def test_save_and_load_default_profile(self):
        inbox.PROFILE = "default"
        inbox.save_config({"from_address": "a@b.com", "list_limit": "25", "app_name": "TEST"})
        cfg = inbox.load_config("default")
        self.assertEqual(cfg["from_address"], "a@b.com")
        self.assertEqual(cfg["list_limit"], "25")

    def test_save_and_load_named_profile(self):
        inbox.PROFILE = "work"
        inbox.save_config({"from_address": "work@corp.com", "list_limit": "100", "app_name": "WORK"})
        inbox.PROFILE = "default"
        inbox.save_config({"from_address": "me@home.com", "list_limit": "50", "app_name": "HOME"})

        cfg_work = inbox.load_config("work")
        cfg_def  = inbox.load_config("default")
        self.assertEqual(cfg_work["from_address"], "work@corp.com")
        self.assertEqual(cfg_def["from_address"], "me@home.com")

    def test_named_profile_falls_back_to_default_keys(self):
        inbox.PROFILE = "default"
        inbox.save_config({"from_address": "base@example.com", "list_limit": "30", "app_name": "BASE"})
        inbox.PROFILE = "work"
        inbox.save_config({"from_address": "work@example.com", "list_limit": "30", "app_name": "BASE"})

        cfg = inbox.load_config("work")
        self.assertEqual(cfg["from_address"], "work@example.com")

    def test_flat_config_migrates_to_default_section(self):
        with open(self.conf, "w") as f:
            f.write('from_address = "flat@example.com"\nlist_limit = "77"\n')
        cfg = inbox.load_config("default")
        self.assertEqual(cfg["from_address"], "flat@example.com")
        self.assertEqual(cfg["list_limit"], "77")

    def test_save_preserves_other_profiles(self):
        inbox.PROFILE = "alpha"
        inbox.save_config({"from_address": "alpha@x.com", "list_limit": "10", "app_name": "A"})
        inbox.PROFILE = "beta"
        inbox.save_config({"from_address": "beta@x.com", "list_limit": "20", "app_name": "B"})
        inbox.PROFILE = "alpha"
        inbox.save_config({"from_address": "alpha2@x.com", "list_limit": "10", "app_name": "A"})

        self.assertEqual(inbox.load_config("beta")["from_address"], "beta@x.com")
        self.assertEqual(inbox.load_config("alpha")["from_address"], "alpha2@x.com")


class TestFmtDate(unittest.TestCase):
    """Tests for fmt_date relative time formatting."""

    def _make_ts(self, delta_seconds):
        from datetime import datetime, timezone, timedelta
        dt = datetime.now(timezone.utc) - timedelta(seconds=delta_seconds)
        return dt.isoformat()

    def test_minutes_ago(self):
        ts     = self._make_ts(300)   # 5 minutes ago
        result = inbox.fmt_date(ts)
        self.assertRegex(result, r"^\d+m$")

    def test_hours_ago(self):
        ts     = self._make_ts(7200)  # 2 hours ago
        result = inbox.fmt_date(ts)
        self.assertRegex(result, r"^\d+h$")

    def test_yesterday(self):
        ts     = self._make_ts(86400 + 3600)  # ~25 hours ago
        result = inbox.fmt_date(ts)
        self.assertEqual(result, "yest")

    def test_days_ago(self):
        ts     = self._make_ts(3 * 86400)  # 3 days ago
        result = inbox.fmt_date(ts)
        self.assertRegex(result, r"^\d+d$")

    def test_old_date_returns_month_day(self):
        ts     = self._make_ts(10 * 86400)  # 10 days ago
        result = inbox.fmt_date(ts)
        self.assertRegex(result, r"^[A-Z][a-z]+\d+$")

    def test_invalid_string_truncates(self):
        result = inbox.fmt_date("bad-date")
        self.assertEqual(len(result), 5)

    def test_z_suffix_handled(self):
        result = inbox.fmt_date("2020-01-01T00:00:00Z")
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)


class TestShortFrom(unittest.TestCase):
    """Tests for short_from address formatting."""

    def test_name_and_angle_bracket(self):
        result = inbox.short_from("Alice Smith <alice@example.com>")
        self.assertEqual(result, "Alice Smith")

    def test_quoted_name(self):
        result = inbox.short_from('"Bob Jones" <bob@example.com>')
        self.assertEqual(result, "Bob Jones")

    def test_bare_email_returns_local_at_domain(self):
        result = inbox.short_from("carol@example.com")
        self.assertEqual(result, "carol@example")

    def test_empty_angle_bracket_falls_back_to_at_split(self):
        result = inbox.short_from(" <dave@example.com>")
        self.assertIn("dave", result)

    def test_plain_string_no_at(self):
        result = inbox.short_from("unknown")
        self.assertEqual(result, "unknown")


class TestStripHtml(unittest.TestCase):
    """Tests for strip_html HTML-to-text conversion."""

    def test_simple_tags_removed(self):
        result = inbox.strip_html("<p>Hello world</p>")
        self.assertIn("Hello world", result)
        self.assertNotIn("<p>", result)

    def test_br_becomes_newline(self):
        result = inbox.strip_html("line1<br>line2")
        self.assertIn("\n", result)

    def test_entities_decoded(self):
        result = inbox.strip_html("AT&amp;T &lt;rocks&gt;")
        self.assertIn("AT&T", result)
        self.assertIn("<rocks>", result)

    def test_empty_string(self):
        result = inbox.strip_html("")
        self.assertEqual(result.strip(), "")

    def test_plain_text_unchanged(self):
        result = inbox.strip_html("just plain text")
        self.assertIn("just plain text", result)
