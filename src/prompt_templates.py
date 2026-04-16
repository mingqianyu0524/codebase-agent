"""Prompt templates used by the annotator and exporter."""

QA_PROMPT = """You are a C++ code-analysis assistant with deep knowledge of Google's LevelDB.

## Project Context
{business_context}

## Retrieved Evidence
{context}

## User Question
{question}

Answer the question grounded in the retrieved evidence. Cite the source \
(annotation path or CBM match) inline using backticks when you use it. If \
the evidence is insufficient, say so explicitly and suggest which file or \
symbol the user should inspect next. Keep the answer under ~300 words.
"""

CORRECTION_PROMPT = """You are updating the LevelDB knowledge base based on a human correction.

## Existing content of `{target_file}`
```
{existing}
```

## User correction
{correction}

Produce the full revised content for `{target_file}` that applies the \
correction. Keep existing structure and YAML front matter intact, but set \
`status: revised`. Return ONLY the new file content, with no surrounding \
commentary or markdown fences.
"""


DISCOVER_WORKFLOWS_PROMPT = """You are a software architect analyzing Google's LevelDB.

## Project Context
{business_context}

## File Overviews (from Layer-2 annotations)
{overviews}

Identify 3-6 end-to-end **workflows** worth documenting. A workflow is a
cross-file flow of control that achieves a user-visible or system-level
outcome (e.g. "Write path", "Compaction cycle", "Crash recovery").

Return ONLY a JSON object with this exact shape (no surrounding text, no
markdown fences):

{{
  "workflows": [
    {{
      "slug": "kebab-case-identifier",
      "name": "Human-Readable Name",
      "summary": "One sentence on what this workflow accomplishes.",
      "entry_points": ["function or class names where the flow begins"],
      "files": ["relative/path/to/annotation/file.cc", "..."]
    }}
  ]
}}

Constraints:
- `files` must only contain paths that appear in the File Overviews above.
- Prefer workflows that span at least 3 files — single-file logic is already
  covered by Layer 2.
- `entry_points` should be concrete symbols, not prose.
"""


WORKFLOW_DOC_PROMPT = """You are documenting an end-to-end workflow in Google's LevelDB.

## Project Context
{business_context}

## Workflow
- Name: {name}
- Summary: {summary}
- Entry points: {entry_points}

## Relevant Layer-2 Annotations
{annotations}

## Call Traces (from structural analysis)
{call_traces}

Write a single markdown document with these sections:

### Overview
2-4 sentences on the workflow's purpose and where it sits in the system.

### Sequence
A mermaid `sequenceDiagram` showing the cross-file interactions. Use file or
class names (not functions) as participants. Show at least the inbound trigger
and the terminal state.

### Step-by-step
An ordered list walking through the flow. Each item cites the specific
function/class responsible and the file.

### Invariants & Failure Modes
Key invariants the workflow preserves, and what happens on failure (e.g.
partial writes, crashes, rate limits).

### Open Questions
Bullets for anything that the annotations don't make clear. Omit if none.
"""


ANNOTATE_PROMPT = """You are a C++ code analysis assistant analyzing Google's LevelDB.

## Project Context
{business_context}

## Current File: {file_path}

## Call Relations (from structural analysis)
### Inbound (functions/files that call into this file):
{inbound}

### Outbound (what this file calls):
{outbound}

## Symbol Signatures (from structural analysis):
{symbols}

## Source Code:
```cpp
{source}
```

Output in markdown with these exact sections:

### File Overview
2-3 sentences: what this file does and where it sits in the system. Ground \
the claim in the call relations above.

### Key Symbol Annotations
For each public/important function or class, 1 sentence describing its role. \
Use a bulleted list of `symbol_name — description`.

### Design Patterns & Engineering Practices
Notable C++ patterns, RAII usage, thread safety mechanisms, ownership \
conventions, or design choices worth learning from. This section is \
important — the user is studying this codebase to learn good C++ engineering \
practices. Be specific and reference line numbers or symbol names.

### Internal Flow
If this file contains important control flow, describe it with a mermaid \
`flowchart` or `sequenceDiagram` block. Skip this section entirely if the \
flow is trivial.

### Questions
Code segments whose purpose is unclear, for human review. Use a bulleted \
list, each item citing a specific symbol or line range. Omit the section if \
nothing is unclear.
"""
