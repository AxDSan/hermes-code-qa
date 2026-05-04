"""
review_file tool — Review a single file inline (no Kanban, no lint).
"""

from __future__ import annotations

import json
import os
from typing import Any

from ..orchestrator import run_inline_review, run_linters
from ..config import load_config

SCHEMA: dict[str, Any] = {
    "name": "review_file",
    "description": "Quick review of a single file. Runs linters then a single-pass LLM review. Best for checking a file you just edited.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute or relative path to the file to review.",
            },
            "scope": {
                "type": "string",
                "enum": ["instant", "quick"],
                "description": "'instant' = linters only, 'quick' = linters + LLM review. Default: 'quick'.",
                "default": "quick",
            },
        },
        "required": ["path"],
    },
}


def handler(args: dict[str, Any], **kwargs) -> str:
    """Handle review_file tool call."""
    filepath = args.get("path", "")
    scope = args.get("scope", "quick")

    if not filepath:
        return json.dumps({"success": False, "error": "No file path provided."})

    # Resolve path
    if not os.path.isabs(filepath):
        filepath = os.path.abspath(filepath)

    if not os.path.exists(filepath):
        return json.dumps(
            {"success": False, "error": f"File not found: {filepath}"}
        )

    if not os.path.isfile(filepath):
        return json.dumps(
            {"success": False, "error": f"Path is not a file: {filepath}"}
        )

    repo_path = os.path.dirname(filepath)
    findings: list[dict] = []

    # Tier 1: linters (always free)
    lint_findings = run_linters([filepath])
    findings.extend(lint_findings)

    if scope == "instant":
        return json.dumps(
            {
                "success": True,
                "scope": "instant",
                "file": filepath,
                "findings": findings,
                "linter_findings": len(lint_findings),
            }
        )

    # Tier 2: inline review
    result_text = run_inline_review([filepath], repo_path, scope="quick")
    findings.append({"type": "llm_review", "output": result_text})

    return json.dumps(
        {
            "success": True,
            "scope": "quick",
            "file": filepath,
            "linter_findings": len(lint_findings),
            "linter_issues": lint_findings,
            "findings": findings,
            "review": result_text,
        }
    )
