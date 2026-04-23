Codebase Knowledge Agent — HMOS AI Engine BLE 协同仲裁模块
Project Goal
Build a Python-based agent that uses Codebase-Memory (structural analysis) + LLM (semantic annotation) to construct a layered knowledge base from source code. This pilot uses the HMOS AI Engine BLE collaborative arbitration module (TypeScript) as the target codebase.
Current State

Codebase-Memory: installed, binary at codebase-memory-mcp
Target repo: D:\07-Hmos_AI_Engine\HMOS_AI_Engine\HMOS_AI_Engine\wakeup (Windows path; use /mnt/d/... under WSL/Linux)
LLM: Company-internal Kimi-K2.5 deployment, model name: kimi
  Base URL: http://10.43.2.173:8263/v1
  API Key: sk-666 (configured directly in agent_config.yaml)

Note on code quality: This codebase has sparse comments and documentation.
Annotation prompts are tuned to infer intent from naming, call patterns, and BLE domain knowledge.
The annotator should explicitly mark inferred content.

Codebase-Memory CLI Reference
IMPORTANT: All CLI commands use JSON parameter format. Do NOT use positional args.
bash# Correct format
codebase-memory-mcp cli <tool_name> '<json_params>'

# Index the target repo (run once)
codebase-memory-mcp cli index_repository '{"repo_path": "D:\\07-Hmos_AI_Engine\\HMOS_AI_Engine\\HMOS_AI_Engine\\wakeup"}'

# List indexed projects
codebase-memory-mcp cli list_projects '{}'

# Get schema (node/edge counts)
codebase-memory-mcp cli get_graph_schema '{}'

# Search symbols by name or file
codebase-memory-mcp cli search_graph '{"name_pattern": ".*Arbitrat.*"}'
codebase-memory-mcp cli search_graph '{"file_pattern": "src/ble/advertiser.ts"}'
codebase-memory-mcp cli search_graph '{"label": "File"}'

# Trace call paths (inbound = who calls it, outbound = what it calls)
codebase-memory-mcp cli trace_call_path '{"function_name": "startArbitration", "direction": "inbound"}'
codebase-memory-mcp cli trace_call_path '{"function_name": "startArbitration", "direction": "both"}'

# Get source code snippet
codebase-memory-mcp cli get_code_snippet '{"qualified_name": "..."}'

# Architecture overview
codebase-memory-mcp cli get_architecture '{}'

# Cypher queries
codebase-memory-mcp cli query_graph '{"query": "MATCH (n:Function)-[:CALLS]->(m:Function) WHERE n.name CONTAINS \"BLE\" RETURN n.name, m.name LIMIT 20"}'

# Find dead code
codebase-memory-mcp cli find_dead_code '{}'
Architecture
codebase-agent/
├── CLAUDE.md                          # This file
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
│   └── ble-arb/                       # Target project knowledge
│       ├── business-context.md        # Human-written domain context
│       ├── skeleton/                  # Layer 1 outputs (from cbm)
│       │   ├── architecture.md
│       │   ├── file-tree.md
│       │   └── hubs.md
│       ├── annotations/               # Layer 2 outputs (LLM-generated)
│       │   └── <dir>/
│       │       └── <file>.md
│       └── workflows/                 # Layer 3 outputs
└── requirements.txt                   # openai, pyyaml, rich
Config: agent_config.yaml
yamlllm:
  providers:
    kimi:
      base_url: "http://10.43.2.173:8263/v1"
      api_key: "sk-666"
      default_model: "kimi"

  task_routing:
    annotate: "kimi"
    query: "kimi"
    export: "kimi"

  max_tokens: 4096
  temperature: 0.3

codebase_memory:
  binary: "codebase-memory-mcp"
  repo_path: "D:\\07-Hmos_AI_Engine\\HMOS_AI_Engine\\HMOS_AI_Engine\\wakeup"
  project: "D-07-Hmos_AI_Engine-HMOS_AI_Engine-HMOS_AI_Engine-wakeup"

knowledge_base:
  root: "./knowledge-base/ble-arb"
Execution Plan
Step 1: Index repo + verify connections
Index the target repository with codebase-memory-mcp. Verify LLM and CBM connectivity:

cbm_client: call list_projects and get_graph_schema
llm_client: send a test prompt to Kimi, verify response

bash# Index repo
codebase-memory-mcp cli index_repository '{"repo_path": "D:\\07-Hmos_AI_Engine\\HMOS_AI_Engine\\HMOS_AI_Engine\\wakeup"}'

# Verify Python clients
python -m src.cbm_client
python -m src.llm_client
Step 2: Layer 1 — Extract skeleton from Codebase-Memory
Run these cbm commands and save results to knowledge-base/ble-arb/skeleton/:

get_architecture '{}' → architecture.md
search_graph '{"label": "File"}' → file-tree.md
find_dead_code '{}' → dead-code.md

bash# Example (adapt to actual CLI):
python -m src.extract_skeleton
Step 3: Update business-context.md
After reviewing the actual file structure from Layer 1, update knowledge-base/ble-arb/business-context.md with:

Actual directory structure
Discovered naming conventions (prefixes, state machine patterns, etc.)
Any BLE API specifics observed in the code

Step 4: Layer 2 — Annotate with Kimi
Use --discover to auto-detect TypeScript source files, then annotate:

bashpython -m src.annotator --discover --dry-run        # preview files + prompt sizes
python -m src.annotator --discover --limit 5         # test first 5 files
python -m src.annotator --discover                   # full annotation pass

Annotation scope is auto-discovered from .ts/.tsx files (excluding *_test, node_modules).
No rate-limit pacing needed — internal deployment.

Prompt notes for sparse-comment code:
- LLM is instructed to explicitly mark inferred intent
- Call relations from CBM are the primary evidence source
- BLE domain knowledge fills gaps where naming is ambiguous

Step 5: Layer 3 — Generate workflow docs
bash python -m src.workflow_exporter
Step 6: Interactive Q&A CLI
bashpython -m src.cli

Default mode: free-text → search relevant annotations + cbm queries → LLM answer
? prefix: structural query → cbm only, no LLM
! prefix: correction → update business-context.md or annotation files
/export workflow: trigger Layer 3
/status: show annotation coverage stats

Key Implementation Notes

No external rate limits: Internal Kimi deployment — no req/min throttle. MIN_SECONDS_BETWEEN_CALLS = 0.5.
Error handling: cbm CLI may return non-JSON on errors. Always try/except parse.
Source code reading: Read files directly from disk using the configured repo_path. On WSL/Linux, adjust path accordingly.
Token budget: Keep total prompt under 16K tokens per annotation call. Large TS files truncated at 45K chars.
Sparse comments: Annotation prompts explicitly instruct the LLM to infer intent and label inferences. Review annotations marked Questions carefully.
Language: All annotation outputs and prompts in English. CLI interface in English.
