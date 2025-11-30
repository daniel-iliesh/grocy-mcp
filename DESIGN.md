# Grocy MCP Server Design Document

## 1. Executive Summary

This document describes the architectural design of a Model Context Protocol (MCP) server that exposes a self-hosted Grocy instance to Large Language Models (LLMs).

The primary goals are:

- Minimize hallucinations and mis-operations.
- Maximize **task completion** for everyday household workflows:
  - Tracking inventory and purchases.
  - Managing shopping lists.
  - Planning and cooking recipes.
  - Managing chores, tasks, and batteries.

The design:

- Follows a **Task-over-CRUD** philosophy: tools are oriented around human intents, not raw REST endpoints.
- Uses **ID-driven operations** and reference lookups to avoid ambiguity.
- Emphasizes **Resource-first** access for read-only context and grounding.
- Plans a shift toward **structured outputs** (`data` / `summary` / `next`) and explicit JSON schemas for robustness.

The current implementation already exposes a rich, mostly endpoint-shaped tool set; this design describes both the present architecture and the direction toward coarser-grained, workflow-shaped tools.

---

## 2. Architecture Principles

### 2.1 Task-Over-CRUD

- Tools are designed around real user intents:
  - "I bought groceries" → add items to stock.
  - "I cooked this recipe" → consume ingredients.
  - "Whats expiring soon?" → volatile stock.
- Under the hood, tools call Grocys REST API (`/stock/...`, `/objects/...`, etc.), but the LLM sees **high-level capabilities**, not raw HTTP operations.

Current state:

- Many tools map closely to single endpoints (e.g., `add_stock`, `consume_stock`, `create_simple_product`).
- The design direction is to introduce **workflow tools** (e.g., `ingest_receipt_items`) that batch and orchestrate multiple Grocy calls.

### 2.2 ID-Driven Operations

To avoid ambiguity and name collisions:

- **All state-changing tools operate on numeric IDs**:
  - `product_id`, `location_id`, `recipe_id`, `chore_id`, `battery_id`, etc.
- Tools exist to discover or derive IDs:
  - `search_products`, `get_product_details`, `get_quantity_units`, `get_locations`, `get_product_groups`, `get_shopping_lists`.
- For barcodes:
  - Tools such as `get_product_by_barcode`, `add_stock_by_barcode`, `consume_stock_by_barcode`, and `add_barcode_to_product` allow workflows to be **barcode-centric** when possible.

Design rationale:

- The LLM should **never guess an ID**.
- It should first resolve human-language references to stable IDs via dedicated tools or (eventually) cached resources.

### 2.3 Rich Context

Each tool aims to provide:

- Machine-usable, structured data (currently direct Grocy JSON).
- Human-readable descriptions via docstrings and README documentation.
- In the future, tool outputs will adopt a **three-layer structure**:

```json
{
  "data": { ... },      // structured payload for chaining
  "summary": "...",    // short NL description
  "next": ["..."]       // optional hints for follow-up tools
}
```

This will make it easier for LLMs to:

- Chain actions (use `data`).
- Explain outcomes to users (quote `summary`).
- Discover workflows (`next` hints).

---

## 3. Resource Definitions (Read-Only Context)

> Note: As of now, the server is tool-centric; resources are a planned enhancement. This section defines the **intended** resource layer.

Resources provide **read-only, side-effect-free** context the LLM can fetch and cache without repeatedly invoking tools or triggering state changes.

### 3.1 Resource URIs

Proposed URI scheme and semantics:

- **`grocy://products`**  
  - JSON: list of active products with key metadata.
  - Example:
    ```json
    [
      { "id": 12, "name": "Milk", "default_location_id": 3, "default_quantity_unit_id": 1 },
      { "id": 45, "name": "Almond Milk", "default_location_id": 3, "default_quantity_unit_id": 1 }
    ]
    ```
  - Purpose:
    - Let the LLM cache product IDs.
    - Reduce dependence on repeated search calls.
    - Help disambiguate user requests ("Milk" vs "Almond Milk").

- **`grocy://locations`**  
  - JSON: list of valid locations.
  - Example:
    ```json
    [
      { "id": 1, "name": "Pantry" },
      { "id": 2, "name": "Fridge" }
    ]
    ```
  - Purpose:
    - Provide a **finite enum-like set** for locations.
    - Prevent "invalid location ID" errors.
    - Support constrained schemas in tools.

- **`grocy://shopping-lists`**  
  - JSON: list of active shopping lists.
  - Example:
    ```json
    [
      { "id": 1, "name": "Main", "description": "Default list" },
      { "id": 2, "name": "Costco" }
    ]
    ```
  - Purpose:
    - Support planning flows ("Add to Costco list").
    - Provide stable IDs for list-related tools.

- **`grocy://stock/volatile`**  
  - JSON: expiring and missing products, derived from `/stock/volatile`.
  - Example:
    ```json
    {
      "expiring_products": [...],
      "expired_products": [...],
      "missing_products": [...]
    }
    ```
  - Purpose:
    - Enable "What do I need to cook?" or "Whats expiring?" queries without a tool call for every subprocess.
    - Provide context for recipe and shopping list workflows.

### 3.2 Prompt and Persona Resources

Planned additional resources:

- **`grocy://prompts/kitchen-assistant`**  
  - Contains a system prompt template that sets expectations:
    - Always resolve IDs before mutating state.
    - Prefer barcode workflows when barcodes are present.
    - Use volatile stock to recommend what to cook.
  - Allows clients to initialize the LLM with a **stable behavioral contract** for Grocy.

---

## 4. Tool Definitions (Capabilities)

This section describes the intended tool layer in **coarse-grained, workflow terms**, mapping them to (possibly multiple) underlying Grocy API calls. Many of these capabilities already exist as sets of primitives; the direction is to consolidate them where appropriate.

### 4.1 Core Inventory Management

#### 4.1.1 Tool: `find_product`

- **Description**  
  Search for products by name to retrieve IDs and key metadata.

- **Parameters**
  - `query: string`  free-text search (e.g., `"milk"`).

- **Behavior**
  - Internally calls Grocys product search endpoints.
  - Returns candidate matches with:
    - `id`, `name`
    - default location ID
    - default quantity unit IDs.

- **Why**
  - Entry point for any stock or shopping workflow.
  - LLM cannot guess IDs; it must resolve them explicitly before any mutation.

_(Currently covered by tools like `search_products` / `get_product_details`.)_

#### 4.1.2 Tool: `add_stock_items` (Batch-Capable)

- **Description**  
  Add one or more purchased items to stock in a single call (e.g., from a shopping trip or parsed receipt).

- **Parameters (proposed schema)**

```json
{
  "items": [
    {
      "product_id": 123,
      "amount": 2.5,
      "price": 5.99,
      "best_before_date": "2025-12-01"
    }
  ]
}
```

- All `product_id` values must be valid.
- `amount > 0`.
- `best_before_date` optional.

- **Behavior**
  - Loops over items, calling Grocy stock add endpoints (`/stock/products/{productId}/add` or barcode-based variants).
  - Aggregates results and errors.

- **Design notes**
  - Batch input avoids "10 tool calls for 10 items".
  - Reduces latency and MCP overhead.
  - Works well with prior parsing (e.g., an LLM parsing a receipt into structured `items`).

_(Current implementation provides per-item tools: `add_stock`, `add_stock_by_barcode`, etc. Batch wrapper is a planned refinement.)_

#### 4.1.3 Tool: `consume_stock_item`

- **Description**  
  Consume or remove an amount of a product from stock (eaten, spoiled, lost).

- **Parameters**
  - `product_id: integer` (required).
  - `amount: number` (required, > 0).
  - `spoiled: boolean` (optional, default `false`).

- **Output (ideal shape)**

```json
{
  "data": {
    "product_id": 123,
    "consumed_amount": 1,
    "remaining_amount": 2,
    "spoiled": false
  },
  "summary": "Removed 1.0 Bottles of Ketchup. 2.0 remaining.",
  "next": ["get_stock_volatile"]
}
```

_(Currently covered by tools such as `consume_stock` and `consume_stock_by_barcode`.)_

---

### 4.2 Shopping & Planning

#### 4.2.1 Tool: `update_shopping_list`

- **Description**  
  Add or remove items from a given shopping list.

- **Parameters**

```json
{
  "action": "add" | "remove",
  "list_id": 1,
  "product_id": 123,
  "amount": 2.0,
  "note": "Organic preferred"
}
```

- `list_id` default can be user-configurable (e.g., 1 = main list).

- **Behavior**
  - For `"add"`: posts a new shopping list item or increments existing.
  - For `"remove"`: decrements/removes the item.
  - Validates that `amount > 0`.

_(Current server exposes tools like `add_to_shopping_list`, `remove_from_shopping_list`, `get_shopping_lists`.)_

#### 4.2.2 Tool: `get_shopping_list_items`

- **Description**  
  Retrieve the full content of a shopping list.

- **Parameters**
  - `list_id: integer` (required).

- **Use cases**
  - "What is on my list?"
  - "Is milk already on the list?"

_(Implemented via list-related tools that call Grocys `/stock/shoppinglist/...` endpoints.)_

---

### 4.3 Recipe Management

#### 4.3.1 Tool: `search_recipes`

- **Description**  
  Find recipes by name or use ingredients availability to filter.

- **Parameters**
  - `query: string`  recipe name or keyword.
  - `only_available_ingredients: boolean`  if true, prefer recipes that can be fulfilled with current stock.

- **Behavior**
  - Uses Grocy recipe endpoints and fulfillment endpoints to assess stock coverage.

_(Currently: tools exist for recipe search and fulfillment; this wraps them into a more intent-oriented interface.)_

#### 4.3.2 Tool: `consume_recipe`

- **Description**  
  "Cook" a recipe: consumes all required ingredients according to the recipe definition and stock levels.

- **Parameters**
  - `recipe_id: integer` (required).

- **Behavior**
  - Calls Grocy endpoints to compute fulfillment.
  - Consumes ingredients via recipe consumption endpoints.
  - Returns:

```json
{
  "data": {
    "recipe_id": 42,
    "servings": 2,
    "ingredients_consumed": [...],
    "missing_ingredients": [...]
  },
  "summary": "Cooked 'Spaghetti Bolognese' for 2 servings. All ingredients were available.",
  "next": ["add_missing_ingredients_to_shopping_list"]
}
```

_(Currently supported via dedicated recipe tools, including fulfillment and consumption.)_

---

### 4.4 Additional Domains (Chores, Tasks, Batteries, Calendar)

The server already exposes tools for:

- **Chores**:
  - Listing chores, tracking executions, undoing executions, and deleting chores.
- **Tasks**:
  - Listing, creating, updating, completing, undoing, and deleting tasks.
- **Batteries**:
  - Listing batteries, recording charge cycles, undoing cycles, and deleting batteries.
- **Calendar (planned / partly implemented)**:
  - `get_calendar_ical`  returns calendar iCal content.
  - `get_calendar_sharing_link`  returns the sharing URL if configured.

Design principle:

- Tools remain **narrow and explicit** (e.g., `undo_chore_execution`, `undo_battery_charge`), avoiding opaque catch-alls.

---

## 5. Best Practices Implementation Details

### 5.1 Strict JSON Schemas and Enums

Tool parameters are defined with explicit types and constraints. Planned improvements:

- Use enums or finite sets where applicable:
  - `action 1 "add", "remove"`
  - `spoiled 1 {true, false}`
- Constrain numeric parameters:
  - `amount > 0`
  - `limit  50` for listing tools.

Example (hypothetical unit-exposing schema):

```json
"unit": {
  "type": "string",
  "enum": ["Pack", "Bottle", "Kg", "Gram", "Piece"],
  "description": "Must match one of the units defined via grocy://quantity-units"
}
```

Currently:

- Many tools use simple numeric IDs and free-text names.
- Quantity units and locations are discovered via tools (`get_quantity_units`, `get_locations`) but not yet surfaced as resources.

### 5.2 Three-Layer Output

Planned uniform output envelope:

```json
{
  "data": { ... },     // canonical machine payload
  "summary": "...",    // human-friendly explanation
  "next": ["..."]      // optional recommended follow-ups
}
```

Current state:

- Tools return Grocys raw JSON responses directly.
- Error details are printed server-side via `make_request` logging for debugging.
- Adopting this pattern will:
  - Provide stable structured fields for client logic.
  - Reduce the token cost of re-deriving natural language summaries in the main model context.

### 5.3 Error Handling as Guidance

`make_request` already logs:

- HTTP method, URL, status code, and response body on non-2xx responses.

Planned server-level error translation:

- Transform raw API errors into structured, LLM-helpful messages:

Bad:

```json
{ "error": "Invalid ID" }
```

Better:

```json
{
  "error": {
    "code": "PRODUCT_NOT_FOUND",
    "message": "Product ID '9999' does not exist. Use 'search_products' or 'find_product' to locate the correct product first."
  }
}
```

Goal:

- Encourage the LLM to recover by calling appropriate lookup tools or resources.

### 5.4 Prompt Templates and Persona

Planned `grocy://prompts/kitchen-assistant` resource:

- Persona:
  - "You are a Kitchen Assistant managing a Grocy instance."
- Behavioral rules:
  - Always resolve product IDs (or barcodes) before mutating stock.
  - If a user says "I bought milk" and multiple milks exist:
    - Ask a clarifying question.
    - Or choose the most frequently used product if clearly dominant.
  - Use volatile stock to suggest recipes or shopping actions.

This ensures that **every client** using the MCP server can bootstrap a consistent, safe interaction style.

---

## 6. Security Considerations

### 6.1 API Keys and Authentication

- The MCP server runs server-side and connects to Grocy via:
  - `GROCY_API_URL`
  - `GROCY_API_KEY`
  - `HA_TOKEN` (for Home Assistant ingress sessions, when applicable).
- These secrets are:
  - Loaded from environment variables / `.env` via `Settings`.
  - **Never exposed** to the LLM or client tools.

### 6.2 Least Privilege and Scope

- Tools do **not** expose arbitrary SQL or generic code execution.
- Only specific, well-defined Grocy endpoints are wrapped.
- Deletion and undo tools exist but are:
  - Explicit (e.g., `delete_product`, `undo_stock_booking`).
  - Named clearly to avoid accidental invocation.

Potential extensions:

- Role-based behavior (e.g., read-only vs. admin) via separate MCP servers or configuration per deployment.

### 6.3 Input Validation and Sanitization

- Inputs checked at the MCP server edge before hitting Grocy:
  - `amount > 0` for stock and list operations.
  - Reasonable upper bounds on `limit` parameters.
- Free-text fields (names, notes, descriptions):
  - Sanitized to avoid injection into Grocys backend or into logs.
- Errors are **fail-fast** with actionable messages, guiding the LLM to:
  - Re-prompt the user.
  - Call lookup tools.
  - Adjust parameters.

### 6.4 Logging and Monitoring

- `make_request` logs:
  - Method, URL, status code, and response body on errors.
- Future structured logging:

```json
{
  "timestamp": "2025-09-23T14:12:00Z",
  "tool": "add_stock_items",
  "userId": "home-user-1",
  "durationMs": 45,
  "ok": true
}
```

- Enables:
  - Debugging LLM behavior and misuses.
  - Building "golden tasks" and safety tests.
  - Monitoring for rate-limit or safety issues.

---

## 7. Future Work

- **Resource layer**: Implement `grocy://products`, `grocy://locations`, `grocy://shopping-lists`, `grocy://stock/volatile`, and prompt resources.
- **Workflow tools**:
  - `ingest_receipt_items`  full receipt → products + barcodes + stock, end-to-end.
  - Higher-level "meal planning" or "weekly restock" tools.
- **Standardized output envelope**:
  - Transition from raw Grocy JSON to `data/summary/next` pattern.
- **Idempotency keys**:
  - Optional parameter for operations that might be retried by LLM clients.
- **Testing**:
  - Golden task suites for:
    - "I bought X, Y, Z."
    - "What should I cook tonight?"
    - "Undo that last chore execution."
  - Safety tests for:
    - Over-broad deletions.
    - Misuse of high-impact tools.
