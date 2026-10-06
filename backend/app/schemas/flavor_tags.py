from __future__ import annotations

from pydantic import BaseModel, Field

from ._base import ORMModel


class FlavorTagInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    parent_id: int | None = None
    active: bool = True
    sort_order: int = 0


class FlavorTagResponse(ORMModel):
    id: int
    name: str
    parent_id: int | None
    active: bool
    sort_order: int
