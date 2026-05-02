from __future__ import annotations

import structlog
from rich.console import Console
from rich.logging import RichHandler
from rich.theme import Theme

from src.config import get_settings

custom_theme = Theme({
    "agent.diagnostic": "cyan",
    "agent.coding": "green",
    "agent.review": "magenta",
    "pipeline": "yellow",
    "error": "bold red",
    "success": "bold green",
})

_console: Console | None = None


def get_console() -> Console:
    global _console
    if _console is None:
        _console = Console(theme=custom_theme, highlight=True)
    return _console


def setup_logging() -> None:
    settings = get_settings()
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = __name__) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
