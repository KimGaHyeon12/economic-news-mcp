import json
import os
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import anyio
import requests
from dotenv import load_dotenv
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from services.intent_classifier import classify_intent_by_rules, normalize_article_id

load_dotenv()

PLANNER_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_PLANNER_MODEL = os.getenv("GEMINI_ROUTER_MODEL", os.getenv("GEMINI_MODEL", "gemma-3-4b-it"))
REQUEST_TIMEOUT_SECONDS = 20
MAX_RETRIES = 2
RETRY_DELAY_SECONDS = 1
ALLOWED_TOOLS = {
    "list_articles",
    "get_article",
    "summarize_article",
    "get_today_weather",
}

BASE_DIR = Path(__file__).resolve().parent.parent


def _extract_json_block(text: str) -> str:
    stripped = text.strip()

    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)

    match = re.search(r"\{.*\}", stripped, re.DOTALL)
    if match:
        return match.group(0)

    return stripped


def _build_tool_planning_prompt(message: str, style: str) -> str:
    today = date.today().isoformat()
    return f"""
You are a planner for an MCP server that exposes exactly these 4 tools:

1. list_articles
   - Use for requests asking for the article list or recent news list.
   - arguments: {{}}

2. get_article
   - Use for requests asking to read one specific article.
   - arguments: {{"article_id": "001"}}

3. summarize_article
   - Use for requests asking to summarize one specific article.
   - arguments: {{"article_id": "001", "style": "brief|executive|bullet"}}

4. get_today_weather
   - Use for requests asking for weather, temperature, or forecast.
   - arguments: {{"location": "city name or null", "date": "YYYY-MM-DD or null", "start_date": "YYYY-MM-DD or null", "end_date": "YYYY-MM-DD or null"}}

Rules:
- If the request mentions an article number, normalize it to a 3-digit ID like 001, 002, or 101.
- Natural forms like "1번 기사", "2번", or "article 3" should become 001, 002, and 003.
- If the request asks for summary, key points, or briefing, choose summarize_article.
- If the request asks to show or explain one article, choose get_article.
- If the request asks for the list of articles or recent news, choose list_articles.
- If the request asks for weather, temperature, or forecast, choose get_today_weather.
- If the request mentions a location like Seoul, Busan, Incheon, Tokyo, or New York, include it as "location".
- If no location is given, set "location" to null.
- Today's date is {today}.
- If the request asks about today, set date/start_date/end_date to null.
- If the request asks about one specific day like tomorrow, yesterday, or a named date, convert it to YYYY-MM-DD and set "date".
- If the request asks about a range like this week, next week, or this weekend, set "start_date" and "end_date".
- When you set "date", leave "start_date" and "end_date" null.
- When you set "start_date" and "end_date", leave "date" null.
- For summarize_article, use the provided default style "{style}" unless the user clearly asks for brief, executive, or bullet.
- Return JSON only. No markdown. No explanation.

Output schema:
{{
  "tool_name": "list_articles|get_article|summarize_article|get_today_weather",
  "arguments": {{}}
}}

User request:
{message}
""".strip()


def _fallback_plan(message: str, style: str) -> dict:
    intent, article_id = classify_intent_by_rules(message)
    date_match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", message)
    target_date = date_match.group(1) if date_match else None

    if intent == "articles":
        return {"tool_name": "list_articles", "arguments": {}}
    if intent == "weather":
        return {
            "tool_name": "get_today_weather",
            "arguments": {
                "location": None,
                "date": target_date,
                "start_date": None,
                "end_date": None,
            },
        }
    if intent == "get_article" and article_id:
        return {"tool_name": "get_article", "arguments": {"article_id": article_id}}
    if intent == "summarize" and article_id:
        return {
            "tool_name": "summarize_article",
            "arguments": {"article_id": article_id, "style": style},
        }

    return {"tool_name": "list_articles", "arguments": {}}


def _normalize_relative_weather_date(value: str | None) -> str | None:
    if value is None:
        return None

    lowered = value.strip().lower()
    today = date.today()

    mapping = {
        "today": today,
        "yesterday": today - timedelta(days=1),
        "tomorrow": today + timedelta(days=1),
    }

    if lowered in mapping:
        return mapping[lowered].isoformat()

    return value


def plan_tool_with_gemma(message: str, style: str = "brief") -> dict:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return _fallback_plan(message, style)

    session = requests.Session()
    session.trust_env = False
    endpoint = PLANNER_API_URL.format(model=DEFAULT_PLANNER_MODEL)
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": _build_tool_planning_prompt(message, style)
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0
        }
    }

    try:
        response = None
        for attempt in range(1, MAX_RETRIES + 1):
            response = session.post(
                endpoint,
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": api_key,
                },
                json=payload,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )

            if response.status_code != 503 or attempt == MAX_RETRIES:
                break

            time.sleep(RETRY_DELAY_SECONDS)

        response.raise_for_status()
        data = response.json()
        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
        plan = json.loads(_extract_json_block(raw_text))
    except Exception:
        return _fallback_plan(message, style)

    tool_name = plan.get("tool_name")
    arguments = plan.get("arguments", {})

    if tool_name not in ALLOWED_TOOLS or not isinstance(arguments, dict):
        return _fallback_plan(message, style)

    if tool_name in {"get_article", "summarize_article"}:
        normalized_article_id = normalize_article_id(arguments.get("article_id"))
        if normalized_article_id is None:
            return _fallback_plan(message, style)
        arguments["article_id"] = normalized_article_id

    if tool_name == "summarize_article":
        arguments.setdefault("style", style)
    if tool_name == "get_today_weather":
        arguments.setdefault("location", None)
        arguments["date"] = _normalize_relative_weather_date(arguments.get("date"))
        arguments["start_date"] = _normalize_relative_weather_date(arguments.get("start_date"))
        arguments["end_date"] = _normalize_relative_weather_date(arguments.get("end_date"))
        arguments.setdefault("date", None)
        arguments.setdefault("start_date", None)
        arguments.setdefault("end_date", None)

    return {
        "tool_name": tool_name,
        "arguments": arguments,
    }


async def _call_mcp_tool_async(tool_name: str, arguments: dict) -> dict:
    server = StdioServerParameters(
        command=sys.executable,
        args=[str(BASE_DIR / "mcp_server.py")],
        cwd=BASE_DIR,
    )

    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)

    content = []
    for item in result.content:
        text = getattr(item, "text", None)
        if text is not None:
            try:
                content.append(json.loads(text))
            except json.JSONDecodeError:
                content.append(text)

    if len(content) == 1:
        return content[0]

    return {"content": content}


def call_mcp_tool(tool_name: str, arguments: dict) -> dict:
    return anyio.run(_call_mcp_tool_async, tool_name, arguments)


def run_mcp_agent(message: str, style: str = "brief") -> dict:
    plan = plan_tool_with_gemma(message, style)
    result = call_mcp_tool(plan["tool_name"], plan["arguments"])

    return {
        "planner": "gemma",
        "plan": plan,
        "result": result,
    }
