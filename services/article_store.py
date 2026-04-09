import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / "data" / "news_samples.json"


def load_articles() -> dict[str, dict]:
    with open(DATA_PATH, "r", encoding="utf-8") as file:
        return {item["id"]: item for item in json.load(file)}


ARTICLES = load_articles()


def list_articles() -> list[dict]:
    return list(ARTICLES.values())


def get_article_by_id(article_id: str) -> dict | None:
    return ARTICLES.get(article_id)
