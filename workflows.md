# Grocy Workflows

This document describes the main real‑world workflows supported by Grocy, grouped by domain.  
Each workflow is expressed in human terms first, then implicitly maps to one or more Grocy API tags and endpoints (Stock, Recipes, Chores, Tasks, Batteries, Calendar, Files, generic `objects/*`, etc.).[attached_file:21][web:11]

---

## 1. Stock & Inventory Workflows

### 1.1 Initial Inventory Setup

- **Intent:** Get an existing pantry/fridge into Grocy for the first time.[web:53][web:55]
- **Steps (conceptual):**
  - Define products with name, location, quantity units, product group, min stock, and best‑before defaults using `objects/products`, `objects/locations`, `objects/quantity_units`, etc.[attached_file:21]
  - Add initial stock entries for each product using stock “add” endpoints with appropriate transaction type (purchase/inventory).[attached_file:21]
- **Notes:**
  - Must be ID‑driven (product_id, location_id, unit IDs).
  - Avoid creating stock for non‑existent products.

### 1.2 Purchase Logging / “I Bought Groceries”

- **Intent:** Log new items coming into the house, often from a physical receipt or mental list.[web:11][web:55][web:58]
- **Steps (conceptual):**
  - Resolve human item names to products (or detect missing products).
  - Optionally create new products when they don’t exist.
  - Use batch stock‑add operations for `{product_id, amount, price?, best_before_date?, location_id?}` via `Stock` endpoints.[attached_file:21]
- **Notes:**
  - Prefer coarse‑grained, batched workflows instead of one call per line item.
  - Surface per‑item errors clearly (unknown product, invalid unit, etc.).

### 1.3 Consumption, Spoilage, and Corrections

- **Intent:** Track items being used, thrown away, or corrected when counts were wrong.[web:11][web:55]
- **Steps (conceptual):**
  - Consume items via stock consume endpoints with `transaction_type="consume"` and a `spoiled` flag for waste tracking.[attached_file:21]
  - Use dedicated inventory‑correction or undo mechanisms to fix mistakes (wrong product, wrong amount).
- **Notes:**
  - Never silently drop stock below zero.
  - Distinguish between normal consumption, spoilage, and corrections.

### 1.4 Stock Overview (“What Do I Have?”)

- **Intent:** Answer “What’s currently in stock?” and “How much X do I have and where is it?”.[web:11][web:53]
- **Steps (conceptual):**
  - Use stock overview endpoints (Stock tag) to list products with current amounts (and possibly locations).[attached_file:21]
  - Provide per‑product details (lots, best‑before dates, per‑location splits) via product‑specific stock endpoints.[attached_file:21]
- **Notes:**
  - Ideal for read‑only tools/resources and dashboards.
  - Used as context for planning, recipes, and corrections.

### 1.5 Volatile Stock (“What’s Expiring or Missing?”)

- **Intent:** See what needs to be used soon and what needs to be bought.[web:11][web:17][web:55]
- **Steps (conceptual):**
  - Query `/stock/volatile` to get `expiring_products`, `expired_products`, and `missing_products` (below `min_stock_amount`).[attached_file:21]
  - Use that information to:
    - Prioritize recipes that consume expiring items.
    - Add missing products to shopping lists.
- **Notes:**
  - Purely read‑only, ideal as a resource (`grocy://stock/volatile`).
  - Summaries should explain why each item is listed (due date, stock below minimum, etc.).

### 1.6 Stock History, Undo, and Inventory Corrections

- **Intent:** Inspect and correct past stock operations (“I logged that wrong”).[web:53][web:62]
- **Steps (conceptual):**
  - Retrieve stock history/transactions per product via log entities or Stock endpoints.[attached_file:21]
  - Expose a safe undo/correction mechanism:
    - Either undo a specific transaction.
    - Or apply a corrective operation to set stock back to desired levels.
- **Notes:**
  - Tools must be clearly named and documented to avoid casual misuse.
  - Prefer surgical corrections over “reset everything”.

### 1.7 Barcode‑Based Stock Flows

- **Intent:** Use barcodes for fast scanning in and out, often from mobile apps.[attached_file:21][web:58]
- **Steps (conceptual):**
  - Use `Stock "by-barcode"` endpoints to add or consume stock directly by barcode.[attached_file:21]
  - Manage barcode–product associations via `objects/product_barcodes` or dedicated endpoints.
- **Notes:**
  - If a barcode is unknown, offer to:
    - Link it to an existing product.
    - Create a new product and associate the barcode.
  - If a barcode maps to multiple products, fail loudly and explain the conflict.

---

## 2. Shopping & Purchasing Workflows

### 2.1 Manual Shopping List Building

- **Intent:** Build and maintain shopping lists by hand.[web:17][web:19]
- **Steps (conceptual):**
  - Add items to specific shopping lists using shopping list item entities (`ShoppingListItem`).[attached_file:21]
  - Organize by product group/store (`shopping_location_id`) to match supermarket aisles.[attached_file:21][web:17]
- **Notes:**
  - Often combined with volatile stock and recipes (“add missing ingredients/items below min stock”).

### 2.2 Auto‑Generated Shopping Lists

- **Intent:** Automatically build shopping lists from stock status and plans.[web:11][web:17][web:55]
- **Steps (conceptual):**
  - From volatile stock: add missing/expired items to a shopping list.
  - From meal plans/recipes: add missing ingredients for scheduled recipes.
- **Notes:**
  - This is a cross‑domain workflow (Stock + Recipes + Shopping).

### 2.3 Store‑Aware and Printed Lists

- **Intent:** Make lists that are optimized for actual shopping (order, store, print). [web:17][web:55]
- **Steps (conceptual):**
  - Use product groups and shopping locations to group and order items.[attached_file:21][web:19]
  - Send lists to thermal printers via `Print` endpoints for paper lists.[attached_file:21][web:55]

---

## 3. Recipes & Meal Planning Workflows

### 3.1 Recipe Management

- **Intent:** Store recipes linked to products and stock.[attached_file:21][web:58]
- **Steps (conceptual):**
  - Create/update recipes with ingredients (linked to products), instructions, servings, and photos.
  - Use Recipes endpoints and generic `objects/recipes` APIs.[attached_file:21]
- **Notes:**
  - Ingredient–product links are critical for stock and fulfillment logic.

### 3.2 Recipe Fulfilment & Due‑Score Cooking

- **Intent:** Decide what to cook based on what you have and what’s due.[web:11][web:55]
- **Steps (conceptual):**
  - For a recipe, compute if it can be cooked with current stock and how many servings are possible.
  - Leverage “due scores” to prioritize recipes using expiring items.[attached_file:21][web:11]
- **Notes:**
  - Naturally builds on stock overview and volatile stock workflows.

### 3.3 Meal Planning into Calendar & Shopping Lists

- **Intent:** Plan meals ahead and ensure ingredients are available.[web:11][web:55]
- **Steps (conceptual):**
  - Schedule recipes into a meal plan (per day/per meal).
  - Add missing ingredients for planned recipes to a shopping list.
- **Notes:**
  - Integrates with Calendar and Shopping list APIs.

### 3.4 Cooking Workflow (Recipe Consumption)

- **Intent:** Log the actual cooking event and update stock accordingly.[web:55]
- **Steps (conceptual):**
  - When a recipe is cooked, call recipe consumption endpoints to consume all required ingredients in one go.[attached_file:21]
  - Optionally track servings/leftovers.
- **Notes:**
  - This is the “batched consume” counterpart to single‑product consumption.

---

## 4. Household Routines: Chores, Tasks, Batteries

### 4.1 Chore Scheduling and Execution

- **Intent:** Track recurring household chores and who did what.[attached_file:21][web:55]
- **Steps (conceptual):**
  - Define chores (frequency, skip rules, assignment) via `Chores` endpoints.
  - Log executions, update next due dates, and allow undo of mistaken completions.[attached_file:21]
- **Notes:**
  - Frequently surfaced via smart home dashboards for the household.[web:56][web:66]

### 4.2 General Task Management

- **Intent:** Track arbitrary to‑dos and one‑off tasks.[attached_file:21][web:56]
- **Steps (conceptual):**
  - Create/update/delete tasks with due dates, categories, priorities using `Tasks` endpoints.
  - Mark tasks done/undone as needed.
- **Notes:**
  - Acts as a simple integrated task manager that can be exposed to other apps.

### 4.3 Battery Tracking

- **Intent:** Know when batteries need charging or replacement.[attached_file:21][web:55]
- **Steps (conceptual):**
  - Create battery entries for devices.
  - Log charge/replacement events and compute due/overdue states.
- **Notes:**
  - Commonly wired into Home Assistant to show which devices need attention.[web:61][web:63]

---

## 5. Equipment, Files, Calendar & Admin

### 5.1 Equipment & Documentation

- **Intent:** Track household equipment/devices with associated documents.[attached_file:21][web:11]
- **Steps (conceptual):**
  - Model equipment as entities and attach manuals, invoices, and pictures via `Files` APIs.
  - Use this when something breaks and you need info quickly.
- **Notes:**
  - Complements tasks/chores (e.g., annual maintenance).

### 5.2 Calendar & iCal Feeds

- **Intent:** Centralize chores, tasks, and meal plan events in calendars.[attached_file:21][web:55]
- **Steps (conceptual):**
  - Use `Calendar` endpoints to export iCal feeds for chores/tasks/recipes.
  - Integrate those feeds into calendar apps or Home Assistant panels.[web:56][web:66]
- **Notes:**
  - Provides a unified “what’s coming” view for the household.

### 5.3 Generic Entity CRUD & System Operations

- **Intent:** Administer master data and system meta‑info.[attached_file:21][web:16]
- **Steps (conceptual):**
  - Use generic `/objects/{entity}` GET/POST/PUT/DELETE to manage entities like products, locations, units, product groups, userfields, tasks, etc.[attached_file:21]
  - Query system info, config, localization, and users via `System` and `User management` tags.
- **Notes:**
  - This underpins the “UI parity” goal: anything configurable in the UI should have an API path via these endpoints.

---