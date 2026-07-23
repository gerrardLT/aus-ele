"""Agent data models (Pydantic schemas).

Defines the core data structures for the AI Agent workflow orchestration system:
- AgentContext: execution context (market, region, user preferences)
- ToolDefinition: tool schema for LLM function-calling
- ToolCall / ToolResult: tool invocation and response
- AgentStep: single ReAct step record
- AgentReport: final synthesized report
- WorkflowTemplate: predefined workflow for deterministic fallback
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================


class MarketType(str, Enum):
    NEM = "NEM"
    WEM = "WEM"


class ToolStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


class WorkflowStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# =============================================================================
# Agent Context
# =============================================================================


class AgentContext(BaseModel):
    """Execution context for an agent workflow run."""

    market: MarketType = MarketType.NEM
    region: Optional[str] = None
    year: Optional[int] = None
    params_override: Dict[str, Any] = Field(default_factory=dict)
    max_steps: int = Field(default=15, ge=1, le=30)

    # Derived defaults
    @property
    def effective_region(self) -> str:
        if self.region:
            return self.region
        return "WEM" if self.market == MarketType.WEM else "NSW1"

    @property
    def effective_year(self) -> int:
        if self.year:
            return self.year
        return datetime.now(timezone.utc).year - 1


# =============================================================================
# Tool Definitions (OpenAI function-calling format)
# =============================================================================


class ToolParameter(BaseModel):
    """JSON Schema for a single tool parameter."""

    type: str = "string"
    description: str = ""
    enum: Optional[List[str]] = None
    default: Optional[Any] = None


class ToolDefinition(BaseModel):
    """Tool definition in OpenAI function-calling format."""

    name: str
    description: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    stage: str = ""  # Which funnel stage this tool belongs to

    def to_openai_schema(self) -> Dict[str, Any]:
        """Convert to OpenAI tools array item format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


# =============================================================================
# Tool Call & Result
# =============================================================================


class ToolCall(BaseModel):
    """A tool invocation request from the LLM."""

    id: str = ""
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    """Result of a tool execution."""

    tool_name: str
    call_id: str = ""
    status: ToolStatus = ToolStatus.SUCCESS
    data: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    duration_ms: float = 0.0
    error_message: Optional[str] = None

    def to_llm_message(self) -> Dict[str, Any]:
        """Format as a tool response message for the LLM conversation."""
        content = self.data if self.status == ToolStatus.SUCCESS else {
            "error": self.error_message or "Unknown error",
            "status": self.status.value,
        }
        import json
        return {
            "role": "tool",
            "tool_call_id": self.call_id,
            "content": json.dumps(content, ensure_ascii=False, default=str),
        }


# =============================================================================
# Agent Step (ReAct trace)
# =============================================================================


class AgentStep(BaseModel):
    """Single step in the ReAct execution loop."""

    step_number: int
    thought: str = ""  # LLM reasoning
    action: Optional[ToolCall] = None  # Tool invoked
    observation: Optional[ToolResult] = None  # Tool result
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# =============================================================================
# Stage Result
# =============================================================================


class StageResult(BaseModel):
    """Result from a single analysis stage."""

    stage_name: str
    tool_name: str
    summary: str = ""
    key_metrics: Dict[str, Any] = Field(default_factory=dict)
    status: ToolStatus = ToolStatus.SUCCESS
    duration_ms: float = 0.0


# =============================================================================
# Agent Report (final output)
# =============================================================================


class AgentReport(BaseModel):
    """Final synthesized agent report."""

    id: str = ""
    query: str
    workflow_type: str = "custom"
    region: str = ""
    market: str = "NEM"
    executive_summary: str = ""
    stage_results: List[StageResult] = Field(default_factory=list)
    recommendation: str = ""
    confidence_level: ConfidenceLevel = ConfidenceLevel.MEDIUM
    risk_flags: List[str] = Field(default_factory=list)
    data_quality_notes: List[str] = Field(default_factory=list)
    tool_trace: List[ToolResult] = Field(default_factory=list)
    steps: List[AgentStep] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    status: WorkflowStatus = WorkflowStatus.COMPLETED
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    total_duration_ms: float = 0.0


# =============================================================================
# Workflow Template (deterministic fallback)
# =============================================================================


class WorkflowTemplate(BaseModel):
    """Predefined workflow template for deterministic execution."""

    id: str
    name: str
    description: str = ""
    steps: List[str]  # Tool names in execution order
    parallel_groups: List[List[int]] = Field(default_factory=list)  # Indices that can run in parallel
    default_params: Dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# API Request / Response Models
# =============================================================================


class AgentRunRequest(BaseModel):
    """Request to run an agent workflow."""

    query: str = Field(..., min_length=1, max_length=2000)
    market: MarketType = MarketType.NEM
    region: Optional[str] = None
    year: Optional[int] = None
    workflow_template: Optional[str] = None
    params_override: Dict[str, Any] = Field(default_factory=dict)
    max_steps: int = Field(default=15, ge=1, le=30)


class AgentRunResponse(BaseModel):
    """Response from an agent workflow run."""

    report: AgentReport
    status: WorkflowStatus


class AgentAsyncResponse(BaseModel):
    """Response from an async agent workflow submission."""

    task_id: str
    status: WorkflowStatus = WorkflowStatus.RUNNING
    message: str = "Workflow submitted"


class AgentTaskStatusResponse(BaseModel):
    """Status of an async agent task."""

    task_id: str
    status: WorkflowStatus
    report: Optional[AgentReport] = None
    progress: Optional[str] = None  # Current step description


class AgentToolsResponse(BaseModel):
    """List of available agent tools."""

    tools: List[ToolDefinition]
    total: int


class AgentWorkflowsResponse(BaseModel):
    """List of available workflow templates."""

    workflows: List[WorkflowTemplate]
    total: int


class AgentHistoryResponse(BaseModel):
    """Execution history."""

    executions: List[Dict[str, Any]]
    total: int
