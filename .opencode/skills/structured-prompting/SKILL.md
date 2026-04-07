---
name: structured-prompting
description: >
  Write structured prompts and documents that agents execute reliably. Use this skill
  whenever writing prompt text inside directive files, milestone steps, execution
  artifacts, task descriptions, agent instructions, verification strategies, or any
  document that an LLM agent will follow. Also use when the user says "write a prompt",
  "rewrite this in imperative", "make this clearer for agents", "structure this better",
  or when reviewing/editing any `<prompt>`, `<verify>`, or instructional content. This
  skill applies to ALL prose that instructs an agent — not just directive artifacts but
  also skill files, system prompts, and task descriptions.
---

# Structured Prompting

Write prompt text and instructional documents that agents execute reliably. Agents are
smart but contextless — they see only what you give them. Every sentence in a prompt is
a resource the agent spends attention on. Structured prompting is about making each
sentence count: clear voice, specific references, explicit delegation, and verification
strategies that catch real failures.

This skill has four features. Apply whichever are relevant to the content you are writing.


## Feature 1: Imperative Voice

Agents respond to commands, not descriptions. Imperative voice ("Create...", "Run...",
"Verify...") tells the agent what to do. Descriptive voice ("You should create...",
"The agent will run...") tells the agent about itself — wasted tokens that dilute the
actual instruction.

### The rule

Write every instruction as a direct command. Start sentences with a verb in imperative
form. Remove hedging, narration, and self-referential framing.

### Why this matters

When an agent reads "You are planning a set of directives", it allocates attention to
modeling its own identity rather than executing. When it reads "Plan a set of directives",
it starts planning immediately. The imperative form is shorter, clearer, and leaves zero
ambiguity about who acts.

Descriptive phrasing also introduces passive constructions ("the file will be created",
"tests should be written") that obscure the actor. In agent prompts, the actor is always
the agent — make that implicit through imperative voice rather than explicit through
narration.

### Patterns

| Weak (descriptive/passive) | Strong (imperative) |
|---|---|
| You are planning a set of directives | Plan a set of directives |
| The agent should create the file | Create the file |
| This step is for writing tests | Write tests |
| Your job is to verify the results | Verify the results |
| Tests should be written for each function | Write tests for each function |
| After validation, the engine will fan out | After validation, the engine fans out |
| For each gap found, describe what is missing | For each gap found, describe: what is missing |
| Check all branches. You should build a table | Check all branches. Build a table |

### Edge cases

Imperative voice applies to **instructions** — what the agent should do. It does not
apply to:
- **Context sentences** explaining why something matters: "The execution engine fans out
  to subdirectives after the prompt phase completes" — this is background, not an action.
- **Conditional framing**: "If any file fails validation, fix it in place" — the "if"
  clause is context, the "fix" clause is imperative. Both are fine.
- **Reference descriptions**: "This directory contains the shared types" — describing
  existing state, not instructing action.

The test: if a sentence tells the agent to DO something, it should start with a verb. If
it tells the agent ABOUT something, descriptive voice is fine.


## Feature 2: Skill and Tool Delegation

When a skill or tool exists for a subtask, delegate to it by name. Do not re-specify the
skill's rules inside the prompt — that creates two sources of truth that drift apart. The
prompt's job is to say WHAT to create and WHY; the skill's job is to enforce HOW.

### The rule

Reference skills with their slash command (`/directive-creation`, `/create-spec`) directly
inside prompt text. State what the agent should produce, then tell it which skill to invoke.
Let the skill handle format enforcement, required fields, and structural validation.

### Why this matters

Skills are versioned, maintained, and tested independently. When you inline a skill's rules
into a prompt ("each file MUST have YAML frontmatter with id, title, goal..."), those rules
become a frozen snapshot that will not update when the skill evolves. Worse, the agent now
has two instruction sources that may conflict.

Delegation also reduces prompt length. A 20-line format specification becomes one line:
"Invoke `/directive-creation` to create the file." The agent loads the skill at invocation
time and gets the current, complete rules.

### Patterns

**Delegate creation to a skill:**
```
Invoke `/directive-creation` to create a directive with 2 sequential steps.
```

**Delegate validation to a skill:**
```
Read the `/directive-creation` skill's format reference to confirm each file
conforms to the unified markdown+XML schema.
```

**Delegate repair to a skill:**
```
If any file fails validation, invoke `/directive-creation` to fix it in place.
```

**Specify the WHAT, delegate the HOW:**
```
Create `df2-csv-parser.md` as a subdirective (leaf node — no <subdirectives>
allowed). Set `parent_directive: df2-data-pipeline` in frontmatter.
Invoke `/directive-creation` once per file — the skill enforces the unified
markdown+XML format, required frontmatter fields, spec sections, adversarial
blocks, and correct step tag ordering.
```

Notice: the prompt specifies domain constraints (leaf node, parent_directive value) that
are specific to THIS directive. The skill handles generic format constraints (frontmatter
fields, spec structure, tag ordering) that apply to ALL directives.

### When NOT to delegate

Do not delegate when:
- No skill exists for the subtask — inline the rules directly
- The prompt needs to override the skill's defaults — state the override explicitly
- The agent operates in a context where skills are not available (raw API calls, non-CLI
  environments)


## Feature 3: Specific Over Vague

Agents have no ambient context. They do not know your project layout, naming conventions,
or what "the usual way" means. Every reference in a prompt must resolve to something
concrete — a file path, a function name, an expected value.

### The rule

Name files, functions, expected behavior, and constraints explicitly. Replace every
pronoun that refers to a technical artifact with the artifact's actual name. Replace
every "appropriate" or "as needed" with the specific thing.

### Why this matters

Vague prompts produce vague results and force the agent into guessing. When the agent
guesses wrong, you spend a retry correcting it. When the prompt says exactly what to
produce, the agent produces exactly that — first try.

This is especially critical for:
- **File paths**: relative paths resolve differently depending on CWD. Use absolute paths
  or paths anchored to a known root.
- **Function signatures**: "a function that parses CSV" vs "parseCsv(input: string): Record[]
  that splits on newlines, handles quoted fields, and returns an array of objects keyed by
  header names."
- **Test expectations**: "tests should pass" vs "at least 4 tests per function, each asserting
  a specific return value."

### Patterns

| Vague | Specific |
|---|---|
| Implement the parser | Implement `pipeline/csv-parser.ts` exporting `parseCsv(input: string): Record[]` |
| Write tests | Write `csv-parser.test.ts` with tests for: normal CSV, quoted fields, empty input, malformed rows |
| Handle edge cases | Handle: empty string, single character, unicode characters, strings with leading/trailing whitespace |
| Create the types file | Create `pipeline/types.ts` defining `Record` and `Pipeline` interfaces |
| The output directory | `/home/user/project/RL/test/dog-food/` |
| Use the right profile | `backend_developer` for implementation, `test_engineer` for tests |
| At least a few tests | At least 4 tests per function using bun test. All tests must assert specific values. |


## Feature 4: Structured Verification

Verification sections (`<verify>` blocks, review checklists, acceptance criteria) are
instructions for a verification agent — not a human. They need the same structure as
execution prompts: imperative voice, specific checks, and explicit failure modes.

### The rule

Structure every verification block with three sections:
1. **What to check** — concrete list of observable facts to verify
2. **Expected results** — what success looks like (counts, values, states)
3. **Anti-patterns to detect** — common failure modes the verifier should catch

This three-part structure prevents the two most common verification failures: checking
only the happy path (no anti-patterns) and checking vague properties ("it works") instead
of specific facts.

### Why this matters

A verification agent that receives "confirm it works" will run one happy-path test and
declare success. A verification agent that receives "confirm `parseCsv` handles quoted
fields — input `'"hello","world"'` produces `[{col1: "hello", col2: "world"}]`" will
actually test the edge case.

Anti-patterns are especially valuable because they encode institutional knowledge about
HOW things fail. "Tests that only check 'response is not null' instead of specific values"
is a failure mode that an agent without this instruction would never think to probe for.

### Patterns

**Full verification block:**
```xml
<verify>
Confirm all 5 directive files exist and conform to the unified schema.

**What to check:**
- All 5 files exist in the dogfood-test-v2/ directory
- Each file has YAML frontmatter with required fields
- Each file has `<spec>` section with at least one feature and two criteria
- Subdirective files do NOT contain `<subdirectives>` in any step

**Expected results:**
- df2-string-transform: 2 steps completed (implement + test)
- df2-data-pipeline: 3 steps completed (setup + parallel fan-out + integration test)
- df2-integration: 2 steps completed (CLI + integration test)

**Anti-patterns to detect:**
- Files that are empty stubs or missing the `<spec>` section
- Subdirective files with `<subdirectives>` tags (violates leaf node constraint)
- Directives with no `<verify>` blocks on steps
- Missing `<adversarial>` block in any spec section
</verify>
```

**Phased audit (for complex verification):**
```
**Phase 1 — Audit git commit history.**
List all branches. Inspect commit history. Build a mapping table.

**Phase 2 — Verify execution completeness.**
Read each directive. Extract step names. Cross-reference against git history.
Flag any step with no corresponding commit.

**Phase 3 — Verify code artifacts.**
Run the full test suite. Report: total, passing, failing, import errors.
```

Phases work well when verification has distinct stages that build on each other.
Each phase is self-contained with its own imperative instructions.

### Anti-patterns in verification writing

- **"Confirm it works"** — what does "works" mean? Name the specific behavior.
- **Shell commands as verification** — `bun test` is a tool, not a strategy. The strategy
  is "run tests, confirm all pass, check for import errors indicating path mismatches."
- **No anti-patterns section** — the verifier only checks the happy path and misses
  subtle failures like hardcoded outputs, phantom execution, or path mismatches.
- **Generic gap analysis** — "the engine needs improvement" vs "src/exec/schema.ts does
  not handle markdown format — the validator is still YAML-only. Add a markdown parser
  branch in `validateDirectiveYaml` around line 45."


## Applying Multiple Features Together

Real prompts use all four features simultaneously. Here is how they compose:

```xml
<prompt>
Plan a set of executable directives for a data utilities toolkit built at
`/home/user/project/RL/test/dog-food/`.
                                                        ← specific path (F3)

Research what a minimal but meaningful data toolkit needs. Then use
`/directive-creation` to create each directive file.    ← skill delegation (F2)
Invoke `/directive-creation` once per file — the skill enforces format compliance.

**Create `df2-csv-parser.md`** — Invoke `/directive-creation` to create a
subdirective (leaf node — no `<subdirectives>` allowed).
                                        ← imperative voice (F1) + delegation (F2)
Set `parent_directive: df2-data-pipeline` in frontmatter.
                                                        ← specific constraint (F3)
- Step 1 (`backend_developer`): Implement `pipeline/csv-parser.ts` — parse CSV
  string to array of record objects. Handle quoted fields, empty rows, header
  detection.                            ← specific profile, file, behaviors (F3)
- Step 2 (`test_engineer`): Write `csv-parser.test.ts` with tests for normal CSV,
  quoted fields, empty input, malformed rows.
                                        ← specific test cases (F3)
</prompt>
<verify>
Confirm all directive files exist and conform to the unified schema.
                                                        ← imperative (F1)

**What to check:**                                      ← structured verification (F4)
- Each file has YAML frontmatter with required fields
- Subdirective files do NOT contain `<subdirectives>`

**Anti-patterns to detect:**                            ← anti-patterns (F4)
- Files that are empty stubs
- Missing `<adversarial>` block in any spec section
</verify>
```


## Quick Reference

When writing or reviewing prompt text, run through this checklist:

1. **Voice**: Does every instruction start with a verb? Remove "you should", "your job is",
   "the agent will".
2. **Delegation**: Is there a skill for any subtask? Reference it by slash command instead
   of inlining its rules.
3. **Specificity**: Can every noun resolve to a concrete artifact? Replace "the file" with
   the filename, "tests" with the test count and framework.
4. **Verification**: Does every verify block have What/Expected/Anti-patterns? Does it name
   specific checks, not vague properties?
