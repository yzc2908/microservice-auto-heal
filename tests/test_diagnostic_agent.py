"""Tests for the DiagnosticAgent and AST analyser."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.diagnostic_agent import DiagnosticAgent, DiagnosticInput
from src.tools.ast_analyzer import ASTAnalyser
from src.tools.log_parser import LogParser, ParsedCIOutput


class TestASTAnalyser:
    def test_analyse_single_file(self):
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("""
def foo(x: int) -> int:
    return bar(x + 1)

def bar(y: int) -> int:
    return y * 2

class Calculator:
    def add(self, a, b):
        return a + b
""")
            f.flush()
            path = Path(f.name)

        try:
            analyser = ASTAnalyser()
            functions = analyser.analyse_file(path)

            assert "foo" in functions
            assert "bar" in functions
            assert "add" in functions
            assert functions["foo"].calls == ["bar"] or "bar" in functions["foo"].calls
            assert "x" in functions["foo"].args
        finally:
            path.unlink()

    def test_analyse_repository(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "module_a.py").write_text("""
def process(data):
    return validate(data)

def validate(data):
    return True
""")
            (root / "module_b.py").write_text("""
def handler(req):
    return process(req.body)
""")

            analyser = ASTAnalyser()
            summary = analyser.analyse_repository(root)

            assert summary.files_analysed == 2
            assert summary.total_functions == 3
            assert summary.functions["process"].calls == ["validate"] or "validate" in summary.functions["process"].calls


class TestLogParser:
    def test_parse_github_actions_error(self):
        log = """
Run pytest
##[error]AssertionError: Expected 200, got 500
  File "/app/src/api.py", line 42, in handle_request
  File "/app/src/validator.py", line 15, in validate
##[error]Test failed
"""
        parser = LogParser()
        result = parser.parse_github_actions(log, "test-job")

        assert result.provider == "github_actions"
        assert len(result.errors) >= 2

    def test_parse_clean_log(self):
        parser = LogParser()
        result = parser.parse_github_actions("All tests passed!", "test-job")
        assert result.status == "success"
        assert len(result.errors) == 0


class TestDiagnosticAgent:
    @pytest.mark.asyncio
    async def test_run_with_ci_output(self):
        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(return_value=MagicMock(
            content="Root cause: null pointer\nConfidence: High",
            usage=MagicMock(input_tokens=500, output_tokens=200),
        ))

        ci_output = ParsedCIOutput(
            provider="github_actions",
            job_name="unit-tests",
            status="failure",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "main.py").write_text("def main(): pass")

            agent = DiagnosticAgent(llm=mock_llm)
            report = await agent.run(DiagnosticInput(
                ci_output=ci_output,
                workspace_path=root,
            ))

        assert report.status == "success"
        diag = report.data["diagnostic_report"]
        assert diag.confidence == "High"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
