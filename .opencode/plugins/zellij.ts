import { type Plugin, tool } from "@opencode-ai/plugin";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

export const ZellijPlugin: Plugin = async (ctx) => {
  return {
    tool: {
      zellij: tool({
        description: "A deep tool for interacting with Zellij terminal workspace",
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
            let cmdArgs: string[] = [];

            if (args.category === 'action') {
              cmdArgs.push('action', args.query);
              if (args.conditional && args.conditional !== 'none') {
                if (args.query === 'new-pane' || args.query === 'move-focus' || args.query === 'move-pane' || args.query === 'move-focus-or-tab') {
                  cmdArgs.push('-d', args.conditional);
                } else {
                  cmdArgs.push(args.conditional);
                }
              }
              if (args.arg) {
                cmdArgs.push(args.arg);
              }
            } else if (args.category === 'system' && args.query === 'run') {
              cmdArgs.push('run', '--');
              if (args.arg) {
                // If it's a multi-word string for `run --`, zellij expects it as one or many args.
                // Using a shell-like execution bypasses `execFile` safety if we pass raw command string.
                // We will split by space if the user passes multiple words for a run command,
                // but usually the first arg is the executable, and rest are args.
                const runArgs = args.arg.split(' ');
                cmdArgs.push(...runArgs);
              }
            } else if (args.category === 'system' && args.query === 'list-sessions') {
              cmdArgs.push('list-sessions');
            } else {
              // Fallback for pane/tab categories
              cmdArgs.push('action', args.query);
              if (args.conditional && args.conditional !== 'none') {
                if (args.query === 'new-pane' || args.query === 'move-focus' || args.query === 'move-pane' || args.query === 'move-focus-or-tab') {
                  cmdArgs.push('-d', args.conditional);
                } else {
                  cmdArgs.push(args.conditional);
                }
              }
              if (args.arg) {
                cmdArgs.push(args.arg);
              }
            }

            const { stdout, stderr } = await execFileAsync('zellij', cmdArgs);

            let result = "";
            if (stdout) result += `STDOUT:\n${stdout}\n`;
            if (stderr) result += `STDERR:\n${stderr}\n`;

            if (!result) {
              result = `Executed successfully with no output: zellij ${cmdArgs.join(' ')}`;
            }

            return result;
          } catch (error: any) {
            return `Failed to execute zellij command: ${error.message}\n${error.stderr || ''}`;
          }
        },
      }),
    },
  };
};