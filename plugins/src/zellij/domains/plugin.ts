import { execZellij, sanitize } from "../exec"
import type { Params } from "../types"
import { cache } from "../utils/cache"
import { Validator } from "../utils/validator"

export async function handlePlugin(action: string, params: Params): Promise<string> {
  switch (action) {
    case "launch": {
      const v = Validator.validatePluginUrl(String(params.plugin_url ?? ""))
      if (!v.valid) return `[ERROR] plugin.launch: ${v.errors.join(", ")}`
      let cmd = `action launch-plugin "${v.sanitized}"`
      if (params.configuration) {
        try {
          cmd += ` --configuration '${JSON.stringify(params.configuration)}'`
        } catch {
          return "[ERROR] plugin.launch: configuration must be valid JSON"
        }
      }
      if (params.floating) cmd += " --floating"
      if (params.in_place) cmd += " --in-place"
      if (params.skip_cache) cmd += " --skip-plugin-cache"
      if (params.width) cmd += ` --width ${sanitize(params.width)}`
      if (params.height) cmd += ` --height ${sanitize(params.height)}`
      if (params.x) cmd += ` --x ${sanitize(params.x)}`
      if (params.y) cmd += ` --y ${sanitize(params.y)}`
      if (params.pinned) cmd += " --pinned true"
      cache.delete("plugins_list")
      return execZellij(cmd)
    }

    case "action_launch": {
      const v = Validator.validatePluginUrl(String(params.plugin_url ?? ""))
      if (!v.valid) return `[ERROR] plugin.action_launch: ${v.errors.join(", ")}`
      let cmd = `action launch-plugin "${v.sanitized}"`
      if (params.configuration) {
        try {
          cmd += ` --configuration '${JSON.stringify(params.configuration)}'`
        } catch {
          return "[ERROR] plugin.action_launch: configuration must be valid JSON"
        }
      }
      if (params.floating) cmd += " --floating"
      if (params.in_place) cmd += " --in-place"
      if (params.skip_cache) cmd += " --skip-plugin-cache"
      cache.delete("plugins_list")
      return execZellij(cmd)
    }

    case "launch_or_focus": {
      const v = Validator.validatePluginUrl(String(params.plugin_url ?? ""))
      if (!v.valid) return `[ERROR] plugin.launch_or_focus: ${v.errors.join(", ")}`
      let cmd = `action launch-or-focus-plugin "${v.sanitized}"`
      if (params.configuration) {
        try {
          cmd += ` --configuration '${JSON.stringify(params.configuration)}'`
        } catch {
          return "[ERROR] plugin.launch_or_focus: configuration must be valid JSON"
        }
      }
      if (params.floating) cmd += " --floating"
      return execZellij(cmd)
    }

    case "start_or_reload": {
      const v = Validator.validatePluginUrl(String(params.plugin_url ?? ""))
      if (!v.valid) return `[ERROR] plugin.start_or_reload: ${v.errors.join(", ")}`
      let cmd = `action start-or-reload-plugin "${v.sanitized}"`
      if (params.configuration) {
        try {
          cmd += ` --configuration '${JSON.stringify(params.configuration)}'`
        } catch {
          return "[ERROR] plugin.start_or_reload: configuration must be valid JSON"
        }
      }
      cache.delete("plugins_list")
      return execZellij(cmd)
    }

    case "list_aliases": {
      const cached = cache.get<string>("plugin_aliases")
      if (cached) return cached
      const result = await execZellij("action list-aliases")
      const output = result || "No plugin aliases found."
      cache.set("plugin_aliases", output, 30000)
      return output
    }

    case "info": {
      const v = Validator.validatePluginUrl(String(params.plugin_url ?? ""))
      if (!v.valid) return `[ERROR] plugin.info: ${v.errors.join(", ")}`
      try {
        const result = await execZellij("action list-plugins")
        return `Plugin Info for: ${v.sanitized}\n\n${result}`
      } catch {
        return `Plugin Info for: ${v.sanitized}\nStatus: Unknown (use launch-or-focus-plugin to check)`
      }
    }

    case "list_running": {
      const cached = cache.get<string>("plugins_list")
      if (cached) return cached
      try {
        const result = await execZellij("action list-plugins")
        const output = result || "No running plugins found."
        cache.set("plugins_list", output, 10000)
        return output
      } catch {
        return "Unable to list running plugins. Use dump-layout to inspect current session."
      }
    }

    default:
      return `[ERROR] Unknown plugin action: "${action}". Valid: launch, action_launch, launch_or_focus, start_or_reload, list_aliases, info, list_running`
  }
}
