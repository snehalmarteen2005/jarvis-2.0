"""
Agent state definition for LangGraph.

The state flows through every node in the graph. The `messages` field
uses the `add_messages` reducer so that new messages are appended
(not overwritten) at each step.
"""

from __future__ import annotations

from typing import Annotated, Sequence
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """
    The state that flows through the Liebchen agent graph.

    Attributes:
        messages: Conversation history. Uses `add_messages` reducer
                  to automatically append new messages.
        user_id: The active user's database ID. Defaults to 1 for
                 single-user mode.
    """
    messages: Annotated[Sequence[BaseMessage], add_messages]
    user_id: int
