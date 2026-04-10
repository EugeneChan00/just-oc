import { execZellij } from "../exec"
import type { Params } from "../types"
import { Validator } from "../utils/validator"

export async function handlePane(action: string, params: Params): Promise<string> {
  switch (action) {
    case "new": {
      let cmd = "action new-pane"
      if (params.direction) {
        const v = Validator.validateSplitDirection(String(params.direction))
        if (!v.valid) return `[ERROR] pane.new: direction — ${v.errors.join(", ")}`
        cmd += ` --direction ${v.sanitized}`
      }
      if (params.cwd) {
        const v = Validator.validateString(String(params.cwd), "working directory", 512)
        if (!v.valid) return `[ERROR] pane.new: cwd — ${v.errors.join(", ")}`
        cmd += ` --cwd "${v.sanitized}"`
      }
      if (params.command) {
        const v = Validator.validateCommand(String(params.command))
        if (!v.valid) return `[ERROR] pane.new: command — ${v.errors.join(", ")}`
        cmd += ` -- ${v.sanitized}`
      }
      return execZellij(cmd)
    }

    case "close":
      return execZellij("action close-pane")

    case "focus": {
      const v = Validator.validateDirection(String(params.direction ?? ""))
      if (!v.valid) return `[ERROR] pane.focus: ${v.errors.join(", ")}`
      if (v.sanitized === "next") return execZellij("action focus-next-pane")
      if (v.sanitized === "previous") return execZellij("action focus-previous-pane")
      return execZellij(`action move-focus ${v.sanitized}`)
    }

    case "resize": {
      const dv = Validator.validateDirection(String(params.direction ?? ""))
      const av = Validator.validateResizeAmount(String(params.amount ?? ""))
      if (!dv.valid) return `[ERROR] pane.resize: direction — ${dv.errors.join(", ")}`
      if (!av.valid) return `[ERROR] pane.resize: amount — ${av.errors.join(", ")}`
      return execZellij(`action resize ${av.sanitized} ${dv.sanitized}`)
    }

    case "scroll": {
      const dir = String(params.direction ?? "")
      if (!["up", "down"].includes(dir)) return '[ERROR] pane.scroll requires params.direction ("up" or "down")'
      const amount = String(params.amount ?? "line")
      if (!["line", "half-page", "page"].includes(amount)) return '[ERROR] pane.scroll: amount must be "line", "half-page", or "page"'
      if (amount === "half-page") return execZellij(`action half-page-scroll-${dir}`)
      if (amount === "page") return execZellij(`action page-scroll-${dir}`)
      return execZellij(`action scroll-${dir}`)
    }

    case "scroll_to_edge": {
      const edge = String(params.edge ?? "")
      if (!["top", "bottom"].includes(edge)) return '[ERROR] pane.scroll_to_edge requires params.edge ("top" or "bottom")'
      return execZellij(`action scroll-to-${edge}`)
    }

    case "toggle_floating":
      return execZellij("action toggle-floating-panes")

    case "toggle_fullscreen":
      return execZellij("action toggle-fullscreen")

    case "toggle_embed_float":
      return execZellij("action toggle-pane-embed-or-floating")

    case "pin":
      return execZellij("action toggle-pane-pinned")

    case "toggle_frames":
      return execZellij("action toggle-pane-frames")

    case "clear":
      return execZellij("action clear")

    case "dump_screen": {
      if (params.output_path) {
        const v = Validator.validatePath(String(params.output_path))
        if (!v.valid) return `[ERROR] pane.dump_screen: output_path — ${v.errors.join(", ")}`
        return execZellij(`action dump-screen ${v.sanitized}`)
      }
      return execZellij("action dump-screen")
    }

    case "edit_scrollback":
      return execZellij("action edit-scrollback")

    case "rename": {
      const v = Validator.validateString(String(params.name ?? ""), "pane name", 64)
      if (!v.valid) return `[ERROR] pane.rename: ${v.errors.join(", ")}`
      return execZellij(`action rename-pane "${v.sanitized}"`)
    }

    case "undo_rename":
      return execZellij("action undo-rename-pane")

    case "swap": {
      const v = Validator.validateDirection(String(params.direction ?? ""))
      if (!v.valid) return `[ERROR] pane.swap: ${v.errors.join(", ")}`
      return execZellij(`action move-pane ${v.sanitized}`)
    }

    case "stack": {
      const ids = params.pane_ids
      if (!Array.isArray(ids) || ids.length === 0) return "[ERROR] pane.stack requires params.pane_ids (array of pane IDs)"
      const validated: string[] = []
      for (const id of ids) {
        const v = Validator.validatePaneId(String(id))
        if (!v.valid) return `[ERROR] pane.stack: pane ID "${id}" — ${v.errors.join(", ")}`
        validated.push(v.sanitized!)
      }
      return execZellij(`action stack-panes ${validated.join(" ")}`)
    }

    case "exec": {
      const v = Validator.validateCommand(String(params.command ?? ""))
      if (!v.valid) return `[ERROR] pane.exec: ${v.errors.join(", ")}`
      return execZellij(`run -- ${v.sanitized}`)
    }

    case "write": {
      const v = Validator.validateText(String(params.text ?? ""))
      if (!v.valid) return `[ERROR] pane.write: ${v.errors.join(", ")}`
      const escaped = v.sanitized!.replace(/"/g, '\\"')
      let cmd = `action write-chars "${escaped}"`
      if (params.submit) cmd += " && zellij action write 10"
      return execZellij(cmd)
    }

    case "info":
      return execZellij("action dump-layout")

    case "move_focus_or_tab": {
      const valid = ["left", "right", "up", "down"]
      const dir = String(params.direction ?? "").toLowerCase()
      if (!valid.includes(dir)) return `[ERROR] pane.move_focus_or_tab: direction must be one of: ${valid.join(", ")}`
      return execZellij(`action move-focus-or-tab ${dir}`)
    }

    case "change_coordinates": {
      const x = params.x != null ? Number(params.x) : undefined
      const y = params.y != null ? Number(params.y) : undefined
      if (x == null || y == null || isNaN(x) || isNaN(y) || x < 0 || y < 0) return "[ERROR] pane.change_coordinates requires params.x and params.y (non-negative numbers)"
      let cmd = `action change-floating-pane-coordinates --x ${x} --y ${y}`
      if (params.width != null) {
        const w = Number(params.width)
        if (isNaN(w) || w <= 0) return "[ERROR] pane.change_coordinates: width must be a positive number"
        cmd += ` --width ${w}`
      }
      if (params.height != null) {
        const h = Number(params.height)
        if (isNaN(h) || h <= 0) return "[ERROR] pane.change_coordinates: height must be a positive number"
        cmd += ` --height ${h}`
      }
      return execZellij(cmd)
    }

    default:
      return `[ERROR] Unknown pane action: "${action}". Valid: new, close, focus, resize, scroll, scroll_to_edge, toggle_floating, toggle_fullscreen, toggle_embed_float, pin, toggle_frames, clear, dump_screen, edit_scrollback, rename, undo_rename, swap, stack, exec, write, info, move_focus_or_tab, change_coordinates`
  }
}
