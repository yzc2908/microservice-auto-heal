"""
Git operations manager — clone, checkout, branch, diff generation, and
automated MR submission via GitHub/GitLab APIs.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

import git
from git import Repo

from src.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class GitDiff:
    file_path: str
    patch: str
    added_lines: int
    removed_lines: int


class GitManager:
    """Handles all git operations for the auto-heal pipeline."""

    def __init__(self, repo_path: Path | None = None) -> None:
        self._repo_path = repo_path or get_settings().resolve_workspace()
        self._repo: Repo | None = None

    @property
    def repo(self) -> Repo:
        if self._repo is None:
            try:
                self._repo = Repo(self._repo_path)
            except git.InvalidGitRepositoryError:
                self._repo = Repo.init(self._repo_path)
        return self._repo

    def clone(self, remote_url: str, target_dir: Path) -> Repo:
        """Clone a remote repository for analysis."""
        if target_dir.exists():
            shutil.rmtree(target_dir)
        logger.info("cloning_repo", url=remote_url, target=str(target_dir))
        return Repo.clone_from(remote_url, target_dir)

    def create_branch(self, name: str) -> str:
        """Create and checkout a fix branch. Returns the branch name."""
        branch = self.repo.create_head(name)
        branch.checkout()
        logger.info("branch_created", name=name)
        return name

    def apply_patch(self, patch_content: str, target_file: Path) -> bool:
        """Apply a unified diff patch to a single file."""
        target = self._repo_path / target_file
        if not target.exists():
            logger.error("patch_target_missing", file=str(target))
            return False

        original = target.read_text(encoding="utf-8")
        patched = self._apply_unified_diff(original, patch_content)
        target.write_text(patched, encoding="utf-8")
        logger.info("patch_applied", file=str(target_file))
        return True

    def write_new_file(self, relative_path: Path, content: str) -> Path:
        """Create a new file (e.g., for new unit tests)."""
        target = self._repo_path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        logger.info("file_written", path=str(relative_path))
        return target

    def stage_and_commit(self, message: str, files: list[str] | None = None) -> str:
        """Stage changes & commit. Returns the commit SHA."""
        if files:
            self.repo.index.add(files)
        else:
            self.repo.git.add(all=True)
        commit = self.repo.index.commit(message)
        logger.info("committed", sha=commit.hexsha[:8], message=message)
        return commit.hexsha

    def get_diff(self, base_branch: str = "main") -> list[GitDiff]:
        """Get the diff between the current branch and base_branch."""
        diffs: list[GitDiff] = []
        base = self.repo.refs[base_branch]

        for diff_obj in base.commit.diff(self.repo.head.commit):
            patch = self.repo.git.diff(
                f"{base_branch}...HEAD", "--", diff_obj.a_path
            )
            diffs.append(GitDiff(
                file_path=diff_obj.a_path or "",
                patch=patch,
                added_lines=patch.count("\n+") - patch.count("\n+++"),
                removed_lines=patch.count("\n-") - patch.count("\n---"),
            ))

        return diffs

    def push(self, branch_name: str, force: bool = False) -> None:
        """Push the fix branch to remote."""
        origin = self.repo.remote("origin")
        flags = ["--force"] if force else []
        origin.push(branch_name, *flags)
        logger.info("pushed", branch=branch_name)

    @staticmethod
    def _apply_unified_diff(original: str, patch: str) -> str:
        """Minimal unified diff application for single-file patches."""
        original_lines = original.splitlines(keepends=True)
        result_lines: list[str] = []
        orig_idx = 0

        for line in patch.splitlines(keepends=True):
            if line.startswith("@@ "):
                # Parse hunk header: @@ -orig_start,orig_count +new_start,new_count @@
                parts = line.split()
                orig_info = parts[1].lstrip("-").split(",")
                orig_hunk_start = int(orig_info[0]) - 1  # 0-indexed

                # Emit lines before this hunk
                while orig_idx < orig_hunk_start and orig_idx < len(original_lines):
                    result_lines.append(original_lines[orig_idx])
                    orig_idx += 1

            elif line.startswith(" ") or not line.startswith(("+", "-")):
                if orig_idx < len(original_lines):
                    result_lines.append(original_lines[orig_idx])
                    orig_idx += 1
            elif line.startswith("-"):
                orig_idx += 1  # skip removed line
            elif line.startswith("+"):
                result_lines.append("+" + line[1:])

        # Emit remaining original lines
        while orig_idx < len(original_lines):
            result_lines.append(original_lines[orig_idx])
            orig_idx += 1

        return "".join(result_lines)
