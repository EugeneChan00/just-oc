import { tool, type PluginInput, type ToolDefinition } from "@opencode-ai/plugin"
import type { BackgroundManager } from "../features/background-agent"
import type { BackgroundTaskArgs } from "./types"
import { BACKGROUND_TASK_DESCRIPTION } from "./constants"
import { resolveMessageContext } from "../features/hook-message-injector"
import { getSessionAgent } from "../features/claude-code-session-state"
import { storeToolMetadata } from "../features/tool-metadata-store"
import { log } from "../shared/logger"
import { delay } from "./delay"
import { getMessageDir } from "./message-dir"

type ToolContextWithMetadata = {
  sessionID: string
  messageID: string
  agent: string
  abort: AbortSignal
  metadata?: (input: { title?: string; metadata?: Record<string, unknown> }) => void
  callID?: string
}

export function createBackgroundTask(
  manager: BackgroundManager,
  client: PluginInput["client"],
  agentNames?: string[]
): ToolDefinition {
  const agentSchema = agentNames && agentNames.length > 0
    ? tool.schema.enum(agentNames as [string, ...string[]]).describe("Agent type to use for this task")
    : tool.schema.string().describe("Agent type to use (any registered agent)")

  return tool({
    description: BACKGROUND_TASK_DESCRIPTION,
    args: {
      description: tool.schema.string().describe("Short task description (shown in status)"),
      prompt: tool.schema.string().describe("Full detailed prompt for the agent"),
      agent: agentSchema,
      background: tool.schema.boolean().describe("Run in background (true) or block until complete (false). Background mode returns immediately and notifies on completion."),
      session_id: tool.schema.string().optional().describe("Only set this to resume a previous task. Pass a prior session_id/task_id to continue the same subagent session instead of creating a fresh one."),
    },
    async execute(args: BackgroundTaskArgs, toolContext) {
      const ctx = toolContext as ToolContextWithMetadata

      if (!args.agent || args.agent.trim() === "") {
        return `[ERROR] Agent parameter is required. Please specify which agent to use (e.g., "explore", "librarian", "build", etc.)`
      }

      try {
        const messageDir = getMessageDir(ctx.sessionID)
        const { prevMessage, firstMessageAgent } = await resolveMessageContext(
          ctx.sessionID,
          client,
          messageDir
        )

        const sessionAgent = getSessionAgent(ctx.sessionID)
        const parentAgent = ctx.agent ?? sessionAgent ?? firstMessageAgent ?? prevMessage?.agent

        log("[background_task] parentAgent resolution", {
          sessionID: ctx.sessionID,
          ctxAgent: ctx.agent,
          sessionAgent,
          firstMessageAgent,
          prevMessageAgent: prevMessage?.agent,
          resolvedParentAgent: parentAgent,
        })

        const parentModel =
          prevMessage?.model?.providerID && prevMessage?.model?.modelID
            ? {
                providerID: prevMessage.model.providerID,
                modelID: prevMessage.model.modelID,
                ...(prevMessage.model.variant ? { variant: prevMessage.model.variant } : {}),
              }
            : undefined

        // Resume existing session if session_id provided
        if (args.session_id) {
          const resumedTask = await manager.resume({
            sessionId: args.session_id,
            prompt: args.prompt,
            parentSessionID: ctx.sessionID,
            parentMessageID: ctx.messageID,
            parentModel,
            parentAgent,
          })

          const bgMeta = {
            title: args.description,
            metadata: {
              ...(resumedTask.sessionID ? { sessionId: resumedTask.sessionID } : {}),
            },
          }
          ctx.metadata?.(bgMeta)

          if (ctx.callID) {
            storeToolMetadata(ctx.sessionID, ctx.callID, bgMeta)
          }

          if (args.background) {
            return `Background task resumed successfully.

Task ID: ${resumedTask.id}
Session ID: ${resumedTask.sessionID ?? "(unknown)"}
Description: ${resumedTask.description}
Agent: ${resumedTask.agent}
Status: ${resumedTask.status}

System notifies on completion. Use \`background_output\` with task_id="${resumedTask.id}" to check.
Use \`background_cancel\` with taskId="${resumedTask.id}" to terminate.

Do NOT call background_output now. Wait for <system-reminder> notification first.`
          }

          // Synchronous mode: block until resumed task completes
          const abortHandler = () => {
            manager.cancelTask(resumedTask.id, {
              source: "user-abort",
              abortSession: true,
              skipNotification: true,
            })
          }
          ctx.abort?.addEventListener("abort", abortHandler)

          const POLL_INTERVAL_MS = 1000
          const POLL_TIMEOUT_MS = 10 * 60 * 1000
          const pollStart = Date.now()
          try {
            while (Date.now() - pollStart < POLL_TIMEOUT_MS) {
              if (ctx.abort?.aborted) break
              const current = manager.getTask(resumedTask.id)
              if (!current) break
              if (current.status === "completed" || current.status === "error" || current.status === "cancelled" || current.status === "interrupt") {
                break
              }
              await delay(POLL_INTERVAL_MS)
            }
          } finally {
            ctx.abort?.removeEventListener("abort", abortHandler)
          }

          const finalTask = manager.getTask(resumedTask.id)
          const finalStatus = finalTask?.status ?? "unknown"
          const finalSessionId = finalTask?.sessionID ?? resumedTask.sessionID

          if (ctx.abort?.aborted && finalTask?.status === "running") {
            await manager.cancelTask(resumedTask.id, {
              source: "user-abort",
              abortSession: true,
              skipNotification: true,
            })
          }

          if (finalSessionId) {
            ctx.metadata?.({
              title: args.description,
              metadata: { sessionId: finalSessionId },
            })
          }

          let resultText = ""
          if (finalSessionId && (finalStatus === "completed" || finalStatus === "error")) {
            try {
              const messagesResp = await client.session.messages({ path: { id: finalSessionId } })
              const messages: Array<Record<string, unknown>> = ((messagesResp as any).data ?? (messagesResp as any).response ?? []) as any
              for (let i = messages.length - 1; i >= 0; i--) {
                const m = messages[i] as any
                const role = m.role ?? m.info?.role
                if (role !== "assistant") continue
                const parts = m.parts ?? []
                const textPart = parts.findLast?.((p: any) => p.type === "text" && p.text?.trim())
                if (textPart) {
                  resultText = textPart.text
                  break
                }
              }
            } catch {}
          }

          return [
            `task_id: ${finalSessionId ?? resumedTask.id} (for resuming to continue this task if needed)`,
            "",
            "<task_result>",
            resultText || `Task ${finalStatus}${finalTask?.error ? `: ${finalTask.error}` : ""}`,
            "</task_result>",
          ].join("\n")
        }

        const task = await manager.launch({
          description: args.description,
          prompt: args.prompt,
          agent: args.agent.trim(),
          parentSessionID: ctx.sessionID,
          parentMessageID: ctx.messageID,
          parentModel,
          parentAgent,
          background: !!args.background,
        })

        const WAIT_FOR_SESSION_INTERVAL_MS = 50
        const WAIT_FOR_SESSION_TIMEOUT_MS = 30000
        const waitStart = Date.now()
        let sessionId = task.sessionID
        while (!sessionId && Date.now() - waitStart < WAIT_FOR_SESSION_TIMEOUT_MS) {
          const updated = manager.getTask(task.id)
          if (updated?.status === "error" || updated?.status === "cancelled" || updated?.status === "interrupt") {
            return `Task ${`entered error state`}\.\n\nTask ID: ${task.id}`
          }
          sessionId = updated?.sessionID
          if (sessionId) {
            break
          }
          if (ctx.abort?.aborted) {
            break
          }
          await delay(WAIT_FOR_SESSION_INTERVAL_MS)
        }

        const bgMeta = {
          title: args.description,
          metadata: {
            ...(sessionId ? { sessionId } : {}),
          },
        }
        ctx.metadata?.(bgMeta)

        if (ctx.callID) {
          storeToolMetadata(ctx.sessionID, ctx.callID, bgMeta)
        }

        // Background mode: return immediately, notify on completion
        if (args.background) {
          return `Background task launched successfully.

Task ID: ${task.id}
Session ID: ${sessionId ?? "(not yet assigned)"}
Description: ${task.description}
Agent: ${task.agent}
Status: ${task.status}

System notifies on completion. Use \`background_output\` with task_id="${task.id}" to check.
Use \`background_cancel\` with taskId="${task.id}" to terminate.

Do NOT call background_output now. Wait for <system-reminder> notification first.`
        }

        // Synchronous mode (default): block with spinner + abort support

        // Abort handler — when user presses ESC, cancel the child session
        const abortHandler = () => {
          manager.cancelTask(task.id, {
            source: "user-abort",
            abortSession: true,
            skipNotification: true,
          })
        }
        ctx.abort?.addEventListener("abort", abortHandler)

        // Block until the sub-agent completes — keeps tool part in "running"
        // state so TUI shows spinner, live tool tracking, and click-to-navigate
        const POLL_INTERVAL_MS = 1000
        const POLL_TIMEOUT_MS = 10 * 60 * 1000
        const pollStart = Date.now()
        try {
          while (Date.now() - pollStart < POLL_TIMEOUT_MS) {
            if (ctx.abort?.aborted) break
            const current = manager.getTask(task.id)
            if (!current) break
            if (current.status === "completed" || current.status === "error" || current.status === "cancelled" || current.status === "interrupt") {
              break
            }
            await delay(POLL_INTERVAL_MS)
          }
        } finally {
          ctx.abort?.removeEventListener("abort", abortHandler)
        }

        const finalTask = manager.getTask(task.id)
        const finalStatus = finalTask?.status ?? "unknown"
        const finalSessionId = finalTask?.sessionID ?? sessionId

        // If aborted but task still running, ensure cleanup
        if (ctx.abort?.aborted && finalTask?.status === "running") {
          await manager.cancelTask(task.id, {
            source: "user-abort",
            abortSession: true,
            skipNotification: true,
          })
        }

        // Update metadata with final session ID
        if (finalSessionId) {
          ctx.metadata?.({
            title: args.description,
            metadata: { sessionId: finalSessionId },
          })
        }

        // Retrieve the sub-agent's last text output if completed
        let resultText = ""
        if (finalSessionId && (finalStatus === "completed" || finalStatus === "error")) {
          try {
            const messagesResp = await client.session.messages({ path: { id: finalSessionId } })
            const messages: Array<Record<string, unknown>> = ((messagesResp as any).data ?? (messagesResp as any).response ?? []) as any
            for (let i = messages.length - 1; i >= 0; i--) {
              const m = messages[i] as any
              const role = m.role ?? m.info?.role
              if (role !== "assistant") continue
              const parts = m.parts ?? []
              const textPart = parts.findLast?.((p: any) => p.type === "text" && p.text?.trim())
              if (textPart) {
                resultText = textPart.text
                break
              }
            }
          } catch {}
        }

        return [
          `task_id: ${finalSessionId ?? task.id} (for resuming to continue this task if needed)`,
          "",
          "<task_result>",
          resultText || `Task ${finalStatus}${finalTask?.error ? `: ${finalTask.error}` : ""}`,
          "</task_result>",
        ].join("\n")
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error)
        return `[ERROR] Failed to launch background task: ${message}`
      }
    },
  })
}
