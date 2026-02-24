#!/bin/bash
# human-guard PreToolUse hook: mid-session enforcement
# Installed by human-guard — https://github.com/thellmwhisperer/human.md
#
# Reads pre-computed epochs from session-state.json and compares with current time.
# Exit 0 = ok (optionally with systemMessage), Exit 2 = block tool use.

# Consume stdin (required by hook protocol)
cat > /dev/null

STATE="$HOME/.claude/session-state.json"
[ ! -f "$STATE" ] && exit 0

NOW=$(date +%s)

# Read thresholds safely — no eval, one jq call for numeric values
VALS=$(jq -r '[.max_epoch, .warn_epoch, (.wind_down_epoch // 0), .end_allowed_epoch, .enforcement, (.blocked_periods | length)] | @tsv' "$STATE" 2>/dev/null) || exit 0
read -r MAX_EPOCH WARN_EPOCH WIND_DOWN_EPOCH END_EPOCH ENFORCEMENT BP_COUNT <<< "$VALS"

# If jq failed or values empty, bail gracefully
[ -z "$MAX_EPOCH" ] && exit 0

# --- One-shot notification helpers ---
# Marker files prevent the same informational message from firing on every tool use.
# Scoped by session ID so multiple terminals don't interfere with each other.
# Only active when launched via the wrapper (HUMAN_GUARD_SESSION_ID set).
# Without a managed session, notifications fire every time (legacy behavior).
NOTIFY_DIR="$HOME/.claude/human-guard"
SID="${HUMAN_GUARD_SESSION_ID:-}"

# Touch session activity (lightweight sentinel file, no JSON race)
if [ -n "$SID" ]; then
  date +%Y-%m-%dT%H:%M:%S > "$NOTIFY_DIR/.activity.$SID" 2>/dev/null
fi

# Emit a one-shot systemMessage (only when session-managed).
# Without SID, always emits (no suppression).
# Uses mkdir for atomic check+create (POSIX guarantee: mkdir fails if exists).
_notify_once() {
  local key="$1" msg="$2"
  if [ -n "$SID" ]; then
    mkdir "$NOTIFY_DIR/.notified.$key.$SID" 2>/dev/null || return 1
  fi
  jq -n --arg msg "$msg" '{"systemMessage": $msg}'
  return 0
}

# Check blocked periods
if [ "$BP_COUNT" -gt 0 ] 2>/dev/null; then
  BP_DATA=$(jq -r '.blocked_periods[] | "\(.start_epoch) \(.end_epoch)"' "$STATE" 2>/dev/null)
  BP_MSG=$(jq -r '.messages.blocked_period // "Blocked period active."' "$STATE")
  while read -r BP_START BP_END; do
    [ -z "$BP_START" ] && continue
    if [ "$NOW" -ge "$BP_START" ] && [ "$NOW" -lt "$BP_END" ]; then
      if [ "$ENFORCEMENT" = "soft" ]; then
        printf '%s\n' "$BP_MSG" >&2
        exit 2
      else
        jq -n --arg msg "$BP_MSG" '{"systemMessage": $msg}'
        exit 0
      fi
    fi
  done <<< "$BP_DATA"
fi

# Check outside allowed hours
if [ "$NOW" -ge "$END_EPOCH" ]; then
  if [ "$ENFORCEMENT" = "soft" ]; then
    MSG=$(jq -r '.messages.outside_hours // "Outside allowed hours."' "$STATE")
    printf '%s\n' "$MSG" >&2
    exit 2
  else
    jq -n --arg msg "$(jq -r '.messages.outside_hours // ""' "$STATE")" '{"systemMessage": $msg}'
    exit 0
  fi
fi

# Check session limit reached (informational — one-shot)
if [ "$NOW" -ge "$MAX_EPOCH" ]; then
  MSG=$(jq -r '.messages.session_limit // ""' "$STATE")
  _notify_once "session_limit" "$MSG" || true
  exit 0
fi

# Check 80% warning (informational — one-shot)
if [ "$NOW" -ge "$WARN_EPOCH" ] && [ "$NOW" -lt "$MAX_EPOCH" ]; then
  MSG=$(jq -r '.messages.break_reminder // ""' "$STATE")
  _notify_once "warn_80" "$MSG" || true
  exit 0
fi

# Check wind-down (informational — one-shot)
if [ "$WIND_DOWN_EPOCH" -gt 0 ] && [ "$NOW" -ge "$WIND_DOWN_EPOCH" ]; then
  MSG=$(jq -r '.messages.wind_down // ""' "$STATE")
  _notify_once "wind_down" "$MSG" || true
  exit 0
fi

exit 0
