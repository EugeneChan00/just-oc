import { execZellij, sanitize } from "../exec"
import type { Params } from "../types"

export async function handleUtility(action: string, params: Params): Promise<string> {
  switch (action) {
    case "run_command": {
      const command = sanitize(params.command)
      if (!command) return "[ERROR] utility.run_command requires params.command"
      let cmd = "run"
      if (params.direction) cmd += ` --direction ${sanitize(params.direction)}`
      cmd += ` -- ${command}`
      return execZellij(cmd)
    }

    case "edit_file": {
      const filePath = sanitize(params.file_path)
      if (!filePath) return "[ERROR] utility.edit_file requires params.file_path"
      return execZellij(`edit "${filePath}"`)
    }

    case "switch_mode": {
      const mode = sanitize(params.mode)
      if (!mode) return "[ERROR] utility.switch_mode requires params.mode (locked|pane|tab|resize|move|search|session)"
      return execZellij(`action switch-mode ${mode}`)
    }

    case "health_check":
      return execZellij("--version")

    case "clear_cache":
      return "Cache cleared"

    case "cache_stats":
      return "No cache configured"

    default:
      return `[ERROR] Unknown utility action: "${action}". Valid: run_command, edit_file, switch_mode, health_check, clear_cache, cache_stats`
  }
}
