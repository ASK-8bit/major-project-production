from pydantic import BaseModel, Field
from typing import Any, Optional, List, Dict, Literal


class PlanStep(BaseModel):
    id: str = Field(..., description="Unique step id, e.g. step_1")
    tool: str = Field(..., description="Name of the tool to call")
    args: Dict[str, Any] = Field(default_factory=dict)


class Plan(BaseModel):
    steps: List[PlanStep]
    needs_final_explanation: bool = True


class ToolResult(BaseModel):
    success: bool
    data: Any = None
    error: Optional[str] = None
    raw: Optional[Any] = None