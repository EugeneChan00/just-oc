/**
 * Event handling, polling, and session validation.
 * Extracted from BackgroundManager to keep modules under ~800 lines.
 */

import type { BackgroundTask } from "./types"
import type { ManagerContext, Event, EventProperties, MessagePartInfo, Todo } from "./manager-context"
import {
  log,
  normalizeSDKResponse,
} from "../../shared"
import { SessionCategoryRegistry } from "../../shared/session-category-registry"
import { subagentSessions } from "../claude-code-session-state"
import { getTaskToastManager } from "../task-toast-manager"
import { removeTaskToastTracking } from "./remove-task-toast-tracking"
import {
  shouldRetryError,
  hasMoreFallbacks,
} from "../../shared/model-error-classifier"
import { POLLING_INTERVAL_MS } from "./constants"
import {
  isAbortedSessionError,
  extractErrorName,
  extractErrorMessage,
  getSessionErrorMessage,
} from "./error-classifier"
import { isAgentNotFoundError } from "./spawner"
import { tryFallbackRetry } from "./fallback-retry-handler"
import { handleSessionIdleBackgroundEvent } from "./session-idle-event-handler"
import { pruneStaleTasksAndNotifications, checkAndInterruptStaleTasks } from "./task-poller"
import { verifySessionExists as verifySessionStillExists, MIN_SESSION_GONE_POLLS } from "./session-existence"
import { isActiveSessionStatus, isTerminalSessionStatus } from "./session-status-classifier"
import {
  detectRepetitiveToolUse,
  recordToolCall,
  resolveCircuitBreakerSettings,
} from "./loop-detector"
import {
  findBySession,
  getTasksByParentSession,
  getAllDescendantTasks,
  unregisterRootDescendant,
  tryCompleteTask,
  cancelTask,
  scheduleTaskRemoval,
} from "./task-lifecycle"
import {
  markForNotification,
  enqueueNotificationForParent,
  notifyParentSession,
  cleanupPendingByParent,
  clearNotificationsForTask,
} from "./task-notification"

// ── Helpers ───────────────────────────────────────────────────────────

function resolveMessagePartInfo(properties: EventProperties | undefined): MessagePartInfo | undefined {
  if (!properties || typeof properties !== "object") return undefined
  const nestedPart = properties.part
  if (nestedPart && typeof nestedPart === "object") return nestedPart as MessagePartInfo
  return properties as MessagePartInfo
}

// ── Session observation ───────────────────────────────────────────────

export function markSessionOutputObserved(ctx: ManagerContext, sessionID: string): void {
  ctx.observedOutputSessions.add(sessionID)
}

export function clearSessionOutputObserved(ctx: ManagerContext, sessionID: string): void {
  ctx.observedOutputSessions.delete(sessionID)
}

export function clearSessionTodoObservation(ctx: ManagerContext, sessionID: string): void {
  ctx.observedIncompleteTodosBySession.delete(sessionID)
}

function hasOutputSignalFromPart(partInfo: MessagePartInfo | undefined): boolean {
  if (!partInfo?.sessionID) return false
  if (partInfo.tool) return true
  if (partInfo.type === "tool" || partInfo.type === "tool_result") return true
  if (partInfo.type === "text" || partInfo.type === "reasoning") return true
  const field = typeof (partInfo as { field?: unknown }).field === "string"
    ? (partInfo as { field?: string }).field
    : undefined
  return field === "text" || field === "reasoning"
}

// ── Session validation ────────────────────────────────────────────────

export async function checkSessionTodos(ctx: ManagerContext, sessionID: string): Promise<boolean> {
  const observed = ctx.observedIncompleteTodosBySession.get(sessionID)
  if (observed !== undefined) return observed

  try {
    const response = await ctx.client.session.todo({ path: { id: sessionID } })
    const todos = normalizeSDKResponse(response, [] as Todo[], { preferResponseOnMissingData: true })
    if (!todos || todos.length === 0) {
      ctx.observedIncompleteTodosBySession.set(sessionID, false)
      return false
    }
    const incomplete = todos.filter(t => t.status !== "completed" && t.status !== "cancelled")
    const hasIncompleteTodos = incomplete.length > 0
    ctx.observedIncompleteTodosBySession.set(sessionID, hasIncompleteTodos)
    return hasIncompleteTodos
  } catch (error) {
    log("[background-agent] Failed to check session todos:", { sessionID, error })
    return false
  }
}

export async function validateSessionHasOutput(ctx: ManagerContext, sessionID: string): Promise<boolean> {
  if (ctx.observedOutputSessions.has(sessionID)) return true

  try {
    const response = await ctx.client.session.messages({ path: { id: sessionID } })
    const messages = normalizeSDKResponse(response, [] as Array<{ info?: { role?: string }; parts?: Array<Record<string, unknown>> }>, { preferResponseOnMissingData: true })

    const hasAssistantOrToolMessage = messages.some(
      (m: { info?: { role?: string } }) => m.info?.role === "assistant" || m.info?.role === "tool"
    )
    if (!hasAssistantOrToolMessage) return false

    const hasContent = messages.some((m: any) => {
      if (m.info?.role !== "assistant" && m.info?.role !== "tool") return false
      const parts = m.parts ?? []
      return parts.some((p: any) =>
        (p.type === "text" && p.text && p.text.trim().length > 0) ||
        (p.type === "reasoning" && p.text && p.text.trim().length > 0) ||
        p.type === "tool" ||
        (p.type === "tool_result" && p.content &&
          (typeof p.content === "string" ? p.content.trim().length > 0 : p.content.length > 0))
      )
    })
    if (!hasContent) return false

    markSessionOutputObserved(ctx, sessionID)
    return true
  } catch (error) {
    log("[background-agent] Error validating session output:", error)
    return true
  }
}

// ── Fallback retry ────────────────────────────────────────────────────

export function tryManagerFallbackRetry(
  ctx: ManagerContext,
  task: BackgroundTask,
  errorInfo: { name?: string; message?: string },
  source: string,
): Promise<boolean> {
  const previousSessionID = task.sessionID
  const { processKey } = require("./task-lifecycle")
  const result = tryFallbackRetry({
    task,
    errorInfo,
    source,
    concurrencyManager: ctx.concurrencyManager,
    client: ctx.client,
    idleDeferralTimers: ctx.idleDeferralTimers,
    queuesByKey: ctx.queuesByKey,
    processKey: (key: string) => processKey(ctx, key),
  })
  return result.then((retried: boolean) => {
    if (retried && previousSessionID) {
      clearSessionOutputObserved(ctx, previousSessionID)
      clearSessionTodoObservation(ctx, previousSessionID)
      subagentSessions.delete(previousSessionID)
    }
    return retried
  })
}

// ── Session error handling ────────────────────────────────────────────

export async function handleSessionErrorEvent(ctx: ManagerContext, args: {
  task: BackgroundTask
  errorInfo: { name?: string; message?: string }
  errorName: string | undefined
  errorMessage: string | undefined
}): Promise<void> {
  const { task, errorInfo, errorMessage, errorName } = args

  if (isAgentNotFoundError({ message: errorInfo.message } as Error)) return

  if (await tryManagerFallbackRetry(ctx, task, errorInfo, "session.error")) return

  const errorMsg = errorMessage ?? "Session error"
  task.status = "error"
  task.error = errorMsg
  task.completedAt = new Date()
  if (task.rootSessionID) unregisterRootDescendant(ctx, task.rootSessionID)
  ctx.taskHistory.record(task.parentSessionID, { id: task.id, sessionID: task.sessionID, agent: task.agent, description: task.description, status: "error", category: task.category, startedAt: task.startedAt, completedAt: task.completedAt })

  if (task.concurrencyKey) {
    ctx.concurrencyManager.release(task.concurrencyKey)
    task.concurrencyKey = undefined
  }

  const completionTimer = ctx.completionTimers.get(task.id)
  if (completionTimer) { clearTimeout(completionTimer); ctx.completionTimers.delete(task.id) }
  const idleTimer = ctx.idleDeferralTimers.get(task.id)
  if (idleTimer) { clearTimeout(idleTimer); ctx.idleDeferralTimers.delete(task.id) }

  cleanupPendingByParent(ctx, task)
  clearNotificationsForTask(ctx, task.id)
  const toastManager = getTaskToastManager()
  if (toastManager) toastManager.removeTask(task.id)
  scheduleTaskRemoval(ctx, task.id)
  if (task.sessionID) SessionCategoryRegistry.remove(task.sessionID)

  markForNotification(ctx, task)
  enqueueNotificationForParent(ctx, task.parentSessionID, () => notifyParentSession(ctx, task)).catch(err => {
    log("[background-agent] Error in notifyParentSession for errored task:", { taskId: task.id, error: err })
  })
}

// ── Main event handler ────────────────────────────────────────────────

export function handleEvent(ctx: ManagerContext, event: Event): void {
  const props = event.properties

  if (event.type === "message.updated") {
    const info = props?.info
    if (!info || typeof info !== "object") return
    const sessionID = (info as Record<string, unknown>)["sessionID"]
    const role = (info as Record<string, unknown>)["role"]
    if (typeof sessionID !== "string") return
    if (role === "tool") markSessionOutputObserved(ctx, sessionID)
    if (role !== "assistant") return

    const task = findBySession(ctx, sessionID)
    if (!task || task.status !== "running") return

    const assistantError = (info as Record<string, unknown>)["error"]
    if (!assistantError) return

    void tryManagerFallbackRetry(ctx, task, {
      name: extractErrorName(assistantError),
      message: extractErrorMessage(assistantError),
    }, "message.updated").catch(() => {})
  }

  if (event.type === "message.part.updated" || event.type === "message.part.delta") {
    const partInfo = resolveMessagePartInfo(props)
    const sessionID = partInfo?.sessionID
    if (!sessionID) return

    const task = findBySession(ctx, sessionID)
    if (!task) return

    if (hasOutputSignalFromPart(partInfo)) markSessionOutputObserved(ctx, sessionID)

    const existingTimer = ctx.idleDeferralTimers.get(task.id)
    if (existingTimer) { clearTimeout(existingTimer); ctx.idleDeferralTimers.delete(task.id) }

    if (!task.progress) task.progress = { toolCalls: 0, lastUpdate: new Date() }
    task.progress.lastUpdate = new Date()

    if (partInfo?.type === "tool" || partInfo?.tool) {
      const countedToolPartIDs = task.progress.countedToolPartIDs ?? new Set<string>()
      const shouldCountToolCall = !partInfo.id || partInfo.state?.status !== "running" || !countedToolPartIDs.has(partInfo.id)
      if (!shouldCountToolCall) return

      if (partInfo.id && partInfo.state?.status === "running") {
        countedToolPartIDs.add(partInfo.id)
        task.progress.countedToolPartIDs = countedToolPartIDs
      }

      task.progress.toolCalls += 1
      task.progress.lastTool = partInfo.tool
      const circuitBreaker = ctx.cachedCircuitBreakerSettings ?? (ctx.cachedCircuitBreakerSettings = resolveCircuitBreakerSettings(ctx.config))
      if (partInfo.tool) {
        task.progress.toolCallWindow = recordToolCall(task.progress.toolCallWindow, partInfo.tool, circuitBreaker, partInfo.state?.input)

        if (circuitBreaker.enabled) {
          const loopDetection = detectRepetitiveToolUse(task.progress.toolCallWindow)
          if (loopDetection.triggered) {
            void cancelTask(ctx, task.id, {
              source: "circuit-breaker",
              reason: `Subagent called ${loopDetection.toolName} ${loopDetection.repeatedCount} consecutive times (threshold: ${circuitBreaker.consecutiveThreshold}). Automatically cancelled.`,
            })
            return
          }
        }
      }

      const maxToolCalls = circuitBreaker.maxToolCalls
      if (task.progress.toolCalls >= maxToolCalls) {
        void cancelTask(ctx, task.id, {
          source: "circuit-breaker",
          reason: `Subagent exceeded maximum tool call limit (${maxToolCalls}). Automatically cancelled.`,
        })
      }
    }
  }

  if (event.type === "todo.updated") {
    const sessionID = typeof props?.sessionID === "string" ? props.sessionID : undefined
    const todos = Array.isArray(props?.todos) ? props.todos : undefined
    if (!sessionID || !todos) return
    const hasIncompleteTodos = todos.some((todo) => {
      if (!todo || typeof todo !== "object") return false
      return (todo as { status?: unknown }).status !== "completed" && (todo as { status?: unknown }).status !== "cancelled"
    })
    ctx.observedIncompleteTodosBySession.set(sessionID, hasIncompleteTodos)
    return
  }

  if (event.type === "session.idle") {
    if (!props || typeof props !== "object") return
    handleSessionIdleBackgroundEvent({
      properties: props as Record<string, unknown>,
      findBySession: (id) => findBySession(ctx, id),
      idleDeferralTimers: ctx.idleDeferralTimers,
      validateSessionHasOutput: (id) => validateSessionHasOutput(ctx, id),
      checkSessionTodos: (id) => checkSessionTodos(ctx, id),
      tryCompleteTask: (task, source) => tryCompleteTask(ctx, task, source),
      emitIdleEvent: (sessionID) => handleEvent(ctx, { type: "session.idle", properties: { sessionID } }),
    })
  }

  if (event.type === "session.error") {
    const sessionID = typeof props?.sessionID === "string" ? props.sessionID : undefined
    if (!sessionID) return
    const task = findBySession(ctx, sessionID)
    if (!task || task.status !== "running") return
    const errorObj = props?.error as { name?: string; message?: string } | undefined
    void handleSessionErrorEvent(ctx, {
      errorInfo: { name: errorObj?.name, message: props ? getSessionErrorMessage(props) : undefined },
      errorMessage: props ? getSessionErrorMessage(props) : undefined,
      errorName: errorObj?.name,
      task,
    }).catch(() => {})
    return
  }

  if (event.type === "session.deleted") {
    const info = props?.info
    if (!info || typeof info.id !== "string") return
    const sessionID = info.id
    clearSessionOutputObserved(ctx, sessionID)
    clearSessionTodoObservation(ctx, sessionID)

    const tasksToCancel = new Map<string, BackgroundTask>()
    const directTask = findBySession(ctx, sessionID)
    if (directTask) tasksToCancel.set(directTask.id, directTask)
    for (const descendant of getAllDescendantTasks(ctx, sessionID)) {
      tasksToCancel.set(descendant.id, descendant)
    }

    ctx.pendingNotifications.delete(sessionID)
    if (tasksToCancel.size === 0) return

    const deletedSessionIDs = new Set<string>([sessionID])
    for (const task of tasksToCancel.values()) {
      if (task.sessionID) deletedSessionIDs.add(task.sessionID)
    }

    for (const task of tasksToCancel.values()) {
      if (task.status === "running" || task.status === "pending") {
        void cancelTask(ctx, task.id, { source: "session.deleted", reason: "Session deleted" })
          .then(() => { if (deletedSessionIDs.has(task.parentSessionID)) ctx.pendingNotifications.delete(task.parentSessionID) })
          .catch(() => { if (deletedSessionIDs.has(task.parentSessionID)) ctx.pendingNotifications.delete(task.parentSessionID) })
      }
    }

    ctx.rootDescendantCounts.delete(sessionID)
    SessionCategoryRegistry.remove(sessionID)
  }

  if (event.type === "session.status") {
    const sessionID = props?.sessionID as string | undefined
    const status = props?.status as { type?: string; message?: string } | undefined
    if (!sessionID || status?.type !== "retry") return
    const task = findBySession(ctx, sessionID)
    if (!task || task.status !== "running") return
    void tryManagerFallbackRetry(ctx, task, { name: "SessionRetry", message: status.message }, "session.status").catch(() => {})
  }
}

// ── Polling ───────────────────────────────────────────────────────────

export function startPolling(ctx: ManagerContext): void {
  if (ctx.pollingInterval) return
  ctx.pollingInterval = setInterval(() => { pollRunningTasks(ctx) }, POLLING_INTERVAL_MS)
  ctx.pollingInterval.unref()
}

export function stopPolling(ctx: ManagerContext): void {
  if (ctx.pollingInterval) {
    clearInterval(ctx.pollingInterval)
    ctx.pollingInterval = undefined
  }
}

export function hasRunningTasks(ctx: ManagerContext): boolean {
  for (const task of ctx.tasks.values()) {
    if (task.status === "running") return true
  }
  return false
}

export async function failCrashedTask(ctx: ManagerContext, task: BackgroundTask, errorMessage: string): Promise<void> {
  task.status = "error"
  task.error = errorMessage
  task.completedAt = new Date()
  if (task.rootSessionID) unregisterRootDescendant(ctx, task.rootSessionID)
  ctx.taskHistory.record(task.parentSessionID, { id: task.id, sessionID: task.sessionID, agent: task.agent, description: task.description, status: "error", category: task.category, startedAt: task.startedAt, completedAt: task.completedAt })

  if (task.concurrencyKey) { ctx.concurrencyManager.release(task.concurrencyKey); task.concurrencyKey = undefined }
  const completionTimer = ctx.completionTimers.get(task.id)
  if (completionTimer) { clearTimeout(completionTimer); ctx.completionTimers.delete(task.id) }
  const idleTimer = ctx.idleDeferralTimers.get(task.id)
  if (idleTimer) { clearTimeout(idleTimer); ctx.idleDeferralTimers.delete(task.id) }

  cleanupPendingByParent(ctx, task)
  clearNotificationsForTask(ctx, task.id)
  removeTaskToastTracking(task.id)
  scheduleTaskRemoval(ctx, task.id)
  if (task.sessionID) SessionCategoryRegistry.remove(task.sessionID)

  markForNotification(ctx, task)
  enqueueNotificationForParent(ctx, task.parentSessionID, () => notifyParentSession(ctx, task)).catch(() => {})
}

export async function pollRunningTasks(ctx: ManagerContext): Promise<void> {
  if (ctx.pollingInFlight) return
  ctx.pollingInFlight = true
  try {
    pruneStaleTasksAndNotifications({
      tasks: ctx.tasks,
      notifications: ctx.notifications,
      taskTtlMs: ctx.config?.taskTtlMs,
      onTaskPruned: (taskId, task, errorMsg) => {
        const wasPending = task.status === "pending"
        task.status = "error"
        task.error = errorMsg
        task.completedAt = new Date()
        if (!wasPending && task.rootSessionID) unregisterRootDescendant(ctx, task.rootSessionID)
        ctx.taskHistory.record(task.parentSessionID, { id: task.id, sessionID: task.sessionID, agent: task.agent, description: task.description, status: "error", category: task.category, startedAt: task.startedAt, completedAt: task.completedAt })
        if (task.concurrencyKey) { ctx.concurrencyManager.release(task.concurrencyKey); task.concurrencyKey = undefined }
        removeTaskToastTracking(task.id)
        const ct = ctx.completionTimers.get(taskId); if (ct) { clearTimeout(ct); ctx.completionTimers.delete(taskId) }
        const it = ctx.idleDeferralTimers.get(taskId); if (it) { clearTimeout(it); ctx.idleDeferralTimers.delete(taskId) }
        if (wasPending) {
          const key = task.model ? `${task.model.providerID}/${task.model.modelID}` : task.agent
          const queue = ctx.queuesByKey.get(key)
          if (queue) {
            const idx = queue.findIndex(i => i.task.id === taskId)
            if (idx !== -1) { queue.splice(idx, 1); if (queue.length === 0) ctx.queuesByKey.delete(key) }
          }
        }
        cleanupPendingByParent(ctx, task)
        markForNotification(ctx, task)
        enqueueNotificationForParent(ctx, task.parentSessionID, () => notifyParentSession(ctx, task)).catch(() => {})
      },
    })

    const statusResult = await ctx.client.session.status()
    const allStatuses = normalizeSDKResponse(statusResult, {} as Record<string, { type: string }>)

    await checkAndInterruptStaleTasks({
      tasks: ctx.tasks.values(),
      client: ctx.client,
      config: ctx.config,
      concurrencyManager: ctx.concurrencyManager,
      notifyParentSession: (task) => enqueueNotificationForParent(ctx, task.parentSessionID, () => notifyParentSession(ctx, task)),
      sessionStatuses: allStatuses,
    })

    for (const task of ctx.tasks.values()) {
      if (task.status !== "running") continue
      const sessionID = task.sessionID
      if (!sessionID) continue

      try {
        const sessionStatus = allStatuses[sessionID]
        if (sessionStatus?.type === "retry") {
          if (await tryManagerFallbackRetry(ctx, task, { name: "SessionRetry", message: (sessionStatus as any).message }, "polling:session.status")) continue
        }
        if (sessionStatus && isActiveSessionStatus(sessionStatus.type)) continue
        if (sessionStatus && isTerminalSessionStatus(sessionStatus.type)) {
          await tryCompleteTask(ctx, task, `polling (terminal: ${sessionStatus.type})`)
          continue
        }

        const sessionGoneFromStatus = !sessionStatus
        const sessionGoneThresholdReached = sessionGoneFromStatus && (task.consecutiveMissedPolls ?? 0) >= MIN_SESSION_GONE_POLLS
        const completionSource = sessionStatus?.type === "idle" ? "polling (idle)" : "polling (session gone)"
        const hasValidOutput = await validateSessionHasOutput(ctx, sessionID)
        if (!hasValidOutput) {
          if (sessionGoneThresholdReached) {
            const exists = await verifySessionStillExists(ctx.client, sessionID)
            if (!exists) { await failCrashedTask(ctx, task, "Subagent session no longer exists."); continue }
            task.consecutiveMissedPolls = 0
          }
          continue
        }
        if (task.status !== "running") continue
        const hasIncompleteTodos = await checkSessionTodos(ctx, sessionID)
        if (hasIncompleteTodos) continue
        await tryCompleteTask(ctx, task, completionSource)
      } catch (error) {
        log("[background-agent] Poll error for task:", { taskId: task.id, error })
      }
    }

    if (!hasRunningTasks(ctx)) stopPolling(ctx)
  } finally {
    ctx.pollingInFlight = false
  }
}
