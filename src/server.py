from typing import Any, Dict, List

from mcp.server.fastmcp import FastMCP

from src.models import ConsumeItemInput, InventoryItemInput, StockItemInput, ToolResponse
from src.repository import GrocyRepository


mcp = FastMCP("Grocy", dependencies=["httpx", "websockets"])

_repo = GrocyRepository()


def _wrap_response(data: Dict[str, Any], summary: str, next_steps: List[str] | None = None) -> Dict[str, Any]:
    """Create a standard ToolResponse envelope and return it as a plain dict."""

    response = ToolResponse(data=data, summary=summary, next=next_steps)
    return response.dict()


@mcp.tool()
async def add_stock(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Batch add multiple stock items in one operation.

    Use this after a shopping trip or parsed receipt. Each item must specify a
    valid product_id and positive amount.
    """

    successes: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []

    for raw in items:
        try:
            item = StockItemInput(**raw)
        except Exception as exc:  # noqa: BLE001
            failures.append({"item": raw, "error": f"Invalid item input: {exc}"})
            continue

        if item.amount <= 0:
            failures.append(
                {
                    "item": item.dict(),
                    "error": "Amount must be greater than 0",
                }
            )
            continue
        try:
            result = await _repo.add_stock_entry(item)
            successes.append({"item": item.dict(), "result": result})
        except Exception as exc:  # noqa: BLE001
            failures.append(
                {
                    "item": item.dict(),
                    "error": str(exc),
                }
            )

    data: Dict[str, Any] = {
        "success_count": len(successes),
        "failure_count": len(failures),
        "successes": successes,
        "failures": failures,
    }

    summary = f"Added {len(successes)} items to stock. {len(failures)} failed."
    next_steps: List[str] = []
    if failures:
        next_steps.append("review_failed_items")

    return _wrap_response(data=data, summary=summary, next_steps=next_steps)


@mcp.tool()
async def consume_stock(
    product_id: int,
    amount: float,
    spoiled: bool = False,
    location_id: int | None = None,
    idempotency_key: str | None = None,
) -> Dict[str, Any]:
    """Consume or spoil a single stock item.

    Use this when a product is used, eaten, spoiled, or otherwise removed
    from inventory.
    """

    item = ConsumeItemInput(
        product_id=product_id,
        amount=amount,
        spoiled=spoiled,
        location_id=location_id,
        idempotency_key=idempotency_key,
    )

    if item.amount <= 0:
        data = {
            "item": item.dict(),
            "error": "Amount must be greater than 0",
        }
        summary = "Failed to consume stock: amount must be greater than 0."
        return _wrap_response(data=data, summary=summary, next_steps=["search_products"])

    try:
        result = await _repo.consume_stock_entry(item)
        data = {
            "item": item.dict(),
            "result": result,
        }
        summary = f"Consumed {item.amount} units of product {item.product_id}."
        next_steps: List[str] = ["get_stock_volatile"]
    except Exception as exc:  # noqa: BLE001
        data = {
            "item": item.dict(),
            "error": str(exc),
        }
        summary = "Failed to consume stock item. See error details in data.error."
        next_steps = ["search_products"]

    return _wrap_response(data=data, summary=summary, next_steps=next_steps)


@mcp.tool()
async def search_products(query: str) -> Dict[str, Any]:
    """Search products by name and return candidate matches with IDs.

    Use this before any state-changing operation if you only know the human
    name of a product.
    """

    candidates = await _repo.search_products(query)

    data = {
        "query": query,
        "candidates": [c.dict() for c in candidates],
    }

    if not candidates:
        summary = f"No products found matching '{query}'."
        next_steps: List[str] = []
    else:
        summary = f"Found {len(candidates)} product candidate(s) for '{query}'."
        next_steps = ["add_stock", "consume_stock"]

    return _wrap_response(data=data, summary=summary, next_steps=next_steps)


@mcp.resource("grocy://products")
async def products_resource() -> List[Dict[str, Any]]:
    """Read-only resource listing simplified product data for grounding."""

    products = await _repo.get_all_products()
    return [p.dict() for p in products]


@mcp.resource("grocy://locations")
async def locations_resource() -> List[Dict[str, Any]]:
    """Read-only resource listing all locations (id and name)."""

    locations = await _repo.get_locations()
    return [loc.dict() for loc in locations]


@mcp.resource("grocy://stock/volatile")
async def stock_volatile_resource() -> Dict[str, Any]:
    """Read-only resource exposing Grocy's volatile stock overview."""

    return await _repo.get_stock_volatile()


@mcp.resource("grocy://stock/overview")
async def stock_overview_resource() -> Dict[str, Any]:
    """Read-only resource exposing Grocy's stock overview list."""

    stock_list = await _repo.get_stock_overview()
    return {"stock": stock_list}


@mcp.resource("grocy://shopping-lists")
async def shopping_lists_resource() -> Dict[str, Any]:
    """Read-only resource exposing all shopping lists."""

    lists_ = await _repo.get_shopping_lists()
    return {"shopping_lists": lists_}


@mcp.resource("grocy://system/config")
async def system_config_resource() -> Dict[str, Any]:
    """Read-only resource exposing Grocy system configuration."""
    return await _repo.get_system_config()


@mcp.tool()
async def get_system_status() -> Dict[str, Any]:
    """Get basic Grocy system status (version, DB change time, etc.)."""

    info = await _repo.get_system_info()
    db_changed = await _repo.get_db_changed_time()

    data = {
        "system_info": info,
        "db_changed_time": db_changed,
    }
    summary = "Retrieved Grocy system status and database change time."
    next_steps: List[str] = ["get_master_data_overview"]
    return _wrap_response(data=data, summary=summary, next_steps=next_steps)


@mcp.tool()
async def get_shopping_lists() -> Dict[str, Any]:
    """Get an overview of all shopping lists."""

    lists_ = await _repo.get_shopping_lists()
    data = {"shopping_lists": lists_}
    summary = f"Retrieved {len(lists_)} shopping list(s)."
    next_steps: List[str] = ["get_shopping_list_items", "update_shopping_list"]
    return _wrap_response(data=data, summary=summary, next_steps=next_steps)


@mcp.tool()
async def get_shopping_list_items(list_id: int) -> Dict[str, Any]:
    """Get all items for a specific shopping list."""

    items = await _repo.get_shopping_list_items(list_id)
    data = {"list_id": list_id, "items": items}
    summary = f"Retrieved {len(items)} item(s) for shopping list {list_id}."
    next_steps: List[str] = ["update_shopping_list"]
    return _wrap_response(data=data, summary=summary, next_steps=next_steps)


@mcp.tool()
async def update_shopping_list(
    action: str,
    list_id: int,
    product_id: int,
    amount: float,
    note: str | None = None,
) -> Dict[str, Any]:
    """Add or remove items from a shopping list.

    action must be "add" or "remove".
    """

    if action not in {"add", "remove"}:
        data = {"action": action, "error": "Invalid action. Use 'add' or 'remove'."}
        summary = "Failed to update shopping list: invalid action."
        return _wrap_response(data=data, summary=summary, next_steps=["get_shopping_lists"])

    if amount <= 0:
        data = {"amount": amount, "error": "Amount must be > 0."}
        summary = "Failed to update shopping list: amount must be > 0."
        return _wrap_response(data=data, summary=summary, next_steps=["get_shopping_list_items"])

    try:
        if action == "add":
            result = await _repo.add_shopping_list_item(list_id=list_id, product_id=product_id, amount=amount, note=note)
            data = {"action": action, "list_id": list_id, "product_id": product_id, "amount": amount, "result": result}
            summary = f"Added {amount} of product {product_id} to shopping list {list_id}."
        else:
            # For simplicity we assume the client has item_id from get_shopping_list_items
            item_id = product_id  # NOTE: this is a simplification; real clients should pass item_id
            result = await _repo.remove_shopping_list_item(item_id=item_id)
            data = {"action": action, "item_id": item_id, "result": result}
            summary = f"Removed item {item_id} from shopping list {list_id}."
        next_steps: List[str] = ["get_shopping_list_items"]
    except Exception as exc:  # noqa: BLE001
        data = {
            "action": action,
            "list_id": list_id,
            "product_id": product_id,
            "amount": amount,
            "error": str(exc),
        }
        summary = "Failed to update shopping list. See data.error for details."
        next_steps = ["get_shopping_list_items"]

    return _wrap_response(data=data, summary=summary, next_steps=next_steps)


@mcp.tool()
async def build_shopping_list_from_volatile_stock() -> Dict[str, Any]:
    """Add all missing products (below min stock) to the default shopping list."""

    try:
        result = await _repo.add_missing_products_to_shopping_list()
        data = {"result": result}
        summary = "Added missing products (below min stock) to the default shopping list."
        next_steps: List[str] = ["get_shopping_lists", "get_shopping_list_items"]
    except Exception as exc:  # noqa: BLE001
        data = {"error": str(exc)}
        summary = "Failed to add missing products to shopping list. See data.error for details."
        next_steps = ["get_stock_volatile"]

    return _wrap_response(data=data, summary=summary, next_steps=next_steps)


@mcp.tool()
async def get_master_data_overview() -> Dict[str, Any]:
    """Get an overview of key Grocy master data (products, locations, units, groups)."""

    products = await _repo.get_all_products()
    locations = await _repo.get_locations()
    quantity_units = await _repo.get_quantity_units()
    product_groups = await _repo.get_product_groups()

    data = {
        "products": [p.dict() for p in products],
        "locations": [loc.dict() for loc in locations],
        "quantity_units": quantity_units,
        "product_groups": product_groups,
    }
    summary = (
        f"Loaded master data overview: {len(products)} products, "
        f"{len(locations)} locations, {len(quantity_units)} units, {len(product_groups)} groups."
    )
    next_steps: List[str] = ["create_product", "update_product_master_data", "create_quantity_unit"]
    return _wrap_response(data=data, summary=summary, next_steps=next_steps)


@mcp.resource("grocy://master-data")
async def master_data_resource() -> Dict[str, Any]:
    """Read-only resource exposing Grocy master data for grounding."""

    products = await _repo.get_all_products()
    locations = await _repo.get_locations()
    quantity_units = await _repo.get_quantity_units()
    product_groups = await _repo.get_product_groups()

    return {
        "products": [p.dict() for p in products],
        "locations": [loc.dict() for loc in locations],
        "quantity_units": quantity_units,
        "product_groups": product_groups,
    }


@mcp.tool()
async def create_product(
    name: str,
    qu_id_stock: int,
    qu_id_purchase: int | None = None,
    location_id: int | None = None,
    product_group_id: int | None = None,
    min_stock_amount: float | None = None,
    description: str | None = None,
) -> Dict[str, Any]:
    """Create a new product with essential master data fields."""

    if qu_id_purchase is None:
        qu_id_purchase = qu_id_stock

    payload: Dict[str, Any] = {
        "name": name,
        "qu_id_stock": qu_id_stock,
        "qu_id_purchase": qu_id_purchase,
    }
    if location_id is not None:
        payload["location_id"] = location_id
    if product_group_id is not None:
        payload["product_group_id"] = product_group_id
    if min_stock_amount is not None:
        payload["min_stock_amount"] = min_stock_amount
    if description:
        payload["description"] = description

    try:
        result = await _repo.create_product(payload)
        data = {"product": result}
        product_id = result.get("id")
        summary = f"Created product '{name}' with id {product_id}."
        next_steps: List[str] = ["set_inventory_levels", "link_barcode_to_product"]
    except Exception as exc:  # noqa: BLE001
        data = {"payload": payload, "error": str(exc)}
        summary = "Failed to create product. See data.error for details."
        next_steps = ["get_master_data_overview"]

    return _wrap_response(data=data, summary=summary, next_steps=next_steps)


@mcp.tool()
async def update_product_master_data(
    product_id: int,
    name: str | None = None,
    qu_id_stock: int | None = None,
    qu_id_purchase: int | None = None,
    location_id: int | None = None,
    product_group_id: int | None = None,
    min_stock_amount: float | None = None,
    description: str | None = None,
) -> Dict[str, Any]:
    """Update selected master data fields for an existing product."""

    payload: Dict[str, Any] = {}
    if name is not None:
        payload["name"] = name
    if qu_id_stock is not None:
        payload["qu_id_stock"] = qu_id_stock
    if qu_id_purchase is not None:
        payload["qu_id_purchase"] = qu_id_purchase
    if location_id is not None:
        payload["location_id"] = location_id
    if product_group_id is not None:
        payload["product_group_id"] = product_group_id
    if min_stock_amount is not None:
        payload["min_stock_amount"] = min_stock_amount
    if description is not None:
        payload["description"] = description

    if not payload:
        data = {"product_id": product_id, "error": "No fields provided to update."}
        summary = "No changes applied: provide at least one field to update."
        return _wrap_response(data=data, summary=summary, next_steps=["get_master_data_overview"])

    try:
        result = await _repo.update_product(product_id, payload)
        data = {"product_id": product_id, "changes": payload, "result": result}
        summary = f"Updated master data for product {product_id}."
        next_steps: List[str] = ["get_master_data_overview"]
    except Exception as exc:  # noqa: BLE001
        data = {"product_id": product_id, "changes": payload, "error": str(exc)}
        summary = "Failed to update product master data. See data.error for details."
        next_steps = ["get_master_data_overview"]

    return _wrap_response(data=data, summary=summary, next_steps=next_steps)


@mcp.tool()
async def create_quantity_unit(
    name: str,
    name_plural: str | None = None,
    description: str | None = None,
) -> Dict[str, Any]:
    """Create a new quantity unit for use with products and stock."""

    payload: Dict[str, Any] = {"name": name}
    if name_plural:
        payload["name_plural"] = name_plural
    if description:
        payload["description"] = description

    try:
        result = await _repo.create_quantity_unit(payload)
        data = {"quantity_unit": result}
        summary = f"Created quantity unit '{name}'."
        next_steps: List[str] = ["get_master_data_overview", "create_product"]
    except Exception as exc:  # noqa: BLE001
        data = {"payload": payload, "error": str(exc)}
        summary = "Failed to create quantity unit. See data.error for details."
        next_steps = ["get_master_data_overview"]

    return _wrap_response(data=data, summary=summary, next_steps=next_steps)


ALLOWED_INSPECT_ENTITIES: List[str] = [
    "products",
    "locations",
    "quantity_units",
    "product_groups",
    "tasks",
    "chores",
]


@mcp.tool()
async def inspect_entity(entity: str, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    """Inspect rows from a generic /objects/{entity} endpoint (read-only).

    The entity name is restricted to a safe allowlist to avoid exposing
    unintended internal tables.
    """

    if entity not in ALLOWED_INSPECT_ENTITIES:
        data = {"entity": entity, "error": "Entity not allowed for inspection."}
        summary = "Refused to inspect entity: not in allowed list."
        return _wrap_response(data=data, summary=summary, next_steps=[])

    if limit <= 0 or limit > 200:
        limit = 50

    try:
        rows = await _repo.inspect_entity(entity, limit=limit, offset=offset)
        data = {"entity": entity, "limit": limit, "offset": offset, "rows": rows}
        summary = f"Retrieved {len(rows)} rows from entity '{entity}'."
        next_steps: List[str] = ["get_master_data_overview"]
    except Exception as exc:  # noqa: BLE001
        data = {"entity": entity, "error": str(exc)}
        summary = "Failed to inspect entity. See data.error for details."
        next_steps = []

    return _wrap_response(data=data, summary=summary, next_steps=next_steps)


@mcp.tool()
async def delete_product(product_id: int, cleanup_stock: bool = False) -> Dict[str, Any]:
    """Delete a product by its id.

    If the product has existing stock, this will fail unless cleanup_stock is True.
    """

    # Check stock level
    try:
        details = await _repo.get_product_stock_details(product_id)
        stock_amount = float(details.get("stock_amount", 0.0))
    except Exception:
        # If lookup fails, we proceed and let the delete call fail if necessary
        stock_amount = 0.0

    if stock_amount > 0:
        if not cleanup_stock:
            data = {
                "product_id": product_id,
                "stock_amount": stock_amount,
                "error": "Product has existing stock.",
            }
            summary = (
                f"Refused to delete product {product_id}: it has {stock_amount} units in stock. "
                "Set cleanup_stock=True to automatically remove stock before deletion."
            )
            return _wrap_response(data=data, summary=summary, next_steps=["consume_stock"])

        # Attempt to clear stock
        try:
            # Consume all stock as spoiled/waste
            consume_input = ConsumeItemInput(
                product_id=product_id,
                amount=stock_amount,
                spoiled=True,
            )
            await _repo.consume_stock_entry(consume_input)
        except Exception as exc:  # noqa: BLE001
            data = {
                "product_id": product_id,
                "stock_amount": stock_amount,
                "error": f"Failed to cleanup stock: {exc}",
            }
            summary = "Failed to remove existing stock before deletion."
            return _wrap_response(data=data, summary=summary, next_steps=["consume_stock"])

    try:
        result = await _repo.delete_product(product_id)
        data = {"product_id": product_id, "result": result}
        if stock_amount > 0:
            data["stock_cleared"] = stock_amount
            summary = f"Cleared {stock_amount} units of stock and deleted product {product_id}."
        else:
            summary = f"Deleted product {product_id}."
        next_steps: List[str] = ["get_master_data_overview"]
    except Exception as exc:  # noqa: BLE001
        data = {"product_id": product_id, "error": str(exc)}
        summary = "Failed to delete product. See data.error for details."
        next_steps = ["inspect_entity"]

    return _wrap_response(data=data, summary=summary, next_steps=next_steps)


@mcp.tool()
async def delete_location(location_id: int) -> Dict[str, Any]:
    """Delete a location by its id."""

    try:
        result = await _repo.delete_location(location_id)
        data = {"location_id": location_id, "result": result}
        summary = f"Deleted location {location_id}."
        next_steps: List[str] = ["get_master_data_overview"]
    except Exception as exc:  # noqa: BLE001
        data = {"location_id": location_id, "error": str(exc)}
        summary = "Failed to delete location. See data.error for details."
        next_steps = ["inspect_entity"]

    return _wrap_response(data=data, summary=summary, next_steps=next_steps)


@mcp.tool()
async def delete_quantity_unit(qu_id: int) -> Dict[str, Any]:
    """Delete a quantity unit by its id."""

    try:
        result = await _repo.delete_quantity_unit(qu_id)
        data = {"quantity_unit_id": qu_id, "result": result}
        summary = f"Deleted quantity unit {qu_id}."
        next_steps: List[str] = ["get_master_data_overview"]
    except Exception as exc:  # noqa: BLE001
        data = {"quantity_unit_id": qu_id, "error": str(exc)}
        summary = "Failed to delete quantity unit. See data.error for details."
        next_steps = ["inspect_entity"]

    return _wrap_response(data=data, summary=summary, next_steps=next_steps)


@mcp.tool()
async def delete_product_group(group_id: int) -> Dict[str, Any]:
    """Delete a product group by its id."""

    try:
        result = await _repo.delete_product_group(group_id)
        data = {"product_group_id": group_id, "result": result}
        summary = f"Deleted product group {group_id}."
        next_steps: List[str] = ["get_master_data_overview"]
    except Exception as exc:  # noqa: BLE001
        data = {"product_group_id": group_id, "error": str(exc)}
        summary = "Failed to delete product group. See data.error for details."
        next_steps = ["inspect_entity"]

    return _wrap_response(data=data, summary=summary, next_steps=next_steps)


@mcp.tool()
async def delete_shopping_list(list_id: int) -> Dict[str, Any]:
    """Delete a shopping list definition by its id."""

    try:
        result = await _repo.delete_shopping_list(list_id)
        data = {"list_id": list_id, "result": result}
        summary = f"Deleted shopping list {list_id}."
        next_steps: List[str] = ["get_shopping_lists"]
    except Exception as exc:  # noqa: BLE001
        data = {"list_id": list_id, "error": str(exc)}
        summary = "Failed to delete shopping list. See data.error for details."
        next_steps = ["get_shopping_lists"]

    return _wrap_response(data=data, summary=summary, next_steps=next_steps)
