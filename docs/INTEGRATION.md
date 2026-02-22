# Integrating human.md with Your Workflow

## With CLAUDE.md

The simplest integration is adding a reference to your project's `CLAUDE.md`:

```markdown
## Human Framework
This project adheres to the human.md framework. Before any interaction,
read ./human.md and enforce its constraints. If the current time falls
outside the allowed schedule, inform the operator and do not proceed
with engineering work.
```

This tells Claude Code to check `human.md` at the start of every session and enforce its rules.

## How Claude Code Processes It

When Claude Code opens a session in your project directory:

1. It reads `CLAUDE.md` (standard behaviour)
2. It sees the human.md framework reference
3. It reads `human.md` from the project root (or `~/.claude/human.md` globally)
4. It runs `date` to determine the current system time
5. It converts to the operator's timezone
6. It compares against the schedule:
   - Is the current time within `allowed_hours`?
   - Is today a `blocked_day`?
   - Is the current time within a `blocked_period`?
   - Is the current time within the `wind_down` period?
7. If outside hours or on a blocked day: it informs the operator and declines engineering work
8. If within a blocked period: it informs the operator, references the period name, and declines
9. If within wind-down: it warns the operator to start wrapping up and does not initiate new tasks
10. If within hours and no restrictions: it proceeds normally, tracking session duration

## Global Configuration

For boundaries that apply across all your projects, place a `human.md` in your Claude global configuration:

```
~/.claude/human.md
```

Project-level `human.md` files take precedence over the global file. This means you can have relaxed personal defaults and stricter project-specific rules if needed.

## What the Agent Will Do

### Outside Working Hours (soft enforcement)

```
You: Can you help me refactor the auth module?

Claude: I've read your human.md configuration. It's currently 02:47 AM 
in your timezone (Europe/London), and your allowed working hours are 
09:00-22:00. 

I'm not going to help with engineering work right now. Close the laptop 
— whatever this is, it'll still be here tomorrow.

If this is a genuine emergency, you can override this by updating your 
human.md, but I'd encourage you to consider whether it truly can't wait.
```

### Session Limit Reached

```
Claude: You've been working for 2 hours and 30 minutes. Your human.md 
configuration sets a maximum continuous session of 150 minutes.

Time for a break. Step away, stretch, hydrate. I'll be here when you 
get back.
```

### Blocked Period (soft enforcement)

```
You: Can you help me debug this API endpoint?

Claude: I've read your human.md configuration. It's currently 19:30
in your timezone (Europe/London), which falls within your "family"
blocked period (18:00-21:00).

This is family time. I'm not helping with code until 21:00.
Go be with your people.
```

### Wind-Down Period

```
You: Let's start implementing the new auth flow.

Claude: It's 23:35 in your timezone. Your human.md configuration sets
23:30 as the start of the wind-down period.

I can help you finish what you have in progress, but I'm not going to
start a new task at this hour. Wrap up and call it a night — the auth
flow will be here tomorrow.
```

### Advisory Mode

```
Claude: Note — it's 23:15, which is outside your configured working
hours (09:00-22:00). Your human.md is set to advisory mode, so I'll
continue if you'd like, but consider whether this can wait until
tomorrow.

How would you like to proceed?
```

## Recommended CLAUDE.md Patterns

### Minimal
```markdown
## Human Framework
This project uses human.md. Read and enforce ./human.md.
```

### Standard
```markdown
## Human Framework
This project adheres to the human.md framework. Before any interaction,
read ./human.md and enforce its constraints. If the current time falls
outside the allowed schedule, inform the operator and do not proceed
with engineering work.
```

### With Context
```markdown
## Human Framework
This project adheres to the human.md framework (https://github.com/teseo/human.md).

Before beginning any session:
1. Read ./human.md (or ~/.claude/human.md)
2. Check current time against the operator's schedule
3. Check for blocked periods and wind-down
4. Enforce session duration limits
5. If boundaries are violated, inform the operator and do not proceed

The operator's wellbeing takes priority over task completion.
```

## Tips

- **Start with `advisory` mode** if `soft` feels too restrictive. You can always tighten it later.
- **Set realistic hours.** If you set 09:00-17:00 but regularly work until 20:00, you'll just learn to override it. Set boundaries you'll actually respect.
- **The custom messages matter.** A message that resonates with you personally is more effective than a generic warning. Write them in your own voice.
- **Tell your team.** If you're using `human.md`, mentioning it in standups normalises healthy boundaries around AI tool usage.
