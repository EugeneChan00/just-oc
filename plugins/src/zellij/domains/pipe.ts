import { execZellij } from "../exec"
import type { Params } from "../types"
import { Validator } from "../utils/validator"

export async function handlePipe(action: string, params: Params): Promise<string> {
  switch (action) {
    case "send": {
      const tv = Validator.validateText(String(params.payload ?? ""))
      if (!tv.valid) return `[ERROR] pipe.send: payload — ${tv.errors.join(", ")}`
      let cmd = `action pipe --payload "${tv.sanitized!.replace(/"/g, '\\"')}"`
      if (params.pipe_name) {
        const v = Validator.validateString(String(params.pipe_name), "pipe name", 64)
        if (!v.valid) return `[ERROR] pipe.send: pipe_name — ${v.errors.join(", ")}`
        cmd += ` --name ${v.sanitized}`
      }
      if (params.plugin_url) {
        const v = Validator.validatePluginUrl(String(params.plugin_url))
        if (!v.valid) return `[ERROR] pipe.send: plugin_url — ${v.errors.join(", ")}`
        cmd += ` --plugin ${v.sanitized}`
      }
      if (params.args) {
        const v = Validator.validateString(String(params.args), "args", 256)
        if (!v.valid) return `[ERROR] pipe.send: args — ${v.errors.join(", ")}`
        cmd += ` --args "${v.sanitized}"`
      }
      return execZellij(cmd)
    }

    case "to_plugin": {
      const tv = Validator.validateText(String(params.payload ?? ""))
      const uv = Validator.validatePluginUrl(String(params.plugin_url ?? ""))
      if (!tv.valid) return `[ERROR] pipe.to_plugin: payload — ${tv.errors.join(", ")}`
      if (!uv.valid) return `[ERROR] pipe.to_plugin: plugin_url — ${uv.errors.join(", ")}`
      let cmd = `action pipe --payload "${tv.sanitized!.replace(/"/g, '\\"')}" --plugin ${uv.sanitized}`
      if (params.pipe_name) {
        const v = Validator.validateString(String(params.pipe_name), "pipe name", 64)
        if (!v.valid) return `[ERROR] pipe.to_plugin: pipe_name — ${v.errors.join(", ")}`
        cmd += ` --name ${v.sanitized}`
      }
      if (params.configuration) {
        try {
          const configJson = JSON.stringify(params.configuration)
          cmd += ` --plugin-configuration '${configJson}'`
        } catch {
          return "[ERROR] pipe.to_plugin: configuration must be valid JSON"
        }
      }
      return execZellij(cmd)
    }

    case "broadcast": {
      const tv = Validator.validateText(String(params.payload ?? ""))
      const nv = Validator.validateString(String(params.pipe_name ?? ""), "pipe name", 64)
      if (!tv.valid) return `[ERROR] pipe.broadcast: payload — ${tv.errors.join(", ")}`
      if (!nv.valid) return `[ERROR] pipe.broadcast: pipe_name — ${nv.errors.join(", ")}`
      return execZellij(`action pipe --payload "${tv.sanitized!.replace(/"/g, '\\"')}" --name ${nv.sanitized}`)
    }

    case "action": {
      const tv = Validator.validateText(String(params.payload ?? ""))
      if (!tv.valid) return `[ERROR] pipe.action: payload — ${tv.errors.join(", ")}`
      let cmd = `action pipe --payload "${tv.sanitized!.replace(/"/g, '\\"')}"`
      if (params.pipe_name) {
        const v = Validator.validateString(String(params.pipe_name), "pipe name", 64)
        if (!v.valid) return `[ERROR] pipe.action: pipe_name — ${v.errors.join(", ")}`
        cmd += ` --name "${v.sanitized}"`
      }
      if (params.plugin_url) {
        const v = Validator.validatePluginUrl(String(params.plugin_url))
        if (!v.valid) return `[ERROR] pipe.action: plugin_url — ${v.errors.join(", ")}`
        cmd += ` --plugin "${v.sanitized}"`
      }
      if (params.configuration) {
        try {
          cmd += ` --plugin-configuration '${JSON.stringify(params.configuration)}'`
        } catch {
          return "[ERROR] pipe.action: configuration must be valid JSON"
        }
      }
      if (params.force_launch) cmd += " --force-launch-plugin"
      if (params.floating) cmd += " --floating"
      if (params.in_place) cmd += " --in-place"
      if (params.skip_cache) cmd += " --skip-plugin-cache"
      if (params.cwd) {
        const v = Validator.validateString(String(params.cwd), "working directory", 512)
        if (!v.valid) return `[ERROR] pipe.action: cwd — ${v.errors.join(", ")}`
        cmd += ` --plugin-cwd "${v.sanitized}"`
      }
      if (params.title) {
        const v = Validator.validateString(String(params.title), "title", 128)
        if (!v.valid) return `[ERROR] pipe.action: title — ${v.errors.join(", ")}`
        cmd += ` --plugin-title "${v.sanitized}"`
      }
      return execZellij(cmd)
    }

    case "with_response": {
      const tv = Validator.validateText(String(params.payload ?? ""))
      if (!tv.valid) return `[ERROR] pipe.with_response: payload — ${tv.errors.join(", ")}`
      let cmd = `action pipe --payload "${tv.sanitized!.replace(/"/g, '\\"')}"`
      if (params.pipe_name) {
        const v = Validator.validateString(String(params.pipe_name), "pipe name", 64)
        if (!v.valid) return `[ERROR] pipe.with_response: pipe_name — ${v.errors.join(", ")}`
        cmd += ` --name ${v.sanitized}`
      }
      if (params.plugin_url) {
        const v = Validator.validatePluginUrl(String(params.plugin_url))
        if (!v.valid) return `[ERROR] pipe.with_response: plugin_url — ${v.errors.join(", ")}`
        cmd += ` --plugin ${v.sanitized}`
      }
      return execZellij(cmd)
    }

    case "from_file": {
      const pv = Validator.validatePath(String(params.file_path ?? ""))
      if (!pv.valid) return `[ERROR] pipe.from_file: file_path — ${pv.errors.join(", ")}`
      const { readFileSync } = await import("node:fs")
      let content: string
      try {
        content = readFileSync(pv.sanitized!, "utf-8")
      } catch (e) {
        return `[ERROR] Cannot read file: ${e}`
      }
      let cmd = `action pipe --payload "${content.replace(/"/g, '\\"')}"`
      if (params.pipe_name) {
        const v = Validator.validateString(String(params.pipe_name), "pipe name", 64)
        if (!v.valid) return `[ERROR] pipe.from_file: pipe_name — ${v.errors.join(", ")}`
        cmd += ` --name ${v.sanitized}`
      }
      if (params.plugin_url) {
        const v = Validator.validatePluginUrl(String(params.plugin_url))
        if (!v.valid) return `[ERROR] pipe.from_file: plugin_url — ${v.errors.join(", ")}`
        cmd += ` --plugin ${v.sanitized}`
      }
      return execZellij(cmd)
    }

    default:
      return `[ERROR] Unknown pipe action: "${action}". Valid: send, to_plugin, broadcast, action, with_response, from_file`
  }
}
