from typing import Any, List
import httpx
from mcp.server.fastmcp import FastMCP
from settings import settings
from starlette.middleware.cors import CORSMiddleware
from starlette.applications import Starlette
from starlette.routing import Mount
import anyio
from ha_session import ha_session

# Initialize FastMCP server
mcp = FastMCP("Grocy", dependencies=["httpx", "websockets"])

# Helper for making API requests
async def make_request(method: str, endpoint: str, params: dict = None, data: dict = None) -> Any:
    url = f"{settings.grocy_api_url.rstrip('/')}/{endpoint.lstrip('/')}"
    
    # Get valid session token
    session_token = await ha_session.ensure_valid_token()
    
    headers = {
        "Cookie": f"ingress_session={session_token}",
        "GROCY-API-KEY": settings.grocy_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.request(method, url, headers=headers, params=params, json=data)
        response.raise_for_status()
        return response.json()

@mcp.tool()
async def get_stock() -> List[dict]:
    """
    Get the current stock overview.
    Returns a list of products currently in stock.
    """
    return await make_request("GET", "stock")

@mcp.tool()
async def get_shopping_list() -> List[dict]:
    """
    Get the current shopping list.
    """
    return await make_request("GET", "objects/shopping_list")

@mcp.tool()
async def add_to_shopping_list(product_id: int, amount: float = 1.0, shopping_list_id: int = 1) -> dict:
    """
    Add a product to the shopping list.
    
    Args:
        product_id: The ID of the product to add.
        amount: The amount to add (default 1.0).
        shopping_list_id: The ID of the shopping list to add to (default 1).
    """
    data = {
        "product_id": product_id,
        "amount": amount,
        "shopping_list_id": shopping_list_id
    }
    return await make_request("POST", "objects/shopping_list", data=data)

@mcp.tool()
async def search_products(query: str) -> List[dict]:
    """
    Search for products by name.
    
    Args:
        query: The search string to match against product names.
    """
    products = await make_request("GET", "objects/products")
    # Filter in python
    return [p for p in products if query.lower() in p.get("name", "").lower()]

if __name__ == "__main__":
    try:
        # Validate settings before starting
        if not settings.grocy_api_key:
            print("Error: GROCY_API_KEY not found. Please set it in a .env file or environment variable.")
            exit(1)
            
        print("Starting Grocy MCP Server (SSE) with CORS enabled...")
        
        # Create Starlette app with CORS
        app = Starlette(
            routes=[
                Mount("/", app=mcp.sse_app())
            ]
        )
        
        # Wrap with CORS middleware
        app = CORSMiddleware(
            app,
            allow_origins=["*"],
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["*"],
        )
        
        print("Server running at: http://localhost:8010/sse")
        
        # Run with uvicorn
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=8010)
        
    except Exception as e:
        print(f"Failed to start server: {e}")
