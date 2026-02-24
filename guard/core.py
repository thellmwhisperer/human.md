#!/usr/bin/env python3
"""human-guard: Enforcement layer for the human.md framework.

Modes:
  --check              Verify schedule, write session-state.json (exit 0=ok, 1=blocked, 2=wind-down)
  --start-session      Register new session in session-log.json (prints session id)
  --end-session ID     Mark session as ended in session-log.json
  --force              Override blocks (used with --check or --start-session)
  --dir PATH           Project directory (used with --start-session)

Zero external dependencies — stdlib only.
"""

import argparse
import contextlib
import json
import sys
import uuid
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

GUARD_DIR = Path.home() / ".claude" / "human-guard"
CLAUDE_DIR = Path.home() / ".claude"
DEFAULT_STATE_PATH = CLAUDE_DIR / "session-state.json"
DEFAULT_LOG_PATH = CLAUDE_DIR / "session-log.json"
def _find_repo_root():
    """Walk up from cwd to find .git directory (repo root)."""
    p = Path.cwd().resolve()
    while p != p.parent:
        if (p / ".git").exists():
            return p
        p = p.parent
    return None


def _build_config_paths():
    """Build config search paths: cwd → repo root → global."""
    paths = [Path("human.md")]  # current dir
    repo = _find_repo_root()
    if repo and repo != Path.cwd().resolve():
        paths.append(repo / "human.md")
    paths.append(CLAUDE_DIR / "human.md")  # global
    return paths


CONFIG_SEARCH_PATHS = _build_config_paths()

# Orphan session threshold (hours)
ORPHAN_THRESHOLD_HOURS = 4


# ---------------------------------------------------------------------------
# Inline YAML parser (subset: human.md schema only)
# ---------------------------------------------------------------------------

def _parse_scalar(value):
    """Parse a YAML scalar value: int, quoted string, or bare string."""
    value = value.strip()
    if not value:
        return ""
    # Quoted string
    if (value.startswith('"') and value.endswith('"')) or \
       (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    # Integer
    try:
        return int(value)
    except ValueError:
        pass
    return value


def _strip_inline_comment(value):
    """Strip inline comments, respecting quoted strings."""
    in_quote = None
    for i, ch in enumerate(value):
        if ch in ('"', "'"):
            if in_quote == ch:
                in_quote = None
            elif in_quote is None:
                in_quote = ch
        elif ch == '#' and in_quote is None and i > 0 and value[i - 1] in (' ', '\t'):
                return value[:i].rstrip()
    return value


def parse_yaml(text):
    """Parse a limited YAML subset used by human.md.

    Supports:
    - key: value (strings, quoted strings, integers)
    - Nested objects by indentation
    - Arrays of objects (- key: val)
    - Arrays of scalars (- value)
    - Folded strings (key: >)
    - Comments (# ...)

    Returns {} on empty or broken input.
    """
    if not text or not text.strip():
        return {}

    try:
        return _do_parse_yaml(text)
    except Exception:
        return {}


def _preprocess_lines(text):
    """Normalize text and return list of (indent, stripped_content) tuples,
    skipping empty lines and comments."""
    text = text.replace('\r\n', '\n').replace('\r', '\n').replace('\t', '  ')
    result = []
    for line in text.split('\n'):
        stripped = line.lstrip()
        if not stripped or stripped.startswith('#'):
            continue
        indent = len(line) - len(stripped)
        result.append((indent, stripped))
    return result


def _do_parse_yaml(text):
    lines = _preprocess_lines(text)
    if not lines:
        return {}
    result, _ = _parse_mapping(lines, 0, 0)
    return result


def _parse_mapping(lines, idx, min_indent):
    """Parse a YAML mapping (dict). Returns (dict, next_index)."""
    result = {}
    while idx < len(lines):
        indent, stripped = lines[idx]
        if indent < min_indent:
            break
        # A mapping line must contain ':'
        if ':' not in stripped or stripped.startswith('- '):
            break
        colon_pos = stripped.index(':')
        key = stripped[:colon_pos].strip()
        if not key:
            raise ValueError("Empty key")
        rest = stripped[colon_pos + 1:].strip()

        if rest:
            rest = _strip_inline_comment(rest)

        if rest == '>':
            # Folded string
            value, idx = _parse_folded(lines, idx + 1, indent + 1)
            result[key] = value
        elif rest:
            result[key] = _parse_scalar(rest)
            idx += 1
        else:
            # No value — peek at next line to decide mapping vs sequence
            idx += 1
            if idx < len(lines) and lines[idx][0] > indent:
                next_indent, next_stripped = lines[idx]
                if next_stripped.startswith('- '):
                    value, idx = _parse_sequence(lines, idx, next_indent)
                else:
                    value, idx = _parse_mapping(lines, idx, next_indent)
                result[key] = value
            else:
                result[key] = None
    return result, idx


def _parse_sequence(lines, idx, min_indent):
    """Parse a YAML sequence (list). Returns (list, next_index)."""
    result = []
    while idx < len(lines):
        indent, stripped = lines[idx]
        if indent < min_indent:
            break
        if not stripped.startswith('- '):
            break
        content = stripped[2:].strip()
        item_indent = indent + 2  # children of this item are at indent+2

        if ':' in content and not content.startswith('"') and not content.startswith("'"):
            # Array of objects: - key: value (+ more keys on subsequent lines)
            k, _, v = content.partition(':')
            v = _strip_inline_comment(v.strip())
            obj = {k.strip(): _parse_scalar(v)}
            idx += 1
            # Parse remaining keys of this object
            while idx < len(lines):
                ni, ns = lines[idx]
                if ni < item_indent or ns.startswith('- '):
                    break
                if ':' not in ns:
                    break
                cp = ns.index(':')
                ok = ns[:cp].strip()
                ov = ns[cp + 1:].strip()
                if ov:
                    ov = _strip_inline_comment(ov)
                if ov == '>':
                    fv, idx = _parse_folded(lines, idx + 1, ni + 1)
                    obj[ok] = fv
                elif ov:
                    obj[ok] = _parse_scalar(ov)
                    idx += 1
                else:
                    idx += 1
                    if idx < len(lines) and lines[idx][0] > ni:
                        nni, nns = lines[idx]
                        if nns.startswith('- '):
                            val, idx = _parse_sequence(lines, idx, nni)
                        else:
                            val, idx = _parse_mapping(lines, idx, nni)
                        obj[ok] = val
                    else:
                        obj[ok] = None
            result.append(obj)
        else:
            # Scalar item
            result.append(_parse_scalar(content))
            idx += 1
    return result, idx


def _parse_folded(lines, idx, min_indent):
    """Parse a YAML folded string (>). Returns (string, next_index)."""
    parts = []
    while idx < len(lines):
        indent, stripped = lines[idx]
        if indent < min_indent:
            break
        parts.append(stripped)
        idx += 1
    return ' '.join(parts), idx


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_config(config_paths):
    """Load the first valid human.md config found. Returns None if none found."""
    for p in config_paths:
        p = Path(p)
        if p.exists():
            try:
                text = p.read_text()
                config = parse_yaml(text)
                if isinstance(config, dict) and config.get("framework") == "human-md":
                    return config
            except Exception:
                continue
    return None


# ---------------------------------------------------------------------------
# Schedule checking
# ---------------------------------------------------------------------------

def _parse_time(s):
    """Parse 'HH:MM' string to a time object."""
    h, m = s.split(":")
    return time(int(h), int(m))


def _time_to_minutes(t):
    """Convert time to minutes since midnight."""
    return t.hour * 60 + t.minute


def check_schedule(config, now):
    """Check if `now` (naive datetime) is within the allowed schedule.

    Returns dict with:
      status: 'ok' | 'blocked' | 'wind_down'
      reason: 'outside_hours' | 'blocked_period' | 'blocked_day' | None
      period_name: name of blocked period (if applicable)
    """
    schedule = config.get("schedule", {})
    allowed = schedule.get("allowed_hours", {})
    start = _parse_time(allowed.get("start", "00:00"))
    end = _parse_time(allowed.get("end", "23:59"))

    now_time = now.time().replace(second=0, microsecond=0)
    now_minutes = _time_to_minutes(now_time)
    start_minutes = _time_to_minutes(start)
    end_minutes = _time_to_minutes(end)

    # Check blocked days first
    blocked_days = schedule.get("blocked_days", [])
    if blocked_days:
        day_name = now.strftime("%A")
        if day_name in blocked_days:
            return {"status": "blocked", "reason": "blocked_day", "period_name": None}

    # Check allowed hours
    if end_minutes == 0:
        # end=00:00 means end of day (midnight)
        end_minutes = 24 * 60

    if start_minutes < end_minutes:
        # Normal range: e.g. 09:00 - 00:00
        in_allowed = start_minutes <= now_minutes < end_minutes
    else:
        # Overnight range: e.g. 22:00 - 06:00
        in_allowed = now_minutes >= start_minutes or now_minutes < end_minutes

    if not in_allowed:
        return {"status": "blocked", "reason": "outside_hours", "period_name": None}

    # Check blocked periods (supports overnight: start > end)
    blocked_periods = schedule.get("blocked_periods", [])
    for bp in blocked_periods:
        bp_start = _time_to_minutes(_parse_time(bp["start"]))
        bp_end = _time_to_minutes(_parse_time(bp["end"]))
        if bp_start < bp_end:
            in_blocked = bp_start <= now_minutes < bp_end
        else:
            # Overnight blocked period (e.g. 23:00-01:00)
            in_blocked = now_minutes >= bp_start or now_minutes < bp_end
        if in_blocked:
            return {
                "status": "blocked",
                "reason": "blocked_period",
                "period_name": bp.get("name", "unknown"),
            }

    # Check wind-down (from wd_start to end of allowed window)
    wind_down = schedule.get("wind_down")
    if wind_down:
        wd_start = _time_to_minutes(_parse_time(wind_down["start"]))
        if wd_start < end_minutes:
            in_wind_down = wd_start <= now_minutes < end_minutes
        else:
            # Wind-down range wraps around midnight
            in_wind_down = now_minutes >= wd_start or now_minutes < end_minutes
        if in_wind_down:
            return {"status": "wind_down", "reason": None, "period_name": None}

    return {"status": "ok", "reason": None, "period_name": None}


# ---------------------------------------------------------------------------
# Session log
# ---------------------------------------------------------------------------

def _load_log(log_path):
    """Load session log. Returns {"sessions": []} on failure."""
    try:
        if log_path.exists():
            data = json.loads(log_path.read_text())
            if isinstance(data, dict) and "sessions" in data:
                return data
    except Exception:
        pass
    return {"sessions": []}


def _save_log(log_path, data):
    """Save session log."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def _clean_notification_markers(session_id):
    """Remove one-shot notification markers for a specific session."""
    for marker in GUARD_DIR.glob(f".notified.*.{session_id}"):
        with contextlib.suppress(OSError):
            marker.rmdir()


def start_session(log_path, project_dir, forced=False):
    """Register a new session. Returns session ID."""
    log_path = Path(log_path)
    data = _load_log(log_path)
    sid = uuid.uuid4().hex[:8]
    data["sessions"].append({
        "id": sid,
        "start_time": datetime.now().astimezone().isoformat(),
        "end_time": None,
        "project_dir": str(project_dir),
        "forced": forced,
    })
    _save_log(log_path, data)
    return sid


def end_session(log_path, session_id):
    """Mark a session as ended and clean its notification markers."""
    log_path = Path(log_path)
    data = _load_log(log_path)
    for s in data["sessions"]:
        if s["id"] == session_id and s["end_time"] is None:
            s["end_time"] = datetime.now().astimezone().isoformat()
            # Read last_activity from sentinel file (written by hook on each tool use)
            activity_file = GUARD_DIR / f".activity.{session_id}"
            if activity_file.exists():
                with contextlib.suppress(Exception):
                    s["last_activity"] = activity_file.read_text().strip()
                with contextlib.suppress(OSError):
                    activity_file.unlink()
            if not s.get("last_activity"):
                s["last_activity"] = s["end_time"]
            break
    _save_log(log_path, data)
    _clean_notification_markers(session_id)


def touch_session(log_path, session_id):
    """Write last_activity sentinel file for an active session.

    Uses a separate file to avoid racing with session-log.json writes.
    The sentinel is read by end_session when the session closes.
    """
    activity_file = GUARD_DIR / f".activity.{session_id}"
    activity_file.parent.mkdir(parents=True, exist_ok=True)
    activity_file.write_text(datetime.now().astimezone().isoformat() + "\n")


def cleanup_orphan_sessions(log_path, now=None):
    """Auto-close sessions without end_time that are older than threshold."""
    log_path = Path(log_path)
    data = _load_log(log_path)
    if now is None:
        now = datetime.now()
    threshold = timedelta(hours=ORPHAN_THRESHOLD_HOURS)

    for s in data["sessions"]:
        if s["end_time"] is not None:
            continue
        try:
            start = datetime.fromisoformat(s["start_time"])
            # Make naive for comparison
            if start.tzinfo:
                start = start.replace(tzinfo=None)
            if now - start > threshold:
                s["end_time"] = s["start_time"]  # Close it at start time
                _clean_notification_markers(s["id"])
        except Exception:
            s["end_time"] = s["start_time"] if s.get("start_time") else now.isoformat()
            if s.get("id"):
                _clean_notification_markers(s["id"])

    _save_log(log_path, data)


def _parse_naive(dt_str):
    """Parse ISO datetime string to naive datetime, handling Z suffix."""
    if dt_str.endswith("Z"):
        dt_str = dt_str[:-1] + "+00:00"
    dt = datetime.fromisoformat(dt_str)
    if dt.tzinfo:
        dt = dt.replace(tzinfo=None)
    return dt


def check_break(log_path, min_break_minutes, now=None, max_continuous_minutes=150):
    """Check if enough break time has passed since last session.

    Break is only required when cumulative work time (across sessions without
    sufficient breaks between them) meets or exceeds max_continuous_minutes.

    Returns {"ok": True/False, "minutes_left": int}.
    """
    log_path = Path(log_path)
    data = _load_log(log_path)
    if now is None:
        now = datetime.now()

    sessions = data.get("sessions", [])
    if not sessions:
        return {"ok": True, "minutes_left": 0}

    # If there's an active non-orphaned session (another terminal working),
    # skip break enforcement
    for s in sessions:
        if s.get("end_time") is None and s.get("start_time"):
            try:
                start = _parse_naive(s["start_time"])
                age_hours = (now - start).total_seconds() / 3600
                if 0 <= age_hours < ORPHAN_THRESHOLD_HOURS:
                    return {"ok": True, "minutes_left": 0}
            except Exception:
                continue

    # Walk backward through ended sessions, accumulating work time.
    # Stop when we find a gap >= min_break_minutes (a real break).
    cumulative_work = 0
    last_interaction = None
    prev_session_start = None  # start of the chronologically later session

    for s in reversed(sessions):
        if not s.get("end_time") or not s.get("start_time"):
            continue
        try:
            end = _parse_naive(s["end_time"])
            start = _parse_naive(s["start_time"])
            # Get last interaction time for this session
            activity_str = s.get("last_activity")
            if activity_str:
                try:
                    session_interaction = _parse_naive(activity_str)
                except (ValueError, TypeError):
                    session_interaction = end
            else:
                session_interaction = end

            # If there was a real break between this session and the next one, stop
            if prev_session_start is not None:
                gap = (prev_session_start - session_interaction).total_seconds() / 60
                if gap >= min_break_minutes:
                    break  # Real break found — stop accumulating

            duration_min = (end - start).total_seconds() / 60
            if duration_min < min_break_minutes:
                # Trivial sessions still interrupt gap chaining
                prev_session_start = start
                continue

            cumulative_work += duration_min
            if last_interaction is None:
                last_interaction = session_interaction
            prev_session_start = start
        except Exception:
            continue

    if last_interaction is None:
        return {"ok": True, "minutes_left": 0}

    # Only require break if cumulative work >= max_continuous_minutes
    if cumulative_work < max_continuous_minutes:
        return {"ok": True, "minutes_left": 0}

    elapsed = (now - last_interaction).total_seconds() / 60
    if elapsed >= min_break_minutes:
        return {"ok": True, "minutes_left": 0}
    else:
        return {"ok": False, "minutes_left": int(min_break_minutes - elapsed)}


# ---------------------------------------------------------------------------
# Epoch computation for session-state.json
# ---------------------------------------------------------------------------

def _time_to_epoch_today(t, tz, now):
    """Convert a time to epoch for today in the given timezone."""
    dt = datetime.combine(now.date(), t, tzinfo=tz)
    return int(dt.timestamp())


def compute_session_state(config, now_dt, tz):
    """Compute the session-state.json content."""
    schedule = config.get("schedule", {})
    sessions = config.get("sessions", {})
    messages = config.get("messages", {})
    if messages is None:
        messages = {}

    now_epoch = int(now_dt.timestamp())
    max_minutes = sessions.get("max_continuous_minutes", 150)
    max_epoch = now_epoch + max_minutes * 60
    warn_epoch = now_epoch + int(max_minutes * 60 * 0.8)

    # End of allowed hours epoch
    allowed = schedule.get("allowed_hours", {})
    start_time_cfg = _parse_time(allowed.get("start", "00:00"))
    end_time = _parse_time(allowed.get("end", "23:59"))
    start_minutes = _time_to_minutes(start_time_cfg)
    end_minutes = _time_to_minutes(end_time)

    # Wind-down epoch (computed after start/end minutes for overnight check)
    wind_down = schedule.get("wind_down")
    wind_down_epoch = 0
    if wind_down:
        wd_time = _parse_time(wind_down["start"])
        wind_down_epoch = _time_to_epoch_today(wd_time, tz, now_dt)
        if end_minutes != 0 and end_minutes < start_minutes:
            # Overnight schedule: determine which instance of wind_down is relevant
            wd_minutes = _time_to_minutes(wd_time)
            now_minutes = _time_to_minutes(now_dt.time().replace(second=0, microsecond=0))
            if wd_minutes >= start_minutes:
                # Wind_down in evening portion — if we're post-midnight, use yesterday's
                if now_minutes < end_minutes:
                    wind_down_epoch -= 86400
            else:
                # Wind_down in morning portion — if we're pre-midnight, use tomorrow's
                if now_minutes >= start_minutes:
                    wind_down_epoch += 86400
    if end_minutes == 0:
        # Midnight = end of day → next day 00:00
        end_epoch = _time_to_epoch_today(time(0, 0), tz, now_dt) + 86400
    else:
        end_epoch = _time_to_epoch_today(end_time, tz, now_dt)
        # Overnight schedule: if end < start and end_epoch is in the past, it's tomorrow
        if end_minutes < start_minutes and end_epoch <= now_epoch:
            end_epoch += 86400

    # Blocked periods as epochs
    blocked_periods = []
    for bp in schedule.get("blocked_periods", []):
        bp_start = _parse_time(bp["start"])
        bp_end = _parse_time(bp["end"])
        bp_start_epoch = _time_to_epoch_today(bp_start, tz, now_dt)
        bp_end_epoch = _time_to_epoch_today(bp_end, tz, now_dt)
        # Overnight blocked period: if end < start, end is tomorrow
        if bp_end_epoch <= bp_start_epoch:
            bp_end_epoch += 86400
        # If the period starts in the future but we're inside yesterday's instance,
        # shift back by one day (e.g. 23:00-01:00, now=00:30)
        if bp_start_epoch > now_epoch:
            prev_start = bp_start_epoch - 86400
            prev_end = bp_end_epoch - 86400
            if now_epoch >= prev_start and now_epoch < prev_end:
                bp_start_epoch = prev_start
                bp_end_epoch = prev_end
        blocked_periods.append({
            "name": bp.get("name", "unknown"),
            "start_epoch": bp_start_epoch,
            "end_epoch": bp_end_epoch,
        })

    return {
        "session_id": uuid.uuid4().hex[:8],
        "start_epoch": now_epoch,
        "max_epoch": max_epoch,
        "warn_epoch": warn_epoch,
        "wind_down_epoch": wind_down_epoch,
        "end_allowed_epoch": end_epoch,
        "blocked_periods": blocked_periods,
        "enforcement": config.get("enforcement", "soft"),
        "messages": {
            "session_limit": str(messages.get("session_limit", "") or "").strip(),
            "wind_down": str(messages.get("wind_down", "") or "").strip(),
            "blocked_period": str(messages.get("blocked_period", "") or "").strip(),
            "break_reminder": str(messages.get("break_reminder", "") or "").strip(),
            "outside_hours": str(messages.get("outside_hours", "") or "").strip(),
        },
    }


# ---------------------------------------------------------------------------
# Main check() function
# ---------------------------------------------------------------------------

def check(config_paths=None, state_path=None, log_path=None, force=False, now=None):
    """Full --check flow. Returns exit code: 0=ok, 1=blocked, 2=wind-down."""
    if config_paths is None:
        config_paths = CONFIG_SEARCH_PATHS
    if state_path is None:
        state_path = DEFAULT_STATE_PATH
    if log_path is None:
        log_path = DEFAULT_LOG_PATH

    state_path = Path(state_path)
    log_path = Path(log_path)

    config = load_config(config_paths)
    if config is None:
        return 0  # No config = passthrough

    tz_name = config.get("operator", {}).get("timezone", "UTC")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")

    if now is None:
        now_dt = datetime.now(tz)
        now_naive = now_dt.replace(tzinfo=None)
    else:
        # For testing: now is naive, localize it
        now_naive = now
        now_dt = now.replace(tzinfo=tz)

    # Check schedule
    result = check_schedule(config, now_naive)
    enforcement = config.get("enforcement", "soft")

    if result["status"] == "blocked" and not force:
        msg = config.get("messages", {}).get(result["reason"], "")
        if msg:
            print(str(msg).strip(), file=sys.stderr)
        if enforcement == "advisory":
            # Advisory: warn but allow — write session state and proceed
            state = compute_session_state(config, now_dt, tz)
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))
            return 0
        return 1

    if result["status"] == "wind_down" and not force:
        msg = config.get("messages", {}).get("wind_down", "")
        if msg:
            print(str(msg).strip(), file=sys.stderr)
        # Write session state even for wind-down (session can proceed)
        state = compute_session_state(config, now_dt, tz)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))
        return 2

    # Check break
    sessions_config = config.get("sessions", {})
    min_break = sessions_config.get("min_break_minutes", 15)
    max_continuous = sessions_config.get("max_continuous_minutes", 150)
    cleanup_orphan_sessions(log_path, now_naive)
    break_result = check_break(log_path, min_break, now=now_naive, max_continuous_minutes=max_continuous)
    if not break_result["ok"] and not force:
        if enforcement == "advisory":
            print(
                f"Need {break_result['minutes_left']} more minutes of break.",
                file=sys.stderr,
            )
            state = compute_session_state(config, now_dt, tz)
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))
            return 0
        print(
            f"Need {break_result['minutes_left']} more minutes of break.",
            file=sys.stderr,
        )
        return 1

    # All good — write session state
    state = compute_session_state(config, now_dt, tz)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="human-guard enforcement")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="Check schedule and write session state")
    group.add_argument("--start-session", action="store_true", help="Register new session")
    group.add_argument("--end-session", metavar="ID", help="End a session by ID")
    group.add_argument("--touch-session", metavar="ID", help="Update last_activity for a session")

    parser.add_argument("--force", action="store_true", help="Override blocks")
    parser.add_argument("--dir", default=".", help="Project directory")

    args = parser.parse_args()

    if args.check:
        rc = check(force=args.force)
        sys.exit(rc)
    elif args.start_session:
        sid = start_session(
            log_path=DEFAULT_LOG_PATH,
            project_dir=args.dir,
            forced=args.force,
        )
        print(sid)
    elif args.end_session:
        end_session(log_path=DEFAULT_LOG_PATH, session_id=args.end_session)
    elif args.touch_session:
        touch_session(log_path=DEFAULT_LOG_PATH, session_id=args.touch_session)


if __name__ == "__main__":
    main()
