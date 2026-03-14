# Planectra

> **Early alpha (v0.1.0)** — This project is under active development. Expect rough edges, breaking changes, and incomplete features. Bug reports and feedback are welcome via [GitHub Issues](https://github.com/ChernovAndrey/Planectra/issues).

Planning conversation tracker with RAG for [Claude Code](https://docs.anthropic.com/en/docs/claude-code).

Claude Code's plan mode produces valuable planning conversations, but this knowledge is lost after each session. Planectra captures planning sessions (conversations + metadata), stores them in a vector database, and uses RAG to surface relevant past plans during new planning sessions.

## How it works

Planectra uses a **hook + MCP hybrid** architecture:

- **Hooks** (automatic, event-driven) — operate directly on config files and session state on disk. Inject RAG context on first plan-mode prompt, record plans on acceptance, check project configuration on session start
- **MCP Server** (interactive, tool-only) — receives structured reflection data from Claude, manages projects, provides semantic search via MCP tools

```
┌──────────────────────────────────┐
│       MCP Server Process         │
│  (local stdio, per-session)      │
│                                  │
│  ┌──────────┐  ┌──────────────┐  │
│  │ ChromaDB │  │ ONNX Embed   │  │
│  │ (SQLite) │  │ MiniLM-L6-v2 │  │
│  └──────────┘  └──────────────┘  │
│                                  │
│  ┌────────────────────────────┐  │
│  │ MCP Tools (stdio)          │  │
│  │ - planectra_finalize_plan  │  │
│  │ - planectra_search_plans   │  │
│  │ - planectra_recent_plans   │  │
│  │ - planectra_init_project   │  │
│  │ - planectra_list_projects  │  │
│  │ - planectra_update_config  │  │
│  └────────────────────────────┘  │
└──────────────────────────────────┘

┌──────────────────────────────────────────────┐
│  Hooks (self-contained, no IPC)              │
│                                              │
│  SessionStart  → config read (~5ms)          │
│  PromptSubmit  → session state + RAG (~2-3s) │
│  ExitPlanMode  → save plan + embed (~2-3s)   │
│                                              │
│  Session state: ~/.planectra/sessions/*.json  │
└──────────────────────────────────────────────┘
```

Hooks operate independently — they read config files and manage session state on disk. ChromaDB is imported lazily only when needed (first plan prompt or plan acceptance). Multiple Claude Code sessions work simultaneously with no conflicts.

**Resource usage:** No background daemon. The MCP server is a child process of Claude Code — it starts when a session begins and exits when it ends. ChromaDB and the embedding model are loaded lazily on first plan-mode use (~150MB RAM). Zero resource usage when Claude Code isn't running.

## Performance

| Operation | Latency | When |
|---|---|---|
| Non-plan prompt | <10ms | Every normal prompt (transcript check, exit) |
| Subsequent plan prompts | ~10ms | Session file read + increment + write |
| First plan prompt (RAG) | ~2-3s | Once per planning session (cold ChromaDB + ONNX) |
| Plan acceptance | ~2-3s | Once per plan (transcript parse + ChromaDB) |

Embeddings run locally on CPU via ONNX Runtime (no GPU required).

## Installation

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/) (recommended) or pip.

### Option 1: Install from GitHub (no clone needed)

```bash
uv tool install git+https://github.com/ChernovAndrey/Planectra
planectra install
```

### Option 2: Install from source

```bash
git clone https://github.com/ChernovAndrey/Planectra.git
cd Planectra
uv tool install -e .
planectra install
```

`planectra install` walks you through setup interactively:

1. Creates `~/.planectra/` directory structure
2. Merges hooks into Claude Code settings (non-destructive)
3. Registers the MCP server via `claude mcp add`
4. Adds Planectra instructions to `CLAUDE.md`
5. Asks you to configure default settings (top_k, verbosity, etc.)
6. Detects existing plans in `~/.claude/plans/` and offers to import them

### Scope: global vs project-local

By default, hooks and settings are installed globally (`~/.claude/`). To install only for the current project:

```bash
planectra install --scope project
```

This writes to `.claude/settings.json` and `.claude/CLAUDE.md` in the current directory instead, leaving your global Claude Code config untouched. With `--scope project`, Planectra also auto-initializes the project for you (no separate `planectra init` needed).

| Flag | Hooks & CLAUDE.md | MCP server | Affects |
|---|---|---|---|
| `--scope global` (default) | `~/.claude/` | global | All Claude Code sessions |
| `--scope project` | `./.claude/` | project | Only sessions in this directory |

To remove:
```bash
planectra uninstall              # or --scope project
uv tool uninstall planectra
```

## Usage

### 1. Initialize a project

Run the CLI in your project directory:

```bash
cd ~/code/my-api
planectra init my-project
```

Then open Claude Code — the SessionStart hook will confirm the project is configured:

```
[Planectra] Project: my-project
```

### 2. Plan as usual

Enter plan mode in Claude Code and start planning. On your first plan-mode prompt, Planectra automatically:
- Searches for similar past plans via vector similarity (across all projects by default)
- Injects relevant context (past drafts, user feedback, reflection data) into the conversation

### 3. After plan acceptance

When you accept a plan (`ExitPlanMode`), Planectra:
- Extracts the planning conversation from the transcript
- Stores the full plan record on disk + embeds it in ChromaDB
- Prompts Claude to call `planectra_finalize_plan` with structured reflection

### 4. Import existing plans

Backfill plans from previous sessions:

```bash
planectra import
```

Imports `~/.claude/plans/*.md` into a default "imported" project with deterministic UUIDs (idempotent — safe to run repeatedly). Imported plans have no conversation or reflection data but their content is indexed for RAG search.

To assign to a specific project:
```bash
planectra import --project <uuid> --name "my-project"
```

## CLI Reference

### `planectra install`

Set up hooks, MCP server, configure defaults, and optionally import existing plans.

```bash
$ planectra install
Created ~/.planectra/ directory structure
Added hooks to ~/.claude/settings.json
Registered MCP server (global)
Added instructions to ~/.claude/CLAUDE.md

Planectra installed successfully!

--- Default settings (inherited by new projects) ---
Press Enter to accept defaults.

Enable RAG context injection? [Y/n]:
Number of similar plans to retrieve (top_k) [3]: 5
RAG verbosity (compact/standard/full) [standard]:
Max RAG tokens [4000]:
Ask user for feedback after plan acceptance? [Y/n]:
Search across all Planectra projects for RAG? (no = current project only) [Y/n]:
Settings saved.

Found 33 existing plan(s) in ~/.claude/plans/. Import them now? [y/N]: y
Imported 33/33 plans (0 already imported, 0 errors)
```

### `planectra uninstall`

Remove hooks and MCP server registration.

```bash
$ planectra uninstall
Removed hooks from ~/.claude/settings.json
Unregistered MCP server
Removed instructions from ~/.claude/CLAUDE.md

Note: ~/.planectra/ data directory preserved. Delete manually if desired.
```

### `planectra init <name>`

Initialize a project for the current directory.

```bash
$ cd ~/code/my-api
$ planectra init my-api
Project 'my-api' initialized (UUID: a1b2c3d4-...)
```

### `planectra projects`

List all configured projects and their directories.

```bash
$ planectra projects
  my-api (a1b2c3d4-...)
    dir: /Users/you/code/my-api
  imported (e5f6a7b8-...)
```

### `planectra search <query>`

Semantic search across all stored plans.

```bash
$ planectra search "caching layer for API"
[87%] my-api: Design a caching mechanism for API responses
     UUID: f1e2d3c4-..., Attempts: 3
[62%] imported: Implement Redis Cache
     UUID: a9b8c7d6-..., Attempts: 1
```

### `planectra recent`

Show the most recent plans.

```bash
$ planectra recent
[Mar 14, 2026 at 10:30 AM] my-api: Add caching layer for API responses
     UUID: f1e2d3c4-..., Attempts: 3
[Mar 13, 2026 at 03:15 PM] mobile-app: Refactor navigation stack
     UUID: a9b8c7d6-..., Attempts: 1
```

Filter by project or change result count:
```bash
$ planectra recent --project a1b2c3d4-... --top-k 10
```

### `planectra show <plan-uuid>`

Show full details of a plan.

```bash
$ planectra show f1e2d3c4-...
Plan f1e2d3c4
Project:  my-api
Created:  Mar 10, 2026 at 02:30 PM
Attempts: 3
Full UUID: f1e2d3c4-...

── Prompt ──────────────────────────────
  Design a caching mechanism for API responses

── Conversation (6 turns) ──────────────

  You [attempt 1]:
  Design a caching mechanism for API responses

  Claude [attempt 1]:
  # Plan v1: Basic Redis cache...

  You [attempt 2]:
  Missing cache invalidation strategy

  Claude [attempt 2]:
  # Plan v2: Redis cache with TTL...
  ...

── Plan ────────────────────────────────
  # Plan v3: Redis cache with per-endpoint TTL...

── Reflection ──────────────────────────
  Issues:       Cache invalidation was missing, didn't consider TTL policies
  Improvements: Added per-endpoint TTL config, separated read/write cache paths
  RAG useful:   Redis caching plan helped with TTL design patterns
```

Use `--json` for full raw output:
```bash
$ planectra show f1e2d3c4-... --json
```

### `planectra import`

Import existing plans from `~/.claude/plans/`.

```bash
$ planectra import
Imported 33/33 plans (0 already imported, 0 errors)

$ planectra import  # safe to re-run
Imported 0/33 plans (33 already imported, 0 errors)
```

### `planectra config <project-uuid>`

View or update project configuration.

```bash
# View current config
$ planectra config a1b2c3d4-...
Project: my-api
  use_rag: True
  top_k: 3
  verbosity: standard
  max_rag_tokens: 4000
  include_user_comment: True

# Update settings
$ planectra config a1b2c3d4-... --verbosity compact --top-k 5 --max-tokens 2000
Project a1b2c3d4-... config updated.
```

### `planectra export`

Export all plans as JSON (for backup or analysis).

```bash
$ planectra export > plans_backup.json
```

## MCP Tools

These tools are available to Claude during a session:

| Tool | Description |
|---|---|
| `planectra_init_project` | Initialize a new project or assign directory to existing one |
| `planectra_list_projects` | List all configured projects |
| `planectra_search_plans` | Semantic search across stored plans |
| `planectra_finalize_plan` | Add structured reflection after plan acceptance |
| `planectra_update_config` | Update project configuration |
| `planectra_recent_plans` | List most recent plans sorted by date |

## RAG Context Format

Retrieved plans are injected as XML with three verbosity levels:

- **compact** (~200-500 tokens/plan) — initial prompt + reflection summary
- **standard** (default, ~1000-2000 tokens/plan) — all drafts + user feedback + reflection
- **full** (~3000-5000 tokens/plan) — complete drafts without truncation

Configure per-project:
```bash
planectra config <uuid> --verbosity compact --max-tokens 2000 --top-k 5
```

## Configuration

### Global defaults (`~/.planectra/config.json`)

Set during `planectra install`. New projects inherit these values.

| Field | Default | Description |
|---|---|---|
| `default_use_rag` | `true` | Enable RAG injection |
| `default_top_k` | `3` | Number of similar plans to retrieve |
| `default_rag_verbosity` | `"standard"` | Detail level: compact / standard / full |
| `default_max_rag_tokens` | `4000` | Token budget for RAG injection (first plan prompt only) |
| `default_include_user_comment` | `true` | Ask user for feedback after plan acceptance |
| `default_scan_all_projects` | `true` | RAG searches across all Planectra projects (false = current project only) |

### Project config (`~/.planectra/projects/<uuid>/config.json`)

Per-project overrides. Created via `planectra init` or `planectra_init_project`.

| Field | Default | Description |
|---|---|---|
| `use_rag` | inherited | Enable RAG injection during planning |
| `top_k` | inherited | Number of similar plans to retrieve |
| `rag_verbosity` | inherited | Detail level: compact / standard / full |
| `max_rag_tokens` | inherited | Token budget cap for RAG injection |
| `include_user_comment` | inherited | Ask user for feedback after plan acceptance |
| `scan_project_ids` | `[self]` | Cross-project RAG search scope (overridden by global `scan_all_projects`) |

## Data Storage

```
~/.planectra/
├── config.json                       # Global config + dir-to-project mapping
├── projects/
│   └── <project-uuid>/
│       ├── config.json               # Project config
│       └── plans/
│           └── <plan-uuid>.json      # Full PlanRecord (source of truth)
├── sessions/                         # Per-session state (auto-cleaned)
│   └── <session-id>.json
└── vectordb/                         # ChromaDB (search index only)
    └── chroma.sqlite3
```

ChromaDB is a search index only — disk JSON files are the single source of truth for all plan data.

## Development

```bash
git clone https://github.com/ChernovAndrey/Planectra.git
cd Planectra
uv venv && uv pip install -e . && uv pip install ruff pytest

# Run tests
pytest tests/ -v

# Lint
ruff check src/ tests/
```

## License

MIT