# Economic News Summary API

Economic News Summary API is a FastAPI-based MVP project for economic news retrieval and summarization.

It provides:

- a health check endpoint
- a news article listing endpoint
- a single article retrieval endpoint
- a summary endpoint powered by Google Gemini API
- a small agent-style routing endpoint
- a real-time weather endpoint backed by Open-Meteo

The service is packaged to run locally or through Docker.

This repository now includes both:

- an HTTP API built with FastAPI
- an MCP server built with the official Python MCP SDK

## Project Goal

- Build a simple backend API for economic news summarization
- Separate API routing, data loading, and business logic
- Integrate a real LLM with a small service-layer change
- Package the service in a reproducible Docker environment

## Features

- `GET /health` for service health checks
- `GET /articles` for article listing
- `GET /articles/{article_id}` for single article lookup
- `GET /weather/today` for current weather in Incheon
- `POST /summarize` for article summarization
- `POST /agent` for lightweight request routing
- Gemini-powered summary styles:
  - `brief`
  - `executive`
  - `bullet`
- LLM-based intent classification with rule-based fallback
- MCP tools for listing, reading, and summarizing articles
- MCP tool for current weather lookup
- MCP resources for article context loading
- Docker-based execution

## Tech Stack

- Python 3.11
- FastAPI
- Uvicorn
- Pydantic
- Requests
- Python Dotenv
- Google Gemini API
- Docker

## Project Structure

```text
PythonProject3/
|-- api/
|   `-- main.py
|-- data/
|   `-- news_samples.json
|-- mcp_server.py
|-- services/
|   |-- article_store.py
|   |-- intent_classifier.py
|   `-- summarizer.py
|-- .dockerignore
|-- .env.example
|-- .gitignore
|-- Dockerfile
|-- requirements.txt
`-- README.md
```

## Run Locally

1. Create a virtual environment.

```powershell
python -m venv .venv
```

2. Activate the virtual environment.

```powershell
.\.venv\Scripts\Activate.ps1
```

3. Install dependencies.

```powershell
pip install -r requirements.txt
```

4. Create an environment file.

```powershell
Copy-Item .env.example .env
```

5. Set your Gemini API key in `.env`.

```text
GEMINI_API_KEY=your_google_ai_studio_api_key
GEMINI_MODEL=gemma-3-4b-it
```

6. Start the server.

```powershell
uvicorn api.main:app --reload
```

7. Open the service in your browser or API client.

- Swagger UI: `http://localhost:8000/docs`
- Health Check: `http://localhost:8000/health`

## Run MCP Server

1. Install dependencies.

```powershell
pip install -r requirements.txt
```

2. Make sure your `.env` file contains a valid Gemini API key.

3. Run the MCP server over stdio.

```powershell
python mcp_server.py
```

This server exposes MCP tools and resources through the official Python SDK.

## Run With Docker

1. Build the Docker image.

```powershell
docker build -t economic-news-mcp .
```

2. Run the container with your Gemini API key.

```powershell
docker run --rm -p 8000:8000 -e GEMINI_API_KEY=your_google_ai_studio_api_key economic-news-mcp
```

3. Verify the service.

- Swagger UI: `http://localhost:8000/docs`
- Health Check: `http://localhost:8000/health`

### Run MCP In Docker

Run the same image in MCP mode:

```powershell
docker run --rm -e APP_MODE=mcp -e GEMINI_API_KEY=your_google_ai_studio_api_key economic-news-mcp
```

The container will start `mcp_server.py` with `streamable-http` transport on port `8000`.

## API Endpoints

### `GET /health`

Checks whether the server is running.

Example response:

```json
{
  "status": "ok",
  "message": "Server is running"
}
```

### `GET /articles`

Returns the list of stored news articles.

Example response:

```json
{
  "total": 2,
  "data": [
    {
      "id": "001",
      "title": "Bank of Korea holds base rate at 3.5%",
      "category": "Interest Rate",
      "date": "2026-04-09",
      "content": "..."
    }
  ]
}
```

### `GET /articles/{article_id}`

Returns one specific article by ID.

Example response:

```json
{
  "data": {
    "id": "001",
    "title": "Bank of Korea holds base rate at 3.5%",
    "category": "Interest Rate",
    "date": "2026-04-09",
    "content": "..."
  }
}
```

### `POST /summarize`

Generates a Gemini-based summary for a selected article.

Example request:

```json
{
  "article_id": "001",
  "style": "brief"
}
```

### `GET /weather/today`

Returns today's current weather and temperature for Incheon.

Example response:

```json
{
  "message": "오늘 인천 날씨는 맑음이고, 현재 기온은 18.4°C입니다.",
  "data": {
    "location": "인천",
    "temperature_c": 18.4,
    "weather_code": 0,
    "weather_text": "맑음"
  }
}
```

Example response:

```json
{
  "article_id": "001",
  "title": "Bank of Korea holds base rate at 3.5%",
  "style": "brief",
  "summary": "..."
}
```

### `POST /agent`

Routes a natural-language request to article listing, single article lookup, or article summarization.

The current flow is:

```text
user input
-> Gemini intent classifier
-> articles / get_article / summarize / weather
-> rule-based fallback if classification fails
```

Example request for article listing:

```json
{
  "message": "Show me the article list"
}
```

Example request for weather:

```json
{
  "message": "오늘 날씨 알려줘"
}
```

Example request for single article lookup:

```json
{
  "message": "What is article 001?"
}
```

Example request for summarization:

```json
{
  "message": "Summarize article 001",
  "style": "executive"
}
```

Example response:

```json
{
  "action": "get_article",
  "article_id": "001",
  "result": {
    "data": {
      "id": "001",
      "title": "Bank of Korea holds base rate at 3.5%",
      "category": "Interest Rate",
      "date": "2026-04-09",
      "content": "..."
    }
  }
}
```

Example summarize response:

```json
{
  "action": "summarize",
  "article_id": "001",
  "result": {
    "article_id": "001",
    "title": "Bank of Korea holds base rate at 3.5%",
    "style": "executive",
    "summary": "..."
  }
}
```

## Environment Variables

- `GEMINI_API_KEY`: required Google AI Studio API key
- `GEMINI_MODEL`: optional model name, defaults to `gemma-3-4b-it`
- `GEMINI_ROUTER_MODEL`: optional model for intent classification, defaults to `GEMINI_MODEL`

## MCP Capabilities

The MCP server exposes these tools:

- `list_articles`
- `get_article`
- `summarize_article`
- `get_today_weather`

The MCP server exposes these resources:

- `news://articles`
- `news://article/{article_id}`
- `weather://today`

## Current Limitations

- JSON file used instead of a database
- No authentication or authorization
- No automated tests yet
- Agent routing depends on LLM output quality and fallback rules

## Next Steps

- Add stronger validation and error handling
- Add test coverage
- Publish the project to GitHub as a portfolio project

## Why This Project Matters

This project is a practical backend and infrastructure MVP that demonstrates:

- API design with FastAPI
- service-layer separation
- real LLM integration with Gemini
- MCP server implementation with official tools and resources
- Docker-based packaging and execution

In short, it shows that the service can be developed locally and packaged into a runnable containerized API.
