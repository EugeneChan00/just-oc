---
name: code-writing
description: >
  Enforces disciplined code structure when writing TypeScript/JavaScript. Use this skill
  whenever writing new modules, refactoring existing code, creating functions, defining
  types, or implementing any feature. Covers: file layout order, error handling patterns,
  function scope discipline, type safety, namespace design, and antipattern detection.
  Trigger on ANY code creation or modification task — not just when the user asks about
  "code quality". If you are about to write or edit a .ts or .js file, consult this skill.
---

# Code Writing Discipline

This skill encodes hard-won lessons from real refactoring work. Every rule here exists
because the opposite was tried and produced code that was unreadable, untestable, or
silently broken. Follow these patterns and your code will be readable top-to-bottom,
testable in isolation, and honest about its failure modes.

## File Layout Order

Code files read like documents. A reader opening a file should understand what it exports
before seeing how it works. Organize every file in this order:

```
1. Imports
2. Types / Interfaces / Enums  (what shapes exist)
3. Error classes               (what can go wrong)
4. Constants                   (what values are fixed)
5. Internal helpers            (how things work — private)
6. Implementation functions    (the actual logic — grouped by concern)
7. Public API / Exports        (what consumers see)
```

The public API at the bottom is the assembly point — it maps names to the functions
defined above. A reader scans imports to understand dependencies, types to understand
shapes, then scrolls to the bottom to see what's exported. Implementation details are
in the middle where they belong.

When a module uses namespace objects (like `git.branch.*`, `git.worktree.*`), define
all functions as standalone named functions first, then assemble them into the namespace
object at the bottom. This makes each function independently readable and testable:

```typescript
// Good: standalone functions, assembled at bottom
function branchExists(name: string): boolean { ... }
function branchCreate(name: string, base: string): void { ... }

export const git = {
  branch: { exists: branchExists, create: branchCreate },
};

// Bad: methods defined inline on an object literal
const branch = {
  exists(name: string): boolean { ... },  // can't test independently
  create(name: string, base: string): void { ... },
};
```

## Error Handling: The Two-Track Pattern

Every function that calls something that can fail faces a choice: throw or return a
result. The wrong answer is "both" — catching an exception and rethrowing a different
one creates nested try-catch, which is the single worst readability antipattern.

### The execSafe / exec pattern

When you wrap an external API that throws (like `execFileSync`, `fetch`, database
drivers), create exactly two internal helpers:

```typescript
type Result<T> = { ok: true; value: T } | { ok: false; error: SomeError };

// Returns result union — never throws the domain error
function doSafe(...): Result<T> { ... }

// Throws on failure — for callers that want exceptions
function doOrThrow(...): T {
  const result = doSafe(...);
  if (!result.ok) throw result.error;
  return result.value;
}
```

Then each function in your module picks ONE track:

- **Query functions** (existence checks, status, listing) use `doSafe` and return
  values or booleans. They never throw. No try-catch in the caller.
- **Mutation functions** (create, delete, write) use `doOrThrow`. They throw on
  unexpected failure. The caller decides whether to catch.
- **Expected-failure operations** (merge conflicts, HTTP 404) use `doSafe` and
  return a result union. Conflicts are data, not exceptions.

This eliminates nested try-catch entirely. The only try-catch in the codebase is
inside `doSafe`, at the boundary with the external API. Everything above it uses
either result checking (`if (!result.ok)`) or exception propagation — never both.

### Never do this

```typescript
// BAD: try-catch wrapping a function that already has try-catch internally
function createThing() {
  try {
    exec(args);  // exec has its own try-catch
  } catch (e) {
    if (e instanceof MyError) {
      try {        // nested try-catch — unreadable
        exec(otherArgs);
      } catch (e2) { ... }
    }
  }
}
```

```typescript
// GOOD: query first, then act
function createThing() {
  if (thingExists()) return;        // query — uses doSafe, no throw
  prepareForThing();                // mutate — uses doOrThrow
  doCreateThing();                  // mutate — uses doOrThrow
}
```

The pattern is called **query-then-act**: check state with a non-throwing query,
then mutate with a throwing call. The caller is flat — no nesting, no catching.

## Function Scope: One Function, One Job

A function should do one thing. Not "one thing and also check if it needs to do
the thing and also recover if the thing was already done."

Signs a function is doing too much:
- It has both query logic AND mutation logic interleaved
- It catches an error to decide what to do next (exception-driven branching)
- It calls the same external operation more than once with different arguments
- Two functions in the module are 90% identical (duplication = missing abstraction)

The fix is always decomposition:

```typescript
// BAD: one function that queries, creates, and recovers
function ensureWorktree(dir, id, base) {
  try {
    exec(`git worktree add -b ${branch} ${path} ${base}`);
  } catch (err) {
    if (err.stderr.includes("already exists")) {    // parsing errors for control flow
      try {
        exec(`git worktree add ${path} ${branch}`); // retry with different args
      } catch (err2) { throw new Error(...); }
    }
    throw new Error(...);
  }
}

// GOOD: decomposed into query + act
function ensureWorktree(dir, id, base) {
  const entries = listWorktrees();                    // query (no throw)
  const existing = entries.find(matchPath(dir, id));
  if (existing) return existing.path;                 // already done

  if (!branchExists(branch)) branchCreate(branch, base);  // query then act
  return worktreeAdd(path, branch);                        // act
}
```

## Type Safety

### No `any`

Every `any` is a lie. It tells the type checker "trust me" when the programmer
doesn't actually know the shape. Use `unknown` and narrow with type guards.

```typescript
// BAD
} catch (err: any) {
  const stderr = err.stderr?.toString() ?? "";

// GOOD
} catch (error: unknown) {
  if (!(error instanceof Error)) throw error;
  const e = error as Error & { status?: number | null };
```

### No string parsing for typed data

If an external API returns structured data, parse it into a typed object once
at the boundary. Never pass raw strings through the codebase and parse them
at each call site.

```typescript
// BAD: every caller parses the same string differently
const output = exec("git status --porcelain");
if (output.includes("M ")) { ... }  // fragile

// GOOD: parse once, return typed
function status(cwd: string): GitStatus {
  const result = execSafe(["status", "--porcelain"], { cwd });
  if (!result.ok) return { clean: true, files: [] };
  const files = result.stdout.split("\n").filter(Boolean).map(l => l.slice(3));
  return { clean: files.length === 0, files };
}
```

### No `err.stderr.includes("some message")` for control flow

Error message content is not a stable API. Git can change wording between versions.
Locale settings change messages. Never branch on error string content.

```typescript
// BAD: parsing stderr strings for branching
if (stderr.includes("branch already exists")) { ... }

// GOOD: query before acting
if (branchExists(name)) { ... }
```

## Namespace Design

When grouping related operations into a namespace object, follow these rules:

**Sub-namespaces group methods by resource type.** Methods that operate on a specific
named resource (a branch name, a worktree path, a database table) go under a
sub-namespace. Methods that operate on global state go at the top level.

```typescript
export const git = {
  // Top-level: operate on repo/cwd state
  status, commit, merge,

  // Sub-namespace: operate on a named branch
  branch: { exists, create, delete, name },

  // Sub-namespace: operate on a named worktree path
  worktree: { add, remove, list, create, cleanup },
};
```

**Each method in the namespace should be a standalone function.** Don't define
methods inline on the object literal. Define them as named functions above the
namespace object, then reference them. This makes each function independently
readable, searchable, and testable.

## Shell Command Safety

When executing shell commands, use array-form APIs that structurally prevent
injection. Never interpolate variables into shell command strings.

```typescript
// BAD: string interpolation — injection if branch contains $() or backticks
execSync(`git branch -D "${name}"`);

// GOOD: array args — structurally impossible to inject
execFileSync("git", ["branch", "-D", name]);
```

## Module Boundaries

**One module, one responsibility.** If you find a module importing from a layer
above it (exec importing from config, worktree importing from exec), the
boundary is wrong. Dependencies point downward only.

**Don't create wrapper modules that just re-export.** If module A wraps module B
and every function in A is `return B.thing()`, module A shouldn't exist. Consumers
should import B directly.

**Don't split horizontally.** When implementing a feature, write it vertically in
one module rather than spreading thin changes across 8 files simultaneously. A
module that's complete and tested is better than 8 modules that each have 20% of
the implementation.

## Idempotency Contracts

For every function that creates, deletes, or modifies state, document what happens
when the precondition is already satisfied:

| Method | Already exists | Doesn't exist |
|--------|---------------|---------------|
| `create` | throws / returns existing | creates |
| `delete` | deletes | throws / no-op |
| `ensure` | returns existing | creates |

Pick one behavior per method and be consistent. An `ensure` method is idempotent
(safe to call twice). A `create` method is not. Name accordingly.

## Checklist Before Committing Code

Before considering any code complete, verify:

- [ ] File reads top-to-bottom: imports → types → errors → helpers → implementation → exports
- [ ] No `any` types (use `unknown` and narrow)
- [ ] No nested try-catch (use the two-track execSafe/exec pattern)
- [ ] No error string parsing for control flow (query before acting)
- [ ] Each function does one thing (no query+mutate+recover combos)
- [ ] No duplicated functions (>50% similarity = extract common logic)
- [ ] Shell commands use array args (no string interpolation)
- [ ] Dependencies point downward only (no upward imports)
- [ ] Idempotency behavior documented for state-changing functions
- [ ] Types exported before implementations in file layout
