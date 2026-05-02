"""
Multi-Agent Orchestrator — the central execution engine that coordinates
the three-agent pipeline: Diagnose → Code → Review.

Supports:
- Automatic retry loops (on REJECT, CodingAgent revises)
- Parallel processing of multiple error events
- Token usage aggregation across the full pipeline
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Optional

from src.agents.base import AgentReport
from src.agents.diagnostic_agent import DiagnosticAgent, DiagnosticInput, DiagnosticReport
from src.agents.coding_agent import CodingAgent, CodingInput, CodingReport
from src.agents.review_agent import ReviewAgent, ReviewInput, ReviewReport, ReviewVerdict
from src.tools.git_manager import GitManager
from src.tools.mr_manager import MRInfo, MRManager
from src.utils.logger import get_console, get_logger

logger = get_logger(__name__)
console = get_console()


@dataclass
class PipelineResult:
    success: bool
    diagnostic_report: Optional[DiagnosticReport] = None
    coding_report: Optional[CodingReport] = None
    review_report: Optional[ReviewReport] = None
    total_tokens: int = 0
    total_latency_ms: float = 0.0
    retries: int = 0
    mr_url: str = ""
    errors: list[str] = field(default_factory=list)


class Orchestrator:
    """Orchestrates the full Diagnose → Code → Review → Merge pipeline."""

    MAX_RETRIES = 3

    def __init__(
        self,
        diagnostic_agent: DiagnosticAgent | None = None,
        coding_agent: CodingAgent | None = None,
        review_agent: ReviewAgent | None = None,
        git_manager: GitManager | None = None,
        mr_manager: MRManager | None = None,
    ) -> None:
        self.diagnostic = diagnostic_agent or DiagnosticAgent()
        self.coding = coding_agent or CodingAgent()
        self.review = review_agent or ReviewAgent()
        self.git = git_manager or GitManager()
        self.mr = mr_manager or MRManager()

    async def run_pipeline(
        self,
        diag_input: DiagnosticInput,
        repo_slug: str = "",
        auto_merge: bool = False,
    ) -> PipelineResult:
        """Execute the full auto-heal pipeline for a single error event."""
        result = PipelineResult(success=False)

        console.rule("[bold blue]🚀 Auto-Heal Pipeline Started")
        logger.info("pipeline_started")

        # Phase 1: Diagnosis
        diag_report = await self.diagnostic.run(diag_input)
        result.total_tokens += self._extract_tokens(diag_report)
        result.total_latency_ms += diag_report.latency_ms

        if diag_report.status != "success":
            result.errors.append("Diagnostic phase failed")
            return result

        diagnosis: DiagnosticReport = diag_report.data["diagnostic_report"]
        result.diagnostic_report = diagnosis

        # Phase 2: Code (with retry on review rejection)
        coding_input = CodingInput(
            diagnostic_report=diagnosis,
            workspace_path=diag_input.workspace_path,
        )

        for attempt in range(1, self.MAX_RETRIES + 1):
            if attempt > 1:
                # Feed the rejection feedback back into the coding agent
                coding_input.diagnostic_report.raw_llm_response += (
                    f"\n\n## Review Feedback (Attempt {attempt - 1})\n"
                    + (result.review_report.feedback if result.review_report else "")
                )

            # Phase 2a: Generate fix
            coding_report = await self.coding.run(coding_input)
            result.total_tokens += self._extract_tokens(coding_report)
            result.total_latency_ms += coding_report.latency_ms

            if coding_report.status != "success":
                result.errors.append(f"Coding phase failed on attempt {attempt}")
                continue

            code: CodingReport = coding_report.data["coding_report"]
            result.coding_report = code

            # Phase 3: Review
            review_input = ReviewInput(
                diagnostic_report=diagnosis,
                coding_report=code,
            )

            review_report = await self.review.run(review_input)
            result.total_tokens += self._extract_tokens(review_report)
            result.total_latency_ms += review_report.latency_ms

            review: ReviewReport = review_report.data["review_report"]
            result.review_report = review
            result.retries = attempt - 1

            if review.verdict == ReviewVerdict.APPROVE:
                result.success = True
                break
            elif review.verdict == ReviewVerdict.REJECT:
                logger.info("retry_coding", attempt=attempt, feedback=review.feedback[:200])
            else:
                result.errors.append(f"Review needs clarification (attempt {attempt})")

        # Phase 4: Apply fix and create MR (if approved)
        if result.success and result.coding_report:
            result.mr_url = await self._apply_and_submit(
                result.coding_report, repo_slug, auto_merge
            )

        console.rule(
            f"[bold green]✅ Pipeline Complete — {'APPROVED' if result.success else 'REJECTED'}"
        )
        logger.info(
            "pipeline_complete",
            success=result.success,
            tokens=result.total_tokens,
            latency_ms=result.total_latency_ms,
            retries=result.retries,
        )

        return result

    async def run_batch(
        self,
        inputs: list[DiagnosticInput],
        repo_slug: str = "",
        auto_merge: bool = False,
    ) -> list[PipelineResult]:
        """Process multiple error events concurrently (up to MAX_CONCURRENT)."""
        from src.config import get_settings
        settings = get_settings()
        max_concurrent = settings.max_concurrent_agents

        semaphore = asyncio.Semaphore(max_concurrent)

        async def bounded_run(inp: DiagnosticInput) -> PipelineResult:
            async with semaphore:
                return await self.run_pipeline(inp, repo_slug=repo_slug, auto_merge=auto_merge)

        tasks = [bounded_run(inp) for inp in inputs]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        return [
            r if isinstance(r, PipelineResult) else PipelineResult(success=False, errors=[str(r)])
            for r in results
        ]

    async def _apply_and_submit(
        self, code: CodingReport, repo_slug: str, auto_merge: bool
    ) -> str:
        """Apply the fix to the repo, commit, and optionally submit an MR."""
        import uuid
        branch = f"auto-heal/fix-{uuid.uuid4().hex[:8]}"
        self.git.create_branch(branch)

        # Apply patch to each modified file
        for file_path in code.modified_files:
            self.git.apply_patch(code.fix_patch, file_path)

        # Write new test files
        for test_file in code.new_test_files:
            self.git.write_new_file(test_file, code.new_tests)

        commit_msg = (
            f"fix(auto-heal): {code.explanation[:80]}\n\n"
            f"Auto-generated by microservice-auto-heal multi-agent pipeline.\n"
            f"Modified: {', '.join(code.modified_files)}"
        )
        self.git.stage_and_commit(commit_msg)

        mr_url = ""
        if auto_merge and repo_slug:
            self.git.push(branch)
            mr_info = MRInfo(
                platform="github",
                title=f"fix(auto-heal): {code.explanation[:60]}",
                description=code.explanation,
                source_branch=branch,
                target_branch="main",
            )
            result = await self.mr.create_mr(mr_info, repo_slug)
            mr_url = result.url

        return mr_url

    @staticmethod
    def _extract_tokens(report: AgentReport) -> int:
        return report.token_usage.get("input_tokens", 0) + report.token_usage.get("output_tokens", 0)
