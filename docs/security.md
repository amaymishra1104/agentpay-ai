# AgentPay Security Architecture & Payment Hardening

## Overview
AgentPay is an autonomous AI agent commerce platform designed with rigorous defense-in-depth principles. This document details the cryptographic protocols, server-authoritative identity models, cross-tenant isolation mechanisms, and payment-hardening guarantees enforced across the backend and frontend systems.

---

## 1. Server-Authoritative Customer Identity

### Threat Addressed
- **Client Impersonation**: Malicious clients or compromised frontends asserting arbitrary `customer_id` parameters in query strings or JSON request payloads to manipulate other customers' carts, inspect order history, or hijack deliveries.

### Implementation
- **Cryptographic Session Tokens**: All requests interacting with customer-scoped data must present a signed HMAC-SHA256 token in the standard HTTP `Authorization: Bearer <session_token>` header.
- **Session Issuance (`POST /api/v1/auth/session`)**:
  - The server generates a base64url-encoded payload containing `customer_id`, issued-at timestamp (`iat`), and expiration timestamp (`exp`).
  - The payload is cryptographically signed using the server-secret key (`SESSION_SECRET`).
  - Tokens expire after 24 hours (86,400 seconds) by default.
- **FastAPI Authentication Dependency (`Depends(get_authenticated_customer_id)`)**:
  - Validates cryptographic signatures using constant-time comparison (`hmac.compare_digest`).
  - Enforces expiration timestamps against UTC system time.
  - Resolves the caller's server-authoritative `customer_id`. Any client-supplied `customer_id` in request query strings or request bodies is strictly ignored or rejected.

---

## 2. Resource Ownership & Cross-Tenant Access Control

### Threat Addressed
- **Cross-Tenant Horizontal Privilege Escalation**: Customer B accessing, modifying, checking out, cancelling, or returning Customer A's carts or orders.

### Access Control Matrix

| Endpoint | Operation | Security Enforcement | Violation Result |
| :--- | :--- | :--- | :--- |
| `POST /api/v1/cart` | Create Cart | Binds new cart strictly to authenticated customer | N/A |
| `GET /api/v1/cart/{cart_id}` | Read Cart | Enforces `cart.customer_id == auth_customer_id` | `403 Forbidden` |
| `POST /api/v1/cart/{cart_id}/items` | Add Item | Enforces `cart.customer_id == auth_customer_id` | `403 Forbidden` |
| `PATCH /api/v1/cart/{cart_id}/items/{id}` | Update Item | Enforces `cart.customer_id == auth_customer_id` | `403 Forbidden` |
| `DELETE /api/v1/cart/{cart_id}/items/{id}` | Remove Item | Enforces `cart.customer_id == auth_customer_id` | `403 Forbidden` |
| `POST /api/v1/cart/{cart_id}/checkout` | Checkout | Enforces `cart.customer_id == auth_customer_id` | `403 Forbidden` |
| `GET /api/v1/checkout/orders` | List Orders | Filters orders strictly where `order.customer_id == auth_customer_id` | Empty / Own Only |
| `GET /api/v1/checkout/order/{order_id}` | Read Order | Enforces `order.customer_id == auth_customer_id` | `403 Forbidden` |
| `GET /api/v1/checkout/order/{order_id}/tracking` | Tracking | Enforces `order.customer_id == auth_customer_id` | `403 Forbidden` |
| `POST /api/v1/checkout/order/{order_id}/cancel` | Cancel | Enforces `order.customer_id == auth_customer_id` | `403 Forbidden` |
| `POST /api/v1/checkout/order/{order_id}/return` | Return | Enforces `order.customer_id == auth_customer_id` | `403 Forbidden` |
| `POST /api/v1/checkout/order/{order_id}/advance-status`| Advance | Enforces `order.customer_id == auth_customer_id` | `403 Forbidden` |
| `POST /api/v1/agent/chat` | Agent Chat | Validates session token and scopes agent memory to customer | `401 Unauthorized` |

---

## 3. Razorpay Payment-Order Binding & Anti-Tampering

### Threat Addressed
- **Cart Substitution / Amount Tampering Attack**:
  1. Attacker initializes Razorpay payment order for a cheap item (₹299).
  2. Attacker modifies their cart or creates a second cart with expensive items (₹8,998).
  3. Attacker submits checkout for the expensive cart using the valid Razorpay order ID and signature from the cheap item.

### Implementation (`app/services/razorpay_service.py`)
- **Persistent `PaymentOrder` Record**:
  - When `POST /api/v1/cart/{cart_id}/payment/create-order` is called, the server persists a record binding `razorpay_order_id` to `(cart_id, customer_id, amount_paise)`.
  - Database schema includes a `UNIQUE` index on `payment_orders.razorpay_order_id`.
- **Checkout Verification Pipeline (`verify_and_bind_payment_order`)**:
  1. **Intent Lookup**: Fetches persistent `PaymentOrder` by `razorpay_order_id`.
  2. **Customer Verification**: Asserts `payment_order.customer_id == authenticated_customer_id`.
  3. **Cart Verification**: Asserts `payment_order.cart_id == cart.id`.
  4. **Amount Verification**: Recalculates cart total and asserts `payment_order.amount_paise == (cart.total_inr * 100)`.
  5. **Cryptographic Verification**: Verifies HMAC-SHA256 signature (`msg = f"{order_id}|{payment_id}"`) against `RAZORPAY_KEY_SECRET`.

---

## 4. Authoritative Webhook Processing & Replay Protection

### Threat Addressed
- **Forged Webhooks & Duplicate Delivery**: Attackers injecting fake webhook calls, or payment gateway retries causing duplicate inventory deductions or order duplications.

### Implementation (`app/services/webhook_service.py`, `POST /api/v1/webhooks/razorpay`)
- **Signature Verification**:
  - Validates `X-Razorpay-Signature` against the raw payload bytes using `WEBHOOK_SECRET` with constant-time comparison. Rejects unsigned or forged requests with `400 Bad Request`.
- **Idempotency & Replay Deduplication**:
  - Extracts unique event identifier from `X-Razorpay-Event-Id` header or JSON body `event_id`/`id` (with payload SHA-256 fallback).
  - Attempts to insert into `webhook_events` table (enforced with `UNIQUE` constraint on `event_id`).
  - If event already exists (or raises `IntegrityError` under concurrent execution), returns `{"status": "already_processed"}` immediately without duplicate state mutations.
- **Event Lifecycle Handlers**:
  - `payment.captured`: Updates `PaymentOrder` to `captured` and `Order` to `successful`.
  - `payment.failed`: Updates status to `failed`.
  - `refund.processed`: Marks order as `refunded` and automatically restocks inventory.

---

## 5. Database-Level Concurrency & Idempotency Controls

### Database Constraints
- `orders.cart_id`: `UNIQUE` constraint prevents duplicate orders for the same cart instance.
- `orders.payment_id`: `UNIQUE` constraint prevents double-charging or reusing transaction references.
- `payment_orders.razorpay_order_id`: `UNIQUE` constraint prevents duplicate payment intents.
- `webhook_events.event_id`: `UNIQUE` constraint prevents re-executing webhook events.

### Atomic Concurrency Handling
- Under concurrent race conditions, any secondary thread attempting a duplicate insert triggers an `IntegrityError`. The transaction is rolled back and the existing order/event record is returned safely.

---

## 6. Spending Limits Enforcement

### Threat Addressed
- **Rogue Agent Runaway Spend**: Unconstrained autonomous agent spending or accidental large purchases.

### Implementation (`app/services/spending_limit_service.py`)
- **Per-Transaction Ceiling**: Maximum allowed single transaction is **₹80,000** (8,000,000 paise). Cart totals exceeding ₹80,000 are rejected at checkout.
- **Daily Spending Limit**: Maximum aggregate spend across all successful orders for a customer within the UTC calendar day is **₹200,000** (20,000,000 paise).
- **Real-Time Database Aggregation**: Calculates `sum(Order.total)` for all non-cancelled orders created between `start_of_day_utc` and current time.

---

## 7. Human Confirmation Gate & Cart Invalidation

### Threat Addressed
- **Silent Cart Mutation**: Items being added or prices mutating between the time the user approves a purchase and final checkout execution.

### Implementation (`app/services/confirmation_service.py`)
- **Deterministic Cart Hashing**: Computes SHA-256 hash over sorted items: `f"{sku}:{quantity}:{unit_price}"` concatenated with `f"|total:{cart.total_inr}"`.
- **Confirmation Request (`POST /api/v1/cart/{cart_id}/confirm`)**:
  - Computes active cart hash.
  - Persists `OrderConfirmation` record valid for 15 minutes.
- **Checkout Verification**:
  - When `confirmation_id` is supplied, recalculates active cart hash and asserts exact match.
  - Any item addition, removal, quantity change, or discount alteration invalidates the confirmation with `400 Bad Request`.
  - On successful checkout, confirmation is marked `status = "used"`.

---

## 8. Inventory Locking & Safe Rollbacks

### Implementation
- Preserved atomic file locking (`backend/app/services/file_lock.py`) using Windows `msvcrt.locking` and POSIX `fcntl.flock`.
- **Two-Phase Inventory Commitment**:
  - In-stock availability checked atomically.
  - Decremented inside critical section.
  - In the event of downstream payment gateway failure or integrity errors, inventory is automatically restored via `increment_inventory`.

---

## 9. Security Test Suite Matrix

The security hardening test suite (`backend/tests/test_security_hardening.py`) validates every security control:

| Test Case | Vulnerability / Control Verified |
| :--- | :--- |
| `test_auth_session_endpoint_issue_token` | Validates HMAC-SHA256 session token generation and format |
| `test_auth_me_endpoint` | Verifies server-authoritative identity retrieval |
| `test_missing_session_token_rejected_with_401` | Verifies all protected routes reject unauthenticated requests |
| `test_forged_and_tampered_token_signature_rejected_with_401` | Verifies cryptographic rejection of tampered session tokens |
| `test_expired_token_rejected_with_401` | Verifies expired session tokens cannot be used |
| `test_client_cannot_impersonate_by_overriding_payload_customer_id` | Verifies client body customer_id cannot override authenticated token |
| `test_cross_tenant_cart_manipulation_prevented` | Verifies full tenant isolation on cart operations (GET, POST, DELETE) |
| `test_cross_tenant_order_manipulation_prevented` | Verifies tenant isolation on orders, tracking, status advancement, cancellation |
| `test_cart_substitution_attack_rejected` | Verifies rejection when Razorpay order from ₹299 cart is applied to ₹8,998 cart |
| `test_cross_customer_payment_order_usage_rejected` | Verifies Customer B cannot use Customer A's Razorpay payment intent |
| `test_webhook_missing_signature_rejected` | Verifies rejection of unsigned Razorpay webhook requests |
| `test_webhook_invalid_signature_rejected` | Verifies cryptographic signature verification on webhook endpoint |
| `test_webhook_payment_captured_and_idempotency` | Verifies payment capture and deduplication of webhook replay attacks |
| `test_webhook_refund_processed_restores_inventory` | Verifies webhook refund processing and automated inventory restocking |
| `test_per_transaction_spending_limit` | Verifies enforcement of ₹10,000 per-transaction spend ceiling |
| `test_daily_spending_limit` | Verifies enforcement of ₹25,000 daily spend ceiling |
| `test_confirmation_gate_workflow_and_tamper_invalidation` | Verifies cart hash invalidation on mid-flight cart mutation |
