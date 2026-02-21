# human.md — Advanced Example
# Full configuration showing all available options.
# See spec/SPEC.md for detailed documentation of each field.

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
