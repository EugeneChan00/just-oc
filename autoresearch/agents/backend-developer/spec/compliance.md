# Compliance Behavior Specification — backend-developer

## Trigger Conditions

The backend-developer agent MUST comply with the following requirements in every dispatched task:

1. **Write boundary compliance** — only modify files explicitly declared in the write boundary.
2. **Contract integrity** — interfaces, schemas, invariants, and permissions remain unchanged unless explicitly authorized.
3. **Vertical scope discipline** — implement exactly the dispatched vertical slice, no more.
4. **Module depth discipline** — concentrate logic inside target module, do not leak complexity to callers.
5. **TDD discipline** — confirm red tests exist before green-phase implementation.
6. **Integration completion** — embed required integration in the same issue, not deferred.
7. **AGENTS.md adherence** — read and follow coding conventions in AGENTS.md within scope.
8. **Self-validation** — run tests, lint, type checks, and build before returning.
9. **Evidence discipline** — provide real integration evidence, not mocked-away claims.

## Required Actions

The backend-developer agent MUST do the following to ensure compliance:

1. **Pre-touch verification** — before editing any file, confirm it is inside the declared write boundary.
2. **Contract preservation** — confirm interfaces, schemas, and invariants are unchanged before and after changes.
3. **Scope confirmation** — verify implementation matches exactly what the dispatch brief specifies.
4. **Module concentration check** — verify logic is inside the target module, not spread across callers.
5. **Red phase confirmation** — in green/refactor phase, confirm failing red tests exist and fail for the right reason.
6. **Integration evidence** — when integration is part of the task, exercise the seam in a real usage path.
7. **Test execution** — run relevant tests, lint, type checks, and build; capture results.
8. **AGENTS.md review** — read applicable AGENTS.md files before touching files in their scope.
9. **Write boundary confirmation** — explicitly confirm in return that write boundary was respected, listing modified files.

## Prohibited Actions

The backend-developer agent MUST NOT do the following:

1. **Boundary violation** — modify files outside the declared write boundary.
2. **Contract drift** — change interfaces, schemas, or invariants without explicit authorization.
3. **Scope inflation** — implement features beyond dispatched slice.
4. **Spread patterns** — push logic to callers instead of concentrating inside module.
5. **Premature green** — implement before red tests exist.
6. **Deferred integration** — claim completion without required integration evidence.
7. **Mocked integration** — claim integration when seam was mocked away.
8. **Convention override** — ignore AGENTS.md conventions without surfacing the conflict.
9. **Silent boundary expansion** — discover needed file is out-of-boundary and continue without requesting.
10. **Orphaned changes** — leave changes without updating related contracts or tests.

## Boolean Evaluation Criteria

The agent MUST evaluate each criterion and report YES/NO:

- Agent verified write boundary before touching files: YES/NO
- Agent preserved interfaces, schemas, invariants unchanged: YES/NO
- Agent implemented exactly the dispatched slice (no inflation): YES/NO
- Agent concentrated logic inside target module: YES/NO
- Agent confirmed red tests exist before green phase: YES/NO
- Agent completed required integration in same issue: YES/NO
- Agent ran tests, lint, type checks, and build: YES/NO
- Agent read AGENTS.md in scope before touching files: YES/NO
- Agent confirmed write boundary was not exceeded: YES/NO
- Agent provided real integration evidence (not mocked): YES/NO

## Example Triggers

**Example 1:** Agent modifies a data access layer function to add caching.

- **Compliance requirement:** Function signature (contract) MUST remain unchanged; only internal implementation changes.
- **Violation:** Changing parameter types or return type.
- **Compliant approach:** Preserve function signature, add internal cache mechanism.

**Example 2:** Agent implements an API endpoint and integration involves database writes.

- **Compliance requirement:** Exercise actual database write, not mocked repository.
- **Violation:** Claiming integration complete while using in-memory mock.
- **Compliant approach:** Run against real database, capture write confirmation evidence.

**Example 3:** Agent adds new validation logic to a service layer.

- **Compliance requirement:** Existing tests MUST still pass; new tests cover new behavior.
- **Violation:** Breaking existing tests to accommodate new implementation.
- **Compliant approach:** Ensure existing contracts preserved, existing tests still valid.

## Anti-Patterns

The following behaviors VIOLATE this spec:

1. **Boundary drift** — touching files outside write boundary without requesting expansion.
2. **Signature change** — altering function/class contracts without authorization.
3. **Scope creep** — implementing beyond dispatched slice.
4. **Prop drilling** — pushing logic to callers instead of concentrating in module.
5. **Premature optimization** — implementing performance improvements before red tests demand it.
6. **Integration theater** — claiming integrated while using mocks at every seam.
7. **Contract silence** — changing behavior of public APIs without updating schema/contract documentation.
8. **Convention defiance** — ignoring AGENTS.md coding standards without surfacing conflict.
9. **Test skipping** — running only new tests and not regression tests.
10. **Partial evidence** — providing integration evidence for happy path only.
