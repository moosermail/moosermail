#!/usr/bin/env python3
"""
inbox.py — Terminal email client for Resend inbound mail
Stdlib only: curses, urllib. No pip installs required. Python 3.7+.

FIRST RUN
  The app will ask for your Resend domain and sender address.
  Config is saved to ~/.inboxpy.conf automatically.

USAGE
  export RESEND_API_KEY="re_xxxxxxxxxxxx"
  chmod +x inbox.py && ./inbox.py

INBOX KEYS
  ↑/↓ or j/k   Navigate list      Enter       Open email
  PgUp/PgDn     Scroll preview     r           Reply
  c             Compose new        R           Refresh
  d             Mark read          s           Sent folder
  D             Drafts             ?           Help
  q             Quit

COMPOSE / REPLY
  Tab           Next field         Shift+Tab   Prev field
  ↑/↓/←/→      Move cursor        Enter       New line (in body)
  Backspace     Delete char        Ctrl+G      Send
  Esc           Cancel
"""

import curses
import os
import sys
import json
import re
import textwrap
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode

# ─────────────────────────────────────────────────────────────────────────────
# Config / State
# ─────────────────────────────────────────────────────────────────────────────

API_KEY     = os.environ.get("RESEND_API_KEY", "")
API_BASE    = "https://api.resend.com"
CONFIG_FILE = os.path.expanduser(
    os.environ.get("INBOX_CONFIG", "~/.inboxpy.conf")
)
STATE_FILE  = os.path.expanduser(
    os.environ.get("INBOX_STATE",  "~/.inboxpy_state")
)

DEFAULT_CFG = {
    "from_address": "",
    "list_limit":   "50",
    "app_name":     "INBOX",
}

def load_config():
    cfg = dict(DEFAULT_CFG)
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                cfg[k.strip().lower()] = v.strip().strip('"').strip("'")
    return cfg

def save_config(cfg):
    os.makedirs(os.path.dirname(CONFIG_FILE) or ".", exist_ok=True)
    lines = [f"# inbox.py configuration\n"]
    for k, v in cfg.items():
        lines.append(f'{k} = "{v}"\n')
    with open(CONFIG_FILE, "w") as f:
        f.writelines(lines)

def load_seen():
    if not os.path.exists(STATE_FILE):
        return set()
    with open(STATE_FILE) as f:
        return set(f.read().splitlines())

def mark_seen(eid, seen_set):
    if eid not in seen_set:
        seen_set.add(eid)
        os.makedirs(os.path.dirname(STATE_FILE) or ".", exist_ok=True)
        with open(STATE_FILE, "a") as f:
            f.write(eid + "\n")

# ─────────────────────────────────────────────────────────────────────────────
# API
# ─────────────────────────────────────────────────────────────────────────────

def api(method, path, body=None, params=None):
    url = API_BASE + path
    if params:
        url += "?" + urlencode({k: v for k, v in params.items() if v})
    data = json.dumps(body).encode() if body else None
    req  = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type":  "application/json",
        "User-Agent":    "inbox.py/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            msg = json.loads(raw).get("message", str(e))
        except Exception:
            msg = raw.decode(errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {msg}")

def api_list(limit=50):
    d = api("GET", "/emails/receiving", params={"limit": limit})
    return d.get("data", []), d.get("has_more", False)

def api_get_email(eid):
    return api("GET", f"/emails/receiving/{eid}")

def api_send(payload):
    return api("POST", "/emails", body=payload)

# ─────────────────────────────────────────────────────────────────────────────
# Formatting helpers
# ─────────────────────────────────────────────────────────────────────────────

def fmt_date(s):
    try:
        s = s.replace(" ", "T")
        if "." in s:
            s = s[:s.index(".")]
        if "Z" in s:
            s = s.replace("Z", "+00:00")
        elif "+" not in s:
            s += "+00:00"
        dt   = datetime.fromisoformat(s)
        now  = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        diff = now - dt
        if diff < timedelta(hours=1):
            return f"{diff.seconds // 60}m"
        if diff < timedelta(days=1):
            return f"{diff.seconds // 3600}h"
        if diff < timedelta(days=2):
            return "yest"
        if diff < timedelta(days=7):
            return f"{diff.days}d"
        return dt.strftime("%b%d")
    except Exception:
        return s[:5] if len(s) >= 5 else s

def short_from(addr):
    if "<" in addr:
        name = addr[:addr.index("<")].strip().strip('"')
        if name:
            return name
    if "@" in addr:
        local, _, dom = addr.partition("@")
        return f"{local}@{dom.split('.')[0]}"
    return addr

def normalise_domain(raw):
    """Accept 'example.com', 'http://example.com', 'https://example.com/...'"""
    raw = raw.strip()
    raw = re.sub(r'^https?://', '', raw)
    raw = raw.split("/")[0].strip()
    return raw.lower()

def strip_html(html):
    t = re.sub(r'<style[^>]*>.*?</style>', '',  html, flags=re.DOTALL | re.I)
    t = re.sub(r'<script[^>]*>.*?</script>', '', t,    flags=re.DOTALL | re.I)
    t = re.sub(r'<br\s*/?>', '\n', t, flags=re.I)
    t = re.sub(r'<p[^>]*>',  '\n', t, flags=re.I)
    t = re.sub(r'<[^>]+>', '', t)
    for ent, ch in [('&nbsp;',' '),('&amp;','&'),('&lt;','<'),
                    ('&gt;','>'),('&quot;','"'),('&#39;',"'")]:
        t = t.replace(ent, ch)
    return re.sub(r'\n{3,}', '\n\n', t).strip()

# ─────────────────────────────────────────────────────────────────────────────
# Markdown → curses spans
# Returns list of lines, each line = list of (text, attr) tuples
# ─────────────────────────────────────────────────────────────────────────────

def _inline_spans(text, base_attr=0):
    """Parse inline markdown in `text` into list of (str, attr) tuples."""
    spans = []
    # Pattern order matters: bold-italic before bold before italic
    pattern = re.compile(
        r'(\*\*\*(.+?)\*\*\*)'          # ***bold italic***
        r'|(\*\*(.+?)\*\*)'             # **bold**
        r'|(__(.+?)__)'                 # __bold__
        r'|(\*(.+?)\*)'                 # *italic*
        r'|(_(.+?)_)'                   # _italic_
        r'|(`(.+?)`)'                   # `code`
        r'|(https?://\S+)'              # URL
    )
    pos = 0
    for m in pattern.finditer(text):
        if m.start() > pos:
            spans.append((text[pos:m.start()], base_attr))
        if m.group(1):   # ***bold italic***
            spans.append((m.group(2), base_attr | curses.A_BOLD | curses.A_ITALIC))
        elif m.group(3): # **bold**
            spans.append((m.group(4), base_attr | curses.A_BOLD))
        elif m.group(5): # __bold__
            spans.append((m.group(6), base_attr | curses.A_BOLD))
        elif m.group(7): # *italic*
            spans.append((m.group(8), base_attr | curses.A_ITALIC))
        elif m.group(9): # _italic_
            spans.append((m.group(10), base_attr | curses.A_ITALIC))
        elif m.group(11): # `code`
            spans.append((m.group(12), base_attr | curses.A_REVERSE))
        elif m.group(13): # URL
            spans.append((m.group(13), base_attr | curses.A_UNDERLINE))
        pos = m.end()
    if pos < len(text):
        spans.append((text[pos:], base_attr))
    return spans or [("", base_attr)]

# Colour pair IDs (set up in setup_colors)
CP_HEADER  = 1
CP_NEW     = 2
CP_SEL     = 3
CP_SUBJECT = 4
CP_STATUS  = 5
CP_DIM     = 6
CP_ERR     = 7
CP_HELP    = 8
CP_H1      = 9
CP_QUOTE   = 10
CP_FIELD   = 11   # compose field labels
CP_COMPOSE = 12   # compose border

def setup_colors():
    curses.use_default_colors()
    curses.init_pair(CP_HEADER,  curses.COLOR_BLACK,  curses.COLOR_CYAN)
    curses.init_pair(CP_NEW,     curses.COLOR_GREEN,  -1)
    curses.init_pair(CP_SEL,     curses.COLOR_BLACK,  curses.COLOR_WHITE)
    curses.init_pair(CP_SUBJECT, curses.COLOR_YELLOW, -1)
    curses.init_pair(CP_STATUS,  curses.COLOR_BLACK,  curses.COLOR_CYAN)
    curses.init_pair(CP_DIM,     246,                 -1)
    curses.init_pair(CP_ERR,     curses.COLOR_RED,    -1)
    curses.init_pair(CP_HELP,    curses.COLOR_BLACK,  curses.COLOR_YELLOW)
    curses.init_pair(CP_H1,      curses.COLOR_CYAN,   -1)
    curses.init_pair(CP_QUOTE,   246,                 -1)
    curses.init_pair(CP_FIELD,   curses.COLOR_CYAN,   -1)
    curses.init_pair(CP_COMPOSE, curses.COLOR_BLACK,  curses.COLOR_CYAN)

def _a(pair, extra=0):
    return curses.color_pair(pair) | extra

def md_render_line(line):
    """
    Return list of (text, attr) for one markdown line.
    Handles headings, blockquotes, hr, bullets, inline styles.
    """
    # Horizontal rule
    if re.match(r'^[\-\*_]{3,}\s*$', line):
        return [("─" * 60, _a(CP_DIM))]

    # Heading 1
    m = re.match(r'^#\s+(.*)', line)
    if m:
        return [(m.group(1), _a(CP_H1, curses.A_BOLD))]

    # Heading 2-3
    m = re.match(r'^#{2,3}\s+(.*)', line)
    if m:
        return _inline_spans(m.group(1), curses.A_BOLD)

    # Blockquote
    m = re.match(r'^>\s?(.*)', line)
    if m:
        prefix = [("▌ ", _a(CP_QUOTE))]
        return prefix + _inline_spans(m.group(1), _a(CP_QUOTE) | curses.A_ITALIC)

    # Bullet
    m = re.match(r'^(\s*)[-\*\+]\s+(.*)', line)
    if m:
        indent = " " * len(m.group(1))
        return [(indent + "• ", _a(CP_NEW))] + _inline_spans(m.group(2))

    # Numbered list
    m = re.match(r'^(\s*)\d+\.\s+(.*)', line)
    if m:
        return _inline_spans(line)

    # Empty
    if not line.strip():
        return [("", 0)]

    return _inline_spans(line)

def _join_paragraphs(text):
    """
    Join soft-wrapped lines (hard line-breaks inserted by email clients at
    ~70-80 chars) back into proper paragraphs so we can re-wrap at window
    width.  A blank line = paragraph break.  Lines that look like markdown
    structure (headings, bullets, blockquotes, HR) are kept as-is.
    """
    STRUCTURAL = re.compile(
        r'^(#{1,6}\s|[-\*\+]\s|\d+\.\s|>\s?|[-\*_]{3,}\s*$|\s*$)'
    )
    out   = []
    buf   = []

    def flush():
        if buf:
            out.append(" ".join(buf))
            buf.clear()

    for line in text.splitlines():
        if not line.strip():
            flush()
            out.append("")
        elif STRUCTURAL.match(line):
            flush()
            out.append(line)
        else:
            buf.append(line.rstrip())

    flush()
    return "\n".join(out)


def _rewrap_spans(spans, wrapped):
    """
    Re-map (text, attr) spans onto word-wrapped lines.
    Builds a flat (char, attr) list then slices by wrapped-line length,
    so each wrapped line gets the exact characters that belong to it.
    """
    flat = []
    for seg, attr in spans:
        for ch in seg:
            flat.append((ch, attr))

    output = []
    pos    = 0
    for wline in wrapped:
        seg_chars = flat[pos: pos + len(wline)]
        pos += len(wline)
        # textwrap collapses the space between lines — skip it
        if pos < len(flat) and flat[pos][0] == ' ':
            pos += 1

        if not seg_chars:
            output.append([("", 0)])
            continue
        # Re-group consecutive same-attr chars into span tuples
        line_out = []
        cur_seg, cur_attr = "", seg_chars[0][1]
        for ch, attr in seg_chars:
            if attr == cur_attr:
                cur_seg += ch
            else:
                line_out.append((cur_seg, cur_attr))
                cur_seg, cur_attr = ch, attr
        if cur_seg:
            line_out.append((cur_seg, cur_attr))
        output.append(line_out)
    return output


def md_render(text, width):
    """
    Render markdown text into list of (list of (str, attr)) — one per terminal row.
    Joins soft-wrapped paragraphs first, then re-wraps at window width.
    """
    text   = _join_paragraphs(text)
    output = []
    for raw_line in text.splitlines():
        spans = md_render_line(raw_line)
        plain = "".join(s for s, _ in spans)
        if not plain.strip():
            output.append([("", 0)])
            continue
        wrapped = textwrap.wrap(plain, max(1, width - 2)) or [plain]
        if len(wrapped) == 1:
            output.append(spans)
        else:
            output.extend(_rewrap_spans(spans, wrapped))
    return output

# ─────────────────────────────────────────────────────────────────────────────
# Input compatibility: get_wch() is absent on macOS Python 3.13 universal2
# (CPython issue #128085 — ships without ncursesw).
# _getwch(win) always returns the same contract as get_wch():
#   str  for printable/control chars
#   int  for special keys (KEY_UP, KEY_BACKSPACE, etc.)
# ─────────────────────────────────────────────────────────────────────────────

_HAS_GET_WCH = hasattr(curses.initscr(), 'get_wch') if False else None  # lazy

def _probe_get_wch():
    global _HAS_GET_WCH
    if _HAS_GET_WCH is None:
        import curses as _c
        # Check on the module level — window objects share the same C type
        try:
            _c.initscr()
            win = _c.newwin(1, 1)
            _HAS_GET_WCH = hasattr(win, 'get_wch')
            win.erase()
        except Exception:
            _HAS_GET_WCH = False
    return _HAS_GET_WCH

def _getwch(win):
    """
    Portable replacement for win.get_wch().
    Falls back to getch() + manual UTF-8 assembly on macOS without ncursesw.
    """
    if _probe_get_wch():
        return win.get_wch()

    # Fallback: getch() returns one byte at a time.
    # ncurses KEY_* special keys are ints > 255 (KEY_UP=259, KEY_DOWN=258, etc).
    # Everything ≤255 — including Enter(\n=10), Esc(27), Ctrl+G(7), printable
    # ASCII, and the first byte of a UTF-8 sequence — we return as str(chr).
    # That way the caller's `isinstance(key, str)` branch handles all of them
    # uniformly via ord(), exactly as get_wch() would.
    b0 = win.getch()
    if b0 < 0:
        raise curses.error("no input")

    # True special key (arrow keys, function keys — ncurses KEY_* > 255)
    if b0 > 255:
        return b0

    # Pure ASCII or control char — return as single-char str
    if b0 < 0x80:
        return chr(b0)

    # Multi-byte UTF-8 — collect remaining continuation bytes
    if b0 < 0xC0:              # stray continuation byte — return as-is
        return chr(b0)
    elif b0 < 0xE0:
        nbytes = 2
    elif b0 < 0xF0:
        nbytes = 3
    else:
        nbytes = 4

    raw = bytearray([b0])
    win.nodelay(True)
    try:
        for _ in range(nbytes - 1):
            b = win.getch()
            if b < 0:
                break
            raw.append(b)
    finally:
        win.nodelay(False)

    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return chr(b0)


# ─────────────────────────────────────────────────────────────────────────────
# Custom multiline editor widget
# ─────────────────────────────────────────────────────────────────────────────

BS_KEYS = {curses.KEY_BACKSPACE, 127, 8}   # macOS sends 127 (\x7f) for backspace


class Editor:
    """
    A scrollable multiline text editor embedded in a curses subwindow.
    Enter = newline.  Ctrl+G = submit.  Ctrl+D = save draft.  Esc = cancel.
    Returns (text: str, action: 'submit'|'draft'|'cancel') from .edit().

    Horizontal scroll: each row tracks its own viewport offset so long lines
    (e.g. pasted paragraphs) stay fully accessible — nothing is ever clipped.
    A '>' indicator at col 0 when scrolled right, '<' at end when there's more.
    """
    SUBMIT = 7    # Ctrl+G
    DRAFT  = 4    # Ctrl+D
    CANCEL = 27   # Esc

    def __init__(self, win, inittext=""):
        self.win     = win
        self.lines   = inittext.splitlines() or [""]
        self.row     = len(self.lines) - 1  # start at end when pre-filled
        self.col     = len(self.lines[-1])
        self.vscroll = 0          # top visible line
        self.hscroll = {}         # row -> horizontal viewport offset

    def _hs(self, row=None):
        if row is None: row = self.row
        return self.hscroll.get(row, 0)

    def _h(self): return self.win.getmaxyx()[0]
    def _w(self): return self.win.getmaxyx()[1]

    def _clamp(self):
        self.row = max(0, min(self.row, len(self.lines) - 1))
        self.col = max(0, min(self.col, len(self.lines[self.row])))
        h, w = self.win.getmaxyx()

        # Vertical scroll
        if self.row < self.vscroll:
            self.vscroll = self.row
        elif self.row >= self.vscroll + h:
            self.vscroll = self.row - h + 1

        # Horizontal scroll for current row
        hs = self._hs()
        view_w = w - 2          # -1 for overflow indicators each side
        if self.col < hs:
            hs = max(0, self.col - view_w // 3)
        elif self.col >= hs + view_w:
            hs = self.col - view_w + view_w // 3
        self.hscroll[self.row] = max(0, hs)

    def _draw(self):
        self.win.erase()
        h, w = self.win.getmaxyx()
        view_w = w - 1           # usable columns

        for i in range(h):
            ln = self.vscroll + i
            if ln >= len(self.lines):
                break
            line = self.lines[ln]
            hs   = self._hs(ln)

            if ln == self.row:
                # Show horizontal scroll indicators for current line
                if hs > 0:
                    # scrolled right: show ‹ at col 0, then content from hs+1
                    visible = line[hs + 1: hs + 1 + view_w - 1]
                    try:
                        self.win.addstr(i, 0, "‹", _a(CP_DIM))
                        self.win.addstr(i, 1, visible)
                    except curses.error:
                        pass
                else:
                    visible = line[hs: hs + view_w]
                    try:
                        self.win.addstr(i, 0, visible)
                    except curses.error:
                        pass
                # Overflow indicator on the right
                if hs + view_w < len(line):
                    try:
                        self.win.addstr(i, w - 2, "›", _a(CP_DIM))
                    except curses.error:
                        pass
            else:
                # Non-active rows: show from their own hscroll (or 0 if not scrolled)
                visible = line[hs: hs + view_w]
                if hs > 0:
                    try:
                        self.win.addstr(i, 0, "‹", _a(CP_DIM))
                        self.win.addstr(i, 1, visible[:view_w - 1])
                    except curses.error:
                        pass
                else:
                    try:
                        self.win.addstr(i, 0, visible)
                    except curses.error:
                        pass

        # Position cursor
        hs = self._hs()
        cy = self.row - self.vscroll
        if hs > 0:
            cx = (self.col - hs) + 1   # +1 to skip the ‹ indicator
        else:
            cx = self.col - hs
        cx = max(0, min(cx, w - 2))
        try:
            self.win.move(cy, cx)
        except curses.error:
            pass
        self.win.refresh()

    def _insert_char(self, ch):
        line = self.lines[self.row]
        self.lines[self.row] = line[:self.col] + ch + line[self.col:]
        self.col += 1

    def _backspace(self):
        if self.col > 0:
            line = self.lines[self.row]
            self.lines[self.row] = line[:self.col - 1] + line[self.col:]
            self.col -= 1
        elif self.row > 0:
            prev = self.lines[self.row - 1]
            self.col = len(prev)
            self.lines[self.row - 1] = prev + self.lines[self.row]
            del self.lines[self.row]
            self.row -= 1

    def _delete(self):
        line = self.lines[self.row]
        if self.col < len(line):
            self.lines[self.row] = line[:self.col] + line[self.col + 1:]
        elif self.row < len(self.lines) - 1:
            self.lines[self.row] = line + self.lines[self.row + 1]
            del self.lines[self.row + 1]

    def _enter(self):
        line = self.lines[self.row]
        self.lines[self.row]     = line[:self.col]
        self.lines.insert(self.row + 1, line[self.col:])
        self.row += 1
        self.col  = 0
        self.hscroll[self.row] = 0

    def edit(self):
        curses.curs_set(1)
        self.win.keypad(True)
        action = "cancel"

        while True:
            self._clamp()
            self._draw()
            try:
                key = _getwch(self.win)
            except curses.error:
                continue

            if isinstance(key, str):
                cp = ord(key)
                if cp == self.SUBMIT:
                    action = "submit"; break
                elif cp == self.DRAFT:
                    action = "draft";  break
                elif cp == self.CANCEL:
                    action = "cancel"; break
                elif cp in (ord('\n'), ord('\r')):
                    self._enter()
                elif cp in (8, 127):
                    self._backspace()
                elif cp >= 32:
                    self._insert_char(key)
            else:
                if key == self.SUBMIT:
                    action = "submit"; break
                elif key == self.DRAFT:
                    action = "draft";  break
                elif key == self.CANCEL:
                    action = "cancel"; break
                elif key == curses.KEY_UP:
                    if self.row > 0:
                        self.row -= 1
                        self.col  = min(self.col, len(self.lines[self.row]))
                elif key == curses.KEY_DOWN:
                    if self.row < len(self.lines) - 1:
                        self.row += 1
                        self.col  = min(self.col, len(self.lines[self.row]))
                elif key == curses.KEY_LEFT:
                    if self.col > 0:
                        self.col -= 1
                    elif self.row > 0:
                        self.row -= 1
                        self.col  = len(self.lines[self.row])
                elif key == curses.KEY_RIGHT:
                    if self.col < len(self.lines[self.row]):
                        self.col += 1
                    elif self.row < len(self.lines) - 1:
                        self.row += 1
                        self.col  = 0
                elif key == curses.KEY_HOME:
                    self.col = 0
                elif key == curses.KEY_END:
                    self.col = len(self.lines[self.row])
                elif key in BS_KEYS:
                    self._backspace()
                elif key == curses.KEY_DC:
                    self._delete()
                elif key in (curses.KEY_ENTER,):
                    self._enter()

        curses.curs_set(0)
        return "\n".join(self.lines), action


# ─────────────────────────────────────────────────────────────────────────────
# Single-line field editor (for To, Subject, CC)
# ─────────────────────────────────────────────────────────────────────────────

class FieldEditor:
    """Single-line input. Returns (text, action) where action is one of:
    'next', 'prev', 'submit', 'cancel'."""

    SUBMIT = 7    # Ctrl+G
    CANCEL = 27   # Esc

    def __init__(self, win, inittext=""):
        self.win  = win
        self.text = inittext
        self.col  = len(inittext)

    def _draw(self):
        _, w = self.win.getmaxyx()
        self.win.erase()
        display = self.text[:w - 1]
        try:
            self.win.addstr(0, 0, display, _a(CP_SEL))
            self.win.move(0, min(self.col, w - 2))
        except curses.error:
            pass
        self.win.refresh()

    def edit(self):
        curses.curs_set(1)
        self.win.keypad(True)
        action = "next"

        while True:
            self._draw()
            try:
                key = _getwch(self.win)
            except curses.error:
                continue

            if isinstance(key, str):
                cp = ord(key)
                if cp == self.SUBMIT:
                    action = "submit"; break
                elif cp == self.CANCEL:
                    action = "cancel"; break
                elif cp == ord('\t'):
                    action = "next"; break
                elif cp in (ord('\n'), ord('\r')):
                    action = "next"; break
                elif cp in (8, 127):
                    if self.col > 0:
                        self.text = self.text[:self.col-1] + self.text[self.col:]
                        self.col -= 1
                elif cp >= 32:
                    self.text = self.text[:self.col] + key + self.text[self.col:]
                    self.col += 1
            else:
                if key == self.SUBMIT:
                    action = "submit"; break
                elif key == self.CANCEL:
                    action = "cancel"; break
                elif key == ord('\t'):
                    action = "next"; break
                elif key == curses.KEY_BTAB:
                    action = "prev"; break
                elif key == curses.KEY_UP:
                    action = "prev"; break
                elif key == curses.KEY_DOWN:
                    action = "next"; break
                elif key in (curses.KEY_ENTER,):
                    action = "next"; break
                elif key == curses.KEY_LEFT:
                    self.col = max(0, self.col - 1)
                elif key == curses.KEY_RIGHT:
                    self.col = min(len(self.text), self.col + 1)
                elif key == curses.KEY_HOME:
                    self.col = 0
                elif key == curses.KEY_END:
                    self.col = len(self.text)
                elif key in BS_KEYS:
                    if self.col > 0:
                        self.text = self.text[:self.col-1] + self.text[self.col:]
                        self.col -= 1
                elif key == curses.KEY_DC:
                    self.text = self.text[:self.col] + self.text[self.col+1:]

        curses.curs_set(0)
        return self.text, action

# ─────────────────────────────────────────────────────────────────────────────
# Drafts  (local JSON storage, ~/.inboxpy_drafts/)
# ─────────────────────────────────────────────────────────────────────────────

DRAFTS_DIR = os.path.expanduser(
    os.environ.get("INBOX_DRAFTS", "~/.inboxpy_drafts")
)

def draft_save(fields, body):
    """Save a draft. fields = {to,cc,subject,reply_to_mid}, body = str. Returns path."""
    os.makedirs(DRAFTS_DIR, exist_ok=True)
    import time
    name = f"draft_{int(time.time()*1000)}.json"
    path = os.path.join(DRAFTS_DIR, name)
    data = {
        "id":           name,
        "to":           fields.get("to", ""),
        "cc":           fields.get("cc", ""),
        "subject":      fields.get("subject", ""),
        "body":         body,
        "saved_at":     __import__("datetime").datetime.now().isoformat(),
        "reply_to_mid": fields.get("reply_to_mid", ""),
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    return path

def draft_list():
    """Return list of draft dicts, newest first."""
    if not os.path.isdir(DRAFTS_DIR):
        return []
    out = []
    for name in sorted(os.listdir(DRAFTS_DIR), reverse=True):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(DRAFTS_DIR, name)) as f:
                out.append(json.load(f))
        except Exception:
            pass
    return out

def draft_delete(draft_id):
    path = os.path.join(DRAFTS_DIR, draft_id)
    try:
        os.remove(path)
    except OSError:
        pass


class DraftsView:
    """
    Full-screen overlay listing local drafts.
    ↑/↓ Navigate  Enter Resume editing  d/Del Delete  Esc/← Close
    Returns a draft dict to resume, or None.
    """

    def __init__(self, scr):
        self.scr      = scr
        self.drafts   = []
        self.selected = 0

    def _draw(self):
        self.scr.erase()
        h, w = self.scr.getmaxyx()
        title = " DRAFTS — Enter Resume · d Delete · Esc/← Close "
        try:
            self.scr.addstr(0, 0, title.ljust(w - 1)[:w - 1],
                            _a(CP_COMPOSE, curses.A_BOLD))
        except curses.error:
            pass

        if not self.drafts:
            try:
                self.scr.addstr(2, 2, "No drafts saved.", _a(CP_DIM))
                self.scr.addstr(3, 2, "Press Esc to close.", _a(CP_DIM))
            except curses.error:
                pass
            self.scr.refresh()
            return

        list_h = h - 2
        off    = max(0, self.selected - list_h + 1) if self.selected >= list_h else 0

        for i in range(list_h):
            idx = off + i
            if idx >= len(self.drafts):
                break
            d    = self.drafts[idx]
            subj = d.get("subject", "(no subject)")[:40]
            to   = d.get("to",      "")[:24]
            date = d.get("saved_at","")[:16].replace("T", " ")
            line = f"  {date}  {to:<24}  {subj}"[:w - 2]
            try:
                if idx == self.selected:
                    self.scr.addstr(1 + i, 0, line.ljust(w - 1)[:w - 1],
                                    _a(CP_SEL, curses.A_BOLD))
                else:
                    self.scr.addstr(1 + i, 0, line, _a(CP_DIM))
            except curses.error:
                pass
        self.scr.refresh()

    def run(self):
        self.drafts   = draft_list()
        self.selected = 0
        while True:
            self._draw()
            try:
                key = _getwch(self.scr)
            except curses.error:
                continue
            kint = key if isinstance(key, int) else ord(key)

            if kint in (27, curses.KEY_LEFT):
                return None
            elif kint in (curses.KEY_UP, ord('k')):
                self.selected = max(0, self.selected - 1)
            elif kint in (curses.KEY_DOWN, ord('j')):
                self.selected = min(len(self.drafts) - 1, self.selected + 1)
            elif kint in (curses.KEY_ENTER, ord('\n'), ord('\r')):
                if self.drafts:
                    return self.drafts[self.selected]
            elif kint in (ord('d'), curses.KEY_DC):
                if self.drafts:
                    d = self.drafts[self.selected]
                    draft_delete(d["id"])
                    self.drafts   = draft_list()
                    self.selected = max(0, min(self.selected, len(self.drafts) - 1))



# ─────────────────────────────────────────────────────────────────────────────
# Sent folder  (local JSON storage, ~/.inboxpy_sent/)
# ─────────────────────────────────────────────────────────────────────────────

SENT_DIR = os.path.expanduser(
    os.environ.get("INBOX_SENT", "~/.inboxpy_sent")
)

def sent_save(payload, send_id=""):
    """Persist a sent message to local storage."""
    os.makedirs(SENT_DIR, exist_ok=True)
    import time
    name = f"sent_{int(time.time()*1000)}.json"
    path = os.path.join(SENT_DIR, name)
    data = {
        "id":        name,
        "send_id":   send_id,
        "to":        payload.get("to", []),
        "cc":        payload.get("cc", []),
        "subject":   payload.get("subject", ""),
        "from":      payload.get("from", ""),
        "body":      payload.get("text", ""),
        "sent_at":   __import__("datetime").datetime.now().isoformat(),
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def sent_list():
    """Return sent messages, newest first."""
    if not os.path.isdir(SENT_DIR):
        return []
    out = []
    for name in sorted(os.listdir(SENT_DIR), reverse=True):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(SENT_DIR, name)) as f:
                out.append(json.load(f))
        except Exception:
            pass
    return out


class SentView:
    """
    Full-screen sent-folder browser.
    ↑/↓  Navigate   Enter  Read body   Esc/←  Close
    """

    def __init__(self, scr):
        self.scr      = scr
        self.msgs     = []
        self.selected = 0
        self.reading  = False  # showing full body of selected msg

    def _draw_list(self):
        self.scr.erase()
        h, w = self.scr.getmaxyx()
        title = " SENT — ↑↓ Navigate · Enter Read · Esc/← Close "
        try:
            self.scr.addstr(0, 0, title.ljust(w - 1)[:w - 1],
                            _a(CP_COMPOSE, curses.A_BOLD))
        except curses.error:
            pass

        if not self.msgs:
            try:
                self.scr.addstr(2, 2, "No sent messages yet.", _a(CP_DIM))
            except curses.error:
                pass
            self.scr.refresh()
            return

        list_h = h - 2
        off    = max(0, self.selected - list_h + 1) if self.selected >= list_h else 0
        for i in range(list_h):
            idx = off + i
            if idx >= len(self.msgs):
                break
            m    = self.msgs[idx]
            to   = ", ".join(m.get("to", []))[:28]
            subj = m.get("subject", "(no subject)")[:40]
            date = m.get("sent_at", "")[:16].replace("T", " ")
            line = f"  {date}  {to:<28}  {subj}"[:w - 2]
            try:
                if idx == self.selected:
                    self.scr.addstr(1 + i, 0, line.ljust(w - 1)[:w - 1],
                                    _a(CP_SEL, curses.A_BOLD))
                else:
                    self.scr.addstr(1 + i, 0, line, _a(CP_DIM))
            except curses.error:
                pass
        self.scr.refresh()

    def _draw_msg(self, m):
        self.scr.erase()
        h, w = self.scr.getmaxyx()
        title = " SENT MESSAGE — Esc/← Back "
        try:
            self.scr.addstr(0, 0, title.ljust(w - 1)[:w - 1],
                            _a(CP_COMPOSE, curses.A_BOLD))
            row = 1
            for label, val in [
                ("To",      ", ".join(m.get("to", []))),
                ("Subject", m.get("subject", "")),
                ("Date",    m.get("sent_at", "").replace("T", " ")[:19]),
            ]:
                self.scr.addstr(row, 1, f"{label}:".ljust(9), curses.A_BOLD)
                self.scr.addstr(row, 10, val[:w - 12])
                row += 1
            self.scr.addstr(row, 0, "─" * (w - 1), _a(CP_DIM))
            row += 1
            for line in m.get("body", "").splitlines():
                if row >= h:
                    break
                self.scr.addstr(row, 1, line[:w - 2])
                row += 1
        except curses.error:
            pass
        self.scr.refresh()

    def run(self):
        self.msgs     = sent_list()
        self.selected = 0
        self.reading  = False
        while True:
            if self.reading:
                self._draw_msg(self.msgs[self.selected])
            else:
                self._draw_list()

            try:
                key = _getwch(self.scr)
            except curses.error:
                continue
            kint = key if isinstance(key, int) else ord(key)

            if self.reading:
                if kint in (27, curses.KEY_LEFT, ord('q')):
                    self.reading = False
            else:
                if kint in (27, curses.KEY_LEFT, ord('q')):
                    return
                elif kint in (curses.KEY_UP, ord('k')):
                    self.selected = max(0, self.selected - 1)
                elif kint in (curses.KEY_DOWN, ord('j')):
                    self.selected = min(len(self.msgs) - 1, self.selected + 1)
                elif kint in (curses.KEY_ENTER, ord('\n'), ord('\r')):
                    if self.msgs:
                        self.reading = True


# ─────────────────────────────────────────────────────────────────────────────
# Compose / Reply view (full-screen overlay)
# ─────────────────────────────────────────────────────────────────────────────

class ComposeView:
    """
    Full-screen compose/reply overlay.
    Fields: To, CC, Subject, then a large body editor.
    Ctrl+G sends, Esc cancels.
    Returns (payload: dict|None).
    """

    def __init__(self, scr, from_addr, to="", subject="", reply_to_mid="",
                 cc="", initbody=""):
        self.scr          = scr
        self.from_addr    = from_addr
        self.fields       = {"to": to, "cc": cc, "subject": subject,
                             "reply_to_mid": reply_to_mid}
        self.reply_to_mid = reply_to_mid
        self.initbody     = initbody

    def _draw_chrome(self, w, h):
        """Draw the static compose chrome (header + field labels + separator)."""
        self.scr.erase()
        title = " COMPOSE — Ctrl+G Send · Ctrl+D Save Draft · Esc Cancel · Tab Next field "
        try:
            self.scr.addstr(0, 0, title.ljust(w - 1)[:w - 1], _a(CP_COMPOSE, curses.A_BOLD))
            self.scr.addstr(1, 1, f"{'From':<8}", _a(CP_FIELD, curses.A_BOLD))
            self.scr.addstr(1, 9, self.from_addr[:w - 12])
        except curses.error:
            pass
        field_order  = ["to", "cc", "subject"]
        field_labels = {"to": "To", "cc": "CC", "subject": "Subject"}
        field_y      = {"to": 2, "cc": 3, "subject": 4}
        for name in field_order:
            y = field_y[name]
            try:
                self.scr.addstr(y, 1, f"{field_labels[name]:<8}", _a(CP_FIELD, curses.A_BOLD))
                # filled background for the editable area
                self.scr.addstr(y, 9, self.fields[name].ljust(w - 11)[:w - 11], _a(CP_SEL))
            except curses.error:
                pass
        try:
            self.scr.addstr(5, 0, "─" * (w - 1), _a(CP_DIM))
            self.scr.addstr(6, 1, "Body — Enter for new line, Ctrl+G to send", _a(CP_DIM))
        except curses.error:
            pass
        self.scr.refresh()

    def run(self):
        h, w = self.scr.getmaxyx()
        field_order  = ["to", "cc", "subject"]
        field_y      = {"to": 2, "cc": 3, "subject": 4}

        self._draw_chrome(w, h)

        # --- Tab through header fields ---
        current_field = 0
        while True:
            # Redraw chrome so saved values show and prior window garbage is gone
            self._draw_chrome(w, h)

            name = field_order[current_field]
            y    = field_y[name]
            fw   = max(4, w - 10)
            fwin = curses.newwin(1, fw, y, 9)
            fwin.bkgd(' ', _a(CP_SEL))
            ed   = FieldEditor(fwin, self.fields[name])
            text, action = ed.edit()
            self.fields[name] = text
            fwin.erase()
            fwin.refresh()
            del fwin
            # Force parent to repaint over the now-deleted child window
            self.scr.touchwin()
            self.scr.refresh()

            if action == "cancel":
                return None
            elif action == "submit":
                break
            elif action == "next":
                current_field = (current_field + 1) % len(field_order)
                if current_field == 0:
                    break  # wrapped past last field — go to body
            elif action == "prev":
                current_field = (current_field - 1) % len(field_order)

        # --- Body editor ---
        body_h = h - 8
        body_w = w - 2
        if body_h < 3:
            body_h = 3
        self._draw_chrome(w, h)
        try:
            self.scr.addstr(6, 1,
                "Ctrl+G = send · Ctrl+D = save draft · Esc = cancel · Enter = newline",
                _a(CP_DIM))
        except curses.error:
            pass
        self.scr.refresh()

        bwin = curses.newwin(body_h, body_w, 7, 1)
        ed   = Editor(bwin, self.initbody)
        body, action = ed.edit()
        bwin.erase(); bwin.refresh(); del bwin

        if action == "draft":
            path = draft_save(self.fields, body)
            return ("draft", path)

        if action != "submit" or not body.strip():
            return None

        to_addr = self.fields["to"].strip()
        subject = self.fields["subject"].strip()
        if not to_addr or not subject:
            return None

        payload = {
            "from":    self.from_addr,
            "to":      [to_addr],
            "subject": subject,
            "text":    body,
        }
        if self.fields["cc"].strip():
            payload["cc"] = [self.fields["cc"].strip()]
        if self.reply_to_mid:
            payload["headers"] = {
                "In-Reply-To": self.reply_to_mid,
                "References":  self.reply_to_mid,
            }
        return payload

# ─────────────────────────────────────────────────────────────────────────────
# Setup wizard (first-run)
# ─────────────────────────────────────────────────────────────────────────────

class SetupWizard:
    """Walks user through first-run config. Returns cfg dict or None."""

    def __init__(self, scr):
        self.scr = scr

    def _prompt(self, y, label, default=""):
        h, w = self.scr.getmaxyx()
        try:
            self.scr.addstr(y, 2, label, _a(CP_FIELD, curses.A_BOLD))
            if default:
                self.scr.addstr(y, 2 + len(label) + 1,
                                f"(default: {default})", _a(CP_DIM))
        except curses.error:
            pass
        win = curses.newwin(1, w - 4, y + 1, 2)
        ed  = FieldEditor(win, default)
        text, action = ed.edit()
        del win
        if action == "cancel":
            return None
        return text.strip() or default

    def run(self):
        self.scr.erase()
        h, w = self.scr.getmaxyx()

        lines = [
            " INBOX.PY — First Run Setup ",
            "",
            "Your Resend API key is set. Let's configure the app.",
            "",
        ]
        for i, line in enumerate(lines):
            try:
                attr = _a(CP_COMPOSE, curses.A_BOLD) if i == 0 else 0
                self.scr.addstr(i, 0, line.ljust(w - 1)[:w - 1] if i == 0 else line, attr)
            except curses.error:
                pass

        y = len(lines)

        # Domain
        try:
            self.scr.addstr(y,     2, "What domain did you verify in Resend?",
                            _a(CP_FIELD, curses.A_BOLD))
            self.scr.addstr(y + 1, 2, "e.g. example.com or https://example.com",
                            _a(CP_DIM))
        except curses.error:
            pass
        self.scr.refresh()

        win1 = curses.newwin(1, w - 4, y + 2, 2)
        ed   = FieldEditor(win1, "")
        domain_raw, action = ed.edit()
        del win1
        if action == "cancel" or not domain_raw.strip():
            return None

        domain = normalise_domain(domain_raw)

        y += 4
        suffix = f"@{domain}"
        try:
            self.scr.addstr(y, 2,
                "What name before the @ should send as?",
                _a(CP_FIELD, curses.A_BOLD))
            self.scr.addstr(y + 1, 2,
                f"Type the part before {suffix}  (e.g.  hello, support, me)",
                _a(CP_DIM))
        except curses.error:
            pass
        self.scr.refresh()

        # Show the static @domain label right after the input box
        local_w  = max(16, min(30, w - len(suffix) - 6))
        # Draw static suffix label
        try:
            self.scr.addstr(y + 2, 2 + local_w, suffix, _a(CP_DIM, curses.A_BOLD))
        except curses.error:
            pass
        self.scr.refresh()

        win2 = curses.newwin(1, local_w, y + 2, 2)
        ed   = FieldEditor(win2, "you")
        local_part, action = ed.edit()
        win2.erase(); win2.refresh(); del win2
        if action == "cancel":
            return None
        local_part = (local_part.strip() or "you").split("@")[0]  # strip any accidental @
        from_addr  = f"{local_part}{suffix}"

        cfg = dict(DEFAULT_CFG)
        cfg["domain"]       = domain
        cfg["from_address"] = from_addr

        y += 5
        try:
            self.scr.addstr(y, 2,
                f"✓ Config saved to {CONFIG_FILE}", _a(CP_NEW, curses.A_BOLD))
            self.scr.addstr(y + 1, 2, "Press any key to open your inbox.", _a(CP_DIM))
        except curses.error:
            pass
        self.scr.refresh()
        self.scr.getch()
        return cfg

# ─────────────────────────────────────────────────────────────────────────────
# Main inbox TUI
# ─────────────────────────────────────────────────────────────────────────────

def _safe(win, y, x, text, attr=0):
    try:
        if attr:
            win.attron(attr)
        win.addstr(y, x, text)
        if attr:
            win.attroff(attr)
    except curses.error:
        pass

class InboxTUI:
    def __init__(self, scr, cfg):
        self.scr        = scr
        self.cfg        = cfg
        self.seen       = load_seen()
        self.emails     = []
        self.has_more   = False
        self.selected   = 0
        self.list_off   = 0
        self.full_email = None   # fetched full email dict
        self.md_lines   = []     # rendered markdown lines for preview
        self.prev_scroll = 0
        self.status     = ""
        self.error      = ""

    # ── drawing ──────────────────────────────────────────────────────────────

    def draw(self):
        self.scr.erase()
        h, w = self.scr.getmaxyx()
        if h < 8 or w < 40:
            _safe(self.scr, 0, 0, "Terminal too small — resize and try again.")
            self.scr.refresh()
            return

        list_w = min(50, max(26, w // 3))
        prev_x = list_w + 1
        prev_w = w - prev_x
        pane_h = h - 2

        self._draw_header(w)
        self._draw_list(list_w, pane_h)
        self._draw_divider(list_w, pane_h)
        self._draw_preview(prev_x, prev_w, pane_h)
        self._draw_statusbar(h - 1, w)
        self.scr.refresh()

    def _draw_header(self, w):
        name      = self.cfg.get("app_name", "INBOX")
        new_count = sum(1 for e in self.emails if e["id"] not in self.seen)
        extra     = "  + more" if self.has_more else ""
        title     = f"  {name}  ·  {len(self.emails)} emails  ·  {new_count} new{extra}"
        _safe(self.scr, 0, 0, title.ljust(w - 1)[:w - 1], _a(CP_HEADER, curses.A_BOLD))

    def _draw_list(self, w, h):
        if not self.emails:
            _safe(self.scr, 3, 2, "No emails. Press R to refresh.")
            return

        # Scroll to keep selection visible
        if self.selected < self.list_off:
            self.list_off = self.selected
        elif self.selected >= self.list_off + h:
            self.list_off = self.selected - h + 1

        dw = 6; sw = 16; subj_w = max(4, w - 2 - sw - 1 - dw - 2)

        for i in range(h):
            idx = self.list_off + i
            if idx >= len(self.emails):
                break
            e      = self.emails[idx]
            eid    = e["id"]
            is_new = eid not in self.seen
            is_sel = idx == self.selected

            dot  = "● " if is_new else "  "
            sndr = short_from(e.get("from", ""))[:sw].ljust(sw)
            subj = e.get("subject", "(no subject)")[:subj_w].ljust(subj_w)
            date = fmt_date(e.get("created_at", ""))[:dw].rjust(dw)
            line = (dot + sndr + " " + subj + " " + date)[:w - 1]

            ry = 1 + i
            if is_sel:
                _safe(self.scr, ry, 0, line.ljust(w - 1)[:w - 1], _a(CP_SEL, curses.A_BOLD))
            elif is_new:
                _safe(self.scr, ry, 0, line, _a(CP_NEW, curses.A_BOLD))
            else:
                _safe(self.scr, ry, 0, line, _a(CP_DIM))

        # Scrollbar
        if len(self.emails) > h:
            bar_h   = max(1, h * h // len(self.emails))
            max_off = max(1, len(self.emails) - h)
            bar_pos = int(self.list_off / max_off * (h - bar_h))
            for i in range(h):
                ch = "█" if bar_pos <= i < bar_pos + bar_h else "░"
                _safe(self.scr, 1 + i, w - 1, ch, _a(CP_DIM))

    def _draw_divider(self, x, h):
        for i in range(h):
            _safe(self.scr, 1 + i, x, "│", _a(CP_DIM))

    def _draw_preview(self, x, w, h):
        if not self.emails or w < 4:
            return
        if self.selected >= len(self.emails):
            return
        e = self.emails[self.selected]

        # Header block
        fields = [
            ("From",    e.get("from", "")),
            ("To",      ", ".join(e.get("to", []))),
        ]
        cc  = ", ".join(e.get("cc",  []))
        bcc = ", ".join(e.get("bcc", []))
        if cc:  fields.append(("CC",  cc))
        if bcc: fields.append(("BCC", bcc))
        fields.append(("Subject", e.get("subject", "(no subject)")))
        fields.append(("Date",    e.get("created_at", "")))
        atts = e.get("attachments", [])
        if atts:
            fields.append(("Attach", f"{len(atts)} file(s)"))

        row = 1
        for label, value in fields:
            if row >= 1 + h:
                break
            lbl = f"{label}:".ljust(8)
            val = value[:w - 10]
            _safe(self.scr, row, x, lbl, curses.A_BOLD)
            if label == "Subject":
                _safe(self.scr, row, x + 8, val, _a(CP_SUBJECT, curses.A_BOLD))
            else:
                _safe(self.scr, row, x + 8, val)
            row += 1

        # Separator
        _safe(self.scr, row, x, ("─" * (w - 1))[:w - 1], _a(CP_DIM))
        row += 1

        # Body
        body_h = h - (row - 1)
        if self.full_email and self.full_email.get("id") == e["id"]:
            if not self.md_lines:
                text = self.full_email.get("text") or ""
                html = self.full_email.get("html") or ""
                body = text if text else (strip_html(html) if html else "(no body)")
                self.md_lines = md_render(body, w)

            max_scroll       = max(0, len(self.md_lines) - body_h)
            self.prev_scroll = max(0, min(self.prev_scroll, max_scroll))

            for i, spans in enumerate(self.md_lines[self.prev_scroll: self.prev_scroll + body_h]):
                if row + i >= 1 + h:
                    break
                cx = x
                for seg, attr in spans:
                    seg = seg[:w - (cx - x) - 1]
                    if not seg:
                        break
                    _safe(self.scr, row + i, cx, seg, attr)
                    cx += len(seg)

            if max_scroll > 0:
                pct = int(self.prev_scroll / max_scroll * 100)
                _safe(self.scr, h, x, f" {pct}% ", _a(CP_DIM))
        else:
            _safe(self.scr, row, x, "  Press Enter to load full email",
                  _a(CP_DIM) | curses.A_ITALIC)

    def _draw_statusbar(self, y, w):
        if self.error:
            text = f"  ✗ {self.error}"
            attr = _a(CP_ERR, curses.A_BOLD)
        else:
            text = f"  {self.status}"
            attr = _a(CP_STATUS)
        _safe(self.scr, y, 0, text.ljust(w - 1)[:w - 1], attr)

    # ── data ─────────────────────────────────────────────────────────────────

    def _set_status(self, msg):
        self.status = msg
        self.error  = ""
        self.draw()

    def refresh_list(self):
        self._set_status("Fetching emails…")
        try:
            limit = int(self.cfg.get("list_limit", 50))
            self.emails, self.has_more = api_list(limit)
            new = sum(1 for e in self.emails if e["id"] not in self.seen)
            self.status = (
                "↑↓ Navigate   Enter Open   r Reply   c Compose   s Sent   D Drafts   R Refresh   ? Help   q Quit"
            )
            self.error    = ""
            self.selected = min(self.selected, max(0, len(self.emails) - 1))
        except Exception as ex:
            self.error  = str(ex)
            self.status = ""

    def load_full(self):
        if not self.emails:
            return
        e   = self.emails[self.selected]
        eid = e["id"]
        if self.full_email and self.full_email.get("id") == eid:
            return
        self._set_status("Loading email…")
        try:
            self.full_email  = api_get_email(eid)
            self.md_lines    = []
            self.prev_scroll = 0
            mark_seen(eid, self.seen)
            self.status = (
                "PgUp/K Scroll up   PgDn/J Scroll down   "
                "r Reply   s Sent   D Drafts   R Refresh   q Quit"
            )
            self.error = ""
        except Exception as ex:
            self.error = str(ex)

    # ── help overlay ─────────────────────────────────────────────────────────

    def show_help(self):
        lines = [
            " INBOX.PY — KEYBOARD SHORTCUTS ",
            "",
            "  ↑ / k         Move up in list",
            "  ↓ / j         Move down in list",
            "  Enter         Load and open email",
            "  PgUp / K      Scroll preview up",
            "  PgDn / J      Scroll preview down",
            "  r             Reply to selected email",
            "  c             Compose new email",
            "  D             Open drafts",
            "  s             Open sent folder",
            "  R             Refresh inbox from server",
            "  d             Mark selected as read",
            "  ? / h         This help",
            "  q             Quit",
            "",
            "  IN COMPOSE / REPLY",
            "  Tab / Enter   Next field",
            "  Shift+Tab     Previous field",
            "  Ctrl+G        Send",
            "  Esc           Cancel",
            "",
            "  Press any key to close",
        ]
        h, w  = self.scr.getmaxyx()
        bw    = max(len(l) for l in lines) + 4
        bh    = len(lines) + 2
        sy    = max(0, (h - bh) // 2)
        sx    = max(0, (w - bw) // 2)
        attr  = _a(CP_HELP, curses.A_BOLD)
        for i, line in enumerate(lines):
            _safe(self.scr, sy + i + 1, sx + 2, line.ljust(bw - 4)[:bw - 4], attr)
        self.scr.refresh()
        self.scr.getch()

    # ── compose / reply ───────────────────────────────────────────────────────

    def _send(self, payload):
        self._set_status("Sending…")
        try:
            r = api_send(payload)
            send_id = r.get("id", "")
            self.status = f"✓ Sent — ID: {send_id}"
            self.error  = ""
            sent_save(payload, send_id)
        except Exception as ex:
            self.error  = str(ex)
            self.status = ""

    def _handle_compose_result(self, result):
        """Process what ComposeView.run() returned."""
        if result is None:
            self.status = "Cancelled."
        elif isinstance(result, tuple) and result[0] == "draft":
            self.status = f"Draft saved."
        else:
            # result is the payload dict
            self._send(result)

    def do_reply(self):
        if not self.emails:
            return
        e    = self.emails[self.selected]
        eid  = e["id"]
        full = self.full_email if (self.full_email and self.full_email.get("id") == eid) else e
        cv   = ComposeView(
            self.scr,
            from_addr    = self.cfg.get("from_address", ""),
            to           = full.get("from", ""),
            subject      = f"Re: {full.get('subject', '')}",
            reply_to_mid = full.get("message_id", ""),
        )
        self._handle_compose_result(cv.run())
        self.scr.clear()

    def do_compose(self, draft=None):
        kwargs = {}
        if draft:
            kwargs = {
                "to":           draft.get("to", ""),
                "cc":           draft.get("cc", ""),
                "subject":      draft.get("subject", ""),
                "reply_to_mid": draft.get("reply_to_mid", ""),
                "initbody":     draft.get("body", ""),
            }
            # Delete the draft — it'll be re-saved if they Ctrl+D again
            draft_delete(draft["id"])
        cv = ComposeView(
            self.scr,
            from_addr = self.cfg.get("from_address", ""),
            **kwargs,
        )
        self._handle_compose_result(cv.run())
        self.scr.clear()

    def do_drafts(self):
        dv    = DraftsView(self.scr)
        draft = dv.run()
        self.scr.clear()
        if draft:
            self.do_compose(draft=draft)

    def do_sent(self):
        SentView(self.scr).run()
        self.scr.clear()

    # ── main loop ─────────────────────────────────────────────────────────────

    def run(self):
        self.refresh_list()
        REFRESH_SECS = 60
        # halfdelay(n): getch blocks at most n tenths-of-a-second, returns ERR on timeout
        curses.halfdelay(10)   # 1 second tick
        ticks_since_refresh = 0

        while True:
            self.draw()
            key = self.scr.getch()

            # Timeout (halfdelay returned ERR = -1) — tick the auto-refresh counter
            if key == -1:
                ticks_since_refresh += 1
                if ticks_since_refresh >= REFRESH_SECS:
                    ticks_since_refresh = 0
                    old_status = self.status
                    self.refresh_list()
                    # Restore status if refresh didn't produce a new error
                    if not self.error:
                        self.status = old_status
                continue

            if key in (ord('q'), ord('Q')):
                break
            elif key in (curses.KEY_UP, ord('k')):
                if self.full_email:
                    self.prev_scroll = max(0, self.prev_scroll - 1)
                elif self.selected > 0:
                    self.selected   -= 1
                    self.full_email  = None
                    self.md_lines    = []
                    self.prev_scroll = 0
            elif key in (curses.KEY_DOWN, ord('j')):
                if self.full_email:
                    self.prev_scroll += 1
                elif self.selected < len(self.emails) - 1:
                    self.selected   += 1
                    self.full_email  = None
                    self.md_lines    = []
                    self.prev_scroll = 0
            elif key in (curses.KEY_ENTER, ord('\n'), ord('\r')):
                self.load_full()
            elif key in (27, curses.KEY_LEFT):  # Esc or ← — close email, back to list
                if self.full_email:
                    self.full_email  = None
                    self.md_lines    = []
                    self.prev_scroll = 0
                    self.status = (
                        "↑↓ Navigate   Enter Open   r Reply   c Compose   "
                        "R Refresh   ? Help   q Quit"
                    )
            elif key in (curses.KEY_PPAGE, ord('K')):
                self.prev_scroll = max(0, self.prev_scroll - 10)
            elif key in (curses.KEY_NPAGE, ord('J')):
                self.prev_scroll += 10
            elif key == ord('R'):
                ticks_since_refresh = 0
                self.selected    = 0
                self.list_off    = 0
                self.full_email  = None
                self.md_lines    = []
                self.prev_scroll = 0
                self.refresh_list()
            elif key in (ord('d'), curses.KEY_DC):
                if self.emails:
                    mark_seen(self.emails[self.selected]["id"], self.seen)
            elif key == ord('r'):
                curses.nocbreak(); curses.cbreak()   # exit halfdelay before blocking compose
                self.do_reply()
                curses.halfdelay(10)
                ticks_since_refresh = 0
            elif key == ord('c'):
                curses.nocbreak(); curses.cbreak()
                self.do_compose()
                curses.halfdelay(10)
                ticks_since_refresh = 0
            elif key == ord('D'):
                curses.nocbreak(); curses.cbreak()
                self.do_drafts()
                curses.halfdelay(10)
                ticks_since_refresh = 0
            elif key == ord('s'):
                curses.nocbreak(); curses.cbreak()
                self.do_sent()
                curses.halfdelay(10)
                ticks_since_refresh = 0
            elif key in (ord('?'), ord('h')):
                curses.nocbreak(); curses.cbreak()
                self.show_help()
                curses.halfdelay(10)
            elif key == curses.KEY_RESIZE:
                self.scr.clear()
                self.full_email = None
                self.md_lines   = []

# ─────────────────────────────────────────────────────────────────────────────
# CLI helpers (non-TUI)
# ─────────────────────────────────────────────────────────────────────────────

def cli_list(args):
    if not API_KEY:
        print("Error: RESEND_API_KEY not set.", file=sys.stderr); sys.exit(1)
    cfg   = load_config()
    seen  = load_seen()
    limit = int(cfg.get("list_limit", 50))
    try:
        emails, has_more = api_list(limit)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr); sys.exit(1)
    for e in emails:
        marker = "NEW" if e["id"] not in seen else "   "
        date   = e.get("created_at", "")[:10]
        frm    = short_from(e.get("from", ""))[:30]
        subj   = e.get("subject", "(no subject)")[:60]
        print(f"[{marker}] {e['id']}  {date}  {frm:<30}  {subj}")
    if has_more:
        print("  … more emails not shown (increase list_limit in config)")


def cli_read(args):
    if not API_KEY:
        print("Error: RESEND_API_KEY not set.", file=sys.stderr); sys.exit(1)
    seen = load_seen()
    try:
        e = api_get_email(args.id)
    except Exception as ex:
        print(f"Error: {ex}", file=sys.stderr); sys.exit(1)
    print(f"From:    {e.get('from','')}")
    print(f"To:      {', '.join(e.get('to', []))}")
    if e.get("cc"):
        print(f"CC:      {', '.join(e['cc'])}")
    print(f"Subject: {e.get('subject','')}")
    print(f"Date:    {e.get('created_at','')}")
    print()
    text = e.get("text") or strip_html(e.get("html") or "") or "(no body)"
    print(text)
    mark_seen(e["id"], seen)


def cli_send(args):
    if not API_KEY:
        print("Error: RESEND_API_KEY not set.", file=sys.stderr); sys.exit(1)
    cfg = load_config()
    from_addr = args.from_addr or cfg.get("from_address", "")
    if not from_addr:
        print("Error: specify --from or set from_address in config.", file=sys.stderr)
        sys.exit(1)
    # Body: from --body flag, or stdin if piped, or interactive prompt
    if args.body:
        body = args.body
    elif not sys.stdin.isatty():
        body = sys.stdin.read()
    else:
        print("Body (Ctrl+D to finish):")
        lines = []
        try:
            while True:
                lines.append(input())
        except EOFError:
            pass
        body = "\n".join(lines)
    if not body.strip():
        print("Error: empty body.", file=sys.stderr); sys.exit(1)
    payload = {
        "from":    from_addr,
        "to":      args.to,
        "subject": args.subject,
        "text":    body,
    }
    if args.cc:
        payload["cc"] = args.cc
    if args.reply_to:
        payload["headers"] = {
            "In-Reply-To": args.reply_to,
            "References":  args.reply_to,
        }
    try:
        r = api_send(payload)
        print(f"Sent. ID: {r.get('id','?')}")
    except Exception as ex:
        print(f"Error: {ex}", file=sys.stderr); sys.exit(1)


def cli_config(args):
    cfg = load_config()
    if args.set:
        for pair in args.set:
            if "=" not in pair:
                print(f"Ignoring bad pair (expected key=value): {pair}")
                continue
            k, _, v = pair.partition("=")
            cfg[k.strip().lower()] = v.strip()
        save_config(cfg)
        print(f"Saved to {CONFIG_FILE}")
    else:
        for k, v in cfg.items():
            print(f"{k} = {v}")


# ─────────────────────────────────────────────────────────────────────────────
# TUI entry point
# ─────────────────────────────────────────────────────────────────────────────

def tui_main(stdscr):
    setup_colors()
    curses.curs_set(0)
    stdscr.keypad(True)
    curses.noecho()
    curses.cbreak()

    if not API_KEY:
        try:
            stdscr.addstr(0, 0, "  Error: RESEND_API_KEY is not set.",
                          curses.A_BOLD)
            stdscr.addstr(1, 0, "  Run:   export RESEND_API_KEY=re_xxxxxxxxxxxx")
            stdscr.addstr(3, 0, "  Press any key to exit.")
        except curses.error:
            pass
        stdscr.refresh()
        stdscr.getch()
        return

    cfg = load_config()
    if not cfg.get("from_address"):
        wizard  = SetupWizard(stdscr)
        new_cfg = wizard.run()
        if new_cfg is None:
            return
        cfg = new_cfg
        save_config(cfg)

    InboxTUI(stdscr, cfg).run()


# ─────────────────────────────────────────────────────────────────────────────
# Argument parsing
# ─────────────────────────────────────────────────────────────────────────────

def build_parser():
    p = __import__("argparse").ArgumentParser(
        prog="inbox",
        description="Terminal email client for Resend inbound mail.",
    )
    sub = p.add_subparsers(dest="cmd")

    # Default: open TUI (no subcommand)
    sub.add_parser("tui",  help="Open the interactive TUI inbox (default)")

    # list
    sub.add_parser("list", help="Print inbox as plain text and exit")

    # read
    r = sub.add_parser("read", help="Print a single email by ID and exit")
    r.add_argument("id", help="Email ID from 'inbox list'")

    # send
    s = sub.add_parser("send", help="Send an email from the command line")
    s.add_argument("--to",       required=True,  action="append",
                   metavar="ADDR", dest="to",    help="Recipient (repeatable)")
    s.add_argument("--subject",  required=True,  help="Subject line")
    s.add_argument("--body",     default="",     help="Body text (or pipe stdin)")
    s.add_argument("--from",     default="",     dest="from_addr",
                   metavar="ADDR", help="Sender (defaults to config from_address)")
    s.add_argument("--cc",       action="append", default=[],
                   metavar="ADDR", help="CC address (repeatable)")
    s.add_argument("--reply-to", default="",     dest="reply_to",
                   metavar="MSG_ID", help="Message-ID to reply to (sets In-Reply-To)")

    # config
    c = sub.add_parser("config", help="View or set config values")
    c.add_argument("set", nargs="*", metavar="key=value",
                   help="Set one or more config values, e.g. from_address=you@example.com")

    return p


def main():
    import curses as _curses_check
    parser = build_parser()
    args   = parser.parse_args()

    if args.cmd in (None, "tui"):
        _curses_check.wrapper(tui_main)
    elif args.cmd == "list":
        cli_list(args)
    elif args.cmd == "read":
        cli_read(args)
    elif args.cmd == "send":
        cli_send(args)
    elif args.cmd == "config":
        cli_config(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
