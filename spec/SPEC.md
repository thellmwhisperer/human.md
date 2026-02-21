# human.md Specification v1.0

## Overview

`human.md` is a YAML configuration file that defines the boundaries of healthy human-agent collaboration within a software development context. It is read by AI coding agents (such as Claude Code) at session start and enforced throughout the interaction.

## File Location

The agent should look for `human.md` in the following order of precedence:

1. **Project-level**: `./human.md` in the repository root (highest priority)
2. **Global-level**: `~/.claude/human.md` (fallback defaults)

Project-level files override global-level files. This allows a developer to have personal defaults while specific projects may have different requirements.

## Schema

### Root Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `version` | string | Yes | Specification version. Currently `"1.0"` |
| `framework` | string | Yes | Must be `"human-md"` |
| `operator` | object | No | Information about the human operator |
| `schedule` | object | Yes | Working hours and day restrictions |
| `sessions` | object | No | Session duration limits |
| `enforcement` | string | No | Enforcement level. Default: `"soft"` |
| `messages` | object | No | Custom messages for boundary events |

### `operator`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | No | Operator's name (for personalised messages) |
| `timezone` | string | Yes* | IANA timezone (e.g., `Europe/London`, `America/New_York`). Required if `schedule` is defined |

### `schedule`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `allowed_hours` | object | Yes | Start and end time for permitted work |
| `allowed_hours.start` | string | Yes | Start time in `HH:MM` 24-hour format |
| `allowed_hours.end` | string | Yes | End time in `HH:MM` 24-hour format |
| `blocked_days` | array | No | Days when no work is permitted. Values: `Monday`, `Tuesday`, `Wednesday`, `Thursday`, `Friday`, `Saturday`, `Sunday` |

### `sessions`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `max_continuous_minutes` | integer | No | Maximum session duration before a break is required. Default: `150` |
| `min_break_minutes` | integer | No | Minimum break duration before a new session can start. Default: `15` |

### `enforcement`

| Value | Behaviour |
|-------|-----------|
| `soft` | Agent checks boundaries and declines to proceed with engineering work if violated. Informs the operator of the reason. Will not assist with code-related tasks until boundaries are met. Default. |
| `advisory` | Agent informs the operator of boundary violations but proceeds if the operator insists. Provides periodic reminders during the session. |

### `messages`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `outside_hours` | string | No | Custom message when session is attempted outside allowed hours |
| `session_limit` | string | No | Custom message when maximum session duration is reached |
| `break_reminder` | string | No | Custom message for break reminders |

## Agent Behaviour

When an AI coding agent encounters a `human.md` file (either directly or via reference in `CLAUDE.md`), it MUST:

1. **Read the file** at the start of every new session or conversation
2. **Determine the current time** in the operator's timezone
3. **Check schedule compliance**: If the current time falls outside `allowed_hours` or on a `blocked_day`:
   - In `soft` mode: Inform the operator and decline to proceed with engineering tasks
   - In `advisory` mode: Inform the operator and proceed if they insist
4. **Track session duration**: If `sessions.max_continuous_minutes` is defined, the agent should track elapsed time and alert the operator when the limit approaches
5. **Respect the framework**: The agent should treat `human.md` constraints with the same weight as safety guidelines — they exist to protect the operator

## CLAUDE.md Integration

To activate the `human.md` framework, add the following to your project's `CLAUDE.md`:

```markdown
## Human Framework
This project adheres to the human.md framework. Before any interaction,
read ./human.md and enforce its constraints. If the current time falls
outside the allowed schedule, inform the operator and do not proceed
with engineering work.
```

The agent should check for `human.md` even without this explicit reference if a `human.md` file exists in the project root or globally.

## Example: Minimal Configuration

```yaml
version: "1.0"
framework: human-md

operator:
  timezone: "Europe/London"

schedule:
  allowed_hours:
    start: "09:00"
    end: "22:00"
```

## Example: Full Configuration

```yaml
version: "1.0"
framework: human-md

operator:
  name: "Javi"
  timezone: "Europe/London"

schedule:
  allowed_hours:
    start: "08:00"
    end: "22:00"
  blocked_days:
    - "Sunday"

sessions:
  max_continuous_minutes: 120
  min_break_minutes: 20

enforcement: soft

messages:
  outside_hours: >
    It's outside your working hours. Close the laptop. 
    Whatever it is, it'll still be here tomorrow.
  session_limit: >
    You've been at it for 2 hours. Time for a break.
    Step away, stretch, hydrate. The code isn't going anywhere.
  break_reminder: >
    Quick check — when was the last time you stood up?
```

## Versioning

This specification follows semantic versioning. The current version is `1.0`. Future versions may introduce:

- Session quality tracking
- Multi-agent coordination boundaries
- Break activity suggestions
- Integration with calendar systems

Backward compatibility will be maintained within major versions.
