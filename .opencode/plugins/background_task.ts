import type { Plugin } from "@opencode-ai/plugin"
import {
  createBackgroundTask,
  createBackgroundOutput,
  createBackgroundCancel,
} from "../../plugins/src/background_tasks/tools"
import type { BackgroundManager } from "../../plugins/src/background_tasks/features/background-agent"
import type { BackgroundTask, LaunchInput } from "../../plugins/src/background_tasks/features/background-agent/types"

/**
 * In-memory BackgroundManager implementation.
 * Provides task lifecycle management for the background task tools.
 * This is a minimal implementation - the full oh-my-openagent BackgroundManager
 * (in plugins/src/background_tasks/features/background-agent/manager.ts) can
 * replace this once its deep dependency chain is wired up.
 */
class SimpleBackgroundManager implements BackgroundManager {
  private tasks = new Map<string, BackgroundTask>()
  private taskCounter = 0

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
    }
    this.tasks.set(id, task)
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
    _options: { source: string; abortSession?: boolean; skipNotification?: boolean }
  ): Promise<boolean> {
    const task = this.tasks.get(taskId)
    if (!task) return false
    task.status = "cancelled"
    task.completedAt = new Date()
    return true
  }
}

const BackgroundTaskPlugin: Plugin = async (ctx) => {
  const manager = new SimpleBackgroundManager()

  return {
    tools: {
      background_task: createBackgroundTask(manager, ctx.client),
      background_output: createBackgroundOutput(manager, ctx.client),
      background_cancel: createBackgroundCancel(manager, ctx.client),
    },
  }
}

export default BackgroundTaskPlugin
