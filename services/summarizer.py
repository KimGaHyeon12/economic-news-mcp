import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemma-3-4b-it")
REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2

STYLE_PROMPTS = {
    "brief": (
        "Summarize the article in 2 to 3 concise sentences in Korean. "
        "Focus on the main economic takeaway. "
        "Return only the final Korean summary. "
        "Do not include English, translation, romanization, headings, notes, or extra commentary."
    ),
    "executive": (
        "Write a one-line executive briefing in Korean. "
        "Keep it short, direct, and useful for a quick business update. "
        "Return only one final Korean sentence. "
        "Do not provide multiple options, English, translation, romanization, headings, or recommendations."
    ),
    "bullet": (
        "Summarize the article in Korean as exactly 3 bullet points. "
        "Each bullet should contain one clear key point. "
        "Return only the 3 Korean bullet points. "
        "Do not include English, translation, romanization, headings, or extra commentary."
    ),
}


class SummaryError(Exception):
    """Raised when summary generation cannot be completed."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _build_prompt(content: str, style: str) -> str:
    if style not in STYLE_PROMPTS:
        allowed_styles = ", ".join(sorted(STYLE_PROMPTS))
        raise SummaryError(f"Unsupported style '{style}'. Allowed styles: {allowed_styles}.")

    return (
        f"{STYLE_PROMPTS[style]}\n\n"
        "Article:\n"
        f"{content}"
    )


def _extract_text(response_json: dict) -> str:
    candidates = response_json.get("candidates", [])
    for candidate in candidates:
        response_content = candidate.get("content", {})
        for part in response_content.get("parts", []):
            text = part.get("text")
            if text:
                return text.strip()

    raise SummaryError("Gemini returned no summary text.")


def generate_summary(content: str, style: str = "brief") -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise SummaryError("GEMINI_API_KEY is not set.")

    endpoint = GEMINI_API_URL.format(model=DEFAULT_MODEL)
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": _build_prompt(content, style)
                    }
                ]
            }
        ]
    }
    session = requests.Session()
    session.trust_env = False

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
    except requests.Timeout as exc:
        raise SummaryError("Gemini request timed out.", status_code=504) from exc
    except requests.HTTPError as exc:
        detail = exc.response.text if exc.response is not None else str(exc)
        status_code = exc.response.status_code if exc.response is not None else 400
        raise SummaryError(f"Gemini API request failed: {detail}", status_code=status_code) from exc
    except requests.RequestException as exc:
        raise SummaryError(f"Gemini request failed: {exc}", status_code=502) from exc

    return _extract_text(response.json())
