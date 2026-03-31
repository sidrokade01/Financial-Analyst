"""
IB Pitch Multi-Agent System — Analyst Agent Prototype
======================================================
This is a working prototype of the Analyst Agent and its 4 sub-agents
using LangGraph for orchestration and Anthropic's Claude API.

Architecture:
  Analyst Agent (Sonnet - assembler/reviewer)
    ├── Data Sourcing Sub-Agent (Haiku - extraction)
    ├── Financial Modeler Sub-Agent (Sonnet - code execution)
    ├── Valuation Sub-Agent (Opus - judgment)
    └── Benchmarking Sub-Agent (Sonnet - structured comparison)

Each sub-agent:
  1. Receives the shared deal_context + its specific manifest
  2. Produces structured artifacts (JSON/dict outputs)
  3. Returns to the Analyst Agent for assembly and consistency checks
  4. Human gate approves/rejects before passing upstream

Requirements:
  pip install langgraph anthropic pydantic
"""

import os
import json
from typing import TypedDict, Annotated, Literal, Optional
from pydantic import BaseModel, Field
from anthropic import Anthropic

# ============================================================
# 1. STATE SCHEMA
# ============================================================

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


# ============================================================
# 2. MODEL ROUTER
# ============================================================

class ModelRouter:
    """Routes sub-agents to appropriate Claude models based on task complexity."""
    
    MODEL_MAP = {
        "data_sourcing":    "claude-haiku-4-5-20251001",    # Tier 3: extraction
        "financial_modeler": "claude-sonnet-4-6",            # Tier 2: structured + code
        "valuation":         "claude-opus-4-6",              # Tier 1: judgment
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
            "claude-opus-4-6":              {"input": 15.0, "output": 75.0},  # per 1M tokens
            "claude-sonnet-4-6":            {"input": 3.0,  "output": 15.0},
            "claude-haiku-4-5-20251001":    {"input": 0.80, "output": 4.0},
        }
        model = cls.get_model(agent_id)
        p = pricing.get(model, pricing["claude-sonnet-4-6"])
        return (input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000


# ============================================================
# 3. SUB-AGENT SYSTEM PROMPTS
# ============================================================

SYSTEM_PROMPTS = {
    "data_sourcing": """You are a Data Sourcing sub-agent for an investment banking pitch team.

Your role: Retrieve and structure financial data for the target company.

Given a deal context, produce a structured data package containing:
1. Company overview (business description, key segments, management)
2. Historical financials (3 years: revenue, EBITDA, PAT, total assets, net debt)
3. Segment-level revenue breakdown
4. Key operational metrics (capacity, utilisation, plant load factor for utilities)
5. Recent regulatory developments
6. Macro data relevant to the sector

Output ONLY valid JSON. Every data point must include a "source" field.
If you cannot find specific data, use null and flag it in a "data_gaps" array.
Do not fabricate numbers — accuracy is more important than completeness.""",

    "financial_modeler": """You are a Financial Modeler sub-agent for an investment banking pitch team.

Your role: Build a 3-statement financial model projection for the target company.

Given raw financial data, produce:
1. Revenue projections (5 years, segment-level with growth assumptions)
2. EBITDA projections (with margin assumptions per segment)
3. Capex schedule (maintenance vs growth, linked to capacity plans)
4. Net debt evolution (existing debt maturity + new issuance assumptions)
5. Free cash flow projection
6. Key assumptions table with rationale for each

Output ONLY valid JSON with the following structure:
{
  "projections": { "revenue": [...], "ebitda": [...], "fcf": [...] },
  "assumptions": { "revenue_growth": {...}, "margins": {...}, "capex": {...} },
  "balance_check": { "assets_eq_liabilities": true/false, "notes": "" }
}

Every assumption must have a "rationale" field explaining why that number was chosen.
Flag any assumptions that are particularly uncertain in a "high_uncertainty" array.""",

    "valuation": """You are a Valuation Analyst sub-agent for an investment banking pitch team.
You are the most senior analytical function — your judgment on valuation directly 
determines whether this pitch wins the mandate.

Given a financial model and deal context, produce:
1. DCF valuation
   - WACC calculation (cost of equity via CAPM with India risk premium, cost of debt, 
     target capital structure)
   - Terminal value (exit multiple method AND perpetuity growth — show both)
   - Implied enterprise value range (base, bull, bear)
   - Sensitivity table: WACC vs terminal growth rate
   
2. Sum-of-parts analysis (CRITICAL for conglomerates)
   - Separate valuation for each business segment
   - Segment-appropriate multiples (thermal at utility multiples, renewables at premium)
   - Implied holding company discount/premium
   
3. Trading comparables
   - Peer selection with rationale for each inclusion
   - EV/EBITDA, P/E, EV/Capacity (for utilities) multiples
   - Implied valuation range for target
   
4. Precedent transactions
   - Indian power sector M&A since 2018
   - Relevant global power transactions
   - Implied premiums and multiples

5. Valuation summary (football field)
   - Consolidated range from all methodologies
   - Recommended positioning (where to anchor for this pitch)

Output JSON. Include a "positioning_rationale" field explaining WHY you recommend 
a specific range — this is about winning the mandate, not just being accurate.
Consider: what range makes GS's pitch more compelling than Morgan Stanley's?""",

    "benchmarking": """You are a Benchmarking Analyst sub-agent for an investment banking pitch team.

Your role: Build a comprehensive peer comparison that contextualises the target.

Given financial data and deal context, produce:
1. Peer company list with selection rationale
2. Operational benchmarking table:
   - Installed capacity, capacity utilisation, plant load factor
   - Renewable share of portfolio, capacity addition pipeline
   - Geographic concentration, fuel mix
3. Financial benchmarking table:
   - Revenue, EBITDA margin, EBITDA growth (3Y CAGR)
   - Net debt/EBITDA, interest coverage
   - ROE, ROCE, dividend yield
4. Where target ranks on each metric (quartile position)
5. Key takeaways: what makes the target stand out (positive and negative)

Output JSON. Each metric should include the target value AND the peer median/mean.
Flag any metrics where the target is a significant outlier (>1.5 std dev from peer median).""",

    "analyst_assembly": """You are the Analyst Agent — the senior analytical reviewer who assembles 
and quality-checks all sub-agent outputs before they go to the MD and client.

Your role: Review the outputs from Financial Modeler, Valuation, and Benchmarking 
sub-agents for INTERNAL CONSISTENCY. This is critical — inconsistencies will be 
caught by the MD or worse, by the client.

Check for:
1. MODEL-VALUATION ALIGNMENT
   - Does the DCF use the model's projected cash flows? (not independent estimates)
   - Are discount rate assumptions consistent with the risk profile in the model?
   - Does the SOTP use segment EBITDA from the model?

2. BENCHMARKING-MODEL ALIGNMENT  
   - Are the model's growth assumptions within the range of peer growth rates?
   - If the model assumes premium margins, does benchmarking support this?
   - Are the comp multiples from Valuation consistent with Benchmarking data?

3. INTERNAL CONSISTENCY
   - Do numbers on summary pages match detail pages?
   - Are units consistent (Cr vs Lakhs vs Mn)?
   - Do segment totals reconcile to consolidated figures?

4. ASSUMPTION DEFENSIBILITY
   - Can every material assumption be defended with data from the raw data package?
   - Are there any circular arguments? (e.g., using the DCF output to justify DCF inputs)

Produce a consistency_report with:
- status: "pass" | "pass_with_warnings" | "fail"
- issues: list of specific problems found
- recommendations: what to fix before sending to MD

If status is "fail", specify which sub-agent needs to rework and what exactly needs to change."""
}


# ============================================================
# 4. SUB-AGENT EXECUTION
# ============================================================

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
        max_tokens: int = 8192,
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
        
        # Track costs
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost = ModelRouter.get_cost_estimate(agent_id, input_tokens, output_tokens)
        
        self.cost_log.append({
            "agent_id": agent_id,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost, 4),
        })
        
        print(f"  Tokens: {input_tokens} in / {output_tokens} out")
        print(f"  Cost: ${cost:.4f}")
        
        # Parse JSON from response
        raw_text = response.content[0].text
        try:
            # Try to extract JSON from the response
            if "```json" in raw_text:
                json_str = raw_text.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_text:
                json_str = raw_text.split("```")[1].split("```")[0].strip()
            else:
                json_str = raw_text.strip()
            return json.loads(json_str)
        except (json.JSONDecodeError, IndexError):
            # If JSON parsing fails, return raw text wrapped
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


# ============================================================
# 5. LANGGRAPH STATE GRAPH (ANALYST PIPELINE)
# ============================================================

def build_analyst_graph():
    """
    Build the LangGraph state graph for the Analyst Agent pipeline.
    
    Flow:
      data_sourcing → [financial_modeler, benchmarking] (parallel) → valuation → assembly → human_gate
      
    Note: In production, financial_modeler and benchmarking run in parallel.
    Valuation depends on financial_model output. Assembly reviews everything.
    """
    
    try:
        from langgraph.graph import StateGraph, END
        from langgraph.checkpoint.memory import MemorySaver
    except ImportError:
        print("LangGraph not installed. Install with: pip install langgraph")
        print("Showing the execution flow without LangGraph...")
        return None
    
    runner = SubAgentRunner()
    
    # --- Node functions ---
    
    def data_sourcing_node(state: AnalystState) -> dict:
        """Haiku: Extract and structure raw financial data."""
        ctx = state["deal_context"]
        prompt = f"""Retrieve and structure financial data for:
Company: {ctx['target_name']} ({ctx['target_ticker']})
Sector: {ctx['sector']}
Segments: {', '.join(ctx['segments'])}
Geography: {ctx['geography']}
Listed: {ctx['listed']}

Provide 3 years of historical financials, segment breakdown, 
operational metrics, and recent regulatory developments.
Output as JSON."""
        
        result = runner.run("data_sourcing", prompt)
        return {"raw_data": result}
    
    def financial_modeler_node(state: AnalystState) -> dict:
        """Sonnet: Build 3-statement model projections."""
        ctx = state["deal_context"]
        raw_data = json.dumps(state.get("raw_data", {}), indent=2)
        
        prompt = f"""Build a 5-year financial model for {ctx['target_name']}.

Raw data package:
{raw_data}

Segments to model: {', '.join(ctx['segments'])}

Produce:
1. Segment-level revenue projections with growth assumptions
2. EBITDA projections with margin assumptions
3. Capex schedule (maintenance vs growth)
4. Free cash flow projection
5. Key assumptions with rationale

Output as JSON."""
        
        result = runner.run("financial_modeler", prompt)
        return {"financial_model": result}
    
    def valuation_node(state: AnalystState) -> dict:
        """Opus: Run DCF, SOTP, comps, and precedents."""
        ctx = state["deal_context"]
        model = json.dumps(state.get("financial_model", {}), indent=2)
        raw_data = json.dumps(state.get("raw_data", {}), indent=2)
        
        prompt = f"""Produce a comprehensive valuation for {ctx['target_name']}.

Financial model projections:
{model}

Raw data context:
{raw_data}

The company is a conglomerate with these segments: {', '.join(ctx['segments'])}
This is for a sell-side advisory pitch by Goldman Sachs India.
Competing banks (Morgan Stanley, JPMorgan) are also pitching.

Produce DCF, sum-of-parts, trading comps, precedent transactions, 
and a valuation summary with positioning rationale.
Output as JSON."""
        
        result = runner.run("valuation", prompt, temperature=0.4)
        return {"valuation": result}
    
    def benchmarking_node(state: AnalystState) -> dict:
        """Sonnet: Build peer comparison."""
        ctx = state["deal_context"]
        raw_data = json.dumps(state.get("raw_data", {}), indent=2)
        
        prompt = f"""Build a comprehensive peer benchmarking analysis for {ctx['target_name']}.

Company data:
{raw_data}

Sector: {ctx['sector']} in {ctx['geography']}
Segments: {', '.join(ctx['segments'])}

Compare against relevant listed peers on operational and financial metrics.
Output as JSON."""
        
        result = runner.run("benchmarking", prompt)
        return {"benchmarking": result}
    
    def assembly_node(state: AnalystState) -> dict:
        """Sonnet: Review all outputs for consistency."""
        prompt = f"""Review these sub-agent outputs for internal consistency:

FINANCIAL MODEL:
{json.dumps(state.get('financial_model', {}), indent=2)[:3000]}

VALUATION:
{json.dumps(state.get('valuation', {}), indent=2)[:3000]}

BENCHMARKING:
{json.dumps(state.get('benchmarking', {}), indent=2)[:3000]}

Check for model-valuation alignment, benchmarking-model alignment,
internal consistency, and assumption defensibility.
Output as JSON with status, issues, and recommendations."""
        
        result = runner.run("analyst_assembly", prompt)
        
        status = result.get("status", "pass_with_warnings")
        return {
            "analyst_package": {
                "financial_model": state.get("financial_model"),
                "valuation": state.get("valuation"),
                "benchmarking": state.get("benchmarking"),
            },
            "consistency_report": result,
            "status": "pending_review" if status != "fail" else "rework",
        }
    
    # --- Build graph ---
    
    graph = StateGraph(AnalystState)
    
    graph.add_node("data_sourcing", data_sourcing_node)
    graph.add_node("financial_modeler", financial_modeler_node)
    graph.add_node("benchmarking", benchmarking_node)
    graph.add_node("valuation", valuation_node)
    graph.add_node("assembly", assembly_node)
    
    # Edges: data_sourcing → financial_modeler + benchmarking → valuation → assembly
    graph.set_entry_point("data_sourcing")
    graph.add_edge("data_sourcing", "financial_modeler")
    # In production: add_edge("data_sourcing", "benchmarking") for parallel
    # For sequential prototype:
    graph.add_edge("financial_modeler", "benchmarking")
    graph.add_edge("benchmarking", "valuation")
    graph.add_edge("valuation", "assembly")
    graph.add_edge("assembly", END)
    
    memory = MemorySaver()
    compiled = graph.compile(checkpointer=memory)
    
    return compiled, runner


# ============================================================
# 6. HUMAN GATE (simulated for prototype)
# ============================================================

def human_gate(analyst_package: dict, consistency_report: dict) -> dict:
    """
    Simulate human review gate.
    
    In production, this would:
    1. Surface artifacts to a web UI dashboard
    2. Show consistency_report with pass/fail per check
    3. Allow approve / reject / partial-approve per artifact
    4. Capture structured comments
    5. Return feedback that routes to correct sub-agent for rework
    """
    print(f"\n{'='*60}")
    print("HUMAN GATE: Analyst Review")
    print(f"{'='*60}")
    
    status = consistency_report.get("status", "unknown")
    issues = consistency_report.get("issues", [])
    
    print(f"  Consistency status: {status}")
    if issues:
        print(f"  Issues found: {len(issues)}")
        for issue in issues[:5]:
            if isinstance(issue, str):
                print(f"    - {issue}")
            elif isinstance(issue, dict):
                print(f"    - {issue.get('description', str(issue))}")
    
    # In production: await user input from dashboard
    # For prototype: auto-approve if pass/pass_with_warnings
    if status in ("pass", "pass_with_warnings"):
        decision = "approved"
        print(f"\n  Decision: APPROVED (auto-approve for prototype)")
    else:
        decision = "rework"
        print(f"\n  Decision: REWORK REQUIRED")
    
    return {
        "gate_id": "analyst_review_v1",
        "decision": decision,
        "approved_artifacts": ["financial_model", "valuation", "benchmarking"],
        "rejected_artifacts": [],
        "comments": "Auto-approved in prototype mode",
    }


# ============================================================
# 7. MAIN EXECUTION
# ============================================================

def run_analyst_pipeline():
    """Execute the full Analyst Agent pipeline for Tata Power."""
    
    # Define deal context
    deal_context: DealContext = {
        "target_name": "Tata Power Company Limited",
        "target_ticker": "TATAPOWER.NS",
        "sector": "Power / Utilities",
        "segments": [
            "Thermal Generation",
            "Renewable Energy", 
            "Distribution",
            "EV Charging",
            "Solar Manufacturing",
        ],
        "transaction_type": "sell-side_advisory",
        "listed": True,
        "geography": "India",
    }
    
    analyst_manifest = {
        "priority": "high",
        "deadline": "T+48h",
        "iteration_budget": 3,
        "quality_thresholds": {
            "balance_check": True,
            "source_citation": "every_assumption",
            "segment_reconciliation": True,
        },
    }
    
    # Initial state
    initial_state: AnalystState = {
        "deal_context": deal_context,
        "analyst_manifest": analyst_manifest,
        "raw_data": None,
        "financial_model": None,
        "valuation": None,
        "benchmarking": None,
        "analyst_package": None,
        "consistency_report": None,
        "human_feedback": None,
        "status": "running",
        "errors": [],
    }
    
    print("\n" + "=" * 60)
    print("IB PITCH AGENT SYSTEM — Analyst Pipeline")
    print(f"Target: {deal_context['target_name']}")
    print("=" * 60)
    
    # Try LangGraph execution
    result = build_analyst_graph()
    
    if result is not None:
        compiled_graph, runner = result
        
        # Execute the graph
        config = {"configurable": {"thread_id": "tata-power-pitch-001"}}
        final_state = compiled_graph.invoke(initial_state, config)
        
        # Human gate
        feedback = human_gate(
            final_state.get("analyst_package", {}),
            final_state.get("consistency_report", {}),
        )
        
        # Print cost summary
        runner.print_cost_summary()
        
        return final_state, feedback
    
    else:
        # Fallback: sequential execution without LangGraph
        print("\nRunning sequential fallback (no LangGraph)...")
        runner = SubAgentRunner()
        
        # Step 1: Data Sourcing
        raw_data = runner.run("data_sourcing", f"""
Retrieve and structure financial data for:
Company: {deal_context['target_name']} ({deal_context['target_ticker']})
Sector: {deal_context['sector']}
Segments: {', '.join(deal_context['segments'])}
Geography: {deal_context['geography']}
Output as JSON.""")
        
        # Step 2: Financial Model
        financial_model = runner.run("financial_modeler", f"""
Build a 5-year financial model for {deal_context['target_name']}.
Raw data: {json.dumps(raw_data, indent=2)[:2000]}
Segments: {', '.join(deal_context['segments'])}
Output as JSON.""")
        
        # Step 3: Benchmarking
        benchmarking = runner.run("benchmarking", f"""
Build peer benchmarking for {deal_context['target_name']}.
Company data: {json.dumps(raw_data, indent=2)[:2000]}
Sector: {deal_context['sector']} in {deal_context['geography']}
Output as JSON.""")
        
        # Step 4: Valuation (depends on model)
        valuation = runner.run("valuation", f"""
Produce comprehensive valuation for {deal_context['target_name']}.
Financial model: {json.dumps(financial_model, indent=2)[:2000]}
This is a sell-side pitch by Goldman Sachs India. Competing banks also pitching.
Segments: {', '.join(deal_context['segments'])}
Output as JSON.""", temperature=0.4)
        
        # Step 5: Assembly
        consistency = runner.run("analyst_assembly", f"""
Review these outputs for consistency:
MODEL: {json.dumps(financial_model, indent=2)[:1500]}
VALUATION: {json.dumps(valuation, indent=2)[:1500]}
BENCHMARKING: {json.dumps(benchmarking, indent=2)[:1500]}
Output as JSON.""")
        
        # Human gate
        feedback = human_gate(
            {"financial_model": financial_model, "valuation": valuation, "benchmarking": benchmarking},
            consistency,
        )
        
        runner.print_cost_summary()
        
        return {
            "raw_data": raw_data,
            "financial_model": financial_model,
            "valuation": valuation,
            "benchmarking": benchmarking,
            "consistency_report": consistency,
        }, feedback


if __name__ == "__main__":
    final_state, feedback = run_analyst_pipeline()
    
    print(f"\n{'='*60}")
    print("PIPELINE COMPLETE")
    print(f"{'='*60}")
    print(f"Human gate decision: {feedback['decision']}")
    print(f"\nTo run: export ANTHROPIC_API_KEY=your_key && python analyst_agent.py")
