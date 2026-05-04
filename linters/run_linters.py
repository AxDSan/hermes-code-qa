"""
run_linters — standalone CLI for Tier 1 linting (can be invoked directly).

Usage: python -m hermes_code_qa.linters.run_linters <file1> [file2 ...]

Returns JSON array of findings to stdout.
"""

import json
import os
import subprocess
import sys
from pathlib import Path


def get_linter(filepath: str) -> list[str] | None:
    """Return linter command for a file based on extension."""
    ext = Path(filepath).suffix.lower()
    linter_map = {
        ".py": ["ruff", "check", "--select=E,F,B,S", "--output-format=concise"],
        ".ts": ["npx", "eslint", "--format=compact"],
        ".tsx": ["npx", "eslint", "--format=compact"],
        ".js": ["npx", "eslint", "--format=compact"],
        ".jsx": ["npx", "eslint", "--format=compact"],
        ".rs": ["cargo", "clippy", "--message-format=short"],
        ".go": ["go", "vet"],
        ".sh": ["shellcheck", "-f", "gcc"],
        ".bash": ["shellcheck", "-f", "gcc"],
    }

    cmd = linter_map.get(ext)
    if cmd is None:
        return None

    # Check if command exists using Python's shutil (no external which dependency)
    import shutil as _shutil
    if _shutil.which(cmd[0]) is None:
        return None

    return cmd


def run_one(filepath: str) -> dict | None:
    """Run linter on a single file."""
    if not os.path.exists(filepath):
        return None

    cmd = get_linter(filepath)
    if cmd is None:
        return None

    try:
        full_cmd = cmd + [filepath]
        result = subprocess.run(full_cmd, capture_output=True, text=True, timeout=30)
        output = (result.stdout + result.stderr).strip()
        if output:
            return {
                "file": filepath,
                "linter": cmd[0],
                "output": output[:2000],
                "exit_code": result.returncode,
            }
    except subprocess.TimeoutExpired:
        return {"file": filepath, "linter": cmd[0], "output": "Timed out", "exit_code": -1}
    except Exception as e:
        return {"file": filepath, "linter": cmd[0], "output": str(e), "exit_code": -1}

    return None


def main():
    """CLI entry point."""
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: run_linters <file1> [file2 ...]"}), file=sys.stderr)
        sys.exit(1)

    files = sys.argv[1:]
    findings = []

    for fp in files:
        result = run_one(fp)
        if result:
            findings.append(result)

    print(json.dumps({"files_scanned": len(files), "findings": findings, "total": len(findings)}))


if __name__ == "__main__":
    main()
