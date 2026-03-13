# Planectra

Planning conversation tracker with RAG for [Claude Code](https://docs.anthropic.com/en/docs/claude-code).

Claude Code's plan mode produces valuable planning conversations, but this knowledge is lost after each session. Planectra captures planning sessions (conversations + metadata), stores them in a vector database, and uses RAG to surface relevant past plans during new planning sessions.

## How it works

Planectra uses a **hook + MCP hybrid** architecture:

- **Hooks** (automatic, event-driven) — inject RAG context on every plan-mode prompt, detect plan acceptance, check project configuration on session start
- **MCP Server** (interactive, long-running) — receives structured reflection data from Claude, manages projects, keeps ChromaDB warm in memory for fast vector search

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
│  │ - planectra_init_project   │  │
│  │ - planectra_list_projects  │  │
│  │ - planectra_update_config  │  │
│  └────────────────────────────┘  │
│                                  │
│  ┌────────────────────────────┐  │
│  │ IPC Socket Server (thread) │  │
│  │ ~/.planectra/planectra.sock│  │
│  └────────────────────────────┘  │
└──────────────────────────────────┘
         ▲              ▲
         │              │  Unix Socket
  ┌──────┘              └──────┐
  │                            │
┌─────────────┐      ┌──────────────────┐
│ Hook:       │      │ Hook:            │
│ prompt      │      │ plan_exit /      │
│ (RAG inject)│      │ session          │
└─────────────┘      └──────────────────┘
```

Hooks are thin IPC clients (~20 lines) that talk to the MCP server via a Unix domain socket. The MCP server keeps ChromaDB and the embedding model in memory, avoiding cold-start latency on every prompt.

## Performance

| Operation | Latency | When |
|---|---|---|
| Non-plan prompt | <10ms | Every normal prompt (local check, exits) |
| First plan prompt (RAG) | ~200-400ms | First prompt in plan mode |
| Subsequent plan prompts | ~50ms | Increments counter only |
| Plan acceptance | ~500-1000ms | Transcript parse + embed + store |

Embeddings run locally on CPU via ONNX Runtime (~150MB total RAM, no GPU required).

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

`planectra install` does four things:
1. Creates `~/.planectra/` directory structure
2. Merges hooks into `~/.claude/settings.json` (non-destructive)
3. Registers the MCP server via `claude mcp add`
4. Adds Planectra instructions to `~/.claude/CLAUDE.md`

### Scope: global vs project-local

By default, hooks and settings are installed globally (`~/.claude/`). To install only for the current project:

```bash
planectra install --scope project
```

This writes to `.claude/settings.json` and `.claude/CLAUDE.md` in the current directory instead, leaving your global Claude Code config untouched.

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

Open Claude Code in your project directory and let the `SessionStart` hook prompt you, or run manually:

```bash
planectra init my-project
```

### 2. Plan as usual

Enter plan mode in Claude Code and start planning. On your first plan-mode prompt, Planectra automatically:
- Searches for similar past plans via vector similarity
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
planectra import --project <uuid> --name "my-project"
```

Imports `~/.claude/plans/*.md` with deterministic UUIDs (idempotent — safe to run repeatedly).

## CLI Reference

```
planectra install        Install hooks and MCP server
planectra uninstall      Remove hooks and MCP server
planectra init <name>    Initialize a project in the current directory
planectra projects       List all configured projects
planectra search <query> Semantic search across stored plans
planectra import         Import existing plans from ~/.claude/plans/
planectra config <uuid>  View or update project configuration
planectra export         Export all plans as JSON
```

## MCP Tools

These tools are available to Claude during a session:

| Tool | Description |
|---|---|
| `planectra_init_project` | Initialize a new project for plan tracking |
| `planectra_list_projects` | List all configured projects |
| `planectra_search_plans` | Semantic search across stored plans |
| `planectra_finalize_plan` | Add structured reflection after plan acceptance |
| `planectra_update_config` | Update project configuration |

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

### Project config (`~/.planectra/projects/<uuid>/config.json`)

| Field | Default | Description |
|---|---|---|
| `use_rag` | `true` | Enable RAG injection during planning |
| `top_k` | `3` | Number of similar plans to retrieve |
| `rag_verbosity` | `"standard"` | Detail level: compact / standard / full |
| `max_rag_tokens` | `4000` | Token budget cap for RAG injection |
| `include_user_comment` | `true` | Ask user for feedback after plan acceptance |
| `scan_project_ids` | `[self]` | Cross-project RAG search scope |

## Data Storage

```
~/.planectra/
├── config.json                       # Global config
├── projects/
│   └── <project-uuid>/
│       ├── config.json               # Project config
│       └── plans/
│           └── <plan-uuid>.json      # Full PlanRecord (source of truth)
├── vectordb/                         # ChromaDB (search index only)
│   └── chroma.sqlite3
└── planectra.sock                    # Unix socket (runtime)
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
