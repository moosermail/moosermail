# moosermail

A fast, lightweight terminal email client for [Moosermail](https://mooser.email) and Resend inbound mail. Pure Python stdlib -- no dependencies.

![moosermail TUI](mooser-comp.png)

## Features

- **Terminal TUI** -- full curses interface for reading, composing, and managing emails
- **CLI mode** -- send, list, and read emails from scripts or the command line
- **Markdown rendering** -- HTML emails rendered as clean markdown in the terminal
- **Drafts and Sent** -- local storage for drafts and sent messages
- **Multiple profiles** -- manage separate accounts with named profiles via `--profile`
- **Attachment support** -- view and download email attachments from the TUI
- **Zero dependencies** -- Python stdlib only: `curses`, `urllib`, `json`

## Installation

```bash
pip install moosermail
```

Requires: Python 3.7+, a [Moosermail](https://mooser.email) account or direct Resend API access.

## Quick Start

```bash
export RESEND_API_KEY="re_xxxxxxxxxxxx"
mooser
```

First run asks for your domain and sender address. Config saves to `~/.inboxpy.conf`.

## Usage

### Interactive TUI

```bash
mooser
```

| Key | Action |
|-----|--------|
| `up/down` `j/k` | Move between emails |
| `Enter` | Open email |
| `PgUp/PgDn` | Scroll preview |
| `r` | Reply |
| `c` | Compose |
| `R` | Refresh |
| `s` | Sent folder |
| `D` | Drafts |
| `d` | Mark read |
| `a` | View attachments |
| `?` | Help |
| `q` | Quit |

**Compose:**

| Key | Action |
|-----|--------|
| `Tab` / `Shift+Tab` | Next / prev field |
| `Enter` | New line in body |
| `Ctrl+G` | Send |
| `Ctrl+D` | Save draft |
| `Esc` | Cancel |

### Command Line

```bash
# List inbox
mooser list

# Read an email
mooser read <email_id>

# Send
mooser send --to user@example.com --subject "Hello" --body "Message"

# Pipe body from stdin
echo "Email body" | mooser send --to user@example.com --subject "Test"

# Use a named profile
mooser --profile work list
mooser --profile personal send --to bob@example.com --subject "Hey"

# Manage config
mooser config
mooser config from_address=you@domain.com
```

### Multiple Profiles

Create separate named configs for different accounts:

```bash
mooser --profile work
mooser --profile personal
```

Each profile stores its config in a separate section in `~/.inboxpy.conf`. First run with a new profile name triggers setup for that profile.

## Config

Location: `~/.inboxpy.conf`

```ini
[default]
from_address = you@domain.com
list_limit = 50
app_name = MOOSER

[work]
from_address = you@company.com
list_limit = 100
app_name = WORK
```

Override defaults with env vars:

```bash
export INBOX_CONFIG=~/.my_config
export INBOX_STATE=~/.my_state
export INBOX_DRAFTS=~/.my_drafts
export INBOX_SENT=~/.my_sent
```

## Web App

The CLI pairs with the [Moosermail web app](https://app.mooser.email) -- the same inbox, accessible from any browser. Same Resend API key, same emails.

Source: [github.com/moosermail/mooser-web](https://github.com/moosermail/mooser-web)

## License

MIT
