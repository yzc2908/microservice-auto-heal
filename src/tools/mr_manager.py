"""
Merge Request manager — creates and manages MR/PR submissions via
GitHub and GitLab APIs.
"""

from __future__ import annotations

import httpx
from dataclasses import dataclass

from src.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class MRInfo:
    platform: str
    title: str
    description: str
    source_branch: str
    target_branch: str
    url: str = ""
    mr_id: str = ""


class MRManager:
    """Creates Merge Requests (GitLab) or Pull Requests (GitHub) programmatically."""

    def __init__(self) -> None:
        settings = get_settings()
        self._platform = settings.git_platform
        self._github_token = settings.github_token
        self._gitlab_token = settings.gitlab_token
        self._gitlab_url = settings.gitlab_url.rstrip("/")

    async def create_mr(self, mr: MRInfo, repo_slug: str) -> MRInfo:
        if self._platform == "github":
            return await self._create_github_pr(mr, repo_slug)
        elif self._platform == "gitlab":
            return await self._create_gitlab_mr(mr, repo_slug)
        else:
            raise ValueError(f"Unsupported platform: {self._platform}")

    async def _create_github_pr(self, mr: MRInfo, repo_slug: str) -> MRInfo:
        url = f"https://api.github.com/repos/{repo_slug}/pulls"
        body = {
            "title": mr.title,
            "head": mr.source_branch,
            "base": mr.target_branch,
            "body": mr.description,
        }
        headers = {
            "Authorization": f"Bearer {self._github_token}",
            "Accept": "application/vnd.github+json",
        }
        async with httpx.AsyncClient(headers=headers, timeout=30) as client:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
            data = resp.json()
            mr.url = data["html_url"]
            mr.mr_id = str(data["number"])
        logger.info("github_pr_created", url=mr.url)
        return mr

    async def _create_gitlab_mr(self, mr: MRInfo, repo_slug: str) -> MRInfo:
        encoded = repo_slug.replace("/", "%2F")
        url = f"{self._gitlab_url}/api/v4/projects/{encoded}/merge_requests"
        body = {
            "title": mr.title,
            "source_branch": mr.source_branch,
            "target_branch": mr.target_branch,
            "description": mr.description,
        }
        headers = {"PRIVATE-TOKEN": self._gitlab_token}
        async with httpx.AsyncClient(headers=headers, timeout=30) as client:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
            data = resp.json()
            mr.url = data["web_url"]
            mr.mr_id = str(data["iid"])
        logger.info("gitlab_mr_created", url=mr.url)
        return mr

    async def add_comment(self, mr: MRInfo, repo_slug: str, comment: str) -> None:
        """Add a review comment to an existing MR/PR."""
        if self._platform == "github":
            url = f"https://api.github.com/repos/{repo_slug}/issues/{mr.mr_id}/comments"
            headers = {
                "Authorization": f"Bearer {self._github_token}",
                "Accept": "application/vnd.github+json",
            }
            body = {"body": comment}
        else:
            encoded = repo_slug.replace("/", "%2F")
            url = (
                f"{self._gitlab_url}/api/v4/projects/{encoded}"
                f"/merge_requests/{mr.mr_id}/notes"
            )
            headers = {"PRIVATE-TOKEN": self._gitlab_token}
            body = {"body": comment}

        async with httpx.AsyncClient(headers=headers, timeout=30) as client:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
