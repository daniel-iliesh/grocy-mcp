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
    Returns a list of products currently in stock with quantities and expiration dates.
    """
    return await make_request("GET", "stock")

@mcp.tool()
async def get_stock_volatile() -> dict:
    """
    Get products that are expiring soon, already expired, missing (below min stock), or due soon.
    Returns categorized lists of products requiring attention.
    """
    return await make_request("GET", "stock/volatile")

@mcp.tool()
async def get_product_details(product_id: int) -> dict:
    """
    Get detailed information about a specific product.
    
    Args:
        product_id: The ID of the product to retrieve details for.
    """
    return await make_request("GET", f"stock/products/{product_id}")

@mcp.tool()
async def search_products(query: str) -> List[dict]:
    """
    Search for products by name.
    
    Args:
        query: The search string to match against product names.
    """
    products = await make_request("GET", "objects/products")
    # Filter client-side
    return [p for p in products if query.lower() in p.get("name", "").lower()]

@mcp.tool()
async def add_stock(product_id: int, amount: float, best_before_date: str = None, price: float = None) -> List[dict]:
    """
    Add stock for a product (e.g., after shopping).
    
    Args:
        product_id: The ID of the product to add stock for.
        amount: The amount to add.
        best_before_date: Optional expiration date in YYYY-MM-DD format.
        price: Optional price per unit.
    """
    data = {
        "amount": amount,
        "transaction_type": "purchase"
    }
    if best_before_date:
        data["best_before_date"] = best_before_date
    if price:
        data["price"] = price
    
    return await make_request("POST", f"stock/products/{product_id}/add", data=data)

@mcp.tool()
async def consume_stock(product_id: int, amount: float, spoiled: bool = False) -> List[dict]:
    """
    Consume/use a product from stock.
    
    Args:
        product_id: The ID of the product to consume.
        amount: The amount to consume.
        spoiled: Whether the product was spoiled (default False).
    """
    data = {
        "amount": amount,
        "transaction_type": "consume",
        "spoiled": spoiled
    }
    return await make_request("POST", f"stock/products/{product_id}/consume", data=data)

# Additional Stock Helpers

@mcp.tool()
async def transfer_stock(product_id: int, amount: float, location_id_from: int, location_id_to: int, stock_entry_id: str = None) -> List[dict]:
    """
    Transfer stock of a product from one location to another.
    
    Args:
        product_id: The ID of the product to transfer.
        amount: The amount to transfer.
        location_id_from: Source location ID.
        location_id_to: Destination location ID.
        stock_entry_id: Optional specific stock entry ID to transfer (amount must be 1 if used).
    """
    data = {
        "amount": amount,
        "location_id_from": location_id_from,
        "location_id_to": location_id_to,
    }
    if stock_entry_id:
        data["stock_entry_id"] = stock_entry_id
    return await make_request("POST", f"stock/products/{product_id}/transfer", data=data)


@mcp.tool()
async def inventory_product(
    product_id: int,
    new_amount: float,
    best_before_date: str = None,
    location_id: int = None,
    price: float = None,
    note: str = None,
) -> List[dict]:
    """
    Set the absolute stock amount for a product (inventory adjustment).
    
    Args:
        product_id: The ID of the product to inventory.
        new_amount: The new total amount in stock.
        best_before_date: Optional best before date for added stock.
        location_id: Optional location ID for added stock.
        price: Optional price for added stock.
        note: Optional note stored on the stock entry.
    """
    data = {
        "new_amount": new_amount,
    }
    if best_before_date:
        data["best_before_date"] = best_before_date
    if location_id is not None:
        data["location_id"] = location_id
    if price is not None:
        data["price"] = price
    if note:
        data["note"] = note
    return await make_request("POST", f"stock/products/{product_id}/inventory", data=data)


@mcp.tool()
async def open_product(product_id: int, amount: float = 1.0) -> List[dict]:
    """
    Mark one or more units of a product as opened.
    
    Args:
        product_id: The ID of the product to open.
        amount: The amount to mark as opened (default 1.0).
    """
    data = {
        "amount": amount,
    }
    return await make_request("POST", f"stock/products/{product_id}/open", data=data)

# Shopping List Tools

@mcp.tool()
async def get_shopping_list() -> List[dict]:
    """
    Get the current shopping list with all items.
    """
    return await make_request("GET", "objects/shopping_list")

@mcp.tool()
async def add_to_shopping_list(product_id: int, amount: float = 1.0, shopping_list_id: int = 1, note: str = None) -> dict:
    """
    Add a product to the shopping list.
    
    Args:
        product_id: The ID of the product to add.
        amount: The amount to add (default 1.0).
        shopping_list_id: The ID of the shopping list (default 1).
        note: Optional note for the shopping list item.
    """
    data = {
        "product_id": product_id,
        "amount": amount,
        "shopping_list_id": shopping_list_id
    }
    if note:
        data["note"] = note
    
    return await make_request("POST", "objects/shopping_list", data=data)

@mcp.tool()
async def remove_from_shopping_list(item_id: int) -> dict:
    """
    Remove an item from the shopping list.
    
    Args:
        item_id: The ID of the shopping list item to remove.
    """
    return await make_request("DELETE", f"objects/shopping_list/{item_id}")

@mcp.tool()
async def clear_shopping_list(shopping_list_id: int = 1) -> List[dict]:
    """
    Clear all items from a shopping list.
    
    Args:
        shopping_list_id: The ID of the shopping list to clear (default 1).
    """
    return await make_request("POST", f"stock/shoppinglist/{shopping_list_id}/clear")

@mcp.tool()
async def add_missing_products_to_shopping_list() -> dict:
    """
    Automatically add all products that are below their minimum stock level to the shopping list.
    """
    return await make_request("POST", "stock/shoppinglist/add-missing-products")

# Recipe Tools

@mcp.tool()
async def get_recipes() -> List[dict]:
    """
    Get all recipes.
    """
    return await make_request("GET", "objects/recipes")

@mcp.tool()
async def get_recipe(recipe_id: int) -> dict:
    """
    Get details of a specific recipe including ingredients and instructions.
    
    Args:
        recipe_id: The ID of the recipe.
    """
    return await make_request("GET", f"objects/recipes/{recipe_id}")

@mcp.tool()
async def add_recipe_to_shopping_list(recipe_id: int) -> dict:
    """
    Add all missing ingredients from a recipe to the shopping list.
    
    Args:
        recipe_id: The ID of the recipe.
    """
    return await make_request("POST", f"recipes/{recipe_id}/add-not-fulfilled-products-to-shoppinglist")

@mcp.tool()
async def consume_recipe(recipe_id: int) -> dict:
    """
    Consume/use all ingredients for a recipe from stock.
    
    Args:
        recipe_id: The ID of the recipe to consume ingredients for.
    """
    return await make_request("POST", f"recipes/{recipe_id}/consume")

# Barcode-based Stock Tools

@mcp.tool()
async def get_product_by_barcode(barcode: str) -> dict:
    """
    Get product details by barcode.
    
    Args:
        barcode: The product barcode to look up.
    """
    return await make_request("GET", f"stock/products/by-barcode/{barcode}")


@mcp.tool()
async def add_stock_by_barcode(
    barcode: str,
    amount: float,
    best_before_date: str = None,
    price: float = None,
    location_id: int = None,
) -> List[dict]:
    """
    Add stock for a product identified by barcode (e.g., after scanning groceries).
    
    Args:
        barcode: The product barcode.
        amount: The amount to add.
        best_before_date: Optional expiration date in YYYY-MM-DD format.
        price: Optional price per unit.
        location_id: Optional location ID to store the product.
    """
    data = {
        "amount": amount,
        "transaction_type": "purchase",
    }
    if best_before_date:
        data["best_before_date"] = best_before_date
    if price is not None:
        data["price"] = price
    if location_id is not None:
        data["location_id"] = location_id
    return await make_request("POST", f"stock/products/by-barcode/{barcode}/add", data=data)


@mcp.tool()
async def consume_stock_by_barcode(
    barcode: str,
    amount: float,
    spoiled: bool = False,
    location_id: int = None,
) -> List[dict]:
    """
    Consume or spoil stock for a product identified by barcode.
    
    Args:
        barcode: The product barcode.
        amount: The amount to consume.
        spoiled: Whether the product was spoiled (default False).
        location_id: Optional location restriction for the stock to consume.
    """
    data = {
        "amount": amount,
        "transaction_type": "consume",
        "spoiled": spoiled,
    }
    if location_id is not None:
        data["location_id"] = location_id
    return await make_request("POST", f"stock/products/by-barcode/{barcode}/consume", data=data)


@mcp.tool()
async def transfer_stock_by_barcode(
    barcode: str,
    amount: float,
    location_id_from: int,
    location_id_to: int,
    stock_entry_id: str = None,
) -> List[dict]:
    """
    Transfer stock of a barcode-identified product between locations.
    
    Args:
        barcode: The product barcode.
        amount: The amount to transfer.
        location_id_from: Source location ID.
        location_id_to: Destination location ID.
        stock_entry_id: Optional specific stock entry ID to transfer (amount must be 1 if used).
    """
    data = {
        "amount": amount,
        "location_id_from": location_id_from,
        "location_id_to": location_id_to,
    }
    if stock_entry_id:
        data["stock_entry_id"] = stock_entry_id
    return await make_request("POST", f"stock/products/by-barcode/{barcode}/transfer", data=data)


@mcp.tool()
async def inventory_product_by_barcode(
    barcode: str,
    new_amount: float,
    best_before_date: str = None,
    location_id: int = None,
    price: float = None,
) -> List[dict]:
    """
    Inventory a product by barcode by setting the absolute stock amount.
    
    Args:
        barcode: The product barcode.
        new_amount: The new total amount in stock.
        best_before_date: Optional best before date for added stock.
        location_id: Optional location ID for added stock.
        price: Optional price for added stock.
    """
    data = {
        "new_amount": new_amount,
    }
    if best_before_date:
        data["best_before_date"] = best_before_date
    if location_id is not None:
        data["location_id"] = location_id
    if price is not None:
        data["price"] = price
    return await make_request("POST", f"stock/products/by-barcode/{barcode}/inventory", data=data)

# Chore Tools

@mcp.tool()
async def get_chores() -> List[dict]:
    """
    Get all chores.
    """
    return await make_request("GET", "chores")

@mcp.tool()
async def get_chore(chore_id: int) -> dict:
    """
    Get details of a specific chore.
    
    Args:
        chore_id: The ID of the chore.
    """
    return await make_request("GET", f"chores/{chore_id}")

@mcp.tool()
async def track_chore(chore_id: int, tracked_time: str = None, done_by: int = None) -> dict:
    """
    Mark a chore as completed.
    
    Args:
        chore_id: The ID of the chore to mark as done.
        tracked_time: Optional timestamp in ISO format (defaults to now).
        done_by: Optional user ID who completed the chore.
    """
    data = {}
    if tracked_time:
        data["tracked_time"] = tracked_time
    if done_by:
        data["done_by"] = done_by
    
    return await make_request("POST", f"chores/{chore_id}/execute", data=data if data else None)

# Task Tools

@mcp.tool()
async def get_tasks() -> List[dict]:
    """
    Get all tasks.
    """
    return await make_request("GET", "tasks")

@mcp.tool()
async def create_task(name: str, description: str = None, due_date: str = None) -> dict:
    """
    Create a new task.
    
    Args:
        name: The name of the task.
        description: Optional description of the task.
        due_date: Optional due date in YYYY-MM-DD format.
    """
    data = {
        "name": name
    }
    if description:
        data["description"] = description
    if due_date:
        data["due_date"] = due_date
    
    return await make_request("POST", "objects/tasks", data=data)

@mcp.tool()
async def complete_task(task_id: int) -> dict:
    """
    Mark a task as completed.
    
    Args:
        task_id: The ID of the task to complete.
    """
    return await make_request("POST", f"tasks/{task_id}/complete")

@mcp.tool()
async def delete_task(task_id: int) -> dict:
    """
    Delete a task.
    
    Args:
        task_id: The ID of the task to delete.
    """
    return await make_request("DELETE", f"objects/tasks/{task_id}")

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
