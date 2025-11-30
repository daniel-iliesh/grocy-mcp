from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Mount

from settings import settings
from src.server import mcp


if __name__ == "__main__":
    try:
        # Validate settings before starting
        if not settings.grocy_api_key:
            print("Error: GROCY_API_KEY not found. Please set it in a .env file or environment variable.")
            exit(1)

        print("Starting Grocy MCP Server (SSE) with CORS enabled...")

        app = Starlette(routes=[Mount("/", app=mcp.sse_app())])

        app = CORSMiddleware(
            app,
            allow_origins=["*"],
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["*"],
        )

        print("Server running at: http://localhost:8010/sse")

        import uvicorn

        uvicorn.run(app, host="0.0.0.0", port=8010)

    except Exception as e:  # noqa: BLE001
        print(f"Failed to start server: {e}")
