from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Anthropic
    anthropic_api_key: str = ""

    # Sentry
    sentry_dsn: str = ""
    sentry_auth_token: str = ""
    sentry_org: str = ""
    sentry_project: str = ""

    # Git platform
    git_platform: str = "github"
    github_token: str = ""
    gitlab_token: str = ""
    gitlab_url: str = "https://gitlab.com"

    # CI/CD
    ci_provider: str = "github_actions"
    ci_api_url: str = "https://api.github.com"

    # LLM
    llm_model: str = "claude-opus-4-7"
    llm_max_context_tokens: int = 200_000
    llm_max_output_tokens: int = 32_000

    # Runtime
    log_level: str = "INFO"
    max_concurrent_agents: int = 3
    workspace_root: str = ""

    def resolve_workspace(self) -> Path:
        if self.workspace_root:
            return Path(self.workspace_root)
        return Path.cwd()


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
