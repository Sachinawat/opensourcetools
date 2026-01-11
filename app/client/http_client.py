"""
Lightweight client helper to call the FastAPI orchestrator.
"""
from __future__ import annotations

import argparse
import os
from typing import Any, Dict

import requests


DEFAULT_BASE_URL = os.getenv("ORCHESTRATOR_URL", "http://localhost:8000")


def query_api(query: str, base_url: str = DEFAULT_BASE_URL) -> Dict[str, Any]:
    url = f"{base_url.rstrip('/')}/query"
    resp = requests.post(url, json={"query": query}, timeout=15)
    resp.raise_for_status()
    return resp.json()


def main():
    parser = argparse.ArgumentParser(description="Call the orchestrator HTTP API")
    parser.add_argument("query", help="User question/prompt")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="Orchestrator base URL (default: %(default)s)",
    )
    args = parser.parse_args()

    data = query_api(args.query, args.base_url)
    print("Intent:", data.get("intent"))
    print("Tool used:", data.get("tool_used"))
    print("Answer:", data.get("answer"))
    print("Tool result:", data.get("tool_result"))


if __name__ == "__main__":
    main()
