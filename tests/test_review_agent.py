"""Tests for the ReviewAgent."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.coding_agent import CodingReport
from src.agents.diagnostic_agent import DiagnosticReport
from src.agents.review_agent import ReviewAgent, ReviewInput, ReviewVerdict


class TestReviewAgent:
    @pytest.mark.asyncio
    async def test_approve_clean_fix(self):
        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(return_value=MagicMock(
            content="APPROVE. The fix correctly handles the null case with proper validation.",
            usage=MagicMock(input_tokens=800, output_tokens=150),
        ))

        diagnosis = DiagnosticReport(
            root_cause="Null pointer",
            call_chain="handler",
            affected_files=["api.py"],
            confidence="High",
            impact_assessment="Crashes pipeline",
            raw_llm_response="Root cause: null pointer in handle()",
        )
        coding = CodingReport(
            fix_patch="@@ -1 +1,3 @@\n def handle(req):\n+    if req is None: return",
            new_tests="def test_handle_null(): ...",
            explanation="Add null check",
            modified_files=["api.py"],
            new_test_files=["api_test.py"],
        )

        agent = ReviewAgent(llm=mock_llm)
        report = await agent.run(ReviewInput(
            diagnostic_report=diagnosis,
            coding_report=coding,
        ))

        assert report.status == "success"
        review = report.data["review_report"]
        assert review.verdict == ReviewVerdict.APPROVE

    @pytest.mark.asyncio
    async def test_reject_insecure_fix(self):
        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(return_value=MagicMock(
            content="REJECT. The fix uses eval() which introduces a code injection vulnerability.",
            usage=MagicMock(input_tokens=700, output_tokens=100),
        ))

        diagnosis = DiagnosticReport(
            root_cause="Data parsing error",
            call_chain="parse -> eval",
            affected_files=["parser.py"],
            confidence="Medium",
            impact_assessment="Data ingestion fails",
            raw_llm_response="Root cause: unsafe eval in parser",
        )
        coding = CodingReport(
            fix_patch="eval(user_input)",
            new_tests="",
            explanation="Use eval to parse",
            modified_files=["parser.py"],
            new_test_files=[],
        )

        agent = ReviewAgent(llm=mock_llm)
        report = await agent.run(ReviewInput(
            diagnostic_report=diagnosis,
            coding_report=coding,
        ))

        review = report.data["review_report"]
        assert review.verdict == ReviewVerdict.REJECT
