import { execZellij, sanitize } from "../exec"
import type { Params } from "../types"
import { cache } from "../utils/cache"
import { Validator } from "../utils/validator"

export async function handleSession(action: string, params: Params): Promise<string> {
  switch (action) {
    case "list": {
      const cached = cache.get<string>("sessions_list")
      if (cached) return cached
      const result = await execZellij("list-sessions")
      const output = result || "No active sessions found."
      cache.set("sessions_list", output, 5000)
      return output
    }

    case "new": {
      const v = Validator.validateSessionName(String(params.name ?? ""))
      if (!v.valid) return `[ERROR] session.new: ${v.errors.join(", ")}`
      let cmd = `--session ${v.sanitized}`
      if (params.layout) cmd += ` --layout ${sanitize(params.layout)}`
      cache.delete("sessions_list")
      return execZellij(cmd)
    }

    case "attach": {
      const v = Validator.validateSessionName(String(params.session_name ?? ""))
      if (!v.valid) return `[ERROR] session.attach: ${v.errors.join(", ")}`
      return execZellij(`attach ${v.sanitized}`)
    }

    case "kill": {
      const v = Validator.validateSessionName(String(params.session_name ?? ""))
      if (!v.valid) return `[ERROR] session.kill: ${v.errors.join(", ")}`
      cache.delete("sessions_list")
      cache.delete(`session_info_${v.sanitized}`)
      return execZellij(`kill-session ${v.sanitized}`)
    }

    case "delete": {
      const v = Validator.validateSessionName(String(params.session_name ?? ""))
      if (!v.valid) return `[ERROR] session.delete: ${v.errors.join(", ")}`
      cache.delete("sessions_list")
      cache.delete(`session_info_${v.sanitized}`)
      return execZellij(`delete-session ${v.sanitized}`)
    }

    case "rename": {
      const vOld = Validator.validateSessionName(String(params.old_name ?? ""))
      const vNew = Validator.validateSessionName(String(params.new_name ?? ""))
      if (!vOld.valid) return `[ERROR] session.rename: old_name — ${vOld.errors.join(", ")}`
      if (!vNew.valid) return `[ERROR] session.rename: new_name — ${vNew.errors.join(", ")}`
      cache.delete("sessions_list")
      cache.delete(`session_info_${vOld.sanitized}`)
      return execZellij(`--session ${vOld.sanitized} action rename-session ${vNew.sanitized}`)
    }

    case "switch": {
      const v = Validator.validateSessionName(String(params.session_name ?? ""))
      if (!v.valid) return `[ERROR] session.switch: ${v.errors.join(", ")}`
      return execZellij(`action switch-session ${v.sanitized}`)
    }

    case "info": {
      const v = Validator.validateSessionName(String(params.session_name ?? ""))
      if (!v.valid) return `[ERROR] session.info: ${v.errors.join(", ")}`
      const cacheKey = `session_info_${v.sanitized}`
      const cached = cache.get<string>(cacheKey)
      if (cached) return cached

      const sessionsList = await execZellij("list-sessions")
      let info = `Session Information: ${v.sanitized}\n\n`
      if (sessionsList.includes(v.sanitized!)) {
        info += "Status: Active\n"
        try {
          await execZellij(`--session ${v.sanitized} action dump-layout`)
          info += "Layout available: Yes\n"
        } catch {
          info += "Layout available: No (session may not be current session)\n"
        }
      } else {
        info += "Status: Not found or inactive\n"
      }
      cache.set(cacheKey, info, 10000)
      return info
    }

    case "clone": {
      const vSrc = Validator.validateSessionName(String(params.source_session ?? ""))
      const vNew = Validator.validateSessionName(String(params.new_session_name ?? ""))
      if (!vSrc.valid) return `[ERROR] session.clone: source_session — ${vSrc.errors.join(", ")}`
      if (!vNew.valid) return `[ERROR] session.clone: new_session_name — ${vNew.errors.join(", ")}`
      const layout = await execZellij(`--session ${vSrc.sanitized} action dump-layout`)
      const { writeFileSync, unlinkSync } = await import("node:fs")
      const tempPath = `/tmp/zellij-clone-${Date.now()}.kdl`
      writeFileSync(tempPath, layout)
      try {
        await execZellij(`--session ${vNew.sanitized} --layout ${tempPath}`)
      } finally {
        try { unlinkSync(tempPath) } catch {}
      }
      cache.delete("sessions_list")
      return `Session cloned: ${vSrc.sanitized} → ${vNew.sanitized}`
    }

    case "export": {
      const v = Validator.validateSessionName(String(params.session_name ?? ""))
      if (!v.valid) return `[ERROR] session.export: ${v.errors.join(", ")}`
      const layout = await execZellij(`--session ${v.sanitized} action dump-layout`)
      if (params.output_path) {
        const pv = Validator.validatePath(String(params.output_path))
        if (!pv.valid) return `[ERROR] session.export: output_path — ${pv.errors.join(", ")}`
        const { writeFileSync } = await import("node:fs")
        const exportData = JSON.stringify({ name: v.sanitized, layout, created: new Date().toISOString(), metadata: { exportedBy: "zellij-opencode-plugin", version: "1.0.0" } }, null, 2)
        writeFileSync(pv.sanitized!, exportData)
        return `Session exported to ${pv.sanitized}`
      }
      return layout
    }

    case "import": {
      const pv = Validator.validatePath(String(params.import_path ?? ""))
      if (!pv.valid) return `[ERROR] session.import: import_path — ${pv.errors.join(", ")}`
      const { existsSync, readFileSync, writeFileSync, unlinkSync } = await import("node:fs")
      if (!existsSync(pv.sanitized!)) return `[ERROR] Import file does not exist: ${pv.sanitized}`
      const raw = readFileSync(pv.sanitized!, "utf-8")
      let layoutContent: string
      try {
        const data = JSON.parse(raw)
        layoutContent = typeof data.layout === "string" ? data.layout : convertJsonToKdl(data.layout)
      } catch {
        layoutContent = raw
      }
      let cmd = ""
      if (params.new_session_name) {
        const sv = Validator.validateSessionName(String(params.new_session_name))
        if (!sv.valid) return `[ERROR] session.import: new_session_name — ${sv.errors.join(", ")}`
        cmd += `--session ${sv.sanitized} `
      }
      const tempPath = `/tmp/zellij-import-${Date.now()}.kdl`
      writeFileSync(tempPath, layoutContent)
      try {
        await execZellij(`${cmd}--layout ${tempPath}`)
      } finally {
        try { unlinkSync(tempPath) } catch {}
      }
      cache.delete("sessions_list")
      return `Session imported from ${pv.sanitized}`
    }

    case "kill_all":
      cache.clear()
      return execZellij("kill-all-sessions --yes")

    case "delete_all":
      cache.clear()
      return execZellij("delete-all-sessions --yes")

    default:
      return `[ERROR] Unknown session action: "${action}". Valid: list, new, attach, kill, delete, rename, switch, info, clone, export, import, kill_all, delete_all`
  }
}

function convertJsonToKdl(layout: Record<string, unknown>): string {
  let kdl = "layout {\n"
  const tabs = layout.tabs
  if (Array.isArray(tabs)) {
    for (const tab of tabs) {
      kdl += "  tab {\n"
      if (tab.name) kdl += `    name "${tab.name}"\n`
      if (Array.isArray(tab.panes)) {
        for (const _pane of tab.panes) kdl += "    pane\n"
      } else {
        kdl += "    pane\n"
      }
      kdl += "  }\n"
    }
  } else {
    kdl += "  tab {\n    pane\n  }\n"
  }
  kdl += "}\n"
  return kdl
}
