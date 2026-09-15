# Backend file purpose: LangGraph/orchestrator infrastructure for routing backend agent tasks.
from __future__ import annotations

from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from agents.jd_agent import run_jd_agent
from agents.matching_agent import run_matching_agent
from agents.ranking_agent import run_ranking_agent
from agents.resume_agent import run_resume_agent
from agents.router_agent import route_request
from agents.summary_agent import run_summary_agent
from orchestration.tracing import trace_end, trace_start
from workflows.app_workflow import run_app_workflow
from workflows.recruiter_chat_workflow import run_recruiter_chat_workflow


RouteName = Literal["screening", "chat", "jd", "candidate", "client", "interview", "dashboard", "reports", "unsupported"]


# Class purpose: Defines the HRGraphState data structure or configuration used by the backend.
class HRGraphState(TypedDict, total=False):
    """Shared LangGraph state passed between router, role-agent nodes, and final response node."""
    payload: dict[str, Any]
    username: str
    run_id: str
    task_type: str
    route: RouteName
    route_decision: dict[str, Any]
    app_task: bool
    jd_id: int
    jd_context: dict[str, Any]
    resume_context: dict[str, Any]
    match_context: dict[str, Any]
    ranked_context: dict[str, Any]
    summary: dict[str, Any]
    errors: list[dict[str, Any]]
    path_result: Any
    final_response: dict[str, Any]


# Purpose: Implements the node start backend behavior.
def _node_start(name: str, message: str | None = None) -> None:
    """Emit a standardized trace line when a graph node starts."""
    trace_start("graph-node", name, message)


# Purpose: Implements the node end backend behavior.
def _node_end(name: str, message: str | None = None) -> None:
    """Emit a standardized trace line when a graph node finishes."""
    trace_end("graph-node", name, message)


# Purpose: Implements the router node backend behavior.
def router_node(state: HRGraphState) -> HRGraphState:
    """Run the Router Agent and store the selected route in graph state."""
    name = "Router Node"
    payload = state.get("payload") or {}
    _node_start(name, str(payload.get("task_type") or payload.get("type") or "unknown"))
    decision = route_request(payload)
    _node_end(name, f"route={decision.get('route')}")
    return {"route_decision": decision, "route": decision.get("route") or "unsupported"}


# Purpose: Implements the route after router backend behavior.
def route_after_router(state: HRGraphState) -> RouteName:
    """Map the router decision to the next LangGraph branch name."""
    route = str(state.get("route") or "unsupported").strip().lower()
    if route in {"screening", "chat", "jd", "candidate", "client", "interview", "dashboard", "reports"}:
        return route  # type: ignore[return-value]
    return "unsupported"


# Purpose: Implements the screening entry node backend behavior.
def screening_entry_node(state: HRGraphState) -> HRGraphState:
    """Validate screening input and place the numeric JD id into graph state."""
    name = "Screening Entry Node"
    payload = state.get("payload") or {}
    _node_start(name)
    jd_id = int(payload.get("jd_id") or 0)
    if not jd_id:
        raise ValueError("jd_id is required for screening.")
    _node_end(name, f"jd_id={jd_id}")
    return {"jd_id": jd_id, "app_task": False}


# Purpose: Implements the jd agent node backend behavior.
def jd_agent_node(state: HRGraphState) -> HRGraphState:
    """Load the selected JD context for downstream resume matching."""
    name = "JD Agent Node"
    jd_id = int(state.get("jd_id") or 0)
    _node_start(name, f"jd_id={jd_id}")
    jd_context = run_jd_agent(jd_id)
    _node_end(name, jd_context["jd_row"].get("title") or "JD loaded")
    return {"jd_context": jd_context}


# Purpose: Implements the resume agent node backend behavior.
def resume_agent_node(state: HRGraphState) -> HRGraphState:
    """Build normalized candidate profiles from existing candidate ids and uploaded resumes."""
    name = "Resume Agent Node"
    payload = state.get("payload") or {}
    _node_start(name)
    resume_context = run_resume_agent(payload.get("candidate_ids") or [], payload.get("resume_items") or [])
    _node_end(name, f"profiles={len(resume_context.get('profiles') or [])}")
    return {"resume_context": resume_context}


# Purpose: Implements the matching agent node backend behavior.
def matching_agent_node(state: HRGraphState) -> HRGraphState:
    """Compare each normalized profile against the JD and persist comparison records."""
    name = "Matching Agent Node"
    jd_context = state.get("jd_context") or {}
    resume_context = state.get("resume_context") or {}
    _node_start(name, f"profiles={len(resume_context.get('profiles') or [])}")
    match_context = run_matching_agent(
        int(state.get("jd_id") or 0),
        jd_context["jd_row"],
        jd_context["jd_json"],
        resume_context.get("profiles") or [],
    )
    _node_end(name, f"matches={len(match_context.get('results') or [])}")
    return {"match_context": match_context}


# Purpose: Implements the ranking agent node backend behavior.
def ranking_agent_node(state: HRGraphState) -> HRGraphState:
    """Rank match results and split them into selected and rejected candidate lists."""
    name = "Ranking Agent Node"
    match_context = state.get("match_context") or {}
    results = match_context.get("results") or []
    _node_start(name, f"results={len(results)}")
    ranked_context = run_ranking_agent(results)
    _node_end(name, f"ranked={len(ranked_context.get('ranked_candidates') or [])}")
    return {"ranked_context": ranked_context}


# Purpose: Implements the summary agent node backend behavior.
def summary_agent_node(state: HRGraphState) -> HRGraphState:
    """Create the final screening summary and collect non-fatal processing errors."""
    name = "Summary Agent Node"
    jd_context = state.get("jd_context") or {}
    resume_context = state.get("resume_context") or {}
    match_context = state.get("match_context") or {}
    ranked_context = state.get("ranked_context") or {}
    errors = [*(resume_context.get("errors") or []), *(match_context.get("errors") or [])]
    _node_start(name, f"errors={len(errors)}")
    summary = run_summary_agent(jd_context["jd_row"], ranked_context.get("ranked_candidates") or [], errors)
    path_result = {
        "status": "completed",
        **ranked_context,
        "summary": summary,
        "errors": errors,
    }
    _node_end(name, summary.get("message") or "summary ready")
    return {"summary": summary, "errors": errors, "path_result": path_result}


# Purpose: Implements the recruiter context node backend behavior.
def recruiter_context_node(state: HRGraphState) -> HRGraphState:
    """Validate chat/action payloads before the recruiter chat agent runs."""
    name = "Recruiter Context Node"
    payload = state.get("payload") or {}
    message = str(payload.get("message") or payload.get("msg") or "").strip()
    task = str(payload.get("task_type") or "").strip().lower()
    action = str(payload.get("action") or "").strip()
    _node_start(name, message[:80] or action or task)
    if not message and task != "chat_action":
        raise ValueError("message is required for recruiter chat.")
    _node_end(name, "chat input validated")
    return {"app_task": False}


# Purpose: Implements the recruiter chat agent node backend behavior.
def recruiter_chat_agent_node(state: HRGraphState) -> HRGraphState:
    """Execute recruiter Q&A or confirmed chat actions through the chat workflow."""
    name = "Recruiter Chat Agent Node"
    _node_start(name)
    result = run_recruiter_chat_workflow(state.get("payload") or {})
    _node_end(name, "chat completed")
    return {"path_result": result}


# Purpose: Implements the app role node backend behavior.
def app_role_node(state: HRGraphState) -> HRGraphState:
    """Dispatch non-screening application tasks to the shared app workflow."""
    route = str(state.get("route") or "app").title()
    name = f"{route} Role Agent Node"
    _node_start(name)
    result = run_app_workflow(state.get("payload") or {})
    _node_end(name)
    return {"path_result": result, "app_task": True}


# Purpose: Implements the unsupported node backend behavior.
def unsupported_node(state: HRGraphState) -> HRGraphState:
    """Stop graph execution with a clear validation error for unsupported routes."""
    decision = state.get("route_decision") or {}
    route = decision.get("route") or "unsupported"
    reason = decision.get("reason") or "Unsupported task_type. Use a supported HR task."
    raise ValueError(f"Unsupported route '{route}'. {reason}")


# Purpose: Implements the final response node backend behavior.
def final_response_node(state: HRGraphState) -> HRGraphState:
    """Normalize branch output into the API response shape returned to Flask."""
    name = "Final Response Node"
    _node_start(name)
    result = state["path_result"] if "path_result" in state else {}
    task = state.get("task_type") or "unknown"
    run_id = state.get("run_id") or ""

    if state.get("app_task"):
        final = {
            "run_id": run_id,
            "task_type": task,
            "agentic": True,
            "route_decision": state.get("route_decision") or {},
            "data": result,
            **(result if isinstance(result, dict) else {}),
        }
    else:
        final = {
            "run_id": run_id,
            "task_type": task,
            "agentic": True,
            "route_decision": state.get("route_decision") or {},
            **(result if isinstance(result, dict) else {"data": result}),
        }

    _node_end(name, f"task_type={task}")
    return {"final_response": final}


# Purpose: Builds hr graph used by downstream code.
def build_hr_graph():
    """Construct and compile the LangGraph StateGraph with all nodes and conditional edges."""
    graph = StateGraph(HRGraphState)
    graph.add_node("router", router_node)
    graph.add_node("screening_entry", screening_entry_node)
    graph.add_node("jd_agent", jd_agent_node)
    graph.add_node("resume_agent", resume_agent_node)
    graph.add_node("matching_agent", matching_agent_node)
    graph.add_node("ranking_agent", ranking_agent_node)
    graph.add_node("summary_agent", summary_agent_node)
    graph.add_node("recruiter_context", recruiter_context_node)
    graph.add_node("recruiter_chat_agent", recruiter_chat_agent_node)
    graph.add_node("app_role_agent", app_role_node)
    graph.add_node("unsupported", unsupported_node)
    graph.add_node("final_response", final_response_node)

    graph.add_edge(START, "router")
    graph.add_conditional_edges(
        "router",
        route_after_router,
        {
            "screening": "screening_entry",
            "chat": "recruiter_context",
            "jd": "app_role_agent",
            "candidate": "app_role_agent",
            "client": "app_role_agent",
            "interview": "app_role_agent",
            "dashboard": "app_role_agent",
            "reports": "app_role_agent",
            "unsupported": "unsupported",
        },
    )
    graph.add_edge("screening_entry", "jd_agent")
    graph.add_edge("jd_agent", "resume_agent")
    graph.add_edge("resume_agent", "matching_agent")
    graph.add_edge("matching_agent", "ranking_agent")
    graph.add_edge("ranking_agent", "summary_agent")
    graph.add_edge("summary_agent", "final_response")
    graph.add_edge("recruiter_context", "recruiter_chat_agent")
    graph.add_edge("recruiter_chat_agent", "final_response")
    graph.add_edge("app_role_agent", "final_response")
    graph.add_edge("final_response", END)
    return graph.compile()


_HR_GRAPH = None


# Purpose: Fetches hr graph from storage or service context.
def get_hr_graph():
    """Return the cached compiled graph so each request does not rebuild the graph."""
    global _HR_GRAPH
    if _HR_GRAPH is None:
        _HR_GRAPH = build_hr_graph()
    return _HR_GRAPH


# Purpose: Runs the hr graph workflow or agent step.
def run_hr_graph(payload: dict[str, Any], run_id: str, task_type: str, username: str = "") -> dict[str, Any]:
    """Invoke the compiled LangGraph graph with the initial request state."""
    state: HRGraphState = {
        "payload": payload,
        "username": username,
        "run_id": run_id,
        "task_type": task_type or "unknown",
    }
    result = get_hr_graph().invoke(state)
    return result.get("final_response") or {}
