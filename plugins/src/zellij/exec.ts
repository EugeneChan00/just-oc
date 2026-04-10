import { exec } from "node:child_process"

const TIMEOUT_MS = 30_000
const MAX_BUFFER = 10 * 1024 * 1024 // 10 MB

/**
 * Sanitize a string for safe shell interpolation.
 * Strips characters that could allow injection.
 */
export function sanitize(value: unknown): string {
  return String(value ?? "").replace(/[;&|`$(){}[\]!#]/g, "")
}

/**
 * Execute a zellij CLI command and return stdout.
 */
export function execZellij(command: string): Promise<string> {
  return new Promise((resolve, reject) => {
    exec(`zellij ${command}`, { timeout: TIMEOUT_MS, maxBuffer: MAX_BUFFER }, (error, stdout, stderr) => {
      if (error) {
        reject(new Error(`zellij command failed: ${error.message}\n${stderr}`.trim()))
        return
      }
      resolve(stdout.trim())
    })
  })
}

/**
 * After a mutation (new session/tab/pane), query the focused state and return
 * a structured summary so the agent knows exactly what it just created.
 */
export async function queryFocusedState(sessionName?: string): Promise<string> {
  try {
    const prefix = sessionName ? `--session ${sessionName} ` : ""

    // Get tab names to find focused tab
    const tabNames = await execZellij(`${prefix}action query-tab-names`)
    const tabs = tabNames.split("\n").filter(l => l.trim())

    // Get client pane IDs
    let clients = ""
    try { clients = await execZellij(`${prefix}action list-clients`) } catch {}

    const paneLines = clients.split("\n").filter(l => l.trim() && !l.startsWith("CLIENT_ID"))
    const panes = paneLines.map(l => {
      const parts = l.trim().split(/\s+/)
      return { client_id: parts[0], pane_id: parts[1], command: parts.slice(2).join(" ") }
    })

    // Get layout for focused tab details
    let layout = ""
    try { layout = await execZellij(`${prefix}action dump-layout`) } catch {}

    // Extract focused pane name from layout
    let focusedPaneName: string | undefined
    let focusedPaneCommand: string | undefined
    const layoutLines = layout.split("\n")
    for (let i = 0; i < layoutLines.length; i++) {
      const line = layoutLines[i].trim()
      if (line.startsWith("pane") && line.includes("focus=true") && !line.includes("borderless=true")) {
        focusedPaneName = line.match(/name="([^"]*)"/) ?.[1]
        focusedPaneCommand = line.match(/command="([^"]*)"/) ?.[1]
        break
      }
    }

    const state: Record<string, unknown> = {
      session: sessionName || process.env.ZELLIJ_SESSION_NAME || "(current)",
      tabs,
      focused_pane: {
        id: panes[0]?.pane_id,
        name: focusedPaneName,
        command: focusedPaneCommand,
      },
      all_panes: panes,
    }

    return JSON.stringify(state, null, 2)
  } catch (e) {
    return `(could not query state: ${e instanceof Error ? e.message : String(e)})`
  }
}
