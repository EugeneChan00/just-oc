import { type Plugin, tool } from "@opencode-ai/plugin";
import { SessionTools } from "./src/tools/sessions.js";
import { PaneTools } from "./src/tools/panes.js";
import { execAsync } from "./src/utils/command.js";

export const ZellijPlugin: Plugin = async (ctx) => {
  return {
    tool: {
      zellij: tool({
        description: "A deep tool for interacting with Zellij terminal workspace using a standalone local instance",
        args: {
          category: tool.schema.enum(['system', 'pane', 'tab', 'action']),
          query: tool.schema.enum([
            'new-pane', 'close-pane', 'new-tab', 'close-tab',
            'write', 'write-chars', 'run', 'edit', 'rename-pane',
            'rename-tab', 'go-to-tab', 'list-clients', 'list-sessions'
          ]),
          conditional: tool.schema.enum(['left', 'right', 'down', 'up', 'none']),
          arg: tool.schema.string().optional().describe("Additional string argument for the query (e.g., command to run, keys to type)"),
        },
        async execute(args, context) {
          try {
            if (args.category === 'system' && args.query === 'list-sessions') {
              const response = await SessionTools.listSessions();
              return JSON.stringify(response.content, null, 2);
            }

            if (args.category === 'pane' && args.query === 'new-pane') {
              const direction = args.conditional === 'none' ? undefined : args.conditional;
              const response = await PaneTools.newPane(direction, undefined, args.arg);
              return JSON.stringify(response.content, null, 2);
            }

            if (args.category === 'system' && args.query === 'run') {
              const response = await execAsync('zellij run -- ' + (args.arg || ''));
              let result = "";
              if (response.stdout) result += `STDOUT:\n${response.stdout}\n`;
              if (response.stderr) result += `STDERR:\n${response.stderr}\n`;
              return result || `Executed zellij run successfully`;
            }

            if (args.category === 'pane' && args.query === 'close-pane') {
              const response = await execAsync('zellij action close-pane');
              let result = "";
              if (response.stdout) result += `STDOUT:\n${response.stdout}\n`;
              if (response.stderr) result += `STDERR:\n${response.stderr}\n`;
              return result || `Executed zellij action close-pane successfully`;
            }

            // Fallback for remaining queries using execAsync
            let actionCommand = 'zellij action ' + args.query;
            if (args.conditional && args.conditional !== 'none') {
              if (args.query === 'move-focus' || args.query === 'move-pane' || args.query === 'move-focus-or-tab') {
                actionCommand += ' -d ' + args.conditional;
              } else {
                actionCommand += ' ' + args.conditional;
              }
            }
            if (args.arg) {
              actionCommand += ' "' + args.arg.replace(/"/g, '\\"') + '"';
            }

            const response = await execAsync(actionCommand);
            let result = "";
            if (response.stdout) result += `STDOUT:\n${response.stdout}\n`;
            if (response.stderr) result += `STDERR:\n${response.stderr}\n`;
            return result || `Executed successfully with no output: ${actionCommand}`;

          } catch (error: any) {
            return `Failed to execute zellij tool command: ${error.message}\n${error.stderr || ''}`;
          }
        },
      }),
    },
  };
};
