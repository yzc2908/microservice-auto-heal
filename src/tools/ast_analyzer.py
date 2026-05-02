"""
AST (Abstract Syntax Tree) analyser that extracts call chains, data-flow
paths, and structural summaries from Python source code.

Used by DiagnosticAgent to trace execution paths across files.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class FunctionInfo:
    name: str
    file: str
    lineno: int
    end_lineno: int
    args: list[str]
    calls: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)


@dataclass
class CallChainNode:
    function: FunctionInfo
    callers: list[CallChainNode] = field(default_factory=list)
    callees: list[CallChainNode] = field(default_factory=list)


@dataclass
class ASTSummary:
    files_analysed: int
    total_functions: int
    total_classes: int
    imports_graph: dict[str, list[str]]
    functions: dict[str, FunctionInfo]
    entry_points: list[FunctionInfo]


class ASTAnalyser:
    """Parses Python source trees and extracts structured call-graph data."""

    def analyse_file(self, file_path: Path) -> dict[str, FunctionInfo]:
        if not file_path.exists():
            logger.warning("file_not_found", path=str(file_path))
            return {}

        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        visitor = _FunctionVisitor(str(file_path))
        visitor.visit(tree)
        return visitor.functions

    def analyse_repository(self, root: Path, glob_pattern: str = "**/*.py") -> ASTSummary:
        functions: dict[str, FunctionInfo] = {}
        imports: dict[str, list[str]] = {}
        total_classes = 0

        for py_file in root.glob(glob_pattern):
            if any(skip in py_file.parts for skip in (".git", ".venv", "venv", "__pycache__", "node_modules")):
                continue

            file_fns = self.analyse_file(py_file)
            functions.update(file_fns)

            # Count classes
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source)
            cls_visitor = _ClassCounter()
            cls_visitor.visit(tree)
            total_classes += cls_visitor.count

            # Collect imports
            imports[str(py_file)] = self._extract_imports(tree)

        entry_points = [f for f in functions.values() if not f.decorators and f.args]

        return ASTSummary(
            files_analysed=len(set(f.file for f in functions.values())),
            total_functions=len(functions),
            total_classes=total_classes,
            imports_graph=imports,
            functions=functions,
            entry_points=entry_points,
        )

    def trace_call_chain(
        self, summary: ASTSummary, start_function: str
    ) -> Optional[CallChainNode]:
        """Build a forward call chain starting from a given function name."""
        fn = summary.functions.get(start_function)
        if fn is None:
            return None

        root = CallChainNode(function=fn)
        for callee_name in fn.calls:
            callee = summary.functions.get(callee_name)
            if callee:
                child = CallChainNode(function=callee)
                root.callees.append(child)
        return root

    def format_summary(self, summary: ASTSummary, focus_functions: list[str] | None = None) -> str:
        lines = [
            f"AST Analysis — {summary.files_analysed} files, "
            f"{summary.total_functions} functions, {summary.total_classes} classes",
            "-" * 60,
        ]

        fns_to_show = focus_functions or list(summary.functions.keys())[:50]
        for name in fns_to_show:
            fn = summary.functions.get(name)
            if fn is None:
                continue
            call_str = ", ".join(fn.calls[:10]) if fn.calls else "(no calls)"
            lines.append(
                f"  {name}() @ {fn.file}:{fn.lineno}-{fn.end_lineno} "
                f"→ calls: [{call_str}]"
            )

        return "\n".join(lines)

    @staticmethod
    def _extract_imports(tree: ast.AST) -> list[str]:
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imports.append(module)
        return imports


class _FunctionVisitor(ast.NodeVisitor):
    def __init__(self, filepath: str) -> None:
        self.filepath = filepath
        self.functions: dict[str, FunctionInfo] = {}

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        info = FunctionInfo(
            name=node.name,
            file=self.filepath,
            lineno=node.lineno,
            end_lineno=node.end_lineno or node.lineno,
            args=[arg.arg for arg in node.args.args],
            decorators=[
                (d.id if isinstance(d, ast.Name) else "complex_decorator")
                for d in node.decorator_list
            ],
        )

        call_collector = _CallCollector()
        call_collector.visit(node)
        info.calls = list(set(call_collector.calls))  # deduplicate

        self.functions[node.name] = info
        self.generic_visit(node)


class _CallCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.calls: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            self.calls.append(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            self.calls.append(node.func.attr)
        self.generic_visit(node)


class _ClassCounter(ast.NodeVisitor):
    def __init__(self) -> None:
        self.count = 0

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.count += 1
        self.generic_visit(node)
