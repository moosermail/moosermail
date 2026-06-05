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
