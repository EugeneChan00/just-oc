import type { Params } from "../types"
import { Validator } from "../utils/validator"

const watchers = new Map<string, boolean>()
const processes = new Map<string, unknown>()

export async function handleDetection(action: string, params: Params): Promise<string> {
  switch (action) {
    case "watch_pipe": {
      const pv = Validator.validatePath(String(params.pipe_path ?? ""))
      if (!pv.valid) return `[ERROR] detection.watch_pipe: pipe_path — ${pv.errors.join(", ")}`
      const timeout = Number(params.timeout_ms) || 30000
      if (timeout < 100 || timeout > 300000) return "[ERROR] detection.watch_pipe: timeout_ms must be between 100 and 300000"

      const { existsSync, createReadStream } = await import("node:fs")
      if (!existsSync(pv.sanitized!)) return `[ERROR] Pipe does not exist: ${pv.sanitized}`

      const patterns: string[] = []
      if (params.patterns) {
        const raw = Array.isArray(params.patterns) ? params.patterns : [String(params.patterns)]
        for (const p of raw) {
          const v = Validator.validateString(String(p), "pattern", 256)
          if (!v.valid) return `[ERROR] detection.watch_pipe: pattern — ${v.errors.join(", ")}`
          patterns.push(v.sanitized!)
        }
      }

      return new Promise((resolve) => {
        const timer = setTimeout(() => {
          resolve(`Pipe watch timeout after ${timeout}ms. No matching patterns found.`)
        }, timeout)

        let buffer = ""
        const stream = createReadStream(pv.sanitized!)
        watchers.set(pv.sanitized!, true)

        stream.on("data", (chunk: Buffer) => {
          buffer += chunk.toString()
          if (patterns.length > 0) {
            for (const pattern of patterns) {
              if (buffer.includes(pattern)) {
                clearTimeout(timer)
                watchers.delete(pv.sanitized!)
                resolve(`Pattern found: "${pattern}" in pipe ${pv.sanitized}`)
                stream.destroy()
                return
              }
            }
          }
        })

        stream.on("end", () => {
          clearTimeout(timer)
          watchers.delete(pv.sanitized!)
          resolve(`EOF reached on pipe ${pv.sanitized}. ${patterns.length > 0 ? "No patterns matched." : ""}`)
        })

        stream.on("error", (err) => {
          clearTimeout(timer)
          watchers.delete(pv.sanitized!)
          resolve(`[ERROR] Error reading pipe: ${err.message}`)
        })
      })
    }

    case "create_named_pipe": {
      const nv = Validator.validateString(String(params.pipe_name ?? ""), "pipe name", 64)
      if (!nv.valid) return `[ERROR] detection.create_named_pipe: ${nv.errors.join(", ")}`
      const mode = String(params.mode ?? "0666")
      if (!/^0[0-7]{3}$/.test(mode)) return '[ERROR] detection.create_named_pipe: mode must be in octal format (e.g., "0666")'
      const pipePath = `/tmp/zellij-pipe-${nv.sanitized}`
      const { execSync } = await import("node:child_process")
      execSync(`mkfifo -m ${mode} "${pipePath}" 2>/dev/null || true`)
      return `Named pipe created at ${pipePath}`
    }

    case "pipe_with_timeout": {
      const cv = Validator.validateCommand(String(params.command ?? ""))
      const pv = Validator.validatePath(String(params.target_pipe ?? ""))
      if (!cv.valid) return `[ERROR] detection.pipe_with_timeout: command — ${cv.errors.join(", ")}`
      if (!pv.valid) return `[ERROR] detection.pipe_with_timeout: target_pipe — ${pv.errors.join(", ")}`
      const timeout = Number(params.timeout_ms) || 30000
      if (timeout < 1000 || timeout > 600000) return "[ERROR] detection.pipe_with_timeout: timeout_ms must be between 1000 and 600000"

      const { spawn } = await import("node:child_process")
      const processId = `pipe-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`

      return new Promise((resolve) => {
        let completed = false
        const timer = setTimeout(() => {
          if (!completed) {
            completed = true
            const proc = processes.get(processId)
            if (proc) {
              proc.kill("SIGTERM")
              processes.delete(processId)
            }
            resolve(`Command piped with timeout completion after ${timeout}ms: ${cv.sanitized}`)
          }
        }, timeout)

        const proc = spawn("bash", ["-c", `${cv.sanitized} > "${pv.sanitized}"`], { stdio: ["ignore", "pipe", "pipe"] })
        processes.set(processId, proc)

        proc.on("exit", (code) => {
          if (!completed) {
            completed = true
            clearTimeout(timer)
            processes.delete(processId)
            resolve(`Command completed with exit code ${code}: ${cv.sanitized}`)
          }
        })

        proc.on("error", (err) => {
          if (!completed) {
            completed = true
            clearTimeout(timer)
            processes.delete(processId)
            resolve(`[ERROR] Command error: ${err.message}`)
          }
        })
      })
    }

    case "poll_process": {
      const pid = String(params.pid ?? "")
      const pidNum = parseInt(pid)
      if (isNaN(pidNum) || pidNum <= 0 || pidNum > 4194304) return "[ERROR] detection.poll_process: pid must be a positive integer"
      const { execSync } = await import("node:child_process")
      try {
        const result = execSync(`ps -p ${pidNum} -o pid,ppid,state,comm --no-headers 2>/dev/null`, { encoding: "utf-8" }).trim()
        if (result) {
          return `Process ${pidNum} status:\n${result}`
        }
        return `Process ${pidNum} is not running`
      } catch {
        return `Process ${pidNum} is not running`
      }
    }

    case "watch_file": {
      const pv = Validator.validatePath(String(params.file_path ?? ""))
      if (!pv.valid) return `[ERROR] detection.watch_file: file_path — ${pv.errors.join(", ")}`
      const timeout = Number(params.timeout_ms) || 30000
      if (timeout < 100 || timeout > 300000) return "[ERROR] detection.watch_file: timeout_ms must be between 100 and 300000"

      const patterns: string[] = []
      if (params.patterns) {
        const raw = Array.isArray(params.patterns) ? params.patterns : [String(params.patterns)]
        for (const p of raw) {
          const v = Validator.validateString(String(p), "pattern", 256)
          if (!v.valid) return `[ERROR] detection.watch_file: pattern — ${v.errors.join(", ")}`
          patterns.push(v.sanitized!)
        }
      }

      const { readFileSync, existsSync, watchFile, unwatchFile } = await import("node:fs")

      return new Promise((resolve) => {
        const timer = setTimeout(() => {
          unwatchFile(pv.sanitized!)
          watchers.delete(pv.sanitized!)
          resolve(`File watch timeout after ${timeout}ms: ${pv.sanitized}`)
        }, timeout)

        const checkFile = () => {
          try {
            if (!existsSync(pv.sanitized!)) return
            const content = readFileSync(pv.sanitized!, "utf-8")
            if (patterns.length > 0) {
              for (const pattern of patterns) {
                if (content.includes(pattern)) {
                  clearTimeout(timer)
                  unwatchFile(pv.sanitized!)
                  watchers.delete(pv.sanitized!)
                  resolve(`Pattern "${pattern}" found in file: ${pv.sanitized}`)
                  return
                }
              }
            } else {
              clearTimeout(timer)
              unwatchFile(pv.sanitized!)
              watchers.delete(pv.sanitized!)
              resolve(`File detected: ${pv.sanitized}\n\n${content}`)
            }
          } catch {}
        }

        checkFile()
        watchFile(pv.sanitized!, (_curr, _prev) => checkFile())
        watchers.set(pv.sanitized!, true)
      })
    }

    case "create_llm_wrapper": {
      const nv = Validator.validateString(String(params.wrapper_name ?? ""), "wrapper name", 32)
      const cv = Validator.validateCommand(String(params.llm_command ?? ""))
      if (!nv.valid) return `[ERROR] detection.create_llm_wrapper: wrapper_name — ${nv.errors.join(", ")}`
      if (!cv.valid) return `[ERROR] detection.create_llm_wrapper: llm_command — ${cv.errors.join(", ")}`
      const marker = String(params.detect_marker ?? "<<<LLM_COMPLETE>>>")
      const timeout = Number(params.timeout_ms) || 60000

      const wrapperPath = `/tmp/llm-wrapper-${nv.sanitized}.sh`
      const statusPath = `/tmp/llm-status-${nv.sanitized}`
      const { writeFileSync, chmodSync } = await import("node:fs")

      const script = `#!/bin/bash
# LLM Completion Detection Wrapper
# Generated by Zellij OpenCode Plugin

set -euo pipefail

WRAPPER_NAME="${nv.sanitized}"
STATUS_FILE="${statusPath}"
OUTPUT_FILE="/tmp/llm-output-$WRAPPER_NAME-$$"
MARKER="${marker}"
TIMEOUT_MS="${timeout}"
LLM_PID=""

cleanup() {
    if [[ -n "$LLM_PID" ]] && kill -0 "$LLM_PID" 2>/dev/null; then
        kill "$LLM_PID" 2>/dev/null || true
        wait "$LLM_PID" 2>/dev/null || true
    fi
    [[ -f "$OUTPUT_FILE" ]] && rm -f "$OUTPUT_FILE"
}

trap cleanup EXIT INT TERM

echo "running" > "$STATUS_FILE"
echo "$(date -Iseconds): Starting LLM query" >> "$STATUS_FILE"

{
    timeout $((TIMEOUT_MS / 1000))s ${cv.sanitized} "$@" || {
        EXIT_CODE=$?
        if [[ $EXIT_CODE -eq 124 ]]; then
            echo "timeout" >> "$STATUS_FILE"
            echo "$(date -Iseconds): LLM query timed out" >> "$STATUS_FILE"
        else
            echo "error:$EXIT_CODE" >> "$STATUS_FILE"
            echo "$(date -Iseconds): LLM query failed with code $EXIT_CODE" >> "$STATUS_FILE"
        fi
        exit $EXIT_CODE
    }
    echo "$MARKER:$?"
} | tee "$OUTPUT_FILE" &

LLM_PID=$!
wait "$LLM_PID"
LLM_EXIT_CODE=$?

if [[ $LLM_EXIT_CODE -eq 0 ]]; then
    echo "complete:$LLM_EXIT_CODE" > "$STATUS_FILE"
    echo "$(date -Iseconds): LLM query completed successfully" >> "$STATUS_FILE"
else
    echo "error:$LLM_EXIT_CODE" > "$STATUS_FILE"
    echo "$(date -Iseconds): LLM query failed with code $LLM_EXIT_CODE" >> "$STATUS_FILE"
fi

cat "$OUTPUT_FILE"
exit $LLM_EXIT_CODE
`
      writeFileSync(wrapperPath, script, { mode: 0o755 })
      chmodSync(wrapperPath, "755")

      return `LLM wrapper created: ${wrapperPath}\nStatus file: ${statusPath}\nDetection marker: ${marker}\nTimeout: ${timeout}ms\n\nUsage: ${wrapperPath} [your-llm-args...]\n\nThe wrapper provides:\n- Multi-signal completion detection (exit code + marker + status file)\n- Automatic timeout handling\n- Process monitoring and cleanup\n- Timestamped status logging`
    }

    case "cleanup": {
      let cleaned = 0
      for (const [path] of watchers) {
        try {
          const { unwatchFile } = await import("node:fs")
          unwatchFile(path)
        } catch {}
        cleaned++
      }
      watchers.clear()

      for (const [_id, proc] of processes) {
        try { (proc as any).kill("SIGTERM") } catch {}
        cleaned++
      }
      processes.clear()

      const { execSync } = await import("node:child_process")
      try {
        execSync('rm -f /tmp/zellij-pipe-* /tmp/llm-wrapper-* /tmp/llm-status-* /tmp/llm-output-* 2>/dev/null || true')
      } catch {}

      return `Detection cleanup completed. Stopped ${cleaned} watchers/processes and cleaned temporary files.`
    }

    default:
      return `[ERROR] Unknown detection action: "${action}". Valid: watch_pipe, create_named_pipe, pipe_with_timeout, poll_process, watch_file, create_llm_wrapper, cleanup`
  }
}
