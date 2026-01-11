"""
FastMCP server exposing the same tools for external MCP-compatible clients.
"""
import logging

import asyncio

from fastmcp import FastMCP
from fastmcp.tools.tool import FunctionTool

from app.config.settings import configure_logging, get_settings
from app.tools import news, stock, weather

logger = logging.getLogger(__name__)


def create_server() -> FastMCP:
    settings = get_settings()
    configure_logging(settings.config.logging)

    server = FastMCP(
        name="india-multi-agent-tools",
        instructions="Weather, news, and stock tools focused on India.",
        version="1.0.0",
    )

    server.add_tool(FunctionTool.from_function(weather.fetch_weather))
    server.add_tool(
        FunctionTool.from_function(
            lambda topic="india", feed_url=settings.config.defaults.news_feed, limit=settings.config.defaults.max_news: news.fetch_news(
                topic=topic, feed_url=feed_url, limit=limit
            ),
            name="fetch_news",
            description="Fetch latest India news",
        )
    )
    server.add_tool(
        FunctionTool.from_function(
            lambda symbol, exchange_suffix=settings.config.defaults.default_stock_suffix: stock.fetch_stock(
                symbol=symbol, exchange_suffix=exchange_suffix
            ),
            name="fetch_stock",
            description="Fetch India stock price",
        )
    )

    return server


def run_stdio():
    """
    Launch the MCP server over stdio (for local dev or MCP-capable clients).
    """
    server = create_server()
    logger.info("Starting FastMCP stdio server...")
    asyncio.run(server.run_stdio_async())


def run_http(host: str = "0.0.0.0", port: int = 8001):
    server = create_server()
    logger.info("Starting FastMCP HTTP server on %s:%s", host, port)
    asyncio.run(server.run_http_async(host=host, port=port))


__all__ = ["create_server", "run_stdio", "run_http"]
