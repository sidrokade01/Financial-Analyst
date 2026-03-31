"""
SubAgentRunner — calls the Claude API and tracks costs.
Pulls system prompts directly from each agent's own file.
"""

import os
import json
from dotenv import load_dotenv
from anthropic import Anthropic
from model_router import ModelRouter

# Load .env file
load_dotenv()

# Import system prompt from each agent file
from agents.data_sourcing    import SYSTEM_PROMPT as DATA_SOURCING_PROMPT
from agents.financial_modeler import SYSTEM_PROMPT as FINANCIAL_MODELER_PROMPT
from agents.valuation        import SYSTEM_PROMPT as VALUATION_PROMPT
from agents.benchmarking     import SYSTEM_PROMPT as BENCHMARKING_PROMPT
from agents.assembly         import SYSTEM_PROMPT as ASSEMBLY_PROMPT

SYSTEM_PROMPTS = {
    "data_sourcing":     DATA_SOURCING_PROMPT,
    "financial_modeler": FINANCIAL_MODELER_PROMPT,
    "valuation":         VALUATION_PROMPT,
    "benchmarking":      BENCHMARKING_PROMPT,
    "analyst_assembly":  ASSEMBLY_PROMPT,
}


class SubAgentRunner:
    """Runs a sub-agent with the appropriate model and tracks costs."""

    def __init__(self, api_key: str = None):
        self.client = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
        self.cost_log = []

    def run(
        self,
        agent_id: str,
        user_message: str,
        temperature: float = 0.3,
        max_tokens: int = 8000,
    ) -> dict:
        """Execute a sub-agent and return parsed JSON output."""

        model = ModelRouter.get_model(agent_id)
        system_prompt = SYSTEM_PROMPTS[agent_id]

        print(f"\n{'='*60}")
        print(f"Running: {agent_id} on {model}")
        print(f"{'='*60}")

        response = self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )

        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost = ModelRouter.get_cost_estimate(agent_id, input_tokens, output_tokens)

        self.cost_log.append({
            "agent_id":     agent_id,
            "model":        model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd":     round(cost, 4),
        })

        print(f"  Tokens: {input_tokens} in / {output_tokens} out")
        print(f"  Cost: ${cost:.4f}")

        raw_text = response.content[0].text
        try:
            # Strategy 1: extract ```json ... ``` block
            if "```json" in raw_text:
                json_str = raw_text.split("```json")[1].split("```")[0].strip()
            # Strategy 2: extract ``` ... ``` block
            elif "```" in raw_text:
                json_str = raw_text.split("```")[1].split("```")[0].strip()
            else:
                json_str = raw_text.strip()

            # Strategy 3: find first { ... } if above fails
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                start = raw_text.find("{")
                end   = raw_text.rfind("}") + 1
                if start != -1 and end > start:
                    return json.loads(raw_text[start:end])
                raise

        except (json.JSONDecodeError, IndexError):
            # Last resort: return raw text so no data is lost
            print(f"  ⚠️  JSON parse failed — storing raw output")
            return {"raw_output": raw_text, "parse_error": True}

    def get_total_cost(self) -> float:
        return sum(entry["cost_usd"] for entry in self.cost_log)

    def print_cost_summary(self):
        print(f"\n{'='*60}")
        print("COST SUMMARY")
        print(f"{'='*60}")
        for entry in self.cost_log:
            print(f"  {entry['agent_id']:25s} | {entry['model']:30s} | ${entry['cost_usd']:.4f}")
        print(f"  {'TOTAL':25s} | {'':30s} | ${self.get_total_cost():.4f}")
