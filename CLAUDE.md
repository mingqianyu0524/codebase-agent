Codebase Knowledge Agent — LevelDB Annotation Pilot
Project Goal
Build a Python-based agent that uses Codebase-Memory (structural analysis) + LLM (semantic annotation) to construct a layered knowledge base from source code. This pilot uses Google's leveldb C++ project as the test codebase.
Current State

Codebase-Memory: installed, binary at codebase-memory-mcp
LevelDB: cloned at /Users/myu/projects/leveldb, already indexed
Index cache: ~/.cache/codebase-memory-mcp/
LLM: OpenRouter API, model google/gemma-4-31b-it:free (256K context, free tier)

Alternative: google/gemma-4-26b-a4b-it:free (MoE, only 3.8B active/token, faster but lower quality)
Alternative: google/gemma-4-31b-it (paid, $0.14/M input — use if free tier rate limits hit)



Codebase-Memory CLI Reference
IMPORTANT: All CLI commands use JSON parameter format. Do NOT use positional args.
bash# Correct format
codebase-memory-mcp cli <tool_name> '<json_params>'

# Index a repo (already done for leveldb)
codebase-memory-mcp cli index_repository '{"repo_path": "/Users/myu/projects/leveldb"}'

# List indexed projects
codebase-memory-mcp cli list_projects '{}'

# Get schema (node/edge counts)
codebase-memory-mcp cli get_graph_schema '{}'

# Search symbols by name or file
codebase-memory-mcp cli search_graph '{"name_pattern": ".*Cache.*"}'
codebase-memory-mcp cli search_graph '{"file_pattern": "db/db_impl.cc"}'

# Trace call paths (inbound = who calls it, outbound = what it calls)
codebase-memory-mcp cli trace_call_path '{"function_name": "DBImpl::Write", "direction": "inbound"}'
codebase-memory-mcp cli trace_call_path '{"function_name": "DBImpl::Write", "direction": "both"}'

# Get source code snippet
codebase-memory-mcp cli get_code_snippet '{"qualified_name": "leveldb.db.db_impl.DBImpl"}'

# Architecture overview
codebase-memory-mcp cli get_architecture '{}'

# Cypher queries
codebase-memory-mcp cli query_graph '{"query": "MATCH (n:Function)-[:CALLS]->(m:Function) WHERE n.name CONTAINS \"Compact\" RETURN n.name, m.name LIMIT 20"}'

# Find dead code
codebase-memory-mcp cli find_dead_code '{}'
Architecture
wakeup-agent/
├── CLAUDE.md                          # This file
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
│   └── leveldb/                       # Test project knowledge
│       ├── business-context.md        # Human-written domain context
│       ├── skeleton/                  # Layer 1 outputs (from cbm)
│       │   ├── architecture.md
│       │   ├── file-tree.md
│       │   └── hubs.md
│       ├── annotations/               # Layer 2 outputs (LLM-generated)
│       │   ├── db/
│       │   │   ├── db_impl.md
│       │   │   ├── version_set.md
│       │   │   └── ...
│       │   ├── table/
│       │   └── util/
│       └── workflows/                 # Layer 3 outputs
└── requirements.txt                   # openai, pyyaml, rich
Config: agent_config.yaml
yamlllm:
  providers:
    openrouter:
      base_url: "https://openrouter.ai/api/v1"
      api_key: "${OPENROUTER_API_KEY}"    # Read from env var
      default_model: "google/gemma-4-31b-it:free"

  task_routing:
    annotate: "openrouter"
    query: "openrouter"
    export: "openrouter"

  max_tokens: 4096
  temperature: 0.3

codebase_memory:
  binary: "codebase-memory-mcp"
  repo_path: "/Users/myu/projects/leveldb"

knowledge_base:
  root: "./knowledge-base/leveldb"
Execution Plan
Step 1: Scaffold project + LLM client
Create the project directory structure. Implement llm_client.py that wraps openai SDK with OpenRouter config. Implement cbm_client.py that wraps subprocess.run("codebase-memory-mcp", "cli", ...) calls and parses JSON output.
Verify both work:

cbm_client: call list_projects and get_graph_schema, print results
llm_client: send a test prompt to Gemma 4, print response

Step 2: Layer 1 — Extract skeleton from Codebase-Memory
Run these cbm commands and save results to knowledge-base/leveldb/skeleton/:

get_architecture '{}' → architecture.md
search_graph '{"label": "File"}' → file-tree.md
find_dead_code '{}' → dead-code.md
For each core directory (db/, table/, util/, include/), run search_graph with file_pattern to get all symbols

Step 3: Write business-context.md for LevelDB
Create knowledge-base/leveldb/business-context.md with:
markdown# LevelDB — Business Context

## Overview
LevelDB is a fast key-value storage library by Google. It provides an ordered
mapping from string keys to string values, backed by a log-structured
merge-tree (LSM-tree).

## Core Architecture
- Write path: Write → WAL log → MemTable → (when full) → Immutable MemTable → SSTable
- Read path: MemTable → Immutable MemTable → SSTable files (newest first)
- Compaction: background thread merges SSTable files to reduce read amplification

## Key Concepts
- MemTable: in-memory sorted skiplist for recent writes
- SSTable (Sorted String Table): immutable on-disk sorted file
- WAL (Write-Ahead Log): crash recovery journal
- Manifest/VersionSet: tracks which SSTable files are live
- Compaction: merges overlapping SSTables across levels
- Block/BlockBuilder: SSTable is composed of data blocks + index blocks
- Cache: LRU cache for frequently accessed blocks

## Directory Structure
- `db/`: core database logic (DBImpl, compaction, recovery, write batch)
- `table/`: SSTable read/write (Table, Block, BlockBuilder, format)
- `util/`: infrastructure (Arena, Cache, Env, Coding, CRC, Bloom filter)
- `include/leveldb/`: public API headers
- `helpers/memenv/`: in-memory Env implementation for testing

## Naming Conventions
- `rep_` → internal representation struct
- `Ref()/Unref()` → manual reference counting
- `user_key` vs `internal_key` → user-visible key vs key with sequence number appended
Step 4: Layer 2 — Annotate with Gemma 4
Implement annotator.py. For each source file in scope:

Call cbm_client.search_graph(file_pattern=<file>) → get symbol signatures
Call cbm_client.trace_call_path(function_name=<each_exported_func>, direction="both") → get call context
Read source file directly from /Users/myu/projects/leveldb/<path>
Assemble prompt (see Prompt Template below) with: business-context + call relations + signatures + source code
Call llm_client.complete(prompt) → parse markdown response
Write to knowledge-base/leveldb/annotations/<path>.md with review header

Annotation scope (prioritized, ~25 files):
# Priority 1: Core DB logic
db/db_impl.cc          # Main database implementation
db/db_impl.h
db/version_set.cc      # SSTable version management
db/version_set.h
db/version_edit.cc     # Version metadata changes
db/write_batch.cc      # Atomic batch writes
db/memtable.cc         # In-memory write buffer
db/log_writer.cc       # WAL writer
db/log_reader.cc       # WAL reader
db/table_cache.cc      # SSTable file cache
db/builder.cc          # SSTable builder from memtable
db/filename.cc         # File naming conventions

# Priority 2: SSTable layer
table/table.cc         # SSTable reader
table/table_builder.cc # SSTable writer
table/block.cc         # Block reader
table/block_builder.cc # Block writer
table/format.cc        # On-disk format
table/merger.cc        # Multi-way merge iterator
table/two_level_iterator.cc

# Priority 3: Utilities
util/cache.cc          # LRU cache
util/arena.cc          # Memory arena
util/bloom.cc          # Bloom filter
util/coding.cc         # Varint encoding
util/env_posix.cc      # POSIX file operations
Skip: test files (*_test.cc), benchmarks, third_party/
Prompt template for annotation:
You are a C++ code analysis assistant analyzing Google's LevelDB.

## Project Context
{business-context.md content}

## Current File: {file_path}

## Call Relations (from structural analysis)
### Inbound (who calls functions in this file):
{trace_call_path inbound results}
### Outbound (what this file calls):
{trace_call_path outbound results}

## Symbol Signatures (from structural analysis):
{search_graph results for this file}

## Source Code:
{file content}

Output in markdown:

### File Overview
2-3 sentences: what this file does and where it sits in the system (use call relations).

### Key Symbol Annotations
For each public/important function or class, 1 sentence describing its role.

### Design Patterns & Engineering Practices
Notable C++ patterns, RAII usage, thread safety mechanisms, or design choices
worth learning from. This is important — the user is studying this codebase
to learn good C++ engineering practices.

### Internal Flow
If this file contains important control flow, describe it with a mermaid
flowchart or sequenceDiagram. Skip if trivial.

### Questions
Code segments whose purpose is unclear, for human review.
Each annotation file gets a YAML front matter:
yaml---
status: pending    # pending | reviewed | revised
file: db/db_impl.cc
symbols: 42
annotated_at: 2026-04-13T...
model: google/gemma-4-31b-it:free
---
Step 5: Layer 3 — Generate workflow docs
Implement workflow_exporter.py with auto-discovery:

Feed all annotation "File Overview" paragraphs to LLM
LLM returns JSON list of discoverable workflows
For each workflow, gather relevant annotations + cbm call traces
Generate workflow doc + mermaid diagram
Save to knowledge-base/leveldb/workflows/

Step 6: Interactive Q&A CLI
Implement cli.py using rich for terminal UI:

Default mode: free-text → search relevant annotations + cbm queries → LLM answer
? prefix: structural query → cbm only, no LLM
! prefix: correction → update business-context.md or annotation files
/export workflow: trigger Layer 3
/status: show annotation coverage stats

Key Implementation Notes

Rate limits: OpenRouter free tier = 20 req/min, 200 req/day. Add retry with backoff. For 25 files, one annotation pass fits within daily limit.
Error handling: cbm CLI may return non-JSON on errors. Always try/except parse.
Source code reading: Read files directly from disk (/Users/myu/projects/leveldb/), don't rely on cbm's get_code_snippet for full file content — it may truncate.
Token budget: Gemma 4 has 256K context but free tier may have shorter effective limits. Keep total prompt under 16K tokens per annotation call.
Language: All annotation outputs and prompts in English. CLI interface in English.
