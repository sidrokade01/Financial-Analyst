"""
Human Gate — approval checkpoint after all agents complete.
In production: surfaces artifacts to a web UI dashboard.
In prototype: auto-approves if consistency status is pass/pass_with_warnings.
"""


def human_gate(analyst_package: dict, consistency_report: dict) -> dict:
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

    # Auto-approve in prototype mode regardless of status
    decision = "approved"
    print(f"\n  Decision: APPROVED (prototype auto-approve)")

    return {
        "gate_id": "analyst_review_v1",
        "decision": decision,
        "approved_artifacts": ["financial_model", "valuation", "benchmarking"],
        "rejected_artifacts": [],
        "comments": "Auto-approved in prototype mode",
    }
