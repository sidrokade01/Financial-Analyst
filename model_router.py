"""
Model router — maps each agent to the appropriate Claude model.
"""


class ModelRouter:
    """Routes sub-agents to appropriate Claude models based on task complexity."""

    MODEL_MAP = {
        "data_sourcing":     "claude-haiku-4-5-20251001",   # Tier 3: extraction
        "financial_modeler": "claude-sonnet-4-6",            # Tier 2: structured + code
        "valuation":         "claude-sonnet-4-6",            # Tier 2: cost-optimised
        "benchmarking":      "claude-sonnet-4-6",            # Tier 2: structured comparison
        "analyst_assembly":  "claude-sonnet-4-6",            # Tier 2: review/assembly
    }

    @classmethod
    def get_model(cls, agent_id: str) -> str:
        return cls.MODEL_MAP.get(agent_id, "claude-sonnet-4-6")

    @classmethod
    def get_cost_estimate(cls, agent_id: str, input_tokens: int, output_tokens: int) -> float:
        """Estimate cost in USD based on model pricing."""
        pricing = {
            "claude-opus-4-6":           {"input": 15.0, "output": 75.0},
            "claude-sonnet-4-6":         {"input": 3.0,  "output": 15.0},
            "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0},
        }
        model = cls.get_model(agent_id)
        p = pricing.get(model, pricing["claude-sonnet-4-6"])
        return (input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000
