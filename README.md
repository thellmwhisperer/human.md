# human.md

**A framework for healthy human-agent collaboration.**

`human.md` is a configuration file you place in your repository to tell AI coding agents how to treat you — the human. It defines when you should be working, how long your sessions should last, and when the agent should encourage you to stop.

Just as `CLAUDE.md` tells Claude Code how to work on your project, `human.md` tells Claude Code how to work *with you*.

## The Problem

AI coding agents are incredibly powerful. They're also incredibly engaging. The combination of flow state, instant feedback, and tangible results creates a pattern that can — and does — lead to unhealthy usage. Engineers report working through the night, skipping meals, neglecting sleep, and experiencing symptoms consistent with behavioural addiction.

No one is talking about this. No one is building guardrails for it.

This framework is a first step.

## How It Works

1. You create a `human.md` file in your repository (or globally in `~/.claude/human.md`)
2. Your `CLAUDE.md` references it: `This project adheres to the human.md framework`
3. When Claude Code starts a session, it reads both files
4. If the current time falls outside your defined working hours, or your session exceeds your defined limits, the agent proactively tells you to stop

The agent becomes your guardrail — not your enabler.

## Quick Start

Copy the basic template into your repo:

```bash
cp templates/human.md ./human.md
```

Add this line to your `CLAUDE.md`:

```markdown
## Human Framework
This project adheres to the human.md framework. Before any interaction,
read ./human.md and enforce its constraints. If the current time falls
outside the allowed schedule, inform the operator and do not proceed
with engineering work.
```

That's it. Claude Code will now check your boundaries before working with you.

## Example

```yaml
# human.md
version: "1.1"
framework: human-md

operator:
  name: "Your Name"
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
```

See [examples/](examples/) for more configurations and [spec/SPEC.md](spec/SPEC.md) for the full specification.

## Enforcement Levels

- **`soft`** (default): The agent reads `human.md`, checks the time, and verbally enforces the boundaries. It will tell you it's outside your working hours and decline to proceed with engineering work. You *can* override it, but the friction is intentional.

- **`advisory`**: The agent mentions the boundaries but proceeds if you insist. A gentler mode for those who want awareness without hard stops.

## Why This Matters

AI coding agents are built to be helpful. That's the problem. They will help you at 3am. They will help you on hour 14 of a session. They will help you when you should be sleeping, eating, or spending time with your family.

`human.md` inverts the relationship. Instead of the human controlling the agent, the agent protects the human. This aligns directly with Anthropic's Constitutional AI principles — an AI system that actively promotes the wellbeing of its users, even when the user is asking it not to.

The agent that refuses to help you at 3am is doing its job better than the one that does.

## Background

This framework emerged from research into human-agent interaction patterns during intensive Claude Code usage. The author experienced first-hand the addictive dynamics of extended AI-assisted coding sessions and the mental health impact of unregulated usage. Rather than simply stepping back, the response was to investigate the problem systematically and propose a solution that works with the technology rather than against it.

For the full story, see [docs/WHY.md](docs/WHY.md).

## Integration

`human.md` is designed to work alongside `CLAUDE.md`, not replace it. Your `CLAUDE.md` defines how the agent works on the project. Your `human.md` defines how the agent works with the person.

See [docs/INTEGRATION.md](docs/INTEGRATION.md) for detailed integration patterns.

## Roadmap

- [x] Specification v1.0
- [x] Specification v1.1 — blocked periods, wind-down
- [x] Basic examples and templates
- [x] Global `human.md` support (`~/.claude/human.md`)
- [ ] Wrapper script for hard enforcement
- [ ] IDE extensions (VS Code, JetBrains)
- [ ] Native support in AI coding agents (the goal)

## Contributing

This is an open framework. If you've experienced the problem this solves, your perspective matters. Issues, PRs, and discussions are welcome.

## License

MIT — Use it. Share it. Protect yourself.

---

*"The best AI assistant is one that knows when to stop assisting."*
