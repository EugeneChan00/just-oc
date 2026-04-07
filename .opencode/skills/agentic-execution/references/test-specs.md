# Common Test Spec Scenarios (TDD + No-Mock)

This document defines reusable test-spec scenarios for feature work.

Use this with:
- `test-driven-development.md` for red/green/refactor flow
- `agent-browser` for frontend and frontend-backend integration verification

## Global Spec Criteria

1. Every behavior change starts with one failing test.
2. Tests verify behavior through real code paths.
3. Mock/patch/stub-driven assertions are not allowed.
4. Existing code paths are preferred over adding new production code.
5. Each test run stores concise red and green evidence.

## Tool Selection Matrix

| Test Type | Primary Tooling | Secondary Tooling | Notes |
|---|---|---|---|
| Frontend unit/component | `pnpm -C packages/webui test` (Vitest + Testing Library) | Serena symbol tools | Fast behavior checks at component/lib layer. |
| Frontend workflow (browser) | `agent-browser` | Screenshots/PDF artifacts | Preferred for user-flow verification against running UI. |
| Backend unit/integration (Python) | `pytest` | Serena symbol/reference mapping | Use targeted tests first, then broaden scope. |
| Backend unit/integration (Spawner TS) | `pnpm -C packages/spawner test` | Serena symbol/reference mapping | Use when change impacts spawner adapters/runtime behavior. |
| Frontend-backend integration | `agent-browser` + running stack | API assertions via `curl`/existing tests | Validate full flow across UI, MCP API, and spawner. |

## Scenario Catalog

### FE-001: Form Validation Behavior

Scope: frontend-only behavior validation for form inputs and error states.
Preconditions: web UI test environment available.
Red target: invalid input path fails with expected visible error.
Green target: valid path submits and clears previous error state.
Primary tools: `pnpm -C packages/webui test -- <target-test-file>`.
Evidence: failing assertion output, passing run output.

### FE-002: Browser Workflow Smoke

Scope: UI route and action flow from entry page to primary success state.
Preconditions: web UI running (`pnpm --filter @mlre/webui dev`).
Red target: intended success marker absent or wrong route/state.
Green target: success marker and route/state are correct.
Primary tools: `agent-browser`.
Command seed:
```bash
agent-browser open http://localhost:5173
agent-browser snapshot -i
agent-browser click @e1
agent-browser wait --load networkidle
agent-browser snapshot -i
agent-browser screenshot --full
```
Evidence: terminal output, screenshot, optional page text capture.

### BE-001: MCP API Contract

Scope: request/response behavior for MCP API endpoints.
Preconditions: Python test environment ready.
Red target: contract mismatch reproduced by failing test.
Green target: endpoint behavior and status codes match spec.
Primary tools: `pytest tests/unit/mcp_server/test_api.py -k <case>`.
Evidence: failing test name and reason, passing rerun result.

### BE-002: Persistence and Repository Behavior

Scope: database/repository behavior, migrations, and invariants.
Preconditions: database test environment available.
Red target: invariant or persistence rule fails in test.
Green target: data lifecycle and invariant checks pass.
Primary tools: `pytest tests/unit/database/test_repositories.py -k <case>`.
Evidence: failing and passing outputs, affected symbol list.

### INT-001: Frontend-Backend Runtime Creation

Scope: end-to-end runtime creation from UI through API to spawner.
Preconditions:
- MCP server running (`uvicorn src.mcp_server.server:create_server --factory --host 0.0.0.0 --port 8000 --reload`)
- spawner running (`pnpm --filter @agent/spawner dev`)
- web UI running (`pnpm --filter @mlre/webui dev`)
Red target: runtime/session creation path fails for expected reason.
Green target: runtime appears in UI and API returns expected object.
Primary tools: `agent-browser` + API check.
Command seed:
```bash
agent-browser open http://localhost:5173
agent-browser snapshot -i
agent-browser click @e1
agent-browser wait --url "**/sessions*"
agent-browser snapshot -i
curl -s http://localhost:8000/api/sessions | head
```
Evidence: browser capture, API response snippet, pass/fail summary.

### INT-002: Frontend Error Handling With Service Fault

Scope: UI behavior when backend dependency is unavailable.
Preconditions: UI and MCP running; spawner intentionally stopped.
Red target: UI does not show expected failure state.
Green target: UI shows stable error state with actionable message.
Primary tools: `agent-browser`.
Command seed:
```bash
agent-browser open http://localhost:5173
agent-browser snapshot -i
agent-browser click @e1
agent-browser wait --load networkidle
agent-browser snapshot -i
agent-browser screenshot
```
Evidence: browser output and screenshot proving fallback behavior.

## Execution Notes

1. For frontend and frontend-backend integration, prefer `agent-browser` over synthetic test doubles.
2. Re-snapshot after each navigation or DOM mutation.
3. Store artifacts under `artifacts/test-specs/<scenario-id>/` when the task is non-trivial.
