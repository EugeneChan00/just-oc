"""
autoresearch.harness.scaffolder

Creates minimal mock codebases for agent eval runs.
Path: autoresearch/test/<agent-name>/<run-id>/
"""

import json
import shutil
from pathlib import Path


class Scaffolder:
    """Create and clean up ephemeral test workspaces for eval runs."""

    def __init__(self, test_dir: str | Path = "autoresearch/test"):
        self.test_dir = Path(test_dir)

    def scaffold(self, agent_name: str, run_id: str) -> Path:
        """Create a minimal mock codebase. Returns the workspace path.

        The scaffold provides enough structure that agent tool calls
        (read, grep, glob, bash) don't fail on empty directories.
        """
        workspace = self.test_dir / agent_name / run_id
        workspace.mkdir(parents=True, exist_ok=True)

        # package.json
        (workspace / "package.json").write_text(json.dumps({
            "name": f"eval-{agent_name}",
            "version": "1.0.0",
            "description": f"Mock workspace for {agent_name} eval",
        }, indent=2))

        # Source directories
        (workspace / "src").mkdir(exist_ok=True)
        (workspace / "src" / "index.ts").write_text(
            '// Entry point\nexport function main() { console.log("hello"); }\n'
        )

        # Test directory
        (workspace / "tests").mkdir(exist_ok=True)
        (workspace / "tests" / "index.test.ts").write_text(
            '// Tests\nimport { main } from "../src/index";\n'
        )

        # Config
        (workspace / "tsconfig.json").write_text(json.dumps({
            "compilerOptions": {"target": "es2022", "module": "commonjs", "strict": True},
            "include": ["src/**/*"],
        }, indent=2))

        return workspace

    def cleanup(self, path: str | Path) -> None:
        """Remove a scaffold directory."""
        path = Path(path)
        if path.exists() and "autoresearch/test" in str(path):
            shutil.rmtree(path)
