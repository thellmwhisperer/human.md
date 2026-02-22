#!/bin/bash
# E2E tests for install.sh, wizard, and uninstall.sh
# Runs in a sandboxed $HOME to avoid touching the real system.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PASS=0
FAIL=0
ERRORS=""

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

setup_sandbox() {
  SANDBOX=$(mktemp -d)
  export HOME="$SANDBOX"
  mkdir -p "$HOME/.claude"
  mkdir -p "$SANDBOX/bin"
  printf '#!/bin/bash\necho "claude mock"\n' > "$SANDBOX/bin/claude"
  chmod +x "$SANDBOX/bin/claude"
  local real_jq real_python real_node
  real_jq="$(command -v jq 2>/dev/null || true)"
  real_python="$(command -v python3 2>/dev/null || true)"
  real_node="$(command -v node 2>/dev/null || true)"
  [ -n "$real_jq" ] && ln -sf "$real_jq" "$SANDBOX/bin/jq"
  [ -n "$real_python" ] && ln -sf "$real_python" "$SANDBOX/bin/python3"
  [ -n "$real_node" ] && ln -sf "$real_node" "$SANDBOX/bin/node"
  export PATH="$SANDBOX/bin:$PATH"
  touch "$HOME/.zshrc" "$HOME/.bashrc"
}

teardown_sandbox() {
  [ -n "${SANDBOX:-}" ] && rm -rf "$SANDBOX"
}

run_test() {
  local name="$1" func="$2"
  setup_sandbox
  local result=0
  ( set -e; "$func" ) 2>&1 || result=$?
  if [ $result -eq 0 ]; then
    printf "${GREEN}  PASS${NC} %s\n" "$name"
    PASS=$((PASS + 1))
  else
    printf "${RED}  FAIL${NC} %s\n" "$name"
    FAIL=$((FAIL + 1))
    ERRORS="${ERRORS}\n  - ${name}"
  fi
  teardown_sandbox
}

run_install_defaults() {
  printf '\n\n\n\n\n\n\n\n\n' | bash "$SCRIPT_DIR/install.sh" 2>/dev/null
}

run_uninstall() {
  printf 'y\n' | bash "$SCRIPT_DIR/uninstall.sh" 2>/dev/null
}

# === Installer tests ===

test_install_creates_all_files() {
  run_install_defaults
  [ -f "$HOME/.claude/human-guard/core" ]
  [ -f "$HOME/.claude/human-guard/hook.sh" ]
  [ -f "$HOME/.claude/human-guard/core.py" ] || [ -f "$HOME/.claude/human-guard/core.mjs" ]
  [ -f "$HOME/.claude/human-guard/wrapper.zsh" ] || [ -f "$HOME/.claude/human-guard/wrapper.bash" ]
}

test_install_core_shim_executable() {
  run_install_defaults
  [ -x "$HOME/.claude/human-guard/core" ]
  "$HOME/.claude/human-guard/core" --check 2>/dev/null || true
}

test_install_hook_registered() {
  echo '{}' > "$HOME/.claude/settings.json"
  run_install_defaults
  jq -e '.hooks.PreToolUse' "$HOME/.claude/settings.json" > /dev/null
  jq -r '.hooks.PreToolUse[].hooks[].command' "$HOME/.claude/settings.json" | grep -q 'human-guard'
}

test_install_source_line_added() {
  run_install_defaults
  grep -qF 'human-guard/wrapper' "$HOME/.zshrc" || grep -qF 'human-guard/wrapper' "$HOME/.bashrc"
}

test_install_idempotent() {
  echo '{}' > "$HOME/.claude/settings.json"
  run_install_defaults
  run_install_defaults
  local hook_count
  hook_count=$(jq '[.hooks.PreToolUse[].hooks[].command | select(contains("human-guard"))] | length' "$HOME/.claude/settings.json")
  [ "$hook_count" -eq 1 ]
  local zsh_count bash_count
  zsh_count=$(grep -cF 'human-guard/wrapper' "$HOME/.zshrc" 2>/dev/null) || zsh_count=0
  bash_count=$(grep -cF 'human-guard/wrapper' "$HOME/.bashrc" 2>/dev/null) || bash_count=0
  [ "$zsh_count" -le 1 ]
  [ "$bash_count" -le 1 ]
}

test_install_preserves_existing_hooks() {
  cat > "$HOME/.claude/settings.json" <<'JSON'
{"hooks":{"PreToolUse":[{"hooks":[{"type":"command","command":"echo existing-hook"}]}]}}
JSON
  run_install_defaults
  jq -r '.hooks.PreToolUse[].hooks[].command' "$HOME/.claude/settings.json" | grep -q 'existing-hook'
  jq -r '.hooks.PreToolUse[].hooks[].command' "$HOME/.claude/settings.json" | grep -q 'human-guard'
}

test_install_no_jq_fails_graceful() {
  # Build restricted PATH with all system tools EXCEPT jq
  local rbin="$SANDBOX/rbin-nojq"
  mkdir -p "$rbin"
  for cmd in bash sh grep awk sed mkdir cp chmod cat mv touch mktemp basename dirname ln rm head tail sort tr wc printf date; do
    local p; p="$(command -v "$cmd" 2>/dev/null || true)"
    [ -n "$p" ] && ln -sf "$p" "$rbin/$cmd"
  done
  local real_python; real_python="$(command -v python3 2>/dev/null || true)"
  [ -n "$real_python" ] && ln -sf "$real_python" "$rbin/python3"
  ln -sf "$SANDBOX/bin/claude" "$rbin/claude"
  local result=0
  local output
  output=$( export PATH="$rbin"; printf '\n' | bash "$SCRIPT_DIR/install.sh" 2>&1 ) || result=$?
  [ $result -ne 0 ]
  # Verify it's actually about jq, not some other missing tool
  echo "$output" | grep -qi 'jq'
}

test_install_no_runtime_fails_graceful() {
  # Build restricted PATH with all system tools + jq, but NO runtimes
  local rbin="$SANDBOX/rbin-noruntime"
  mkdir -p "$rbin"
  for cmd in bash sh grep awk sed mkdir cp chmod cat mv touch mktemp basename dirname ln rm head tail sort tr wc printf date; do
    local p; p="$(command -v "$cmd" 2>/dev/null || true)"
    [ -n "$p" ] && ln -sf "$p" "$rbin/$cmd"
  done
  ln -sf "$(command -v jq)" "$rbin/jq"
  ln -sf "$SANDBOX/bin/claude" "$rbin/claude"
  local result=0
  local output
  output=$( export PATH="$rbin"; printf '\n' | bash "$SCRIPT_DIR/install.sh" 2>&1 ) || result=$?
  [ $result -ne 0 ]
  # Verify it's actually about missing runtime, not some other tool
  echo "$output" | grep -qi 'runtime\|python\|node'
}

test_install_settings_json_missing() {
  rm -f "$HOME/.claude/settings.json"
  run_install_defaults
  [ -f "$HOME/.claude/settings.json" ]
  jq -e '.hooks.PreToolUse' "$HOME/.claude/settings.json" > /dev/null
}

test_install_settings_json_corrupt() {
  echo '{{{bad' > "$HOME/.claude/settings.json"
  run_install_defaults || true
}

test_install_detects_python() {
  rm -f "$SANDBOX/bin/node" "$SANDBOX/bin/bun" "$SANDBOX/bin/deno"
  run_install_defaults
  [ -f "$HOME/.claude/human-guard/core.py" ]
  grep -q 'python3' "$HOME/.claude/human-guard/core"
}

test_install_detects_node() {
  command -v node &>/dev/null || { echo "SKIP: node not available"; return 0; }
  # Build a restricted PATH with only essential tools — NO python3
  local rbin="$SANDBOX/rbin"
  mkdir -p "$rbin"
  for cmd in bash sh grep awk sed mkdir cp chmod cat mv touch mktemp basename dirname ln rm head tail sort tr wc; do
    local p; p="$(command -v "$cmd" 2>/dev/null || true)"
    [ -n "$p" ] && ln -sf "$p" "$rbin/$cmd"
  done
  ln -sf "$(command -v jq)" "$rbin/jq"
  ln -sf "$(command -v node)" "$rbin/node"
  ln -sf "$SANDBOX/bin/claude" "$rbin/claude"
  local old_path="$PATH"
  export PATH="$rbin"
  printf '\n\n\n\n\n\n\n\n\n' | bash "$SCRIPT_DIR/install.sh" 2>/dev/null
  export PATH="$old_path"
  [ -f "$HOME/.claude/human-guard/core.mjs" ]
  grep -q 'node' "$HOME/.claude/human-guard/core"
}

test_install_prefers_python_over_node() {
  run_install_defaults
  [ -f "$HOME/.claude/human-guard/core.py" ]
  grep -q 'python3' "$HOME/.claude/human-guard/core"
}

# === Wizard tests ===

test_wizard_all_defaults() {
  printf '\n\n\n\n\n\n\n\n\n' | bash "$SCRIPT_DIR/install.sh" 2>/dev/null
  [ -f "$HOME/.claude/human.md" ]
  grep -q 'human-md' "$HOME/.claude/human.md"
  grep -q '09:00' "$HOME/.claude/human.md"
}

test_wizard_custom_values() {
  printf 'Javi\nEurope/London\n09:00\n00:00\ny\nfamily\n18:00\n21:00\nn\n23:30\n150\n15\nsoft\n' | bash "$SCRIPT_DIR/install.sh" 2>/dev/null
  [ -f "$HOME/.claude/human.md" ]
  grep -q 'Javi' "$HOME/.claude/human.md"
  grep -q 'Europe/London' "$HOME/.claude/human.md"
  grep -q 'family' "$HOME/.claude/human.md"
  grep -q '23:30' "$HOME/.claude/human.md"
}

test_wizard_end_before_start() {
  printf 'Test\nUTC\n22:00\n06:00\nn\n\n120\n15\nsoft\n' | bash "$SCRIPT_DIR/install.sh" 2>/dev/null
  [ -f "$HOME/.claude/human.md" ]
  grep -q '22:00' "$HOME/.claude/human.md"
  grep -q '06:00' "$HOME/.claude/human.md"
}

test_wizard_empty_name() {
  printf '\nUTC\n09:00\n18:00\nn\n\n120\n15\nsoft\n' | bash "$SCRIPT_DIR/install.sh" 2>/dev/null
  [ -f "$HOME/.claude/human.md" ]
  grep -q 'human-md' "$HOME/.claude/human.md"
}

test_wizard_no_blocked_periods() {
  printf 'Test\nUTC\n09:00\n18:00\nn\n\n120\n15\nsoft\n' | bash "$SCRIPT_DIR/install.sh" 2>/dev/null
  [ -f "$HOME/.claude/human.md" ]
  ! grep -q 'blocked_periods' "$HOME/.claude/human.md"
}

test_wizard_no_wind_down() {
  printf 'Test\nUTC\n09:00\n18:00\nn\n\n120\n15\nsoft\n' | bash "$SCRIPT_DIR/install.sh" 2>/dev/null
  [ -f "$HOME/.claude/human.md" ]
  ! grep -q 'wind_down' "$HOME/.claude/human.md"
}

test_wizard_multiple_blocked_periods() {
  printf 'Test\nUTC\n09:00\n23:00\ny\nlunch\n12:00\n13:00\ny\nfamily\n18:00\n21:00\nn\n22:30\n120\n15\nsoft\n' | bash "$SCRIPT_DIR/install.sh" 2>/dev/null
  [ -f "$HOME/.claude/human.md" ]
  grep -q 'lunch' "$HOME/.claude/human.md"
  grep -q 'family' "$HOME/.claude/human.md"
}

test_wizard_special_chars_in_name() {
  printf 'Jose Maria\nUTC\n09:00\n18:00\nn\n\n120\n15\nsoft\n' | bash "$SCRIPT_DIR/install.sh" 2>/dev/null
  [ -f "$HOME/.claude/human.md" ]
  grep -q 'Jose Maria' "$HOME/.claude/human.md"
}

test_wizard_skip_if_human_md_exists() {
  printf 'version: "1.1"\nframework: human-md\n' > "$HOME/.claude/human.md"
  run_install_defaults
  head -1 "$HOME/.claude/human.md" | grep -q 'version: "1.1"'
}

test_wizard_output_is_valid_yaml() {
  printf 'Test User\nUTC\n09:00\n23:00\ny\nfamily\n18:00\n21:00\nn\n22:30\n150\n15\nsoft\n' | bash "$SCRIPT_DIR/install.sh" 2>/dev/null
  [ -f "$HOME/.claude/human.md" ]
  if command -v python3 &>/dev/null; then
    python3 -c "
import sys; sys.path.insert(0, '$SCRIPT_DIR/guard')
from core import parse_yaml
config = parse_yaml(open('$HOME/.claude/human.md').read())
assert config.get('framework') == 'human-md', f'Bad framework: {config}'
"
  fi
}

# === E2E usage tests ===

test_e2e_check_within_hours() {
  run_install_defaults
  cat > "$HOME/.claude/human.md" <<'YAML'
version: "1.1"
framework: human-md
operator:
  timezone: "UTC"
schedule:
  allowed_hours:
    start: "00:00"
    end: "23:59"
sessions:
  max_continuous_minutes: 150
enforcement: soft
YAML
  local rc=0
  "$HOME/.claude/human-guard/core" --check 2>/dev/null || rc=$?
  [ $rc -eq 0 ]
  [ -f "$HOME/.claude/session-state.json" ]
}

test_e2e_session_lifecycle() {
  run_install_defaults
  cat > "$HOME/.claude/human.md" <<'YAML'
version: "1.1"
framework: human-md
operator:
  timezone: "UTC"
schedule:
  allowed_hours:
    start: "00:00"
    end: "23:59"
enforcement: soft
YAML
  local sid
  sid=$("$HOME/.claude/human-guard/core" --start-session --dir /tmp)
  [ -n "$sid" ]
  [ -f "$HOME/.claude/session-log.json" ]
  "$HOME/.claude/human-guard/core" --end-session "$sid"
  jq -e '.sessions[0].end_time != null' "$HOME/.claude/session-log.json" > /dev/null
}

test_e2e_hook_reads_state() {
  run_install_defaults
  cat > "$HOME/.claude/human.md" <<'YAML'
version: "1.1"
framework: human-md
operator:
  timezone: "UTC"
schedule:
  allowed_hours:
    start: "00:00"
    end: "23:59"
enforcement: soft
YAML
  "$HOME/.claude/human-guard/core" --check 2>/dev/null
  local rc=0
  echo '{}' | bash "$HOME/.claude/human-guard/hook.sh" || rc=$?
  [ $rc -eq 0 ]
}

test_e2e_hook_no_state_file() {
  run_install_defaults
  rm -f "$HOME/.claude/session-state.json"
  local rc=0
  echo '{}' | bash "$HOME/.claude/human-guard/hook.sh" || rc=$?
  [ $rc -eq 0 ]
}

test_e2e_remote_install() {
  # Patch REPO_URL to use file:// so install.sh downloads from local repo (no HTTP server needed)
  # Escape & for sed replacement and spaces for file:// URLs
  local file_url
  file_url="file://$(printf '%s' "$SCRIPT_DIR" | sed -e 's/ /%20/g' -e 's/[\\&]/\\&/g')"
  local patched="$SANDBOX/install.sh"
  sed "s|https://raw.githubusercontent.com/thellmwhisperer/human.md/main|${file_url}|" "$SCRIPT_DIR/install.sh" > "$patched"

  # Run from $SANDBOX (no guard/core.py present) so install.sh takes the remote download branch
  (cd "$SANDBOX" && printf '\n\n\n\n\n\n\n\n\n' | bash "$patched" 2>/dev/null)

  # Verify installation
  [ -x "$HOME/.claude/human-guard/core" ]
  [ -f "$HOME/.claude/human-guard/hook.sh" ]
  jq -e '.hooks.PreToolUse' "$HOME/.claude/settings.json" > /dev/null
  [ -f "$HOME/.claude/human.md" ]
}

# === Uninstaller tests ===

test_uninstall_removes_guard_dir() {
  run_install_defaults
  run_uninstall
  [ ! -d "$HOME/.claude/human-guard" ]
}

test_uninstall_removes_hook() {
  echo '{}' > "$HOME/.claude/settings.json"
  run_install_defaults
  run_uninstall
  local hook_count
  hook_count=$(jq '[.hooks.PreToolUse // [] | .[].hooks[].command | select(contains("human-guard"))] | length' "$HOME/.claude/settings.json" 2>/dev/null || echo 0)
  [ "$hook_count" -eq 0 ]
}

test_uninstall_removes_source_line() {
  run_install_defaults
  run_uninstall
  ! grep -qF 'human-guard/wrapper' "$HOME/.zshrc"
  ! grep -qF 'human-guard/wrapper' "$HOME/.bashrc"
}

test_uninstall_preserves_human_md() {
  run_install_defaults
  [ -f "$HOME/.claude/human.md" ]
  run_uninstall
  [ -f "$HOME/.claude/human.md" ]
}

test_uninstall_preserves_session_log() {
  run_install_defaults
  echo '{"sessions":[]}' > "$HOME/.claude/session-log.json"
  run_uninstall
  [ -f "$HOME/.claude/session-log.json" ]
}

test_uninstall_on_clean_system() {
  local result=0
  run_uninstall || result=$?
  [ $result -eq 0 ]
}

# === Security tests ===

test_hook_no_command_injection() {
  run_install_defaults
  # Create session-state.json with injection attempt in message
  cat > "$HOME/.claude/session-state.json" <<'JSON'
{
  "max_epoch": 0,
  "warn_epoch": 0,
  "wind_down_epoch": 0,
  "end_allowed_epoch": 0,
  "enforcement": "soft",
  "blocked_periods": [],
  "messages": {
    "session_limit": "$(touch $HOME/hacked-limit)",
    "wind_down": "$(touch $HOME/hacked-wind)",
    "outside_hours": "$(touch $HOME/hacked-outside)",
    "break_reminder": "`touch $HOME/hacked-backtick`",
    "blocked_period": "normal message"
  }
}
JSON
  # Run the hook (will trigger outside_hours since end_allowed_epoch=0)
  echo '{}' | bash "$HOME/.claude/human-guard/hook.sh" 2>/dev/null || true
  # Verify no files were created by injection
  [ ! -f "$HOME/hacked-limit" ]
  [ ! -f "$HOME/hacked-wind" ]
  [ ! -f "$HOME/hacked-outside" ]
  [ ! -f "$HOME/hacked-backtick" ]
}

test_hook_json_output_valid() {
  run_install_defaults
  cat > "$HOME/.claude/human.md" <<'YAML'
version: "1.1"
framework: human-md
operator:
  timezone: "UTC"
schedule:
  allowed_hours:
    start: "00:00"
    end: "23:59"
sessions:
  max_continuous_minutes: 1
enforcement: advisory
messages:
  session_limit: >
    Message with "quotes" and back\slash
YAML
  "$HOME/.claude/human-guard/core" --check 2>/dev/null
  # Modify max_epoch to trigger session_limit message
  jq '.max_epoch = 0' "$HOME/.claude/session-state.json" > "$HOME/.claude/session-state.json.tmp"
  mv "$HOME/.claude/session-state.json.tmp" "$HOME/.claude/session-state.json"
  local output
  output=$(echo '{}' | bash "$HOME/.claude/human-guard/hook.sh" 2>/dev/null) || true
  # Output must be valid JSON if non-empty
  if [ -n "$output" ]; then
    echo "$output" | jq empty
  fi
}

test_wizard_timezone_no_injection() {
  # Timezone with shell injection attempt — should not execute
  printf "Test\nUTC'; touch \$HOME/tz-hacked; echo '\n09:00\n18:00\nn\n\n120\n15\nsoft\n" | bash "$SCRIPT_DIR/install.sh" 2>/dev/null || true
  [ ! -f "$HOME/tz-hacked" ]
}

test_wizard_quotes_in_name_safe() {
  # Name with quotes that could break YAML
  printf 'John "Johnny" O'\''Brien\nUTC\n09:00\n18:00\nn\n\n120\n15\nsoft\n' | bash "$SCRIPT_DIR/install.sh" 2>/dev/null
  [ -f "$HOME/.claude/human.md" ]
  # The generated YAML must be parseable by the core
  if command -v python3 &>/dev/null; then
    python3 -c "
import sys; sys.path.insert(0, '$SCRIPT_DIR/guard')
from core import parse_yaml
config = parse_yaml(open('$HOME/.claude/human.md').read())
assert config.get('framework') == 'human-md', f'Bad framework: {config}'
"
  fi
}

test_hook_advisory_blocked_period_no_block() {
  run_install_defaults
  # Create session-state with advisory enforcement and an active blocked period
  local now
  now=$(date +%s)
  local bp_start=$((now - 60))
  local bp_end=$((now + 3600))
  cat > "$HOME/.claude/session-state.json" <<JSON
{
  "max_epoch": $((now + 9000)),
  "warn_epoch": $((now + 7200)),
  "wind_down_epoch": 0,
  "end_allowed_epoch": $((now + 9000)),
  "enforcement": "advisory",
  "blocked_periods": [{"name": "test", "start_epoch": $bp_start, "end_epoch": $bp_end}],
  "messages": {
    "session_limit": "",
    "wind_down": "",
    "blocked_period": "Advisory blocked.",
    "break_reminder": "",
    "outside_hours": ""
  }
}
JSON
  local rc=0
  local output
  output=$(echo '{}' | bash "$HOME/.claude/human-guard/hook.sh" 2>/dev/null) || rc=$?
  # Advisory should NOT block (exit 0, not exit 2)
  [ $rc -eq 0 ]
  # Should emit a systemMessage JSON
  echo "$output" | jq -e '.systemMessage' > /dev/null
}

test_hook_soft_blocked_period_blocks() {
  run_install_defaults
  local now
  now=$(date +%s)
  local bp_start=$((now - 60))
  local bp_end=$((now + 3600))
  cat > "$HOME/.claude/session-state.json" <<JSON
{
  "max_epoch": $((now + 9000)),
  "warn_epoch": $((now + 7200)),
  "wind_down_epoch": 0,
  "end_allowed_epoch": $((now + 9000)),
  "enforcement": "soft",
  "blocked_periods": [{"name": "test", "start_epoch": $bp_start, "end_epoch": $bp_end}],
  "messages": {
    "session_limit": "",
    "wind_down": "",
    "blocked_period": "Soft blocked.",
    "break_reminder": "",
    "outside_hours": ""
  }
}
JSON
  local rc=0
  echo '{}' | bash "$HOME/.claude/human-guard/hook.sh" 2>/dev/null || rc=$?
  # Soft should block (exit 2)
  [ $rc -eq 2 ]
}

test_hook_wind_down_pre_midnight_session_post_midnight() {
  # Scenario: schedule 22:00-06:00, wind_down 23:30, session at 01:00
  # wind_down_epoch should be in the past (yesterday 23:30) → hook detects it
  run_install_defaults
  local now
  now=$(date +%s)
  # wind_down was 1.5h ago (simulates 23:30 yesterday from a 01:00 session)
  local wd_epoch=$((now - 5400))
  cat > "$HOME/.claude/session-state.json" <<JSON
{
  "max_epoch": $((now + 9000)),
  "warn_epoch": $((now + 7200)),
  "wind_down_epoch": $wd_epoch,
  "end_allowed_epoch": $((now + 18000)),
  "enforcement": "soft",
  "blocked_periods": [],
  "messages": {
    "session_limit": "",
    "wind_down": "Wind-down: overnight session past 23:30.",
    "blocked_period": "",
    "break_reminder": "",
    "outside_hours": ""
  }
}
JSON
  local rc=0
  local output
  output=$(echo '{}' | bash "$HOME/.claude/human-guard/hook.sh" 2>/dev/null) || rc=$?
  # Should exit 0 (systemMessage, not block)
  [ $rc -eq 0 ]
  # Should emit wind_down systemMessage
  echo "$output" | jq -e '.systemMessage' > /dev/null
  echo "$output" | grep -q 'Wind-down'
}

test_uninstall_preserves_unrelated_hook_entries() {
  # Install with existing hooks in separate PreToolUse entries
  cat > "$HOME/.claude/settings.json" <<'JSON'
{"hooks":{"PreToolUse":[{"hooks":[{"type":"command","command":"echo other-hook"}]}]}}
JSON
  run_install_defaults
  # Verify both hooks exist
  local count
  count=$(jq '.hooks.PreToolUse | length' "$HOME/.claude/settings.json")
  [ "$count" -eq 2 ]
  # Uninstall
  run_uninstall
  # Other hook must survive
  jq -r '.hooks.PreToolUse[].hooks[].command' "$HOME/.claude/settings.json" | grep -q 'other-hook'
  # Human-guard hook must be gone
  ! jq -r '.hooks.PreToolUse[].hooks[].command' "$HOME/.claude/settings.json" | grep -q 'human-guard'
}

# === Run all ===

echo ""
echo "human-guard E2E tests"
echo "====================="
echo ""
echo "Installer:"
run_test "creates all files" test_install_creates_all_files
run_test "core shim executable" test_install_core_shim_executable
run_test "hook registered" test_install_hook_registered
run_test "source line added" test_install_source_line_added
run_test "idempotent" test_install_idempotent
run_test "preserves existing hooks" test_install_preserves_existing_hooks
run_test "no jq fails gracefully" test_install_no_jq_fails_graceful
run_test "no runtime fails gracefully" test_install_no_runtime_fails_graceful
run_test "settings.json missing" test_install_settings_json_missing
run_test "settings.json corrupt" test_install_settings_json_corrupt
run_test "detects python" test_install_detects_python
run_test "detects node" test_install_detects_node
run_test "prefers python" test_install_prefers_python_over_node
echo ""
echo "Wizard:"
run_test "all defaults" test_wizard_all_defaults
run_test "custom values" test_wizard_custom_values
run_test "overnight schedule" test_wizard_end_before_start
run_test "empty name" test_wizard_empty_name
run_test "no blocked periods" test_wizard_no_blocked_periods
run_test "no wind-down" test_wizard_no_wind_down
run_test "multiple blocked periods" test_wizard_multiple_blocked_periods
run_test "special chars in name" test_wizard_special_chars_in_name
run_test "skip if exists" test_wizard_skip_if_human_md_exists
run_test "valid yaml output" test_wizard_output_is_valid_yaml
echo ""
echo "E2E usage:"
run_test "check within hours" test_e2e_check_within_hours
run_test "session lifecycle" test_e2e_session_lifecycle
run_test "hook reads state" test_e2e_hook_reads_state
run_test "hook no state" test_e2e_hook_no_state_file
run_test "remote install (curl|bash)" test_e2e_remote_install
echo ""
echo "Security:"
run_test "hook no command injection" test_hook_no_command_injection
run_test "hook JSON output valid" test_hook_json_output_valid
run_test "wizard timezone no injection" test_wizard_timezone_no_injection
run_test "wizard quotes in name safe" test_wizard_quotes_in_name_safe
run_test "hook advisory blocked_period no block" test_hook_advisory_blocked_period_no_block
run_test "hook soft blocked_period blocks" test_hook_soft_blocked_period_blocks
run_test "hook wind_down pre-midnight + session post-midnight" test_hook_wind_down_pre_midnight_session_post_midnight
run_test "uninstall preserves unrelated hooks" test_uninstall_preserves_unrelated_hook_entries
echo ""
echo "Uninstaller:"
run_test "removes guard dir" test_uninstall_removes_guard_dir
run_test "removes hook" test_uninstall_removes_hook
run_test "removes source line" test_uninstall_removes_source_line
run_test "preserves human.md" test_uninstall_preserves_human_md
run_test "preserves session-log" test_uninstall_preserves_session_log
run_test "clean system" test_uninstall_on_clean_system
echo ""
echo "====================="
printf "Results: ${GREEN}%d passed${NC}" "$PASS"
if [ "$FAIL" -gt 0 ]; then
  printf ", ${RED}%d failed${NC}" "$FAIL"
  printf "\n\nFailed tests:%b\n" "$ERRORS"
fi
echo ""
echo ""
exit $FAIL
