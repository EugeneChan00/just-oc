const ACTIVE_SESSION_STATUSES = new Set(["busy", "retry", "running"])
const KNOWN_TERMINAL_STATUSES = new Set(["idle", "interrupted"])

export function isActiveSessionStatus(type: string): boolean {
  return ACTIVE_SESSION_STATUSES.has(type)
}

export function isTerminalSessionStatus(type: string): boolean {
  return KNOWN_TERMINAL_STATUSES.has(type) && type !== "idle"
}
