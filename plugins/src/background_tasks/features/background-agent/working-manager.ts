import type { PluginInput } from "@opencode-ai/plugin"

import type { BackgroundManager } from "./manager-interface"
import type { BackgroundTask, LaunchInput, ResumeInput, BackgroundTaskStatus } from "./types"
import { formatDuration } from "./duration-formatter"
import { isActiveSessionStatus } from "./session-status-classifier"
import { buildBackgroundTaskNotificationText } from "./background-task-notification-template"

type OpencodeClient = PluginInput["client"]

const POLLING_INTERVAL_MS = 3000

export class WorkingBackgroundManager implements BackgroundManager {
  private tasks = new Map<string, BackgroundTask>()
  private taskCounter = 0
  private pollingInterval?: ReturnType<typeof setInterval>
  private pollingInFlight = false
  private pendingByParent = new Map<string, Set<string>>()
  private completedTaskSummaries = new Map<string, Array<{ id: string; description: string; status: BackgroundTaskStatus; error?: string }>>()

  constructor(
    private client: OpencodeClient,
    private directory: string,
  ) {}

  async launch(input: LaunchInput): Promise<BackgroundTask> {
    const id = `bg_${++this.taskCounter}_${Date.now()}`
    const task: BackgroundTask = {
      id,
      parentSessionID: input.parentSessionID,
      parentMessageID: input.parentMessageID,
      description: input.description,
      prompt: input.prompt,
      agent: input.agent,
      status: "pending",
      queuedAt: new Date(),
      parentModel: input.parentModel,
      parentAgent: input.parentAgent,
      background: input.background,
    }
    this.tasks.set(id, task)

    const pending = this.pendingByParent.get(input.parentSessionID) ?? new Set()
    pending.add(id)
    this.pendingByParent.set(input.parentSessionID, pending)

    // Fire-and-forget: create session and send prompt
    void this.startTask(task, input).catch((error) => {
      task.status = "error"
      task.error = error instanceof Error ? error.message : String(error)
      task.completedAt = new Date()
      if (task.background) void this.notifyParent(task)
    })

    return task
  }

  getTask(taskId: string): BackgroundTask | undefined {
    return this.tasks.get(taskId)
  }

  getAllDescendantTasks(sessionID: string): BackgroundTask[] {
    return Array.from(this.tasks.values()).filter(
      (t) => t.parentSessionID === sessionID
    )
  }

  async cancelTask(
    taskId: string,
    options: { source: string; abortSession?: boolean; skipNotification?: boolean }
  ): Promise<boolean> {
    const task = this.tasks.get(taskId)
    if (!task || (task.status !== "running" && task.status !== "pending")) return false

    task.status = "cancelled"
    task.completedAt = new Date()

    if (task.sessionID && options.abortSession !== false) {
      try {
        await this.client.session.abort({ path: { id: task.sessionID } })
      } catch {}
    }

    if (!options.skipNotification && task.background) {
      void this.notifyParent(task)
    }

    return true
  }

  async resume(input: ResumeInput): Promise<BackgroundTask> {
    // Find existing task by session ID
    let existingTask: BackgroundTask | undefined
    for (const task of this.tasks.values()) {
      if (task.sessionID === input.sessionId) {
        existingTask = task
        break
      }
    }
    if (!existingTask) throw new Error(`Task not found for session: ${input.sessionId}`)
    if (!existingTask.sessionID) throw new Error(`Task has no sessionID: ${existingTask.id}`)
    if (existingTask.status === "running") return existingTask

    // Reset task state for resumption
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
      lastUpdate: new Date(),
    }

    // Track as pending for this parent
    const pending = this.pendingByParent.get(input.parentSessionID) ?? new Set()
    pending.add(existingTask.id)
    this.pendingByParent.set(input.parentSessionID, pending)

    // Start polling
    this.startPolling()

    // Send new prompt to existing session
    this.client.session.promptAsync({
      path: { id: existingTask.sessionID },
      body: {
        agent: existingTask.agent,
        parts: [{ type: "text" as const, text: input.prompt }],
      },
    }).catch((error) => {
      const msg = error instanceof Error ? error.message : String(error)
      existingTask!.status = "error"
      existingTask!.error = msg
      existingTask!.completedAt = new Date()
      if (existingTask!.background) void this.notifyParent(existingTask!)
    })

    return existingTask
  }

  // --- Internal ---

  private async startTask(task: BackgroundTask, input: LaunchInput): Promise<void> {
    // Resolve parent directory
    const parentSession = await this.client.session.get({
      path: { id: input.parentSessionID },
    }).catch(() => null)
    const parentDirectory = parentSession?.data?.directory ?? this.directory

    // Create child session
    const createResult = await this.client.session.create({
      body: {
        parentID: input.parentSessionID,
        title: `${input.description} (@${input.agent} subagent)`,
      } as Record<string, unknown>,
      query: { directory: parentDirectory },
    })

    if (createResult.error || !createResult.data?.id) {
      throw new Error(`Failed to create background session: ${createResult.error ?? "no session ID returned"}`)
    }

    const sessionID = createResult.data.id

    // Mark running
    task.status = "running"
    task.startedAt = new Date()
    task.sessionID = sessionID
    task.progress = { toolCalls: 0, lastUpdate: new Date() }


    // Start polling
    this.startPolling()

    // Send prompt (fire-and-forget)
    this.client.session.promptAsync({
      path: { id: sessionID },
      body: {
        agent: input.agent,
        parts: [{ type: "text" as const, text: input.prompt }],
      },
    }).catch((error) => {
      const msg = error instanceof Error ? error.message : String(error)
      task.status = "error"
      task.error = msg
      task.completedAt = new Date()
      void this.notifyParent(task)
    })
  }

  private startPolling(): void {
    if (this.pollingInterval) return
    this.pollingInterval = setInterval(() => { void this.pollRunningTasks() }, POLLING_INTERVAL_MS)
    if (this.pollingInterval.unref) this.pollingInterval.unref()
  }

  private stopPolling(): void {
    if (this.pollingInterval) {
      clearInterval(this.pollingInterval)
      this.pollingInterval = undefined
    }
  }

  private async pollRunningTasks(): Promise<void> {
    if (this.pollingInFlight) return
    this.pollingInFlight = true

    try {
      const statusResult = await this.client.session.status()
      const raw = statusResult as any
      // Debug: log what the SDK actually returns
      const allStatuses: Record<string, { type: string }> =
        raw.data ?? raw.response ?? {}

      for (const task of this.tasks.values()) {
        if (task.status !== "running") continue
        const sessionID = task.sessionID
        if (!sessionID) continue

        const sessionStatus = allStatuses[sessionID]

        // Still active — keep polling
        if (sessionStatus && isActiveSessionStatus(sessionStatus.type)) continue

        // Idle or missing from status — check if session produced output
        if (!sessionStatus || sessionStatus.type === "idle") {
          const hasOutput = await this.checkSessionHasOutput(sessionID)
          if (!hasOutput) continue

          // Complete the task
          await this.completeTask(task, sessionStatus?.type ?? "gone")
          continue
        }

        // Interrupted
        if (sessionStatus.type === "interrupted") {
          task.status = "error"
          task.error = "Session was interrupted"
          task.completedAt = new Date()
          if (task.background) void this.notifyParent(task)
          continue
        }
      }

      // Stop polling if no running tasks
      let hasRunning = false
      for (const task of this.tasks.values()) {
        if (task.status === "running") { hasRunning = true; break }
      }
      if (!hasRunning) this.stopPolling()
    } finally {
      this.pollingInFlight = false
    }
  }

  private async checkSessionHasOutput(sessionID: string): Promise<boolean> {
    try {
      const response = await this.client.session.messages({ path: { id: sessionID } })
      const messages: Array<Record<string, unknown>> =
        ((response as any).data ?? (response as any).response ?? []) as any
      return messages.some((m: any) => {
        const role = m.role ?? m.info?.role
        return role === "assistant" || role === "tool"
      })
    } catch {
      return false
    }
  }

  private async completeTask(task: BackgroundTask, _source: string): Promise<void> {
    if (task.status !== "running") return

    task.status = "completed"
    task.completedAt = new Date()

    // Abort the sub-agent session (cleanup)
    if (task.sessionID) {
      try {
        await this.client.session.abort({ path: { id: task.sessionID } })
      } catch {}
    }

    // Only send system-reminder notification for background tasks
    if (task.background) {
      void this.notifyParent(task)
    }
  }

  private async notifyParent(task: BackgroundTask): Promise<void> {
    const duration = formatDuration(task.startedAt ?? new Date(), task.completedAt)

    // Track completed tasks per parent
    if (!this.completedTaskSummaries.has(task.parentSessionID)) {
      this.completedTaskSummaries.set(task.parentSessionID, [])
    }
    this.completedTaskSummaries.get(task.parentSessionID)!.push({
      id: task.id,
      description: task.description,
      status: task.status,
      error: task.error,
    })

    // Check remaining tasks for this parent
    const pendingSet = this.pendingByParent.get(task.parentSessionID)
    let allComplete = false
    let remainingCount = 0
    if (pendingSet) {
      pendingSet.delete(task.id)
      remainingCount = pendingSet.size
      allComplete = remainingCount === 0
      if (allComplete) this.pendingByParent.delete(task.parentSessionID)
    }

    const completedTasks = allComplete
      ? (this.completedTaskSummaries.get(task.parentSessionID) ?? [])
      : []
    if (allComplete) this.completedTaskSummaries.delete(task.parentSessionID)

    const statusText = task.status === "completed" ? "COMPLETED"
      : task.status === "interrupt" ? "INTERRUPTED"
      : task.status === "error" ? "ERROR"
      : "CANCELLED"

    const notification = buildBackgroundTaskNotificationText({
      task, duration, statusText, allComplete, remainingCount, completedTasks,
    })

    try {
      await this.client.session.promptAsync({
        path: { id: task.parentSessionID },
        body: {
          noReply: !allComplete && task.status === "completed",
          parts: [{ type: "text" as const, text: notification }],
        },
      })
    } catch {
      // Parent session may have been aborted — nothing we can do
    }
  }
}
