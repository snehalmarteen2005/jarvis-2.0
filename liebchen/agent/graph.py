"""
LangGraph StateGraph assembly and compilation.

This module wires together:
- The agent state (conversation history + user context)
- The LLM with bound tools
- The ToolNode for automatic tool execution
- SQLite-backed checkpointing for persistent memory

The compiled graph is the core "brain" of the Liebchen agent.
"""

from __future__ import annotations

from langchain_core.messages import SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver

from liebchen.agent.state import AgentState
from liebchen.agent.tools import ALL_TOOLS
from liebchen.llm.ollama_client import get_llm
from liebchen.llm.prompts import get_system_prompt
from liebchen.config import CHECKPOINT_DB_PATH


def _create_agent_node(llm_with_tools):
    """
    Create the agent node function.

    This node invokes the LLM with the current conversation history.
    The system prompt is injected at the start of every invocation
    to maintain consistent behavior.
    """
    async def agent_node(state: AgentState) -> dict:
        messages = list(state["messages"])
        
        # ── OPTIMIZATION: Context Truncation ──
        # Never send the full conversation. Only send the last 6 messages.
        # This drastically reduces prompt size, memory usage, and inference time.
        if len(messages) > 6:
            messages = messages[-6:]

        # Ensure the system prompt is always the first message
        sys_prompt = SystemMessage(content=get_system_prompt())
        full_messages = [sys_prompt] + messages

        response = await llm_with_tools.ainvoke(full_messages)
        return {"messages": [response]}

    return agent_node


def build_graph(
    llm=None,
    checkpointer=None,
) -> tuple:
    """
    Build and compile the Liebchen agent graph.

    Args:
        llm: Optional pre-configured LLM. If None, creates one via get_llm().
        checkpointer: Optional custom checkpointer. If None, uses SqliteSaver.

    Returns:
        A tuple of (compiled_graph, checkpointer) so the caller can manage
        the checkpointer lifecycle.
    """
    # 1. Initialize LLM and bind tools
    if llm is None:
        llm = get_llm()

    llm_with_tools = llm.bind_tools(ALL_TOOLS)

    # 2. Create the checkpointer for persistent memory
    if checkpointer is None:
        conn = sqlite3.connect(CHECKPOINT_DB_PATH, check_same_thread=False)
        checkpointer = SqliteSaver(conn)

    # 3. Build the StateGraph
    builder = StateGraph(AgentState)

    # Add nodes
    builder.add_node("agent", _create_agent_node(llm_with_tools))
    builder.add_node("tools", ToolNode(ALL_TOOLS))

    # Add edges
    builder.add_edge(START, "agent")

    # Conditional: if the agent called a tool → go to "tools" node
    #              if no tool call → go to END
    builder.add_conditional_edges("agent", tools_condition)

    # After tools execute, loop back to the agent for reflection
    builder.add_edge("tools", "agent")

    # 4. Compile with checkpointer
    graph = builder.compile(checkpointer=checkpointer)

    return graph, checkpointer


def create_agent():
    """
    High-level factory that creates the agent with all defaults.

    Returns:
        A tuple of (compiled_graph, checkpointer).

    Usage:
        graph, checkpointer = create_agent()
        result = graph.invoke(
            {"messages": [HumanMessage(content="Hello!")], "user_id": 1},
            config={"configurable": {"thread_id": "session-1"}},
        )
    """
    return build_graph()
