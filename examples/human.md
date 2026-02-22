# human.md — Basic Example
# Minimal configuration with just working hours.
# See spec/SPEC.md for all available options.

version: "1.1"
framework: human-md

operator:
  name: ""
  timezone: "Europe/London"

schedule:
  allowed_hours:
    start: "09:00"
    end: "22:00"

sessions:
  max_continuous_minutes: 150
  min_break_minutes: 15

enforcement: soft
