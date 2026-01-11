import logging
from typing import List, Optional

from dataclasses import asdict, is_dataclass
from typing import Any, Mapping, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from app.agents.orchestrator import AgentState, build_workflow
from app.config.settings import configure_logging, get_settings


logger = logging.getLogger(__name__)

settings = get_settings()
configure_logging(settings.config.logging)
workflow = build_workflow(settings)


class QueryRequest(BaseModel):
    query: str


class ToolOutput(BaseModel):
    tool: str
    label: Optional[str] = None
    result: Any


class MessagePayload(BaseModel):
    role: str
    content: str


class QueryResponse(BaseModel):
    intent: str
    tool_used: Optional[str]
    tool_result: Optional[str]
    tool_outputs: List[ToolOutput]
    answer: str
    messages: List[MessagePayload]


def _serialize_message(message: BaseMessage) -> MessagePayload:
    role = "assistant"
    if isinstance(message, HumanMessage):
        role = "user"
    elif isinstance(message, ToolMessage):
        role = "tool"
    elif isinstance(message, AIMessage):
        role = "assistant"
    else:
        role = message.type
    return MessagePayload(role=role, content=str(message.content))


def _as_agent_state(result: Any) -> AgentState:
    """
    LangGraph may return a dataclass or a plain dict; normalize to AgentState.
    """
    if isinstance(result, AgentState):
        return result
    if is_dataclass(result):
        return AgentState(**asdict(result))
    if isinstance(result, Mapping):
        return AgentState(**result)
    raise TypeError(f"Unexpected workflow result type: {type(result)}")


app = FastAPI(title="Multi-Agent Orchestrator", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest) -> QueryResponse:
    try:
        logger.info("Incoming query: %s", req.query)
        state = AgentState(messages=[HumanMessage(content=req.query)])
        raw_result = workflow.invoke(state)
        result = _as_agent_state(raw_result)

        answer_msg = next((m for m in reversed(result.messages) if isinstance(m, AIMessage)), None)
        answer = answer_msg.content if answer_msg else ""

        payload = QueryResponse(
            intent=result.intent,
            tool_used=result.tool_used,
            tool_result=result.tool_result,
            tool_outputs=[ToolOutput(**t) for t in result.tool_outputs],
            answer=str(answer),
            messages=[_serialize_message(m) for m in result.messages],
        )
        logger.info("Response intent=%s tool=%s", result.intent, result.tool_used)
        return payload
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Query processing failed")
        raise HTTPException(status_code=500, detail=str(exc))


# Entry point for `uvicorn app.server.main:app --reload`
__all__ = ["app"]
