# Hermes Code QA

Autonomous multi-agent code review QA pipeline for [Hermes Agent](https://github.com/NousResearch/hermes-agent).

**Three tiers of review quality:**

| Tier | Method | Latency | Cost | Use Case |
|------|--------|---------|------|----------|
| **1 — Instant** | Linters (ruff, eslint, shellcheck) | <1s | $0 | Every file save |
| **2 — Quick** | Single-pass LLM review | ~30s | ~$0.01 | Medium changes |
| **3 — Full** | 5-agent Kanban pipeline | ~5min | ~$0.10 | Features, PRs, releases |

## Install

```bash
# Clone into Hermes plugins
git clone https://github.com/AxDSan/hermes-code-qa ~/.hermes/plugins/code-qa

# Enable it
hermes plugins enable code-qa

# Create reviewer profiles (first time only)
hermes profile create security-reviewer --clone
hermes profile create style-reviewer --clone
hermes profile create logic-reviewer --clone
hermes profile create diff-reviewer --clone
hermes profile create consolidator --clone

# Copy the bundled SOUL.md personas
cp ~/.hermes/plugins/code-qa/profiles/security-reviewer/SOUL.md ~/.hermes/profiles/security-reviewer/
cp ~/.hermes/plugins/code-qa/profiles/style-reviewer/SOUL.md ~/.hermes/profiles/style-reviewer/
cp ~/.hermes/plugins/code-qa/profiles/logic-reviewer/SOUL.md ~/.hermes/profiles/logic-reviewer/
cp ~/.hermes/plugins/code-qa/profiles/diff-reviewer/SOUL.md ~/.hermes/profiles/diff-reviewer/
cp ~/.hermes/plugins/code-qa/profiles/consolidator/SOUL.md ~/.hermes/profiles/consolidator/

# Gateway must be running for Kanban dispatch
hermes gateway status
```

## Usage

### Tools available in any Hermes session:

**review_diff** — Review uncommitted changes in current directory
```
review_diff(scope="quick")       # Tier 2, ~30s
review_diff(scope="full")        # Tier 3, 5-agent pipeline
review_diff(scope="instant")     # Tier 1, linters only
```

**review_pr** — Review a GitHub pull request
```
review_pr(url="https://github.com/owner/repo/pull/42")
review_pr(url="...", scope="full", wait=true)
```

**review_file** — Review a single file
```
review_file(path="src/auth.ts")
review_file(path="src/auth.ts", scope="instant")
```

**review_toggle** — Toggle auto-review modes
```
review_toggle(mode="status")     # Show current config
review_toggle(mode="auto")       # Enable lint-on-save
review_toggle(mode="off")        # Disable everything
```

### Summon from chat (natural language):
- "review PR https://github.com/AxDSan/mnemosyne/pull/22"
- "tier 3 review what I just wrote"
- "quick review src/auth.ts"
- "run full QA on my changes"

## Architecture

```
You say "review PR url"
        │
        ▼
┌─────────────────┐     ┌──────────────────────────┐
│  Hermes Session │────▶│  review_pr() tool         │
│  (you)          │     │  - clones repo            │
└─────────────────┘     │  - extracts diff           │
                        │  - creates Kanban tasks    │
                        └─────────┬────────────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼             ▼
           ┌──────────┐  ┌──────────┐  ┌──────────────┐
           │ security │  │  style   │  │    logic     │ ... 4 reviewers
           │ reviewer │  │ reviewer │  │  reviewer    │
           └────┬─────┘  └────┬─────┘  └──────┬───────┘
                │              │               │
                └──────────────┼───────────────┘
                               ▼
                    ┌──────────────────┐
                    │  consolidator    │  ← auto-starts when all 4 done
                    │  (merges +       │
                    │   formats)       │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │  Final Report    │
                    │  (Markdown)      │
                    └──────────────────┘
```

### The 5 specialist profiles:

- **security-reviewer** — Secrets, injection, auth, env vars, CVE deps
- **style-reviewer** — Conventions, patterns, anti-patterns, structure
- **logic-reviewer** — Edge cases, null handling, state transitions, spec compliance
- **diff-reviewer** — Breaking changes, missed callers, impact radius
- **consolidator** — Cross-references, deduplicates, filters, formats final report

## Config

Write to `~/.hermes/config.yaml` under `code_qa:`:

```yaml
code_qa:
  auto_lint_on_save: true          # Run linters on every file write
  auto_lint_threshold_lines: 5     # Min lines to trigger auto-lint
  default_scope: quick             # quick | full | instant
  tier3_auto_trigger: false        # Auto full pipeline for features
  tier3_auto_threshold_files: 3    # Min files changed to auto-trigger
  poll_interval_seconds: 30        # How often to check Kanban status
  poll_timeout_seconds: 600        # Max wait for full review
```

## Requirements

- **Hermes Agent v0.12.0+** (for Kanban system)
- **Gateway running** (for Kanban dispatcher)
- **Profiles created** with bundled SOUL.md personas
- Linters are optional (silently skipped if not installed):
  - `ruff` for Python
  - `eslint` for TypeScript/JavaScript
  - `shellcheck` for shell scripts
  - `cargo clippy` for Rust
  - `go vet` for Go

## License

MIT

## Author

Abdias J (AxDSan)
