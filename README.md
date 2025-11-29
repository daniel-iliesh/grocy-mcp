# Grocy MCP Server for Home Assistant

Grocy MCP is an MCP (Model Context Protocol) server that exposes a curated, LLM‑friendly layer over the **Grocy REST API**, optimized for use from tools like **MCP Inspector** and LLM IDE integrations.

It provides structured tools for:

- **Stock management**
- **Shopping lists**
- **Recipes**
- **Chores**
- **Tasks**

…plus some convenience helpers (e.g. barcode‑based stock operations and stock adjustments).

All calls are routed through a Home Assistant ingress URL with WebSocket‑based authentication and are served over **Server‑Sent Events (SSE)** on port **8010**.

---

## Architecture & Transport

- **MCP framework**: `mcp.server.fastmcp.FastMCP`
- **Transport**: SSE (`mcp.sse_app()` wrapped in a Starlette app)
- **Port**: `8010`
- **CORS**: Fully open (`allow_origins=["*"]`) for browser‑based MCP Inspector
- **HTTP client**: `httpx.AsyncClient`
- **Auth + ingress**:
  - Uses a Home Assistant WebSocket session (`ha_session.py`) to request a short‑lived `ingress_session` token every ~60s.
  - That token is sent as a cookie: `Cookie: ingress_session=<token>`
  - Grocy API key is passed via `GROCY-API-KEY` header.

The MCP server itself **does not store any credentials**; it reads them from environment variables / `.env` via `pydantic-settings`.

---

## Configuration

Configuration is defined in `settings.py` and loaded from environment / `.env`:

- `GROCY_API_URL`  
  Base URL for Grocy’s API including the ingress path, for example:
  `http://homeassistant.local:9192/api/hassio_ingress/XXXX/api`

- `GROCY_API_KEY`  
  Grocy API key. Can be managed in the Grocy UI.

- `HA_TOKEN`  
  Long‑lived Home Assistant access token used for WebSocket authentication.

Example `.env`:

```env
GROCY_API_URL=http://homeassistant.local:9192/api/hassio_ingress/XXXX/api
GROCY_API_KEY=your-grocy-api-key
HA_TOKEN=your-home-assistant-token
```

> The `Settings` class in `settings.py` automatically reads from `.env` when present.

---

## Running the MCP Server

From the project root:

```bash
uv run python server.py
```

On successful startup you should see something like:

```text
Starting Grocy MCP Server (SSE) with CORS enabled...
Server running at: http://localhost:8010/sse
```

You can then point **MCP Inspector** (or any MCP‑compatible client) at the SSE URL:

- URL: `http://localhost:8010/sse`

All Grocy tools will appear under the **Tools** panel with their docstrings and type information.

---

## Tool Overview

Total tools (baseline): **27**  
Plus several additional helpers (barcode‑based operations, transfers, inventory adjustments).

### 1. Stock Management

- **`get_stock()`**  
  Returns all products currently in stock with quantities and next due dates.  
  Grocy endpoint: `GET /stock`.

- **`get_stock_volatile()`**  
  Returns volatile stock: expiring soon, expired, missing (below min stock), and due products.  
  Grocy endpoint: `GET /stock/volatile`.

- **`get_product_details(product_id: int)`**  
  Detailed information for a single product: quantities, expiry, locations, etc.  
  Grocy endpoint: `GET /stock/products/{productId}`.

- **`search_products(query: str)`**  
  Convenience search over all products by name.  
  Implementation: `GET /objects/products` and in‑memory filter on `name`.

- **`add_stock(product_id: int, amount: float, best_before_date: str | None = None, price: float | None = None)`**  
  Add stock for a product (e.g. after shopping).  
  Uses `transaction_type="purchase"`.  
  Grocy endpoint: `POST /stock/products/{productId}/add`.

- **`consume_stock(product_id: int, amount: float, spoiled: bool = False)`**  
  Consume or spoil a product from stock.  
  Uses `transaction_type="consume"`.  
  Grocy endpoint: `POST /stock/products/{productId}/consume`.

#### Additional Stock Helpers

These are built on top of Grocy’s more advanced stock endpoints:

- **`transfer_stock(product_id: int, amount: float, location_id_from: int, location_id_to: int, stock_entry_id: str | None = None)`**  
  Transfer a product from one location to another.  
  Grocy endpoint: `POST /stock/products/{productId}/transfer`.

- **`inventory_product(product_id: int, new_amount: float, best_before_date: str | None = None, location_id: int | None = None, price: float | None = None, note: str | None = None)`**  
  Set the *absolute* stock count for a product (adds or removes as needed).  
  Grocy endpoint: `POST /stock/products/{productId}/inventory`.

- **`open_product(product_id: int, amount: float = 1.0)`**  
  Mark one or more units as opened.  
  Grocy endpoint: `POST /stock/products/{productId}/open`.

### 2. Barcode‑Based Stock Operations

These are especially convenient for “purchasing by scanning” or quick consumption workflows.

- **`get_product_by_barcode(barcode: str)`**  
  Look up product details by barcode.  
  Grocy endpoint: `GET /stock/products/by-barcode/{barcode}`.

- **`add_stock_by_barcode(barcode: str, amount: float, best_before_date: str | None = None, price: float | None = None, location_id: int | None = None)`**  
  Add stock for a product by barcode (e.g. after scanning groceries at home).  
  Uses `transaction_type="purchase"`.  
  Grocy endpoint: `POST /stock/products/by-barcode/{barcode}/add`.

- **`consume_stock_by_barcode(barcode: str, amount: float, spoiled: bool = False, location_id: int | None = None)`**  
  Consume or spoil stock for a product by barcode.  
  Uses `transaction_type="consume"`.  
  Grocy endpoint: `POST /stock/products/by-barcode/{barcode}/consume`.

- **`transfer_stock_by_barcode(barcode: str, amount: float, location_id_from: int, location_id_to: int, stock_entry_id: str | None = None)`**  
  Transfer a barcode‑identified product between locations.  
  Grocy endpoint: `POST /stock/products/by-barcode/{barcode}/transfer`.

- **`inventory_product_by_barcode(barcode: str, new_amount: float, best_before_date: str | None = None, location_id: int | None = None, price: float | None = None)`**  
  Inventory a product by barcode (set absolute amount).  
  Grocy endpoint: `POST /stock/products/by-barcode/{barcode}/inventory`.

- **`external_barcode_lookup(barcode: str, add: bool = False)`**  
  Use Grocy's external barcode lookup plugin to identify unknown barcodes. When `add=true` and supported, Grocy can auto-create the product.  
  Grocy endpoint: `GET /stock/barcodes/external-lookup/{barcode}`.

### 3. Product Creation & Barcodes

- **`create_simple_product(name: str, qu_id_stock: int, qu_id_purchase: int | None = None, location_id: int | None = None, description: str | None = None)`**  
  Create a new product with the most commonly used fields. If `qu_id_purchase` is omitted, it defaults to `qu_id_stock`.  
  Grocy endpoint: `POST /objects/products`.

- **`add_barcode_to_product(product_id: int, barcode: str, note: str | None = None)`**  
  Attach a barcode to an existing product.  
  Grocy endpoint: `POST /objects/product_barcodes`.

- **`delete_product_barcode(barcode_id: int)`**  
  Delete a product barcode row by id.  
  Grocy endpoint: `DELETE /objects/product_barcodes/{id}`.

- **`update_product(product_id: int, ...)`**  
  Update selected fields of an existing product (name, description, location, units, min stock, product group).  
  Grocy endpoint: `PUT /objects/products/{id}`.

- **`delete_product(product_id: int)`**  
  Delete a product by id. Use with care, as it removes the product definition.  
  Grocy endpoint: `DELETE /objects/products/{id}`.

- **`create_quantity_unit(name: str, name_plural: str | None = None, description: str | None = None)`**  
  Create a new quantity unit (for example when you introduce a new kind of unit not yet in Grocy).  
  Grocy endpoint: `POST /objects/quantity_units`.

### 4. Reference Data (IDs the model usually needs)

- **`get_quantity_units()`**  
  List all quantity units. Use this to discover a valid `qu_id_stock` for `create_simple_product`.  
  Grocy endpoint: `GET /objects/quantity_units`.

- **`delete_quantity_unit(qu_id: int)`**  
  Delete a quantity unit by id. Only do this when you're sure it's not used by existing products.  
  Grocy endpoint: `DELETE /objects/quantity_units/{id}`.

- **`get_locations()`**  
  List all locations. Use this to discover valid `location_id` values for products and stock operations.  
  Grocy endpoint: `GET /objects/locations`.

- **`delete_location(location_id: int)`**  
  Delete a location by id.  
  Grocy endpoint: `DELETE /objects/locations/{id}`.

- **`get_shopping_lists()`**  
  List all shopping lists. Use this to pick the right `shopping_list_id`.  
  Grocy endpoint: `GET /objects/shopping_lists`.

- **`delete_shopping_list(list_id: int)`**  
  Delete a shopping list definition (not just its items).  
  Grocy endpoint: `DELETE /objects/shopping_lists/{id}`.

- **`get_product_groups()`**  
  List all product groups. Helpful for categorizing products when working directly with Grocy.  
  Grocy endpoint: `GET /objects/product_groups`.

- **`delete_product_group(group_id: int)`**  
  Delete a product group by id.  
  Grocy endpoint: `DELETE /objects/product_groups/{id}`.

- **`undo_stock_booking(booking_id: int)`**  
  Undo a single stock booking when something was logged incorrectly.  
  Grocy endpoint: `POST /stock/bookings/{bookingId}/undo`.

- **`undo_stock_transaction(transaction_id: str)`**  
  Undo a whole stock transaction (multiple bookings) by transaction id.  
  Grocy endpoint: `POST /stock/transactions/{transactionId}/undo`.

### 5. Shopping List

- **`get_shopping_list()`**  
  Get the current shopping list items.  
  Grocy endpoint: `GET /objects/shopping_list`.

- **`add_to_shopping_list(product_id: int, amount: float = 1.0, shopping_list_id: int = 1, note: str | None = None)`**  
  Add a product to a shopping list.  
  Grocy endpoint: `POST /objects/shopping_list`.

- **`remove_from_shopping_list(item_id: int)`**  
  Remove a specific item from the shopping list.  
  Grocy endpoint: `DELETE /objects/shopping_list/{id}`.

- **`clear_shopping_list(shopping_list_id: int = 1)`**  
  Clear all items from a shopping list.  
  Grocy endpoint: `POST /stock/shoppinglist/{shoppingListId}/clear`.

- **`add_missing_products_to_shopping_list()`**  
  Auto‑add all products below their minimum stock to the default shopping list.  
  Grocy endpoint: `POST /stock/shoppinglist/add-missing-products`.

### 6. Recipes

- **`get_recipes()`**  
  List all recipes.  
  Grocy endpoint: `GET /objects/recipes`.

- **`get_recipe(recipe_id: int)`**  
  Detailed recipe view including ingredients and instructions.  
  Grocy endpoint: `GET /objects/recipes/{recipeId}`.

- **`delete_recipe(recipe_id: int)`**  
  Delete a recipe by id.  
  Grocy endpoint: `DELETE /objects/recipes/{id}`.

- **`add_recipe_to_shopping_list(recipe_id: int)`**  
  Add missing ingredients for the given recipe to the shopping list.  
  Grocy endpoint: `POST /recipes/{recipeId}/add-not-fulfilled-products-to-shoppinglist`.

- **`consume_recipe(recipe_id: int)`**  
  Consume all required ingredients for a recipe from stock.  
  Grocy endpoint: `POST /recipes/{recipeId}/consume`.

- **`get_recipe_fulfillment(recipe_id: int)`**  
  Get stock fulfillment info for a specific recipe (which ingredients are missing or partially available).  
  Grocy endpoint: `GET /recipes/{recipeId}/fulfillment`.

- **`get_all_recipes_fulfillment()`**  
  Get fulfillment info for all recipes to answer questions like "What can I cook right now?".  
  Grocy endpoint: `GET /recipes/fulfillment`.

### 7. Chores

- **`get_chores()`**  
  List all chores, including next estimated execution times.  
  Grocy endpoint: `GET /chores`.

- **`get_chore(chore_id: int)`**  
  Get details for a single chore.  
  Grocy endpoint: `GET /chores/{choreId}`.

- **`track_chore(chore_id: int, tracked_time: str | None = None, done_by: int | None = None)`**  
  Mark a chore as completed, optionally specifying who did it and at what time.  
  Grocy endpoint: `POST /chores/{choreId}/execute`.

- **`undo_chore_execution(execution_id: int)`**  
  Undo a previously tracked chore execution when it was logged by mistake.  
  Grocy endpoint: `POST /chores/executions/{executionId}/undo`.

- **`delete_chore(chore_id: int)`**  
  Delete a chore definition by id.  
  Grocy endpoint: `DELETE /objects/chores/{id}`.

### 8. Tasks

- **`get_tasks()`**  
  List all tasks.  
  Grocy endpoint: `GET /tasks`.

- **`create_task(name: str, description: str | None = None, due_date: str | None = None)`**  
  Create a new task.  
  Grocy endpoint: `POST /objects/tasks`.

- **`update_task(task_id: int, ...)`**  
  Update selected fields of an existing task (name, description, due date).  
  Grocy endpoint: `PUT /objects/tasks/{id}`.

- **`complete_task(task_id: int)`**  
  Mark a task as completed.  
  Grocy endpoint: `POST /tasks/{taskId}/complete`.

- **`delete_task(task_id: int)`**  
  Delete a task by id.  
  Grocy endpoint: `DELETE /objects/tasks/{taskId}`.

---

## Usage Examples

### Stock Management

```python
# Check expiring products
volatile = get_stock_volatile()

# Add groceries after shopping (by product id)
add_stock(
    product_id=42,
    amount=3,
    best_before_date="2025-12-31",
    price=2.99,
)

# Use milk from stock
consume_stock(product_id=10, amount=1)
```

### Barcode‑Based Workflows

```python
# Scan a product to see details
product = get_product_by_barcode(barcode="0123456789012")

# Purchase items by scanning them
add_stock_by_barcode(
    barcode="0123456789012",
    amount=2,
    best_before_date="2025-06-01",
    price=1.49,
)

# Consume by barcode
consume_stock_by_barcode(barcode="0123456789012", amount=1)
```

### Shopping List & Recipes

```python
# Auto‑add missing products
add_missing_products_to_shopping_list()

# Clear the default shopping list
clear_shopping_list()

# Plan dinner
recipe = get_recipe(recipe_id=5)
add_recipe_to_shopping_list(recipe_id=5)

# After cooking
consume_recipe(recipe_id=5)
```

---

## Testing in MCP Inspector

1. Start the server:

   ```bash
   uv run python server.py
   ```

2. In MCP Inspector, add a new SSE server pointing to:

   - `http://localhost:8010/sse`

3. Verify that all Grocy tools appear under the **Tools** section.

4. Try calling tools like:

   - `get_stock`
   - `get_stock_volatile`
   - `get_shopping_list`
   - `get_recipes`
   - `get_chores`
   - `get_tasks`

5. Optionally test barcode tools if you have barcodes configured in Grocy.

---

## Notes & Limitations

- This MCP server assumes **Grocy is running behind Home Assistant ingress**; direct Grocy URLs may require adapting `GROCY_API_URL` and the auth logic.
- All tools are thin wrappers around Grocy’s official API; errors and validations are surfaced directly from Grocy.
- For advanced/custom operations not exposed as explicit tools, you can still combine these building blocks with LLM reasoning.

