"""
CodingAgent — the second agent in the pipeline.

Responsibilities:
1. Receive the DiagnosticReport from DiagnosticAgent
2. Read full source files for all affected paths
3. Generate a surgical fix patch + complementary unit tests
4. Output a CodingReport consumed by the ReviewAgent
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.agents.base import AgentReport, BaseAgent
from src.agents.diagnostic_agent import DiagnosticReport
from src.llm.client import LLMClient
from src.llm.prompts import CODING_SYSTEM_PROMPT, build_coding_prompt


@dataclass
class CodingInput:
    diagnostic_report: DiagnosticReport
    workspace_path: Path = field(default_factory=Path.cwd)
    max_source_files: int = 20


@dataclass
class CodingReport:
    fix_patch: str
    new_tests: str
    explanation: str
    modified_files: list[str]
    new_test_files: list[str]


class CodingAgent(BaseAgent[CodingInput, CodingReport]):
    agent_name = "coding"

    async def run(self, input_data: CodingInput) -> AgentReport:
        start = time.time()

        # Step 1: Read all affected source files
        source_files = self._read_source_files(
            input_data.workspace_path,
            input_data.diagnostic_report.affected_files,
        )

        # Step 2: Build the coding prompt
        prompt = build_coding_prompt(
            diagnostic_report=input_data.diagnostic_report.raw_llm_response,
            source_files=source_files,
        )

        # Step 3: Call LLM to generate the fix
        response = await self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            system=CODING_SYSTEM_PROMPT,
            temperature=0.1,
        )

        latency = (time.time() - start) * 1000

        # Step 4: Parse the generated code from the LLM output
        coding_report = self._parse_code_output(
            response.content,
            input_data.diagnostic_report.affected_files,
        )

        self.logger.info(
            "coding_complete",
            modified_files=len(coding_report.modified_files),
            patch_lines=len(coding_report.fix_patch.splitlines()),
            tokens=response.usage.get("input_tokens", 0),
        )

        return self._build_report(
            status="success",
            token_usage=response.usage,
            latency_ms=latency,
            coding_report=coding_report,
        )

    def _read_source_files(
        self, workspace: Path, file_paths: list[str]
    ) -> dict[str, str]:
        sources: dict[str, str] = {}
        for relative_path in file_paths:
            full_path = workspace / relative_path
            if full_path.exists() and full_path.suffix == ".py":
                try:
                    sources[relative_path] = full_path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    self.logger.warning("read_failed", path=relative_path)
        return sources

    @staticmethod
    def _parse_code_output(
        llm_output: str, affected_files: list[str]
    ) -> CodingReport:
        import re

        # Extract code blocks
        diff_pattern = re.compile(r'```diff\n(.*?)\n```', re.DOTALL)
        python_pattern = re.compile(r'```python\n(.*?)\n```', re.DOTALL)

        fix_patch = ""
        new_tests = ""
        explanation = llm_output

        diffs = diff_pattern.findall(llm_output)
        if diffs:
            fix_patch = "\n\n".join(diffs)

        py_blocks = python_pattern.findall(llm_output)
        if py_blocks:
            new_tests = "\n\n".join(py_blocks)

        # Separate explanation (text before first code block)
        first_block = llm_output.find("```")
        if first_block > 0:
            explanation = llm_output[:first_block].strip()

        return CodingReport(
            fix_patch=fix_patch,
            new_tests=new_tests,
            explanation=explanation,
            modified_files=affected_files,
            new_test_files=[f.replace(".py", "_test.py") for f in affected_files],
        )
