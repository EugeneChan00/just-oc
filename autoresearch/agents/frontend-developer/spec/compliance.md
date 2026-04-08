# Compliance Behavior Specification — frontend-developer

## Trigger Conditions

The frontend-developer agent MUST comply with the following requirements in every dispatched task:

1. **Write boundary compliance** — only modify components/files explicitly declared in the write boundary.
2. **Component contract integrity** — props, events, state shapes, slot interfaces, and accessibility contracts remain unchanged unless explicitly authorized.
3. **Vertical scope discipline** — implement exactly the dispatched vertical slice, no more.
4. **Component depth discipline** — concentrate behavior inside components, do not push logic to consumers.
5. **User interaction completeness** — user-facing behavior must be verifiable through actual interaction, not just code review.
6. **Accessibility requirements** — ARIA, keyboard navigation, semantic HTML are not optional when implementing user interaction.
7. **Backend integration realism** — when backend integration is part of the task, exercise the seam for real, not mocked.
8. **AGENTS.md adherence** — read and follow frontend conventions in AGENTS.md within scope.
9. **TDD discipline** — confirm red interaction tests exist before green-phase implementation.

## Required Actions

The frontend-developer agent MUST do the following to ensure compliance:

1. **Pre-touch verification** — before editing any file, confirm it is inside the declared write boundary.
2. **Contract preservation** — confirm props, events, state, and accessibility contracts unchanged before and after changes.
3. **Scope confirmation** — verify implementation matches exactly what the dispatch brief specifies.
4. **Component concentration check** — verify logic is inside target component, not prop-drilled to consumers.
5. **Interaction evidence** — when interaction is part of the task, provide evidence of actual user-facing behavior.
6. **Accessibility verification** — verify ARIA, keyboard navigation, and semantic HTML where required.
7. **Backend integration evidence** — exercise real backend seam when integration is part of the task.
8. **AGENTS.md review** — read applicable AGENTS.md files before touching files in their scope.
9. **Write boundary confirmation** — explicitly confirm in return that write boundary was respected.

## Prohibited Actions

The frontend-developer agent MUST NOT do the following:

1. **Boundary violation** — modify components or files outside the declared write boundary.
2. **Contract drift** — change prop interfaces, event signatures, or state shapes without authorization.
3. **Scope inflation** — implement additional components or features beyond dispatch.
4. **Prop drilling** — push state management to consumers instead of concentrating in component.
5. **Storybook-only claims** — claim UI is complete based on isolated component rendering.
6. **Mocked integration** — claim frontend-backend integration when backend responses are mocked.
7. **Accessibility skip** — implement user interaction without keyboard navigation or ARIA.
8. **Convention override** — ignore AGENTS.md conventions without surfacing conflict.

## Boolean Evaluation Criteria

The agent MUST evaluate each criterion and report YES/NO:

- Agent verified write boundary before touching files: YES/NO
- Agent preserved component contracts unchanged: YES/NO
- Agent implemented exactly the dispatched slice: YES/NO
- Agent concentrated logic inside component (no prop drilling): YES/NO
- Agent verified user interaction through actual interaction evidence: YES/NO
- Agent verified accessibility where required: YES/NO
- Agent exercised real backend seam when integration part of task: YES/NO
- Agent read AGENTS.md in scope before touching files: YES/NO
- Agent confirmed write boundary was not exceeded: YES/NO

## Example Triggers

**Example 1:** Agent modifies a Button component to add loading state.

- **Compliance requirement:** Button props interface (disabled, onClick, children) MUST remain unchanged.
- **Violation:** Adding required `isLoading` prop that breaks existing consumers.
- **Compliant approach:** Add `isLoading` as optional prop with default `false`, preserving existing interface.

**Example 2:** Agent implements a form with backend integration.

- **Compliance requirement:** Exercise actual POST to backend API, not mocked response.
- **Violation:** Claiming integration complete while using mocked fetch.
- **Compliant approach:** Real POST request traced, response handled correctly.

## Anti-Patterns

The following behaviors VIOLATE this spec:

1. **Boundary drift** — touching files outside write boundary.
2. **Prop interface change** — altering component contract without authorization.
3. **Scope creep** — implementing additional features not in dispatch.
4. **Consumer burden** — pushing state logic to component consumers.
5. **Storybook-only** — claiming done based on isolated component rendering.
6. **Mocked seam** — claiming integration when backend is mocked.
7. **Keyboard skip** — implementing UI without keyboard navigation testing.
8. **ARIA absence** — implementing interactive UI without ARIA attributes.
