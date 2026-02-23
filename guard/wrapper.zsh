# shellcheck shell=bash
# human-guard wrapper for zsh: intercepts `claude` to enforce human.md schedule
# Installed by human-guard — https://github.com/thellmwhisperer/human.md
# Source this file from ~/.zshrc

claude() {
    local GUARD="$HOME/.claude/human-guard/core"
    [[ ! -x "$GUARD" ]] && { command claude "$@"; return $?; }

    # Extract flags with exact matching (no substring)
    local force=false passthrough=false args=()
    for arg in "$@"; do
        case "$arg" in
            --force) force=true ;;
            --print|-p) passthrough=true; args+=("$arg") ;;
            *) args+=("$arg") ;;
        esac
    done
    $passthrough && { command claude "$@"; return $?; }

    # Pre-launch check
    local check_flags=()
    $force && check_flags+=(--force)
    "$GUARD" --check "${check_flags[@]}" 2>&1
    local rc=$?
    [[ $rc -eq 1 ]] && return 1        # Blocked — don't launch

    # rc=0 or rc=2 (wind-down warning already printed) — proceed

    # Start session
    local sid force_flag=""
    $force && force_flag="--force"
    sid=$("$GUARD" --start-session --dir "$PWD" $force_flag)
    # shellcheck disable=SC2064  # intentional: capture $GUARD and $sid at definition time
    trap "'$GUARD' --end-session '$sid' 2>/dev/null" EXIT INT TERM

    # Launch claude
    command claude "${args[@]}"
    local exit_code=$?

    # End session
    trap - EXIT INT TERM
    "$GUARD" --end-session "$sid" 2>/dev/null
    return $exit_code
}
