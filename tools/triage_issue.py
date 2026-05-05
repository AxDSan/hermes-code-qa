"""
triage_issue tool — Auto-assign + auto-label GitHub issues.

Runs the triage workflow: assigns the default maintainer (unless team active),
applies relevant labels based on issue content, then returns the triage summary.
"""

from __future__ import annotations

import json
from typing import Any

from ..orchestrator import triage_issue, _extract_repo_from_url

SCHEMA: dict[str, Any] = {
    "name": "triage_issue",
    "description": "Triage a GitHub issue: auto-assign to the default maintainer (unless other active contributors exist) and auto-apply labels based on issue title/body keywords. Use when you spot an unlabeled, unassigned issue that needs attention.",
    "parameters": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "GitHub issue URL to triage (e.g., https://github.com/owner/repo/issues/42)",
            },
        },
        "required": ["url"],
    },
}


def handler(args: dict[str, Any], **kwargs) -> str:
    """Handle triage_issue tool call."""
    url = args.get("url", "")

    if not url:
        return json.dumps({"success": False, "error": "No issue URL provided."})

    repo_info = _extract_repo_from_url(url)
    if not repo_info:
        return json.dumps(
            {
                "success": False,
                "error": f"Could not parse owner/repo/number from URL: {url}",
            }
        )

    repo_full, number = repo_info

    try:
        result = triage_issue(repo_full, number, is_pr="pull" in url)
        return json.dumps({"success": True, "triage": result})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e), "triage": None})
