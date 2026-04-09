from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from services.intent_classifier import classify_intent_with_llm
from services.mcp_agent import run_mcp_agent
from services.article_store import ARTICLES, get_article_by_id, list_articles
from services.summarizer import SummaryError, generate_summary
from services.weather import WeatherError, get_today_weather

app = FastAPI(title="Economic News Summary API")


class SummaryRequest(BaseModel):
    article_id: str
    style: str = "brief"


class AgentRequest(BaseModel):
    message: str
    style: str = "brief"


def _get_article_or_404(article_id: str) -> dict:
    article = get_article_by_id(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


@app.get("/health")
def health_check():
    return {"status": "ok", "message": "Server is running"}


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


@app.get("/weather/today")
def today_weather(
    location: str | None = None,
    date: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
):
    try:
        weather = get_today_weather(location=location, target_date=date, start_date=start_date, end_date=end_date)
    except WeatherError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return {
        "message": _format_weather_message(weather),
        "data": weather,
    }


@app.get("/articles")
def get_articles():
    return {"total": len(ARTICLES), "data": list_articles()}


@app.get("/articles/{article_id}")
def get_article(article_id: str):
    article = _get_article_or_404(article_id)
    return {"data": article}


@app.post("/summarize")
def summarize_article(req: SummaryRequest):
    article = _get_article_or_404(req.article_id)

    try:
        summary_result = generate_summary(article["content"], req.style)
    except SummaryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return {
        "article_id": article["id"],
        "title": article["title"],
        "style": req.style,
        "summary": summary_result
    }


@app.post("/agent")
def agent_router(req: AgentRequest):
    intent, article_id = classify_intent_with_llm(req.message)

    if intent == "articles":
        return {
            "action": "articles",
            "result": get_articles()
        }

    if intent == "weather":
        return {
            "action": "weather",
            "result": today_weather()
        }

    if intent == "get_article" and article_id:
        return {
            "action": "get_article",
            "article_id": article_id,
            "result": get_article(article_id)
        }

    if intent == "summarize" and article_id:
        return {
            "action": "summarize",
            "article_id": article_id,
            "result": summarize_article(
                SummaryRequest(article_id=article_id, style=req.style)
            )
        }

    return {
        "action": "unknown",
        "message": (
            "I can list articles, show a specific article, summarize a specific article, or tell you today's weather. "
            "Examples: 'Show me the articles', 'What is article 001?', 'Summarize article 001', or 'What's today's weather?'."
        )
    }


@app.post("/mcp-agent")
def mcp_agent_router(req: AgentRequest):
    try:
        return run_mcp_agent(req.message, req.style)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
