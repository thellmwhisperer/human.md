#!/bin/bash
# human-guard uninstaller
# Removes guard files, hook registration, and shell wrapper.
# Does NOT remove: human.md, session-log.json (user data).
set -euo pipefail

GUARD_DIR="$HOME/.claude/human-guard"
SETTINGS="$HOME/.claude/settings.json"

echo ""
echo "human-guard uninstaller"
echo "======================="
echo ""

# Confirm
printf "Remove human-guard? Your human.md and session logs will be preserved. [y/N]: "
read -r CONFIRM || CONFIRM=""
if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
  echo "Cancelled."
  exit 0
fi

echo ""

# 1. Remove hook from settings.json
if [ -f "$SETTINGS" ] && jq empty "$SETTINGS" 2>/dev/null; then
  HOOK_COUNT=$(jq '[.hooks.PreToolUse // [] | .[].hooks[]?.command // "" | select(contains("human-guard"))] | length' "$SETTINGS" 2>/dev/null || echo 0)
  if [ "$HOOK_COUNT" -gt 0 ]; then
    jq '.hooks.PreToolUse = [.hooks.PreToolUse[] | .hooks = [.hooks[] | select(.command | contains("human-guard") | not)] | select(.hooks | length > 0)]' "$SETTINGS" > "$SETTINGS.tmp"
    mv "$SETTINGS.tmp" "$SETTINGS"
    printf "  \033[0;32m✓\033[0m Hook removed from settings.json\n"
  else
    printf "  \033[0;32m✓\033[0m No hook to remove\n"
  fi
fi

# 2. Remove source line from shell configs
for rc_file in "$HOME/.zshrc" "$HOME/.bashrc"; do
  if [ -f "$rc_file" ] && grep -qF "human-guard/wrapper" "$rc_file"; then
    # Use sed to remove the source line and the comment above it
    sed -i.bak '/# human-guard: enforce human.md schedule/d' "$rc_file"
    sed -i.bak '/human-guard\/wrapper/d' "$rc_file"
    rm -f "$rc_file.bak"
    printf "  \033[0;32m✓\033[0m Source line removed from %s\n" "$(basename "$rc_file")"
  fi
done

# 3. Remove guard directory
if [ -d "$GUARD_DIR" ]; then
  rm -rf "$GUARD_DIR"
  printf "  \033[0;32m✓\033[0m Removed ~/.claude/human-guard/\n"
else
  printf "  \033[0;32m✓\033[0m ~/.claude/human-guard/ not found (already clean)\n"
fi

# 4. Note what's preserved
echo ""
echo "Preserved (your data):"
[ -f "$HOME/.claude/human.md" ] && echo "  - ~/.claude/human.md"
[ -f "$HOME/.claude/session-log.json" ] && echo "  - ~/.claude/session-log.json"
[ -f "$HOME/.claude/session-state.json" ] && rm -f "$HOME/.claude/session-state.json"

echo ""
echo "Done. Restart your shell to complete removal."
echo ""
