import type { PluginInput } from "@opencode-ai/plugin"
import type { BackgroundTask, LaunchInput } from "./types"
import type { ConcurrencyManager } from "./concurrency"
import type { TaskHistory } from "./task-history"
import type { BackgroundTaskConfig, TmuxConfig } from "../../config/schema"
import type { BackgroundTaskNotificationTask } from "./background-task-notification-template"
import type { CircuitBreakerSettings } from "./loop-detector"

type OpencodeClient = PluginInput["client"]

export interface QueueItem {
  task: BackgroundTask
  input: LaunchInput
}

export interface SubagentSessionCreatedEvent {
  sessionID: string
  parentID: string
  title: string
}

export type OnSubagentSessionCreated = (event: SubagentSessionCreatedEvent) => Promise<void>

export interface ManagerContext {
  tasks: Map<string, BackgroundTask>
  notifications: Map<string, BackgroundTask[]>
  pendingNotifications: Map<string, string[]>
  pendingByParent: Map<string, Set<string>>
  client: OpencodeClient
  directory: string
  concurrencyManager: ConcurrencyManager
  config?: BackgroundTaskConfig
  tmuxEnabled: boolean
  onSubagentSessionCreated?: OnSubagentSessionCreated
  onShutdown?: () => void | Promise<void>
  shutdownTriggered: boolean

  queuesByKey: Map<string, QueueItem[]>
  processingKeys: Set<string>
  completionTimers: Map<string, ReturnType<typeof setTimeout>>
  completedTaskSummaries: Map<string, BackgroundTaskNotificationTask[]>
  idleDeferralTimers: Map<string, ReturnType<typeof setTimeout>>
  notificationQueueByParent: Map<string, Promise<void>>
  observedOutputSessions: Set<string>
  observedIncompleteTodosBySession: Map<string, boolean>
  rootDescendantCounts: Map<string, number>
  preStartDescendantReservations: Set<string>
  enableParentSessionNotifications: boolean
  taskHistory: TaskHistory
  cachedCircuitBreakerSettings?: CircuitBreakerSettings

  pollingInterval?: ReturnType<typeof setInterval>
  pollingInFlight: boolean
}

export interface MessagePartInfo {
  id?: string
  sessionID?: string
  type?: string
  tool?: string
  state?: { status?: string; input?: Record<string, unknown> }
}

export interface EventProperties {
  sessionID?: string
  info?: { id?: string }
  [key: string]: unknown
}

export interface Event {
  type: string
  properties?: EventProperties
}

export interface Todo {
  content: string
  status: string
  priority: string
  id: string
}
