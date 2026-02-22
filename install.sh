#!/bin/bash
# human-guard installer
# Usage:
#   ./install.sh                      (from cloned repo)
#   curl -fsSL .../install.sh | bash  (remote install)
set -euo pipefail

# ---------------------------------------------------------------------------
# Detect source: local repo or remote (curl|bash)
# ---------------------------------------------------------------------------
if [ -f "$(dirname "$0")/guard/core.py" ]; then
  REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
else
  REPO_DIR=$(mktemp -d)
  REPO_URL="https://raw.githubusercontent.com/teseo/human.md/main"
  echo "Downloading files..."
  curl -fsSL "$REPO_URL/guard/core.py" -o "$REPO_DIR/core.py"
  curl -fsSL "$REPO_URL/guard/core.mjs" -o "$REPO_DIR/core.mjs"
  curl -fsSL "$REPO_URL/guard/hook.sh" -o "$REPO_DIR/hook.sh"
  curl -fsSL "$REPO_URL/guard/wrapper.zsh" -o "$REPO_DIR/wrapper.zsh"
  curl -fsSL "$REPO_URL/guard/wrapper.bash" -o "$REPO_DIR/wrapper.bash"
  CLEANUP_TMPDIR=true
fi

cleanup() {
  [ "${CLEANUP_TMPDIR:-false}" = "true" ] && rm -rf "$REPO_DIR"
}
trap cleanup EXIT

GUARD_DIR="$HOME/.claude/human-guard"
CLAUDE_DIR="$HOME/.claude"
SETTINGS="$CLAUDE_DIR/settings.json"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
info()  { printf "  \033[0;32m✓\033[0m %s\n" "$1"; }
warn()  { printf "  \033[0;33m!\033[0m %s\n" "$1"; }
fail()  { printf "  \033[0;31m✗\033[0m %s\n" "$1"; exit 1; }

# ---------------------------------------------------------------------------
# 1. Check prerequisites
# ---------------------------------------------------------------------------
echo ""
echo "human-guard installer"
echo "====================="
echo ""
echo "→ Checking prerequisites..."

# jq is required for settings.json manipulation
command -v jq &>/dev/null || fail "jq is required. Install it: https://jqlang.github.io/jq/download/"
info "jq found"

# Detect runtime: python3 > node > bun > deno
RUNTIME=""
RUNTIME_CMD=""
CORE_FILE=""
if command -v python3 &>/dev/null; then
  RUNTIME="python"
  RUNTIME_CMD="python3"
  CORE_FILE="core.py"
  local_version=$(python3 --version 2>&1 | awk '{print $2}')
  info "python3 $local_version found"
elif command -v node &>/dev/null; then
  RUNTIME="node"
  RUNTIME_CMD="node"
  CORE_FILE="core.mjs"
  local_version=$(node --version 2>&1)
  info "node $local_version found"
elif command -v bun &>/dev/null; then
  RUNTIME="bun"
  RUNTIME_CMD="bun"
  CORE_FILE="core.mjs"
  info "bun found"
elif command -v deno &>/dev/null; then
  RUNTIME="deno"
  RUNTIME_CMD="deno run --allow-read --allow-write"
  CORE_FILE="core.mjs"
  info "deno found"
else
  fail "No supported runtime found (need python3, node, bun, or deno)"
fi

# ---------------------------------------------------------------------------
# 2. Detect shell
# ---------------------------------------------------------------------------
echo ""
echo "→ Detecting shell..."

USER_SHELL="$(basename "${SHELL:-/bin/bash}")"
case "$USER_SHELL" in
  zsh)  WRAPPER_FILE="wrapper.zsh"; SHELL_RC="$HOME/.zshrc"; info "zsh" ;;
  bash) WRAPPER_FILE="wrapper.bash"; SHELL_RC="$HOME/.bashrc"; info "bash" ;;
  *)    WRAPPER_FILE="wrapper.bash"; SHELL_RC="$HOME/.bashrc"; warn "Unknown shell ($USER_SHELL), defaulting to bash" ;;
esac

# ---------------------------------------------------------------------------
# 3. Install files
# ---------------------------------------------------------------------------
echo ""
echo "→ Installing files to ~/.claude/human-guard/..."

mkdir -p "$GUARD_DIR"

# Determine source path for guard files
if [ -d "$REPO_DIR/guard" ]; then
  GUARD_SRC="$REPO_DIR/guard"
else
  GUARD_SRC="$REPO_DIR"
fi

# Copy core file for detected runtime
cp "$GUARD_SRC/$CORE_FILE" "$GUARD_DIR/$CORE_FILE"
info "$CORE_FILE ($RUNTIME runtime)"

# Copy hook
cp "$GUARD_SRC/hook.sh" "$GUARD_DIR/hook.sh"
chmod +x "$GUARD_DIR/hook.sh"
info "hook.sh"

# Copy wrapper for detected shell
cp "$GUARD_SRC/$WRAPPER_FILE" "$GUARD_DIR/$WRAPPER_FILE"
info "$WRAPPER_FILE"

# Create shim
cat > "$GUARD_DIR/core" <<SHIM
#!/bin/bash
exec $RUNTIME_CMD "\$(dirname "\$0")/$CORE_FILE" "\$@"
SHIM
chmod +x "$GUARD_DIR/core"
info "core shim"

# ---------------------------------------------------------------------------
# 4. Register hook in settings.json
# ---------------------------------------------------------------------------
echo ""
echo "→ Registering hook in ~/.claude/settings.json..."

mkdir -p "$CLAUDE_DIR"

# Create settings.json if missing
if [ ! -f "$SETTINGS" ]; then
  echo '{}' > "$SETTINGS"
fi

# Validate JSON
if ! jq empty "$SETTINGS" 2>/dev/null; then
  warn "settings.json is invalid JSON — creating backup and starting fresh"
  cp "$SETTINGS" "$SETTINGS.bak"
  echo '{}' > "$SETTINGS"
fi

# Check if hook already registered
ALREADY_REGISTERED=$(jq -r "[.hooks.PreToolUse // [] | .[].hooks[]?.command // \"\" | select(contains(\"human-guard\"))] | length" "$SETTINGS" 2>/dev/null || echo 0)

if [ "$ALREADY_REGISTERED" -eq 0 ]; then
  # Backup before modifying
  cp "$SETTINGS" "$SETTINGS.bak"

  # Add hook — ensure .hooks.PreToolUse is an array, then append
  jq '.hooks //= {} | .hooks.PreToolUse //= [] | .hooks.PreToolUse += [{"hooks": [{"type": "command", "command": "~/.claude/human-guard/hook.sh"}]}]' "$SETTINGS" > "$SETTINGS.tmp"
  mv "$SETTINGS.tmp" "$SETTINGS"
  info "PreToolUse hook added"
else
  info "PreToolUse hook already registered"
fi

# ---------------------------------------------------------------------------
# 5. Add wrapper source line to shell config
# ---------------------------------------------------------------------------
echo ""
echo "→ Adding wrapper to ~/${SHELL_RC##*/}..."

SOURCE_LINE="source \"\$HOME/.claude/human-guard/$WRAPPER_FILE\""

# Create shell config if missing
touch "$SHELL_RC"

if ! grep -qF "human-guard/wrapper" "$SHELL_RC"; then
  printf '\n# human-guard: enforce human.md schedule\n%s\n' "$SOURCE_LINE" >> "$SHELL_RC"
  info "source line added"
else
  info "source line already present"
fi

# ---------------------------------------------------------------------------
# 6. Wizard: generate human.md if not exists
# ---------------------------------------------------------------------------
echo ""
echo "→ Checking for human.md configuration..."

HUMAN_MD="$CLAUDE_DIR/human.md"

if [ -f "$HUMAN_MD" ]; then
  info "human.md already exists — keeping yours"
else
  echo "  No human.md found. Let's create one!"
  echo ""

  # Detect timezone default
  DEFAULT_TZ=""
  if command -v python3 &>/dev/null; then
    DEFAULT_TZ=$(python3 -c "
try:
    import time
    import datetime
    tz = datetime.datetime.now().astimezone().tzinfo
    print(str(tz))
except: pass
" 2>/dev/null || true)
  fi
  [ -z "$DEFAULT_TZ" ] && DEFAULT_TZ="UTC"

  # --- Read input with defaults ---

  # Name
  printf "  Your name (optional): "
  read -r WIZ_NAME || WIZ_NAME=""

  # Timezone
  printf "  Timezone [%s]: " "$DEFAULT_TZ"
  read -r WIZ_TZ || WIZ_TZ=""
  WIZ_TZ="${WIZ_TZ:-$DEFAULT_TZ}"

  # Validate timezone (pass as argument, never interpolate into code)
  TZ_VALID=false
  if command -v python3 &>/dev/null; then
    python3 -c "import sys; from zoneinfo import ZoneInfo; ZoneInfo(sys.argv[1])" "$WIZ_TZ" 2>/dev/null && TZ_VALID=true
  elif command -v node &>/dev/null; then
    node -e "Intl.DateTimeFormat('en',{timeZone:process.argv[1]})" "$WIZ_TZ" 2>/dev/null && TZ_VALID=true
  else
    TZ_VALID=true  # Can't validate, trust user
  fi
  if [ "$TZ_VALID" = "false" ]; then
    warn "Could not validate timezone '$WIZ_TZ' — using UTC"
    WIZ_TZ="UTC"
  fi

  # Work start time
  printf "  Work start time (HH:MM) [09:00]: "
  read -r WIZ_START || WIZ_START=""
  WIZ_START="${WIZ_START:-09:00}"
  # Simple validation — accept if matches pattern, else default
  if ! echo "$WIZ_START" | grep -qE '^([01][0-9]|2[0-3]):[0-5][0-9]$'; then
    warn "Invalid time format '$WIZ_START' — using 09:00"
    WIZ_START="09:00"
  fi

  # Work end time
  printf "  Work end time (HH:MM) [23:00]: "
  read -r WIZ_END || WIZ_END=""
  WIZ_END="${WIZ_END:-23:00}"
  if ! echo "$WIZ_END" | grep -qE '^([01][0-9]|2[0-3]):[0-5][0-9]$'; then
    warn "Invalid time format '$WIZ_END' — using 23:00"
    WIZ_END="23:00"
  fi

  # Escape YAML special characters in user-provided strings
  yaml_escape() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    printf '%s' "$s"
  }

  # Blocked periods
  BLOCKED_YAML=""
  printf "  Any blocked periods? (e.g. family time) [y/N]: "
  read -r WIZ_BLOCKED || WIZ_BLOCKED=""
  if [ "$WIZ_BLOCKED" = "y" ] || [ "$WIZ_BLOCKED" = "Y" ]; then
    BLOCKED_YAML="  blocked_periods:"
    ADD_MORE="y"
    while [ "$ADD_MORE" = "y" ] || [ "$ADD_MORE" = "Y" ]; do
      printf "    Period name: "
      read -r BP_NAME || BP_NAME="break"
      BP_START=""
      while ! echo "$BP_START" | grep -qE '^([01][0-9]|2[0-3]):[0-5][0-9]$'; do
        printf "    Start (HH:MM): "
        read -r BP_START || BP_START="12:00"
        [ -z "$BP_START" ] && BP_START="12:00"
      done
      BP_END=""
      while ! echo "$BP_END" | grep -qE '^([01][0-9]|2[0-3]):[0-5][0-9]$'; do
        printf "    End (HH:MM): "
        read -r BP_END || BP_END="13:00"
        [ -z "$BP_END" ] && BP_END="13:00"
      done
      escaped_bp_name="$(yaml_escape "$BP_NAME")"
      BLOCKED_YAML="$BLOCKED_YAML
    - name: \"$escaped_bp_name\"
      start: \"$BP_START\"
      end: \"$BP_END\""
      printf "    Add another? [y/N]: "
      read -r ADD_MORE || ADD_MORE=""
    done
  fi

  # Wind-down
  printf "  Wind-down reminder time (HH:MM or empty to skip): "
  read -r WIZ_WIND || WIZ_WIND=""
  WIND_YAML=""
  if [ -n "$WIZ_WIND" ] && echo "$WIZ_WIND" | grep -qE '^([01][0-9]|2[0-3]):[0-5][0-9]$'; then
    WIND_YAML="  wind_down:
    start: \"$WIZ_WIND\""
  fi

  # Session limits
  printf "  Max session length in minutes [120]: "
  read -r WIZ_MAX || WIZ_MAX=""
  WIZ_MAX="${WIZ_MAX:-120}"
  # Validate positive integer
  if ! echo "$WIZ_MAX" | grep -qE '^[1-9][0-9]*$'; then
    warn "Invalid number '$WIZ_MAX' — using 120"
    WIZ_MAX="120"
  fi

  printf "  Min break between sessions in minutes [15]: "
  read -r WIZ_BREAK || WIZ_BREAK=""
  WIZ_BREAK="${WIZ_BREAK:-15}"
  if ! echo "$WIZ_BREAK" | grep -qE '^[1-9][0-9]*$'; then
    warn "Invalid number '$WIZ_BREAK' — using 15"
    WIZ_BREAK="15"
  fi

  # Enforcement
  printf "  Enforcement level (soft/advisory) [soft]: "
  read -r WIZ_ENFORCE || WIZ_ENFORCE=""
  WIZ_ENFORCE="${WIZ_ENFORCE:-soft}"
  if [ "$WIZ_ENFORCE" != "soft" ] && [ "$WIZ_ENFORCE" != "advisory" ]; then
    warn "Invalid enforcement '$WIZ_ENFORCE' — using soft"
    WIZ_ENFORCE="soft"
  fi

  # --- Generate YAML ---
  {
    echo 'version: "1.1"'
    echo 'framework: human-md'
    echo ''
    echo 'operator:'
    if [ -n "$WIZ_NAME" ]; then
      printf '  name: "%s"\n' "$(yaml_escape "$WIZ_NAME")"
    fi
    printf '  timezone: "%s"\n' "$(yaml_escape "$WIZ_TZ")"
    echo ''
    echo 'schedule:'
    echo '  allowed_hours:'
    echo "    start: \"$WIZ_START\""
    echo "    end: \"$WIZ_END\""
    if [ -n "$BLOCKED_YAML" ]; then
      echo "$BLOCKED_YAML"
    fi
    if [ -n "$WIND_YAML" ]; then
      echo "$WIND_YAML"
    fi
    echo ''
    echo 'sessions:'
    echo "  max_continuous_minutes: $WIZ_MAX"
    echo "  min_break_minutes: $WIZ_BREAK"
    echo ''
    echo "enforcement: $WIZ_ENFORCE"
  } > "$HUMAN_MD"

  echo ""
  info "Created ~/.claude/human.md"
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo "Done! Restart your shell or run: source $SHELL_RC"
echo ""
