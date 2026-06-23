from functools import partial

from sqlalchemy.orm import Session

from langgraph.graph import StateGraph, END

from ledger_agent.agent.nodes import (
    ClassificationState, auto_resolve_node, classify_node, escalate_node, gate, lookup_node, vm_gate
)


def build_graph(session: Session, settings):
    """Build the classification graph. Returns uncompiled StateGraph.

    Caller must call .compile(checkpointer=...) before use.
    """
    g = StateGraph(ClassificationState)

    g.add_node("lookup", partial(lookup_node, session=session))
    g.add_node("classify", partial(classify_node, session=session, settings=settings))
    g.add_node("auto_resolve", partial(auto_resolve_node, session=session))
    g.add_node("escalate", partial(escalate_node, session=session))

    g.set_entry_point("lookup")
    g.add_conditional_edges(
        "lookup",
        vm_gate,
        {"auto_resolve": "auto_resolve", "classify": "classify"},
    )
    g.add_conditional_edges(
        "classify",
        gate,
        {"auto_resolve": "auto_resolve", "escalate": "escalate"},
    )
    g.add_edge("auto_resolve", END)
    g.add_edge("escalate", END)

    return g
