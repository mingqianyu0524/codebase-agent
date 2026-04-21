# Codebase Knowledge Agent — HMOS AI Engine BLE 协同仲裁模块

A Python-based agent that uses **Codebase-Memory** (structural analysis) + **LLM** (semantic annotation) to construct a layered knowledge base from source code. This instance targets the **HMOS AI Engine BLE collaborative arbitration module** (TypeScript).

## Overview

The agent builds a three-layer knowledge base:

| Layer | Tool | Output |
|-------|------|--------|
| Layer 1: Skeleton | Codebase-Memory CLI | Architecture, file tree, symbol graph |
| Layer 2: Annotations | Kimi via internal API | Per-file markdown docs with design notes |
| Layer 3: Workflows | Kimi via internal API | End-to-end flow docs with Mermaid diagrams |

> **Note on code quality:** The target codebase has sparse comments. Annotation prompts are specifically tuned to infer intent from function naming, call graphs, and BLE domain knowledge. Inferred content is explicitly marked in annotations.

## Project Structure

```
codebase-agent/
├── CLAUDE.md                          # Project instructions
├── agent_config.yaml                  # LLM + paths config
├── src/
│   ├── llm_client.py                  # OpenAI-compatible LLM wrapper (Kimi)
│   ├── cbm_client.py                  # Codebase-Memory CLI wrapper
│   ├── annotator.py                   # Layer 2: annotation pipeline
│   ├── workflow_exporter.py           # Layer 3: workflow doc generation
│   ├── context_manager.py             # Context retrieval for Q&A
│   ├── cli.py                         # Interactive CLI
│   └── prompt_templates.py            # All prompt templates
├── knowledge-base/
│   └── ble-arb/
│       ├── business-context.md        # BLE + arbitration domain context
│       ├── skeleton/                  # Layer 1 outputs
│       ├── annotations/               # Layer 2 outputs (per-file .md)
│       └── workflows/                 # Layer 3 outputs
└── requirements.txt
```

## Prerequisites

- Python 3.10+
- `codebase-memory-mcp` binary installed and on `PATH`
- Target repo cloned at `D:\07-Hmos_AI_Engine\HMOS_AI_Engine`
  - If running under WSL/Linux, adjust `repo_path` in `agent_config.yaml` to the Linux mount path (e.g. `/mnt/d/07-Hmos_AI_Engine/HMOS_AI_Engine`)
- Access to company internal network (Kimi API at `10.43.2.173`)

## Setup

```bash
pip install -r requirements.txt
```

No external API key environment variable needed — the Kimi API key is configured directly in `agent_config.yaml`.

## Configuration

`agent_config.yaml`:

```yaml
llm:
  providers:
    kimi:
      base_url: "http://10.43.2.173:8263/v1"
      api_key: "sk-666"
      default_model: "kimi"
  max_tokens: 4096
  temperature: 0.3

codebase_memory:
  binary: "codebase-memory-mcp"
  repo_path: "D:\\07-Hmos_AI_Engine\\HMOS_AI_Engine"
  project: "07-Hmos_AI_Engine-HMOS_AI_Engine"

knowledge_base:
  root: "./knowledge-base/ble-arb"
```

## Usage

### Step 0 — Index the repository (once)

```bash
codebase-memory-mcp cli index_repository '{"repo_path": "D:\\07-Hmos_AI_Engine\\HMOS_AI_Engine"}'
```

### Layer 1 — Extract skeleton

```bash
python src/extract_skeleton.py
```

Runs Codebase-Memory queries and writes results to `knowledge-base/ble-arb/skeleton/`.

### Layer 2 — Annotate files

```bash
# Preview: discover TypeScript files and show prompt sizes without calling LLM
python -m src.annotator --discover --dry-run

# Test run: annotate first 5 files
python -m src.annotator --discover --limit 5

# Full annotation pass
python -m src.annotator --discover

# Force re-annotate specific files
python -m src.annotator path/to/file.ts --force
```

The `--discover` flag queries Codebase-Memory for all `.ts`/`.tsx` files (excluding tests and `node_modules`) and uses them as the annotation scope. Each output is a markdown file with YAML front matter (`status: pending|reviewed|revised`).

### Layer 3 — Generate workflow docs

```bash
python -m src.workflow_exporter
```

Auto-discovers workflows from Layer 2 annotations and generates Mermaid-diagram docs in `knowledge-base/ble-arb/workflows/`.

### Interactive Q&A CLI

```bash
python -m src.cli
```

| Prefix | Behavior |
|--------|----------|
| *(none)* | Free-text → annotations + CBM + LLM answer |
| `?` | Structural query → CBM only, no LLM |
| `!` | Correction → update `business-context.md` or annotations |
| `/export workflow` | Trigger Layer 3 |
| `/status` | Show annotation coverage stats |

## Codebase-Memory CLI Reference

All commands use JSON parameter format:

```bash
# List indexed projects
codebase-memory-mcp cli list_projects '{}'

# Discover all source files
codebase-memory-mcp cli search_graph '{"label": "File"}'

# Search symbols by name pattern
codebase-memory-mcp cli search_graph '{"name_pattern": ".*Arbitrat.*"}'

# Trace call paths
codebase-memory-mcp cli trace_call_path '{"function_name": "startArbitration", "direction": "both"}'

# Architecture overview
codebase-memory-mcp cli get_architecture '{}'

# Cypher query
codebase-memory-mcp cli query_graph '{"query": "MATCH (n:Function)-[:CALLS]->(m:Function) WHERE n.name CONTAINS \"BLE\" RETURN n.name, m.name LIMIT 20"}'
```

## Annotation Scope

Scope is auto-discovered via `--discover`. It includes all `.ts`/`.tsx` files from the indexed repository, excluding:
- Files containing `_test` in the path
- Files under `node_modules/`

After the first `--discover --dry-run` run, review the file list and optionally populate `SCOPE` in `src/annotator.py` manually to prioritize core modules.

## Working with Sparse-Comment Code

Because the target codebase has limited inline documentation, annotations follow these conventions:

- **Inferred intent** is explicitly labeled as "(inferred)" in annotation text
- The `### Questions` section in each annotation captures genuinely ambiguous code for human review
- `business-context.md` serves as the primary domain knowledge source; update it as you learn more about the codebase
- The `!` correction command in the CLI lets you refine annotations and business-context interactively
