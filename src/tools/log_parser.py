"""
CI/CD log parser — extracts structured error information from GitHub Actions,
GitLab CI, and Jenkins build logs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CILogEntry:
    timestamp: str = ""
    level: str = "INFO"
    message: str = ""
    source_file: str = ""
    line_number: int = 0


@dataclass
class ParsedCIOutput:
    provider: str
    job_name: str
    status: str  # success | failure | cancelled
    errors: list[CILogEntry] = field(default_factory=list)
    warnings: list[CILogEntry] = field(default_factory=list)
    raw_tail: str = ""


class LogParser:
    """Parses CI provider logs into structured error reports."""

    # Common Python traceback patterns
    TRACEBACK_RE = re.compile(
        r'File\s+"([^"]+)",\s+line\s+(\d+),\s+in\s+(\w+)'
    )
    ERROR_RE = re.compile(
        r'(ERROR|CRITICAL|FATAL)\s*[:|-]\s*(.+)', re.IGNORECASE
    )
    WARNING_RE = re.compile(
        r'WARNING\s*[:|-]\s*(.+)', re.IGNORECASE
    )

    def parse_github_actions(self, raw_log: str, job_name: str = "") -> ParsedCIOutput:
        """Parse a GitHub Actions raw log."""
        status = "failure" if "##[error]" in raw_log else "success"
        output = ParsedCIOutput(
            provider="github_actions",
            job_name=job_name,
            status=status,
            raw_tail=raw_log[-3000:],
        )

        for match in self.ERROR_RE.finditer(raw_log):
            output.errors.append(CILogEntry(
                level="ERROR",
                message=match.group(2).strip(),
            ))

        for match in self.TRACEBACK_RE.finditer(raw_log):
            fn, lineno, func_name = match.groups()
            source = fn if fn.startswith("/") else fn
            output.errors.append(CILogEntry(
                level="TRACEBACK",
                source_file=source,
                line_number=int(lineno),
                message=f"in {func_name}",
            ))

        return output

    def parse_gitlab_ci(self, raw_log: str, job_name: str = "") -> ParsedCIOutput:
        """Parse a GitLab CI job log."""
        # GitLab CI uses ANSI codes; strip them
        clean = re.sub(r'\x1b\[[0-9;]*m', '', raw_log)
        status = "failure" if "ERROR:" in clean or "Job failed" in clean else "success"

        output = ParsedCIOutput(
            provider="gitlab_ci",
            job_name=job_name,
            status=status,
            raw_tail=clean[-3000:],
        )

        for match in self.ERROR_RE.finditer(clean):
            output.errors.append(CILogEntry(
                level="ERROR",
                message=match.group(2).strip(),
            ))

        for match in self.TRACEBACK_RE.finditer(clean):
            fn, lineno, func_name = match.groups()
            output.errors.append(CILogEntry(
                level="TRACEBACK",
                source_file=fn,
                line_number=int(lineno),
                message=f"in {func_name}",
            ))

        return output

    def parse_jenkins(self, raw_log: str, job_name: str = "") -> ParsedCIOutput:
        """Parse a Jenkins build log."""
        status = "failure" if "BUILD FAILURE" in raw_log or "ERROR" in raw_log else "success"
        return ParsedCIOutput(
            provider="jenkins",
            job_name=job_name,
            status=status,
            errors=self._extract_errors(raw_log),
            raw_tail=raw_log[-3000:],
        )

    def _extract_errors(self, log: str) -> list[CILogEntry]:
        entries: list[CILogEntry] = []
        for match in self.ERROR_RE.finditer(log):
            entries.append(CILogEntry(
                level="ERROR",
                message=match.group(2).strip(),
            ))
        return entries
