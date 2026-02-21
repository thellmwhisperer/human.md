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
3. It reads `human.md` from the project root
4. It runs `date` to determine the current system time
5. It converts to the operator's timezone
6. It compares against the schedule
7. If outside hours: it informs the operator and declines engineering work
8. If within hours: it proceeds normally, tracking session duration

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
1. Read ./human.md
2. Check current time against the operator's schedule
3. Enforce session duration limits
4. If boundaries are violated, inform the operator and do not proceed

The operator's wellbeing takes priority over task completion.
```

## Tips

- **Start with `advisory` mode** if `soft` feels too restrictive. You can always tighten it later.
- **Set realistic hours.** If you set 09:00-17:00 but regularly work until 20:00, you'll just learn to override it. Set boundaries you'll actually respect.
- **The custom messages matter.** A message that resonates with you personally is more effective than a generic warning. Write them in your own voice.
- **Tell your team.** If you're using `human.md`, mentioning it in standups normalises healthy boundaries around AI tool usage.
