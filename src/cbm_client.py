"""Codebase-Memory MCP CLI wrapper."""
from __future__ import annotations

import json
import subprocess
from typing import Any, Optional

from .config import load_config


class CBMError(RuntimeError):
    pass


class CBMClient:
    def __init__(self, config: Optional[dict] = None):
        cfg = config or load_config()
        cbm = cfg["codebase_memory"]
        self.binary = cbm["binary"]
        self.repo_path = cbm["repo_path"]
        self.project = cbm.get("project")

    def _call(self, tool: str, params: dict | None = None) -> Any:
        params = dict(params or {})
        if self.project and "project" not in params and tool != "list_projects":
            params["project"] = self.project
        args = [self.binary, "cli", tool, json.dumps(params)]
        try:
            proc = subprocess.run(args, capture_output=True, text=True, timeout=120)
        except FileNotFoundError as e:
            raise CBMError(f"codebase-memory-mcp binary not found: {e}") from e
        except subprocess.TimeoutExpired as e:
            raise CBMError(f"cbm CLI timed out: {tool}") from e

        # stdout contains JSON envelope; stderr contains log lines.
        stdout = proc.stdout.strip()
        if not stdout:
            raise CBMError(f"cbm returned empty output (stderr={proc.stderr!r})")

        # Some commands emit one or more log lines on stdout before JSON; take last line.
        last_line = stdout.splitlines()[-1]
        try:
            envelope = json.loads(last_line)
        except json.JSONDecodeError as e:
            raise CBMError(f"cbm returned non-JSON: {last_line!r}") from e

        content = envelope.get("content", [])
        if not content:
            raise CBMError(f"cbm envelope missing content: {envelope}")
        text = content[0].get("text", "")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = {"raw": text}

        if envelope.get("isError"):
            raise CBMError(f"cbm tool '{tool}' error: {payload}")
        return payload

    # Convenience wrappers -------------------------------------------------

    def list_projects(self) -> dict:
        return self._call("list_projects", {})

    def get_graph_schema(self) -> dict:
        return self._call("get_graph_schema")

    def get_architecture(self, aspects: Optional[list] = None) -> dict:
        params = {}
        if aspects:
            params["aspects"] = aspects
        return self._call("get_architecture", params)

    def search_graph(
        self,
        *,
        name_pattern: Optional[str] = None,
        file_pattern: Optional[str] = None,
        label: Optional[str] = None,
        qn_pattern: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> dict:
        params = {}
        if name_pattern:
            params["name_pattern"] = name_pattern
        if file_pattern:
            params["file_pattern"] = file_pattern
        if label:
            params["label"] = label
        if qn_pattern:
            params["qn_pattern"] = qn_pattern
        if limit:
            params["limit"] = limit
        return self._call("search_graph", params)

    def trace_call_path(self, function_name: str, direction: str = "both") -> dict:
        return self._call(
            "trace_call_path",
            {"function_name": function_name, "direction": direction},
        )

    def trace_path(self, function_name: str, mode: str = "calls") -> dict:
        return self._call(
            "trace_path", {"function_name": function_name, "mode": mode}
        )

    def get_code_snippet(self, qualified_name: str) -> dict:
        return self._call("get_code_snippet", {"qualified_name": qualified_name})

    def query_graph(self, query: str) -> dict:
        return self._call("query_graph", {"query": query})

    def find_dead_code(self) -> dict:
        return self._call("find_dead_code")


if __name__ == "__main__":
    import pprint

    c = CBMClient()
    print("== list_projects ==")
    pprint.pp(c.list_projects())
    print("\n== get_graph_schema ==")
    pprint.pp(c.get_graph_schema())
