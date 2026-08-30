# AgentPay System Architecture

Technical architectural specification for **AgentPay**, an AI-native commerce agent platform developed for the **Razorpay AI Buildathon 2026 (Track 1)**.

---

## 1. System Context & Overview

AgentPay connects conversational natural-language discovery directly to a transactional commerce engine. Unlike classical e-commerce platforms that rely on static browsing catalogs, AgentPay exposes an AI agent that acts on behalf of the customer to search, filter, compare, configure, checkout, and track orders across an extensible product catalog.

```mermaid
flowchart TB
    subgraph Frontend_App["Frontend Layer (Next.js 15 App Router)"]
        BUYER_UI["/buyer (Agent Chat and Markdown UX)"]
        CART_UI["/cart (Cart and Razorpay Checkout)"]
        ORDERS_UI["/orders (Order History)"]
        TRACKING_UI["/tracking/[orderId] (Fulfillment Timeline)"]
        SWITCHER["CustomerSwitcher (Demo Identity Personas)"]
    end

    subgraph API_Gateway["FastAPI Gateway (Port 8000)"]
        ROUTERS["REST API Routers (/api/v1/*)"]
        MIDDLEWARE["CORS and Error Handlers"]
    end

    subgraph Agent_Engine["Agent Engine (LangGraph)"]
        GRAPH["BuyerAgent Graph"]
        INJECT["Trusted Argument Injection Layer"]
        MODEL["Groq LLM / Deterministic Mock"]
    end

    subgraph Core_Services["Domain Service Layer"]
        CATALOG_SVC["Catalog Service (113 products, search, caching)"]
        CART_SVC["Cart Service (pricing, coupons, offers)"]
        CHECKOUT_SVC["Checkout Service (order placement, Razorpay)"]
        TRACKING_SVC["Tracking Service (state transitions, returns)"]
        LOCK_SVC["FileLock (atomic Windows-safe locking)"]
    end

    subgraph External_Storage["Data and External Gateways"]
        SQLITE[("SQLite Database")]
        JSON_DATA[("JSON Data Files (products, offers, merchants)")]
        RZP_GATEWAY["Razorpay Payment Gateway (Test Mode)"]
    end

    Frontend_App <-->|HTTP / JSON| API_Gateway
    API_Gateway --> Agent_Engine
    Agent_Engine --> Core_Services
    API_Gateway --> Core_Services
    Core_Services --> External_Storage
    Core_Services <-->|SDK & HMAC| RZP_GATEWAY
```

---

## 2. Key Subsystems

### A. AI Agent Orchestration (LangGraph)
- **State Machine:** Maintained as a LangGraph `StateGraph(BuyerAgentState)`.
- **Context Compaction:** Historical search results and tool responses are compacted to maintain high token efficiency and prevent context explosion.
- **Reference Resolution:** Disambiguates contextual linguistic references (e.g. *"the first one"*, *"the cheaper one"*, *"it"*) against verified historical catalog outputs.
- **Trusted Argument Injection:** Intercepts LLM tool invocations to overwrite `customer_id`, `cart_id`, and `merchant_id` with verified session values.

### B. Frontend Buyer UX & Markdown Presentation
- **App Router:** Built on Next.js 15 (`/buyer`, `/cart`, `/orders`, `/tracking/[orderId]`, `/audit`, `/merchant`, `/catalog`).
- **Markdown & GFM Rendering:** Assistant responses in `/buyer` use `react-markdown` + `remark-gfm` with custom styled renderers for responsive tables, bolding, lists, and safe links. Raw HTML is disabled by default.
- **Persistent Composer:** The chat input composer remains pinned to the bottom of the viewport while conversation history auto-scrolls.
- **Persona Context:** `CustomerContext` and `CustomerSwitcher` provide instantaneous switching between demo personas (`c_demo_001`, `c_demo_002`) to demonstrate customer isolation.

### C. Catalog & Offers Engine
- **Catalog Dataset:** 113 products categorized into 19 categories (running shoes, trail running, apparel, sports watches, hydration, headphones, recovery, fitness equipment, and accessories).
- **Rule-Based Offers:** Evaluates volume discounts, category promos, and bundle offers deterministically from `data/offers.json`.
- **Related Products (Cross-sell):** User-requested recommendations and complementary item lookups via `get_related_products`.
- **Inventory Locking:** Protects inventory state from overselling during concurrent checkouts using `file_lock.py`.

### D. Checkout & Payment Integration
- **Razorpay SDK:** Generates server-side payment orders and validates client responses.
- **Cryptographic Verification:** Server recalculates HMAC-SHA256 of `razorpay_order_id|razorpay_payment_id` and verifies with constant-time `hmac.compare_digest`.
- **Order Placement:** State-based transition from validated cart to finalized order.

### E. Order Lifecycle & Fulfillment Tracking
- **Timeline Engine:** Tracks fulfillment states (`placed` → `confirmed` → `packed` → `shipped` → `out_for_delivery` → `delivered`).
- **Cancellations & Refunds:** Allows cancellation of unfulfilled orders with immediate payment refund simulation.
- **Returns Management:** Validates return window policies (e.g., 7-day or 30-day return policy) and records structured return requests.
