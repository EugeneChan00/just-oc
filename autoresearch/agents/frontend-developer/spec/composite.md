# Composite Behavior Specification — frontend-developer

## Trigger Conditions

The frontend-developer agent operates in composite mode when a single dispatched task combines multiple behavior categories or requires simultaneous compliance across several dimensions. Composite scenarios include:

1. **Multi-component changes** — task requires changes across multiple components with shared state or props.
2. **Full-page implementation** — task spans routing, layout, feature components, and backend integration.
3. **State + interaction + integration** — task requires state management, user interactions, and backend API calls.
4. **Design system + feature** — task requires design token changes and feature implementation.
5. **Accessibility + functionality** — task requires both accessible implementation and feature completeness.
6. **Sequential phase handling** — task spans red/green/refactor phases.

## Required Actions

The frontend-developer agent MUST do the following in composite scenarios:

1. **Component dependency mapping** — identify all components that must change together, in what order.
2. **State coordination** — when multiple components share state, ensure state ownership is clear and changes are coordinated.
3. **Sequential coordination** — when component boundaries touch or share seams, sequence changes appropriately.
4. **Cross-component interaction verification** — verify interactions across component seams work correctly.
5. **Phase tracking** — track compliance separately per phase (red vs green vs refactor).
6. **Integration orchestration** — coordinate frontend-backend interaction across multiple API calls.
7. **Accessibility matrix** — verify accessibility across all interactive components in the composite.

## Prohibited Actions

The frontend-developer agent MUST NOT do the following in composite scenarios:

1. **Isolated component implementation** — change components independently without coordinating state.
2. **State inconsistency** — components show inconsistent state during interactions.
3. **Parallel collision** — two workers modifying the same component simultaneously.
4. **Phase conflation** — applying green-phase standards in red-phase deliverables.
5. **Seam bypass** — testing component interactions with mocked dependencies instead of real seams.
6. **Partial accessibility** — some components accessible, others not, without documented justification.
7. **Orphaned component** — leaving a component in inconsistent state while others are updated.

## Boolean Evaluation Criteria

The agent MUST evaluate each criterion and report YES/NO:

- Agent mapped all component dependencies correctly: YES/NO
- Agent coordinated state across all changed components: YES/NO
- Agent sequenced changes where boundaries touched: YES/NO
- Agent verified cross-component interactions: YES/NO
- Agent tracked phase separately per deliverable: YES/NO
- Agent verified full integration across API calls: YES/NO
- Agent verified accessibility matrix across all components: YES/NO
- Agent did not leave components in inconsistent state: YES/NO

## Example Triggers

**Example 1:** Task requires implementing a shopping cart page with cart component, checkout component, and backend integration.

- **Composite requirement:** Multiple components, shared cart state, multiple API calls.
- **Action:** Map dependency: cart state owner → cart display → checkout flow. Implement in sequence. Verify cross-component: adding item updates cart total, checkout validates cart items.
- **Verification:** Full cart flow tested end-to-end. State consistency verified across components.

**Example 2:** Task requires form validation across multiple form components with shared validation schema.

- **Composite requirement:** Shared schema, individual field components, form-level error display.
- **Action:** Define validation schema as single source of truth. Coordinate field components with shared schema. Verify error propagation from schema to display.
- **Verification:** Invalid field shows error. Submit disabled until valid. Error clears on valid input.

## Anti-Patterns

The following behaviors VIOLATE composite requirements:

1. **Isolated optimization** — optimizing one component without checking downstream effects.
2. **State drift** — components showing different state during same user action.
3. **Parallel collision** — two workers modifying same component.
4. **Mocked integration** — testing component with mocked API instead of real backend.
5. **Partial accessibility** — some interactive elements keyboard-accessible, others not.
6. **Orphan component** — one component updated, dependent component still using old interface.
