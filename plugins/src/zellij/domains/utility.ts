import { execZellij } from "../exec"
import type { Params } from "../types"
import { cache } from "../utils/cache"
import { Validator } from "../utils/validator"

type PaneInfo = { id?: string; type: string; name?: string; command?: string; focused?: boolean; plugin?: string }
type TabInfo = { name: string; focused: boolean; panes: PaneInfo[] }

/**
 * Parse the actual tab/pane tree from a dump-layout KDL string.
 * Extracts only real tab blocks, skips swap layouts and templates.
 */
function parseLayout(kdl: string): TabInfo[] {
  const tabs: TabInfo[] = []
  const lines = kdl.split("\n")
  let inTab = false
  let inFloating = false
  let depth = 0
  let tabDepth = 0
  let currentTab: TabInfo | null = null

  for (let idx = 0; idx < lines.length; idx++) {
    const trimmed = lines[idx].trim()

    // Stop at swap layouts or new_tab_template — these are just templates, not real state
    if (trimmed.startsWith("swap_") || trimmed.startsWith("new_tab_template")) break

    // Detect tab blocks
    if (trimmed.startsWith("tab ") && !inTab) {
      const nameMatch = trimmed.match(/name="([^"]*)"/)
      currentTab = { name: nameMatch?.[1] ?? "unnamed", focused: trimmed.includes("focus=true"), panes: [] }
      tabs.push(currentTab)
      inTab = true
      tabDepth = depth
      inFloating = false
    }

    if (trimmed.startsWith("floating_panes")) inFloating = true

    // Detect panes inside tabs
    if (inTab && currentTab && trimmed.startsWith("pane")) {
      const nameMatch = trimmed.match(/name="([^"]*)"/)
      const commandMatch = trimmed.match(/command="([^"]*)"/)
      const focused = trimmed.includes("focus=true")
      const isBorderless = trimmed.includes("borderless=true")
      const hasSize1 = trimmed.includes("size=1")

      // A pane with a { body might contain a plugin or command
      let isPlugin = false
      let pluginName: string | undefined
      let command = commandMatch?.[1]
      if (trimmed.includes("{")) {
        for (let i = idx + 1; i < lines.length; i++) {
          const next = lines[i].trim()
          if (!next) continue
          if (next.startsWith("plugin location=")) {
            isPlugin = true
            pluginName = next.match(/location="([^"]*)"/) ?.[1]
          }
          if (next.startsWith("command ") && !command) {
            command = next.match(/command\s+"([^"]*)"/) ?.[1]
          }
          if (next === "}" || next.startsWith("pane") || next.startsWith("tab")) break
        }
      }

      // Filter: skip UI chrome (borderless size=1 plugins like tab-bar, status-bar)
      const isChrome = isPlugin && isBorderless && hasSize1
      if (!isChrome) {
        if (isPlugin) {
          currentTab.panes.push({ type: "plugin", name: nameMatch?.[1], focused: focused || undefined, plugin: pluginName })
        } else {
          currentTab.panes.push({ type: inFloating ? "floating" : "shell", name: nameMatch?.[1], command, focused: focused || undefined })
        }
      }
    }

    // Track brace depth to detect tab exit
    for (const ch of trimmed) {
      if (ch === "{") depth++
      if (ch === "}") {
        depth--
        if (inTab && depth <= tabDepth) {
          inTab = false
          inFloating = false
          currentTab = null
        }
      }
    }
  }

  return tabs
}

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

    case "snapshot": {
      // One-call mega query: returns all sessions, tabs, and panes with IDs
      const sessionsRaw = await execZellij("list-sessions")
      const sessionLines = sessionsRaw.split("\n").filter(l => l.trim())

      const sessions: Array<{
        name: string
        status: string
        tabs: Array<{
          name: string
          focused: boolean
          panes: PaneInfo[]
        }>
      }> = []

      for (const line of sessionLines) {
        // Parse session name — first word, strip ANSI codes
        const clean = line.replace(/\x1b\[[0-9;]*m/g, "").trim()
        const name = clean.split(/\s/)[0]
        if (!name) continue

        const isExited = clean.includes("EXITED")
        let tabs: ReturnType<typeof parseLayout> = []

        if (!isExited) {
          try {
            const layout = await execZellij(`--session ${name} action dump-layout`)
            tabs = parseLayout(layout)

            // Get connected client pane IDs
            try {
              const clients = await execZellij(`--session ${name} action list-clients`)
              const clientLines = clients.split("\n").filter(l => l.trim() && !l.startsWith("CLIENT_ID"))
              const clientPanes = clientLines.map(l => {
                const parts = l.trim().split(/\s+/)
                return { client_id: parts[0], pane_id: parts[1], command: parts.slice(2).join(" ") }
              }).filter(p => p.pane_id)

              // Attach client info to the focused pane in the focused tab
              if (clientPanes.length > 0) {
                const focusedTab = tabs.find(t => t.focused)
                if (focusedTab) {
                  const focusedPane = focusedTab.panes.find(p => p.focused)
                  if (focusedPane) {
                    focusedPane.id = clientPanes[0].pane_id
                  }
                }
              }
            } catch {
              // list-clients may fail on some sessions
            }
          } catch {
            // Session may not be attachable
          }
        }

        sessions.push({ name, status: isExited ? "EXITED" : "ACTIVE", tabs })
      }

      return JSON.stringify(sessions, null, 2)
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
      return `[ERROR] Unknown utility action: "${action}". Valid: run_command, edit_file, switch_mode, health_check, snapshot, clear_cache, cache_stats`
  }
}
