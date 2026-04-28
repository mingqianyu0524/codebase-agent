"""Prompt templates used by the annotator and exporter."""

QA_PROMPT = """You are a code-analysis assistant for the HMOS AI Engine BLE collaborative arbitration module.

## Project Context
{business_context}

## Retrieved Evidence
{context}

## User Question
{question}

请用**中文**回答问题，依据上方检索到的证据作答。引用来源时用反引号标注（标注文件路径或符号名）。
若证据不足，请明确说明，并建议用户下一步检查哪个文件或符号。回答控制在 300 字以内。
"""

CORRECTION_PROMPT = """You are updating the codebase knowledge base based on a human correction.

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


DISCOVER_WORKFLOWS_PROMPT = """You are a software architect analyzing the HMOS AI Engine BLE collaborative arbitration module.

## Project Context
{business_context}

## File Overviews (from Layer-2 annotations)
{overviews}

Identify 3-6 end-to-end **workflows** worth documenting. A workflow is a
cross-file flow of control that achieves a user-visible or system-level
outcome (e.g. "BLE advertisement cycle", "Arbitration round", "Device handoff").

Return ONLY a JSON object with this exact shape (no surrounding text, no
markdown fences):

{{
  "workflows": [
    {{
      "slug": "kebab-case-identifier",
      "name": "Human-Readable Name",
      "summary": "One sentence on what this workflow accomplishes.",
      "entry_points": ["function or class names where the flow begins"],
      "files": ["relative/path/to/annotation/file.ts", "..."]
    }}
  ]
}}

Constraints:
- `files` must only contain paths that appear in the File Overviews above.
- Prefer workflows that span at least 3 files — single-file logic is already
  covered by Layer 2.
- `entry_points` should be concrete symbols, not prose.
"""


WORKFLOW_DOC_PROMPT = """You are documenting an end-to-end workflow in the HMOS AI Engine BLE collaborative arbitration module.

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

请用**中文**输出以下 markdown 各节：

### Overview
2-4 句话说明该工作流的目的及其在系统中的位置。

### Sequence
用 mermaid `sequenceDiagram` 展示跨文件的交互过程。参与方使用文件名或类名（非函数名），
至少展示入站触发点和终态。

### Step-by-step
有序列表，逐步说明流程。每条引用具体负责的函数/类及所在文件。

### Invariants & Failure Modes
该工作流维护的关键不变量，以及失败时的处理（如 BLE 广播丢失、仲裁超时、设备断连）。

### Open Questions
标注从标注文件中仍无法明确的内容。无疑问则省略此节。
"""


ANNOTATE_PROMPT = """你是一名 TypeScript 代码分析助手，正在分析 HMOS AI Engine BLE 协同仲裁模块。

注意：本代码仓注释稀少。对于意图不明确的地方，请综合以下信息推断：
(1) 函数/变量命名，(2) BLE 协议背景知识，(3) 下方调用关系，(4) 业务上下文。
**推断内容请明确标注为「推断」，有代码直接支撑的内容标注为「确认」。**

## 项目背景
{business_context}

## 当前文件：{file_path}

## 调用关系（来自结构分析）
### 入站调用（哪些函数/文件调用了本文件）：
{inbound}

### 出站调用（本文件调用了什么）：
{outbound}

## 符号签名（来自结构分析）：
{symbols}

## 源代码：
```typescript
{source}
```

请用**中文**输出以下 markdown 各节（保留英文节标题不变）：

### File Overview
2-3 句话说明本文件的职责及其在系统中的位置，依据上方调用关系作出判断。
如需推断，请标注。

### Key Symbol Annotations
对每个公开/重要的函数或类，用一句话描述其作用。
格式：`符号名 — 描述（确认/推断）`

### Design Patterns & Engineering Practices
本文件中值得记录的 TypeScript 模式、async/await 用法、BLE 事件驱动模式、
仲裁状态机约定或其他设计选择。尽量引用具体符号名或行号范围。

### Internal Flow
若本文件包含重要控制流（如 BLE 扫描→仲裁→广播，或状态机跳转），
用 mermaid `flowchart` 或 `sequenceDiagram` 展示。流程简单则省略此节。

### Questions
标注推断后仍不明确的代码段，引用具体符号名或行号。无疑问则省略此节。
"""
