FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api ./api
COPY services ./services
COPY data ./data
COPY mcp_server.py ./mcp_server.py
COPY docker-entrypoint.py ./docker-entrypoint.py

EXPOSE 8000

CMD ["python", "docker-entrypoint.py"]
