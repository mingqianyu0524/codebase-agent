"""Layer 2: LLM-driven semantic annotation of source files."""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .cbm_client import CBMClient, CBMError
from .config import load_config
from .llm_client import LLMClient
from .prompt_templates import ANNOTATE_PROMPT

# Annotation scope — populate manually or use --discover to auto-detect .ts/.tsx files.
SCOPE: list[str] = []

# File extensions considered for auto-discovery.
TS_EXTENSIONS = {".ts", ".tsx"}

# Source files exceeding this size get truncated to keep prompts under ~16K tokens.
MAX_SOURCE_CHARS = 45_000
# Hard cap on how many symbols we paste into the prompt.
MAX_SYMBOLS = 80
# Inbound/outbound lists capped to keep context readable.
MAX_EDGES = 20
# Inter-call delay — internal deployment has no rate limit, keep small.
MIN_SECONDS_BETWEEN_CALLS = 0.5


def discover_ts_files(cbm: CBMClient) -> list[str]:
    """Return sorted list of .ts/.tsx source files reported by codebase-memory."""
    res = cbm.search_graph(label="File", limit=500)
    files = [
        r["file_path"]
        for r in res.get("results", [])
        if Path(r["file_path"]).suffix in TS_EXTENSIONS
        and "_test" not in r["file_path"]
        and "node_modules" not in r["file_path"]
    ]
    return sorted(files)


def _fmt_symbols(results: list[dict]) -> str:
    lines = []
    for r in results[:MAX_SYMBOLS]:
        lines.append(
            f"- [{r.get('label','?')}] {r.get('name')} "
            f"(qn={r.get('qualified_name')}, in={r.get('in_degree',0)}, "
            f"out={r.get('out_degree',0)})"
        )
    if len(results) > MAX_SYMBOLS:
        lines.append(f"- ... ({len(results) - MAX_SYMBOLS} more symbols elided)")
    return "\n".join(lines) if lines else "_(none)_"


def _fmt_edges(rows: list[list], label: str) -> str:
    if not rows:
        return "_(none)_"
    lines = []
    for row in rows[:MAX_EDGES]:
        lines.append("- " + " → ".join(str(c) for c in row))
    if len(rows) > MAX_EDGES:
        lines.append(f"- ... ({len(rows) - MAX_EDGES} more {label} elided)")
    return "\n".join(lines)


def _fetch_context(cbm: CBMClient, file_path: str) -> dict:
    """Pull structural context for a single file."""
    syms = cbm.search_graph(file_pattern=file_path, limit=500)
    symbols = syms.get("results", [])

    # Inbound: who calls symbols defined in this file.
    inbound_q = (
        f'MATCH (caller)-[:CALLS]->(callee) '
        f'WHERE callee.file_path = "{file_path}" '
        f'RETURN caller.name AS caller, caller.file_path AS caller_file, '
        f'callee.name AS callee LIMIT 100'
    )
    # Outbound: what symbols defined in this file call.
    outbound_q = (
        f'MATCH (caller)-[:CALLS]->(callee) '
        f'WHERE caller.file_path = "{file_path}" '
        f'RETURN caller.name AS caller, callee.name AS callee, '
        f'callee.file_path AS callee_file LIMIT 100'
    )
    try:
        inbound = cbm.query_graph(inbound_q).get("rows", [])
    except CBMError:
        inbound = []
    try:
        outbound = cbm.query_graph(outbound_q).get("rows", [])
    except CBMError:
        outbound = []
    return {"symbols": symbols, "inbound": inbound, "outbound": outbound}


def _read_source(repo_root: Path, file_path: str) -> str:
    p = repo_root / file_path
    text = p.read_text(errors="replace")
    if len(text) > MAX_SOURCE_CHARS:
        head = text[: MAX_SOURCE_CHARS]
        text = head + f"\n\n/* ... truncated {len(text) - MAX_SOURCE_CHARS} chars ... */\n"
    return text


def _annotation_path(kb_root: Path, file_path: str) -> Path:
    # db/db_impl.cc -> annotations/db/db_impl.md
    rel = Path(file_path)
    out = kb_root / "annotations" / rel.parent / (rel.stem + ".md")
    return out


def _front_matter(file_path: str, symbol_count: int, model: str) -> str:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return (
        "---\n"
        "status: pending\n"
        f"file: {file_path}\n"
        f"symbols: {symbol_count}\n"
        f"annotated_at: {ts}\n"
        f"model: {model}\n"
        "---\n\n"
    )


def annotate_file(
    file_path: str,
    *,
    cbm: CBMClient,
    llm: LLMClient,
    repo_root: Path,
    kb_root: Path,
    business_context: str,
    dry_run: bool = False,
    force: bool = False,
) -> Path | None:
    out_path = _annotation_path(kb_root, file_path)
    if out_path.exists() and not force:
        print(f"  [skip] {file_path} -> {out_path} already exists (pass --force to regenerate)")
        return out_path

    ctx = _fetch_context(cbm, file_path)
    source = _read_source(repo_root, file_path)

    prompt = ANNOTATE_PROMPT.format(
        business_context=business_context,
        file_path=file_path,
        inbound=_fmt_edges(ctx["inbound"], "callers"),
        outbound=_fmt_edges(ctx["outbound"], "callees"),
        symbols=_fmt_symbols(ctx["symbols"]),
        source=source,
    )

    if dry_run:
        print(f"  [dry-run] {file_path} prompt={len(prompt)} chars, "
              f"symbols={len(ctx['symbols'])}, in={len(ctx['inbound'])}, "
              f"out={len(ctx['outbound'])}")
        return None

    print(f"  -> LLM call for {file_path} (prompt={len(prompt)} chars)")
    reply = llm.complete(prompt)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    header = _front_matter(file_path, len(ctx["symbols"]), llm.model)
    out_path.write_text(header + reply.strip() + "\n")
    print(f"  [wrote] {out_path} ({len(reply)} chars)")
    return out_path


def run(
    files: Iterable[str],
    *,
    dry_run: bool = False,
    force: bool = False,
) -> None:
    cfg = load_config()
    repo_root = Path(cfg["codebase_memory"]["repo_path"])
    kb_root = Path(cfg["knowledge_base"]["root"])
    if not kb_root.is_absolute():
        kb_root = Path(__file__).resolve().parent.parent / kb_root
    business_context = (kb_root / "business-context.md").read_text()

    cbm = CBMClient(config=cfg)
    llm = None if dry_run else LLMClient(config=cfg)

    last_call = 0.0
    for i, f in enumerate(files):
        print(f"[{i+1}] {f}")
        # Simple rate-limit pacing.
        if not dry_run and i > 0:
            elapsed = time.monotonic() - last_call
            if elapsed < MIN_SECONDS_BETWEEN_CALLS:
                time.sleep(MIN_SECONDS_BETWEEN_CALLS - elapsed)
        try:
            annotate_file(
                f,
                cbm=cbm,
                llm=llm,
                repo_root=repo_root,
                kb_root=kb_root,
                business_context=business_context,
                dry_run=dry_run,
                force=force,
            )
        except Exception as e:
            print(f"  [error] {f}: {e}")
        last_call = time.monotonic()


def main() -> None:
    ap = argparse.ArgumentParser(description="Annotate TypeScript source files with Kimi.")
    ap.add_argument("files", nargs="*", help="Files to annotate.")
    ap.add_argument("--discover", action="store_true",
                    help="Auto-discover .ts/.tsx files via codebase-memory (ignores positional files).")
    ap.add_argument("--dry-run", action="store_true", help="Build prompts but skip LLM calls.")
    ap.add_argument("--force", action="store_true", help="Overwrite existing annotations.")
    ap.add_argument("--limit", type=int, default=None, help="Only process first N files.")
    args = ap.parse_args()

    if args.discover:
        cfg = load_config()
        cbm = CBMClient(config=cfg)
        files: list[str] = discover_ts_files(cbm)
        if not files:
            print("[warn] --discover found no .ts/.tsx files. Has the repo been indexed?")
            print("       Run: codebase-memory-mcp cli index_repository '{\"repo_path\": \"...\"}'")
            return
        print(f"[discover] found {len(files)} TypeScript files")
    elif args.files:
        files = args.files
    elif SCOPE:
        files = SCOPE
    else:
        print("[error] No files specified. Pass file paths, use --discover, or populate SCOPE.")
        return

    if args.limit is not None:
        files = files[: args.limit]
    run(files, dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":
    main()
