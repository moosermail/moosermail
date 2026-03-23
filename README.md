# MOOSERMAIL CLI

A fast, lightweight terminal email client for Resend inbound mail. Built with pure Python stdlib (no bloated dependencies).

![inbox](mooser-comp.png)

## Features

- **Terminal TUI** — Full-featured curses interface for reading, composing, and managing emails
- **CLI mode** — Send, list, and read emails from the command line or scripts
- **Markdown rendering** — HTML emails rendered as clean markdown in the terminal
- **Drafts & Sent** — Local storage for drafts and sent messages
- **Config management** — Simple config file for API keys and preferences
- **Zero dependencies** — Uses only Python stdlib: `curses`, `urllib`, `json`
- **Works offline** — Compose and save drafts without internet

## Installation

```bash
pip install inbox-py
```

Requires: Python 3.7+, Resend account

## Quick Start

1. Export your Resend API key:
```bash
export RESEND_API_KEY="re_xxxxxxxxxxxx"
```

2. Run:
```bash
inbox
```

First run will ask for your domain and sender address. Config is saved to `~/.inboxpy.conf`.

## Usage

### Interactive TUI

```bash
inbox
```

**Keys:**
| Key | Action |
|-----|--------|
| `↑/↓` `j/k` | Navigate emails |
| `Enter` | Open email |
| `PgUp/PgDn` | Scroll preview |
| `r` | Reply |
| `c` | Compose |
| `R` | Refresh |
| `s` | Sent folder |
| `D` | Drafts |
| `d` | Mark read |
| `?` | Help |
| `q` | Quit |

**Compose Keys:**
| Key | Action |
|-----|--------|
| `Tab` / `Shift+Tab` | Next / prev field |
| `Enter` | New line (in body) |
| `Ctrl+G` | Send |
| `Ctrl+D` | Save draft |
| `Esc` | Cancel |

### Command Line

**List emails:**
```bash
inbox list
```

**Read an email:**
```bash
inbox read <email_id>
```

**Send email:**
```bash
inbox send --to user@example.com --subject "Hello" --body "Your message"
```

**Pipe body from stdin:**
```bash
echo "Email body" | inbox send --to user@example.com --subject "Test"
```

**Manage config:**
```bash
inbox config                                    # view
inbox config from_address=you@domain.com        # set
```

## Config

Location: `~/.inboxpy.conf`

```
from_address = you@domain.com
list_limit = 50
app_name = INBOX
```

Override with env vars:
```bash
export INBOX_CONFIG=~/.my_config
export INBOX_STATE=~/.my_state
export INBOX_DRAFTS=~/.my_drafts
export INBOX_SENT=~/.my_sent
```

## License

CC-BY-NC-SA 4.0 — See LICENSE file for details
