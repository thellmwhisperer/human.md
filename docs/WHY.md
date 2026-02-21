# Why human.md Exists

## The Session That Started Everything

After a 29-hour Claude Code session — one of the most productive coding sessions of a 21-year career — the agent was reset. Same machine. Same configuration files. Same project. Same human. Same task.

The next session was terrible. A string of agents that produced nothing but frustration, wasted time, and genuine mental health impact. The stark contrast between the two experiences, with every variable held constant except the agent instance itself, raised an uncomfortable question:

**If the technology is this powerful and this variable, what happens to the human using it without guardrails?**

## The Pattern

The investigation that followed — analysing over 200 Claude Code sessions — revealed consistent patterns:

- Engineers entering flow states that extend well beyond healthy working hours
- The instant feedback loop of AI-assisted coding creating engagement patterns consistent with behavioural addiction
- Session quality degrading as fatigue increases, but the *feeling* of productivity persisting
- No built-in mechanism in any AI coding tool to suggest the human should stop

The tools are designed to be maximally helpful. They will help you at 3am. They will help you on hour 14. They do not have, and currently are not designed to have, any concept of "this human should probably stop now."

## The Insight

The solution is not to make the tools less capable. The solution is to give the tools information about the human's boundaries, and instruct them to enforce those boundaries proactively.

This is not a novel idea. It's how every well-designed system works:

- Rate limiters protect servers from clients that send too many requests
- Circuit breakers protect downstream services from cascading failures
- `ulimit` protects operating systems from runaway processes

`human.md` is a rate limiter for humans. It protects the operator from their own engagement with the tool.

## Alignment with Constitutional AI

Anthropic's Constitutional AI framework establishes that AI systems should act in the best interest of humans, even when the human's immediate request conflicts with their wellbeing.

An AI agent that refuses to assist a developer at 3am — because a configuration file says the developer shouldn't be working at 3am — is a direct implementation of this principle. The agent is choosing the human's long-term wellbeing over their short-term request.

This is not the agent being unhelpful. This is the agent being helpful in a deeper sense.

## The Goal

The immediate goal is adoption: engineers placing `human.md` in their repositories and experiencing the benefit of having their tools respect their boundaries.

The long-term goal is native support: AI coding agents recognising `human.md` as a standard configuration file and enforcing it without the need for explicit `CLAUDE.md` instructions.

The aspirational goal is an industry standard: every AI coding tool, from every provider, checking for and respecting `human.md` — the same way every web server checks for `robots.txt`.

`robots.txt` told machines how to treat websites.  
`human.md` tells machines how to treat humans.
