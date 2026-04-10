import { execZellij } from "../exec"
import type { Params } from "../types"
import { cache } from "../utils/cache"
import { Validator } from "../utils/validator"

export async function handleUtility(action: string, params: Params): Promise<string> {
  switch (action) {
    case "run_command": {
      const v = Validator.validateCommand(String(params.command ?? ""))
      if (!v.valid) return `[ERROR] utility.run_command: ${v.errors.join(", ")}`
      let cmd = "run"
      if (params.direction) {
        const dv = Validator.validateSplitDirection(String(params.direction))
        if (!dv.valid) return `[ERROR] utility.run_command: direction — ${dv.errors.join(", ")}`
        cmd += ` --direction ${dv.sanitized}`
      }
      cmd += ` -- ${v.sanitized}`
      return execZellij(cmd)
    }

    case "edit_file": {
      const v = Validator.validatePath(String(params.file_path ?? ""))
      if (!v.valid) return `[ERROR] utility.edit_file: ${v.errors.join(", ")}`
      return execZellij(`edit "${v.sanitized}"`)
    }

    case "switch_mode": {
      const mode = String(params.mode ?? "").toLowerCase()
      const valid = ["locked", "pane", "tab", "resize", "move", "search", "session", "normal"]
      if (!valid.includes(mode)) return `[ERROR] utility.switch_mode: mode must be one of: ${valid.join(", ")}`
      return execZellij(`action switch-mode ${mode}`)
    }

    case "health_check":
      return execZellij("--version")

    case "clear_cache": {
      cache.clear()
      return "Cache cleared successfully"
    }

    case "cache_stats": {
      const stats = cache.getStats()
      return `Cache statistics:\n  Entries: ${stats.size}\n  Keys: ${stats.keys.length > 0 ? stats.keys.join(", ") : "(empty)"}`
    }

    default:
      return `[ERROR] Unknown utility action: "${action}". Valid: run_command, edit_file, switch_mode, health_check, clear_cache, cache_stats`
  }
}
