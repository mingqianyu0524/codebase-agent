"""Interactive Q&A CLI for the LevelDB knowledge base."""
from __future__ import annotations

import argparse
import re
import shlex
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from .cbm_client import CBMClient, CBMError
from .config import load_config
from .context_manager import ContextManager
from .llm_client import LLMClient
from .prompt_templates import CORRECTION_PROMPT, QA_PROMPT

MAX_CONTEXT_CHARS = 20_000

HELP = """\
Commands:
  <free-text>        — ask a question; answered with LLM + retrieved context
  ?<query>           — structural-only query, CBM (no LLM)
                       • `?SymbolName`   → search_graph by name
                       • `?trace Foo`    → trace_call_path both directions
                       • `?file db/x.cc` → list symbols in that file
  !<path> <text>     — correction: LLM rewrites annotation/business-context
                       • `!db/db_impl.cc Actually this also calls Foo()`
                       • `!business-context Clarify that WAL fsyncs every ...`
  /export workflow   — regenerate Layer-3 workflow docs (reuses spec)
  /status            — annotation/workflow coverage
  /help              — this help
  /exit or /quit     — leave
"""


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n/* ... {len(text) - limit} chars truncated ... */"


def _format_context(chunks) -> str:
    if not chunks:
        return "_(no relevant context found)_"
    parts = []
    for c in chunks:
        parts.append(f"### {c.title}\n{c.body}")
    joined = "\n\n".join(parts)
    return _truncate(joined, MAX_CONTEXT_CHARS)


class REPL:
    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()
        self.cfg = load_config()
        kb_root = Path(self.cfg["knowledge_base"]["root"])
        if not kb_root.is_absolute():
            kb_root = Path(__file__).resolve().parent.parent / kb_root
        self.kb_root = kb_root
        self.cbm = CBMClient(config=self.cfg)
        self.llm = LLMClient(config=self.cfg)
        self.ctx = ContextManager(kb_root, self.cbm)

    # --- command handlers -------------------------------------------------

    def handle_structural(self, q: str) -> None:
        q = q.strip()
        if not q:
            self.console.print("[yellow]Empty structural query.[/yellow]")
            return
        if q.lower().startswith("trace "):
            fn = q[6:].strip()
            try:
                res = self.cbm.trace_call_path(function_name=fn, direction="both")
            except CBMError as e:
                self.console.print(f"[red]{e}[/red]")
                return
            self.console.print(Panel.fit(str(res), title=f"trace {fn}"))
            return
        if q.lower().startswith("file "):
            fp = q[5:].strip()
            try:
                res = self.cbm.search_graph(file_pattern=fp, limit=200)
            except CBMError as e:
                self.console.print(f"[red]{e}[/red]")
                return
            self._print_search(res, title=f"symbols in {fp}")
            return
        # Default: name_pattern search.
        try:
            res = self.cbm.search_graph(name_pattern=q, limit=50)
        except CBMError as e:
            self.console.print(f"[red]{e}[/red]")
            return
        self._print_search(res, title=f"search_graph name~{q!r}")

    def _print_search(self, res: dict, *, title: str) -> None:
        results = res.get("results", [])
        table = Table(title=f"{title} — {res.get('total', len(results))} hits")
        table.add_column("label")
        table.add_column("name")
        table.add_column("qualified_name", overflow="fold")
        table.add_column("file", overflow="fold")
        for r in results[:50]:
            table.add_row(
                r.get("label", ""),
                r.get("name", ""),
                r.get("qualified_name", ""),
                r.get("file_path", ""),
            )
        self.console.print(table)

    def handle_correction(self, args: str) -> None:
        """`!<path> <correction text>`"""
        parts = args.strip().split(None, 1)
        if len(parts) < 2:
            self.console.print("[yellow]Usage: !<path-or-business-context> <correction text>[/yellow]")
            return
        target_hint, correction = parts[0], parts[1]

        if target_hint.lower().startswith("business"):
            target = self.kb_root / "business-context.md"
        else:
            target = self.ctx.find_annotation(target_hint)
            if target is None:
                self.console.print(
                    f"[red]Could not locate annotation for {target_hint!r}.[/red] "
                    f"Try `business-context` or a source path like `db/db_impl.cc`."
                )
                return

        existing = target.read_text()
        prompt = CORRECTION_PROMPT.format(
            target_file=target.relative_to(self.kb_root),
            existing=existing,
            correction=correction,
        )
        self.console.print(f"[dim]Rewriting {target.relative_to(self.kb_root)} via LLM…[/dim]")
        new_text = self.llm.complete(prompt).strip()
        # Strip accidental code fences.
        new_text = re.sub(r"^```[a-zA-Z]*\s*", "", new_text)
        new_text = re.sub(r"\s*```$", "", new_text)

        # Show a diff preview.
        self.console.rule(f"Proposed update → {target.relative_to(self.kb_root)}")
        self.console.print(Markdown(new_text[:4000]))
        if len(new_text) > 4000:
            self.console.print(f"[dim]... ({len(new_text) - 4000} chars more)[/dim]")
        choice = Prompt.ask("Apply?", choices=["y", "n"], default="n")
        if choice == "y":
            target.write_text(new_text + ("\n" if not new_text.endswith("\n") else ""))
            self.console.print(f"[green]Wrote {target}[/green]")
        else:
            self.console.print("[yellow]Discarded.[/yellow]")

    def handle_status(self) -> None:
        s = self.ctx.stats()
        table = Table(title="Knowledge-Base Coverage")
        table.add_column("metric")
        table.add_column("value", justify="right")
        for k, v in s.items():
            table.add_row(k, str(v))
        self.console.print(table)

    def handle_export(self, args: str) -> None:
        if args.strip() != "workflow":
            self.console.print("[yellow]Usage: /export workflow[/yellow]")
            return
        from . import workflow_exporter
        self.console.print("[dim]Running workflow exporter (reuses _discovered.json)…[/dim]")
        try:
            workflow_exporter.run()
            self.console.print("[green]Export complete.[/green]")
        except Exception as e:
            self.console.print(f"[red]Export failed: {e}[/red]")

    def handle_question(self, q: str) -> None:
        chunks = self.ctx.retrieve(q)
        if not chunks:
            self.console.print("[yellow]No relevant annotations or CBM matches — answering from business-context only.[/yellow]")
        prompt = QA_PROMPT.format(
            business_context=self.ctx.business_context(),
            context=_format_context(chunks),
            question=q,
        )
        self.console.print(f"[dim]Retrieved {len(chunks)} context chunks; calling LLM…[/dim]")
        answer = self.llm.complete(prompt)
        self.console.rule("Answer")
        self.console.print(Markdown(answer))
        if chunks:
            self.console.print(
                f"\n[dim]Sources: {', '.join(c.source for c in chunks)}[/dim]"
            )

    # --- main loop --------------------------------------------------------

    def run(self) -> None:
        self.console.print(Panel.fit(
            "[bold]LevelDB Knowledge-Base CLI[/bold]\n"
            f"model: {self.llm.model}   kb: {self.kb_root}\n\n"
            "Type /help for commands. /exit to quit.",
            title="ready",
        ))
        while True:
            try:
                line = Prompt.ask("[bold cyan]>[/bold cyan]")
            except (EOFError, KeyboardInterrupt):
                self.console.print("\n[dim]bye[/dim]")
                return
            line = line.strip()
            if not line:
                continue
            try:
                if line in ("/exit", "/quit"):
                    return
                if line == "/help":
                    self.console.print(HELP)
                    continue
                if line == "/status":
                    self.handle_status()
                    continue
                if line.startswith("/export"):
                    self.handle_export(line[len("/export"):].strip())
                    continue
                if line.startswith("?"):
                    self.handle_structural(line[1:])
                    continue
                if line.startswith("!"):
                    self.handle_correction(line[1:])
                    continue
                self.handle_question(line)
            except Exception as e:
                self.console.print(f"[red]Error: {e}[/red]")


def main() -> None:
    ap = argparse.ArgumentParser(description="Interactive LevelDB knowledge-base CLI.")
    args = ap.parse_args()
    REPL().run()


if __name__ == "__main__":
    main()
