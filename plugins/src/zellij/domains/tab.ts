import { execZellij, sanitize } from "../exec"
import type { Params } from "../types"
import { Validator } from "../utils/validator"

export async function handleTab(action: string, params: Params): Promise<string> {
  switch (action) {
    case "new": {
      let cmd = "action new-tab"
      if (params.name) {
        const v = Validator.validateString(String(params.name), "tab name", 64)
        if (!v.valid) return `[ERROR] tab.new: name — ${v.errors.join(", ")}`
        cmd += ` --name "${v.sanitized}"`
      }
      if (params.layout) cmd += ` --layout ${sanitize(params.layout)}`
      return execZellij(cmd)
    }

    case "close":
      return execZellij("action close-tab")

    case "rename": {
      const v = Validator.validateString(String(params.name ?? ""), "tab name", 64)
      if (!v.valid) return `[ERROR] tab.rename: ${v.errors.join(", ")}`
      return execZellij(`action rename-tab "${v.sanitized}"`)
    }

    case "undo_rename":
      return execZellij("action undo-rename-tab")

    case "go_to": {
      const index = params.index != null ? Number(params.index) : undefined
      if (index == null || isNaN(index)) return "[ERROR] tab.go_to requires params.index (number)"
      return execZellij(`action go-to-tab ${index}`)
    }

    case "go_to_name": {
      const v = Validator.validateString(String(params.name ?? ""), "tab name", 64)
      if (!v.valid) return `[ERROR] tab.go_to_name: ${v.errors.join(", ")}`
      return execZellij(`action go-to-tab-name "${v.sanitized}"`)
    }

    case "move": {
      const dir = String(params.direction ?? "").toLowerCase()
      if (!["left", "right"].includes(dir)) return '[ERROR] tab.move: direction must be "left" or "right"'
      return execZellij(`action move-tab ${dir}`)
    }

    case "query_names":
      return execZellij("action query-tab-names")

    case "toggle_sync":
      return execZellij("action toggle-active-sync-tab")

    case "next":
      return execZellij("action go-to-next-tab")

    case "previous":
      return execZellij("action go-to-previous-tab")

    default:
      return `[ERROR] Unknown tab action: "${action}". Valid: new, close, rename, undo_rename, go_to, go_to_name, move, query_names, toggle_sync, next, previous`
  }
}
