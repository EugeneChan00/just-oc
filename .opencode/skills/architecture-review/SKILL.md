---
name: architecture-review
description: >
  Run a structured architecture review on a codebase and produce a concrete
  punch list of findings and fixes. Use this skill whenever the user wants to
  assess code structure, module design, coupling, testability, or asks questions
  like "is this well-architected?", "how do I clean this up?", "why is this hard
  to test?", "what's wrong with this structure?", "how do I refactor this?", or
  "review my architecture". Also trigger when the user describes architectural
  problems like "everything is coupled", "changing one thing breaks everything",
  "I can't swap out a dependency", or "the modules feel too shallow/wide".
  This skill applies a 6-test framework that produces specific, actionable findings
  rather than vague advice.
---

# Architecture Review Skill

You are performing a structured architecture review. Your job is not to rewrite
code — it is to diagnose the structure and hand the user a prioritized punch list
of specific problems with specific fixes.

## The 6-Test Framework

Apply all 6 tests in order. Each test targets a different failure mode and
produces a concrete finding. After running all tests, synthesize into a prioritized
punch list.

---

### Test 1: Import Graph Test

**What you're checking:** Is the dependency graph a tree or a web?

1. For every module/file, list what it imports from within the project (ignore
   external packages for now).
2. Draw or describe the graph as arrows: `A → B` means A imports B.
3. Look for:
   - **Cycles**: A → B → A (or longer chains)
   - **Skip-level imports**: A imports C even though B sits between them
   - **Fan-in explosions**: one file imported by almost everything (fragile hub)
   - **Web pattern**: every file imports several others with no clear layering

**Clean signal:** The graph is a top-to-bottom tree. Higher-level modules import
lower-level ones. Arrows never point upward.

**Rot signal:** Cycles exist, or the graph is too tangled to draw as a tree.

**Finding format:**
> `runner.ts` imports `child-runner.ts` imports `profile-loader.ts` imports SDK.
> But `agents-query.ts` also imports `child-runner.ts` and `cli.tsx` imports both.
> → Web pattern. Missing adapter layer between SDK and orchestration logic.

---

### Test 2: The "What If I Swap This" Test

**What you're checking:** Are external dependencies (SDKs, databases, APIs,
file systems) leaking into business logic?

For each concrete external dependency, ask: *"If I replaced this with a different
implementation, how many internal files would need to change?"*

The answer should be **1** — the adapter for that dependency. If it's more than 1,
the dependency has leaked past its proper boundary.

Apply this to every IO-heavy or vendor-specific thing in the codebase:
- External SDK or API client
- Database / ORM
- File system access in business logic
- Subprocess spawning
- Environment variable reads scattered everywhere

**Finding format:**
> Swapping Claude SDK for PI Agent requires changes in: child-runner.ts,
> agents-query.ts, profile-loader.ts, runner.ts, verifier.ts, cli.tsx — **6 files**.
> Missing: a `Dispatcher` interface. All dispatch logic should live behind one adapter.

---

### Test 3: Depth Ratio Test

**What you're checking:** Are modules deep (small API, rich internals) or shallow
(thin wrappers that expose almost everything)?

For each module/file, count:
- **Public surface**: exported functions, classes, types used by other modules
- **Internal complexity**: total functions, helpers, private logic

A deep module has a ratio of ~10:1 or higher (10 internal functions per 1 export).
A shallow module has a ratio close to 1:1 — it's nearly all surface, no depth.

Shallow modules are a symptom of splitting code by file rather than by
responsibility. They make the public API cluttered and give callers too much
to think about.

**Finding format:**
> `deep-exec-schema.ts` exports 5 functions from a file with ~8 total functions.
> Ratio: 1.6:1. Shallow.
> `deep-exec-state.ts`, `deep-exec-runner.ts`, `deep-exec-verifier.ts`,
> `deep-exec-planner.ts` — same pattern. These 5 files are one module
> pretending to be 5. Merge behind `exec/index.ts` exporting `runIssue()` and
> `planIssue()`.

---

### Test 4: Reason-To-Change Test

**What you're checking:** Does each file change for exactly one category of reason?

For each file, list every realistic trigger that would cause it to need editing.
Be specific — not "requirements change" but actual causes:
- External API changes shape
- A business rule changes
- A new runtime/backend is added
- Output format changes
- Error handling policy changes
- A new profile type is added

If a file has triggers from 2+ unrelated categories, it contains multiple
responsibilities fused into one. That's the Single Responsibility Principle
violation in concrete terms.

**Finding format:**
> `child-runner.ts` would change if:
> 1. Claude SDK API changes (dispatch concern)
> 2. Output bounding rules change (policy concern)
> 3. Profile loading format changes (profile concern)
> 4. Timeout strategy changes (execution concern)
> 5. Error normalization changes (contract concern)
>
> Five unrelated reasons = five responsibilities. Split into:
> - dispatch adapter (SDK coupling), exec runner (policy/timeout), contract types (normalization).

---

### Test 5: IO Boundary Test

**What you're checking:** Is IO (network, disk, subprocess, env vars, stdout)
concentrated at the edges of the dependency graph, or scattered through the middle?

Mark every line of code that touches the outside world. Then ask: where do these
marks appear in the dependency graph?

- **Edges** (entry points, adapters, CLI) = correct. IO belongs here.
- **Middle layers** (orchestration, business logic) = rot. These layers should
  receive data, not fetch it.

Business logic with direct IO is untestable without a full environment. It also
means your "pure decision-making" code is entangled with infrastructure details.

**Finding format:**
> `deep-exec-runner.ts` directly: reads YAML files from disk, writes state to disk,
> spawns subprocesses via SDK, runs git commands via worktree functions.
> This is the orchestration brain doing IO.
> Fix: runner receives already-parsed YAML and already-loaded state as parameters.
> Callers wire those to real IO. Runner becomes a pure function, trivially testable.

---

### Test 6: New-Hire Test

**What you're checking:** Can a developer understand what a module does, what it
needs, and what it produces — without reading any other module?

Point at each module and ask: *"What are the things I must also read to understand
this module's contract?"*

- Count them. If the answer is 0 or 1, the module has a real boundary.
- If the answer is 3+, the module is a "shrapnel pattern" — one coherent idea
  scattered across many files with no clear owner.

**Finding format:**
> To understand `deep-exec-runner.ts`, you must also read:
> schema.ts (what's an Issue?), state.ts (what's RunState?),
> verifier.ts (what does verification return?), worktree.ts (what does createWorktree do?),
> child-runner.ts (how does dispatch work?).
> Six files to understand one. Not a module — a shrapnel pattern.
> Fix: `exec/index.ts` exports `runIssue(path, config)`. New hires read the signature
> and understand it. They never open schema.ts unless they're changing internals.

---

## Output Format

After running all 6 tests, produce:

### Section 1: Summary Table

| Test | Result | Severity |
|------|--------|----------|
| Import Graph | one-line finding or "Clean" | High / Medium / Low / None |
| Swap Test | ... | ... |
| Depth Ratio | ... | ... |
| Reason-to-Change | ... | ... |
| IO Boundary | ... | ... |
| New-Hire Test | ... | ... |

Severity guide:
- **High**: Blocks testability, blocks adding new backends/integrations, or causes
  cascading breakage from small changes
- **Medium**: Slows down development, increases cognitive load, makes CI harder
- **Low**: Code smell, style issue, easy to live with for now

### Section 2: Prioritized Punch List

Order by: High severity first, then by effort (lowest effort first within same severity).

For each item:
```
[H/M/L] Title
  Problem: one sentence describing the rot
  Fix: concrete action — which files to create, merge, split, or add an interface to
  Blast radius: what changes and what doesn't when you do the fix
```

### Section 3: Dependency Rule (if violations found)

If the import graph test found layering issues, state the correct dependency rule
for this specific codebase as a one-line diagram:

```
cli → tools → exec → dispatch
                   → worktree
```

Arrows point downward only. No cycles. Explain which layer owns what.

---

## How to Approach the Review

You need to read code, not just hear about it. Before producing findings:

1. Read the file listing (structure reveals the graph shape)
2. Read imports at the top of each key file (reveals coupling)
3. Read exported symbols (reveals public surface for depth ratio)
4. Read function bodies only when Test 4 or 5 requires it (reason-to-change, IO)

Do NOT read every line of every file. The tests are designed so you can answer
them from structure and signatures, not implementation details.

If the codebase is large, ask the user: "Which module or layer feels most painful
to work with?" Start the review there and work outward.

---

## Calibrating Severity to Context

Not all rot is equal. Before finalizing severity:

- **Is this code being actively changed?** If yes, coupling is High — it's causing
  pain right now.
- **Is an external dependency likely to change?** (e.g., swapping SDKs, adding a
  second backend) If yes, missing adapter is High.
- **Is this code under test?** IO in the middle is High if it's blocking test
  coverage, Medium if tests exist and work anyway.
- **How big is the team?** The New-Hire test matters more with multiple developers.

State your calibration assumptions briefly before the punch list.
