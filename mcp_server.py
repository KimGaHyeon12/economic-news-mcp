import json
import os

from mcp.server.fastmcp import FastMCP

from services.article_store import ARTICLES, get_article_by_id, list_articles as list_articles_data
from services.summarizer import SummaryError, generate_summary
from services.weather import WeatherError, get_today_weather as get_today_weather_data

mcp = FastMCP(
    "Economic News MCP Server",
    instructions=(
        "Use the provided tools to list economic news articles, inspect a specific article, "
        "and summarize an article with Gemma 3."
    ),
    host=os.getenv("MCP_HOST", "127.0.0.1"),
    port=int(os.getenv("MCP_PORT", "8000")),
    json_response=True,
)


def _require_article(article_id: str) -> dict:
    article = get_article_by_id(article_id)
    if not article:
        raise ValueError(f"Article '{article_id}' not found.")
    return article


def _format_weather_message(weather: dict) -> str:
    if weather.get("is_current"):
        return (
            f"\uc624\ub298 {weather['location']} \ub0a0\uc528\ub294 {weather['weather_text']}\uc774\uace0, "
            f"\ud604\uc7ac \uae30\uc628\uc740 {weather['temperature_c']}\u00b0C\uc785\ub2c8\ub2e4."
        )

    if weather.get("entries"):
        return (
            f"{weather['start_date']} \ubd80\ud130 {weather['end_date']}\uae4c\uc9c0 "
            f"{weather['location']} \ub0a0\uc528 \uc608\ubcf4\ub97c \ubc18\ud658\ud588\uc2b5\ub2c8\ub2e4."
        )

    return (
        f"{weather['date']} {weather['location']} \ub0a0\uc528\ub294 {weather['weather_text']}\uc774\uace0, "
        f"\ucd5c\uc800 \uae30\uc628\uc740 {weather['temperature_min_c']}\u00b0C, "
        f"\ucd5c\uace0 \uae30\uc628\uc740 {weather['temperature_max_c']}\u00b0C\uc785\ub2c8\ub2e4."
    )


@mcp.tool()
def list_articles() -> dict:
    """Return the full list of available economic news articles."""
    return {"total": len(ARTICLES), "data": list_articles_data()}


@mcp.tool()
def get_article(article_id: str) -> dict:
    """Return a specific article by its 3-digit article ID."""
    article = _require_article(article_id)
    return {"data": article}


@mcp.tool()
def summarize_article(article_id: str, style: str = "brief") -> dict:
    """Summarize one article in Korean using styles: brief, executive, or bullet."""
    article = _require_article(article_id)

    try:
        summary = generate_summary(article["content"], style)
    except SummaryError as exc:
        raise ValueError(str(exc)) from exc

    return {
        "article_id": article["id"],
        "title": article["title"],
        "style": style,
        "summary": summary,
    }


@mcp.tool()
def get_today_weather(
    location: str | None = None,
    date: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """Return current weather, a single-day forecast, or a date-range forecast for a given location."""
    try:
        weather = get_today_weather_data(
            location=location,
            target_date=date,
            start_date=start_date,
            end_date=end_date,
        )
    except WeatherError as exc:
        raise ValueError(str(exc)) from exc

    return {
        "message": _format_weather_message(weather),
        "data": weather,
    }


@mcp.resource("news://articles")
def articles_resource() -> str:
    """Expose the full article list as an MCP resource."""
    return json.dumps({"total": len(ARTICLES), "data": list_articles_data()}, ensure_ascii=False, indent=2)


@mcp.resource("news://article/{article_id}")
def article_resource(article_id: str) -> str:
    """Expose a single article as an MCP resource."""
    article = _require_article(article_id)
    return json.dumps({"data": article}, ensure_ascii=False, indent=2)


@mcp.resource("weather://today")
def weather_resource() -> str:
    """Expose today's current weather for Incheon as an MCP resource."""
    weather = get_today_weather_data()
    return json.dumps(
        {
            "message": _format_weather_message(weather),
            "data": weather,
        },
        ensure_ascii=False,
        indent=2,
    )


def main() -> None:
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
