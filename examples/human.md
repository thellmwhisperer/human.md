# Example: Minimal Configuration

A basic `human.md` with just working hours and session limits. This is the simplest useful configuration — define when you work, how long your sessions last, and let the agent handle the rest.

See [spec/SPEC.md](../spec/SPEC.md) for all available options.

```yaml
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
```
