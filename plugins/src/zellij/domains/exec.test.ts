/**
 * Tests for the exec domain (shell bridge).
 *
 * Unit tests: exercise the listener script directly (no Zellij needed).
 * Integration tests: exercise the full exec handler against a live Zellij session.
 *
 * Run: ZELLIJ_SESSION=test-bridge npx tsx plugins/src/zellij/domains/exec.test.ts
 */

import { existsSync, readFileSync, writeFileSync, mkdirSync, unlinkSync } from "node:fs"
import { execSync, spawn } from "node:child_process"

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

let passed = 0
let failed = 0

function assert(condition: boolean, msg: string) {
  if (condition) {
    console.log(`  PASS: ${msg}`)
    passed++
  } else {
    console.error(`  FAIL: ${msg}`)
    failed++
  }
}

function assertEq(actual: unknown, expected: unknown, msg: string) {
  assert(actual === expected, `${msg} (got ${JSON.stringify(actual)}, expected ${JSON.stringify(expected)})`)
}

function sleep(ms: number): Promise<void> {
  return new Promise(r => setTimeout(r, ms))
}

const LISTENER_SCRIPT = `#!/usr/bin/env bash
BRIDGE_DIR="$1"
CMD_PIPE="\${BRIDGE_DIR}/cmd.pipe"
RESULT_DIR="\${BRIDGE_DIR}/results"

echo "$$" > "\${BRIDGE_DIR}/listener.pid"
echo "[shell-bridge] Listener active (pid $$)"

exec 3<> "\$CMD_PIPE"

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

exec 3<&-
echo "[shell-bridge] Stopped"
`

// ---------------------------------------------------------------------------
// Unit Tests — Listener Script (standalone, no Zellij)
// ---------------------------------------------------------------------------

async function unitTests() {
  console.log("\n=== UNIT TESTS: listener script ===\n")

  const dir = "/tmp/zellij-bridge-unittest"

  // Clean slate
  execSync(`rm -rf ${dir}`)
  mkdirSync(`${dir}/results`, { recursive: true })
  execSync(`mkfifo ${dir}/cmd.pipe`)

  // Write listener script — unescape the TypeScript template literal
  const rawScript = LISTENER_SCRIPT
    .replace(/\\\$/g, "$")
    .replace(/\\"/g, '"')
    .replace(/\\\\/g, "\\")
  writeFileSync(`${dir}/listener.sh`, rawScript, { mode: 0o755 })

  // Start listener in background using spawn (non-blocking)
  const proc = spawn("bash", [`${dir}/listener.sh`, dir], {
    stdio: "ignore",
    detached: true,
  })
  proc.unref()
  await sleep(500)

  if (!existsSync(`${dir}/listener.pid`)) {
    console.error("FAIL: Listener did not start (no PID file)")
    execSync(`rm -rf ${dir}`)
    return
  }

  const pid = readFileSync(`${dir}/listener.pid`, "utf-8").trim()
  assert(!!pid, `Listener started with PID ${pid}`)

  // Helper to send a command and read result
  async function sendCmd(requestId: string, command: string): Promise<Record<string, unknown>> {
    const json = JSON.stringify({ request_id: requestId, command }) + "\n"
    writeFileSync(`${dir}/cmd.pipe`, json)
    const deadline = Date.now() + 5000
    const resultPath = `${dir}/results/${requestId}.json`
    while (!existsSync(resultPath) && Date.now() < deadline) {
      await sleep(50)
    }
    if (!existsSync(resultPath)) throw new Error(`Timeout waiting for ${requestId}`)
    const result = JSON.parse(readFileSync(resultPath, "utf-8"))
    unlinkSync(resultPath)
    return result
  }

  // Test 1: basic echo
  {
    const r = await sendCmd("u-001", "echo hello world")
    assertEq(r.stdout, "hello world", "echo captures stdout")
    assertEq(r.exit_code, 0, "echo exit code is 0")
    assertEq(r.stderr, "", "echo has empty stderr")
    assert(typeof r.duration_ms === "number" && (r.duration_ms as number) >= 0, "duration_ms is non-negative")
    assert(typeof r.cwd === "string" && (r.cwd as string).length > 0, "cwd is non-empty")
  }

  // Test 2: exit code capture
  {
    const r = await sendCmd("u-002", "false")
    assertEq(r.exit_code, 1, "false returns exit code 1")
  }

  // Test 3: stderr capture
  {
    const r = await sendCmd("u-003", "echo err_msg >&2 && echo ok")
    assertEq(r.stdout, "ok", "stdout captured alongside stderr")
    assertEq(r.stderr, "err_msg", "stderr captured")
    assertEq(r.exit_code, 0, "exit code 0 with mixed streams")
  }

  // Test 4: cwd persistence
  {
    await sendCmd("u-004a", "cd /tmp")
    const r = await sendCmd("u-004b", "pwd")
    assertEq(r.stdout, "/tmp", "cwd persists after cd")
    assertEq(r.cwd, "/tmp", "cwd field matches pwd")
  }

  // Test 5: env var persistence
  {
    await sendCmd("u-005a", "export BRIDGE_TEST_VAR=hello42")
    const r = await sendCmd("u-005b", "echo $BRIDGE_TEST_VAR")
    assertEq(r.stdout, "hello42", "env var persists across commands")
  }

  // Test 6: multiline output
  {
    const r = await sendCmd("u-006", "echo line1 && echo line2 && echo line3")
    assertEq(r.stdout, "line1\nline2\nline3", "multiline output captured")
  }

  // Test 7: request_id round-trip
  {
    const r = await sendCmd("u-007-custom-id", "echo test")
    assertEq(r.request_id, "u-007-custom-id", "request_id matches")
  }

  // Test 8: exit code 2
  {
    const r = await sendCmd("u-008", "exit 2")
    assertEq(r.exit_code, 2, "exit code 2 captured")
  }

  // Test 9: large output (1000 lines)
  {
    const r = await sendCmd("u-009", "seq 1 1000")
    const lines = (r.stdout as string).split("\n")
    assertEq(lines.length, 1000, "1000 lines captured")
    assertEq(lines[0], "1", "first line is 1")
    assertEq(lines[999], "1000", "last line is 1000")
  }

  // Test 10: JSON in output (escaping)
  {
    const r = await sendCmd("u-010", 'echo \'{"key":"value"}\'')
    assertEq(r.stdout, '{"key":"value"}', "JSON in stdout properly escaped")
  }

  // Test 11: graceful shutdown
  {
    writeFileSync(`${dir}/cmd.pipe`, JSON.stringify({ request_id: "shutdown", command: "__shutdown__" }) + "\n")
    await sleep(1000)
    let alive = false
    try {
      execSync(`kill -0 ${pid} 2>/dev/null`, { stdio: "pipe" })
      alive = true
    } catch { /* expected */ }
    assert(!alive, "Listener exits on __shutdown__")
  }

  // Cleanup
  execSync(`rm -rf ${dir}`)
}

// ---------------------------------------------------------------------------
// Integration Tests — exec handler against live Zellij
// ---------------------------------------------------------------------------

async function integrationTests() {
  const sessionName = process.env.ZELLIJ_SESSION || ""

  if (!sessionName) {
    console.log("\n=== INTEGRATION TESTS: SKIPPED (set ZELLIJ_SESSION=<name>) ===\n")
    return
  }

  try {
    const sessions = execSync("zellij list-sessions", { encoding: "utf-8" })
    if (!sessions.includes(sessionName)) {
      console.log(`\n=== INTEGRATION TESTS: SKIPPED (session "${sessionName}" not found) ===\n`)
      return
    }
  } catch {
    console.log("\n=== INTEGRATION TESTS: SKIPPED (zellij not available) ===\n")
    return
  }

  console.log(`\n=== INTEGRATION TESTS: exec handler (session: ${sessionName}) ===\n`)

  const { handleExec } = await import("./exec.js")

  // Clean up any existing bridge
  await handleExec("stop", { session: sessionName }).catch(() => {})

  // Start bridge in a new pane
  {
    const r = await handleExec("start", { session: sessionName, direction: "down" })
    assert(r.includes("Bridge started") || r.includes("Bridge already running"), `start: ${r.slice(0, 80)}`)
  }

  // Status check
  {
    const r = await handleExec("status", { session: sessionName })
    assert(r.includes("alive"), `status: ${r.slice(0, 80)}`)
  }

  // Run echo
  {
    const r = await handleExec("run", { session: sessionName, command: "echo integration-ok" })
    const parsed = JSON.parse(r)
    assertEq(parsed.stdout, "integration-ok", "integration: echo stdout")
    assertEq(parsed.exit_code, 0, "integration: echo exit_code")
  }

  // Run failing command
  {
    const r = await handleExec("run", { session: sessionName, command: "ls /nonexistent-path-xyz-123" })
    const parsed = JSON.parse(r)
    assert(parsed.exit_code !== 0, `integration: non-zero exit (${parsed.exit_code})`)
    assert((parsed.stderr as string).length > 0, "integration: stderr for failed cmd")
  }

  // cwd persistence
  {
    await handleExec("run", { session: sessionName, command: "cd /tmp" })
    const r = await handleExec("run", { session: sessionName, command: "pwd" })
    const parsed = JSON.parse(r)
    assertEq(parsed.stdout, "/tmp", "integration: cwd persists")
  }

  // env var persistence
  {
    await handleExec("run", { session: sessionName, command: "export INTEG_VAR=works" })
    const r = await handleExec("run", { session: sessionName, command: "echo $INTEG_VAR" })
    const parsed = JSON.parse(r)
    assertEq(parsed.stdout, "works", "integration: env var persists")
  }

  // Stop
  {
    const r = await handleExec("stop", { session: sessionName })
    assert(r.includes("stopped") || r.includes("cleaned"), `stop: ${r.slice(0, 80)}`)
  }

  // Status after stop
  {
    const r = await handleExec("status", { session: sessionName })
    assert(r.includes("No bridge") || r.includes("dead"), `status after stop: ${r.slice(0, 80)}`)
  }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  console.log("Zellij exec domain - test suite\n")

  await unitTests()
  await integrationTests()

  console.log(`\n========================================`)
  console.log(`Results: ${passed} passed, ${failed} failed`)
  console.log(`========================================\n`)

  process.exit(failed > 0 ? 1 : 0)
}

main().catch(e => {
  console.error(e)
  process.exit(1)
})
