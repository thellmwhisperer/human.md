# Security Policy

## Scope

human.md includes shell scripts that run as hooks and wrappers in the user's
terminal environment. Security issues in these components are taken seriously.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.1.x   | Yes       |
| < 1.1   | No        |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly.

**Do not open a public issue.**

Email **ssh@thellmwhisperer.dev** with:

- A description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

You will receive an acknowledgment within 48 hours. We aim to release a fix
within 7 days for confirmed vulnerabilities.

## Security Considerations

- The shell wrapper and hook execute in the user's shell context
- The installer modifies `~/.claude/settings.json` and shell RC files
- Session state is stored in `~/.claude/` with user-level permissions
- No data is transmitted externally — all enforcement is local
