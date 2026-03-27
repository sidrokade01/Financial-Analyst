# IB Pitch Multi-Agent System

## Quick start

```bash
# Install dependencies
pip install -r requirements.txt

# Set your API key
export ANTHROPIC_API_KEY=your_key_here

# Run the Analyst Agent pipeline
python analyst_agent.py
```

## What this does

Runs the **Analyst Agent** sub-pipeline for a Tata Power sell-side advisory pitch:

1. **Data Sourcing** (Haiku) — retrieves and structures company financial data
2. **Financial Modeler** (Sonnet) — builds 5-year 3-statement model projections
3. **Benchmarking** (Sonnet) — constructs peer comparison analysis
4. **Valuation** (Opus) — runs DCF, SOTP, comps, and precedent transactions
5. **Assembly** (Sonnet) — reviews all outputs for internal consistency
6. **Human Gate** — approval checkpoint (auto-approved in prototype)

## Model optimization

| Sub-agent | Model | Why |
|---|---|---|
| Data sourcing | Haiku 4.5 | Pure extraction, no judgment needed |
| Financial modeler | Sonnet 4.6 | Structured model building, code-like |
| Valuation | Opus 4.6 | Highest-judgment task, deal-winning |
| Benchmarking | Sonnet 4.6 | Structured comparison, some judgment |
| Assembly review | Sonnet 4.6 | Consistency checking, not strategy |

## Estimated cost per run

~$3-5 for the Analyst pipeline alone (dominated by the Opus valuation call).
Full system with all agents: ~$12-22 per pitch depending on iteration rounds.

## Next steps to production

See `ib_pitch_multi_agent_spec.md` for the full system specification.
Phase 0-4 implementation roadmap is in the interactive visualization.
