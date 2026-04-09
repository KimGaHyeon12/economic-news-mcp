import os
import subprocess
import sys


def main() -> None:
    mode = os.getenv("APP_MODE", "api").strip().lower()

    if mode == "api":
        command = [
            "uvicorn",
            "api.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
        ]
    elif mode == "mcp":
        os.environ.setdefault("MCP_TRANSPORT", "streamable-http")
        os.environ.setdefault("MCP_HOST", "0.0.0.0")
        os.environ.setdefault("MCP_PORT", "8000")
        command = [sys.executable, "mcp_server.py"]
    else:
        raise SystemExit("APP_MODE must be either 'api' or 'mcp'.")

    raise SystemExit(subprocess.call(command))


if __name__ == "__main__":
    main()
