"""Layer 1: extract structural skeleton from Codebase-Memory into markdown."""
from __future__ import annotations

import json
from pathlib import Path

from .cbm_client import CBMClient, CBMError
from .config import load_config

CORE_DIRS = ["db", "table", "util", "include"]


def _md_block(obj) -> str:
    return "```json\n" + json.dumps(obj, indent=2, ensure_ascii=False) + "\n```\n"


def write_architecture(cbm: CBMClient, out: Path) -> None:
    arch = cbm.get_architecture(aspects=["all"])
    body = "# LevelDB — Architecture (from Codebase-Memory)\n\n" + _md_block(arch)
    out.write_text(body)


def write_file_tree(cbm: CBMClient, out: Path) -> None:
    files = cbm.search_graph(label="File", limit=500)
    body = "# LevelDB — File Index\n\n" + _md_block(files)
    out.write_text(body)


def write_dead_code(cbm: CBMClient, out: Path) -> None:
    try:
        dead = cbm.find_dead_code()
    except CBMError as e:
        dead = {"error": str(e)}
    body = "# LevelDB — Dead Code Report\n\n" + _md_block(dead)
    out.write_text(body)


def write_hubs(cbm: CBMClient, out: Path) -> None:
    """Top-10 most-called functions = hubs of the system."""
    query = (
        "MATCH (caller)-[:CALLS]->(f:Function) "
        "RETURN f.name AS name, f.qualified_name AS qn, count(caller) AS inbound "
        "ORDER BY inbound DESC LIMIT 20"
    )
    try:
        hubs = cbm.query_graph(query)
    except CBMError as e:
        hubs = {"error": str(e)}
    body = "# LevelDB — Call Hubs (top inbound CALLS)\n\n" + _md_block(hubs)
    out.write_text(body)


def write_directory_symbols(cbm: CBMClient, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for d in CORE_DIRS:
        # Exclude tests/benchmarks so the skeleton stays focused on production code.
        query = (
            f"MATCH (n) WHERE n.file_path STARTS WITH \"{d}/\" "
            "AND NOT n.file_path CONTAINS \"_test.\" "
            "AND NOT n.file_path CONTAINS \"_bench.\" "
            "RETURN n.name AS name, n.qualified_name AS qn, n.file_path AS fp "
            "ORDER BY n.file_path, n.name"
        )
        try:
            syms = cbm.query_graph(query)
        except CBMError as e:
            syms = {"error": str(e)}
        (out_dir / f"{d}.md").write_text(
            f"# LevelDB — Symbols in `{d}/` (excluding tests/benchmarks)\n\n"
            + _md_block(syms)
        )


def main() -> None:
    cfg = load_config()
    kb_root = Path(cfg["knowledge_base"]["root"])
    if not kb_root.is_absolute():
        kb_root = Path(__file__).resolve().parent.parent / kb_root
    skel = kb_root / "skeleton"
    skel.mkdir(parents=True, exist_ok=True)

    cbm = CBMClient(config=cfg)
    print("-> architecture.md")
    write_architecture(cbm, skel / "architecture.md")
    print("-> file-tree.md")
    write_file_tree(cbm, skel / "file-tree.md")
    print("-> dead-code.md")
    write_dead_code(cbm, skel / "dead-code.md")
    print("-> hubs.md")
    write_hubs(cbm, skel / "hubs.md")
    print("-> by-dir/")
    write_directory_symbols(cbm, skel / "by-dir")
    print(f"Skeleton written to {skel}")


if __name__ == "__main__":
    main()
