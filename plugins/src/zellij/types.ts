export type Domain =
  | "session"
  | "pane"
  | "tab"
  | "pipe"
  | "plugin"
  | "layout"
  | "utility"
  | "detection"
  | "exec"

export type Params = Record<string, unknown>

export type DomainHandler = (action: string, params: Params) => Promise<string>

export interface ZellijSession {
  name: string
  created: string
  attached: boolean
  tabs?: ZellijTab[]
}

export interface ZellijTab {
  name: string
  active: boolean
  panes?: ZellijPane[]
}

export interface ZellijPane {
  id: string
  title?: string
  command?: string
  cwd?: string
  focused: boolean
}

export interface ZellijPlugin {
  id: string
  name: string
  url: string
  configuration?: Record<string, unknown>
  running: boolean
}

export interface ZellijLayout {
  name: string
  description?: string
  tabs: Array<{
    name?: string
    panes: Array<{
      split_direction?: "horizontal" | "vertical"
      parts?: unknown[]
    }>
  }>
}

export interface PipeOptions {
  name?: string
  plugin?: string
  args?: string
  configuration?: Record<string, unknown>
  forceLaunch?: boolean
  skipCache?: boolean
  floating?: boolean
  inPlace?: boolean
  cwd?: string
  title?: string
}

export interface PluginLaunchOptions {
  url: string
  configuration?: Record<string, unknown>
  floating?: boolean
  inPlace?: boolean
  skipCache?: boolean
  width?: string
  height?: string
  x?: string
  y?: string
  pinned?: boolean
}

export interface SessionExport {
  name: string
  layout: ZellijLayout
  created: string
  metadata?: Record<string, unknown>
}
