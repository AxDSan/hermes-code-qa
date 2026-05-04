"""
Code QA Plugin — Orchestrator: Kanban pipeline creation, polling, inline review.

Called by tool handlers to create and manage code review workflows.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Any

from .config import load_config, get_hermes_home

# ───────────────────────────────────────────────────────────────
# Constants
# ───────────────────────────────────────────────────────────────

KANBAN_DB = get_hermes_home() / "kanban.db"

PROFILES = {
    "security": "security-reviewer",
    "style": "style-reviewer",
    "logic": "logic-reviewer",
    "impact": "diff-reviewer",
    "consolidator": "consolidator",
}

# ───────────────────────────────────────────────────────────────
# Kanban helpers
# ───────────────────────────────────────────────────────────────


def _kanban(cmd: str, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a hermes kanban command."""
    full_cmd = f"hermes kanban {cmd}"
    return subprocess.run(
        full_cmd, shell=True, capture_output=True, text=True, timeout=timeout
    )


def _kanban_init() -> bool:
    """Ensure kanban.db exists."""
    result = _kanban("init")
    return result.returncode == 0


def _kanban_create(
    title: str,
    assignee: str,
    body: str,
    priority: str = "medium",
    skills: list[str] | None = None,
) -> str | None:
    """Create a kanban task. Returns task ID or None."""
    body_escaped = shlex.quote(body)
    title_escaped = shlex.quote(title)

    # Map string priorities to numeric (higher = more important)
    priority_map = {"critical": 200, "high": 100, "medium": 50, "low": 10}
    priority_num = priority_map.get(priority, 50)

    cmd = (
        f"create {title_escaped} "
        f"--assignee {assignee} "
        f"--body {body_escaped} "
        f"--priority {priority_num}"
    )
    if skills:
        for s in skills:
            cmd += f" --skill {shlex.quote(s)}"

    result = _kanban(cmd)
    if result.returncode != 0:
        return None

    # Parse task ID from output: "Created t_8f7af075  (ready, assignee=...)"
    output = result.stdout + result.stderr
    match = re.search(r"Created\s+(t_[a-f0-9]+)", output)
    if match:
        return match.group(1)

    # Fallback: try to extract any t_ hex ID
    match = re.search(r"\b(t_[a-f0-9]+)\b", output)
    return match.group(1) if match else None


def _kanban_link(parent_id: str, child_id: str) -> bool:
    """Add dependency link."""
    result = _kanban(f"link {parent_id} {child_id}")
    return result.returncode == 0


def _kanban_show(task_id: str) -> dict[str, Any] | None:
    """Get task details."""
    result = _kanban(f"show {task_id}")
    if result.returncode != 0:
        return None
    output = result.stdout

    # Parse the show output
    info: dict[str, Any] = {"raw": output, "task_id": task_id}

    for line in output.split("\n"):
        line = line.strip()
        if line.startswith("status:"):
            info["status"] = line.split(":", 1)[1].strip().lower()
        elif line.startswith("assignee:"):
            info["assignee"] = line.split(":", 1)[1].strip()

    return info


def _get_task_status_from_db(task_id: str) -> str:
    """Get task status directly from SQLite (faster than CLI)."""
    if not KANBAN_DB.exists():
        return "unknown"
    try:
        conn = sqlite3.connect(str(KANBAN_DB))
        cur = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else "unknown"
    except Exception:
        return "unknown"


def _get_task_result_from_db(task_id: str) -> str | None:
    """Get task result/body from SQLite."""
    if not KANBAN_DB.exists():
        return None
    try:
        conn = sqlite3.connect(str(KANBAN_DB))
        # Check result field first, then latest comment
        cur = conn.execute("SELECT result FROM tasks WHERE id = ?", (task_id,))
        row = cur.fetchone()
        if row and row[0]:
            conn.close()
            return row[0]

        # Fallback to comments
        cur = conn.execute(
            "SELECT body FROM task_comments WHERE task_id = ? ORDER BY created_at DESC LIMIT 1",
            (task_id,),
        )
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


# ───────────────────────────────────────────────────────────────
# Tier 1: Linters (instant, no LLM)
# ───────────────────────────────────────────────────────────────


def _get_linter_for_file(filepath: str) -> list[str] | None:
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


def run_linters(file_paths: list[str]) -> list[dict[str, Any]]:
    """Run linters on a list of files. Returns findings."""
    findings: list[dict[str, Any]] = []
    for fp in file_paths:
        if not os.path.exists(fp):
            continue
        cmd = _get_linter_for_file(fp)
        if cmd is None:
            continue
        try:
            full_cmd = cmd + [fp]
            result = subprocess.run(full_cmd, capture_output=True, text=True, timeout=30)
            output = (result.stdout + result.stderr).strip()
            if output:
                findings.append(
                    {
                        "file": fp,
                        "linter": cmd[0],
                        "severity": "INFO",
                        "output": output[:2000],
                        "exit_code": result.returncode,
                    }
                )
        except subprocess.TimeoutExpired:
            findings.append(
                {
                    "file": fp,
                    "linter": cmd[0],
                    "severity": "INFO",
                    "output": "Linter timed out",
                    "exit_code": -1,
                }
            )
        except Exception as e:
            findings.append(
                {
                    "file": fp,
                    "linter": cmd[0],
                    "severity": "INFO",
                    "output": str(e),
                    "exit_code": -1,
                }
            )

    return findings


# ───────────────────────────────────────────────────────────────
# Tier 2: Quick inline review (single-pass, no Kanban)
# ───────────────────────────────────────────────────────────────


def run_inline_review(
    file_paths: list[str],
    repo_path: str,
    pr_context: str = "",
    scope: str = "quick",
) -> str:
    """Run a single-pass review via `hermes chat -q`.

    Faster than the full Kanban pipeline. Good for medium changes.
    """
    file_list = "\n".join(f"- {fp}" for fp in file_paths)
    prompt = f"""You are a code reviewer. Review the following files for bugs, security issues, 
edge cases, and logical errors. Be concise and direct. For each finding, include:
- File and line (if determinable)
- Severity: CRITICAL | HIGH | MEDIUM | LOW
- One-line description
- Suggested fix

Scope: {scope}
Files changed:
{file_list}

Repository path: {repo_path}
{pr_context}

Read each file, analyze it, and return your findings. If no issues found, say "No issues detected."
"""

    try:
        cmd = f"hermes chat -q {shlex.quote(prompt)}"
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=300
        )
        return result.stdout.strip() or "Review produced no output."
    except subprocess.TimeoutExpired:
        return "Review timed out after 5 minutes."
    except Exception as e:
        return f"Review failed: {e}"


# ───────────────────────────────────────────────────────────────
# Tier 3: Full Kanban pipeline
# ───────────────────────────────────────────────────────────────


def create_kanban_pipeline(
    pr_url: str,
    repo_path: str,
    changed_files: list[str],
    pr_description: str = "",
) -> dict[str, Any]:
    """Create the full 5-agent Kanban review pipeline.

    Returns dict with task IDs and status.
    """
    _kanban_init()

    file_list_str = "\n".join(f"- {f}" for f in changed_files)
    short_files = ", ".join(changed_files[:10])
    if len(changed_files) > 10:
        short_files += f" (+{len(changed_files) - 10} more)"

    pr_num = _extract_pr_number(pr_url)

    # Task bodies
    security_body = f"""Review PR #{pr_num} at {pr_url}.

Repository cloned at: {repo_path}
Changed files:
{file_list_str}

PR Description: {pr_description}

YOUR JOB: Scan every changed file for security vulnerabilities.
Check: hardcoded secrets, SQL injection, XSS, unsafe deserialization,
missing auth checks, exposed env vars, insecure dependencies.
Read the full diff, not just changed lines. Check callers and context.

Output per your SOUL.md format. Be thorough but concise."""

    style_body = f"""Review PR #{pr_num} at {pr_url}.

Repository cloned at: {repo_path}
Changed files:
{file_list_str}

YOUR JOB: Check code style, patterns, and conventions.
Look at the project's conventions (AGENTS.md, CLAUDE.md, configs).
Flag: inconsistent naming, deep nesting, god functions, missing error handling,
mixed patterns, magic numbers, commented-out code, TODO cruft, duplication.
Verify file structure matches project conventions.

Output per your SOUL.md format."""

    logic_body = f"""Review PR #{pr_num} at {pr_url}.

Repository cloned at: {repo_path}
Changed files:
{file_list_str}

PR Description: {pr_description}

YOUR JOB: Review for logical correctness and business rule compliance.
Read project docs (AGENTS.md, specs) to understand requirements.
Flag: missing edge cases, race conditions, incorrect state transitions,
broken assumptions, null/undefined gaps, boundary errors, off-by-one.
Check: does this change actually solve the problem?

Output per your SOUL.md format."""

    impact_body = f"""Analyze change impact for PR #{pr_num} at {pr_url}.

Repository cloned at: {repo_path}
Changed files:
{file_list_str}

YOUR JOB: Map the blast radius of these changes.
For every changed function/signature/type: find all callers and consumers.
Flag: breaking API changes, renamed exports, moved files, changed default values.
Check: deprecated things removed without migration? Tests cover changed paths?
Use grep/search to find all callers. Never assume.

Output per your SOUL.md format."""

    # Create review tasks
    sec_id = _kanban_create(
        f"Security: PR #{pr_num}", PROFILES["security"], security_body, "high"
    )
    sty_id = _kanban_create(
        f"Style: PR #{pr_num}", PROFILES["style"], style_body, "medium"
    )
    log_id = _kanban_create(
        f"Logic: PR #{pr_num}", PROFILES["logic"], logic_body, "high"
    )
    imp_id = _kanban_create(
        f"Impact: PR #{pr_num}", PROFILES["impact"], impact_body, "medium"
    )

    review_ids = [tid for tid in [sec_id, sty_id, log_id, imp_id] if tid]

    # Create consolidator
    parent_ids_str = " ".join(review_ids)
    cons_body = f"""Consolidate code review findings for PR #{pr_num} at {pr_url}.

Parent review tasks: {parent_ids_str}
Repository: {repo_path}

YOUR JOB: Read the outputs of all 4 parent review tasks (security, style, logic, impact).
1. Cross-reference findings: merge duplicates
2. Remove false positives with brief notes
3. Sort by severity: CRITICAL/BREAKING first
4. Add summary: total findings, severity breakdown, overall verdict
5. Format as clean markdown for a PR comment

Output per your SOUL.md format."""

    cons_id = _kanban_create(
        f"Consolidate: PR #{pr_num}", PROFILES["consolidator"], cons_body, "high"
    )

    # Link dependencies
    if cons_id:
        for rid in review_ids:
            _kanban_link(rid, cons_id)

    return {
        "pr_url": pr_url,
        "repo_path": repo_path,
        "files_count": len(changed_files),
        "review_tasks": review_ids,
        "consolidator_task": cons_id,
        "files": short_files,
    }


def poll_pipeline(consolidator_id: str, timeout: int = 600) -> dict[str, Any]:
    """Poll kanban.db until consolidator task completes or timeout.

    Returns {"completed": bool, "result": str, "status": str}
    """
    config = load_config()
    interval = config.get("poll_interval_seconds", 30)
    start = time.time()

    while time.time() - start < timeout:
        status = _get_task_status_from_db(consolidator_id)

        if status == "done":
            result = _get_task_result_from_db(consolidator_id)
            return {"completed": True, "result": result or "", "status": "done"}

        if status in ("blocked", "crashed", "timed_out", "failed"):
            result = _get_task_result_from_db(consolidator_id)
            return {
                "completed": False,
                "result": result or f"Task {status}",
                "status": status,
            }

        time.sleep(interval)

    # Timeout
    result = _get_task_result_from_db(consolidator_id)
    return {
        "completed": False,
        "result": result or "Review timed out waiting for consolidator.",
        "status": _get_task_status_from_db(consolidator_id) or "running",
    }


# ───────────────────────────────────────────────────────────────
# Git helpers
# ───────────────────────────────────────────────────────────────


def _extract_pr_number(url: str) -> str:
    """Extract PR number from GitHub URL."""
    match = re.search(r"/pull/(\d+)", url)
    return match.group(1) if match else "?"


def get_changed_files(repo_path: str, base_ref: str = "HEAD") -> list[str]:
    """Get list of changed files in a repo."""
    try:
        result = subprocess.run(
            f"cd {shlex.quote(repo_path)} && git diff --name-only {base_ref}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
        files = [f.strip() for f in result.stdout.split("\n") if f.strip()]
        return files
    except Exception:
        return []


def get_diff(repo_path: str, base_ref: str = "HEAD") -> str:
    """Get git diff as text."""
    try:
        result = subprocess.run(
            f"cd {shlex.quote(repo_path)} && git diff {base_ref}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def clone_pr(pr_url: str) -> tuple[str, str] | None:
    """Clone a PR repo to /tmp. Returns (repo_path, pr_number) or None."""
    pr_num = _extract_pr_number(pr_url)
    if pr_num == "?":
        return None

    # Parse owner/repo from URL
    match = re.search(r"github\.com/([^/]+/[^/]+)", pr_url)
    if not match:
        return None

    repo_full = match.group(1)
    repo_name = repo_full.split("/")[-1]
    clone_path = f"/tmp/review-pr-{pr_num}-{repo_name}"

    try:
        # Remove if exists
        subprocess.run(f"rm -rf {shlex.quote(clone_path)}", shell=True, timeout=10)

        # Shallow clone
        clone_cmd = (
            f"git clone --depth=1 https://github.com/{repo_full}.git "
            f"{shlex.quote(clone_path)} 2>&1"
        )
        result = subprocess.run(clone_cmd, shell=True, capture_output=True, text=True, timeout=60)

        if result.returncode != 0:
            return None

        # Fetch the PR branch
        fetch_cmd = (
            f"cd {shlex.quote(clone_path)} && "
            f"git fetch origin pull/{pr_num}/head:pr-{pr_num} 2>&1 && "
            f"git checkout pr-{pr_num} 2>&1"
        )
        subprocess.run(fetch_cmd, shell=True, capture_output=True, text=True, timeout=30)

        return clone_path, pr_num
    except Exception:
        return None
