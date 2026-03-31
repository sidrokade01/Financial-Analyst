"""
LangGraph pipeline — wires all agents into a state graph.
"""

from state import AnalystState
from runner import SubAgentRunner
import agents.data_sourcing    as data_sourcing
import agents.financial_modeler as financial_modeler
import agents.benchmarking     as benchmarking
import agents.valuation        as valuation
import agents.assembly         as assembly


def build_analyst_graph(runner: SubAgentRunner):
    """
    Flow:
      data_sourcing → financial_modeler → benchmarking → valuation → assembly
    """
    try:
        from langgraph.graph import StateGraph, END
        from langgraph.checkpoint.memory import MemorySaver
    except ImportError:
        print("LangGraph not installed. Run: pip install langgraph")
        return None

    graph = StateGraph(AnalystState)

    graph.add_node("data_sourcing",     lambda s: data_sourcing.run(s, runner))
    graph.add_node("financial_modeler", lambda s: financial_modeler.run(s, runner))
    graph.add_node("benchmarking",      lambda s: benchmarking.run(s, runner))
    graph.add_node("valuation",         lambda s: valuation.run(s, runner))
    graph.add_node("assembly",          lambda s: assembly.run(s, runner))

    graph.set_entry_point("data_sourcing")
    graph.add_edge("data_sourcing",     "financial_modeler")
    graph.add_edge("financial_modeler", "benchmarking")
    graph.add_edge("benchmarking",      "valuation")
    graph.add_edge("valuation",         "assembly")
    graph.add_edge("assembly",          END)

    memory = MemorySaver()
    return graph.compile(checkpointer=memory)
