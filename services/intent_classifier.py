import json
import os
import re
import time
from typing import Literal

import requests
from dotenv import load_dotenv

load_dotenv()

CLASSIFIER_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_CLASSIFIER_MODEL = os.getenv("GEMINI_ROUTER_MODEL", os.getenv("GEMINI_MODEL", "gemma-3-4b-it"))
REQUEST_TIMEOUT_SECONDS = 20
MAX_RETRIES = 2
RETRY_DELAY_SECONDS = 1
ALLOWED_INTENTS = {"articles", "get_article", "summarize", "weather", "unknown"}

Intent = Literal["articles", "get_article", "summarize", "weather", "unknown"]


def _extract_json_block(text: str) -> str:
    stripped = text.strip()

    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)

    match = re.search(r"\{.*\}", stripped, re.DOTALL)
    if match:
        return match.group(0)

    return stripped


def normalize_article_id(value: str | int | None) -> str | None:
    if value in ("", None):
        return None

    text = str(value).strip()
    if not text.isdigit():
        return None

    number = int(text)
    if number <= 0 or number > 999:
        return None

    return f"{number:03d}"


def _extract_article_id(message: str) -> str | None:
    contextual_patterns = [
        r"(?<!\d)(\d{1,3})(?!\d)\s*번(?:\s*기사)?",
        r"(?:article|articles|기사)\s*(\d{1,3})(?!\d)",
    ]

    for pattern in contextual_patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            return normalize_article_id(match.group(1))

    match = re.search(r"(?<!\d)(\d{3})(?!\d)", message)
    if match:
        return normalize_article_id(match.group(1))

    return None


def classify_intent_by_rules(message: str) -> tuple[Intent, str | None]:
    cleaned = message.strip()
    article_id = _extract_article_id(cleaned)
    lowered = cleaned.lower()

    summary_keywords = [
        "summary",
        "summarize",
        "\uc694\uc57d",
        "\uc815\ub9ac",
        "\ube0c\ub9ac\ud551",
        "\ud575\uc2ec",
    ]
    list_keywords = [
        "article",
        "articles",
        "list",
        "show",
        "news",
        "recent",
        "\ubaa9\ub85d",
        "\uc804\uccb4",
        "\uae30\uc0ac",
        "\ubcf4\uc5ec",
        "\ub274\uc2a4",
        "\ucd5c\uadfc",
    ]
    weather_keywords = [
        "weather",
        "temperature",
        "forecast",
        "\ub0a0\uc528",
        "\uae30\uc628",
        "\uc628\ub3c4",
    ]
    detail_keywords = [
        "what",
        "detail",
        "about",
        "\ubb50\uc57c",
        "\uc790\uc138\ud788",
        "\ub0b4\uc6a9",
        "\uc124\uba85",
        "\ubcf4\uc5ec\uc918",
    ]

    if article_id:
        if any(keyword in lowered for keyword in summary_keywords):
            return "summarize", article_id

        if any(keyword in lowered for keyword in detail_keywords):
            return "get_article", article_id

        return "get_article", article_id

    if any(keyword in lowered for keyword in weather_keywords):
        return "weather", None

    if any(keyword in lowered for keyword in list_keywords):
        return "articles", None

    return "unknown", None


def _build_classifier_prompt(message: str) -> str:
    return f"""
You are an intent router for an economic news API.
Classify the user request into exactly one of these intents:

- articles: request for the full article list or recent news list
- get_article: request to view one specific article
- summarize: request to summarize one specific article
- weather: request for today's weather or temperature
- unknown: anything else

Rules:
1. If an article number appears, normalize it to a 3-digit article_id like 001, 002, or 101.
2. Natural forms like "1번 기사", "2번", or "article 3" should become 001, 002, and 003.
3. If the user wants a summary, choose summarize.
4. If the user wants to read, inspect, or see one specific article, choose get_article.
5. If the user wants the full list, recent news, or all articles, choose articles.
6. If the user asks about today's weather, temperature, or forecast, choose weather.
7. If unclear, choose unknown.
8. Return only JSON. No markdown, no explanation.

Output schema:
{{
  "intent": "articles|get_article|summarize|weather|unknown",
  "article_id": "001 or null"
}}

User input:
{message}
""".strip()


def classify_intent_with_llm(message: str) -> tuple[Intent, str | None]:
    rule_intent, rule_article_id = classify_intent_by_rules(message)
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return rule_intent, rule_article_id

    session = requests.Session()
    session.trust_env = False
    endpoint = CLASSIFIER_API_URL.format(model=DEFAULT_CLASSIFIER_MODEL)
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": _build_classifier_prompt(message)
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
        parsed = json.loads(_extract_json_block(raw_text))
    except Exception:
        return rule_intent, rule_article_id

    intent = parsed.get("intent", "unknown")
    article_id = parsed.get("article_id")

    if intent not in ALLOWED_INTENTS:
        return rule_intent, rule_article_id

    if article_id in ("null", "", None):
        article_id = None
    else:
        article_id = normalize_article_id(article_id)

    if article_id is None and rule_article_id is not None:
        article_id = rule_article_id

    if rule_intent == "summarize" and intent != "summarize":
        return rule_intent, rule_article_id

    if rule_intent == "articles" and intent == "unknown":
        return rule_intent, rule_article_id

    if rule_intent == "weather" and intent == "unknown":
        return rule_intent, rule_article_id

    return intent, article_id
