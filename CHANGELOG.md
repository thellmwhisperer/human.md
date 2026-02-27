# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.3.0](https://github.com/thellmwhisperer/human.md/compare/human-md-v1.2.0...human-md-v1.3.0) (2026-02-27)


### Features

* add open-source standards and project infrastructure ([#4](https://github.com/thellmwhisperer/human.md/issues/4)) ([8ecb9c7](https://github.com/thellmwhisperer/human.md/commit/8ecb9c704819653017d1249072b851fd2ff844f3))
* human-guard distributable — zero-dep install with wizard ([0ea4098](https://github.com/thellmwhisperer/human.md/commit/0ea40989d126de42432018ad7264fac43c8f8db3))
* human-guard distributable — zero-dep install with wizard ([fd60d46](https://github.com/thellmwhisperer/human.md/commit/fd60d4667002eaa2fab0acf04b39d5f7267482f0))
* spec v1.1 — blocked periods, wind-down, global support ([cd090ff](https://github.com/thellmwhisperer/human.md/commit/cd090ff24721460530771542b15c3d514091f4a8))


### Bug Fixes

* address CodeRabbit review findings ([f5562b8](https://github.com/thellmwhisperer/human.md/commit/f5562b85c615d7f2c627bc1d7f501c719a01113e))
* correct repo URL and hook matching pattern ([#2](https://github.com/thellmwhisperer/human.md/issues/2)) ([744906f](https://github.com/thellmwhisperer/human.md/commit/744906f6637a73f0025a16257ffb5e73f071890e))
* cumulative break enforcement + last_activity tracking ([#6](https://github.com/thellmwhisperer/human.md/issues/6)) ([a32341a](https://github.com/thellmwhisperer/human.md/commit/a32341a4df88c9068b4ced2a816c0c0cac5d5add))
* detect intra-session breaks for accurate work tracking ([#7](https://github.com/thellmwhisperer/human.md/issues/7)) ([c77de14](https://github.com/thellmwhisperer/human.md/commit/c77de1466ce8f35a6d4644d7c16fcea016a085ce))
* format examples as markdown with fenced YAML blocks ([50b5c6d](https://github.com/thellmwhisperer/human.md/commit/50b5c6d6a4e6783d7d4aeabe5bfbc306820d67b0))
* idempotent E2E test — check both .zshrc and .bashrc ([de470b6](https://github.com/thellmwhisperer/human.md/commit/de470b668a23233854cc7134c35fca285ff067eb))
* prevent notification spam with one-shot session-scoped markers ([#5](https://github.com/thellmwhisperer/human.md/issues/5)) ([3e58c57](https://github.com/thellmwhisperer/human.md/commit/3e58c578ecb00f8dd55971f7b04feb083d431a41))
* remove unused fixture params from epoch tests ([f784aac](https://github.com/thellmwhisperer/human.md/commit/f784aacffbed089fdad9aa3ee3b467a8b1d29cc1))
* skip break enforcement when active session exists in another terminal ([#3](https://github.com/thellmwhisperer/human.md/issues/3)) ([f875e4e](https://github.com/thellmwhisperer/human.md/commit/f875e4e1a49429c902917cd4788e2c6e1e93e40c))
* typo distribuible→distributable, remove global sys.path mutation ([2eb5af2](https://github.com/thellmwhisperer/human.md/commit/2eb5af27b0f864183747ceae094cf64cbfea1996))

## [1.2.0] - 2026-02-24

### Added
- Cumulative work tracking: break only required after `max_continuous_minutes` (default 150min) of total work across sessions
- `touch_session` sentinel file for accurate `last_activity` tracking
- Hook writes last interaction time on each tool use
- `_parse_naive()` helper for Z-suffix timestamp safety net

### Fixed
- Break enforcement was too aggressive — triggered after every session regardless of duration
- Aligned `check_break`/`checkBreak` signatures across Python and JS
- `end_session` now records `last_activity` from sentinel file

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
