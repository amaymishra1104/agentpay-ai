# AgentPay — Backend Engineering Guide

FastAPI + LangGraph backend service for AgentPay, an AI-native autonomous commerce platform built for the **Razorpay AI Buildathon 2026 (Track 1)**.

---

## 1. Backend Architecture

```mermaid
flowchart TD
    subgraph API_Routers["FastAPI Routers (/api/v1)"]
        AGENT_ROUTER["agent.py\n/agent/chat, /agent/sessions"]
        CART_ROUTER["cart.py\n/cart, /cart/{id}/items, /validate"]
        CHECKOUT_ROUTER["checkout.py\n/cart/{id}/checkout, /order/{id}"]
        CATALOG_ROUTER["catalog.py\n/catalog/products, /categories"]
    end

    subgraph Agent_Core["Agentic Core (LangGraph)"]
        GRAPH["BuyerAgent Graph\nStateGraph(BuyerAgentState)"]
        INJECT["_inject_trusted_tool_arguments\n(Trusted Identity Injection)"]
        TOOLS["Tool Registry\nsearch_products, add_to_cart, etc."]
    end

    subgraph Domain_Services["Domain Service Layer"]
        CATALOG_SVC["CatalogService\n113 products, search, inventory"]
        CART_SVC["CartService\npricing, rule-based offers"]
        CHECKOUT_SVC["CheckoutService\norder creation, Razorpay HMAC"]
        TRACKING_SVC["TrackingService\norder timeline, returns, refunds"]
    end

    subgraph Security_Concur["Security & Concurrency Layer"]
        AUTHZ_CHK["Route & Service AuthZ Checks\n(customer_id ownership)"]
        FILE_LOCK["file_lock.py\nAtomic O_CREAT | O_EXCL Lock"]
        HMAC_VERIFY["HMAC-SHA256\nhmac.compare_digest"]
    end

    subgraph Persistence["Storage Layer"]
        SQLITE[("SQLite (agentpay.db)\nSQLAlchemy 2.0 ORM")]
        JSON_DATA[("data/products.json\ndata/offers.json")]
    end

    AGENT_ROUTER --> GRAPH
    GRAPH --> INJECT
    INJECT --> TOOLS
    TOOLS --> AUTHZ_CHK

    CART_ROUTER --> AUTHZ_CHK
    CHECKOUT_ROUTER --> AUTHZ_CHK
    CATALOG_ROUTER --> CATALOG_SVC

    AUTHZ_CHK --> CART_SVC
    AUTHZ_CHK --> CHECKOUT_SVC
    AUTHZ_CHK --> TRACKING_SVC

    CHECKOUT_SVC --> HMAC_VERIFY
    CHECKOUT_SVC --> FILE_LOCK
    FILE_LOCK --> CATALOG_SVC
    CATALOG_SVC --> JSON_DATA

    CART_SVC --> SQLITE
    CHECKOUT_SVC --> SQLITE
    TRACKING_SVC --> SQLITE
```

---

## 2. Agent / LangGraph Flow

- **File Path:** `app/agents/graph.py`
- **State Schema:** `BuyerAgentState` (`app/agents/state.py`)
- **Execution Loop:**
  1. `prepare_context`: Compacts historical tool outputs and prepares chat memory.
  2. `call_model`: Invokes Groq Llama 3.3 70B (or `MockBuyerModel` fallback in `app/agents/model.py`).
  3. `has_tool_calls`: Conditional edge checking if model returned tool calls.
  4. `execute_tools`: Invokes `_inject_trusted_tool_arguments()`, resolves contextual references, runs deterministic tool functions, compacts results, and loops back.
  5. `format_response`: Assembles final assistant text and persists session state.

---

## 3. Tool Architecture

- **File Paths:** `app/agents/tools.py`, `app/tools/catalog_tools.py`, `app/tools/cart_tools.py`, `app/tools/checkout_tools.py`, `app/tools/tracking_tools.py`
- **Tool Registry:** Standard JSON Schema tool definitions exposed to the LLM:
  - `search_products(query, category, min_price, max_price, min_rating, sort_by)`
  - `get_product(product_id)`
  - `compare_products(product_ids)`
  - `create_cart(customer_id, merchant_id)`
  - `add_to_cart(cart_id, customer_id, product_id, quantity)`
  - `get_cart(cart_id, customer_id)`
  - `update_cart_item(cart_id, customer_id, product_id, quantity)`
  - `remove_from_cart(cart_id, customer_id, product_id)`
  - `validate_cart(cart_id, customer_id)`
  - `checkout_cart(cart_id, customer_id, payment_method)`
  - `get_order(order_id, customer_id)`
  - `get_order_tracking(order_id, customer_id)`

---

## 4. Trusted Argument Injection

- **File Path:** `app/agents/graph.py` (`_inject_trusted_tool_arguments`)
- **Mechanism:**
  ```python
  def _inject_trusted_tool_arguments(
      state: BuyerAgentState,
      tool_name: str,
      arguments: dict[str, Any],
  ) -> dict[str, Any]:
      safe_arguments = dict(arguments)
      # Forcefully inject verified customer identity
      if tool_name in {
          "add_to_cart", "get_cart", "update_cart_item", "remove_from_cart",
          "validate_cart", "checkout_cart", "get_order", "get_order_tracking",
          "cancel_order", "request_return"
      }:
          safe_arguments["customer_id"] = state.customer_id
      # Forcefully inject verified cart context
      if tool_name in {"add_to_cart", "get_cart", "update_cart_item", "remove_from_cart", "validate_cart", "checkout_cart"}:
          if state.cart_id:
              safe_arguments["cart_id"] = state.cart_id
      return safe_arguments
  ```

---

## 5. Catalog Service

- **File Path:** `app/services/catalog_service.py`
- **Data Source:** `data/products.json` (113 SKUs across 19 categories).
- **Features:** Multi-attribute filtering, price range parsing, full-text matching, in-memory caching, and stock verification.

---

## 6. Cart Service

- **File Path:** `app/services/cart_service.py`
- **Features:** Cart lifecycle management, line-item pricing snapshots, rule-based offer evaluation (`data/offers.json`), and subtotal/tax/discount calculation.

---

## 7. Checkout Service

- **File Path:** `app/services/checkout_service.py`
- **Features:** Pre-checkout cart validation, Razorpay order generation, HMAC-SHA256 signature verification, inventory locking, and transactional order persistence.

---

## 8. Razorpay Service

- **File Path:** `app/services/checkout_service.py`
- **Integration:** Official `razorpay.Client` SDK.
- **Verification:**
  ```python
  def verify_payment_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature, key_secret):
      msg = f"{razorpay_order_id}|{razorpay_payment_id}".encode("utf-8")
      expected = hmac.new(key_secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
      return hmac.compare_digest(expected, razorpay_signature)
  ```
- **Fallback:** Sandboxed `mock_upi` and `mock_card` payment methods enable offline local testing without requiring external credentials.

---

## 9. Inventory Locking & Concurrency

- **File Path:** `app/services/file_lock.py`
- **Mechanism:** Cross-process atomic file creation via `os.O_CREAT | os.O_EXCL | os.O_WRONLY`.
- **Windows Safety:** Retries on transient `WinError 32` (`ERROR_SHARING_VIOLATION`) and checks PID liveness with `psutil.pid_exists(pid)`.
- **Stress Test:** Verified with `mp_lock_stress.py`.

---

## 10. Database / Persistence

- **File Path:** `app/db/models.py`, `app/db/session.py`
- **Database:** SQLite with SQLAlchemy 2.0 ORM.
- **Models:** `Cart`, `CartItem`, `Order`, `OrderItem`, `AgentSession`, `ReturnRequest`.

---

## 11. Authorization Model

All API endpoints and services verify that the requesting `customer_id` matches the stored resource owner:
```python
if cart.customer_id != customer_id:
    raise HTTPException(status_code=403, detail="Access denied: Cart belongs to another customer")
```

---

## 12. Testing

```powershell
# Run full suite (124 passed, 2 skipped)
.venv\Scripts\python -m pytest -q

# Run customer isolation tests
.venv\Scripts\python -m pytest tests/test_isolation.py tests/test_isolation_adversarial.py -v

# Run inventory concurrency stress test
.venv\Scripts\python mp_lock_stress.py
```

---

## 13. Running Locally

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -e .
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```
OpenAPI documentation: `http://127.0.0.1:8000/docs`
