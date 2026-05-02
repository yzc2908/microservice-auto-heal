"""
CI/CD Pipeline Integration — connects the orchestrator to external triggers:
- Webhook listener (Sentry, GitHub, GitLab)
- Scheduled polling mode
- One-shot CLI mode for manual invocation
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Callable, Optional

from src.agents.diagnostic_agent import DiagnosticInput
from src.config import get_settings
from src.core.orchestrator import Orchestrator, PipelineResult
from src.tools.log_parser import LogParser
from src.tools.sentry_client import SentryClient, SentryErrorEvent
from src.utils.logger import get_console, get_logger

logger = get_logger(__name__)
console = get_console()


class AutoHealPipeline:
    """Top-level pipeline that connects triggers to the orchestrator."""

    def __init__(self, orchestrator: Orchestrator | None = None) -> None:
        self.orchestrator = orchestrator or Orchestrator()
        self.sentry = SentryClient()
        self.log_parser = LogParser()
        self._running = False
        self._on_complete_callbacks: list[Callable[[PipelineResult], Any]] = []

    def on_complete(self, callback: Callable[[PipelineResult], Any]) -> None:
        """Register a callback invoked after each pipeline run."""
        self._on_complete_callbacks.append(callback)

    async def run_from_sentry(
        self,
        workspace: Path,
        repo_slug: str = "",
        auto_merge: bool = False,
        limit: int = 5,
    ) -> list[PipelineResult]:
        """Fetch recent Sentry errors and run the pipeline on each."""
        console.print("[cyan]📡 Fetching from Sentry...")
        events = await self.sentry.fetch_recent_issues(limit=limit)
        if not events:
            console.print("[yellow]No unresolved Sentry issues found.")
            return []

        console.print(f"[cyan]Found {len(events)} error(s). Starting diagnosis pipeline...")

        inputs = [
            DiagnosticInput(error_event=event, workspace_path=workspace)
            for event in events
        ]

        results = await self.orchestrator.run_batch(
            inputs, repo_slug=repo_slug, auto_merge=auto_merge
        )

        for r in results:
            for cb in self._on_complete_callbacks:
                try:
                    cb(r)
                except Exception:
                    logger.exception("callback_failed")

        await self.sentry.close()
        return results

    async def run_from_ci_log(
        self,
        log_text: str,
        provider: str,
        workspace: Path,
        job_name: str = "",
        repo_slug: str = "",
        auto_merge: bool = False,
    ) -> list[PipelineResult]:
        """Parse a CI log and run the pipeline."""
        console.print("[cyan]📋 Parsing CI log...")

        if provider == "github_actions":
            parsed = self.log_parser.parse_github_actions(log_text, job_name)
        elif provider == "gitlab_ci":
            parsed = self.log_parser.parse_gitlab_ci(log_text, job_name)
        else:
            parsed = self.log_parser.parse_jenkins(log_text, job_name)

        if parsed.errors:
            console.print(f"[red]{len(parsed.errors)} error(s) found in CI log.")
        else:
            console.print("[yellow]No errors detected in CI log.")
            return []

        diag_input = DiagnosticInput(ci_output=parsed, workspace_path=workspace)
        return [
            await self.orchestrator.run_pipeline(
                diag_input, repo_slug=repo_slug, auto_merge=auto_merge,
            )
        ]

    async def run_polling_loop(
        self,
        workspace: Path,
        repo_slug: str = "",
        interval_seconds: int = 300,
    ) -> None:
        """Continuously poll Sentry at a fixed interval (daemon mode)."""
        self._running = True
        console.print(f"[bold]🔄 Polling mode started (interval: {interval_seconds}s)")

        while self._running:
            try:
                await self.run_from_sentry(
                    workspace=workspace,
                    repo_slug=repo_slug,
                    auto_merge=True,
                    limit=3,
                )
            except Exception as exc:
                logger.error("polling_cycle_failed", error=str(exc))

            await asyncio.sleep(interval_seconds)

    def stop_polling(self) -> None:
        self._running = False
