# Example: Full Configuration

A complete `human.md` showing all available options. This configuration models a real day with distinct blocks — work, family time, and personal coding — with a wind-down period before midnight and custom messages for each boundary event.

See [spec/SPEC.md](../spec/SPEC.md) for detailed documentation of each field.

```yaml
version: "1.1"
framework: human-md

operator:
  name: "Javi"
  timezone: "Europe/London"

schedule:
  allowed_hours:
    start: "09:00"
    end: "00:00"
  blocked_periods:
    - name: "family"
      start: "18:00"
      end: "21:00"
  wind_down:
    start: "23:30"

sessions:
  max_continuous_minutes: 150
  min_break_minutes: 15

enforcement: soft

messages:
  outside_hours: >
    It's outside your working hours. Close the laptop.
    Whatever it is, it'll still be here tomorrow.
  blocked_period: >
    This is family time. I'm not helping with code until 21:00.
    Go be with your people.
  wind_down: >
    It's 23:30. Start wrapping up. Finish what you have in hand
    but don't start anything new. Tomorrow.
  session_limit: >
    You've been at it for 2.5 hours. Time for a break.
    Step away, stretch, hydrate. The code isn't going anywhere.
  break_reminder: >
    Quick check — when was the last time you stood up?
```
