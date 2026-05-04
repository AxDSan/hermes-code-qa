"""
review_toggle tool — Enable/disable auto-review modes.
"""

from __future__ import annotations

import json
from typing import Any

from ..config import load_config, save_config

SCHEMA: dict[str, Any] = {
    "name": "review_toggle",
    "description": "Toggle Code QA auto-review modes. 'auto' = linters run on every file save. 'off' = completely disabled. 'status' = show current settings. Call with no mode to show current status.",
    "parameters": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["auto", "off", "status"],
                "description": "Mode to set: 'auto' enables lint-on-save, 'off' disables everything, 'status' shows current config.",
            },
        },
        "required": [],
    },
}


def handler(args: dict[str, Any], **kwargs) -> str:
    """Handle review_toggle tool call."""
    mode = args.get("mode", "status")

    config = load_config()

    if mode == "status":
        return json.dumps(
            {
                "success": True,
                "config": {
                    "auto_lint_on_save": config.get("auto_lint_on_save", True),
                    "auto_lint_threshold_lines": config.get("auto_lint_threshold_lines", 5),
                    "default_scope": config.get("default_scope", "quick"),
                    "tier3_auto_trigger": config.get("tier3_auto_trigger", False),
                },
            }
        )

    if mode == "auto":
        config["auto_lint_on_save"] = True
        save_config(config)
        return json.dumps(
            {
                "success": True,
                "mode": "auto",
                "message": "Auto-lint enabled. Linters will run on every file save.",
            }
        )

    if mode == "off":
        config["auto_lint_on_save"] = False
        save_config(config)
        return json.dumps(
            {
                "success": True,
                "mode": "off",
                "message": "All Code QA automation disabled. Use review_diff/review_file/review_pr manually.",
            }
        )

    return json.dumps({"success": False, "error": f"Unknown mode: {mode}"})
