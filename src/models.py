from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ToolResponse(BaseModel):
    """Standard response envelope for all MCP tools."""

    data: Dict[str, Any] = Field(..., description="Structured data payload for the tool result.")
    summary: str = Field(..., description="Human-readable summary of the operation result.")
    next: Optional[List[str]] = Field(None, description="Suggested next tool calls to chain.")


class StockItemInput(BaseModel):
    """Input for a single stock item to be added in batch operations."""

    product_id: int = Field(..., description="The unique ID of the product to add.")
    amount: float = Field(..., description="The quantity to add (must be positive).")
    best_before_date: Optional[str] = Field(None, description="ISO 8601 date string (YYYY-MM-DD) for expiration.")
    price: Optional[float] = Field(None, description="Price per unit for this purchase.")
    location_id: Optional[int] = Field(None, description="ID of the location where this stock is stored.")
    idempotency_key: Optional[str] = Field(None, description="Unique key to prevent duplicate operations.")


class ConsumeItemInput(BaseModel):
    """Input for consuming or spoiling a single stock item."""

    product_id: int = Field(..., description="The unique ID of the product to consume.")
    amount: float = Field(..., description="The quantity to consume (must be positive).")
    spoiled: bool = Field(False, description="Set to true if the item was spoiled/wasted.")
    location_id: Optional[int] = Field(None, description="Specific location ID to consume from (optional).")
    idempotency_key: Optional[str] = Field(None, description="Unique key to prevent duplicate operations.")


class InventoryItemInput(BaseModel):
    """Input for setting absolute inventory levels for a product."""

    product_id: int = Field(..., description="The unique ID of the product to inventory.")
    new_amount: float = Field(..., description="The absolute new quantity for the product.")
    best_before_date: Optional[str] = Field(None, description="ISO 8601 date string (YYYY-MM-DD) for expiration.")
    location_id: Optional[int] = Field(None, description="ID of the location where this stock is stored.")
    price: Optional[float] = Field(None, description="Price per unit.")
    note: Optional[str] = Field(None, description="Optional note for the inventory entry.")
    idempotency_key: Optional[str] = Field(None, description="Unique key to prevent duplicate operations.")


class Location(BaseModel):
    """Location entity used for resources and lookups."""

    id: int = Field(..., description="Unique ID of the location.")
    name: str = Field(..., description="Name of the location.")


class ProductCandidate(BaseModel):
    """Simplified product representation for search results and resources."""

    id: int = Field(..., description="Unique ID of the product.")
    name: str = Field(..., description="Name of the product.")
    location_id: Optional[int] = Field(None, description="Default location ID for the product.")
    qu_id_stock: Optional[int] = Field(None, description="Quantity unit ID for stock.")
    qu_id_purchase: Optional[int] = Field(None, description="Quantity unit ID for purchase.")
    stock_amount: Optional[float] = Field(None, description="Current stock amount (if available).")
