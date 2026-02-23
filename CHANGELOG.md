# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.1.0] - 2026-02-22

### Added
- Shell wrapper + PreToolUse hook enforcement (two-layer system)
- Multi-runtime support: Python 3.9+, Node 18+, Bun, Deno
- Interactive installer with configuration wizard
- Session logging and break enforcement
- Orphan session cleanup for multi-terminal workflows
- Active terminal detection — skips break enforcement when another session is running
- E2E installer tests

### Fixed
- Break enforcement skipped when active session exists in another terminal
- Repository URL and hook matching pattern corrected
- Typo in distributable path naming

## [1.0.0] - 2026-02-21

### Added
- Initial specification (v1.0)
- Core YAML parser and schedule checker
- Basic examples and templates
- Global `~/.claude/human.md` support
- Blocked periods and wind-down (spec v1.1)
- Documentation: WHY.md, INTEGRATION.md, SPEC.md
