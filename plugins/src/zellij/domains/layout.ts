import { execZellij, sanitize } from "../exec"
import type { Params } from "../types"
import { cache } from "../utils/cache"
import { Validator } from "../utils/validator"

export async function handleLayout(action: string, params: Params): Promise<string> {
  switch (action) {
    case "dump": {
      const layout = await execZellij("action dump-layout")
      if (params.output_path) {
        const v = Validator.validatePath(String(params.output_path))
        if (!v.valid) return `[ERROR] layout.dump: output_path — ${v.errors.join(", ")}`
        const { writeFileSync } = await import("node:fs")
        writeFileSync(v.sanitized!, layout)
        return `Layout dumped to ${v.sanitized}`
      }
      return layout
    }

    case "save": {
      const nv = Validator.validateString(String(params.layout_name ?? ""), "layout name", 64)
      if (!nv.valid) return `[ERROR] layout.save: ${nv.errors.join(", ")}`
      const dir = sanitize(params.layouts_dir) || `${process.env.HOME}/.config/zellij/layouts`
      const dv = Validator.validatePath(dir)
      if (!dv.valid) return `[ERROR] layout.save: layouts_dir — ${dv.errors.join(", ")}`
      const layout = await execZellij("action dump-layout")
      const { mkdirSync, writeFileSync } = await import("node:fs")
      mkdirSync(dv.sanitized!, { recursive: true })
      const layoutPath = `${dv.sanitized}/${nv.sanitized}.kdl`
      writeFileSync(layoutPath, layout)
      cache.delete("layouts_list")
      return `Layout saved as ${layoutPath}`
    }

    case "apply": {
      const nv = Validator.validateString(String(params.layout_name ?? ""), "layout name", 64)
      if (!nv.valid) return `[ERROR] layout.apply: ${nv.errors.join(", ")}`
      let cmd = `--layout ${nv.sanitized}`
      if (params.session_name) {
        const sv = Validator.validateSessionName(String(params.session_name))
        if (!sv.valid) return `[ERROR] layout.apply: session_name — ${sv.errors.join(", ")}`
        cmd = `--session ${sv.sanitized} ${cmd}`
      }
      return execZellij(cmd)
    }

    case "list": {
      const dir = sanitize(params.layouts_dir) || `${process.env.HOME}/.config/zellij/layouts`
      const cacheKey = `layouts_list_${dir}`
      const cached = cache.get<string>(cacheKey)
      if (cached) return cached

      const { readdirSync, existsSync } = await import("node:fs")
      let output = "Available Layouts:\n\n"
      if (existsSync(dir)) {
        const files = readdirSync(dir).filter((f: string) => f.endsWith(".kdl")).map((f: string) => f.replace(".kdl", ""))
        if (files.length > 0) {
          output += `Custom layouts in ${dir}:\n`
          for (const f of files) output += `  • ${f}\n`
        } else {
          output += `No custom layouts found in ${dir}\n`
        }
      } else {
        output += `Layouts directory not found: ${dir}\n`
      }
      output += "\nBuilt-in layouts:\n  • default\n  • strider\n  • compact"
      cache.set(cacheKey, output, 30000)
      return output
    }

    case "load": {
      const nv = Validator.validateString(String(params.layout_name ?? ""), "layout name", 64)
      if (!nv.valid) return `[ERROR] layout.load: ${nv.errors.join(", ")}`
      const { existsSync, readFileSync } = await import("node:fs")
      const { join } = await import("node:path")
      let layoutPath: string
      if (nv.sanitized!.includes("/")) {
        layoutPath = nv.sanitized!
      } else {
        const dir = sanitize(params.layouts_dir) || `${process.env.HOME}/.config/zellij/layouts`
        layoutPath = join(dir, `${nv.sanitized}.kdl`)
      }
      const pv = Validator.validatePath(layoutPath)
      if (!pv.valid) return `[ERROR] layout.load: path — ${pv.errors.join(", ")}`
      if (!existsSync(pv.sanitized!)) return `[ERROR] Layout file not found: ${pv.sanitized}`
      return readFileSync(pv.sanitized!, "utf-8")
    }

    case "new_tab_with": {
      const nv = Validator.validateString(String(params.layout_name ?? ""), "layout name", 64)
      if (!nv.valid) return `[ERROR] layout.new_tab_with: ${nv.errors.join(", ")}`
      let cmd = `action new-tab --layout ${nv.sanitized}`
      if (params.tab_name) {
        const tv = Validator.validateString(String(params.tab_name), "tab name", 64)
        if (!tv.valid) return `[ERROR] layout.new_tab_with: tab_name — ${tv.errors.join(", ")}`
        cmd += ` --name "${tv.sanitized}"`
      }
      return execZellij(cmd)
    }

    case "validate": {
      const pv = Validator.validatePath(String(params.layout_path ?? ""))
      if (!pv.valid) return `[ERROR] layout.validate: ${pv.errors.join(", ")}`
      const { existsSync, readFileSync } = await import("node:fs")
      if (!existsSync(pv.sanitized!)) return `[ERROR] Layout file does not exist: ${pv.sanitized}`
      try {
        const content = readFileSync(pv.sanitized!, "utf-8")
        const hasLayout = content.includes("layout")
        const hasTab = content.includes("tab")
        const hasPane = content.includes("pane")
        const checks: string[] = []
        checks.push(`File readable: Yes`)
        checks.push(`Contains 'layout' block: ${hasLayout ? "Yes" : "No"}`)
        checks.push(`Contains 'tab' block: ${hasTab ? "Yes" : "No"}`)
        checks.push(`Contains 'pane' block: ${hasPane ? "Yes" : "No"}`)
        return `Layout validation for ${pv.sanitized}:\n${checks.join("\n")}\n\n${hasLayout && hasTab && hasPane ? "Layout appears structurally valid" : "Warning: layout may be missing required blocks"}`
      } catch (e) {
        return `[ERROR] Cannot read layout file: ${e}`
      }
    }

    case "convert": {
      const iv = Validator.validatePath(String(params.input_path ?? ""))
      const ov = Validator.validatePath(String(params.output_path ?? ""))
      if (!iv.valid) return `[ERROR] layout.convert: input_path — ${iv.errors.join(", ")}`
      if (!ov.valid) return `[ERROR] layout.convert: output_path — ${ov.errors.join(", ")}`
      const fromFmt = String(params.from_format ?? "").toLowerCase()
      const toFmt = String(params.to_format ?? "").toLowerCase()
      if (!["kdl", "json"].includes(fromFmt) || !["kdl", "json"].includes(toFmt)) {
        return '[ERROR] layout.convert: from_format and to_format must be "kdl" or "json"'
      }
      const { existsSync, readFileSync, writeFileSync } = await import("node:fs")
      if (!existsSync(iv.sanitized!)) return `[ERROR] Input file does not exist: ${iv.sanitized}`
      const input = readFileSync(iv.sanitized!, "utf-8")
      let output: string
      if (fromFmt === toFmt) {
        output = input
      } else if (fromFmt === "json" && toFmt === "kdl") {
        const data = JSON.parse(input)
        output = convertJsonToKdl(data)
      } else {
        output = convertKdlToJson(input)
      }
      writeFileSync(ov.sanitized!, output)
      return `Layout converted: ${fromFmt.toUpperCase()} → ${toFmt.toUpperCase()}\nInput: ${iv.sanitized}\nOutput: ${ov.sanitized}`
    }

    default:
      return `[ERROR] Unknown layout action: "${action}". Valid: dump, save, apply, list, load, new_tab_with, validate, convert`
  }
}

function convertJsonToKdl(data: Record<string, unknown>): string {
  let kdl = "layout {\n"
  const tabs = data.tabs
  if (Array.isArray(tabs)) {
    for (const tab of tabs) {
      kdl += "  tab {\n"
      if (tab.name) kdl += `    name "${tab.name}"\n`
      kdl += "    pane\n  }\n"
    }
  } else {
    kdl += "  tab {\n    pane\n  }\n"
  }
  kdl += "}\n"
  return kdl
}

function convertKdlToJson(kdlContent: string): string {
  return JSON.stringify({ name: "converted-layout", raw: kdlContent, tabs: [{ name: "main", panes: [{ split_direction: "horizontal" }] }] }, null, 2)
}
