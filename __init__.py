"""
Code QA Plugin for Hermes Agent.

Multi-agent code review QA pipeline with three tiers:
  - Tier 1: Instant linters (zero LLM cost)
  - Tier 2: Quick single-pass review (~30s)
  - Tier 3: Full 5-agent Kanban pipeline (~3-5min)

Summon: review_pr(url), review_diff(scope="full"), review_file(path), review_toggle(mode)
"""

from __future__ import annotations

import logging
from typing import Any

__version__ = "1.2.0"
__author__ = "Abdias J (AxDSan)"

logger = logging.getLogger(__name__)


def register(ctx: Any) -> dict[str, Any]:
    """Register Code QA plugin with Hermes.

    Called by Hermes on plugin load. Registers 4 tools + 1 hook.
    """
    from . import tools as _tools_module

    # ── Tools ──
    from .tools.review_pr import SCHEMA as PR_SCHEMA, handler as pr_handler
    from .tools.review_diff import SCHEMA as DIFF_SCHEMA, handler as diff_handler
    from .tools.review_file import SCHEMA as FILE_SCHEMA, handler as file_handler
    from .tools.review_toggle import SCHEMA as TOGGLE_SCHEMA, handler as toggle_handler
    from .tools.triage_issue import SCHEMA as TRIAGE_SCHEMA, handler as triage_handler

    ctx.register_tool(
        name="review_pr",
        toolset="code_qa",
        schema=PR_SCHEMA,
        handler=pr_handler,
    )
    ctx.register_tool(
        name="review_diff",
        toolset="code_qa",
        schema=DIFF_SCHEMA,
        handler=diff_handler,
    )
    ctx.register_tool(
        name="review_file",
        toolset="code_qa",
        schema=FILE_SCHEMA,
        handler=file_handler,
    )
    ctx.register_tool(
        name="review_toggle",
        toolset="code_qa",
        schema=TOGGLE_SCHEMA,
        handler=toggle_handler,
    )
    ctx.register_tool(
        name="triage_issue",
        toolset="code_qa",
        schema=TRIAGE_SCHEMA,
        handler=triage_handler,
    )

    # ── Hooks ──
    from .hooks.post_tool_call import on_post_tool_call

    ctx.register_hook("post_tool_call", on_post_tool_call)

    # ── Check profiles ──
    _check_profiles()

    logger.info("Code QA plugin v%s registered (5 tools, 1 hook)", __version__)

    return {
        "status": "registered",
        "plugin": "code-qa",
        "version": __version__,
        "tools": 5,
        "hooks": 1,
    }


def _check_profiles() -> None:
    """Check if reviewer profiles exist. Log warning if not."""
    from pathlib import Path

    profiles_dir = Path.home() / ".hermes" / "profiles"
    required = [
        "security-reviewer",
        "style-reviewer",
        "logic-reviewer",
        "diff-reviewer",
        "consolidator",
    ]

    missing = [p for p in required if not (profiles_dir / p / "SOUL.md").exists()]

    if missing:
        logger.warning(
            "Code QA: Missing reviewer profiles: %s. "
            "Run: hermes profile create <name> --clone, then install the bundled SOUL.md files.",
            ", ".join(missing),
        )
