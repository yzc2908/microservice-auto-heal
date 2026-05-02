"""
Context window manager — optimises token usage across the multi-agent pipeline
by truncating, summarising, and compressing context for each agent call.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.utils.logger import get_logger

logger = get_logger(__name__)

# Approximate token count: ~4 chars per token for English text
CHARS_PER_TOKEN = 4


@dataclass
class ContextBudget:
    max_tokens: int
    used_tokens: int = 0
    allocations: dict[str, int] = field(default_factory=dict)

    def allocate(self, section: str, tokens: int) -> bool:
        if self.used_tokens + tokens > self.max_tokens:
            return False
        self.allocations[section] = tokens
        self.used_tokens += tokens
        return True

    @property
    def remaining(self) -> int:
        return max(0, self.max_tokens - self.used_tokens)


class ContextManager:
    """Manages context budgets to keep prompts within model limits."""

    def __init__(self, max_tokens: int) -> None:
        self.budget = ContextBudget(max_tokens=max_tokens)

    def truncate_source_file(self, content: str, max_lines: int = 500) -> str:
        """Truncate a source file to fit within context limits."""
        lines = content.splitlines()
        if len(lines) <= max_lines:
            return content

        # Keep first 50 lines (imports, class defs) + last 100 (logic)
        head = "\n".join(lines[:50])
        tail = "\n".join(lines[-100:])
        truncated = f"{head}\n\n# ... {len(lines) - 150} lines truncated ...\n\n{tail}"
        logger.debug("file_truncated", original=len(lines), kept=150)
        return truncated

    def summarise_for_review(self, full_diagnosis: str, max_chars: int = 4000) -> str:
        """Create a condensed version of the diagnosis for the review agent."""
        if len(full_diagnosis) <= max_chars:
            return full_diagnosis

        # Extract key sections
        sections = full_diagnosis.split("##")
        key_sections = [
            s for s in sections
            if any(kw in s.lower() for kw in ("root cause", "call chain", "impact", "confidence"))
        ]
        result = "##".join(key_sections)[:max_chars]
        return result or full_diagnosis[:max_chars]

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Rough token count estimation."""
        return max(1, len(text) // CHARS_PER_TOKEN)
