/**
 * Task notification operations: notify parent sessions, manage notification queues.
 * Extracted from BackgroundManager to keep modules under ~800 lines.
 */

import type { BackgroundTask } from "./types"
import type { ManagerContext } from "./manager-context"
import {
  log,
  normalizePromptTools,
  normalizeSDKResponse,
  resolveInheritedPromptTools,
  createInternalAgentTextPart,
} from "../../shared"
import { SessionCategoryRegistry } from "../../shared/session-category-registry"
import { subagentSessions } from "../claude-code-session-state"
import { getTaskToastManager } from "../task-toast-manager"
import { formatDuration } from "./duration-formatter"
import {
  buildBackgroundTaskNotificationText,
  type BackgroundTaskNotificationTask,
} from "./background-task-notification-template"
import {
  isAbortedSessionError,
  isRecord,
} from "./error-classifier"
import {
  findNearestMessageExcludingCompaction,
  resolvePromptContextFromSessionMessages,
} from "./compaction-aware-message-resolver"
import { MESSAGE_STORAGE } from "../hook-message-injector"
import { join } from "node:path"
import { removeTaskToastTracking } from "./remove-task-toast-tracking"
import { TASK_CLEANUP_DELAY_MS, TASK_TTL_MS } from "./constants"
import { scheduleTaskRemoval, getTasksByParentSession, findBySession } from "./task-lifecycle"

// ── Notification markers ──────────────────────────────────────────────

export function markForNotification(ctx: ManagerContext, task: BackgroundTask): void {
  const queue = ctx.notifications.get(task.parentSessionID) ?? []
  queue.push(task)
  ctx.notifications.set(task.parentSessionID, queue)
}

export function getPendingNotifications(ctx: ManagerContext, sessionID: string): BackgroundTask[] {
  return ctx.notifications.get(sessionID) ?? []
}

export function clearNotifications(ctx: ManagerContext, sessionID: string): void {
  ctx.notifications.delete(sessionID)
}

export function queuePendingNotification(ctx: ManagerContext, sessionID: string | undefined, notification: string): void {
  if (!sessionID) return
  const existing = ctx.pendingNotifications.get(sessionID) ?? []
  existing.push(notification)
  ctx.pendingNotifications.set(sessionID, existing)
}

export function injectPendingNotificationsIntoChatMessage(
  ctx: ManagerContext,
  output: { parts: Array<{ type: string; text?: string; [key: string]: unknown }> },
  sessionID: string
): void {
  const pending = ctx.pendingNotifications.get(sessionID)
  if (!pending || pending.length === 0) return

  ctx.pendingNotifications.delete(sessionID)
  const notificationContent = pending.join("\n\n")
  const firstTextPartIndex = output.parts.findIndex((part) => part.type === "text")

  if (firstTextPartIndex === -1) {
    output.parts.unshift(createInternalAgentTextPart(notificationContent))
    return
  }

  const originalText = output.parts[firstTextPartIndex].text ?? ""
  output.parts[firstTextPartIndex].text = `${notificationContent}\n\n---\n\n${originalText}`
}

// ── Pending parent tracking ───────────────────────────────────────────

export function cleanupPendingByParent(ctx: ManagerContext, task: BackgroundTask): void {
  if (!task.parentSessionID) return
  const pending = ctx.pendingByParent.get(task.parentSessionID)
  if (pending) {
    pending.delete(task.id)
    if (pending.size === 0) ctx.pendingByParent.delete(task.parentSessionID)
  }
}

export function clearNotificationsForTask(ctx: ManagerContext, taskId: string): void {
  for (const [sessionID, tasks] of ctx.notifications.entries()) {
    const filtered = tasks.filter((t) => t.id !== taskId)
    if (filtered.length === 0) ctx.notifications.delete(sessionID)
    else ctx.notifications.set(sessionID, filtered)
  }
}

// ── Notification queue ────────────────────────────────────────────────

export function enqueueNotificationForParent(
  ctx: ManagerContext,
  parentSessionID: string | undefined,
  operation: () => Promise<void>
): Promise<void> {
  if (!parentSessionID) return operation()

  const previous = ctx.notificationQueueByParent.get(parentSessionID) ?? Promise.resolve()
  const cleanupQueueEntry = (): void => {
    if (ctx.notificationQueueByParent.get(parentSessionID) === current) {
      ctx.notificationQueueByParent.delete(parentSessionID)
    }
  }

  const current = previous
    .catch((error) => {
      log("[background-agent] Continuing notification queue after previous failure:", { parentSessionID, error })
    })
    .then(operation)

  ctx.notificationQueueByParent.set(parentSessionID, current)
  void current.then(cleanupQueueEntry, cleanupQueueEntry)
  return current
}

// ── Notify parent session ─────────────────────────────────────────────

export async function notifyParentSession(ctx: ManagerContext, task: BackgroundTask): Promise<void> {
  const duration = formatDuration(task.startedAt ?? new Date(), task.completedAt)

  const toastManager = getTaskToastManager()
  if (toastManager) {
    toastManager.showCompletionToast({ id: task.id, description: task.description, duration })
  }

  if (!ctx.completedTaskSummaries.has(task.parentSessionID)) {
    ctx.completedTaskSummaries.set(task.parentSessionID, [])
  }
  ctx.completedTaskSummaries.get(task.parentSessionID)!.push({
    id: task.id,
    description: task.description,
    status: task.status,
    error: task.error,
  })

  const pendingSet = ctx.pendingByParent.get(task.parentSessionID)
  let allComplete = false
  let remainingCount = 0
  if (pendingSet) {
    pendingSet.delete(task.id)
    remainingCount = pendingSet.size
    allComplete = remainingCount === 0
    if (allComplete) ctx.pendingByParent.delete(task.parentSessionID)
  } else {
    remainingCount = Array.from(ctx.tasks.values())
      .filter(t => t.parentSessionID === task.parentSessionID && t.id !== task.id && (t.status === "running" || t.status === "pending"))
      .length
    allComplete = remainingCount === 0
  }

  const completedTasks = allComplete
    ? (ctx.completedTaskSummaries.get(task.parentSessionID) ?? [{ id: task.id, description: task.description, status: task.status, error: task.error }])
    : []

  if (allComplete) ctx.completedTaskSummaries.delete(task.parentSessionID)

  const statusText = task.status === "completed" ? "COMPLETED"
    : task.status === "interrupt" ? "INTERRUPTED"
    : task.status === "error" ? "ERROR"
    : "CANCELLED"

  const notification = buildBackgroundTaskNotificationText({
    task, duration, statusText, allComplete, remainingCount, completedTasks,
  })

  let agent: string | undefined = task.parentAgent
  let model: { providerID: string; modelID: string } | undefined
  let tools: Record<string, boolean> | undefined = task.parentTools
  let promptContext: ReturnType<typeof resolvePromptContextFromSessionMessages> = null

  if (ctx.enableParentSessionNotifications) {
    try {
      const messagesResp = await ctx.client.session.messages({ path: { id: task.parentSessionID } })
      const messages = normalizeSDKResponse(messagesResp, [] as Array<{
        info?: {
          agent?: string
          model?: { providerID: string; modelID: string }
          modelID?: string
          providerID?: string
          tools?: Record<string, boolean | "allow" | "deny" | "ask">
        }
      }>)
      promptContext = resolvePromptContextFromSessionMessages(messages, task.parentSessionID)
      const normalizedTools = isRecord(promptContext?.tools) ? normalizePromptTools(promptContext.tools) : undefined

      if (promptContext?.agent || promptContext?.model || normalizedTools) {
        agent = promptContext?.agent ?? task.parentAgent
        model = promptContext?.model?.providerID && promptContext.model.modelID
          ? { providerID: promptContext.model.providerID, modelID: promptContext.model.modelID }
          : undefined
        tools = normalizedTools ?? tools
      }
    } catch (error) {
      if (isAbortedSessionError(error)) {
        log("[background-agent] Parent session aborted; using messageDir fallback:", { taskId: task.id })
      }
      const messageDir = join(MESSAGE_STORAGE, task.parentSessionID)
      const currentMessage = messageDir
        ? findNearestMessageExcludingCompaction(messageDir, task.parentSessionID)
        : null
      agent = currentMessage?.agent ?? task.parentAgent
      model = currentMessage?.model?.providerID && currentMessage?.model?.modelID
        ? { providerID: currentMessage.model.providerID, modelID: currentMessage.model.modelID }
        : undefined
      tools = normalizePromptTools(currentMessage?.tools) ?? tools
    }

    const resolvedTools = resolveInheritedPromptTools(task.parentSessionID, tools)

    const isTaskFailure = task.status === "error" || task.status === "cancelled" || task.status === "interrupt"
    const shouldReply = allComplete || isTaskFailure
    const variant = promptContext?.model?.variant

    try {
      await ctx.client.session.promptAsync({
        path: { id: task.parentSessionID },
        body: {
          noReply: !shouldReply,
          ...(agent !== undefined ? { agent } : {}),
          ...(model !== undefined ? { model } : {}),
          ...(variant !== undefined ? { variant } : {}),
          ...(resolvedTools ? { tools: resolvedTools } : {}),
          parts: [createInternalAgentTextPart(notification)],
        },
      })
    } catch (error) {
      if (isAbortedSessionError(error)) {
        queuePendingNotification(ctx, task.parentSessionID, notification)
      } else {
        log("[background-agent] Failed to send notification:", error)
      }
    }
  }

  if (task.status !== "running" && task.status !== "pending") {
    scheduleTaskRemoval(ctx, task.id)
  }
}
