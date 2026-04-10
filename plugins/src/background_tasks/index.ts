import type { Plugin } from "@opencode-ai/plugin"
import {
  createBackgroundTask,
  createBackgroundOutput,
  createBackgroundCancel,
} from "./tools"
import { WorkingBackgroundManager } from "./features/background-agent/working-manager"

const BackgroundTaskPlugin: Plugin = async (ctx) => {
  const manager = new WorkingBackgroundManager(ctx.client, ctx.directory)

  // Fetch available agents, filtered by task permission
  // Respects explicit task:deny, wildcard *:deny, and tools.task=false
  let agentNames: string[] = []
  try {
    const resp = await (ctx.client as any).app.agents()
    const agents: Array<{
      name?: string
      mode?: string
      permission?: Record<string, string>
      tools?: Record<string, boolean>
    }> = (resp as any).data ?? (resp as any).response ?? []
    agentNames = agents
      .filter((a) => {
        if (!a.name) return false
        const perm = a.permission ?? {}
        // Explicit task permission takes precedence
        if (perm.task === "deny") return false
        if (perm.task === "allow" || perm.task === "ask") return true
        // Wildcard deny blocks all tools including task
        if (perm["*"] === "deny") return false
        // Check tools map
        if (a.tools?.task === false) return false
        return true
      })
      .map((a) => a.name!)
      .sort()
  } catch {}

  return {
    tool: {
      task: createBackgroundTask(manager, ctx.client, agentNames),
      background_output: createBackgroundOutput(manager, ctx.client),
      background_cancel: createBackgroundCancel(manager, ctx.client),
    },
  }
}

export default BackgroundTaskPlugin
