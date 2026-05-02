"""
DiagnosticAgent — the first agent in the pipeline.

Responsibilities:
1. Receive error events from Sentry / CI logs
2. Run AST analysis on files in the error call chain
3. Call the LLM with structured prompts for deep root cause analysis
4. Output a DiagnosticReport consumed by the CodingAgent
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.agents.base import AgentReport, BaseAgent
from src.llm.client import LLMClient
from src.llm.prompts import DIAGNOSTIC_SYSTEM_PROMPT, build_diagnostic_prompt
from src.tools.ast_analyzer import ASTAnalyser
from src.tools.git_manager import GitManager
from src.tools.log_parser import ParsedCIOutput
from src.tools.sentry_client import SentryErrorEvent


@dataclass
class DiagnosticInput:
    error_event: Optional[SentryErrorEvent] = None
    ci_output: Optional[ParsedCIOutput] = None
    workspace_path: Path = field(default_factory=Path.cwd)


@dataclass
class DiagnosticReport:
    root_cause: str
    call_chain: str
    affected_files: list[str]
    confidence: str  # Low / Medium / High
    impact_assessment: str
    raw_llm_response: str = ""
    ast_summary: str = ""


class DiagnosticAgent(BaseAgent[DiagnosticInput, DiagnosticReport]):
    agent_name = "diagnostic"

    def __init__(
        self,
        llm: LLMClient | None = None,
        ast_analyser: ASTAnalyser | None = None,
        git_manager: GitManager | None = None,
    ) -> None:
        super().__init__(llm)
        self.ast = ast_analyser or ASTAnalyser()
        self.git = git_manager or GitManager()

    async def run(self, input_data: DiagnosticInput) -> AgentReport:
        start = time.time()

        # Step 1: Extract error information
        error_trace, log_excerpts = self._extract_error_data(input_data)

        # Step 2: Run AST analysis on the repository
        ast_summary = self.ast.analyse_repository(input_data.workspace_path)

        # Step 3: Identify affected files from the trace
        affected = self._parse_affected_files(error_trace)

        # Step 4: Generate focused AST summary
        ast_text = self.ast.format_summary(ast_summary, focus_functions=affected)

        # Step 5: Build prompt and call LLM
        prompt = build_diagnostic_prompt(
            error_trace=error_trace,
            log_excerpts=log_excerpts,
            ast_summary=ast_text,
        )

        response = await self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            system=DIAGNOSTIC_SYSTEM_PROMPT,
            temperature=0.2,
        )

        latency = (time.time() - start) * 1000

        # Step 6: Parse the LLM response into structured report
        diag_report = self._parse_diagnosis(response.content, ast_text)

        self.logger.info(
            "diagnosis_complete",
            confidence=diag_report.confidence,
            files=len(diag_report.affected_files),
            tokens=response.usage.get("input_tokens", 0),
        )

        return self._build_report(
            status="success",
            token_usage=response.usage,
            latency_ms=latency,
            diagnostic_report=diag_report,
        )

    def _extract_error_data(self, inp: DiagnosticInput) -> tuple[str, str]:
        trace = ""
        logs = ""

        if inp.error_event:
            trace = inp.error_event.stacktrace
            logs = inp.error_event.title + "\n" + inp.error_event.culprit

        if inp.ci_output:
            if not trace:
                err_msgs = [e.message for e in inp.ci_output.errors if e.level == "TRACEBACK"]
                trace = "\n".join(err_msgs)
            logs += "\n" + inp.ci_output.raw_tail

        return trace or "No error trace available.", logs or "No logs available."

    @staticmethod
    def _parse_affected_files(error_trace: str) -> list[str]:
        import re
        pattern = re.compile(r'["\']?([\w/\-]+\.py)["\']?')
        files = pattern.findall(error_trace)
        return list(set(files))

    @staticmethod
    def _parse_diagnosis(llm_output: str, ast_summary: str) -> DiagnosticReport:
        confidence = "Medium"
        if "confidence: high" in llm_output.lower():
            confidence = "High"
        elif "confidence: low" in llm_output.lower():
            confidence = "Low"

        # Extract affected files
        import re
        file_pattern = re.compile(r'([\w/\-]+\.py):(\d+)')
        affected = list(set(f[0] for f in file_pattern.findall(llm_output)))

        return DiagnosticReport(
            root_cause=llm_output,
            call_chain=llm_output,
            affected_files=affected,
            confidence=confidence,
            impact_assessment=llm_output,
            raw_llm_response=llm_output,
            ast_summary=ast_summary,
        )
