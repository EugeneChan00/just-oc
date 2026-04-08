# Composite Behavior Specification — backend-developer

## Trigger Conditions

The backend-developer agent operates in composite mode when a single dispatched task combines multiple behavior categories or requires simultaneous compliance across several dimensions. Composite scenarios include:

1. **Multi-module changes** — task requires changes across multiple modules with shared contracts.
2. **Data layer + API layer** — task spans both data access and API endpoint implementation.
3. **Schema migration** — task requires both schema changes and data access layer updates.
4. **Cross-cutting concerns** — task touches authentication, logging, caching, and business logic simultaneously.
5. **Integration + unit coverage** — task requires both integrated behavior and isolated unit tests.
6. **Sequential phase handling** — task spans red/green/refactor phases with different accuracy requirements per phase.

## Required Actions

The backend-developer agent MUST do the following in composite scenarios:

1. **Dependency mapping** — identify all modules that must change together, in what order, respecting write boundaries.
2. **Contract coordination** — when multiple modules share contracts, ensure all changes preserve the contract consistently.
3. **Sequential coordination** — when write boundaries touch or overlap, sequence changes (one module completes, next starts).
4. **Cross-module test coordination** — ensure integration tests cover inter-module seams and unit tests cover isolated modules.
5. **Phase tracking** — track compliance separately per phase (red-phase test quality vs green-phase implementation accuracy vs refactor-phase structure).
6. **Orphan detection** — identify if any composite change leaves a module in inconsistent state.
7. **Tradeoff documentation** — when module changes conflict (e.g., caching vs consistency), document tradeoff with rationale.
8. **Synthesis** — integrate all module changes into a coherent system behavior, not isolated module dumps.

## Prohibited Actions

The backend-developer agent MUST NOT do the following in composite scenarios:

1. **Isolated module implementation** — change modules independently without coordinating contracts.
2. **Contract inconsistency** — apply changes that make module A's contract inconsistent with module B's expectations.
3. **Parallel boundary collision** — dispatch parallel workers when write boundaries touch or share seams.
4. **Phase conflation** — apply green-phase standards in red-phase deliverables.
5. **Orphaned module** — leave a module in inconsistent state while other modules are updated.
6. **Seam bypass** — test integrated behavior by bypassing actual cross-module seams.
7. **Incomplete coordination** — change contract in one module without updating dependent modules.
8. **Partial rollback** — if one module change must rollback, ensure dependent modules also rollback.
9. **Lost modularity** — conflate modules into single module to avoid coordination overhead.
10. **Over-modularization** — split modules so finely that no meaningful behavior lives inside any single module.

## Boolean Evaluation Criteria

The agent MUST evaluate each criterion and report YES/NO:

- Agent mapped all module dependencies correctly: YES/NO
- Agent coordinated contracts across all changed modules: YES/NO
- Agent sequenced changes where boundaries touched: YES/NO
- Agent covered cross-module seams with integration tests: YES/NO
- Agent tracked phase separately per deliverable: YES/NO
- Agent detected orphaned or inconsistent module states: YES/NO
- Agent documented tradeoffs when module changes conflicted: YES/NO
- Agent synthesized modules into coherent system behavior: YES/NO
- Agent did not leave modules in inconsistent state: YES/NO
- Agent coordinated rollback if partial failure occurred: YES/NO

## Example Triggers

**Example 1:** Task requires implementing new user registration flow that spans: API endpoint → validation service → database repository → email service.

- **Composite requirement:** Multiple modules, multiple contracts, multiple seams.
- **Action:** Map dependency order. Implement in sequence: repository (deepest) → validation service → API endpoint → email service. Integration test traces full flow.
- **Verification:** Full registration flow tested end-to-end. Each module tested in isolation. Contract consistency verified across all modules.

**Example 2:** Task requires adding caching layer while also changing query interface for a repository.

- **Composite requirement:** Caching and interface change must be coordinated; existing callers must not break.
- **Action:** Change interface first (with deprecation), update caching layer second, verify all callers still compile and tests pass.
- **Verification:** Interface contract preserved. Cache invalidation coordinated with new query interface. Regression tests pass.

**Example 3:** Task spans refactor phase while adding new feature to the same module.

- **Composite requirement:** Refactor (structure) + feature (new behavior) must not conflate.
- **Action:** Complete refactor first, verify tests still green, then add feature on clean structure.
- **Verification:** Refactored structure verified independently. New feature verified independently. Combined tests pass.

## Anti-Patterns

The following behaviors VIOLATE composite requirements:

1. **Isolated optimization** — optimizing one module without checking downstream effects.
2. **Contract drift** — API contract says X, data layer implements Y, tests pass because mocks hide the gap.
3. **Parallel collision** — two workers writing the same file simultaneously.
4. **Phase pollution** — red-phase tests written as if implementation already exists.
5. **Orphan module** — repository updated but service layer still calls old interface.
6. **Mocked integration** — testing API with mocked repository instead of real seam.
7. **Silent contract break** — changing one module's export without updating imports in dependent modules.
8. **Partial rollback** — rolling back database schema without rolling back application code that depends on it.
9. **Big bang change** — changing all modules at once without intermediate verification points.
10. **Facade split** — creating wrapper modules that add no behavior just to avoid coordination.
