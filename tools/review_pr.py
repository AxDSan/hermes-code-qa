"""
review_pr tool — Full Tier 3 Kanban pipeline for GitHub PR review.
"""

from __future__ import annotations

import json
from typing import Any

from ..orchestrator import (
    clone_pr,
    create_kanban_pipeline,
    get_changed_files,
    poll_pipeline,
    run_inline_review,
    triage_issue,
    _extract_repo_from_url,
)
from ..config import load_config

SCHEMA: dict[str, Any] = {
    "name": "review_pr",
    "description": "Review a GitHub pull request using the Code QA pipeline. Runs auto-triage first (assigns to maintainer unless active team exists, applies labels based on content), then proceeds with review. For small PRs (<10 files), use scope='quick' for faster results. For large PRs or features, use scope='full' for the complete 5-agent Kanban pipeline.",
    "parameters": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "GitHub PR URL to review (e.g., https://github.com/owner/repo/pull/42)",
            },
            "scope": {
                "type": "string",
                "enum": ["quick", "full"],
                "description": "Review depth: 'quick' = single-pass (~30s), 'full' = 5-agent Kanban pipeline (~3-5min). Default: 'quick'.",
                "default": "quick",
            },
            "wait": {
                "type": "boolean",
                "description": "Wait for results (true) or return task IDs immediately (false). Default: true.",
                "default": True,
            },
        },
        "required": ["url"],
    },
}


def handler(args: dict[str, Any], **kwargs) -> str:
    """Handle review_pr tool call."""
    url = args.get("url", "")
    scope = args.get("scope", "quick")
    wait = args.get("wait", True)

    if not url:
        return json.dumps({"success": False, "error": "No PR URL provided."})

    # ── Triage: auto-assign + auto-label ──
    triage_result = None
    repo_info = _extract_repo_from_url(url)
    if repo_info:
        repo_full, pr_num = repo_info
        try:
            triage_result = triage_issue(repo_full, pr_num, is_pr=True)
        except Exception:
            pass

    # Clone the PR
    clone_result = clone_pr(url)
    if clone_result is None:
        return json.dumps(
            {
                "success": False,
                "error": f"Failed to clone PR from {url}. Check the URL and ensure the repo is public.",
                "triage": triage_result,
            }
        )

    repo_path, pr_num = clone_result

    # Get changed files
    changed = get_changed_files(repo_path)
    if not changed:
        return json.dumps(
            {
                "success": False,
                "error": "No changed files found in the PR. The PR may be empty or already merged.",
            }
        )

    # Get PR description from GitHub
    pr_description = ""
    try:
        import subprocess
        import shlex

        result = subprocess.run(
            f"gh pr view {pr_num} --repo {_extract_repo(url)} --json body -q .body 2>/dev/null",
            shell=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            pr_description = result.stdout.strip()[:3000]
    except Exception:
        pass

    config = load_config()

    if scope == "quick" or len(changed) <= 3:
        # Tier 2: inline review
        result_text = run_inline_review(
            changed, repo_path, pr_context=f"PR #{pr_num}: {pr_description}"
        )
        return json.dumps(
            {
                "success": True,
                "scope": "quick",
                "pr_url": url,
                "files_reviewed": len(changed),
                "review": result_text,
                "triage": triage_result,
            }
        )

    # Tier 3: full Kanban pipeline
    pipeline = create_kanban_pipeline(url, repo_path, changed, pr_description)

    if wait:
        review_result = poll_pipeline(
            pipeline["consolidator_task"], config.get("poll_timeout_seconds", 600)
        )
        return json.dumps(
            {
                "success": review_result["completed"],
                "scope": "full",
                "pr_url": url,
                "files_reviewed": len(changed),
                "pipeline": pipeline,
                "review": review_result["result"],
                "status": review_result["status"],
                "triage": triage_result,
            }
        )
    else:
        return json.dumps(
            {
                "success": True,
                "scope": "full",
                "pr_url": url,
                "files_reviewed": len(changed),
                "pipeline": pipeline,
                "message": f"Kanban pipeline created. Monitor with: hermes kanban list. "
                f"Consolidator task: {pipeline['consolidator_task']}",
                "triage": triage_result,
            }
        )


def _extract_repo(url: str) -> str:
    """Extract owner/repo from GitHub URL."""
    import re

    match = re.search(r"github\.com/([^/]+/[^/]+)", url)
    return match.group(1) if match else ""
