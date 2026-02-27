"""Tests for guard/core.py — TDD for human-guard distributable.

Tests time checking, session logging, the full --check flow, and the inline YAML parser.
All times use Europe/London timezone to match the real human.md config.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# Import guard module from repo
GUARD_PATH = Path(__file__).resolve().parent.parent / "guard" / "core.py"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_YAML = """\
version: "1.1"
framework: human-md

operator:
  name: "Javi"
  timezone: "Europe/London"

schedule:
  allowed_hours:
    start: "09:00"
    end: "00:00"
  blocked_periods:
    - name: "family"
      start: "18:00"
      end: "21:00"
  wind_down:
    start: "23:30"

sessions:
  max_continuous_minutes: 150
  min_break_minutes: 15

enforcement: soft

messages:
  outside_hours: >
    Fuera de horario.
  blocked_period: >
    Tiempo de familia.
  wind_down: >
    Empieza a cerrar.
  session_limit: >
    Llevas 2h30.
  break_reminder: >
    ¿Te has levantado?
"""

SAMPLE_CONFIG = {
    "version": "1.1",
    "framework": "human-md",
    "operator": {"name": "Javi", "timezone": "Europe/London"},
    "schedule": {
        "allowed_hours": {"start": "09:00", "end": "00:00"},
        "blocked_periods": [{"name": "family", "start": "18:00", "end": "21:00"}],
        "wind_down": {"start": "23:30"},
    },
    "sessions": {"max_continuous_minutes": 150, "min_break_minutes": 15},
    "enforcement": "soft",
    "messages": {
        "outside_hours": "Fuera de horario.",
        "blocked_period": "Tiempo de familia.",
        "wind_down": "Empieza a cerrar.",
        "session_limit": "Llevas 2h30.",
        "break_reminder": "¿Te has levantado?",
    },
}


@pytest.fixture
def config_file(tmp_path):
    """Write sample config to a temp file and return its path."""
    p = tmp_path / "human.md"
    p.write_text(SAMPLE_YAML)
    return p


@pytest.fixture
def session_log_path(tmp_path):
    return tmp_path / "session-log.json"


@pytest.fixture
def session_state_path(tmp_path):
    return tmp_path / "session-state.json"


# ---------------------------------------------------------------------------
# Import guard module (after it exists)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _import_guard():
    """Import human_guard module. Skip all tests if it doesn't exist yet."""
    global human_guard
    import importlib
    spec = importlib.util.spec_from_file_location("human_guard", GUARD_PATH)
    if spec is None or spec.loader is None:
        pytest.skip("guard/core.py not found")
    human_guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(human_guard)


# ===========================================================================
# 0. YAML parser
# ===========================================================================

class TestYamlParser:
    """Inline YAML parser: parse_yaml()."""

    def test_empty_string(self):
        assert human_guard.parse_yaml("") == {}

    def test_empty_whitespace(self):
        assert human_guard.parse_yaml("   \n\n  ") == {}

    def test_simple_key_value(self):
        result = human_guard.parse_yaml('version: "1.1"')
        assert result["version"] == "1.1"

    def test_unquoted_string(self):
        result = human_guard.parse_yaml("framework: human-md")
        assert result["framework"] == "human-md"

    def test_integer_value(self):
        result = human_guard.parse_yaml("count: 150")
        assert result["count"] == 150

    def test_nested_object(self):
        yaml_str = "operator:\n  name: \"Javi\"\n  timezone: \"Europe/London\""
        result = human_guard.parse_yaml(yaml_str)
        assert result["operator"]["name"] == "Javi"
        assert result["operator"]["timezone"] == "Europe/London"

    def test_array_of_objects(self):
        yaml_str = (
            "items:\n"
            "  - name: \"family\"\n"
            "    start: \"18:00\"\n"
            "    end: \"21:00\"\n"
        )
        result = human_guard.parse_yaml(yaml_str)
        assert len(result["items"]) == 1
        assert result["items"][0]["name"] == "family"
        assert result["items"][0]["start"] == "18:00"

    def test_array_of_scalars(self):
        yaml_str = "days:\n  - Sunday\n  - Monday"
        result = human_guard.parse_yaml(yaml_str)
        assert result["days"] == ["Sunday", "Monday"]

    def test_folded_string(self):
        yaml_str = "msg: >\n  Hello world.\n  Second line."
        result = human_guard.parse_yaml(yaml_str)
        assert "Hello world." in result["msg"]
        assert "Second line." in result["msg"]
        # Folded: joined with space, not newline
        assert "\n" not in result["msg"]

    def test_comments_ignored(self):
        yaml_str = "# comment\nkey: value  # inline comment"
        result = human_guard.parse_yaml(yaml_str)
        assert result["key"] == "value"

    def test_full_human_md(self):
        """Parse the full sample YAML and verify structure."""
        result = human_guard.parse_yaml(SAMPLE_YAML)
        assert result["version"] == "1.1"
        assert result["framework"] == "human-md"
        assert result["operator"]["name"] == "Javi"
        assert result["operator"]["timezone"] == "Europe/London"
        assert result["schedule"]["allowed_hours"]["start"] == "09:00"
        assert result["schedule"]["allowed_hours"]["end"] == "00:00"
        assert len(result["schedule"]["blocked_periods"]) == 1
        assert result["schedule"]["blocked_periods"][0]["name"] == "family"
        assert result["schedule"]["wind_down"]["start"] == "23:30"
        assert result["sessions"]["max_continuous_minutes"] == 150
        assert result["sessions"]["min_break_minutes"] == 15
        assert result["enforcement"] == "soft"
        assert "Fuera de horario." in result["messages"]["outside_hours"]

    def test_broken_yaml_returns_empty(self):
        """Broken YAML → {} (passthrough)."""
        result = human_guard.parse_yaml(": : : [[[")
        assert result == {}

    def test_tabs_converted(self):
        yaml_str = "key:\n\tsubkey: value"
        result = human_guard.parse_yaml(yaml_str)
        assert result["key"]["subkey"] == "value"

    def test_crlf_normalized(self):
        yaml_str = "key: value\r\nother: 42"
        result = human_guard.parse_yaml(yaml_str)
        assert result["key"] == "value"
        assert result["other"] == 42

    def test_multiple_arrays_of_objects(self):
        yaml_str = (
            "periods:\n"
            "  - name: \"lunch\"\n"
            "    start: \"12:00\"\n"
            "    end: \"13:00\"\n"
            "  - name: \"family\"\n"
            "    start: \"18:00\"\n"
            "    end: \"21:00\"\n"
        )
        result = human_guard.parse_yaml(yaml_str)
        assert len(result["periods"]) == 2
        assert result["periods"][0]["name"] == "lunch"
        assert result["periods"][1]["name"] == "family"

    def test_deeply_nested(self):
        yaml_str = (
            "schedule:\n"
            "  allowed_hours:\n"
            "    start: \"09:00\"\n"
            "    end: \"00:00\"\n"
        )
        result = human_guard.parse_yaml(yaml_str)
        assert result["schedule"]["allowed_hours"]["start"] == "09:00"


# ===========================================================================
# 1. Time/schedule checking
# ===========================================================================

class TestAllowedHours:
    """allowed_hours: start=09:00, end=00:00 (midnight = end of day)."""

    def test_before_start_blocked(self):
        """08:59 → blocked."""
        fake_now = datetime(2026, 2, 22, 8, 59)
        result = human_guard.check_schedule(SAMPLE_CONFIG, fake_now)
        assert result["status"] == "blocked"
        assert result["reason"] == "outside_hours"

    def test_at_start_ok(self):
        """09:00 → ok."""
        fake_now = datetime(2026, 2, 22, 9, 0)
        result = human_guard.check_schedule(SAMPLE_CONFIG, fake_now)
        assert result["status"] == "ok"

    def test_midday_ok(self):
        """12:00 → ok (but skip if in blocked period)."""
        fake_now = datetime(2026, 2, 22, 12, 0)
        result = human_guard.check_schedule(SAMPLE_CONFIG, fake_now)
        assert result["status"] == "ok"

    def test_before_end_ok(self):
        """17:30 → ok."""
        fake_now = datetime(2026, 2, 22, 17, 30)
        result = human_guard.check_schedule(SAMPLE_CONFIG, fake_now)
        assert result["status"] == "ok"

    def test_at_midnight_blocked(self):
        """00:00 → blocked (end of allowed window)."""
        fake_now = datetime(2026, 2, 23, 0, 0)
        result = human_guard.check_schedule(SAMPLE_CONFIG, fake_now)
        assert result["status"] == "blocked"
        assert result["reason"] == "outside_hours"

    def test_deep_night_blocked(self):
        """02:00 → blocked."""
        fake_now = datetime(2026, 2, 23, 2, 0)
        result = human_guard.check_schedule(SAMPLE_CONFIG, fake_now)
        assert result["status"] == "blocked"
        assert result["reason"] == "outside_hours"


class TestBlockedPeriods:
    """blocked_periods: family 18:00-21:00."""

    def test_before_blocked_ok(self):
        """17:59 → ok."""
        fake_now = datetime(2026, 2, 22, 17, 59)
        result = human_guard.check_schedule(SAMPLE_CONFIG, fake_now)
        assert result["status"] == "ok"

    def test_at_blocked_start(self):
        """18:00 → blocked (family)."""
        fake_now = datetime(2026, 2, 22, 18, 0)
        result = human_guard.check_schedule(SAMPLE_CONFIG, fake_now)
        assert result["status"] == "blocked"
        assert result["reason"] == "blocked_period"
        assert result["period_name"] == "family"

    def test_mid_blocked(self):
        """19:30 → blocked."""
        fake_now = datetime(2026, 2, 22, 19, 30)
        result = human_guard.check_schedule(SAMPLE_CONFIG, fake_now)
        assert result["status"] == "blocked"
        assert result["reason"] == "blocked_period"

    def test_end_of_blocked(self):
        """20:59 → blocked."""
        fake_now = datetime(2026, 2, 22, 20, 59)
        result = human_guard.check_schedule(SAMPLE_CONFIG, fake_now)
        assert result["status"] == "blocked"
        assert result["reason"] == "blocked_period"

    def test_after_blocked_ok(self):
        """21:00 → ok."""
        fake_now = datetime(2026, 2, 22, 21, 0)
        result = human_guard.check_schedule(SAMPLE_CONFIG, fake_now)
        assert result["status"] == "ok"


class TestWindDown:
    """wind_down: start=23:30, ends at allowed_hours.end (00:00)."""

    def test_before_wind_down_ok(self):
        """23:29 → ok."""
        fake_now = datetime(2026, 2, 22, 23, 29)
        result = human_guard.check_schedule(SAMPLE_CONFIG, fake_now)
        assert result["status"] == "ok"

    def test_at_wind_down(self):
        """23:30 → wind_down."""
        fake_now = datetime(2026, 2, 22, 23, 30)
        result = human_guard.check_schedule(SAMPLE_CONFIG, fake_now)
        assert result["status"] == "wind_down"

    def test_during_wind_down(self):
        """23:59 → wind_down."""
        fake_now = datetime(2026, 2, 22, 23, 59)
        result = human_guard.check_schedule(SAMPLE_CONFIG, fake_now)
        assert result["status"] == "wind_down"


class TestNoBlockedPeriods:
    """Config without blocked_periods should still work."""

    def test_no_blocked_periods(self):
        config = {
            **SAMPLE_CONFIG,
            "schedule": {
                "allowed_hours": {"start": "09:00", "end": "18:00"},
            },
        }
        fake_now = datetime(2026, 2, 22, 12, 0)
        result = human_guard.check_schedule(config, fake_now)
        assert result["status"] == "ok"


class TestNoWindDown:
    """Config without wind_down should still work."""

    def test_no_wind_down_late(self):
        config = {
            **SAMPLE_CONFIG,
            "schedule": {
                "allowed_hours": {"start": "09:00", "end": "00:00"},
            },
        }
        fake_now = datetime(2026, 2, 22, 23, 50)
        result = human_guard.check_schedule(config, fake_now)
        assert result["status"] == "ok"


class TestEndBeforeStart:
    """end < start means overnight window (e.g. start=22:00, end=06:00)."""

    def test_overnight_allowed(self):
        config = {
            **SAMPLE_CONFIG,
            "schedule": {
                "allowed_hours": {"start": "22:00", "end": "06:00"},
            },
        }
        # 23:00 → ok (within 22-06 window)
        result = human_guard.check_schedule(config, datetime(2026, 2, 22, 23, 0))
        assert result["status"] == "ok"

        # 03:00 → ok
        result = human_guard.check_schedule(config, datetime(2026, 2, 23, 3, 0))
        assert result["status"] == "ok"

        # 12:00 → blocked
        result = human_guard.check_schedule(config, datetime(2026, 2, 22, 12, 0))
        assert result["status"] == "blocked"


# ===========================================================================
# 2. Session log
# ===========================================================================

class TestSessionLog:
    """Session logging: start, end, break checking."""

    def test_start_session_creates_entry(self, session_log_path):
        sid = human_guard.start_session(
            log_path=session_log_path,
            project_dir="/tmp/project",
            forced=False,
        )
        assert sid  # non-empty string
        data = json.loads(session_log_path.read_text())
        assert len(data["sessions"]) == 1
        assert data["sessions"][0]["id"] == sid
        assert data["sessions"][0]["end_time"] is None

    def test_end_session_updates_entry(self, session_log_path):
        sid = human_guard.start_session(
            log_path=session_log_path,
            project_dir="/tmp/project",
            forced=False,
        )
        human_guard.end_session(log_path=session_log_path, session_id=sid)
        data = json.loads(session_log_path.read_text())
        assert data["sessions"][0]["end_time"] is not None

    def test_break_too_short_blocked(self, session_log_path):
        """5 min break → not enough (min_break_minutes=15)."""
        now = datetime(2026, 2, 22, 12, 0)
        five_min_ago = now - timedelta(minutes=5)
        log_data = {
            "sessions": [
                {
                    "id": "old",
                    "start_time": "2026-02-22T09:00:00+00:00",
                    "end_time": five_min_ago.isoformat(),
                    "project_dir": "/tmp",
                    "forced": False,
                }
            ]
        }
        session_log_path.write_text(json.dumps(log_data))
        result = human_guard.check_break(
            log_path=session_log_path,
            min_break_minutes=15,
            now=now,
        )
        assert result["ok"] is False

    def test_break_sufficient_ok(self, session_log_path):
        """20 min break → ok."""
        now = datetime(2026, 2, 22, 12, 0)
        twenty_min_ago = now - timedelta(minutes=20)
        log_data = {
            "sessions": [
                {
                    "id": "old",
                    "start_time": "2026-02-22T10:00:00+00:00",
                    "end_time": twenty_min_ago.isoformat(),
                    "project_dir": "/tmp",
                    "forced": False,
                }
            ]
        }
        session_log_path.write_text(json.dumps(log_data))
        result = human_guard.check_break(
            log_path=session_log_path,
            min_break_minutes=15,
            now=now,
        )
        assert result["ok"] is True

    def test_orphan_session_auto_closed(self, session_log_path):
        """Session without end_time older than 4h gets auto-closed."""
        log_data = {
            "sessions": [
                {
                    "id": "orphan",
                    "start_time": "2026-02-22T06:00:00+00:00",
                    "end_time": None,
                    "project_dir": "/tmp",
                    "forced": False,
                }
            ]
        }
        session_log_path.write_text(json.dumps(log_data))
        now = datetime(2026, 2, 22, 12, 0)
        human_guard.cleanup_orphan_sessions(
            log_path=session_log_path, now=now
        )
        data = json.loads(session_log_path.read_text())
        assert data["sessions"][0]["end_time"] is not None

    def test_short_session_no_break_required(self, session_log_path):
        """Session < min_break_minutes → no break required (not a real session)."""
        now = datetime(2026, 2, 22, 12, 0)
        two_min_ago = now - timedelta(minutes=2)
        # Session that lasted only 1 minute (start 3min ago, end 2min ago)
        log_data = {
            "sessions": [
                {
                    "id": "short",
                    "start_time": (now - timedelta(minutes=3)).isoformat(),
                    "end_time": two_min_ago.isoformat(),
                    "project_dir": "/tmp",
                    "forced": False,
                }
            ]
        }
        session_log_path.write_text(json.dumps(log_data))
        result = human_guard.check_break(
            log_path=session_log_path,
            min_break_minutes=15,
            now=now,
        )
        assert result["ok"] is True

    def test_short_session_followed_by_long_session(self, session_log_path):
        """Long session ended 5min ago, then short session 1min ago → break still required."""
        now = datetime(2026, 2, 22, 12, 0)
        log_data = {
            "sessions": [
                {
                    "id": "long",
                    "start_time": (now - timedelta(minutes=160)).isoformat(),
                    "end_time": (now - timedelta(minutes=5)).isoformat(),
                    "project_dir": "/tmp",
                    "forced": False,
                },
                {
                    "id": "short",
                    "start_time": (now - timedelta(minutes=2)).isoformat(),
                    "end_time": (now - timedelta(minutes=1)).isoformat(),
                    "project_dir": "/tmp",
                    "forced": False,
                },
            ]
        }
        session_log_path.write_text(json.dumps(log_data))
        result = human_guard.check_break(
            log_path=session_log_path,
            min_break_minutes=15,
            now=now,
        )
        assert result["ok"] is False

    def test_empty_log_graceful(self, session_log_path):
        """Empty/missing log → no crash."""
        result = human_guard.check_break(
            log_path=session_log_path,
            min_break_minutes=15,
            now=datetime(2026, 2, 22, 12, 0),
        )
        assert result["ok"] is True

    def test_corrupt_log_graceful(self, session_log_path):
        """Corrupt JSON → graceful fallback."""
        session_log_path.write_text("not json at all {{{")
        result = human_guard.check_break(
            log_path=session_log_path,
            min_break_minutes=15,
            now=datetime(2026, 2, 22, 12, 0),
        )
        assert result["ok"] is True

    def test_break_skipped_when_active_session_exists(self, session_log_path):
        """Active session in another terminal → skip break enforcement."""
        now = datetime(2026, 2, 22, 12, 0)
        log_data = {
            "sessions": [
                {
                    "id": "long-done",
                    "start_time": (now - timedelta(minutes=65)).isoformat(),
                    "end_time": (now - timedelta(minutes=5)).isoformat(),
                    "project_dir": "/tmp",
                    "forced": False,
                },
                {
                    "id": "active-terminal2",
                    "start_time": (now - timedelta(minutes=10)).isoformat(),
                    "end_time": None,
                    "project_dir": "/tmp/other",
                    "forced": False,
                },
            ]
        }
        session_log_path.write_text(json.dumps(log_data))
        result = human_guard.check_break(
            log_path=session_log_path,
            min_break_minutes=15,
            now=now,
        )
        assert result["ok"] is True

    def test_break_enforced_when_no_active_sessions(self, session_log_path):
        """No active sessions → break still enforced after max_continuous work."""
        now = datetime(2026, 2, 22, 12, 0)
        log_data = {
            "sessions": [
                {
                    "id": "long-done",
                    "start_time": (now - timedelta(minutes=160)).isoformat(),
                    "end_time": (now - timedelta(minutes=5)).isoformat(),
                    "project_dir": "/tmp",
                    "forced": False,
                },
            ]
        }
        session_log_path.write_text(json.dumps(log_data))
        result = human_guard.check_break(
            log_path=session_log_path,
            min_break_minutes=15,
            now=now,
        )
        assert result["ok"] is False

    def test_break_skipped_with_multiple_active_sessions(self, session_log_path):
        """Multiple active sessions → skip break enforcement."""
        now = datetime(2026, 2, 22, 12, 0)
        log_data = {
            "sessions": [
                {
                    "id": "long-done",
                    "start_time": (now - timedelta(minutes=65)).isoformat(),
                    "end_time": (now - timedelta(minutes=2)).isoformat(),
                    "project_dir": "/tmp",
                    "forced": False,
                },
                {
                    "id": "active-t2",
                    "start_time": (now - timedelta(minutes=30)).isoformat(),
                    "end_time": None,
                    "project_dir": "/tmp/a",
                    "forced": False,
                },
                {
                    "id": "active-t3",
                    "start_time": (now - timedelta(minutes=15)).isoformat(),
                    "end_time": None,
                    "project_dir": "/tmp/b",
                    "forced": False,
                },
            ]
        }
        session_log_path.write_text(json.dumps(log_data))
        result = human_guard.check_break(
            log_path=session_log_path,
            min_break_minutes=15,
            now=now,
        )
        assert result["ok"] is True

    def test_break_not_skipped_for_orphan_active_session(self, session_log_path):
        """Orphan 'active' session (>4h old) → don't skip break."""
        now = datetime(2026, 2, 22, 12, 0)
        log_data = {
            "sessions": [
                {
                    "id": "long-done",
                    "start_time": (now - timedelta(minutes=160)).isoformat(),
                    "end_time": (now - timedelta(minutes=5)).isoformat(),
                    "project_dir": "/tmp",
                    "forced": False,
                },
                {
                    "id": "orphan-active",
                    "start_time": (now - timedelta(hours=5)).isoformat(),
                    "end_time": None,
                    "project_dir": "/tmp/old",
                    "forced": False,
                },
            ]
        }
        session_log_path.write_text(json.dumps(log_data))
        result = human_guard.check_break(
            log_path=session_log_path,
            min_break_minutes=15,
            now=now,
        )
        assert result["ok"] is False

    def test_break_not_skipped_for_future_active_session(self, session_log_path):
        """Active session with future start_time (clock skew) → don't skip break."""
        now = datetime(2026, 2, 22, 12, 0)
        log_data = {
            "sessions": [
                {
                    "id": "long-done",
                    "start_time": (now - timedelta(minutes=160)).isoformat(),
                    "end_time": (now - timedelta(minutes=5)).isoformat(),
                    "project_dir": "/tmp",
                    "forced": False,
                },
                {
                    "id": "future-active",
                    "start_time": (now + timedelta(hours=2)).isoformat(),
                    "end_time": None,
                    "project_dir": "/tmp/future",
                    "forced": False,
                },
            ]
        }
        session_log_path.write_text(json.dumps(log_data))
        result = human_guard.check_break(
            log_path=session_log_path,
            min_break_minutes=15,
            now=now,
        )
        assert result["ok"] is False

    def test_break_skipped_when_active_session_missing_end_time_key(self, session_log_path):
        """Active session with end_time key absent (malformed log) → skip break."""
        now = datetime(2026, 2, 22, 12, 0)
        log_data = {
            "sessions": [
                {
                    "id": "long-done",
                    "start_time": (now - timedelta(minutes=65)).isoformat(),
                    "end_time": (now - timedelta(minutes=5)).isoformat(),
                    "project_dir": "/tmp",
                    "forced": False,
                },
                {
                    "id": "active-no-key",
                    "start_time": (now - timedelta(minutes=10)).isoformat(),
                    "project_dir": "/tmp/other",
                    "forced": False,
                },
            ]
        }
        session_log_path.write_text(json.dumps(log_data))
        result = human_guard.check_break(
            log_path=session_log_path,
            min_break_minutes=15,
            now=now,
        )
        assert result["ok"] is True


# ===========================================================================
# 2b. last_activity — break uses last interaction, not process close time
# ===========================================================================

class TestLastActivity:
    """check_break should use last_activity (last user message) instead of end_time
    when available. This prevents false break enforcement when a session is left
    idle before closing."""

    def test_break_uses_last_activity_over_end_time(self, session_log_path):
        """User stopped interacting 30min ago but closed session 2min ago.
        Break should be 30min (ok), not 2min (blocked)."""
        now = datetime(2026, 2, 24, 16, 30)
        log_data = {
            "sessions": [
                {
                    "id": "idle-session",
                    "start_time": "2026-02-24T11:00:00",
                    "end_time": (now - timedelta(minutes=2)).isoformat(),
                    "last_activity": (now - timedelta(minutes=30)).isoformat(),
                    "project_dir": "/tmp",
                    "forced": False,
                }
            ]
        }
        session_log_path.write_text(json.dumps(log_data))
        result = human_guard.check_break(
            log_path=session_log_path,
            min_break_minutes=15,
            now=now,
        )
        assert result["ok"] is True, \
            "break should measure from last_activity (30min ago), not end_time (2min ago)"

    def test_break_falls_back_to_end_time_without_last_activity(self, session_log_path):
        """Sessions without last_activity field use end_time (backward compat)."""
        now = datetime(2026, 2, 24, 16, 30)
        log_data = {
            "sessions": [
                {
                    "id": "old-session",
                    "start_time": "2026-02-24T11:00:00",
                    "end_time": (now - timedelta(minutes=2)).isoformat(),
                    "project_dir": "/tmp",
                    "forced": False,
                }
            ]
        }
        session_log_path.write_text(json.dumps(log_data))
        result = human_guard.check_break(
            log_path=session_log_path,
            min_break_minutes=15,
            now=now,
        )
        assert result["ok"] is False, \
            "without last_activity, should fall back to end_time (2min ago = blocked)"

    def test_touch_writes_sentinel_file(self, session_log_path, tmp_path):
        """touch_session writes a sentinel file instead of modifying session-log.json."""
        guard_dir = tmp_path / "human-guard"
        guard_dir.mkdir()
        orig = human_guard.GUARD_DIR
        human_guard.GUARD_DIR = guard_dir
        try:
            sid = human_guard.start_session(
                log_path=session_log_path,
                project_dir="/tmp",
            )
            human_guard.touch_session(log_path=session_log_path, session_id=sid)
            sentinel = guard_dir / f".activity.{sid}"
            assert sentinel.exists(), "touch_session should create sentinel file"
            content = sentinel.read_text().strip()
            assert len(content) > 0, "sentinel should contain a timestamp"
        finally:
            human_guard.GUARD_DIR = orig

    def test_end_session_reads_sentinel_into_last_activity(self, session_log_path, tmp_path):
        """end_session reads the sentinel file and stores last_activity in session log."""
        guard_dir = tmp_path / "human-guard"
        guard_dir.mkdir()
        orig = human_guard.GUARD_DIR
        human_guard.GUARD_DIR = guard_dir
        try:
            sid = human_guard.start_session(
                log_path=session_log_path,
                project_dir="/tmp",
            )
            # Simulate hook writing sentinel
            sentinel = guard_dir / f".activity.{sid}"
            sentinel.write_text("2026-02-24T14:00:00+00:00\n")

            human_guard.end_session(log_path=session_log_path, session_id=sid)
            data = json.loads(session_log_path.read_text())
            session = next(s for s in data["sessions"] if s["id"] == sid)
            assert session["last_activity"] == "2026-02-24T14:00:00+00:00", \
                "end_session should read sentinel into last_activity"
            assert not sentinel.exists(), "sentinel should be cleaned up after end_session"
        finally:
            human_guard.GUARD_DIR = orig

    def test_end_session_without_sentinel_uses_end_time(self, session_log_path, tmp_path):
        """Without sentinel file, end_session sets last_activity = end_time."""
        guard_dir = tmp_path / "human-guard"
        guard_dir.mkdir()
        orig = human_guard.GUARD_DIR
        human_guard.GUARD_DIR = guard_dir
        try:
            sid = human_guard.start_session(
                log_path=session_log_path,
                project_dir="/tmp",
            )
            # No sentinel written — no hook touched the session
            human_guard.end_session(log_path=session_log_path, session_id=sid)
            data = json.loads(session_log_path.read_text())
            session = next(s for s in data["sessions"] if s["id"] == sid)
            assert session["last_activity"] == session["end_time"], \
                "without sentinel, last_activity should equal end_time"
        finally:
            human_guard.GUARD_DIR = orig

    def test_utc_z_suffix_last_activity_parsed_correctly(self, session_log_path):
        """Safety net: Z-suffix timestamps from legacy data or JS touchSession must parse correctly."""
        now = datetime(2026, 2, 24, 16, 30)
        log_data = {
            "sessions": [
                {
                    "id": "utc-z-session",
                    "start_time": "2026-02-24T11:00:00",
                    "end_time": (now - timedelta(minutes=2)).isoformat(),
                    # Hook writes: date -u +%Y-%m-%dT%H:%M:%SZ → "2026-02-24T16:00:00Z"
                    "last_activity": "2026-02-24T16:00:00Z",
                    "project_dir": "/tmp",
                    "forced": False,
                }
            ]
        }
        session_log_path.write_text(json.dumps(log_data))
        result = human_guard.check_break(
            log_path=session_log_path,
            min_break_minutes=15,
            now=now,
        )
        # last_activity is 30min ago (16:00), not 2min ago (end_time 16:28)
        assert result["ok"] is True, \
            "Z-suffix timestamp should be parsed correctly (30min break = ok)"

    def test_malformed_last_activity_falls_back_to_end_time(self, session_log_path):
        """P3: Malformed last_activity should fall back to end_time, not skip session."""
        now = datetime(2026, 2, 24, 16, 30)
        log_data = {
            "sessions": [
                {
                    "id": "bad-activity",
                    "start_time": "2026-02-24T11:00:00",
                    "end_time": (now - timedelta(minutes=2)).isoformat(),
                    "last_activity": "NOT_A_VALID_TIMESTAMP",
                    "project_dir": "/tmp",
                    "forced": False,
                }
            ]
        }
        session_log_path.write_text(json.dumps(log_data))
        result = human_guard.check_break(
            log_path=session_log_path,
            min_break_minutes=15,
            now=now,
        )
        assert result["ok"] is False, \
            "malformed last_activity should fall back to end_time (2min ago = blocked)"

    def test_no_break_when_work_below_max_continuous(self, session_log_path):
        """Break only required after max_continuous_minutes of cumulative work.
        User worked 67min (below 150min limit) → no break needed."""
        now = datetime(2026, 2, 24, 22, 10)
        log_data = {
            "sessions": [
                {
                    "id": "short-session",
                    "start_time": "2026-02-24T21:00:00",
                    "end_time": "2026-02-24T22:07:00",
                    "last_activity": "2026-02-24T22:06:00",
                    "project_dir": "/tmp",
                    "forced": False,
                }
            ]
        }
        session_log_path.write_text(json.dumps(log_data))
        result = human_guard.check_break(
            log_path=session_log_path,
            min_break_minutes=15,
            max_continuous_minutes=150,
            now=now,
        )
        assert result["ok"] is True, \
            "67 min of work is below 150min limit — no break required"

    def test_break_required_when_cumulative_exceeds_max(self, session_log_path):
        """Break required when cumulative work across sessions >= max_continuous_minutes."""
        now = datetime(2026, 2, 24, 23, 35)
        log_data = {
            "sessions": [
                {
                    "id": "session-1",
                    "start_time": "2026-02-24T21:00:00",
                    "end_time": "2026-02-24T22:20:00",
                    "last_activity": "2026-02-24T22:18:00",
                    "project_dir": "/tmp",
                    "forced": False,
                },
                {
                    "id": "session-2",
                    "start_time": "2026-02-24T22:23:00",
                    "end_time": "2026-02-24T23:33:00",
                    "last_activity": "2026-02-24T23:32:00",
                    "project_dir": "/tmp",
                    "forced": False,
                },
            ]
        }
        session_log_path.write_text(json.dumps(log_data))
        result = human_guard.check_break(
            log_path=session_log_path,
            min_break_minutes=15,
            max_continuous_minutes=150,
            now=now,
        )
        # Session 1: 80min, gap 5min (< 15min break), Session 2: 70min → cumulative 150min
        assert result["ok"] is False, \
            "150 min cumulative work (no real break between) → break required"

    def test_break_resets_after_sufficient_gap(self, session_log_path):
        """A real break (>= min_break_minutes gap) resets cumulative work counter."""
        now = datetime(2026, 2, 24, 23, 35)
        log_data = {
            "sessions": [
                {
                    "id": "session-1",
                    "start_time": "2026-02-24T20:00:00",
                    "end_time": "2026-02-24T22:00:00",
                    "last_activity": "2026-02-24T21:58:00",
                    "project_dir": "/tmp",
                    "forced": False,
                },
                {
                    "id": "session-2",
                    "start_time": "2026-02-24T22:30:00",
                    "end_time": "2026-02-24T23:33:00",
                    "last_activity": "2026-02-24T23:32:00",
                    "project_dir": "/tmp",
                    "forced": False,
                },
            ]
        }
        session_log_path.write_text(json.dumps(log_data))
        result = human_guard.check_break(
            log_path=session_log_path,
            min_break_minutes=15,
            max_continuous_minutes=150,
            now=now,
        )
        # Session 1: 120min, then 32min real break, Session 2: 63min
        # Cumulative since last break = only 63min (< 150) → no break needed
        assert result["ok"] is True, \
            "32 min break resets counter — 63 min since break is below 150 limit"

    # --- Intra-session break detection ---

    def test_long_session_with_intra_session_break_no_break_required(self, session_log_path):
        """Session open 11h33m but user idle 3h during family block.
        work_since_break=88min (< 150) → no break required."""
        now = datetime(2026, 2, 27, 22, 30)
        log_data = {
            "sessions": [{
                "id": "long-session",
                "start_time": "2026-02-27T10:56:00",
                "end_time": "2026-02-27T22:29:00",
                "last_activity": "2026-02-27T22:28:00",
                "work_since_break": 88,
                "project_dir": "/tmp",
                "forced": False,
            }]
        }
        session_log_path.write_text(json.dumps(log_data))
        result = human_guard.check_break(
            log_path=session_log_path,
            min_break_minutes=15,
            max_continuous_minutes=150,
            now=now,
        )
        assert result["ok"] is True, \
            "work_since_break (88 min) < 150 → no break required"

    def test_work_since_break_exceeds_max_break_required(self, session_log_path):
        """work_since_break exceeds max_continuous_minutes → break required."""
        now = datetime(2026, 2, 27, 22, 35)
        log_data = {
            "sessions": [{
                "id": "marathon",
                "start_time": "2026-02-27T18:00:00",
                "end_time": "2026-02-27T22:32:00",
                "last_activity": "2026-02-27T22:31:00",
                "work_since_break": 272,
                "project_dir": "/tmp",
                "forced": False,
            }]
        }
        session_log_path.write_text(json.dumps(log_data))
        result = human_guard.check_break(
            log_path=session_log_path,
            min_break_minutes=15,
            max_continuous_minutes=150,
            now=now,
        )
        assert result["ok"] is False, \
            "work_since_break (272 min) >= 150 → break required"

    def test_no_work_since_break_falls_back_to_wall_clock(self, session_log_path):
        """No work_since_break field → falls back to end-start (backwards compat)."""
        now = datetime(2026, 2, 27, 22, 35)
        log_data = {
            "sessions": [{
                "id": "old-format",
                "start_time": "2026-02-27T10:56:00",
                "end_time": "2026-02-27T22:29:00",
                "last_activity": "2026-02-27T22:28:00",
                "project_dir": "/tmp",
                "forced": False,
            }]
        }
        session_log_path.write_text(json.dumps(log_data))
        result = human_guard.check_break(
            log_path=session_log_path,
            min_break_minutes=15,
            max_continuous_minutes=150,
            now=now,
        )
        assert result["ok"] is False, \
            "without work_since_break, uses end-start (693 min) — break required"

    def test_work_since_break_chains_across_sessions(self, session_log_path):
        """work_since_break chains across sessions when gap < min_break_minutes."""
        now = datetime(2026, 2, 27, 23, 40)
        log_data = {
            "sessions": [
                {
                    "id": "session-a",
                    "start_time": "2026-02-27T21:00:00",
                    "end_time": "2026-02-27T23:00:00",
                    "last_activity": "2026-02-27T22:58:00",
                    "work_since_break": 118,
                    "project_dir": "/tmp",
                    "forced": False,
                },
                {
                    "id": "session-b",
                    "start_time": "2026-02-27T23:05:00",
                    "end_time": "2026-02-27T23:37:00",
                    "last_activity": "2026-02-27T23:36:00",
                    "work_since_break": 32,
                    "project_dir": "/tmp",
                    "forced": False,
                },
            ]
        }
        session_log_path.write_text(json.dumps(log_data))
        result = human_guard.check_break(
            log_path=session_log_path,
            min_break_minutes=15,
            max_continuous_minutes=150,
            now=now,
        )
        assert result["ok"] is False, \
            "118 + 32 = 150 min cumulative (gap 7min < 15min) → break required"

    def test_end_session_reads_work_since_break_sentinel(self, session_log_path, tmp_path):
        """end_session should read .work-since-break sentinel and store as integer."""
        guard_dir = tmp_path / "human-guard"
        guard_dir.mkdir()
        orig = human_guard.GUARD_DIR
        human_guard.GUARD_DIR = guard_dir
        try:
            sid = human_guard.start_session(
                log_path=session_log_path,
                project_dir="/tmp",
            )
            (guard_dir / f".activity.{sid}").write_text("2026-02-27T22:28:00\n")
            (guard_dir / f".work-since-break.{sid}").write_text("88\n")

            human_guard.end_session(log_path=session_log_path, session_id=sid)
            data = json.loads(session_log_path.read_text())
            session = next(s for s in data["sessions"] if s["id"] == sid)
            assert session["work_since_break"] == 88, \
                "endSession should read work-since-break sentinel as integer"
            assert not (guard_dir / f".work-since-break.{sid}").exists(), \
                "work-since-break sentinel should be cleaned up"
        finally:
            human_guard.GUARD_DIR = orig

    def test_end_session_without_wsb_sentinel_no_field(self, session_log_path, tmp_path):
        """Without work-since-break sentinel, field should not be set."""
        guard_dir = tmp_path / "human-guard"
        guard_dir.mkdir()
        orig = human_guard.GUARD_DIR
        human_guard.GUARD_DIR = guard_dir
        try:
            sid = human_guard.start_session(
                log_path=session_log_path,
                project_dir="/tmp",
            )
            (guard_dir / f".activity.{sid}").write_text("2026-02-27T22:28:00\n")

            human_guard.end_session(log_path=session_log_path, session_id=sid)
            data = json.loads(session_log_path.read_text())
            session = next(s for s in data["sessions"] if s["id"] == sid)
            assert "work_since_break" not in session, \
                "without sentinel, work_since_break should not be set"
        finally:
            human_guard.GUARD_DIR = orig


# ===========================================================================
# 2c. Notification markers — lifecycle
# ===========================================================================

class TestNotificationMarkers:
    """One-shot notification marker cleanup in end_session and orphan cleanup."""

    def test_end_session_cleans_markers(self, tmp_path, session_log_path):
        """end_session removes notification markers for that session."""
        guard_dir = tmp_path / "human-guard"
        guard_dir.mkdir()
        # Monkey-patch GUARD_DIR for this test
        original = human_guard.GUARD_DIR
        human_guard.GUARD_DIR = guard_dir
        try:
            sid = human_guard.start_session(
                log_path=session_log_path,
                project_dir="/tmp",
            )
            # Create markers (directories, matching atomic mkdir in hook.sh)
            (guard_dir / f".notified.session_limit.{sid}").mkdir()
            (guard_dir / f".notified.warn_80.{sid}").mkdir()
            assert (guard_dir / f".notified.session_limit.{sid}").exists()

            human_guard.end_session(log_path=session_log_path, session_id=sid)

            assert not (guard_dir / f".notified.session_limit.{sid}").exists()
            assert not (guard_dir / f".notified.warn_80.{sid}").exists()
        finally:
            human_guard.GUARD_DIR = original

    def test_end_session_only_cleans_own_markers(self, tmp_path, session_log_path):
        """end_session for sessA must not touch sessB's markers."""
        guard_dir = tmp_path / "human-guard"
        guard_dir.mkdir()
        original = human_guard.GUARD_DIR
        human_guard.GUARD_DIR = guard_dir
        try:
            sidA = human_guard.start_session(
                log_path=session_log_path, project_dir="/tmp"
            )
            sidB = human_guard.start_session(
                log_path=session_log_path, project_dir="/tmp"
            )
            (guard_dir / f".notified.session_limit.{sidA}").mkdir()
            (guard_dir / f".notified.session_limit.{sidB}").mkdir()

            human_guard.end_session(log_path=session_log_path, session_id=sidA)

            # A's marker gone, B's intact
            assert not (guard_dir / f".notified.session_limit.{sidA}").exists()
            assert (guard_dir / f".notified.session_limit.{sidB}").exists()
        finally:
            human_guard.GUARD_DIR = original

    def test_orphan_cleanup_removes_markers(self, tmp_path, session_log_path):
        """cleanup_orphan_sessions removes markers for auto-closed sessions."""
        guard_dir = tmp_path / "human-guard"
        guard_dir.mkdir()
        original = human_guard.GUARD_DIR
        human_guard.GUARD_DIR = guard_dir
        try:
            now = datetime(2026, 2, 22, 12, 0)
            log_data = {
                "sessions": [
                    {
                        "id": "orphan1",
                        "start_time": "2026-02-22T06:00:00+00:00",
                        "end_time": None,
                        "project_dir": "/tmp",
                        "forced": False,
                    }
                ]
            }
            session_log_path.write_text(json.dumps(log_data))
            (guard_dir / ".notified.session_limit.orphan1").mkdir()
            (guard_dir / ".notified.warn_80.orphan1").mkdir()

            human_guard.cleanup_orphan_sessions(
                log_path=session_log_path, now=now
            )

            assert not (guard_dir / ".notified.session_limit.orphan1").exists()
            assert not (guard_dir / ".notified.warn_80.orphan1").exists()
        finally:
            human_guard.GUARD_DIR = original

    def test_end_session_no_markers_no_error(self, tmp_path, session_log_path):
        """end_session works fine when no markers exist."""
        guard_dir = tmp_path / "human-guard"
        guard_dir.mkdir()
        original = human_guard.GUARD_DIR
        human_guard.GUARD_DIR = guard_dir
        try:
            sid = human_guard.start_session(
                log_path=session_log_path, project_dir="/tmp"
            )
            # No markers created — should not raise
            human_guard.end_session(log_path=session_log_path, session_id=sid)
        finally:
            human_guard.GUARD_DIR = original


# ===========================================================================
# 3. check() integration — full --check flow
# ===========================================================================

class TestCheckIntegration:
    """Full check() function: config loading, schedule, session state output."""

    def test_no_config_passthrough(self, tmp_path, session_state_path, session_log_path):
        """No human.md → exit 0 (passthrough, no enforcement)."""
        rc = human_guard.check(
            config_paths=[tmp_path / "nonexistent.md"],
            state_path=session_state_path,
            log_path=session_log_path,
            force=False,
            now=datetime(2026, 2, 22, 3, 0),
        )
        assert rc == 0

    def test_corrupt_yaml_passthrough(self, tmp_path, session_state_path, session_log_path):
        """Corrupt YAML → exit 0 (passthrough)."""
        bad = tmp_path / "human.md"
        bad.write_text(": : : not: valid: yaml: [[[")
        rc = human_guard.check(
            config_paths=[bad],
            state_path=session_state_path,
            log_path=session_log_path,
            force=False,
            now=datetime(2026, 2, 22, 12, 0),
        )
        assert rc == 0

    def test_blocked_returns_1(self, config_file, session_state_path, session_log_path):
        """Outside hours → exit 1."""
        rc = human_guard.check(
            config_paths=[config_file],
            state_path=session_state_path,
            log_path=session_log_path,
            force=False,
            now=datetime(2026, 2, 22, 3, 0),
        )
        assert rc == 1

    def test_wind_down_returns_2(self, config_file, session_state_path, session_log_path):
        """Wind-down → exit 2 (warning, but proceed)."""
        rc = human_guard.check(
            config_paths=[config_file],
            state_path=session_state_path,
            log_path=session_log_path,
            force=False,
            now=datetime(2026, 2, 22, 23, 45),
        )
        assert rc == 2

    def test_ok_writes_session_state(self, config_file, session_state_path, session_log_path):
        """OK check → writes session-state.json with correct epochs."""
        rc = human_guard.check(
            config_paths=[config_file],
            state_path=session_state_path,
            log_path=session_log_path,
            force=False,
            now=datetime(2026, 2, 22, 12, 0),
        )
        assert rc == 0
        state = json.loads(session_state_path.read_text())
        assert "session_id" in state
        assert "start_epoch" in state
        assert "max_epoch" in state
        assert "warn_epoch" in state
        assert state["max_epoch"] == state["start_epoch"] + 150 * 60
        assert state["warn_epoch"] == state["start_epoch"] + int(150 * 60 * 0.8)
        assert state["enforcement"] == "soft"
        assert len(state["blocked_periods"]) == 1
        assert state["blocked_periods"][0]["name"] == "family"

    def test_force_overrides_block(self, config_file, session_state_path, session_log_path):
        """--force → exit 0 even when blocked."""
        rc = human_guard.check(
            config_paths=[config_file],
            state_path=session_state_path,
            log_path=session_log_path,
            force=True,
            now=datetime(2026, 2, 22, 3, 0),
        )
        assert rc == 0

    def test_blocked_period_returns_1(self, config_file, session_state_path, session_log_path):
        """During family time → exit 1."""
        rc = human_guard.check(
            config_paths=[config_file],
            state_path=session_state_path,
            log_path=session_log_path,
            force=False,
            now=datetime(2026, 2, 22, 19, 0),
        )
        assert rc == 1

    def test_session_state_has_messages(self, config_file, session_state_path, session_log_path):
        """Session state includes all configured messages."""
        human_guard.check(
            config_paths=[config_file],
            state_path=session_state_path,
            log_path=session_log_path,
            force=False,
            now=datetime(2026, 2, 22, 12, 0),
        )
        state = json.loads(session_state_path.read_text())
        assert "messages" in state
        assert "session_limit" in state["messages"]
        assert "wind_down" in state["messages"]
        assert "outside_hours" in state["messages"]
        assert "break_reminder" in state["messages"]
        assert "blocked_period" in state["messages"]

    def test_session_state_has_min_break_seconds(self, config_file, session_state_path, session_log_path):
        """Session state includes min_break_seconds for hook intra-session break detection."""
        human_guard.check(
            config_paths=[config_file],
            state_path=session_state_path,
            log_path=session_log_path,
            force=False,
            now=datetime(2026, 2, 22, 12, 0),
        )
        state = json.loads(session_state_path.read_text())
        assert state["min_break_seconds"] == 900, \
            "min_break_seconds should be 15 * 60 = 900"


class TestOvernightBlockedPeriods:
    """blocked_periods with start > end (e.g. 23:00-01:00)."""

    def test_overnight_blocked_during(self):
        """23:30 → blocked when period is 23:00-01:00."""
        config = {
            **SAMPLE_CONFIG,
            "schedule": {
                "allowed_hours": {"start": "00:00", "end": "23:59"},
                "blocked_periods": [{"name": "night", "start": "23:00", "end": "01:00"}],
            },
        }
        result = human_guard.check_schedule(config, datetime(2026, 2, 22, 23, 30))
        assert result["status"] == "blocked"
        assert result["reason"] == "blocked_period"

    def test_overnight_blocked_after_midnight(self):
        """00:30 → blocked when period is 23:00-01:00."""
        config = {
            **SAMPLE_CONFIG,
            "schedule": {
                "allowed_hours": {"start": "00:00", "end": "23:59"},
                "blocked_periods": [{"name": "night", "start": "23:00", "end": "01:00"}],
            },
        }
        result = human_guard.check_schedule(config, datetime(2026, 2, 23, 0, 30))
        assert result["status"] == "blocked"
        assert result["reason"] == "blocked_period"

    def test_overnight_blocked_end_exclusive(self):
        """01:00 → ok (end is exclusive)."""
        config = {
            **SAMPLE_CONFIG,
            "schedule": {
                "allowed_hours": {"start": "00:00", "end": "23:59"},
                "blocked_periods": [{"name": "night", "start": "23:00", "end": "01:00"}],
            },
        }
        result = human_guard.check_schedule(config, datetime(2026, 2, 23, 1, 0))
        assert result["status"] == "ok"


class TestOvernightEpochs:
    """Overnight schedule epoch computation."""

    def test_overnight_end_epoch_greater_than_start(self):
        """22:00-06:00 schedule at 23:00: end_allowed_epoch must be > start_epoch."""
        from zoneinfo import ZoneInfo
        config = {**SAMPLE_CONFIG}
        config["schedule"] = {"allowed_hours": {"start": "22:00", "end": "06:00"}}
        now = datetime(2026, 2, 22, 23, 0, tzinfo=ZoneInfo("Europe/London"))
        state = human_guard.compute_session_state(config, now, ZoneInfo("Europe/London"))
        assert state["end_allowed_epoch"] > state["start_epoch"]

    def test_overnight_blocked_period_epoch(self):
        """23:00-01:00 blocked period: end_epoch must be > start_epoch when checked at 23:30."""
        from zoneinfo import ZoneInfo
        config = {**SAMPLE_CONFIG}
        config["schedule"] = {
            "allowed_hours": {"start": "00:00", "end": "23:59"},
            "blocked_periods": [{"name": "night", "start": "23:00", "end": "01:00"}],
        }
        now = datetime(2026, 2, 22, 23, 30, tzinfo=ZoneInfo("Europe/London"))
        state = human_guard.compute_session_state(config, now, ZoneInfo("Europe/London"))
        bp = state["blocked_periods"][0]
        assert bp["end_epoch"] > bp["start_epoch"]


class TestWindDownOvernight:
    """Finding 3: wind_down broken for overnight schedules."""

    def test_overnight_wind_down_not_triggered_early(self):
        """22:00-06:00 with wind_down 05:30 → at 23:00 should be ok, not wind_down."""
        config = {
            **SAMPLE_CONFIG,
            "schedule": {
                "allowed_hours": {"start": "22:00", "end": "06:00"},
                "wind_down": {"start": "05:30"},
            },
        }
        result = human_guard.check_schedule(config, datetime(2026, 2, 22, 23, 0))
        assert result["status"] == "ok"

    def test_overnight_wind_down_triggered_near_end(self):
        """22:00-06:00 with wind_down 05:30 → at 05:30 should be wind_down."""
        config = {
            **SAMPLE_CONFIG,
            "schedule": {
                "allowed_hours": {"start": "22:00", "end": "06:00"},
                "wind_down": {"start": "05:30"},
            },
        }
        result = human_guard.check_schedule(config, datetime(2026, 2, 23, 5, 30))
        assert result["status"] == "wind_down"

    def test_overnight_wind_down_boundary(self):
        """22:00-06:00 with wind_down 05:30 → at 05:59 should be wind_down."""
        config = {
            **SAMPLE_CONFIG,
            "schedule": {
                "allowed_hours": {"start": "22:00", "end": "06:00"},
                "wind_down": {"start": "05:30"},
            },
        }
        result = human_guard.check_schedule(config, datetime(2026, 2, 23, 5, 59))
        assert result["status"] == "wind_down"

    def test_standard_wind_down_still_works(self):
        """09:00-00:00 with wind_down 23:30 → at 23:30 should be wind_down (regression check)."""
        result = human_guard.check_schedule(SAMPLE_CONFIG, datetime(2026, 2, 22, 23, 30))
        assert result["status"] == "wind_down"

    def test_standard_before_wind_down_ok(self):
        """09:00-00:00 with wind_down 23:30 → at 23:29 should be ok."""
        result = human_guard.check_schedule(SAMPLE_CONFIG, datetime(2026, 2, 22, 23, 29))
        assert result["status"] == "ok"


class TestAdvisoryEnforcement:
    """Finding 1 (Audit 3): advisory enforcement in check()."""

    def test_advisory_outside_hours_allows(self, tmp_path):
        """advisory + outside hours → exit 0 (not 1)."""
        config_path = tmp_path / "human.md"
        config_path.write_text(
            'version: "1.1"\nframework: human-md\noperator:\n  timezone: "UTC"\n'
            'schedule:\n  allowed_hours:\n    start: "09:00"\n    end: "18:00"\n'
            'enforcement: advisory\n'
        )
        state_path = tmp_path / "session-state.json"
        log_path = tmp_path / "session-log.json"
        rc = human_guard.check(
            config_paths=[config_path],
            state_path=state_path,
            log_path=log_path,
            force=False,
            now=datetime(2026, 2, 22, 3, 0),
        )
        assert rc == 0

    def test_advisory_writes_session_state(self, tmp_path):
        """advisory blocked → still writes session-state.json."""
        config_path = tmp_path / "human.md"
        config_path.write_text(
            'version: "1.1"\nframework: human-md\noperator:\n  timezone: "UTC"\n'
            'schedule:\n  allowed_hours:\n    start: "09:00"\n    end: "18:00"\n'
            'enforcement: advisory\n'
        )
        state_path = tmp_path / "session-state.json"
        log_path = tmp_path / "session-log.json"
        human_guard.check(
            config_paths=[config_path],
            state_path=state_path,
            log_path=log_path,
            force=False,
            now=datetime(2026, 2, 22, 3, 0),
        )
        state = json.loads(state_path.read_text())
        assert "session_id" in state
        assert state["enforcement"] == "advisory"

    def test_advisory_blocked_period_allows(self, tmp_path):
        """advisory + blocked_period → exit 0."""
        config_path = tmp_path / "human.md"
        config_path.write_text(
            'version: "1.1"\nframework: human-md\noperator:\n  timezone: "UTC"\n'
            'schedule:\n  allowed_hours:\n    start: "00:00"\n    end: "23:59"\n'
            '  blocked_periods:\n    - name: "family"\n      start: "18:00"\n      end: "21:00"\n'
            'enforcement: advisory\n'
        )
        state_path = tmp_path / "session-state.json"
        log_path = tmp_path / "session-log.json"
        rc = human_guard.check(
            config_paths=[config_path],
            state_path=state_path,
            log_path=log_path,
            force=False,
            now=datetime(2026, 2, 22, 19, 0),
        )
        assert rc == 0

    def test_soft_still_blocks(self, tmp_path):
        """soft + outside hours → exit 1 (regression)."""
        config_path = tmp_path / "human.md"
        config_path.write_text(
            'version: "1.1"\nframework: human-md\noperator:\n  timezone: "UTC"\n'
            'schedule:\n  allowed_hours:\n    start: "09:00"\n    end: "18:00"\n'
            'enforcement: soft\n'
        )
        state_path = tmp_path / "session-state.json"
        log_path = tmp_path / "session-log.json"
        rc = human_guard.check(
            config_paths=[config_path],
            state_path=state_path,
            log_path=log_path,
            force=False,
            now=datetime(2026, 2, 22, 3, 0),
        )
        assert rc == 1


class TestWindDownEpochOvernight:
    """Finding 3 (Audit 3): wind_down_epoch overnight in computeSessionState."""

    def test_pre_midnight_session_post_midnight_wind_down(self):
        """22:00-06:00, wind_down 05:30, session at 23:00 → epoch in future."""
        from zoneinfo import ZoneInfo
        config = {
            **SAMPLE_CONFIG,
            "schedule": {
                "allowed_hours": {"start": "22:00", "end": "06:00"},
                "wind_down": {"start": "05:30"},
            },
        }
        tz = ZoneInfo("UTC")
        now_dt = datetime(2026, 2, 22, 23, 0, tzinfo=tz)
        now_epoch = int(now_dt.timestamp())
        state = human_guard.compute_session_state(config, now_dt, tz)
        assert state["wind_down_epoch"] > now_epoch, (
            f"wind_down_epoch ({state['wind_down_epoch']}) should be > now ({now_epoch})"
        )


    def test_pre_midnight_wind_down_post_midnight_session(self):
        """22:00-06:00, wind_down 23:30, session at 01:00 → epoch in the past."""
        from zoneinfo import ZoneInfo
        config = {
            **SAMPLE_CONFIG,
            "schedule": {
                "allowed_hours": {"start": "22:00", "end": "06:00"},
                "wind_down": {"start": "23:30"},
            },
        }
        tz = ZoneInfo("UTC")
        now_dt = datetime(2026, 2, 23, 1, 0, tzinfo=tz)
        now_epoch = int(now_dt.timestamp())
        state = human_guard.compute_session_state(config, now_dt, tz)
        assert state["wind_down_epoch"] <= now_epoch, (
            f"wind_down_epoch ({state['wind_down_epoch']}) should be <= now ({now_epoch})"
        )


class TestBlockedPeriodEpochOvernight:
    """Finding 4 (Audit 3): blocked_period overnight epoch anchoring."""

    def test_force_at_0030_inside_2300_0100(self):
        """--force at 00:30 inside 23:00-01:00 → epoch contains now."""
        from zoneinfo import ZoneInfo
        config = {
            **SAMPLE_CONFIG,
            "schedule": {
                "allowed_hours": {"start": "00:00", "end": "23:59"},
                "blocked_periods": [{"name": "night", "start": "23:00", "end": "01:00"}],
            },
        }
        tz = ZoneInfo("UTC")
        now_dt = datetime(2026, 2, 23, 0, 30, tzinfo=tz)
        now_epoch = int(now_dt.timestamp())
        state = human_guard.compute_session_state(config, now_dt, tz)
        bp = state["blocked_periods"][0]
        assert now_epoch >= bp["start_epoch"] and now_epoch < bp["end_epoch"], (
            f"now ({now_epoch}) should be in [{bp['start_epoch']}, {bp['end_epoch']})"
        )


class TestBlockedDays:
    """blocked_days support."""

    def test_blocked_day(self):
        config = {
            **SAMPLE_CONFIG,
            "schedule": {
                **SAMPLE_CONFIG["schedule"],
                "blocked_days": ["Sunday"],
            },
        }
        # 2026-02-22 is a Sunday
        fake_now = datetime(2026, 2, 22, 12, 0)
        result = human_guard.check_schedule(config, fake_now)
        assert result["status"] == "blocked"
        assert result["reason"] == "blocked_day"

    def test_non_blocked_day(self):
        config = {
            **SAMPLE_CONFIG,
            "schedule": {
                **SAMPLE_CONFIG["schedule"],
                "blocked_days": ["Sunday"],
            },
        }
        # 2026-02-23 is a Monday
        fake_now = datetime(2026, 2, 23, 12, 0)
        result = human_guard.check_schedule(config, fake_now)
        assert result["status"] == "ok"
