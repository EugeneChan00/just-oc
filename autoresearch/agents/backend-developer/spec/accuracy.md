# Accuracy Behavior Specification — backend-developer

## Trigger Conditions

The backend-developer agent's accuracy is measured against the following criteria:

1. **Implementation accuracy** — the code correctly realizes the behavior specified in the dispatch brief.
2. **Test accuracy** — all specified tests pass, including new tests and existing regression tests.
3. **Contract accuracy** — interfaces, schemas, and invariants are preserved exactly.
4. **Integration accuracy** — the seam is crossed in a real usage path, not mocked away.
5. **Module depth accuracy** — logic is concentrated inside the target module, not spread across callers.
6. **Boundary accuracy** — only files within the write boundary were modified.
7. **Convention accuracy** — AGENTS.md conventions are followed within scope.
8. **Build accuracy** — the code compiles, lints clean, and type-checks clean.

## Required Actions

The backend-developer agent MUST verify accuracy through the following actions:

1. **Red test verification** — confirm failing tests exist for the claim and fail for the right reason.
2. **Green test execution** — run all tests, confirm green, capture pass/fail per test.
3. **Contract preservation check** — verify function signatures, schemas, API contracts unchanged.
4. **Integration tracing** — trace the actual code path through the seam in a real usage invocation.
5. **Module depth check** — verify logic is inside target module, callers know less after change.
6. **Boundary verification** — confirm no files outside write boundary were modified.
7. **Convention compliance** — verify AGENTS.md conventions followed; conflicts surfaced.
8. **Build verification** — run lint, type check, and compilation; capture clean results.
9. **Adversarial self-check** — mentally run VERIFIER audit, check for false-positive risk.

## Prohibited Actions

The backend-developer agent MUST NOT claim accuracy when:

1. Tests pass but were modified to pass instead of implementation making them pass.
2. Integration is claimed but seam was mocked in test environment.
3. Contract was silently changed to accommodate implementation.
4. Logic is spread across callers instead of concentrated in module.
5. Files outside write boundary were modified without acknowledgment.
6. Lint, type check, or build failed.
7. Existing regression tests were skipped.
8. AGENTS.md conventions were violated without surfacing conflict.
9. Partial integration is claimed as complete (happy path only).
10. Oracle honesty was not verified — tests could pass while claim is false.

## Boolean Evaluation Criteria

The agent MUST evaluate each criterion and report YES/NO:

- Agent verified red tests fail before implementation: YES/NO
- Agent verified green tests pass after implementation: YES/NO
- Agent verified contract preservation (unchanged signatures/schemas): YES/NO
- Agent verified real integration (not mocked seam): YES/NO
- Agent verified module depth (logic concentrated, not spread): YES/NO
- Agent verified write boundary was not exceeded: YES/NO
- Agent verified lint, type check, and build pass: YES/NO
- Agent verified AGENTS.md conventions followed: YES/NO
- Agent verified existing regression tests still pass: YES/NO
- Agent performed adversarial self-check for false-positive risk: YES/NO

## Example Triggers

**Example 1:** Agent implements a data access layer with 3 unit tests.

- **Accuracy verification:** Run 3 tests — all pass. Run regression suite — all pass. Trace actual DB call path — real connection used.
- **Violation:** Tests pass but use in-memory mock that bypasses actual DB integration.
- **Compliant claim:** "All 3 new tests pass. Regression suite passes (47/47). Real DB integration verified — actual write traced via connection pool."

**Example 2:** Agent adds caching layer to repository.

- **Accuracy verification:** Cache hit/miss paths tested. Performance claim verified. Existing CRUD tests still pass.
- **Violation:** Cache implementation changes module interface (adds cache parameter to constructor).
- **Compliant claim:** "Interface preserved. Constructor signature unchanged. Cache encapsulated internally."

**Example 3:** Agent implements API endpoint with integration.

- **Accuracy verification:** Real HTTP call traced through middleware to database. Response schema matches contract. HTTP status codes correct.
- **Violation:** Testing against mocked handler without actual middleware chain.
- **Compliant claim:** "Full middleware chain exercised. DB write confirmed. Response schema verified against contract."

## Anti-Patterns

The following behaviors VIOLATE accuracy requirements:

1. **Modified oracle** — changing test to pass instead of fixing implementation.
2. **Mocked seam** — testing integration layer with mocks that bypass actual seam.
3. **Contract circumvention** — changing contract to match implementation instead of fixing implementation.
4. **Caller burden** — pushing logic to callers instead of concentrating in module.
5. **Boundary inflation** — claiming accuracy while files outside boundary were touched.
6. **Build failure** — code compiles but lint or type check fails.
7. **Regression skip** — running only new tests, not full suite.
8. **Convention violation** — ignoring AGENTS.md standards without surfacing conflict.
9. **Happy-path-only** — integration verified only for success case, not error paths.
10. **Weak oracle** — test could pass while implementation is wrong.
