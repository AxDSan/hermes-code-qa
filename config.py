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
    # ── Triage (auto-assign + auto-label for Issues/PRs) ──
    "triage_enabled": True,
    "triage_assignee": None,           # GitHub username to assign. null = auto-detect from gh auth status
    "triage_auto_assign": True,        # Auto-assign issues/PRs to triage_assignee
    "triage_auto_label": True,         # Auto-apply labels based on title/body keywords
    "triage_min_contributors_for_skip": 3,  # Skip auto-assign if repo has this many contributors
    "triage_min_others_for_skip": 2,   # Skip auto-assign if this many non-owner humans exist
    # Override the built-in label map. Empty dict = use built-in defaults.
    "triage_label_map": {},
    # Example custom label map:
    # triage_label_map:
    #   bug: ["bug", "type: bug"]
    #   security: ["security", "priority: critical"]
}

# ── Built-in triage label map (used when triage_label_map config is empty) ──

BUILTIN_TRIAGE_LABEL_MAP: dict[str, list[str]] = {
    "bug": ["bug", "type: bug"],
    "fix": ["bug", "type: bug"],
    "crash": ["bug", "type: bug", "priority: critical"],
    "security": ["security", "type: security", "priority: critical"],
    "vulnerability": ["security", "type: security", "priority: critical"],
    "feature": ["enhancement", "type: feature"],
    "enhancement": ["enhancement", "type: feature"],
    "docs": ["documentation", "type: docs"],
    "documentation": ["documentation", "type: docs"],
    "readme": ["documentation", "type: docs"],
    "refactor": ["refactor", "type: chore"],
    "test": ["testing", "type: test"],
    "ci": ["ci/cd", "type: ci"],
    "performance": ["performance", "type: performance"],
    "slow": ["performance", "type: performance"],
    "ux": ["ux", "type: ux"],
    "css": ["ux", "type: ux", "scope: frontend"],
    "ui": ["ux", "type: ux", "scope: frontend"],
    "api": ["scope: api"],
    "dependency": ["dependencies", "type: chore"],
    "deps": ["dependencies", "type: chore"],
}


def resolve_triage_assignee(config: dict[str, Any]) -> str | None:
    """Resolve the triage assignee from config, falling back to gh auth status."""
    assignee = config.get("triage_assignee")
    if assignee:
        return assignee
    # Auto-detect from gh auth
    try:
        import subprocess
        result = subprocess.run(
            "gh auth status 2>&1 | grep -oP 'Logged in to github\\.com account \\K\\w+'",
            shell=True, capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


def resolve_triage_label_map(config: dict[str, Any]) -> dict[str, list[str]]:
    """Resolve triage label map: user config overrides built-in defaults."""
    custom = config.get("triage_label_map") or {}
    # Empty dict means use built-ins entirely
    if not custom:
        return dict(BUILTIN_TRIAGE_LABEL_MAP)
    # Merge: user entries override built-in entries, plus new ones
    merged = dict(BUILTIN_TRIAGE_LABEL_MAP)
    merged.update(custom)
    return merged


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
