"""
Contract between AI agent and Tool Executor.

The LLM agent does NOT call business functions directly.
It produces a RecommendationDTO — a formal recommendation that
passes through the Policy Enforcement Point (Tool Executor)
before execution.

Implements Least Privilege principle from blueprint section 4.1.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ToolName(str, Enum):
    """Allow-list of tools the agent may recommend."""
    SEND_NOTIFICATION = "send-notification"
    ARCHIVE_DOCUMENTS = "archive-documents"


class RecommendationDTO(BaseModel):
    """
    Formal recommendation from AI agent.

    The agent does NOT execute — it only recommends.
    The Tool Executor decides whether to execute.
    """

    tool_name: ToolName = Field(
        ...,
        description="Tool name from allow-list",
    )

    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Agent confidence in recommendation (0.0 - 1.0)",
    )

    reasoning: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Justification for audit",
    )

    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Parameters for target worker",
    )

    agent_svid: str = Field(
        ...,
        description="SPIFFE ID of agent (identity for RBAC)",
    )

    @field_validator("agent_svid")
    @classmethod
    def validate_svid_format(cls, v: str) -> str:
        """Validate SPIFFE ID format: spiffe://<trust-domain>/<path>."""
        if not v.startswith("spiffe://"):
            raise ValueError("agent_svid must start with 'spiffe://'")
        if len(v) < 15:
            raise ValueError("agent_svid is too short to be valid")
        return v


# ─── Policy thresholds ────────────────────────────────────────────

CONFIDENCE_THRESHOLD = 0.85
"""Minimum confidence for autonomous execution."""

ALLOWED_SVIDS = {
    "spiffe://company.ru/agents/llm_agent_v1",
}
"""White-list of SVIDs allowed to call Tool Executor."""