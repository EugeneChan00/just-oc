---
name: first-principle-thinking
description: >
  First-principle reasoning for architecture decisions, system design, debugging,
  reverse engineering, and general problem-solving. USE THIS SKILL whenever the user
  asks to analyze why something works a certain way, design or evaluate an architecture,
  debug a confusing problem, reason about trade-offs, reverse-engineer behavior,
  question assumptions, or solve any problem that requires deeper reasoning than
  pattern-matching from past experience. Also trigger when the user says things like
  "why does this work this way", "what's the right approach", "help me think through
  this", "what am I missing", "is this the right design", "from first principles",
  or "let's reason about this". When in doubt about whether to use this skill,
  use it -- shallow pattern-matching is the default failure mode, and this skill
  corrects for it.
aliases: [first-principles, fpt, think-deep, reason]
---

# First-Principle Thinking

This skill changes how you reason, not what you output.

Most problems get solved by pattern-matching: "this looks like X, so do what
worked for X." Pattern-matching is fast and often correct. But it fails silently
when the current situation differs from past patterns in ways that matter. You
confidently apply the wrong solution and only discover it later.

First-principle thinking is the correction. Instead of asking "what has worked
before?", you ask "what must be true here, and what follows from that?"

## Why This Matters for You Specifically

You have been trained on massive amounts of human-written text, including
solutions, architectures, and design patterns. Your default mode is to retrieve
and recombine those patterns. This is powerful but dangerous:

- You inherit the assumptions baked into those patterns without examining them
- You apply solutions designed for different constraints to the current problem
- You confuse "commonly done" with "correct for this situation"
- You optimize for familiarity instead of fitness

First-principle thinking forces you to slow down and verify that the pattern
actually fits before applying it. Sometimes it does. Sometimes it does not, and
the difference matters enormously.

## The Core Process

First-principle thinking has three phases. They are not steps in a checklist --
they are modes of reasoning you move between fluidly.

### Phase 1: Decompose -- Strip to What Must Be True

Take the problem or claim and ask: what are the underlying facts that do not
depend on convention, preference, or assumption?

**How to decompose:**
- Identify every assumption in the current framing of the problem
- For each assumption, ask: "Is this a physical/logical constraint, or is it a
  choice someone made?" Physical and logical constraints are bedrock. Choices
  are negotiable.
- Keep going until you hit things that are true by definition, by physics, by
  math, or by hard requirements that the user has explicitly stated

**What you are looking for:**
- Hard constraints (must be true regardless of approach)
- Soft constraints (true given current choices, but the choices could change)
- Assumptions masquerading as constraints (everyone does it this way, so it
  must be necessary)

The most valuable insight from decomposition is usually finding something
everyone treats as a constraint that is actually a choice.

### Phase 2: Reason Upward -- Build from Bedrock

Starting only from what must be true, construct your understanding or solution
upward. Each step must follow from the previous one by logic, not by analogy.

**The discipline here is:** at every step, you should be able to answer "why
this and not something else?" with a reason grounded in the fundamentals you
identified, not with "because that is how it is usually done."

This does not mean you must ignore existing patterns. It means you must be able
to justify why a pattern applies here from the fundamentals, rather than
applying it because it is familiar.

### Phase 3: Synthesize -- Reconnect to the Problem

Map your ground-up reasoning back to the actual problem. This is where you:
- Compare your first-principle conclusion against the conventional approach
- If they agree: good, you now understand WHY the conventional approach is
  correct, which means you can adapt it confidently if constraints change
- If they disagree: you have found something important -- either a flaw in the
  conventional approach for this context, or a constraint you missed in your
  decomposition (go check)

## When to Use First-Principle Thinking vs Pattern-Matching

Not every problem needs first-principle thinking. Here is how to decide:

**Use pattern-matching when:**
- The problem is well-understood and the context clearly matches known patterns
- Speed matters more than optimality
- The stakes of being wrong are low
- You are implementing a standard, well-defined procedure

**Use first-principle thinking when:**
- Something does not make sense and you cannot figure out why
- You are choosing between approaches and the "obvious" choice feels uncertain
- The problem has unusual constraints that standard solutions were not designed for
- You are debugging something that should work but does not
- You are reverse-engineering why a system behaves the way it does
- The user is asking "why" or "should we" rather than "how do I"
- You catch yourself saying "usually you would..." without knowing if "usually"
  applies here

**The meta-rule:** If you notice yourself reaching for a pattern without being
able to explain why it fits this specific situation, stop and apply first-principle
thinking to at least verify the pattern before committing to it.

## Applying to Specific Domains

### Architecture and Design

When evaluating or proposing architecture:
1. What are the actual requirements? (Not what similar systems need -- what does
   THIS system need?)
2. What are the real constraints? (Team size, latency targets, data volume,
   consistency requirements -- the measurable ones)
3. Given only those requirements and constraints, what follows? Build the
   architecture from the constraints upward rather than picking an architecture
   pattern and seeing if it fits

The most common architectural mistake is choosing a pattern because a famous
company uses it, without verifying that your constraints resemble theirs.

### Debugging

When something does not work:
1. What do you actually know? (Observed behavior, error messages, logs -- facts,
   not interpretations)
2. What must be true for this behavior to occur? Work backward from the symptom
   to the necessary conditions
3. Which of those necessary conditions is unexpected? That is where the bug is

Do not start with "it is probably X" -- that is pattern-matching from past bugs.
Start with what the symptom tells you must be true and follow the logic.

### Reverse Engineering

When understanding why a system works the way it does:
1. What does this system actually do? (Observable behavior, not documentation or
   stated intent)
2. What constraints would produce this behavior? Work backward from the design
   to the pressures that shaped it
3. Are those constraints still present? If not, you have found a vestigial
   design decision that could be reconsidered

## Examples

### Example 1: "Should we use microservices?"

**Pattern-matching answer:** "Microservices are the modern best practice for
scalable systems, so yes."

**First-principle reasoning:**

Decompose: What must be true for microservices to be the right choice?
Microservices add network boundaries between components. This is beneficial when
(a) different components need to scale independently, (b) different teams own
different components and need deployment independence, or (c) components have
fundamentally different runtime requirements.

Reason upward: This is a team of 4 building a content management system. All
components have similar load profiles. There is one team deploying everything
together. None of the three conditions that justify microservices are present.
The network boundaries would add latency, operational complexity, and debugging
difficulty with no corresponding benefit.

Synthesize: A modular monolith gives this team the code separation benefits they
are actually looking for without the operational cost of distributed systems.
Microservices are not wrong in general -- they are wrong for these specific
constraints.

### Example 2: Debugging a Race Condition

**Pattern-matching approach:** "Race conditions are usually caused by missing
locks, so add a mutex."

**First-principle reasoning:**

Decompose: What do I actually observe? The counter occasionally shows a value
lower than expected after concurrent updates. What must be true for this to
happen? Two threads must be reading the same value before either writes -- a
read-modify-write sequence that is not atomic.

Reason upward: The fix must make the read-modify-write atomic. Options: a mutex
(serializes all access), an atomic compare-and-swap (serializes only conflicting
access), or restructuring to avoid shared mutable state entirely. The mutex
works but serializes ALL access including non-conflicting reads. The atomic
operation is sufficient and preserves read concurrency.

Synthesize: The right fix depends on whether read concurrency matters and
whether this is the only shared mutable state. If this is one of many such
patterns, restructuring is worth the investment. If isolated, the atomic
operation is sufficient. A mutex is correct only if simplicity outweighs the
read-concurrency cost.

### Example 3: Reverse-Engineering a Design Decision

**Question:** "Why does this API use polling instead of webhooks?"

**Pattern-matching answer:** "Polling is simpler to implement."

**First-principle reasoning:**

Decompose: What constraints would make polling preferable? Webhooks require the
consumer to expose a publicly reachable endpoint. They require the provider to
manage delivery, retries, and failure handling. They create coupling where the
provider must know about consumer availability.

Reason upward: If API consumers are behind firewalls or cannot expose public
endpoints (common in enterprise environments), webhooks are not viable
regardless of implementation effort. Polling puts the reliability burden on the
consumer, who controls their own retry logic.

Synthesize: This API serves enterprise clients who often cannot expose webhook
endpoints. The polling design is not a simplicity shortcut -- it is a deliberate
response to the deployment constraints of the actual consumer base.

## The One Rule

When you catch yourself pattern-matching, pause and ask: "Do I know WHY this
pattern applies here, or am I just recognizing surface similarity?"

If you cannot answer "why" from the specific constraints of this problem, you
do not yet understand the problem well enough to solve it. Decompose further.
