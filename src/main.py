"""
Entry point for the Microservice Auto-Heal system.

Usage:
    auto-heal sentry --workspace /path/to/repo --auto-merge
    auto-heal ci-log <logfile> --provider github_actions
    auto-heal poll --workspace /path/to/repo --interval 300
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from src.config import get_settings
from src.core.pipeline import AutoHealPipeline
from src.utils.logger import get_console, setup_logging

console = get_console()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="auto-heal",
        description="LLM-powered multi-agent auto-heal pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # Sentry subcommand
    sentry = sub.add_parser("sentry", help="Fetch errors from Sentry and run the pipeline")
    sentry.add_argument("--workspace", "-w", required=True, help="Path to the repository")
    sentry.add_argument("--repo-slug", "-r", default="", help="GitHub/GitLab repo slug (owner/repo)")
    sentry.add_argument("--auto-merge", action="store_true", help="Auto-create MR on approval")
    sentry.add_argument("--limit", type=int, default=5, help="Max issues to process")

    # CI log subcommand
    ci = sub.add_parser("ci-log", help="Parse a CI log file and run the pipeline")
    ci.add_argument("logfile", help="Path to the CI log file")
    ci.add_argument("--workspace", "-w", required=True, help="Path to the repository")
    ci.add_argument("--provider", "-p", default="github_actions",
                    choices=["github_actions", "gitlab_ci", "jenkins"])
    ci.add_argument("--job-name", default="", help="CI job name")
    ci.add_argument("--repo-slug", "-r", default="")
    ci.add_argument("--auto-merge", action="store_true")

    # Poll subcommand
    poll = sub.add_parser("poll", help="Run in polling daemon mode")
    poll.add_argument("--workspace", "-w", required=True, help="Path to the repository")
    poll.add_argument("--repo-slug", "-r", default="")
    poll.add_argument("--interval", type=int, default=300, help="Polling interval in seconds")

    return parser


async def async_main(args: argparse.Namespace) -> int:
    settings = get_settings()
    if not settings.anthropic_api_key:
        console.print(
            "[red]ANTHROPIC_API_KEY not set. "
            "Export it or add it to your .env file."
        )
        return 1

    pipeline = AutoHealPipeline()

    def handle_result(result):
        if result.success:
            console.print(f"[green]✓ Fix applied — MR: {result.mr_url or 'local only'}")
        else:
            console.print(f"[red]✗ Pipeline failed: {'; '.join(result.errors)}")

    pipeline.on_complete(handle_result)

    if args.command == "sentry":
        await pipeline.run_from_sentry(
            workspace=Path(args.workspace),
            repo_slug=args.repo_slug,
            auto_merge=args.auto_merge,
            limit=args.limit,
        )

    elif args.command == "ci-log":
        log_text = Path(args.logfile).read_text(encoding="utf-8")
        await pipeline.run_from_ci_log(
            log_text=log_text,
            provider=args.provider,
            workspace=Path(args.workspace),
            job_name=args.job_name,
            repo_slug=args.repo_slug,
            auto_merge=args.auto_merge,
        )

    elif args.command == "poll":
        await pipeline.run_polling_loop(
            workspace=Path(args.workspace),
            repo_slug=args.repo_slug,
            interval_seconds=args.interval,
        )

    return 0


def main() -> None:
    setup_logging()
    parser = build_parser()
    args = parser.parse_args()
    try:
        exit_code = asyncio.run(async_main(args))
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user.")
        exit_code = 0
    except Exception as exc:
        console.print(f"[red]Fatal error: {exc}")
        exit_code = 1
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
