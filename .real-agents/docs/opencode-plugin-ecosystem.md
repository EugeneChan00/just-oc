# OpenCode Plugin Ecosystem

## Overview

OpenCode plugins extend the AI agent harness with custom tools, hooks, lifecycle handlers, and chat transformers. Plugins are TypeScript modules that export a default `Plugin` async function. The plugin system is provided by `@opencode-ai/plugin`.

**Reference implementation**: `plugin/oh-my-openagent/` (git submodule) — the most comprehensive OpenCode plugin, providing background agents, parallel task orchestration, LSP tools, skill system, and 50+ hooks.

---

## Core Types

### Plugin Entry Point

```ts
import type { Plugin } from "@opencode-ai/plugin"

const MyPlugin: Plugin = async (ctx) => {
  // ctx.directory  — project root path
  // ctx.client     — OpenCode SDK client for session/message APIs
  return {
    name: "my-plugin",
    tool: { /* tool definitions */ },
    // hooks and handlers (optional)
  }
}
export default MyPlugin
```

**`Plugin`** is an async function: `(ctx: PluginContext) => Promise<PluginInstance>`

### PluginContext (`ctx`)

| Property      | Type              | Description                            |
|---------------|-------------------|----------------------------------------|
| `directory`   | `string`          | Absolute path to the project root      |
| `client`      | `PluginInput["client"]` | SDK client with session/message APIs |

The `client` provides:
- `client.session.messages({ path: { id } })` — fetch session messages
- `client.session.abort({ path: { id } })` — abort a session
- Other session management APIs

### PluginInstance (return value)

The object returned from the Plugin function can include:

| Key | Type | Description |
|-----|------|-------------|
| `name` | `string` | Plugin display name |
| `tool` | `Record<string, ToolDefinition>` | Custom tool definitions |
| `config` | handler | Configuration provider |
| `event` | handler | Event listener (session lifecycle) |
| `chat.params` | handler | Modify chat API parameters |
| `chat.headers` | handler | Inject custom HTTP headers |
| `chat.message` | handler | Transform/intercept chat messages |
| `command.execute.before` | handler | Pre-process slash commands |
| `tool.execute.before` | handler | Pre-process tool calls |
| `tool.execute.after` | handler | Post-process tool results |
| `experimental.chat.messages.transform` | handler | Transform message arrays |
| `experimental.chat.system.transform` | handler | Transform system prompts |
| `experimental.session.compacting` | handler | Context compaction hook |

---

## Tool Definition

Tools are defined using the `tool()` factory from `@opencode-ai/plugin`:

```ts
import { tool, type ToolDefinition } from "@opencode-ai/plugin"

const myTool: ToolDefinition = tool({
  description: "What this tool does",
  args: {
    query: tool.schema.string().describe("Search query"),
    limit: tool.schema.number().optional().describe("Max results"),
    verbose: tool.schema.boolean().optional().describe("Include details"),
  },
  async execute(args, toolContext) {
    // toolContext.sessionID — current session
    // toolContext.messageID — current message
    // toolContext.agent     — agent name
    // toolContext.abort     — AbortSignal
    // toolContext.metadata  — set tool metadata for UI
    return "Tool output string"
  },
})
```

### tool.schema

Schema builder (Zod-compatible) for defining tool arguments:

| Method | Description |
|--------|-------------|
| `tool.schema.string()` | String parameter |
| `tool.schema.number()` | Number parameter |
| `tool.schema.boolean()` | Boolean parameter |
| `.optional()` | Mark parameter as optional |
| `.describe(text)` | Add description for the LLM |

### toolContext

| Property | Type | Description |
|----------|------|-------------|
| `sessionID` | `string` | Current session ID |
| `messageID` | `string` | Current message ID |
| `agent` | `string` | Active agent name |
| `abort` | `AbortSignal` | Cancellation signal |
| `metadata` | `(input) => void` | Set title/metadata for UI display |
| `callID` | `string` | Unique tool call identifier |

---

## Hook System

Hooks intercept and modify behavior at various points in the agent lifecycle. They are registered via the plugin interface keys.

### Plugin Interface Hooks

| Hook | Signature | When |
|------|-----------|------|
| `tool.execute.before` | `(input, output) => Promise<void>` | Before any tool runs |
| `tool.execute.after` | `(input, output) => Promise<void>` | After any tool completes |
| `chat.message` | `(input, output) => Promise<void>` | On each chat message |
| `chat.params` | `(input, output) => Promise<void>` | Before API call (modify params) |
| `chat.headers` | `(input, output) => Promise<void>` | Before API call (inject headers) |
| `command.execute.before` | `(input, output) => Promise<void>` | Before slash command runs |
| `event` | `(event) => Promise<void>` | Session lifecycle events |
| `experimental.session.compacting` | `(input, output) => Promise<void>` | During context compaction |

### Named Hooks (oh-my-openagent)

oh-my-openagent implements 50+ named hooks organized into categories:

**Core Hooks**: `context-window-monitor`, `tool-output-truncator`, `think-mode`, `model-fallback`, `rules-injector`, `preemptive-compaction`, `edit-error-recovery`, `json-error-recovery`

**Session Hooks**: `session-recovery`, `session-notification`, `background-notification`, `compaction-context-injector`, `compaction-todo-preserver`

**Agent Hooks**: `todo-continuation-enforcer`, `agent-usage-reminder`, `category-skill-reminder`, `delegate-task-retry`, `stop-continuation-guard`

**Guard Hooks**: `comment-checker`, `write-existing-file-guard`, `bash-file-read-guard`, `webfetch-redirect-guard`, `thinking-block-validator`, `tool-pair-validator`

**UI Hooks**: `auto-update-checker`, `startup-toast`, `keyword-detector`, `legacy-plugin-toast`

Hooks can be disabled via config:
```jsonc
{ "disabled_hooks": ["auto-update-checker", "startup-toast"] }
```

---

## Plugin Lifecycle

### Initialization

1. OpenCode loads the plugin module (ESM import)
2. Calls the default export `Plugin` function with `ctx`
3. Plugin returns the interface object with tools + hooks
4. OpenCode registers tools and wires up hook handlers

### Dispose Pattern

Plugins can manage cleanup via a dispose pattern:

```ts
const dispose = createPluginDispose({
  backgroundManager: { shutdown: () => { /* ... */ } },
  skillMcpManager:   { disconnectAll: async () => { /* ... */ } },
  lspManager:        { stopAll: async () => { /* ... */ } },
  disposeHooks:      () => { /* unhook all listeners */ },
})
```

On re-initialization (e.g., config reload), the previous plugin instance is disposed before creating a new one.

---

## Configuration

### Plugin Config File

oh-my-openagent loads config from `oh-my-openagent.jsonc` (or `.json`) in:
1. Project directory (`.opencode/oh-my-openagent.jsonc`)
2. Global OpenCode config directory

Config uses Zod schema validation with partial parsing — invalid sections are skipped while valid sections are preserved.

### Key Config Sections

| Section | Description |
|---------|-------------|
| `agents` | Agent name overrides, model configs |
| `categories` | Custom agent categories |
| `disabled_agents` | Agents to exclude |
| `disabled_tools` | Tools to exclude |
| `disabled_hooks` | Hooks to disable |
| `disabled_skills` | Skills to exclude |
| `disabled_commands` | Slash commands to exclude |
| `background_task` | Background task concurrency settings |
| `experimental` | Feature flags (`max_tools`, `safe_hook_creation`) |
| `claude_code` | Claude Code integration settings |
| `git_master` | Git operation configuration |
| `openclaw` | OpenClaw integration |

---

## Background Task System

The background task system (isolated in `plugins/src/background_tasks/`) provides three tools:

### `background_task`
Launch an agent task in the background. Returns a task ID immediately.

```
Args: description (string), prompt (string), agent (string)
Returns: Task ID, session ID, status
```

### `background_output`
Get output from a background task. Supports blocking, full session replay, and filtered output.

```
Args: task_id, block?, timeout?, full_session?, include_thinking?, message_limit?, since_message_id?
Returns: Task result or status
```

### `background_cancel`
Cancel running/pending background tasks.

```
Args: taskId? (single), all? (boolean)
Returns: Cancellation confirmation with continuable sessions
```

### BackgroundManager Interface

```ts
interface BackgroundManager {
  launch(input: LaunchInput): Promise<BackgroundTask>
  getTask(taskId: string): BackgroundTask | undefined
  getAllDescendantTasks(sessionID: string): BackgroundTask[]
  cancelTask(taskId: string, options: CancelOptions): Promise<boolean>
}
```

---

## File Layout Reference

### Plugin entry point & config
```
.opencode/opencode.json                 # Plugin registration: file://./plugins/src/background_tasks/index.ts
plugins/src/background_tasks/index.ts   # Entry point — exports default Plugin
```

### Isolated source
```
plugins/src/background_tasks/
├── index.ts                            # Plugin entry point (SimpleBackgroundManager + tool wiring)
├── tools/                              # Tool definitions (create-background-*.ts)
├── features/
│   ├── background-agent/
│   │   ├── manager-context.ts          # Shared ManagerContext type for submodules
│   │   ├── manager-interface.ts        # BackgroundManager interface contract
│   │   ├── task-lifecycle.ts           # Launch, start, track, resume, cancel, complete (~780 lines)
│   │   ├── event-handler.ts           # Event handling, polling, session validation (~514 lines)
│   │   ├── task-notification.ts       # Parent notifications, queue management (~249 lines)
│   │   ├── types.ts                    # BackgroundTask, LaunchInput types
│   │   └── index.ts                    # Re-exports
│   ├── tool-metadata-store/            # Tool metadata persistence
│   ├── hook-message-injector/          # Message context resolution (stub)
│   └── claude-code-session-state/      # Session agent tracking (stub)
└── shared/                             # Logger, cursor, display names, storage paths
```

### Upstream reference (git submodule)
```
plugin/oh-my-openagent/                 # Full oh-my-openagent source (git submodule)
└── src/
    ├── index.ts                        # Plugin entry point pattern
    ├── create-tools.ts                 # Tool registration
    ├── create-hooks.ts                 # Hook composition
    ├── plugin-interface.ts             # Interface assembly
    ├── plugin-dispose.ts               # Cleanup lifecycle
    ├── plugin-config.ts                # Config loading (Zod)
    ├── tools/background-task/          # Original background task tools
    ├── features/background-agent/
    │   └── manager.ts                  # Full BackgroundManager (2217 lines) — reference impl
    └── shared/                         # Shared utilities
```

> **Note**: The full `BackgroundManager` class lives in the submodule at
> `plugin/oh-my-openagent/src/features/background-agent/manager.ts`.
> Our isolated source splits its logic into `task-lifecycle.ts`, `event-handler.ts`,
> and `task-notification.ts` submodules.

---

## Research Metadata

- **Topic**: OpenCode Plugin Ecosystem Architecture
- **Date**: 2026-04-09
- **Source**: oh-my-openagent v3.16.0 (`plugin/oh-my-openagent/`)
- **Key Package**: `@opencode-ai/plugin` (core plugin types and tool builder)
