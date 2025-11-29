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
        try:
            response = await client.request(method, url, headers=headers, params=params, json=data)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Log detailed information for easier debugging of Grocy API errors
            resp = exc.response
            body = None
            try:
                body = resp.text
            except Exception:
                body = "<unable to read response body>"
            print(
                "Grocy API error:",
                {
                    "method": method,
                    "url": url,
                    "status_code": resp.status_code,
                    "response_body": body,
                },
            )
            raise
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
async def delete_recipe(recipe_id: int) -> None:
    """
    Delete a recipe by id.

    Args:
        recipe_id: ID of the recipe to delete.
    """
    return await make_request("DELETE", f"objects/recipes/{recipe_id}")

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


@mcp.tool()
async def get_recipe_fulfillment(recipe_id: int) -> dict:
    """
    Get stock fulfillment information for a specific recipe.

    Args:
        recipe_id: The ID of the recipe.
    """
    return await make_request("GET", f"recipes/{recipe_id}/fulfillment")


@mcp.tool()
async def get_all_recipes_fulfillment() -> List[dict]:
    """
    Get stock fulfillment information for all recipes.
    """
    return await make_request("GET", "recipes/fulfillment")

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


@mcp.tool()
async def external_barcode_lookup(barcode: str, add: bool = False) -> dict:
    """
    Perform an external barcode lookup via Grocy's configured plugin.

    Args:
        barcode: The barcode to look up.
        add: If true and the plugin supports it, automatically add the product to Grocy.
    """
    params = {"add": "true" if add else "false"}
    return await make_request("GET", f"stock/barcodes/external-lookup/{barcode}", params=params)

@mcp.tool()
async def create_simple_product(
    name: str,
    qu_id_stock: int,
    qu_id_purchase: int = None,
    location_id: int = None,
    description: str = None,
) -> dict:
    """
    Create a new product in Grocy with a simple set of fields.

    This is a convenience wrapper around POST /objects/products.

    Args:
        name: Product name.
        qu_id_stock: Quantity unit ID used for stock (required by Grocy).
        qu_id_purchase: Quantity unit ID used for purchasing (defaults to qu_id_stock).
        location_id: Optional default location ID where the product is stored.
        description: Optional description.
    """
    if qu_id_purchase is None:
        qu_id_purchase = qu_id_stock
    data = {
        "name": name,
        "qu_id_stock": qu_id_stock,
        "qu_id_purchase": qu_id_purchase,
    }
    if location_id is not None:
        data["location_id"] = location_id
    if description:
        data["description"] = description
    return await make_request("POST", "objects/products", data=data)


@mcp.tool()
async def update_product(
    product_id: int,
    name: str = None,
    description: str = None,
    location_id: int = None,
    qu_id_stock: int = None,
    qu_id_purchase: int = None,
    min_stock_amount: float = None,
    product_group_id: int = None,
) -> dict:
    """
    Update selected fields of an existing product.

    Only fields provided (non-None) will be updated.

    Args:
        product_id: ID of the product to update.
        name: New product name.
        description: New description.
        location_id: New default location ID.
        qu_id_stock: New stock quantity unit ID.
        qu_id_purchase: New purchase quantity unit ID.
        min_stock_amount: New minimum stock amount.
        product_group_id: New product group ID.
    """
    data: dict[str, Any] = {}
    if name is not None:
        data["name"] = name
    if description is not None:
        data["description"] = description
    if location_id is not None:
        data["location_id"] = location_id
    if qu_id_stock is not None:
        data["qu_id_stock"] = qu_id_stock
    if qu_id_purchase is not None:
        data["qu_id_purchase"] = qu_id_purchase
    if min_stock_amount is not None:
        data["min_stock_amount"] = min_stock_amount
    if product_group_id is not None:
        data["product_group_id"] = product_group_id
    return await make_request("PUT", f"objects/products/{product_id}", data=data)


@mcp.tool()
async def delete_product(product_id: int) -> None:
    """
    Delete a product by id.

    Args:
        product_id: ID of the product to delete.
    """
    return await make_request("DELETE", f"objects/products/{product_id}")


@mcp.tool()
async def add_barcode_to_product(product_id: int, barcode: str, note: str = None) -> dict:
    """
    Add a barcode to an existing product.

    This wraps POST /objects/product_barcodes.

    Args:
        product_id: Existing Grocy product ID.
        barcode: Barcode string to associate with the product.
        note: Optional note for this barcode entry.
    """
    data = {
        "product_id": product_id,
        "barcode": barcode,
    }
    if note:
        data["note"] = note
    return await make_request("POST", "objects/product_barcodes", data=data)


@mcp.tool()
async def delete_product_barcode(barcode_id: int) -> None:
    """
    Delete a product barcode by its object id.

    Args:
        barcode_id: ID of the product barcode row to delete.
    """
    return await make_request("DELETE", f"objects/product_barcodes/{barcode_id}")


# Reference Data Tools

@mcp.tool()
async def get_quantity_units() -> List[dict]:
    """
    Get all quantity units.

    Useful for choosing a valid qu_id_stock when creating a product.
    """
    return await make_request("GET", "objects/quantity_units")


@mcp.tool()
async def create_quantity_unit(name: str, name_plural: str = None, description: str = None) -> dict:
    """
    Create a new quantity unit.

    Args:
        name: Singular name of the unit (e.g., "Piece").
        name_plural: Optional plural name (e.g., "Pieces").
        description: Optional description of the unit.
    """
    data = {"name": name}
    if name_plural:
        data["name_plural"] = name_plural
    if description:
        data["description"] = description
    return await make_request("POST", "objects/quantity_units", data=data)


@mcp.tool()
async def delete_quantity_unit(qu_id: int) -> None:
    """
    Delete a quantity unit by id.

    Args:
        qu_id: ID of the quantity unit to delete.
    """
    return await make_request("DELETE", f"objects/quantity_units/{qu_id}")


@mcp.tool()
async def get_locations() -> List[dict]:
    """
    Get all locations.

    Useful for choosing a valid location_id when creating products or moving stock.
    """
    return await make_request("GET", "objects/locations")


@mcp.tool()
async def delete_location(location_id: int) -> None:
    """
    Delete a location by id.

    Args:
        location_id: ID of the location to delete.
    """
    return await make_request("DELETE", f"objects/locations/{location_id}")


@mcp.tool()
async def get_shopping_lists() -> List[dict]:
    """
    Get all shopping lists.

    Useful for choosing a valid shopping_list_id.
    """
    return await make_request("GET", "objects/shopping_lists")


@mcp.tool()
async def delete_shopping_list(list_id: int) -> None:
    """
    Delete a shopping list definition by id (not just its items).

    Args:
        list_id: ID of the shopping list to delete.
    """
    return await make_request("DELETE", f"objects/shopping_lists/{list_id}")


@mcp.tool()
async def get_product_groups() -> List[dict]:
    """
    Get all product groups.

    Helpful for categorizing products when managing stock.
    """
    return await make_request("GET", "objects/product_groups")


@mcp.tool()
async def delete_product_group(group_id: int) -> None:
    """
    Delete a product group by id.

    Args:
        group_id: ID of the product group to delete.
    """
    return await make_request("DELETE", f"objects/product_groups/{group_id}")


@mcp.tool()
async def get_batteries() -> List[dict]:
    """
    Get all batteries.
    """
    return await make_request("GET", "objects/batteries")


@mcp.tool()
async def get_battery(battery_id: int) -> dict:
    """
    Get details of a specific battery.

    Args:
        battery_id: The ID of the battery.
    """
    return await make_request("GET", f"objects/batteries/{battery_id}")


@mcp.tool()
async def delete_battery(battery_id: int) -> None:
    """
    Delete a battery by id.

    Args:
        battery_id: ID of the battery to delete.
    """
    return await make_request("DELETE", f"objects/batteries/{battery_id}")


@mcp.tool()
async def track_battery_charge(battery_id: int, tracked_time: str = None) -> dict:
    """
    Track a battery charge event.

    Args:
        battery_id: The ID of the battery.
        tracked_time: Optional ISO timestamp when the battery was charged (defaults to now).
    """
    data = {}
    if tracked_time:
        data["tracked_time"] = tracked_time
    return await make_request("POST", f"batteries/{battery_id}/charge", data=data)


@mcp.tool()
async def undo_battery_charge(charge_cycle_id: int) -> None:
    """
    Undo a battery charge cycle.

    Args:
        charge_cycle_id: The charge cycle ID to undo.
    """
    return await make_request("POST", f"batteries/charge-cycles/{charge_cycle_id}/undo")


@mcp.tool()
async def print_product_label(product_id: int) -> dict:
    """
    Print the Grocycode label of a product on the configured label printer.

    Args:
        product_id: The ID of the product.
    """
    return await make_request("GET", f"stock/products/{product_id}/printlabel")


@mcp.tool()
async def print_stock_entry_label(entry_id: int) -> dict:
    """
    Print the label for a specific stock entry on the configured label printer.

    Args:
        entry_id: The stock entry ID.
    """
    return await make_request("GET", f"stock/entry/{entry_id}/printlabel")


@mcp.tool()
async def undo_stock_booking(booking_id: int) -> None:
    """
    Undo a specific stock booking.

    Args:
        booking_id: The stock booking ID to undo.
    """
    return await make_request("POST", f"stock/bookings/{booking_id}/undo")


@mcp.tool()
async def undo_stock_transaction(transaction_id: str) -> None:
    """
    Undo a complete stock transaction (may contain multiple bookings).

    Args:
        transaction_id: The stock transaction ID to undo.
    """
    return await make_request("POST", f"stock/transactions/{transaction_id}/undo")


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
async def delete_chore(chore_id: int) -> None:
    """
    Delete a chore by id.

    Args:
        chore_id: ID of the chore to delete.
    """
    return await make_request("DELETE", f"objects/chores/{chore_id}")

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


@mcp.tool()
async def undo_chore_execution(execution_id: int) -> None:
    """
    Undo a previously tracked chore execution.

    Args:
        execution_id: The chore execution ID to undo.
    """
    return await make_request("POST", f"chores/executions/{execution_id}/undo")

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
async def update_task(task_id: int, name: str = None, description: str = None, due_date: str = None) -> None:
    """
    Update selected fields of an existing task.

    Only fields provided (non-None) will be updated.

    Args:
        task_id: ID of the task to update.
        name: New task name.
        description: New task description.
        due_date: New due date in YYYY-MM-DD format.
    """
    data: dict[str, Any] = {}
    if name is not None:
        data["name"] = name
    if description is not None:
        data["description"] = description
    if due_date is not None:
        data["due_date"] = due_date
    return await make_request("PUT", f"objects/tasks/{task_id}", data=data)

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
