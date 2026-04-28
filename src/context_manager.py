"""Retrieve relevant knowledge-base context for a free-text query."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .cbm_client import CBMClient, CBMError

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "and", "or", "but", "of", "in", "on", "at", "to", "for", "from", "by",
    "with", "about", "as", "into", "through", "that", "this", "these",
    "those", "it", "its", "if", "how", "what", "why", "when", "where", "who",
    "which", "does", "do", "did", "can", "could", "should", "would",
    "leveldb",
}
# Camel-case identifiers worth looking up in CBM.
_IDENT_RE = re.compile(r"\b[A-Z][a-zA-Z0-9_]{2,}(?:::[A-Za-z0-9_]+)*\b")
# English words OR Chinese character sequences (2+ chars).
_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}|[一-鿿]{2,}")


@dataclass
class RetrievedChunk:
    source: str          # e.g. "annotations/db/db_impl.md" or "cbm:search"
    title: str
    body: str
    score: float = 0.0


def _tokens(text: str) -> list[str]:
    tokens = []
    for w in _WORD_RE.findall(text):
        if w[0].isascii():
            t = w.lower()
            if t not in _STOPWORDS:
                tokens.append(t)
        else:
            tokens.append(w)  # Chinese sequences: keep as-is
    return tokens


def _score_annotation(query_tokens: list[str], body: str) -> float:
    if not query_tokens:
        return 0.0
    body_lower = body.lower()
    hits = sum(body_lower.count(t) for t in set(query_tokens))
    return hits / max(len(body), 1) * 1000  # normalize by length


class ContextManager:
    def __init__(self, kb_root: Path, cbm: CBMClient):
        self.kb_root = kb_root
        self.annotations_dir = kb_root / "annotations"
        self.workflows_dir = kb_root / "workflows"
        self.cbm = cbm
        self._annotation_cache: list[tuple[Path, str]] | None = None

    def _annotations(self) -> list[tuple[Path, str]]:
        if self._annotation_cache is None:
            self._annotation_cache = [
                (p, p.read_text()) for p in sorted(self.annotations_dir.rglob("*.md"))
            ]
        return self._annotation_cache

    def business_context(self) -> str:
        bc = self.kb_root / "business-context.md"
        return bc.read_text() if bc.exists() else ""

    def retrieve(self, query: str, *, top_k: int = 4, cbm_limit: int = 6) -> list[RetrievedChunk]:
        tokens = _tokens(query)
        chunks: list[RetrievedChunk] = []

        scored: list[tuple[float, Path, str]] = []
        for path, text in self._annotations():
            score = _score_annotation(tokens, text)
            if score > 0:
                scored.append((score, path, text))
        scored.sort(key=lambda x: -x[0])
        for score, path, text in scored[:top_k]:
            rel = path.relative_to(self.kb_root)
            chunks.append(
                RetrievedChunk(
                    source=f"annotation:{rel}",
                    title=str(rel),
                    body=text,
                    score=score,
                )
            )

        # Pull CBM symbol matches for any identifier-shaped token in the query.
        seen: set[str] = set()
        idents = _IDENT_RE.findall(query)
        for raw in idents:
            name = raw.split("::")[-1]
            if name in seen:
                continue
            seen.add(name)
            try:
                res = self.cbm.search_graph(name_pattern=name, limit=cbm_limit)
            except CBMError:
                continue
            hits = res.get("results", [])
            if not hits:
                continue
            lines = [
                f"- [{h.get('label')}] {h.get('qualified_name')} "
                f"(file={h.get('file_path')})"
                for h in hits
            ]
            chunks.append(
                RetrievedChunk(
                    source="cbm:search_graph",
                    title=f"CBM matches for `{name}`",
                    body="\n".join(lines),
                    score=float(len(hits)),
                )
            )

        return chunks

    def stats(self) -> dict:
        annotations = list(self.annotations_dir.rglob("*.md"))
        workflows = list(self.workflows_dir.glob("*.md"))
        pending = 0
        reviewed = 0
        for p, text in self._annotations():
            m = re.search(r"^status:\s*(\S+)", text, re.MULTILINE)
            status = m.group(1) if m else "unknown"
            if status == "reviewed":
                reviewed += 1
            else:
                pending += 1
        return {
            "annotations_total": len(annotations),
            "annotations_pending": pending,
            "annotations_reviewed": reviewed,
            "workflows_total": len(workflows),
        }

    def find_annotation(self, file_hint: str) -> Path | None:
        """Locate an annotation file by source-file hint (e.g. 'db/db_impl.cc' → annotations/db/db_impl.md)."""
        hint = file_hint.strip()
        target_stem = Path(hint).stem
        target_dir = Path(hint).parent
        candidates = [
            self.annotations_dir / target_dir / f"{target_stem}.md",
        ]
        for c in candidates:
            if c.exists():
                return c
        # Fallback: scan.
        for p in self.annotations_dir.rglob("*.md"):
            if p.stem == target_stem:
                return p
        return None
