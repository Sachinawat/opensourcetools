"""
Run the LangGraph workflow directly from terminal (no HTTP), printing step-by-step details.
Usage:
    python -m app.client.cli_workflow "I need Bengaluru weather today"
"""
from __future__ import annotations

import argparse
import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agents.orchestrator import AgentState, build_workflow
from app.config.settings import configure_logging, get_settings


def format_message(msg: Any) -> str:
    if isinstance(msg, HumanMessage):
        role = "user"
    elif isinstance(msg, ToolMessage):
        role = f"tool[{msg.tool_call_id}]"
    elif isinstance(msg, AIMessage):
        role = "assistant"
    else:
        role = getattr(msg, "type", "message")
    return f"{role}: {msg.content}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run workflow locally and print steps")
    parser.add_argument("query", help="User query/prompt")
    args = parser.parse_args()

    settings = get_settings()
    configure_logging(settings.config.logging)
    workflow = build_workflow(settings)

    state = AgentState(messages=[HumanMessage(content=args.query)])
    result: AgentState = workflow.invoke(state)

    print("=== Execution Trace ===")
    for msg in result.messages:
        print(format_message(msg))

    print("\n=== Summary ===")
    print("Intent     :", result.intent)
    print("Tool used  :", result.tool_used)
    print("Tool result:", result.tool_result)


if __name__ == "__main__":
    main()
