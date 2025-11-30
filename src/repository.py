from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from ha_session import ha_session
from settings import settings
from src.models import (
    ConsumeItemInput,
    InventoryItemInput,
    Location,
    ProductCandidate,
    StockItemInput,
)


class GrocyRepository:
    """Repository responsible for all direct Grocy API interactions."""

    def __init__(self) -> None:
        self._base_url = settings.grocy_api_url.rstrip("/")

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> Any:
        url = f"{self._base_url}/{endpoint.lstrip('/')}"

        session_token = await ha_session.ensure_valid_token()

        headers = {
            "Cookie": f"ingress_session={session_token}",
            "GROCY-API-KEY": settings.grocy_api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # Simple retry loop for transient 5xx errors
        attempt = 0
        last_exc: Optional[Exception] = None
        while attempt < 3:
            attempt += 1
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.request(
                        method,
                        url,
                        headers=headers,
                        params=params,
                        json=data,
                        timeout=30.0,
                    )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:  # type: ignore[assignment]
                last_exc = exc
                if 500 <= exc.response.status_code < 600 and attempt < 3:
                    continue
                body: Optional[str]
                try:
                    body = exc.response.text
                except Exception:
                    body = "<unable to read response body>"
                print(
                    "Grocy API error:",
                    {
                        "method": method,
                        "url": url,
                        "status_code": exc.response.status_code,
                        "response_body": body,
                    },
                )
                raise
            except Exception as exc:  # network / timeout
                last_exc = exc
                if attempt < 3:
                    continue
                raise
        if last_exc is not None:
            raise last_exc

    # System helpers

    async def get_system_info(self) -> Dict[str, Any]:
        """Return Grocy system information (version, features, etc.)."""

        result = await self._request("GET", "system/info")
        assert isinstance(result, dict)
        return result

    async def get_db_changed_time(self) -> Dict[str, Any]:
        """Return the last database changed time from Grocy."""

        result = await self._request("GET", "system/db-changed-time")
        assert isinstance(result, dict)
        return result

    async def get_system_config(self) -> Dict[str, Any]:
        """Return all config settings."""
        result = await self._request("GET", "system/config")
        assert isinstance(result, dict)
        return result

    # Product helpers

    async def get_all_products(self) -> List[ProductCandidate]:
        """Return all products with basic metadata and current stock amounts."""

        products = await self._request("GET", "objects/products")
        stock_entries = await self._request("GET", "stock")

        stock_by_product: Dict[int, float] = {}
        if isinstance(stock_entries, list):
            for entry in stock_entries:
                try:
                    pid = int(entry.get("product_id"))
                except (TypeError, ValueError):
                    continue
                amount = float(entry.get("amount", 0.0))
                stock_by_product[pid] = amount

        result: List[ProductCandidate] = []
        for p in products:
            pid_raw = p.get("id")
            try:
                pid = int(pid_raw)
            except (TypeError, ValueError):
                continue
            result.append(
                ProductCandidate(
                    id=pid,
                    name=p.get("name", ""),
                    location_id=p.get("location_id"),
                    qu_id_stock=p.get("qu_id_stock"),
                    qu_id_purchase=p.get("qu_id_purchase"),
                    stock_amount=stock_by_product.get(pid),
                )
            )
        return result

    async def get_quantity_units(self) -> List[Dict[str, Any]]:
        """Return all quantity units from Grocy."""

        result = await self._request("GET", "objects/quantity_units")
        assert isinstance(result, list)
        return result

    async def get_product_groups(self) -> List[Dict[str, Any]]:
        """Return all product groups from Grocy."""

        result = await self._request("GET", "objects/product_groups")
        assert isinstance(result, list)
        return result

    async def search_products(self, query: str) -> List[ProductCandidate]:
        query_lower = query.lower()
        products = await self.get_all_products()
        return [p for p in products if query_lower in p.name.lower()]

    async def get_locations(self) -> List[Location]:
        """Return all locations defined in Grocy."""

        locations = await self._request("GET", "objects/locations")
        result: List[Location] = []
        for loc in locations:
            lid = loc.get("id")
            name = loc.get("name")
            if lid is None or name is None:
                continue
            try:
                result.append(Location(id=int(lid), name=str(name)))
            except (TypeError, ValueError):
                continue
        return result

    # Shopping list helpers

    async def get_shopping_lists(self) -> List[Dict[str, Any]]:
        """Return all shopping lists."""

        result = await self._request("GET", "objects/shopping_lists")
        assert isinstance(result, list)
        return result

    async def get_shopping_list_items(self, list_id: int) -> List[Dict[str, Any]]:
        """Return all items for a specific shopping list."""

        # Shopping list items are in objects/shopping_list with a shopping_list_id field
        result = await self._request("GET", "objects/shopping_list")
        assert isinstance(result, list)
        return [row for row in result if row.get("shopping_list_id") == list_id]

    async def add_shopping_list_item(
        self,
        list_id: int,
        product_id: int,
        amount: float,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add an item to a shopping list."""

        payload: Dict[str, Any] = {
            "product_id": product_id,
            "amount": amount,
            "shopping_list_id": list_id,
        }
        if note:
            payload["note"] = note

        result = await self._request("POST", "objects/shopping_list", data=payload)
        assert isinstance(result, dict)
        return result

    async def remove_shopping_list_item(self, item_id: int) -> Dict[str, Any]:
        """Remove a single shopping list item by its id."""

        result = await self._request("DELETE", f"objects/shopping_list/{item_id}")
        assert isinstance(result, dict) or result is None
        return result or {}

    async def clear_shopping_list(self, list_id: int) -> Dict[str, Any]:
        """Clear all items from a specific shopping list."""

        result = await self._request("POST", f"stock/shoppinglist/{list_id}/clear")
        assert isinstance(result, dict) or isinstance(result, list)
        return {"result": result}

    async def add_missing_products_to_shopping_list(self) -> Dict[str, Any]:
        """Add all missing products (below min stock) to the default shopping list."""

        result = await self._request("POST", "stock/shoppinglist/add-missing-products")
        assert isinstance(result, dict) or isinstance(result, list)
        return {"result": result}

    async def get_stock_overview(self) -> List[Dict[str, Any]]:
        """Return Grocy's stock overview list from GET /stock."""

        result = await self._request("GET", "stock")
        assert isinstance(result, list)
        return result

    async def get_product_stock_details(self, product_id: int) -> Dict[str, Any]:
        """Return detailed stock information for a single product."""

        result = await self._request("GET", f"stock/products/{product_id}")
        assert isinstance(result, dict)
        return result

    async def get_product_stock_history(self, product_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent stock log entries for a product.

        Uses the stock log endpoint for the given product.
        """

        params: Dict[str, Any] = {"limit": limit}
        result = await self._request("GET", f"stock/products/{product_id}/log", params=params)
        assert isinstance(result, list)
        return result

    # Stock helpers

    async def add_stock_entry(self, item: StockItemInput) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "amount": item.amount,
            "transaction_type": "purchase",
        }
        if item.best_before_date:
            data["best_before_date"] = item.best_before_date
        if item.price is not None:
            data["price"] = item.price
        if item.location_id is not None:
            data["location_id"] = item.location_id
        
        # Note: Grocy API doesn't natively support idempotency keys in the body for this endpoint yet,
        # but we include it in the model for future compatibility or middleware handling.
        # For now, we could log it if needed.

        return await self._request(
            "POST",
            f"stock/products/{item.product_id}/add",
            data=data,
        )

    async def consume_stock_entry(self, item: ConsumeItemInput) -> Dict[str, Any]:
        """Consume or spoil stock for a single product."""

        data: Dict[str, Any] = {
            "amount": item.amount,
            "transaction_type": "consume",
            "spoiled": item.spoiled,
        }
        if item.location_id is not None:
            data["location_id"] = item.location_id

        return await self._request(
            "POST",
            f"stock/products/{item.product_id}/consume",
            data=data,
        )

    async def get_stock_volatile(self) -> Dict[str, Any]:
        """Return Grocy's volatile stock overview (expiring/missing products)."""

        result = await self._request("GET", "stock/volatile")
        assert isinstance(result, dict)  # for type-checkers
        return result

    async def inventory_product(self, item: InventoryItemInput) -> Dict[str, Any]:
        """Set the absolute stock amount for a product (inventory adjustment)."""

        data: Dict[str, Any] = {"new_amount": item.new_amount}
        if item.best_before_date:
            data["best_before_date"] = item.best_before_date
        if item.location_id is not None:
            data["location_id"] = item.location_id
        if item.price is not None:
            data["price"] = item.price
        if item.note:
            data["note"] = item.note

        return await self._request(
            "POST",
            f"stock/products/{item.product_id}/inventory",
            data=data,
        )

    async def undo_stock_booking(self, booking_id: int) -> Dict[str, Any]:
        """Undo a specific stock booking."""

        result = await self._request("POST", f"stock/bookings/{booking_id}/undo")
        assert isinstance(result, dict)
        return result

    async def undo_stock_transaction(self, transaction_id: str) -> Dict[str, Any]:
        """Undo a complete stock transaction."""

        result = await self._request("POST", f"stock/transactions/{transaction_id}/undo")
        assert isinstance(result, dict)
        return result

    # Barcode helpers

    async def get_product_by_barcode(self, barcode: str) -> Dict[str, Any]:
        result = await self._request("GET", f"stock/products/by-barcode/{barcode}")
        assert isinstance(result, dict)
        return result

    async def add_stock_by_barcode(
        self,
        barcode: str,
        amount: float,
        best_before_date: Optional[str] = None,
        price: Optional[float] = None,
        location_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "amount": amount,
            "transaction_type": "purchase",
        }
        if best_before_date:
            data["best_before_date"] = best_before_date
        if price is not None:
            data["price"] = price
        if location_id is not None:
            data["location_id"] = location_id

        result = await self._request(
            "POST",
            f"stock/products/by-barcode/{barcode}/add",
            data=data,
        )
        assert isinstance(result, dict)
        return result

    async def consume_stock_by_barcode(
        self,
        barcode: str,
        amount: float,
        spoiled: bool = False,
        location_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "amount": amount,
            "transaction_type": "consume",
            "spoiled": spoiled,
        }
        if location_id is not None:
            data["location_id"] = location_id

        result = await self._request(
            "POST",
            f"stock/products/by-barcode/{barcode}/consume",
            data=data,
        )
        assert isinstance(result, dict)
        return result

    async def link_barcode_to_product(
        self,
        product_id: int,
        barcode: str,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a product-barcode link via POST /objects/product_barcodes."""

        payload: Dict[str, Any] = {"product_id": product_id, "barcode": barcode}
        if note:
            payload["note"] = note

        result = await self._request("POST", "objects/product_barcodes", data=payload)
        assert isinstance(result, dict)
        return result

    # Generic entity and master data helpers

    async def create_product(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a product via POST /objects/products."""

        result = await self._request("POST", "objects/products", data=data)
        assert isinstance(result, dict)
        return result

    async def update_product(self, product_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update a product via PUT /objects/products/{id}."""

        result = await self._request("PUT", f"objects/products/{product_id}", data=data)
        assert isinstance(result, dict)
        return result

    async def create_quantity_unit(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a quantity unit via POST /objects/quantity_units."""

        result = await self._request("POST", "objects/quantity_units", data=data)
        assert isinstance(result, dict)
        return result

    async def inspect_entity(self, entity: str, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Read rows from a generic /objects/{entity} endpoint (read-only)."""

        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        result = await self._request("GET", f"objects/{entity}", params=params)
        assert isinstance(result, list)
        return result

    async def delete_product(self, product_id: int) -> Dict[str, Any]:
        """Delete a product via DELETE /objects/products/{id}."""

        result = await self._request("DELETE", f"objects/products/{product_id}")
        assert isinstance(result, dict) or result is None
        return result or {}

    async def delete_location(self, location_id: int) -> Dict[str, Any]:
        """Delete a location via DELETE /objects/locations/{id}."""

        result = await self._request("DELETE", f"objects/locations/{location_id}")
        assert isinstance(result, dict) or result is None
        return result or {}

    async def delete_quantity_unit(self, qu_id: int) -> Dict[str, Any]:
        """Delete a quantity unit via DELETE /objects/quantity_units/{id}."""

        result = await self._request("DELETE", f"objects/quantity_units/{qu_id}")
        assert isinstance(result, dict) or result is None
        return result or {}

    async def delete_product_group(self, group_id: int) -> Dict[str, Any]:
        """Delete a product group via DELETE /objects/product_groups/{id}."""

        result = await self._request("DELETE", f"objects/product_groups/{group_id}")
        assert isinstance(result, dict) or result is None
        return result or {}

    async def delete_shopping_list(self, list_id: int) -> Dict[str, Any]:
        """Delete a shopping list definition via DELETE /objects/shopping_lists/{id}."""

        result = await self._request("DELETE", f"objects/shopping_lists/{list_id}")
        assert isinstance(result, dict) or result is None
        return result or {}
