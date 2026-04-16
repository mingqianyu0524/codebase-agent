"""Layer 3: derive end-to-end workflow docs from Layer-2 annotations + CBM traces."""
from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .cbm_client import CBMClient, CBMError
from .config import load_config
from .llm_client import LLMClient
from .prompt_templates import DISCOVER_WORKFLOWS_PROMPT, WORKFLOW_DOC_PROMPT

MIN_SECONDS_BETWEEN_CALLS = 4.0
MAX_ANNOTATION_CHARS_PER_WORKFLOW = 40_000


def _parse_annotation(path: Path) -> dict:
    """Split an annotation file into front-matter + section dict."""
    text = path.read_text()
    front: dict[str, str] = {}
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            raw = text[3:end].strip()
            for line in raw.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    front[k.strip()] = v.strip()
            body = text[end + 4 :].lstrip()

    sections: dict[str, str] = {}
    current = "_preamble"
    buf: list[str] = []
    for line in body.splitlines():
        m = re.match(r"^###\s+(.+)$", line)
        if m:
            if buf:
                sections[current] = "\n".join(buf).strip()
            current = m.group(1).strip()
            buf = []
        else:
            buf.append(line)
    if buf:
        sections[current] = "\n".join(buf).strip()

    return {"path": path, "front": front, "sections": sections, "body": body}


def _collect_overviews(annotations_dir: Path) -> list[dict]:
    """Return [{file, overview}] for every annotation file."""
    out = []
    for p in sorted(annotations_dir.rglob("*.md")):
        parsed = _parse_annotation(p)
        overview = parsed["sections"].get("File Overview", "").strip()
        src_file = parsed["front"].get("file", str(p.relative_to(annotations_dir)))
        if overview:
            out.append({"file": src_file, "overview": overview, "path": p, "parsed": parsed})
    return out


def discover_workflows(llm: LLMClient, business_context: str, overviews: list[dict]) -> list[dict]:
    summary_block = "\n".join(
        f"- **{o['file']}**: {o['overview']}" for o in overviews
    )
    prompt = DISCOVER_WORKFLOWS_PROMPT.format(
        business_context=business_context, overviews=summary_block
    )
    reply = llm.complete(prompt)
    # Tolerate accidental fences despite the "no markdown fences" instruction.
    cleaned = reply.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"workflow discovery returned non-JSON: {reply!r}") from e
    workflows = data.get("workflows", [])
    if not isinstance(workflows, list):
        raise RuntimeError(f"workflow discovery JSON missing 'workflows' list: {data}")
    return workflows


def _gather_call_traces(cbm: CBMClient, entry_points: list[str]) -> str:
    chunks: list[str] = []
    for fn in entry_points:
        for direction in ("inbound", "outbound"):
            try:
                trace = cbm.trace_call_path(function_name=fn, direction=direction)
            except CBMError as e:
                chunks.append(f"- {fn} ({direction}): error {e}")
                continue
            peers = trace.get("callers" if direction == "inbound" else "callees", [])
            if not peers:
                chunks.append(f"- `{fn}` {direction}: _(none)_")
                continue
            names = [f"`{p.get('name')}`" for p in peers[:15]]
            chunks.append(f"- `{fn}` {direction}: {', '.join(names)}")
    return "\n".join(chunks) if chunks else "_(no trace data)_"


def _gather_annotations(files: list[str], overviews: list[dict]) -> str:
    by_file = {o["file"]: o for o in overviews}
    pieces: list[str] = []
    total = 0
    for f in files:
        o = by_file.get(f)
        if not o:
            pieces.append(f"### {f}\n_(no annotation found)_\n")
            continue
        body = o["parsed"]["body"]
        piece = f"### {f}\n{body}\n"
        if total + len(piece) > MAX_ANNOTATION_CHARS_PER_WORKFLOW:
            pieces.append(f"### {f}\n_(elided — workflow budget exhausted)_\n")
            continue
        pieces.append(piece)
        total += len(piece)
    return "\n".join(pieces)


def generate_workflow_doc(
    spec: dict,
    *,
    llm: LLMClient,
    cbm: CBMClient,
    business_context: str,
    overviews: list[dict],
) -> str:
    annotations = _gather_annotations(spec.get("files", []), overviews)
    call_traces = _gather_call_traces(cbm, spec.get("entry_points", []))
    prompt = WORKFLOW_DOC_PROMPT.format(
        business_context=business_context,
        name=spec.get("name", spec.get("slug", "unnamed")),
        summary=spec.get("summary", ""),
        entry_points=", ".join(spec.get("entry_points", [])) or "_(none)_",
        annotations=annotations,
        call_traces=call_traces,
    )
    return llm.complete(prompt)


def _slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s.strip().lower())
    return s.strip("-") or "workflow"


def run(
    *,
    dry_run: bool = False,
    force: bool = False,
    rediscover: bool = False,
    only: Iterable[str] | None = None,
) -> None:
    cfg = load_config()
    kb_root = Path(cfg["knowledge_base"]["root"])
    if not kb_root.is_absolute():
        kb_root = Path(__file__).resolve().parent.parent / kb_root
    annotations_dir = kb_root / "annotations"
    workflows_dir = kb_root / "workflows"
    workflows_dir.mkdir(parents=True, exist_ok=True)
    business_context = (kb_root / "business-context.md").read_text()

    cbm = CBMClient(config=cfg)
    llm = LLMClient(config=cfg)

    overviews = _collect_overviews(annotations_dir)
    spec_path = workflows_dir / "_discovered.json"

    if spec_path.exists() and not rediscover:
        workflows = json.loads(spec_path.read_text()).get("workflows", [])
        print(f"[discover] reusing {spec_path} ({len(workflows)} workflows). "
              f"Pass --rediscover to regenerate.")
    else:
        print(f"[discover] {len(overviews)} annotations feeding discovery prompt")
        workflows = discover_workflows(llm, business_context, overviews)
        spec_path.write_text(json.dumps({"workflows": workflows}, indent=2))
        print(f"[discover] wrote spec → {spec_path}")

    print(f"[discover] {len(workflows)} workflows:")
    for w in workflows:
        print(f"  - {w.get('slug')} ({w.get('name')}): {len(w.get('files', []))} files")

    if dry_run:
        return

    filter_set = set(only) if only else None
    last_call = time.monotonic()
    for i, spec in enumerate(workflows):
        slug = spec.get("slug") or _slugify(spec.get("name", f"workflow-{i}"))
        if filter_set and slug not in filter_set:
            continue
        out_path = workflows_dir / f"{slug}.md"
        if out_path.exists() and not force:
            print(f"  [skip] {slug} -> {out_path} already exists")
            continue

        elapsed = time.monotonic() - last_call
        if elapsed < MIN_SECONDS_BETWEEN_CALLS:
            time.sleep(MIN_SECONDS_BETWEEN_CALLS - elapsed)

        print(f"  -> LLM call for workflow '{slug}'")
        try:
            doc = generate_workflow_doc(
                spec,
                llm=llm,
                cbm=cbm,
                business_context=business_context,
                overviews=overviews,
            )
        except Exception as e:
            print(f"  [error] {slug}: {e}")
            last_call = time.monotonic()
            continue

        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        header = (
            "---\n"
            "status: pending\n"
            f"slug: {slug}\n"
            f"name: {spec.get('name', slug)}\n"
            f"entry_points: {json.dumps(spec.get('entry_points', []))}\n"
            f"files: {json.dumps(spec.get('files', []))}\n"
            f"generated_at: {ts}\n"
            f"model: {llm.model}\n"
            "---\n\n"
        )
        out_path.write_text(header + doc.strip() + "\n")
        print(f"  [wrote] {out_path} ({len(doc)} chars)")
        last_call = time.monotonic()


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate Layer-3 workflow docs for LevelDB.")
    ap.add_argument("--dry-run", action="store_true", help="Discover workflows only; skip per-workflow docs.")
    ap.add_argument("--force", action="store_true", help="Overwrite existing workflow docs.")
    ap.add_argument("--rediscover", action="store_true", help="Re-run LLM discovery even if _discovered.json exists.")
    ap.add_argument("--only", action="append", help="Limit to these workflow slugs (repeatable).")
    args = ap.parse_args()
    run(dry_run=args.dry_run, force=args.force, rediscover=args.rediscover, only=args.only)


if __name__ == "__main__":
    main()
