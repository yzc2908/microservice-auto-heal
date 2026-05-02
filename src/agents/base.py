"""
Abstract base agent defining the contract for all agents in the pipeline.

Each agent:
1. Receives structured input (error data, source code, review criteria)
2. Calls the LLM with a specialised system prompt
3. Returns a typed output consumed by the next agent in the chain
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from src.llm.client import LLMClient, get_llm_client
from src.utils.logger import get_logger

TInput = TypeVar("TInput")
TOutput = TypeVar("TOutput")


@dataclass
class AgentReport:
    agent: str
    status: str  # success | failed | needs_retry
    token_usage: dict[str, int] = field(default_factory=dict)
    latency_ms: float = 0.0
    data: dict[str, Any] = field(default_factory=dict)


class BaseAgent(ABC, Generic[TInput, TOutput]):
    """Template method pattern for agent execution."""

    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm or get_llm_client()
        self.logger = get_logger(self.agent_name)

    @property
    @abstractmethod
    def agent_name(self) -> str:
        ...

    @abstractmethod
    async def run(self, input_data: TInput) -> AgentReport:
        """Execute the agent's task and return a structured report."""
        ...

    def _build_report(
        self,
        status: str,
        token_usage: dict[str, int] | None = None,
        latency_ms: float = 0.0,
        **data: Any,
    ) -> AgentReport:
        return AgentReport(
            agent=self.agent_name,
            status=status,
            token_usage=token_usage or {},
            latency_ms=latency_ms,
            data=data,
        )
