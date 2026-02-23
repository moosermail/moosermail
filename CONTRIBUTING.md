# Contributing to inbox.py

Thanks for your interest in contributing! We appreciate your help. Please follow these guidelines to make the process smooth for everyone.

## Code of Conduct

Be respectful. Harassment, discrimination, or abusive behavior will not be tolerated. Keep discussions focused and constructive.

## How to Contribute

### Reporting Bugs

Before opening an issue:
- Check existing issues to avoid duplicates
- Provide clear steps to reproduce
- Include your Python version, OS, and terminal type
- Paste error messages/tracebacks in full

**Good bug report example:**
```
Title: Crash on resize with small terminal

Steps:
1. Start inbox.py with default terminal size
2. Resize terminal to < 40 columns
3. Press 'R' to refresh

Error: curses.error: addstr() arg 2 must be less than 80

System: macOS 13, Python 3.11, iTerm2
```

### Suggesting Features

- Explain the use case clearly
- Keep the scope focused (inbox.py is intentionally minimal)
- Check if similar features already exist
- Be open to feedback that features might not fit the project vision

### Submitting Code

1. **Fork and branch:**
   ```bash
   git checkout -b fix/issue-name
   ```

2. **Keep it focused:**
   - One feature or fix per PR
   - Don't refactor unrelated code in the same PR
   - Keep commits clean and descriptive

3. **Testing:**
   - Test your changes manually
   - Include relevant terminal sizes and configurations
   - Verify with `RESEND_API_KEY=test_key inbox --help`

4. **Code style:**
   - Follow PEP 8
   - Keep functions reasonably sized
   - Add docstrings for new functions
   - Comment non-obvious logic

5. **Commit messages:**
   ```
   Short (≤50 char) summary

   Longer explanation if needed. Why this change?
   What problem does it solve?
   ```

6. **PR description:**
   - Reference any related issues (#123)
   - Explain what your change does
   - Note any breaking changes or dependencies

## Standards

- **No external dependencies** — Keep it stdlib only (curses, urllib, json)
- **Python 3.7+** compatibility required
- **Terminal-first** — Prioritize terminal compatibility and accessibility
- **Minimal scope** — inbox.py is intentionally simple. Major features may be out of scope

## Review Process

- Be patient. Maintainers review when available
- Feedback is not rejection — iterate together
- Ask questions if something is unclear
- Respect the project's vision and constraints

## License

By contributing, you agree your work is licensed under CC-BY-NC-SA 4.0. See LICENSE file.

---

**Questions?** Open an issue or discussion. We're here to help!
