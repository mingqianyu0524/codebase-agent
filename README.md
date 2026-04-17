# Codebase Knowledge Agent — LevelDB Annotation Pilot

A Python-based agent that uses **Codebase-Memory** (structural analysis) + **LLM** (semantic annotation) to construct a layered knowledge base from source code. This pilot uses Google's [LevelDB](https://github.com/google/leveldb) C++ project as the test codebase.

## Overview

The agent builds a three-layer knowledge base:

| Layer | Tool | Output |
|-------|------|--------|
| Layer 1: Skeleton | Codebase-Memory CLI | Architecture, file tree, symbol graph |
| Layer 2: Annotations | Gemma 4 via OpenRouter | Per-file markdown docs with design notes |
| Layer 3: Workflows | Gemma 4 via OpenRouter | End-to-end flow docs with Mermaid diagrams |

## Project Structure

```
wakeup-agent/
├── CLAUDE.md                          # Project instructions
├── agent_config.yaml                  # LLM + paths config
├── src/
│   ├── llm_client.py                  # OpenAI-compatible LLM wrapper
│   ├── cbm_client.py                  # Codebase-Memory CLI wrapper
│   ├── annotator.py                   # Layer 2: annotation pipeline
│   ├── workflow_exporter.py           # Layer 3: workflow doc generation
│   ├── context_manager.py             # Context retrieval for Q&A
│   ├── cli.py                         # Interactive CLI
│   └── prompt_templates.py            # All prompt templates
├── knowledge-base/
│   └── leveldb/
│       ├── business-context.md        # Human-written domain context
│       ├── skeleton/                  # Layer 1 outputs
│       ├── annotations/               # Layer 2 outputs (per-file .md)
│       └── workflows/                 # Layer 3 outputs
└── requirements.txt
```

## Prerequisites

- Python 3.10+
- `codebase-memory-mcp` binary installed and on `PATH`
- LevelDB cloned and indexed at `/Users/myu/projects/leveldb`
- OpenRouter API key (set as `OPENROUTER_API_KEY` env var)

## Setup

```bash
pip install -r requirements.txt
export OPENROUTER_API_KEY=<your-key>
```

## Configuration

Edit `agent_config.yaml` to adjust LLM model, paths, and token limits:

```yaml
llm:
  providers:
    openrouter:
      base_url: "https://openrouter.ai/api/v1"
      api_key: "${OPENROUTER_API_KEY}"
      default_model: "google/gemma-4-31b-it:free"
  max_tokens: 4096
  temperature: 0.3

codebase_memory:
  binary: "codebase-memory-mcp"
  repo_path: "/Users/myu/projects/leveldb"

knowledge_base:
  root: "./knowledge-base/leveldb"
```

Alternative models:
- `google/gemma-4-26b-a4b-it:free` — faster MoE variant (lower quality)
- `google/gemma-4-31b-it` — paid tier ($0.14/M tokens), use if free tier rate limits

## Usage

### Layer 1 — Extract skeleton

```bash
python src/annotator.py --layer 1
```

Runs Codebase-Memory queries and writes results to `knowledge-base/leveldb/skeleton/`.

### Layer 2 — Annotate files

```bash
python src/annotator.py --layer 2
```

Annotates ~25 prioritized LevelDB source files. Each output is a markdown file with YAML front matter (`status: pending|reviewed|revised`).

> **Rate limit:** OpenRouter free tier allows 20 req/min / 200 req/day. The annotation pass for 25 files fits within the daily limit.

### Layer 3 — Generate workflow docs

```bash
python src/workflow_exporter.py
```

Auto-discovers workflows from Layer 2 annotations and generates Mermaid-diagram docs in `knowledge-base/leveldb/workflows/`.

### Interactive Q&A CLI

```bash
python src/cli.py
```

| Prefix | Behavior |
|--------|----------|
| *(none)* | Free-text → annotations + cbm + LLM answer |
| `?` | Structural query → cbm only, no LLM |
| `!` | Correction → update `business-context.md` or annotations |
| `/export workflow` | Trigger Layer 3 |
| `/status` | Show annotation coverage stats |

## Codebase-Memory CLI Reference

All commands use JSON parameter format:

```bash
# List indexed projects
codebase-memory-mcp cli list_projects '{}'

# Search symbols
codebase-memory-mcp cli search_graph '{"name_pattern": ".*Cache.*"}'
codebase-memory-mcp cli search_graph '{"file_pattern": "db/db_impl.cc"}'

# Trace call paths
codebase-memory-mcp cli trace_call_path '{"function_name": "DBImpl::Write", "direction": "both"}'

# Architecture overview
codebase-memory-mcp cli get_architecture '{}'

# Cypher query
codebase-memory-mcp cli query_graph '{"query": "MATCH (n:Function)-[:CALLS]->(m:Function) WHERE n.name CONTAINS \"Compact\" RETURN n.name, m.name LIMIT 20"}'
```

## Annotation Scope

**Priority 1 — Core DB logic:** `db/db_impl.cc`, `db/version_set.cc`, `db/write_batch.cc`, `db/memtable.cc`, `db/log_writer.cc`, `db/log_reader.cc`, `db/table_cache.cc`, `db/builder.cc`, `db/filename.cc`

**Priority 2 — SSTable layer:** `table/table.cc`, `table/table_builder.cc`, `table/block.cc`, `table/block_builder.cc`, `table/format.cc`, `table/merger.cc`, `table/two_level_iterator.cc`

**Priority 3 — Utilities:** `util/cache.cc`, `util/arena.cc`, `util/bloom.cc`, `util/coding.cc`, `util/env_posix.cc`

Skipped: `*_test.cc`, benchmarks, `third_party/`
