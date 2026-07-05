"""Pydantic request/response schemas — the contract the frontend builds against.

The one contract to lock first is the /forecast response shape; it mirrors the
scored predictions.csv rows plus a currency field.
"""
from __future__ import annotations

from pydantic import BaseModel


class ForecastRequest(BaseModel):
    session_id: str
    windows: list[int] | None = None  # default: all of 30/60/90
    budget_overrides: dict[str, float] | None = None  # {channel: total_budget}


class SimulateRequest(BaseModel):
    session_id: str
    scenario: dict[str, float]  # {channel: budget}


class ExplainRequest(BaseModel):
    session_id: str
    window_days: int = 30
    budget_overrides: dict[str, float] | None = None
