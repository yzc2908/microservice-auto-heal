"""
ReviewAgent — the third and final agent in the pipeline.

Responsibilities:
1. Receive the CodingReport from CodingAgent
2. Audit the fix for security, correctness, code smells, test adequacy
3. Output APPROVE or REJECT with detailed feedback
4. On APPROVE: auto-commit and submit the Merge Request
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from src.agents.base import AgentReport, BaseAgent
from src.agents.coding_agent import CodingReport
from src.agents.diagnostic_agent import DiagnosticReport
from src.llm.client import LLMClient
from src.llm.prompts import REVIEW_SYSTEM_PROMPT, build_review_prompt


class ReviewVerdict(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"


@dataclass
class ReviewInput:
    diagnostic_report: DiagnosticReport
    coding_report: CodingReport


@dataclass
class ReviewReport:
    verdict: ReviewVerdict
    feedback: str
    security_issues: list[str] = field(default_factory=list)
    code_smells: list[str] = field(default_factory=list)
    test_gaps: list[str] = field(default_factory=list)


class ReviewAgent(BaseAgent[ReviewInput, ReviewReport]):
    agent_name = "review"

    async def run(self, input_data: ReviewInput) -> AgentReport:
        start = time.time()

        # Step 1: Build the review prompt
        prompt = build_review_prompt(
            diagnostic_report=input_data.diagnostic_report.raw_llm_response,
            fix_patch=input_data.coding_report.fix_patch,
            new_tests=input_data.coding_report.new_tests,
            explanation=input_data.coding_report.explanation,
        )

        # Step 2: Call LLM for architectural review
        response = await self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            system=REVIEW_SYSTEM_PROMPT,
            temperature=0.1,
        )

        latency = (time.time() - start) * 1000

        # Step 3: Parse the review verdict
        review_report = self._parse_review(response.content)

        log_extra = {
            "verdict": review_report.verdict.value,
            "security_issues": len(review_report.security_issues),
            "code_smells": len(review_report.code_smells),
        }
        if review_report.verdict == ReviewVerdict.APPROVE:
            self.logger.info("review_approved", **log_extra)
        else:
            self.logger.warning("review_rejected", **log_extra)

        return self._build_report(
            status="success",
            token_usage=response.usage,
            latency_ms=latency,
            review_report=review_report,
        )

    @staticmethod
    def _parse_review(llm_output: str) -> ReviewReport:
        verdict = ReviewVerdict.NEEDS_CLARIFICATION
        upper = llm_output.upper()

        if "APPROVE" in upper and "REJECT" not in upper:
            verdict = ReviewVerdict.APPROVE
        elif "REJECT" in upper:
            verdict = ReviewVerdict.REJECT

        security_issues: list[str] = []
        code_smells: list[str] = []
        test_gaps: list[str] = []

        # Extract categorised issues
        for line in llm_output.splitlines():
            stripped = line.strip()
            if "security" in stripped.lower() or "injection" in stripped.lower():
                security_issues.append(stripped)
            elif "smell" in stripped.lower() or "duplicate" in stripped.lower():
                code_smells.append(stripped)
            elif "test" in stripped.lower() or "assert" in stripped.lower():
                test_gaps.append(stripped)

        return ReviewReport(
            verdict=verdict,
            feedback=llm_output,
            security_issues=security_issues,
            code_smells=code_smells,
            test_gaps=test_gaps,
        )
