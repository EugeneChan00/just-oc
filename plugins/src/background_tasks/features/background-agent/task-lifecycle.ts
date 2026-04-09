/**
 * Task lifecycle operations: launch, start, track, resume, cancel, complete.
 * Extracted from BackgroundManager to keep modules under ~800 lines.
 */

import type { BackgroundTask, LaunchInput, ResumeInput } from "./types"
import type { ManagerContext, QueueItem } from "./manager-context"
import { isAgentNotFoundError, FALLBACK_AGENT, buildFallbackBody } from "./spawner"
import {
  log,
  getAgentToolRestrictions,
  normalizeSDKResponse,
  promptWithModelSuggestionRetry,
  createInternalAgentTextPart,
} from "../../shared"
import { applySessionPromptParams } from "../../shared/session-prompt-params-helpers"
import { setSessionTools } from "../../shared/session-tools-store"
import { SessionCategoryRegistry } from "../../shared/session-category-registry"
import { isInsideTmux } from "../../shared/tmux"
import { subagentSessions } from "../claude-code-session-state"
import { getTaskToastManager } from "../task-toast-manager"
import { removeTaskToastTracking } from "./remove-task-toast-tracking"
import { abortWithTimeout } from "./abort-with-timeout"
import { formatDuration } from "./duration-formatter"
import {
  getMaxRootSessionSpawnBudget,
  getMaxSubagentDepth,
  resolveSubagentSpawnContext,
  createSubagentDepthLimitError,
  createSubagentDescendantLimitError,
  type SubagentSpawnContext,
} from "./subagent-spawn-limits"
import {
  enqueueNotificationForParent,
  markForNotification,
  cleanupPendingByParent,
} from "./task-notification"

// ── Abort helper ──────────────────────────────────────────────────────

export async function abortSessionWithLogging(
  ctx: ManagerContext,
  sessionID: string,
  reason: string
): Promise<void> {
  try {
    await abortWithTimeout(ctx.client, sessionID)
  } catch (error) {
    log(`[background-agent] Failed to abort session during ${reason}:`, {
      sessionID,
      error,
    })
  }
}

// ── Subagent spawn validation ─────────────────────────────────────────

export async function assertCanSpawn(
  ctx: ManagerContext,
  parentSessionID: string
): Promise<SubagentSpawnContext> {
  const spawnContext = await resolveSubagentSpawnContext(ctx.client, parentSessionID)
  const maxDepth = getMaxSubagentDepth(ctx.config)
  if (spawnContext.childDepth > maxDepth) {
    throw createSubagentDepthLimitError({
      childDepth: spawnContext.childDepth,
      maxDepth,
      parentSessionID,
      rootSessionID: spawnContext.rootSessionID,
    })
  }

  const maxBudget = getMaxRootSessionSpawnBudget(ctx.config)
  const descendantCount = ctx.rootDescendantCounts.get(spawnContext.rootSessionID) ?? 0
  if (descendantCount >= maxBudget) {
    throw createSubagentDescendantLimitError({
      rootSessionID: spawnContext.rootSessionID,
      descendantCount,
      maxDescendants: maxBudget,
    })
  }

  return spawnContext
}

export async function reserveSubagentSpawn(
  ctx: ManagerContext,
  parentSessionID: string
): Promise<{
  spawnContext: SubagentSpawnContext
  descendantCount: number
  commit: () => number
  rollback: () => void
}> {
  const spawnContext = await assertCanSpawn(ctx, parentSessionID)
  const descendantCount = registerRootDescendant(ctx, spawnContext.rootSessionID)
  let settled = false

  return {
    spawnContext,
    descendantCount,
    commit: () => {
      settled = true
      return descendantCount
    },
    rollback: () => {
      if (settled) return
      settled = true
      unregisterRootDescendant(ctx, spawnContext.rootSessionID)
    },
  }
}

export function registerRootDescendant(ctx: ManagerContext, rootSessionID: string): number {
  const nextCount = (ctx.rootDescendantCounts.get(rootSessionID) ?? 0) + 1
  ctx.rootDescendantCounts.set(rootSessionID, nextCount)
  return nextCount
}

export function unregisterRootDescendant(ctx: ManagerContext, rootSessionID: string): void {
  const currentCount = ctx.rootDescendantCounts.get(rootSessionID) ?? 0
  if (currentCount <= 1) {
    ctx.rootDescendantCounts.delete(rootSessionID)
    return
  }
  ctx.rootDescendantCounts.set(rootSessionID, currentCount - 1)
}

export function markPreStartDescendantReservation(ctx: ManagerContext, task: BackgroundTask): void {
  ctx.preStartDescendantReservations.add(task.id)
}

export function settlePreStartDescendantReservation(ctx: ManagerContext, task: BackgroundTask): void {
  ctx.preStartDescendantReservations.delete(task.id)
}

export function rollbackPreStartDescendantReservation(ctx: ManagerContext, task: BackgroundTask): void {
  if (!ctx.preStartDescendantReservations.delete(task.id)) return
  if (!task.rootSessionID) return
  unregisterRootDescendant(ctx, task.rootSessionID)
}

// ── Concurrency key ───────────────────────────────────────────────────

export function getConcurrencyKeyFromInput(input: LaunchInput): string {
  if (input.model) {
    return `${input.model.providerID}/${input.model.modelID}`
  }
  return input.agent
}

// ── Launch ────────────────────────────────────────────────────────────

export async function launch(ctx: ManagerContext, input: LaunchInput): Promise<BackgroundTask> {
  log("[background-agent] launch() called with:", {
    agent: input.agent,
    model: input.model,
    description: input.description,
    parentSessionID: input.parentSessionID,
  })

  if (!input.agent || input.agent.trim() === "") {
    throw new Error("Agent parameter is required")
  }

  const spawnReservation = await reserveSubagentSpawn(ctx, input.parentSessionID)

  try {
    log("[background-agent] spawn guard passed", {
      parentSessionID: input.parentSessionID,
      rootSessionID: spawnReservation.spawnContext.rootSessionID,
      childDepth: spawnReservation.spawnContext.childDepth,
      descendantCount: spawnReservation.descendantCount,
    })

    const task: BackgroundTask = {
      id: `bg_${crypto.randomUUID().slice(0, 8)}`,
      status: "pending",
      queuedAt: new Date(),
      rootSessionID: spawnReservation.spawnContext.rootSessionID,
      description: input.description,
      prompt: input.prompt,
      agent: input.agent,
      spawnDepth: spawnReservation.spawnContext.childDepth,
      parentSessionID: input.parentSessionID,
      parentMessageID: input.parentMessageID,
      parentModel: input.parentModel,
      parentAgent: input.parentAgent,
      parentTools: input.parentTools,
      model: input.model,
      fallbackChain: input.fallbackChain,
      attemptCount: 0,
      category: input.category,
    }

    ctx.tasks.set(task.id, task)
    ctx.taskHistory.record(input.parentSessionID, { id: task.id, agent: input.agent, description: input.description, status: "pending", category: input.category })

    if (input.parentSessionID) {
      const pending = ctx.pendingByParent.get(input.parentSessionID) ?? new Set()
      pending.add(task.id)
      ctx.pendingByParent.set(input.parentSessionID, pending)
    }

    const key = getConcurrencyKeyFromInput(input)
    const queue = ctx.queuesByKey.get(key) ?? []
    queue.push({ task, input })
    ctx.queuesByKey.set(key, queue)

    log("[background-agent] Task queued:", { taskId: task.id, key, queueLength: queue.length })

    const toastManager = getTaskToastManager()
    if (toastManager) {
      toastManager.addTask({
        id: task.id,
        description: input.description,
        agent: input.agent,
        isBackground: true,
        status: "queued",
        skills: input.skills,
      })
    }

    spawnReservation.commit()
    markPreStartDescendantReservation(ctx, task)

    void processKey(ctx, key)

    return { ...task }
  } catch (error) {
    spawnReservation.rollback()
    throw error
  }
}

// ── Process queue ─────────────────────────────────────────────────────

export async function processKey(ctx: ManagerContext, key: string): Promise<void> {
  if (ctx.processingKeys.has(key)) return
  ctx.processingKeys.add(key)

  try {
    const queue = ctx.queuesByKey.get(key)
    while (queue && queue.length > 0) {
      const item = queue.shift()
      if (!item) continue

      await ctx.concurrencyManager.acquire(key)

      if (item.task.status === "cancelled" || item.task.status === "error" || item.task.status === "interrupt") {
        rollbackPreStartDescendantReservation(ctx, item.task)
        ctx.concurrencyManager.release(key)
        continue
      }

      try {
        await startTask(ctx, item)
      } catch (error) {
        log("[background-agent] Error starting task:", error)
        rollbackPreStartDescendantReservation(ctx, item.task)

        item.task.status = "error"
        item.task.error = error instanceof Error ? error.message : String(error)
        item.task.completedAt = new Date()

        if (item.task.concurrencyKey) {
          ctx.concurrencyManager.release(item.task.concurrencyKey)
          item.task.concurrencyKey = undefined
        } else {
          ctx.concurrencyManager.release(key)
        }

        removeTaskToastTracking(item.task.id)

        if (item.task.sessionID) {
          await abortSessionWithLogging(ctx, item.task.sessionID, "startTask error cleanup")
        }

        markForNotification(ctx, item.task)
        enqueueNotificationForParent(ctx, item.task.parentSessionID, () =>
          import("./task-notification").then(m => m.notifyParentSession(ctx, item.task))
        ).catch(err => {
          log("[background-agent] Failed to notify on startTask error:", err)
        })
      }
    }
  } finally {
    ctx.processingKeys.delete(key)
  }
}

// ── Start task ────────────────────────────────────────────────────────

async function startTask(ctx: ManagerContext, item: QueueItem): Promise<void> {
  const { task, input } = item

  log("[background-agent] Starting task:", { taskId: task.id, agent: input.agent, model: input.model })

  const concurrencyKey = getConcurrencyKeyFromInput(input)

  const parentSession = await ctx.client.session.get({
    path: { id: input.parentSessionID },
  }).catch((err) => {
    log(`[background-agent] Failed to get parent session: ${err}`)
    return null
  })
  const parentDirectory = parentSession?.data?.directory ?? ctx.directory

  const createResult = await ctx.client.session.create({
    body: {
      parentID: input.parentSessionID,
      title: `${input.description} (@${input.agent} subagent)`,
      ...(input.sessionPermission ? { permission: input.sessionPermission } : {}),
    } as Record<string, unknown>,
    query: { directory: parentDirectory },
  })

  if (createResult.error) {
    throw new Error(`Failed to create background session: ${createResult.error}`)
  }
  if (!createResult.data?.id) {
    throw new Error("Failed to create background session: API returned no session ID")
  }

  const sessionID = createResult.data.id

  if (task.status === "cancelled") {
    await abortSessionWithLogging(ctx, sessionID, "cancelled pre-start cleanup")
    ctx.concurrencyManager.release(concurrencyKey)
    return
  }

  settlePreStartDescendantReservation(ctx, task)
  subagentSessions.add(sessionID)

  if (ctx.onSubagentSessionCreated && ctx.tmuxEnabled && isInsideTmux()) {
    await ctx.onSubagentSessionCreated({
      sessionID,
      parentID: input.parentSessionID,
      title: input.description,
    }).catch((err) => { log("[background-agent] Failed to spawn tmux pane:", err) })
    await new Promise(r => setTimeout(r, 200))
  }

  if (ctx.tasks.get(task.id)?.status === "cancelled") {
    await abortSessionWithLogging(ctx, sessionID, "cancelled during tmux setup")
    subagentSessions.delete(sessionID)
    if (task.rootSessionID) unregisterRootDescendant(ctx, task.rootSessionID)
    ctx.concurrencyManager.release(concurrencyKey)
    return
  }

  task.status = "running"
  task.startedAt = new Date()
  task.sessionID = sessionID
  task.progress = { toolCalls: 0, lastUpdate: new Date() }
  task.concurrencyKey = concurrencyKey
  task.concurrencyGroup = concurrencyKey

  ctx.taskHistory.record(input.parentSessionID, { id: task.id, sessionID, agent: input.agent, description: input.description, status: "running", category: input.category, startedAt: task.startedAt })

  // startPolling is called by manager after delegation
  const toastManager = getTaskToastManager()
  if (toastManager) toastManager.updateTask(task.id, "running")

  const launchModel = input.model
    ? { providerID: input.model.providerID, modelID: input.model.modelID }
    : undefined
  const launchVariant = input.model?.variant

  if (input.model) applySessionPromptParams(sessionID, input.model)

  const promptBody = {
    agent: input.agent,
    ...(launchModel ? { model: launchModel } : {}),
    ...(launchVariant ? { variant: launchVariant } : {}),
    system: input.skillContent,
    tools: (() => {
      const tools = {
        task: false,
        call_omo_agent: true,
        question: false,
        ...getAgentToolRestrictions(input.agent),
      }
      setSessionTools(sessionID, tools)
      return tools
    })(),
    parts: [createInternalAgentTextPart(input.prompt)],
  }

  promptWithModelSuggestionRetry(ctx.client, {
    path: { id: sessionID },
    body: promptBody,
  }).catch(async (error) => {
    if (isAgentNotFoundError(error) && input.agent !== FALLBACK_AGENT) {
      try {
        const fallbackBody = buildFallbackBody(promptBody, FALLBACK_AGENT)
        setSessionTools(sessionID, fallbackBody.tools as Record<string, boolean>)
        await promptWithModelSuggestionRetry(ctx.client, { path: { id: sessionID }, body: fallbackBody })
        task.agent = FALLBACK_AGENT
        return
      } catch (retryError) {
        log("[background-agent] Fallback agent also failed:", retryError)
      }
    }

    log("[background-agent] promptAsync error:", error)
    const existingTask = findBySession(ctx, sessionID)
    if (existingTask) {
      existingTask.status = "interrupt"
      const errorMessage = error instanceof Error ? error.message : String(error)
      existingTask.error = errorMessage.includes("agent.name") || errorMessage.includes("undefined") || isAgentNotFoundError(error)
        ? `Agent "${input.agent}" not found. Make sure the agent is registered.`
        : errorMessage
      existingTask.completedAt = new Date()
      if (existingTask.rootSessionID) unregisterRootDescendant(ctx, existingTask.rootSessionID)
      if (existingTask.concurrencyKey) {
        ctx.concurrencyManager.release(existingTask.concurrencyKey)
        existingTask.concurrencyKey = undefined
      }
      removeTaskToastTracking(existingTask.id)
      await abortSessionWithLogging(ctx, sessionID, "launch error cleanup")

      markForNotification(ctx, existingTask)
      enqueueNotificationForParent(ctx, existingTask.parentSessionID, () =>
        import("./task-notification").then(m => m.notifyParentSession(ctx, existingTask))
      ).catch(err => { log("[background-agent] Failed to notify on error:", err) })
    }
  })
}

// ── Query helpers ─────────────────────────────────────────────────────

export function getTask(ctx: ManagerContext, id: string): BackgroundTask | undefined {
  return ctx.tasks.get(id)
}

export function getTasksByParentSession(ctx: ManagerContext, sessionID: string): BackgroundTask[] {
  const result: BackgroundTask[] = []
  for (const task of ctx.tasks.values()) {
    if (task.parentSessionID === sessionID) result.push(task)
  }
  return result
}

export function getAllDescendantTasks(ctx: ManagerContext, sessionID: string): BackgroundTask[] {
  const result: BackgroundTask[] = []
  for (const child of getTasksByParentSession(ctx, sessionID)) {
    result.push(child)
    if (child.sessionID) result.push(...getAllDescendantTasks(ctx, child.sessionID))
  }
  return result
}

export function findBySession(ctx: ManagerContext, sessionID: string): BackgroundTask | undefined {
  for (const task of ctx.tasks.values()) {
    if (task.sessionID === sessionID) return task
  }
  return undefined
}

// ── Track task ────────────────────────────────────────────────────────

export async function trackTask(ctx: ManagerContext, input: {
  taskId: string; sessionID: string; parentSessionID: string
  description: string; agent?: string; parentAgent?: string; concurrencyKey?: string
}): Promise<BackgroundTask> {
  const existingTask = ctx.tasks.get(input.taskId)
  if (existingTask) {
    const parentChanged = input.parentSessionID !== existingTask.parentSessionID
    if (parentChanged) {
      cleanupPendingByParent(ctx, existingTask)
      existingTask.parentSessionID = input.parentSessionID
    }
    if (input.parentAgent !== undefined) existingTask.parentAgent = input.parentAgent
    if (!existingTask.concurrencyGroup) {
      existingTask.concurrencyGroup = input.concurrencyKey ?? existingTask.agent
    }
    if (existingTask.sessionID) subagentSessions.add(existingTask.sessionID)

    if (existingTask.status === "pending" || existingTask.status === "running") {
      const pending = ctx.pendingByParent.get(input.parentSessionID) ?? new Set()
      pending.add(existingTask.id)
      ctx.pendingByParent.set(input.parentSessionID, pending)
    } else if (!parentChanged) {
      cleanupPendingByParent(ctx, existingTask)
    }
    return existingTask
  }

  const concurrencyGroup = input.concurrencyKey ?? input.agent ?? "task"
  if (input.concurrencyKey) await ctx.concurrencyManager.acquire(input.concurrencyKey)

  const task: BackgroundTask = {
    id: input.taskId,
    sessionID: input.sessionID,
    parentSessionID: input.parentSessionID,
    parentMessageID: "",
    description: input.description,
    prompt: "",
    agent: input.agent || "task",
    status: "running",
    startedAt: new Date(),
    progress: { toolCalls: 0, lastUpdate: new Date() },
    parentAgent: input.parentAgent,
    concurrencyKey: input.concurrencyKey,
    concurrencyGroup,
  }

  ctx.tasks.set(task.id, task)
  subagentSessions.add(input.sessionID)
  ctx.taskHistory.record(input.parentSessionID, { id: task.id, sessionID: input.sessionID, agent: input.agent || "task", description: input.description, status: "running", startedAt: task.startedAt })

  if (input.parentSessionID) {
    const pending = ctx.pendingByParent.get(input.parentSessionID) ?? new Set()
    pending.add(task.id)
    ctx.pendingByParent.set(input.parentSessionID, pending)
  }

  return task
}

// ── Resume ────────────────────────────────────────────────────────────

export async function resume(ctx: ManagerContext, input: ResumeInput): Promise<BackgroundTask> {
  const existingTask = findBySession(ctx, input.sessionId)
  if (!existingTask) throw new Error(`Task not found for session: ${input.sessionId}`)
  if (!existingTask.sessionID) throw new Error(`Task has no sessionID: ${existingTask.id}`)
  if (existingTask.status === "running") return existingTask

  const completionTimer = ctx.completionTimers.get(existingTask.id)
  if (completionTimer) {
    clearTimeout(completionTimer)
    ctx.completionTimers.delete(existingTask.id)
  }

  const concurrencyKey = existingTask.concurrencyGroup ?? existingTask.agent
  await ctx.concurrencyManager.acquire(concurrencyKey)
  existingTask.concurrencyKey = concurrencyKey
  existingTask.concurrencyGroup = concurrencyKey

  existingTask.status = "running"
  existingTask.completedAt = undefined
  existingTask.error = undefined
  existingTask.parentSessionID = input.parentSessionID
  existingTask.parentMessageID = input.parentMessageID
  existingTask.parentModel = input.parentModel
  existingTask.parentAgent = input.parentAgent
  if (input.parentTools) existingTask.parentTools = input.parentTools
  existingTask.startedAt = new Date()
  existingTask.progress = {
    toolCalls: existingTask.progress?.toolCalls ?? 0,
    toolCallWindow: existingTask.progress?.toolCallWindow,
    countedToolPartIDs: existingTask.progress?.countedToolPartIDs,
    lastUpdate: new Date(),
  }

  if (existingTask.sessionID) subagentSessions.add(existingTask.sessionID)

  if (input.parentSessionID) {
    const pending = ctx.pendingByParent.get(input.parentSessionID) ?? new Set()
    pending.add(existingTask.id)
    ctx.pendingByParent.set(input.parentSessionID, pending)
  }

  const toastManager = getTaskToastManager()
  if (toastManager) {
    toastManager.addTask({ id: existingTask.id, description: existingTask.description, agent: existingTask.agent, isBackground: true })
  }

  const resumeModel = existingTask.model
    ? { providerID: existingTask.model.providerID, modelID: existingTask.model.modelID }
    : undefined
  const resumeVariant = existingTask.model?.variant

  if (existingTask.model) applySessionPromptParams(existingTask.sessionID!, existingTask.model)

  ctx.client.session.promptAsync({
    path: { id: existingTask.sessionID },
    body: {
      agent: existingTask.agent,
      ...(resumeModel ? { model: resumeModel } : {}),
      ...(resumeVariant ? { variant: resumeVariant } : {}),
      tools: (() => {
        const tools = { task: false, call_omo_agent: true, question: false, ...getAgentToolRestrictions(existingTask.agent) }
        setSessionTools(existingTask.sessionID!, tools)
        return tools
      })(),
      parts: [createInternalAgentTextPart(input.prompt)],
    },
  }).catch(async (error) => {
    log("[background-agent] resume prompt error:", error)
    existingTask.status = "interrupt"
    existingTask.error = error instanceof Error ? error.message : String(error)
    existingTask.completedAt = new Date()
    if (existingTask.rootSessionID) unregisterRootDescendant(ctx, existingTask.rootSessionID)
    if (existingTask.concurrencyKey) {
      ctx.concurrencyManager.release(existingTask.concurrencyKey)
      existingTask.concurrencyKey = undefined
    }
    removeTaskToastTracking(existingTask.id)
    if (existingTask.sessionID) {
      await abortSessionWithLogging(ctx, existingTask.sessionID, "resume error cleanup")
    }
    markForNotification(ctx, existingTask)
    enqueueNotificationForParent(ctx, existingTask.parentSessionID, () =>
      import("./task-notification").then(m => m.notifyParentSession(ctx, existingTask))
    ).catch(err => { log("[background-agent] Failed to notify on resume error:", err) })
  })

  return existingTask
}

// ── Cancel ────────────────────────────────────────────────────────────

export async function cancelTask(
  ctx: ManagerContext,
  taskId: string,
  options?: { source?: string; reason?: string; abortSession?: boolean; skipNotification?: boolean }
): Promise<boolean> {
  const task = ctx.tasks.get(taskId)
  if (!task || (task.status !== "running" && task.status !== "pending")) return false

  const source = options?.source ?? "cancel"
  const abortSession = options?.abortSession !== false
  const reason = options?.reason

  if (task.status === "pending") {
    const key = task.model ? `${task.model.providerID}/${task.model.modelID}` : task.agent
    const queue = ctx.queuesByKey.get(key)
    if (queue) {
      const index = queue.findIndex(item => item.task.id === taskId)
      if (index !== -1) {
        queue.splice(index, 1)
        if (queue.length === 0) ctx.queuesByKey.delete(key)
      }
    }
    rollbackPreStartDescendantReservation(ctx, task)
  }

  const wasRunning = task.status === "running"
  task.status = "cancelled"
  task.completedAt = new Date()
  if (wasRunning && task.rootSessionID) unregisterRootDescendant(ctx, task.rootSessionID)
  if (reason) task.error = reason
  ctx.taskHistory.record(task.parentSessionID, { id: task.id, sessionID: task.sessionID, agent: task.agent, description: task.description, status: "cancelled", category: task.category, startedAt: task.startedAt, completedAt: task.completedAt })

  if (task.concurrencyKey) {
    ctx.concurrencyManager.release(task.concurrencyKey)
    task.concurrencyKey = undefined
  }

  const existingTimer = ctx.completionTimers.get(task.id)
  if (existingTimer) { clearTimeout(existingTimer); ctx.completionTimers.delete(task.id) }
  const idleTimer = ctx.idleDeferralTimers.get(task.id)
  if (idleTimer) { clearTimeout(idleTimer); ctx.idleDeferralTimers.delete(task.id) }

  if (abortSession && task.sessionID) {
    await abortSessionWithLogging(ctx, task.sessionID, `task cancellation (${source})`)
    SessionCategoryRegistry.remove(task.sessionID)
  }

  removeTaskToastTracking(task.id)

  if (options?.skipNotification) {
    cleanupPendingByParent(ctx, task)
    scheduleTaskRemoval(ctx, task.id)
    return true
  }

  markForNotification(ctx, task)

  try {
    await enqueueNotificationForParent(ctx, task.parentSessionID, () =>
      import("./task-notification").then(m => m.notifyParentSession(ctx, task))
    )
  } catch (err) {
    log("[background-agent] Error in notifyParentSession for cancelled task:", { taskId: task.id, error: err })
  }

  return true
}

export function cancelPendingTask(ctx: ManagerContext, taskId: string): boolean {
  const task = ctx.tasks.get(taskId)
  if (!task || task.status !== "pending") return false
  void cancelTask(ctx, taskId, { source: "cancelPendingTask", abortSession: false })
  return true
}

// ── Complete ──────────────────────────────────────────────────────────

export async function tryCompleteTask(ctx: ManagerContext, task: BackgroundTask, source: string): Promise<boolean> {
  if (task.status !== "running") return false

  task.status = "completed"
  task.completedAt = new Date()
  ctx.taskHistory.record(task.parentSessionID, { id: task.id, sessionID: task.sessionID, agent: task.agent, description: task.description, status: "completed", category: task.category, startedAt: task.startedAt, completedAt: task.completedAt })

  if (task.rootSessionID) unregisterRootDescendant(ctx, task.rootSessionID)
  removeTaskToastTracking(task.id)

  if (task.concurrencyKey) {
    ctx.concurrencyManager.release(task.concurrencyKey)
    task.concurrencyKey = undefined
  }

  markForNotification(ctx, task)

  const idleTimer = ctx.idleDeferralTimers.get(task.id)
  if (idleTimer) { clearTimeout(idleTimer); ctx.idleDeferralTimers.delete(task.id) }

  if (task.sessionID) {
    await abortSessionWithLogging(ctx, task.sessionID, `task completion (${source})`)
    SessionCategoryRegistry.remove(task.sessionID)
  }

  try {
    await enqueueNotificationForParent(ctx, task.parentSessionID, () =>
      import("./task-notification").then(m => m.notifyParentSession(ctx, task))
    )
  } catch (err) {
    log("[background-agent] Error in notifyParentSession:", { taskId: task.id, error: err })
  }

  return true
}

// ── Task removal scheduling ───────────────────────────────────────────

const MAX_TASK_REMOVAL_RESCHEDULES = 6

import { TASK_CLEANUP_DELAY_MS, TASK_TTL_MS } from "./constants"

export function scheduleTaskRemoval(ctx: ManagerContext, taskId: string, rescheduleCount = 0): void {
  const existingTimer = ctx.completionTimers.get(taskId)
  if (existingTimer) { clearTimeout(existingTimer); ctx.completionTimers.delete(taskId) }

  const timer = setTimeout(() => {
    ctx.completionTimers.delete(taskId)
    const task = ctx.tasks.get(taskId)
    if (!task) return

    if (task.parentSessionID) {
      const siblings = getTasksByParentSession(ctx, task.parentSessionID)
      const runningOrPending = siblings.filter(s => s.id !== taskId && (s.status === "running" || s.status === "pending"))
      const completedAtTimestamp = task.completedAt?.getTime()
      const reachedTtl = completedAtTimestamp !== undefined && (Date.now() - completedAtTimestamp) >= TASK_TTL_MS
      if (runningOrPending.length > 0 && rescheduleCount < MAX_TASK_REMOVAL_RESCHEDULES && !reachedTtl) {
        scheduleTaskRemoval(ctx, taskId, rescheduleCount + 1)
        return
      }
    }

    clearNotificationsForTask(ctx, taskId)
    ctx.tasks.delete(taskId)
    clearTaskHistoryWhenParentTasksGone(ctx, task.parentSessionID)
    if (task.sessionID) {
      subagentSessions.delete(task.sessionID)
      SessionCategoryRegistry.remove(task.sessionID)
    }
  }, TASK_CLEANUP_DELAY_MS)

  ctx.completionTimers.set(taskId, timer)
}

function clearNotificationsForTask(ctx: ManagerContext, taskId: string): void {
  for (const [sessionID, tasks] of ctx.notifications.entries()) {
    const filtered = tasks.filter((t) => t.id !== taskId)
    if (filtered.length === 0) ctx.notifications.delete(sessionID)
    else ctx.notifications.set(sessionID, filtered)
  }
}

function clearTaskHistoryWhenParentTasksGone(ctx: ManagerContext, parentSessionID: string | undefined): void {
  if (!parentSessionID) return
  if (getTasksByParentSession(ctx, parentSessionID).length > 0) return
  ctx.taskHistory.clearSession(parentSessionID)
  ctx.completedTaskSummaries.delete(parentSessionID)
}
