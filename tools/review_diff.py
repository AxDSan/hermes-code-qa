"""
review_diff tool — Review uncommitted or staged changes in the current working directory.
"""

from __future__ import annotations

import json
import os
from typing import Any

from ..orchestrator import (
    create_kanban_pipeline,
    get_changed_files,
    get_diff,
    poll_pipeline,
    run_inline_review,
    run_linters,
)
from ..config import load_config

SCHEMA: dict[str, Any] = {
    "name": "review_diff",
    "description": "Review uncommitted or staged changes in the current working directory. Runs linters (free), quick single-pass review (fast), or full 5-agent Kanban pipeline (thorough). Use after writing code to check quality.",
    "parameters": {
        "type": "object",
        "properties": {
            "scope": {
                "type": "string",
                "enum": ["instant", "quick", "full"],
                "description": "Review depth: 'instant' = linters only (<1s, no LLM), 'quick' = single-pass review (~30s), 'full' = 5-agent Kanban pipeline (~3-5min). Default: 'quick'.",
                "default": "quick",
            },
            "base_ref": {
                "type": "string",
                "description": "Git ref to diff against (default: HEAD). Use 'origin/main' or 'main' to diff against a branch.",
            },
            "wait": {
                "type": "boolean",
                "description": "Wait for results (true) or return immediately (false). Default: true.",
                "default": True,
            },
        },
        "required": [],
    },
}


def handler(args: dict[str, Any], **kwargs) -> str:
    """Handle review_diff tool call."""
    scope = args.get("scope", "quick")
    base_ref = args.get("base_ref", "HEAD")
    wait = args.get("wait", True)

    repo_path = os.getcwd()

    # Get changed files
    changed = get_changed_files(repo_path, base_ref)
    if not changed:
        # Try staged changes
        changed = get_changed_files(repo_path, "--cached")
    if not changed:
        # Try working tree changes
        changed = get_changed_files(repo_path, "")

    if not changed:
        return json.dumps(
            {
                "success": True,
                "scope": scope,
                "message": "No changed files detected. Nothing to review.",
                "findings": [],
            }
        )

    config = load_config()
    all_findings: list[dict] = []

    # Tier 1 always runs (free)
    lint_findings = run_linters(
        [os.path.join(repo_path, f) for f in changed if os.path.exists(os.path.join(repo_path, f))]
    )
    all_findings.extend(lint_findings)

    if scope == "instant":
        return json.dumps(
            {
                "success": True,
                "scope": "instant",
                "files_reviewed": len(changed),
                "files": changed,
                "findings": all_findings,
                "linter_findings": len(lint_findings),
            }
        )

    if scope == "quick":
        # Tier 2: inline review
        result_text = run_inline_review(
            [os.path.join(repo_path, f) for f in changed], repo_path, scope=scope
        )
        all_findings.append({"type": "llm_review", "output": result_text})

        return json.dumps(
            {
                "success": True,
                "scope": "quick",
                "files_reviewed": len(changed),
                "files": changed,
                "linter_findings": len(lint_findings),
                "findings": all_findings,
                "review": result_text,
            }
        )

    # Tier 3: full Kanban pipeline
    diff_text = get_diff(repo_path, base_ref)
    pr_description = f"Local diff against {base_ref}\n\n```diff\n{diff_text[:5000]}\n```"

    pipeline = create_kanban_pipeline(
        "local-diff", repo_path, changed, pr_description
    )

    if wait:
        review_result = poll_pipeline(
            pipeline["consolidator_task"], config.get("poll_timeout_seconds", 600)
        )
        all_findings.append({"type": "kanban_review", "output": review_result["result"]})

        return json.dumps(
            {
                "success": review_result["completed"],
                "scope": "full",
                "files_reviewed": len(changed),
                "files": changed,
                "linter_findings": len(lint_findings),
                "linter_issues": lint_findings,
                "pipeline": pipeline,
                "review": review_result["result"],
                "status": review_result["status"],
            }
        )
    else:
        return json.dumps(
            {
                "success": True,
                "scope": "full",
                "files_reviewed": len(changed),
                "files": changed,
                "linter_findings": len(lint_findings),
                "linter_issues": lint_findings,
                "pipeline": pipeline,
                "message": f"Kanban pipeline created. Monitor: hermes kanban list. "
                f"Consolidator: {pipeline['consolidator_task']}",
            }
        )
