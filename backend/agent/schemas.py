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

import json
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

    # Harness agent feature flags
    enable_planning: bool = False
    enable_reflection: bool = True
    enable_retry: bool = True
    max_retries: int = Field(default=2, ge=0, le=5)
    session_id: Optional[str] = None

    # PoC: 按阶段工具子集暴露（None=全量动作空间，现有行为不变）
    tool_profile: Optional[str] = None
    # 意图路由开关（§10.4-1）：开启后无显式 profile 时由关键词路由器分类，
    # 无法归类则回落全量；默认关闭
    enable_tool_routing: bool = False
    # C4: Plan-and-Execute 波次并行模式（flag 隔离，默认关闭）；
    # 计划生成失败时自动回落 ReAct
    enable_plan_execute: bool = False

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
    retry_count: int = 0

    def to_llm_message(self, max_chars: int = 3000) -> Dict[str, Any]:
        """Format as a tool response message for the LLM conversation.

        Uses structured summary instead of brute-force truncation:
        - For time series/data tables: extract stats (count, avg, min, max, p90)
        - For nested results: keep top-level keys + summarize arrays/dicts
        - If still too large, truncate JSON payload at boundaries
        
        This prevents context overflow while preserving essential information for LLM reasoning.
        """
        if self.status != ToolStatus.SUCCESS:
            return {
                "role": "tool",
                "tool_call_id": self.call_id,
                # <tool_output> 定界：回灌内容声明为数据非指令（防 prompt injection）
                "content": f"<tool_output tool=\"{self.tool_name}\">" + json.dumps({
                    "error": self.error_message or "Unknown error",
                    "status": self.status.value,
                }, ensure_ascii=False, indent=2) + "</tool_output>",
            }

        content = self.data
        if not isinstance(content, dict):
            # Non-dict results pass through unchanged
            content_str = json.dumps(content, ensure_ascii=False, default=str)
            if len(content_str) > max_chars:
                content_str = content_str[:max_chars] + f"...(truncated {len(content_str)} chars)"
            return {
                "role": "tool",
                "tool_call_id": self.call_id,
                "content": f"<tool_output tool=\"{self.tool_name}\">{content_str}</tool_output>",
            }

        # Structured summary for dict results（_summarize_dict 已返回 JSON 字符串，
        # 直接作为 content，不可再 dumps 一次造成双重序列化/转义）
        summary_str = self._summarize_dict(content, max_chars=max_chars)
        # 完整数据落盘时（artifact），附路径供 read_artifact 按需读取
        artifact_path = self.metadata.get("artifact_path")
        if artifact_path:
            summary_str = (
                summary_str
                + f"\n[完整数据已落盘: {artifact_path}，可用 read_artifact 工具读取]"
            )
        return {
            "role": "tool",
            "tool_call_id": self.call_id,
            "content": f"<tool_output tool=\"{self.tool_name}\">{summary_str}</tool_output>",
        }

    def _summarize_dict(self, data: dict, max_chars: int = 3000) -> str:
        """Extract concise summary from result dict without full JSON serialization.
        
        Strategy:
        1. Always include: status, tool_name, key metric names
        2. For arrays/lists (>5 items): show length + first/last item counts
        3. For numeric fields: extract mean/min/max/p90 if multiple values exist
        4. For nested dicts: recurse with reduced depth
        5. Cap total size at max_chars by dropping verbose array content
        """
        import json

        def summarize_value(v, depth=0, max_depth=2):
            if depth > max_depth:
                if isinstance(v, (list, dict)):
                    return {"__type": type(v).__name__, "truncated": True}
                return v

            if isinstance(v, list):
                if len(v) == 0:
                    return {"length": 0}
                if len(v) > 10:  # Large array → skip all elements
                    sample = [
                        summarize_value(item, depth+1, max_depth) 
                        for item in v[:3]
                    ]
                    return {
                        "length": len(v),
                        "sample": sample,
                        "summary_note": f"Array has {len(v)} items, showing first 3 for brevity",
                    }
                return [summarize_value(item, depth+1, max_depth) for item in v]

            elif isinstance(v, dict):
                if len(v) > 8:  # Deep/nested dict → sample keys
                    summary = {}
                    for k, val in list(v.items())[:8]:
                        summary[k] = summarize_value(val, depth+1, max_depth)
                    if len(v) > 8:
                        summary["__truncated_keys"] = len(v) - 8
                    return summary
                return {k: summarize_value(val, depth+1, max_depth) for k, val in v.items()}

            elif isinstance(v, (int, float)):
                # Numeric values stay as-is
                return round(v, 2) if isinstance(v, float) else v
            else:
                return v

        try:
            summary_obj = summarize_value(data)
            summary_str = json.dumps(summary_obj, ensure_ascii=False)
            
            if len(summary_str) <= max_chars:
                return summary_str

            # If still too large, drop most verbose parts
            summary_obj = {k: v for k, v in summary_obj.items() 
                          if k not in ['data', 'raw_sample', 'rows']}  # Drop largest fields
            summary_str = json.dumps(summary_obj, ensure_ascii=False)
            return summary_str

        except Exception:
            # Fallback: brute-force truncate
            full_str = json.dumps(data, ensure_ascii=False, default=str)
            return full_str[:max_chars] + f"...(truncated {len(full_str)} chars)"


# =============================================================================
# Agent Step (ReAct trace)
# =============================================================================


class AgentStep(BaseModel):
    """Single step in the ReAct execution loop."""

    step_number: int
    thought: str = ""  # LLM reasoning
    action: Optional[ToolCall] = None  # Tool invoked
    observation: Optional[ToolResult] = None  # Tool result
    reflection: Optional[str] = None  # LLM self-evaluation
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
    # PoC：显式工具子集 profile / 意图路由开关（默认均不启用）
    tool_profile: Optional[str] = None
    enable_tool_routing: bool = False
    enable_plan_execute: bool = False


class ChatMessage(BaseModel):
    """A single prior conversation turn sent by the frontend.

    Only the minimal fields needed to reconstruct LLM context are kept; the
    frontend owns the full conversation history (stateless backend).
    """

    role: Literal["user", "assistant"]
    content: str = ""


class AgentChatRequest(BaseModel):
    """Request to run a streaming, multi-turn agent chat."""

    query: str = Field(..., min_length=1, max_length=2000)
    history: List[ChatMessage] = Field(default_factory=list)
    market: MarketType = MarketType.NEM
    session_id: Optional[str] = None
    region: Optional[str] = None
    year: Optional[int] = None
    workflow_template: Optional[str] = None
    params_override: Dict[str, Any] = Field(default_factory=dict)
    max_steps: int = Field(default=15, ge=1, le=30)
    # PoC：显式工具子集 profile / 意图路由开关（默认均不启用）
    tool_profile: Optional[str] = None
    enable_tool_routing: bool = False
    enable_plan_execute: bool = False


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


# =============================================================================
# Harness Agent Models
# =============================================================================


class AnalysisPlan(BaseModel):
    """LLM-generated analysis plan before execution."""

    goal: str = ""
    steps: List[str] = Field(default_factory=list)
    expected_tools: List[str] = Field(default_factory=list)
    reasoning: str = ""


class SessionMemoryEntry(BaseModel):
    """Cached tool result within a conversation session."""

    tool_name: str
    arguments_hash: str
    result_summary: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
