import { type Plugin, tool } from "@opencode-ai/plugin"

export const ZellijPlugin: Plugin = async (ctx) => {
  return {
    tool: {
      zellij: tool({
        description: "Zellij multiplexer commands. Use this tool to manage sessions, panes, tabs, plugins, layouts, pipes, detection, and system operations in Zellij.",
        args: {
          category: tool.schema.enum(["system", "pane", "tab", "plugin", "layout", "pipe", "detection", "session"]).describe("The category of the tool query."),
          action: tool.schema.enum([
            "clear", "close-pane", "close-tab", "dump-layout", "dump-screen",
            "edit", "edit-scrollback", "focus-next-pane", "focus-previous-pane",
            "go-to-next-tab", "go-to-previous-tab", "go-to-tab", "go-to-tab-name",
            "half-page-scroll-down", "half-page-scroll-up", "launch-or-focus-plugin",
            "launch-plugin", "list-clients", "move-focus", "move-focus-or-tab",
            "move-pane", "move-pane-backwards", "move-tab", "new-pane", "new-tab",
            "next-swap-layout", "page-scroll-down", "page-scroll-up", "pipe",
            "previous-swap-layout", "query-tab-names", "rename-pane", "rename-session",
            "rename-tab", "resize", "scroll-down", "scroll-to-bottom", "scroll-to-top",
            "scroll-up", "start-or-reload-plugin", "switch-mode", "toggle-active-sync-tab",
            "toggle-floating-panes", "toggle-fullscreen", "toggle-pane-embed-or-floating",
            "toggle-pane-frames", "undo-rename-pane", "undo-rename-tab", "write", "write-chars"
          ]).describe("The query (action) inside the category."),
          conditional: tool.schema.enum(["right", "left", "up", "down", "increase", "decrease", "locked", "pane", "tab", "resize", "move", "search", "session", "none"]).optional().describe("Conditional argument (e.g. direction). Pass 'none' if unused."),
          query: tool.schema.string().optional().describe("String arg as query (such as piping keys, commands in a pane, or additional text args)."),
        },
        async execute(args, context) {
          const { $ } = context;
          try {
            let result;
            const useConditional = args.conditional && args.conditional !== "none";

            if (args.query && useConditional) {
              result = await $`zellij action ${args.action} ${args.conditional} ${args.query}`;
            } else if (args.query) {
              result = await $`zellij action ${args.action} ${args.query}`;
            } else if (useConditional) {
              result = await $`zellij action ${args.action} ${args.conditional}`;
            } else {
              result = await $`zellij action ${args.action}`;
            }
            return result.stdout.toString() || "Command executed successfully";
          } catch(e) {
            return `Error executing Zellij command: ${e.message}`;
          }
        },
      }),
    },
  }
}
