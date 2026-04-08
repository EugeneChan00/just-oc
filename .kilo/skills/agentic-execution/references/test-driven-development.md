# TDD-First Implementation Reference (Serena-First)

This reference defines how feature and bug work should be executed in this repo.

Primary goal:
- enforce red/green/refactor
- prefer modifying or reducing existing code over appending new code
- use Serena semantic navigation before raw text search

Source inspiration:
- https://github.com/obra/superpowers/blob/main/skills/test-driven-development/SKILL.md

## Scope

Use this workflow when the task is:
- feature implementation
- bug fix
- behavior change
- non-trivial refactor with behavior guarantees

Scenario selection:
- choose or adapt a case from `test-specs.md` before entering RED

## Non-Negotiable Rules

1. Do not change production behavior before writing at least one failing test.
2. Confirm the failing test fails for the expected reason.
3. Implement the smallest change that makes the failing test pass.
4. Refactor only after green.
5. Prefer edit/delete/reduce of existing code before adding new code.
6. New code snippets are a last-resort fallback, not the default path.
7. Do not write mock-based tests (no mock/patch/stub-driven behavior verification).

## Mocking Policy (Strict)

- Avoid mocks, stubs, monkeypatches, and heavy dependency fakes in feature tests.
- Test behavior through real code paths and real collaborators inside the repo.
- Prefer:
  - real objects and fixtures
  - in-memory test backends
  - lightweight integration-style tests at stable boundaries
- If a test would require mocking to be practical, redesign the test target or production seam first.
- For external-system constraints, use hermetic local/in-memory test harnesses instead of mocks.

## Serena-First Investigation Protocol

Run this before writing tests or code:

1. Validate Serena availability:
   - `mcp__serena__get_current_config`
2. Ensure active project:
   - `mcp__serena__activate_project`
3. Map nearby symbols:
   - `mcp__serena__get_symbols_overview`
4. Identify existing implementation points:
   - `mcp__serena__find_symbol`
5. Map callers and impacted behavior surfaces:
   - `mcp__serena__find_referencing_symbols`
6. Search tests and string/assignment patterns:
   - `mcp__serena__search_for_pattern`

Notes:
- In Python, function/class declaration typically equals definition site.
- Treat "variable declaration" as assignment sites in code.

Fallback:
- Use `rg` only after Serena tools cannot resolve the question.
- Return to Serena for precise symbol/reference mapping when possible.

## TDD Cycle

### Phase 0: Investigate Existing Code

Create a short inventory before changes:
- candidate symbols to modify
- candidate symbols to delete/reduce
- impacted references
- likely tests to extend
- selected scenario ID from `test-specs.md` and expected evidence

### Phase 1: RED

1. Add or update exactly one test describing the next behavior increment.
2. Run the narrowest test target.
3. Record red evidence:
   - command used
   - failing test name
   - failure reason

If test is unexpectedly green, tighten test assertions before continuing.
If test only fails because of mocked expectations, rewrite it to verify real behavior.

### Phase 2: GREEN (Minimal Change)

Try in this order:
1. Modify existing function/method logic.
2. Reuse existing helper and remove duplication.
3. Delete dead/overlapping code and simplify flow.
4. Add small local code inside an existing symbol only if required.
5. Add new symbol/file only if all previous options fail.

### Phase 3: REFACTOR

After green:
- improve naming/structure
- remove duplication
- collapse unnecessary indirection
- keep behavior unchanged

Re-run the same test scope to confirm green.

### Phase 4: Verify

Collect minimal evidence:
- red command + failure summary
- green command + pass summary
- list of modified symbols and why they were chosen

## Guardrails Against Declarative-First Coding

1. Block implementation when no failing test has been executed.
2. Block append-heavy changes if Serena investigation did not include:
   - definition/declaration location
   - references/call sites
   - impacted tests
3. Block PR/task completion if added tests are mock-first instead of behavior-first through real code paths.

## Definition Of Done

Done means:
- at least one red-to-green cycle is completed for each behavior increment
- existing code was considered first and used where feasible
- added code is justified as last resort
- tests are passing for affected scope
- newly added tests are not mock-driven

## Quick Trigger Phrases

Use this reference when user asks:
- "implement feature X"
- "fix bug Y"
- "change behavior Z"
- "refactor safely with tests"
