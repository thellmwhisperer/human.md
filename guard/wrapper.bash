# human-guard wrapper for bash: intercepts `claude` to enforce human.md schedule
# Installed by human-guard — https://github.com/thellmwhisperer/human.md
# Source this file from ~/.bashrc

claude() {
    local GUARD="$HOME/.claude/human-guard/core"
    [ ! -x "$GUARD" ] && { command claude "$@"; return $?; }

    # Extract flags with exact matching (no substring)
    local force=false
    local passthrough=false
    local args=()
    local arg
    for arg in "$@"; do
        case "$arg" in
            --force) force=true ;;
            --print|-p) passthrough=true; args+=("$arg") ;;
            *) args+=("$arg") ;;
        esac
    done

    # Passthrough for non-interactive modes
    if $passthrough; then
        command claude "$@"
        return $?
    fi

    # Pre-launch check
    local check_flags=()
    if $force; then
        check_flags+=(--force)
    fi
    "$GUARD" --check "${check_flags[@]}" 2>&1
    local rc=$?
    if [ "$rc" -eq 1 ]; then
        return 1  # Blocked — don't launch
    fi

    # rc=0 or rc=2 (wind-down warning already printed) — proceed

    # Start session
    local sid
    if $force; then
        sid=$("$GUARD" --start-session --dir "$PWD" --force)
    else
        sid=$("$GUARD" --start-session --dir "$PWD")
    fi
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
