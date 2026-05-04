"""
Code QA Plugin for Hermes — configuration management.

Reads/writes `code_qa:` section in ~/.hermes/config.yaml.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

DEFAULT_CONFIG: dict[str, Any] = {
    "auto_lint_on_save": True,
    "auto_lint_threshold_lines": 5,
    "default_scope": "quick",
    "tier3_auto_trigger": False,
    "tier3_auto_threshold_files": 3,
    "poll_interval_seconds": 30,
    "poll_timeout_seconds": 600,
    "review_timeout_seconds": 3600,
    "notify_on_complete": True,
}


def get_hermes_home() -> Path:
    """Resolve HERMES_HOME, falling back to ~/.hermes."""
    return Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))


def get_config_path() -> Path:
    """Path to config.yaml."""
    return get_hermes_home() / "config.yaml"


def load_config() -> dict[str, Any]:
    """Load code_qa config section, merging with defaults."""
    import yaml

    config_path = get_config_path()
    config: dict[str, Any] = dict(DEFAULT_CONFIG)

    if config_path.exists():
        try:
            raw = yaml.safe_load(config_path.read_text()) or {}
            user_section = raw.get("code_qa", {})
            if isinstance(user_section, dict):
                config.update(user_section)
        except Exception:
            pass

    return config


def save_config(config: dict[str, Any]) -> bool:
    """Save code_qa config section back to config.yaml."""
    import yaml

    config_path = get_config_path()

    try:
        if config_path.exists():
            raw = yaml.safe_load(config_path.read_text()) or {}
        else:
            raw = {}
    except Exception:
        raw = {}

    raw["code_qa"] = config

    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(yaml.dump(raw, default_flow_style=False, sort_keys=False))
        return True
    except Exception:
        return False


def is_enabled() -> bool:
    """Check if auto-review is enabled."""
    cfg = load_config()
    return bool(cfg.get("auto_lint_on_save", True))
