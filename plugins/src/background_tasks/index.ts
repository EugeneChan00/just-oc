import type { Plugin } from "@opencode-ai/plugin"
import {
  createBackgroundTask,
  createBackgroundOutput,
  createBackgroundCancel,
} from "./tools"
import { WorkingBackgroundManager } from "./features/background-agent/working-manager"

const BackgroundTaskPlugin: Plugin = async (ctx) => {
  const manager = new WorkingBackgroundManager(ctx.client, ctx.directory)

  // Don't fetch agents at init — app.agents() deadlocks because the app
  // isn't ready until all plugins resolve. Agent names are only used for
  // schema enum hints, so passing undefined gives a free-form string field.

  return {
    tool: {
      task: createBackgroundTask(manager, ctx.client),
      background_output: createBackgroundOutput(manager, ctx.client),
      background_cancel: createBackgroundCancel(manager, ctx.client),
    },
  }
}

export default BackgroundTaskPlugin
