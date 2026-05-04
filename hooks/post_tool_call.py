"""
post_tool_call hook — runs linters after file writes when auto-lint is enabled.
"""

from __future__ import annotations

import logging
from typing import Any

from ..config import load_config, is_enabled
from ..orchestrator import run_linters

logger = logging.getLogger(__name__)


def on_post_tool_call(
    tool_name: str,
    args: dict[str, Any],
    result: Any,
    **kwargs,
) -> dict[str, Any] | None:
    """Hook: after write_file or patch, run linters on changed files.

    Returns a context injection dict or None.
    """
    if not is_enabled():
        return None

    config = load_config()
    threshold = config.get("auto_lint_threshold_lines", 5)

    if tool_name not in ("write_file", "patch"):
        return None

    # Extract the file path from args
    filepath = args.get("path") or args.get("file_path")
    if not filepath:
        return None

    # Only lint known file types
    known_extensions = {".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go", ".sh", ".bash"}
    if not any(str(filepath).endswith(ext) for ext in known_extensions):
        return None

    try:
        import os

        if not os.path.exists(filepath):
            return None

        # Check file size (skip huge files)
        file_size = os.path.getsize(filepath)
        if file_size > 500_000:  # 500KB
            return None

        # Count lines
        with open(filepath, "r", errors="ignore") as f:
            line_count = sum(1 for _ in f)

        if line_count < threshold:
            return None

        # Run linters
        findings = run_linters([filepath])
        if not findings:
            return None

        # Format for context injection
        lines = ["[Code QA] Linter findings:"]
        for f in findings[:5]:  # Cap at 5 findings to avoid flooding
            lines.append(f"  {f['file']}: {f['output'][:200]}")

        context_text = "\n".join(lines)

        return {"context": f"\n\n{context_text}\n"}

    except Exception as e:
        logger.debug(f"Code QA post_tool_call hook failed: {e}")
        return None
