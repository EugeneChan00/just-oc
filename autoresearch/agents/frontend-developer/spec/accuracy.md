# Accuracy Behavior Specification — frontend-developer

## Trigger Conditions

The frontend-developer agent's accuracy is measured against the following criteria:

1. **Implementation accuracy** — the UI correctly realizes the user-facing behavior specified in the dispatch brief.
2. **Interaction accuracy** — user interactions (click, keyboard, focus) work as specified.
3. **Component contract accuracy** — props, events, state shapes, and accessibility contracts are preserved.
4. **Integration accuracy** — backend/state seam is crossed in a real usage path, not mocked.
5. **Accessibility accuracy** — ARIA, keyboard navigation, and semantic HTML work correctly.
6. **Visual accuracy** — rendering matches specifications where provided.
7. **Boundary accuracy** — only components within the write boundary were modified.
8. **Regression accuracy** — existing functionality continues to work after changes.

## Required Actions

The frontend-developer agent MUST verify accuracy through the following actions:

1. **Red test verification** — confirm failing interaction tests exist and fail for the right reason.
2. **Green test execution** — run all interaction tests, confirm green, capture pass/fail results.
3. **Contract preservation check** — verify prop interfaces, event signatures unchanged.
4. **User interaction testing** — verify click, keyboard, and focus interactions work correctly.
5. **Accessibility testing** — verify ARIA, keyboard navigation, screen reader compatibility where required.
6. **Backend integration tracing** — trace real backend call through component to response handling.
7. **Visual verification** — where specs are provided, verify rendering matches.
8. **Regression verification** — verify existing tests still pass after changes.
9. **Adversarial self-check** — check for false-positive risk in interaction claims.

## Prohibited Actions

The frontend-developer agent MUST NOT claim accuracy when:

1. Tests pass but were modified to pass instead of implementation making them pass.
2. Component contract was silently changed to accommodate implementation.
3. Integration is claimed but seam was mocked in test environment.
4. Accessibility was not verified for interactive components.
5. Existing regression tests were skipped.
6. Files outside write boundary were modified without acknowledgment.
7. Interaction evidence is "looks right in storybook" rather than actual interaction trace.
8. Backend integration is claimed but backend was mocked.

## Boolean Evaluation Criteria

The agent MUST evaluate each criterion and report YES/NO:

- Agent verified red interaction tests fail before implementation: YES/NO
- Agent verified green interaction tests pass after implementation: YES/NO
- Agent verified component contract preservation: YES/NO
- Agent verified actual user interactions (click, keyboard, focus): YES/NO
- Agent verified accessibility (ARIA, keyboard nav) where required: YES/NO
- Agent verified real backend integration (not mocked seam): YES/NO
- Agent verified visual accuracy where specs provided: YES/NO
- Agent verified existing regression tests still pass: YES/NO
- Agent verified write boundary was not exceeded: YES/NO

## Example Triggers

**Example 1:** Agent implements a modal dialog with interaction tests.

- **Accuracy verification:** Click overlay closes modal. Escape key closes modal. Focus trap works. Focus returns to trigger on close.
- **Violation:** Tests pass but accessibility not verified — focus trap not working for keyboard users.
- **Compliant claim:** "All 4 interaction tests pass. Focus trap verified manually. Escape key closes modal. Regression tests pass."

**Example 2:** Agent implements form with backend integration.

- **Accuracy verification:** Real POST request sent. Loading state shown. Error state shown. Success state shown.
- **Violation:** Testing with mocked fetch, claiming full integration.
- **Compliant claim:** "Real POST verified. Loading state shown during request. Error state shown on 500. Success state on 200."

## Anti-Patterns

The following behaviors VIOLATE accuracy requirements:

1. **Modified oracle** — changing tests to pass instead of fixing implementation.
2. **Silent contract change** — altering prop interface without updating consumers.
3. **Mocked seam** — testing with mocked backend instead of real integration.
4. **Accessibility skip** — implementing interactive component without keyboard/ARIA verification.
5. **Storybook-only** — claiming done based on component story without interaction testing.
6. **Regression skip** — running only new tests, not full suite.
7. **Boundary inflation** — modifying files outside write boundary.
8. **Visual assumption** — claiming rendering correct without spec comparison.
