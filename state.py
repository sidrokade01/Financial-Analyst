"""
State schema for the Analyst Agent pipeline.
"""

from typing import TypedDict, Optional


class DealContext(TypedDict):
    target_name: str
    target_ticker: str
    sector: str
    segments: list[str]
    transaction_type: str
    listed: bool
    geography: str


class AnalystState(TypedDict):
    """Shared state flowing through the Analyst Agent's sub-graph."""
    deal_context: DealContext
    analyst_manifest: dict

    # Sub-agent outputs (populated as each completes)
    raw_data: Optional[dict]
    financial_model: Optional[dict]
    valuation: Optional[dict]
    benchmarking: Optional[dict]

    # Assembly output
    analyst_package: Optional[dict]
    consistency_report: Optional[dict]

    # Human gate
    human_feedback: Optional[dict]
    status: str  # "running" | "pending_review" | "approved" | "rework"
    errors: list[str]
