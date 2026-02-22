# human.md
# Place this file in your repository root or globally at ~/.claude/human.md
# Add to your CLAUDE.md: "This project adheres to the human.md framework."
# Full spec: https://github.com/thellmwhisperer/human.md/blob/main/spec/SPEC.md

version: "1.1"
framework: human-md

operator:
  name: ""           # Your name (optional)
  timezone: ""       # Your IANA timezone, e.g. "America/New_York"

schedule:
  allowed_hours:
    start: "09:00"   # When your workday starts (24h format)
    end: "22:00"     # When you should stop (24h format)
  # blocked_days:    # Uncomment to block specific days
  #   - "Sunday"
  # blocked_periods: # Uncomment to block time ranges within allowed hours
  #   - name: "family"
  #     start: "18:00"
  #     end: "21:00"
  # wind_down:       # Uncomment to set a wrap-up warning before end of day
  #   start: "21:30"

sessions:
  max_continuous_minutes: 150  # Max time before mandatory break
  min_break_minutes: 15        # Minimum break duration

enforcement: soft    # "soft" = agent refuses to work | "advisory" = agent warns but continues
