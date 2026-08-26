"""Action Item model: a concrete recommendation derived from one or more Issues (FR-006)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Priority(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# Lower rank sorts first (highest impact first, FR-008).
PRIORITY_RANK: dict[Priority, int] = {
    Priority.CRITICAL: 0,
    Priority.HIGH: 1,
    Priority.MEDIUM: 2,
    Priority.LOW: 3,
}


class ActionItem(BaseModel):
    action_item_id: str = Field(min_length=1)
    related_finding_ids: list[str] = Field(min_length=1)
    recommendation: str = Field(min_length=1)
    priority: Priority
