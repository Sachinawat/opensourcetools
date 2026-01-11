import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Union

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import Tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from app.config.settings import Settings
from app.tools import news, stock, weather

logger = logging.getLogger(__name__)


def _unwrap_callable(mcp_tool: Callable) -> Callable:
    """
    FastMCP's @tool returns a callable wrapper; expose the underlying function if present.
    """
    return getattr(mcp_tool, "fn", mcp_tool)


def _to_lc_tool(mcp_tool: Callable, name: Optional[str] = None, description: Optional[str] = None) -> Tool:
    fn = _unwrap_callable(mcp_tool)
    return Tool.from_function(
        name=name or getattr(mcp_tool, "name", fn.__name__),
        description=description or getattr(mcp_tool, "description", fn.__doc__),
        func=fn,
    )


def _intent_from_text(text: str) -> str:
    lowered = text.lower()
    if any(keyword in lowered for keyword in ["weather", "temperature", "rain", "forecast", "climate"]):
        return "weather"
    if any(keyword in lowered for keyword in ["news", "headline", "update", "breaking"]):
        return "news"
    if any(keyword in lowered for keyword in ["stock", "price", "nifty", "sensex", "shares", "market"]):
        return "stock"
    return "unknown"


def _intents_from_text(text: str) -> List[str]:
    intents = []
    lowered = text.lower()
    if any(k in lowered for k in ["weather", "temperature", "rain", "forecast", "climate"]):
        intents.append("weather")
    if any(k in lowered for k in ["news", "headline", "update", "breaking"]):
        intents.append("news")
    if any(k in lowered for k in ["stock", "price", "nifty", "sensex", "shares", "market"]):
        intents.append("stock")
    return intents or ["unknown"]


@dataclass
class AgentState:
    messages: List[BaseMessage] = field(default_factory=list)
    intent: str = "unknown"
    intents: List[str] = field(default_factory=list)
    tool_used: Optional[str] = None
    tool_result: Optional[str] = None
    tool_outputs: List[Dict[str, Union[dict, str]]] = field(default_factory=list)
    error: Optional[str] = None


def _build_llm(settings: Settings, temperature: float = 0.2) -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.config.models.openai_chat,
        temperature=temperature,
        api_key=settings.openai_api_key,
    )


def _run_tool_call(
    state: AgentState,
    llm: ChatOpenAI,
    tools: List[Tool],
    tool_label: str,
) -> AgentState:
    messages = list(state.messages)
    bound = llm.bind_tools(tools)

    ai_msg: AIMessage = bound.invoke(messages)
    messages.append(ai_msg)

    def _normalize_result(result: object) -> Union[dict, str]:
        if hasattr(result, "model_dump"):
            try:
                return result.model_dump()
            except Exception:
                return str(result)
        if isinstance(result, dict):
            return result
        return str(result)

    collected: Dict[str, Union[dict, str]] = {}
    if ai_msg.tool_calls:
        for call in ai_msg.tool_calls:
            tool_name = call["name"]
            try:
                tool_obj = next(t for t in tools if t.name == tool_name)
            except StopIteration:
                logger.warning("Tool %s not registered for %s", tool_name, tool_label)
                continue
            try:
                result = tool_obj.invoke(call["args"])
                normalized = _normalize_result(result)
                collected[tool_name] = normalized
                state.tool_outputs.append({"tool": tool_name, "label": tool_label, "result": normalized})
                messages.append(ToolMessage(content=str(normalized), tool_call_id=call["id"]))
            except Exception as exc:
                err_msg = f"{tool_name} failed: {exc}"
                state.error = err_msg
                logger.exception("Tool %s error", tool_name)
                messages.append(ToolMessage(content=err_msg, tool_call_id=call["id"]))
                collected[tool_name] = err_msg
                state.tool_outputs.append({"tool": tool_name, "label": tool_label, "result": err_msg})
    final_msg: AIMessage = llm.invoke(messages)
    messages.append(final_msg)

    state.messages = messages
    state.tool_used = tool_label
    if collected:
        state.tool_result = str(next(iter(collected.values())))
    return state


def _run_fallback(state: AgentState, llm: ChatOpenAI, label: str = "fallback") -> AgentState:
    messages = list(state.messages)
    ai_msg: AIMessage = llm.invoke(messages)
    messages.append(ai_msg)
    state.messages = messages
    state.tool_used = label
    state.tool_result = None
    return state


def build_workflow(settings: Settings):
    llm = _build_llm(settings)

    weather_tools = [_to_lc_tool(weather.fetch_weather, "fetch_weather", "Fetch Indian city weather")]

    def _news_wrapper(topic: str = "india", limit: Optional[int] = None):
        return news.fetch_news(
            topic=topic,
            feed_url=settings.config.defaults.news_feed,
            limit=limit or settings.config.defaults.max_news,
        )

    news_tools = [_to_lc_tool(_news_wrapper, "fetch_news", "Fetch latest India news")]

    def _stock_wrapper(symbol: str, exchange_suffix: Optional[str] = None):
        return stock.fetch_stock(symbol=symbol, exchange_suffix=exchange_suffix or settings.config.defaults.default_stock_suffix)

    stock_tools = [_to_lc_tool(_stock_wrapper, "fetch_stock", "Fetch India stock price")]
    fallback_llm = _build_llm(settings, temperature=0.5)

    graph = StateGraph(AgentState)

    def classify(state: AgentState) -> AgentState:
        last_user = next((m for m in reversed(state.messages) if isinstance(m, HumanMessage)), None)
        if last_user:
            state.intent = _intent_from_text(last_user.content)
            state.intents = _intents_from_text(last_user.content)
        logger.info("Routing intents=%s", state.intents)
        return state

    def multi_agent(state: AgentState) -> AgentState:
        messages_state = state
        for intent in state.intents:
            if intent == "weather":
                messages_state = _run_tool_call(messages_state, llm, weather_tools, "weather")
            elif intent == "news":
                messages_state = _run_tool_call(messages_state, llm, news_tools, "news")
            elif intent == "stock":
                messages_state = _run_tool_call(messages_state, llm, stock_tools, "stock")
            else:
                messages_state = _run_fallback(messages_state, fallback_llm, "general")
        # mark last intent as primary for response context
        if state.intents:
            messages_state.intent = state.intents[-1]
        return messages_state

    graph.add_node("classify", classify)
    graph.add_node("multi_agent", multi_agent)
    graph.set_entry_point("classify")
    graph.add_edge("classify", "multi_agent")
    graph.add_edge("multi_agent", END)

    return graph.compile()
