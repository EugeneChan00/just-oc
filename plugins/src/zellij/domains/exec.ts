import { execZellij, sanitize } from "../exec"
import type { Params } from "../types"
import { existsSync, readFileSync, writeFileSync, mkdirSync, unlinkSync, rmSync, constants } from "node:fs"
import { open as openAsync } from "node:fs/promises"
import { execFileSync } from "node:child_process"
import { randomBytes } from "node:crypto"

const DEFAULT_TIMEOUT_MS = 30_000
const BRIDGE_BASE = "/tmp/zellij-bridge"

function bridgeDir(session: string): string {
  return `${BRIDGE_BASE}-${session}`
}

function resolveSession(params: Params): string {
  return sanitize(params.session) || "default"
}

async function navigateToTarget(params: Params): Promise<void> {
  if (params.session) {
    await execZellij(`action switch-session ${sanitize(params.session)}`)
  }
  if (params.tab) {
    const tab = String(params.tab)
    const isIndex = /^\d+$/.test(tab)
    if (isIndex) {
      await execZellij(`action go-to-tab ${tab}`)
    } else {
      await execZellij(`action go-to-tab-name "${sanitize(tab)}"`)
    }
  }
  if (params.pane) {
    await execZellij(`action move-focus ${sanitize(params.pane)}`)
  }
}

/**
 * Clean up a bridge — close pane by ID, kill listener, remove directory.
 * Safe to call even if the directory doesn't exist or components are missing.
 */
function cleanupBridge(dir: string): void {
  // Close the bridge pane if we know its ID
  try {
    const paneId = readFileSync(`${dir}/pane.id`, "utf-8").trim()
    if (/^terminal_\d+$/.test(paneId)) {
      execFileSync("zellij", ["action", "close-pane", "--pane-id", paneId],
        { stdio: "pipe", timeout: 3000 })
    }
  } catch {} // pane.id may not exist or pane already closed

  // Kill listener process if still running
  try {
    const pid = readFileSync(`${dir}/listener.pid`, "utf-8").trim()
    if (/^\d+$/.test(pid)) {
      process.kill(Number(pid), "SIGTERM")
    }
  } catch {} // PID file may not exist or process already dead

  // Remove bridge directory
  try { rmSync(dir, { recursive: true, force: true }) } catch {}
}

/**
 * Write data to a FIFO with O_NONBLOCK + retry.
 * Returns once data is written. Throws on timeout (no reader available).
 */
async function writeToFifo(pipePath: string, data: string, timeoutMs = 5000): Promise<void> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    try {
      const fh = await openAsync(pipePath, constants.O_WRONLY | constants.O_NONBLOCK)
      try { await fh.write(data) } finally { await fh.close() }
      return
    } catch (e: any) {
      if (e.code === "ENXIO" || e.code === "ENOENT") {
        // ENXIO = no reader yet; ENOENT = file not created yet
        await new Promise(r => setTimeout(r, 50))
        continue
      }
      throw e
    }
  }
  throw new Error(`FIFO write timed out after ${timeoutMs}ms — no reader on ${pipePath}`)
}

function waitForResult(resultDir: string, requestId: string, timeoutMs: number): Promise<string> {
  const resultPath = `${resultDir}/${requestId}.json`

  // Race condition guard: result may already exist
  if (existsSync(resultPath)) {
    const content = readFileSync(resultPath, "utf-8")
    unlinkSync(resultPath)
    return Promise.resolve(content)
  }

  return new Promise((resolve, reject) => {
    const poll = setInterval(() => {
      if (existsSync(resultPath)) {
        clearInterval(poll)
        try {
          const content = readFileSync(resultPath, "utf-8")
          unlinkSync(resultPath)
          resolve(content)
        } catch (e) {
          reject(new Error(`Failed to read result: ${e}`))
        }
      }
    }, 25)

    setTimeout(() => {
      clearInterval(poll)
      reject(new Error(`Command timed out after ${timeoutMs}ms`))
    }, timeoutMs)
  })
}

const LISTENER_SCRIPT = `#!/usr/bin/env bash
BRIDGE_DIR="$1"
CMD_PIPE="\${BRIDGE_DIR}/cmd.pipe"
RESULT_DIR="\${BRIDGE_DIR}/results"

# Open FIFO first — PID file signals "ready" to parent
exec 3<> "\$CMD_PIPE"

echo "$$" > "\${BRIDGE_DIR}/listener.pid"

# Fallback pane ID from zellij env var (in case new-pane stdout didn't return it)
[ -n "\$ZELLIJ_PANE_ID" ] && [ ! -f "\${BRIDGE_DIR}/pane.id" ] && echo "terminal_\$ZELLIJ_PANE_ID" > "\${BRIDGE_DIR}/pane.id"

trap 'exec 3<&-; echo "[shell-bridge] Stopped"' EXIT TERM INT

echo "[shell-bridge] Listener active (pid $$)"
echo "[shell-bridge] Pipe: \${CMD_PIPE}"

while IFS= read -r request <&3; do
  [ -z "\$request" ] && continue

  request_id=\$(echo "\$request" | jq -r '.request_id // empty')
  command=\$(echo "\$request" | jq -r '.command // empty')

  [ -z "\$request_id" ] || [ -z "\$command" ] && continue
  [ "\$command" = "__shutdown__" ] && break

  echo -e "\\n[bridge:\${request_id}] \\$ \${command}\\n---"

  start_ns=\$(date +%s%N)
  stdout_f=\$(mktemp); stderr_f=\$(mktemp)

  set +e
  # Override exit builtin to prevent terminating the listener
  exit() { return "\${1:-0}"; }
  eval "\$command" >"\$stdout_f" 2>"\$stderr_f"
  ec=\$?
  unset -f exit 2>/dev/null
  set -e

  end_ns=\$(date +%s%N)
  duration_ms=\$(( (end_ns - start_ns) / 1000000 ))

  out=\$(cat "\$stdout_f"); err=\$(cat "\$stderr_f")
  rm -f "\$stdout_f" "\$stderr_f"

  [ -n "\$out" ] && echo "\$out"
  [ -n "\$err" ] && echo "[stderr] \$err" >&2
  echo "--- exit:\${ec} (\${duration_ms}ms)"

  tmp=\$(mktemp "\${RESULT_DIR}/.tmp.XXXXXX")
  jq -n --arg rid "\$request_id" --arg out "\$out" --arg err "\$err" \\
    --argjson ec "\$ec" --arg cwd "\$(pwd)" --argjson dur "\$duration_ms" \\
    '{request_id:\$rid, stdout:\$out, stderr:\$err, exit_code:\$ec, cwd:\$cwd, duration_ms:\$dur}' \\
    > "\$tmp"
  mv "\$tmp" "\${RESULT_DIR}/\${request_id}.json"
done
`

export async function handleExec(action: string, params: Params): Promise<string> {
  switch (action) {
    case "start": {
      // Check jq availability
      try {
        execFileSync("which", ["jq"], { stdio: "pipe" })
      } catch {
        return "[ERROR] exec.start requires 'jq' to be installed. Install it with: apt install jq"
      }

      const session = resolveSession(params)
      const dir = bridgeDir(session)
      const resultDir = `${dir}/results`
      const pipePath = `${dir}/cmd.pipe`
      const scriptPath = `${dir}/listener.sh`

      // Check if bridge already exists and is alive
      if (existsSync(`${dir}/listener.pid`)) {
        try {
          const pid = readFileSync(`${dir}/listener.pid`, "utf-8").trim()
          process.kill(Number(pid), 0)
          return `Bridge already running for session "${session}" (pid ${pid}, dir: ${dir})`
        } catch {
          // Stale bridge — fall through to cleanup
        }
      }

      // Clean up any stale bridge (handles crash case where PID file may not exist)
      cleanupBridge(dir)

      // Create bridge directory structure
      mkdirSync(resultDir, { recursive: true })

      // Create named pipe
      execFileSync("mkfifo", [pipePath])

      // Write listener script
      writeFileSync(scriptPath, LISTENER_SCRIPT, { mode: 0o755 })

      // Navigate to target pane if specified
      await navigateToTarget(params)

      // Launch listener or direct command
      const direction = sanitize(params.direction) || "down"
      const closeOnExit = params.closeOnExit === true
      const command = params.command ? String(params.command) : null

      if (closeOnExit && command) {
        // Direct command mode: run single command in new pane, close on exit
        let cmd = `action new-pane --close-on-exit --direction ${direction}`
        if (params.cwd) cmd += ` --cwd "${sanitize(params.cwd)}"`
        cmd += ` -- ${command}`
        await execZellij(cmd)
        return `Command executed in new pane with close-on-exit: ${command}`
      } else if (params.target_pane_id) {
        // Inject into existing pane by ID — no focus-guessing
        const paneId = sanitize(params.target_pane_id)
        if (!/^terminal_\d+$/.test(paneId)) {
          return `[ERROR] Invalid pane ID format: "${paneId}". Expected terminal_N.`
        }
        let launchCmd = `bash "${scriptPath}" "${dir}"`
        if (params.cwd) launchCmd = `cd "${sanitize(params.cwd)}" && ${launchCmd}`
        await execZellij(`action write-chars --pane-id ${paneId} "${launchCmd}"`)
        await execZellij(`action write --pane-id ${paneId} 10`) // send Enter
        writeFileSync(`${dir}/pane.id`, paneId)
      } else {
        // New pane mode (default)
        let cmd = `action new-pane --direction ${direction}`
        if (params.cwd) cmd += ` --cwd "${sanitize(params.cwd)}"`
        cmd += ` -- bash "${scriptPath}" "${dir}"`
        const paneId = (await execZellij(cmd)).trim()
        if (paneId) writeFileSync(`${dir}/pane.id`, paneId)
      }

      // Wait for PID file to appear (signals listener is ready + FIFO is open)
      const deadline = Date.now() + 5000
      while (!existsSync(`${dir}/listener.pid`) && Date.now() < deadline) {
        await new Promise(r => setTimeout(r, 100))
      }

      if (!existsSync(`${dir}/listener.pid`)) {
        return `[ERROR] Bridge listener failed to start (no PID file after 5s). Dir: ${dir}`
      }

      const pid = readFileSync(`${dir}/listener.pid`, "utf-8").trim()
      const paneIdFile = existsSync(`${dir}/pane.id`) ? readFileSync(`${dir}/pane.id`, "utf-8").trim() : "unknown"
      return `Bridge started for session "${session}" (pid ${pid}, pane ${paneIdFile}, dir: ${dir})`
    }

    case "run": {
      const command = String(params.command ?? "")
      if (!command) return "[ERROR] exec.run requires params.command"

      const session = resolveSession(params)
      const dir = bridgeDir(session)
      const pipePath = `${dir}/cmd.pipe`
      const resultDir = `${dir}/results`

      // Verify bridge is alive
      if (!existsSync(`${dir}/listener.pid`)) {
        return `[ERROR] No bridge running for session "${session}". Call exec.start first.`
      }

      try {
        const pid = readFileSync(`${dir}/listener.pid`, "utf-8").trim()
        process.kill(Number(pid), 0)
      } catch {
        return `[ERROR] Bridge listener is dead for session "${session}". Call exec.start to restart.`
      }

      const timeoutMs = Number(params.timeout_ms) || DEFAULT_TIMEOUT_MS
      const requestId = `${Date.now()}-${randomBytes(4).toString("hex")}`

      // Write command to named pipe (async, non-blocking)
      const request = JSON.stringify({ request_id: requestId, command }) + "\n"
      await writeToFifo(pipePath, request)

      // Wait for result
      try {
        const result = await waitForResult(resultDir, requestId, timeoutMs)
        return result
      } catch (e) {
        return `[ERROR] ${e instanceof Error ? e.message : String(e)}`
      }
    }

    case "status": {
      const session = resolveSession(params)
      const dir = bridgeDir(session)

      if (!existsSync(dir)) {
        return `No bridge found for session "${session}"`
      }

      if (!existsSync(`${dir}/listener.pid`)) {
        return `Bridge directory exists but no PID file for session "${session}"`
      }

      const pid = readFileSync(`${dir}/listener.pid`, "utf-8").trim()
      try {
        process.kill(Number(pid), 0)
      } catch {
        return `Bridge dead for session "${session}" (stale pid ${pid})`
      }

      // Check pane health if we have a pane ID
      const paneIdPath = `${dir}/pane.id`
      if (existsSync(paneIdPath)) {
        const paneId = readFileSync(paneIdPath, "utf-8").trim()
        try {
          const screen = await execZellij(`action dump-screen --pane-id ${paneId}`)
          const lastLines = screen.split("\n").filter((l: string) => l.trim()).slice(-5).join("\n")
          return `Bridge alive for session "${session}" (pid ${pid}, pane ${paneId}, dir: ${dir})\nRecent output:\n${lastLines}`
        } catch {
          return `Bridge PID alive but pane ${paneId} not found for session "${session}". Restart needed.`
        }
      }

      return `Bridge alive for session "${session}" (pid ${pid}, dir: ${dir})`
    }

    case "stop": {
      const session = resolveSession(params)
      const dir = bridgeDir(session)
      const pipePath = `${dir}/cmd.pipe`

      if (!existsSync(dir)) {
        return `No bridge found for session "${session}"`
      }

      // Send shutdown command via FIFO
      if (existsSync(pipePath)) {
        try {
          const shutdownCmd = JSON.stringify({ request_id: "shutdown", command: "__shutdown__" }) + "\n"
          await writeToFifo(pipePath, shutdownCmd, 2000)
        } catch {
          // Pipe may be broken or no reader — proceed to force cleanup
        }
      }

      // Wait briefly for graceful exit
      await new Promise(r => setTimeout(r, 500))

      // Force cleanup — closes pane, kills process, removes dir
      cleanupBridge(dir)
      return `Bridge stopped and cleaned up for session "${session}"`
    }

    default:
      return `[ERROR] Unknown exec action: "${action}". Valid: start, run, status, stop`
  }
}
