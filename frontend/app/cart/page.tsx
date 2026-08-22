"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { Cart, Order } from "../../lib/types";
import { API_BASE_URL } from "../../lib/api";

type ValidationIssue = {
  type: string;
  product_id?: string;
  message: string;
};

type ValidationResult = {
  valid: boolean;
  issues: ValidationIssue[];
};

export default function CartPage() {
  const [cart, setCart] = useState<Cart | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [validating, setValidating] = useState(false);

  // New checkout state variables
  const [checkoutStep, setCheckoutStep] = useState<"cart" | "review" | "success">("cart");
  const [paymentMethod, setPaymentMethod] = useState<"mock_upi" | "mock_card">("mock_upi");
  const [placedOrder, setPlacedOrder] = useState<Order | null>(null);
  const [checkingOut, setCheckingOut] = useState(false);

  const handleProceedToCheckout = async () => {
    if (!cart) return;
    setActionError(null);
    setValidating(true);
    try {
      const res = await fetch(`${API_BASE_URL}/cart/${cart.cart_id}/validate`, {
        method: "POST",
      });
      if (!res.ok) throw new Error("Validation check failed.");
      const result = (await res.json()) as ValidationResult;
      setValidation(result);
      if (!result.valid) {
        setActionError("Please resolve validation issues before checking out.");
        return;
      }
      setCheckoutStep("review");
    } catch (err) {
      setActionError(getErrorMessage(err, "Failed to validate cart."));
    } finally {
      setValidating(false);
    }
  };

  const handlePlaceOrder = async () => {
    if (!cart || !cart.cart_id) return;
    setActionError(null);
    setCheckingOut(true);

    try {
      const res = await fetch(`${API_BASE_URL}/cart/${cart.cart_id}/checkout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          payment_method: paymentMethod,
          customer_id: cart.customer_id
        }),
      });

      if (!res.ok) {
        let errMsg = `Checkout failed (status ${res.status})`;
        try {
          const errData = await res.json();
          if (errData && errData.detail) {
            errMsg = typeof errData.detail === "string" ? errData.detail : JSON.stringify(errData.detail);
          }
        } catch {}
        throw new Error(errMsg);
      }

      const orderData = (await res.json()) as Order;
      setPlacedOrder(orderData);

      // Clear localStorage cart reference so next session starts fresh
      const SESSION_STORAGE_KEY = "agentpay_buyer_session_id";
      const sessionId = typeof window !== "undefined" ? window.sessionStorage.getItem(SESSION_STORAGE_KEY) : null;
      const storageKey = sessionId ? `agentpay_cart_id:${sessionId}` : "agentpay_cart_id";
      localStorage.removeItem(storageKey);

      setCheckoutStep("success");
    } catch (err) {
      setActionError(getErrorMessage(err, "Error placing order"));
    } finally {
      setCheckingOut(false);
    }
  };

  function getErrorMessage(err: unknown, defaultMsg: string): string {
    if (err instanceof TypeError) {
      return "Connection Failed: Unable to reach the AgentPay backend. Please check that the server is running and accessible.";
    }
    if (err instanceof Error) {
      return err.message;
    }
    return defaultMsg;
  }

  const dummyEmptyCart = (cartId: string | null): Cart => ({
    cart_id: cartId || "",
    merchant_id: "m_urbanrun",
    customer_id: "c_demo_001",
    currency: "INR",
    items: [],
    subtotal_inr: 0,
    discount_inr: 0,
    shipping_inr: 0,
    total_inr: 0,
    applied_offers: [],
    status: "active",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  });

  // Initialize or load cart on mount
  useEffect(() => {
    async function initCart() {
      try {
        const SESSION_STORAGE_KEY = "agentpay_buyer_session_id";
        const sessionId = typeof window !== "undefined" ? window.sessionStorage.getItem(SESSION_STORAGE_KEY) : null;
        const storageKey = sessionId ? `agentpay_cart_id:${sessionId}` : "agentpay_cart_id";

        const storedId = localStorage.getItem(storageKey);
        if (!storedId) {
          // Instead of creating a database record immediately, show a clean client empty cart
          setCart(dummyEmptyCart(null));
        } else {
          // Fetch existing cart
          const res = await fetch(`${API_BASE_URL}/cart/${storedId}`);
          if (!res.ok) {
            // If stored cart ID is invalid/expired on server, clear from storage and fallback to empty
            localStorage.removeItem(storageKey);
            setCart(dummyEmptyCart(null));
            return;
          }
          const data = (await res.json()) as Cart;
          setCart(data);

          // Handle checked_out carts on page refresh/initial load
          if (data.status === "checked_out") {
            try {
              const orderRes = await fetch(`${API_BASE_URL}/checkout/order/by-cart/${data.cart_id}?customer_id=${data.customer_id}`);
              if (orderRes.ok) {
                const orderData = (await orderRes.json()) as Order;
                setPlacedOrder(orderData);
                setCheckoutStep("success");
              }
            } catch (orderErr) {
              console.error("Failed to recover checked out order details:", orderErr);
            }
          }
        }
      } catch (err: unknown) {
        setError(getErrorMessage(err, "Failed to load cart"));
      } finally {
        setLoading(false);
      }
    }
    initCart();
  }, []);

  const updateQuantity = async (productId: string, newQty: number) => {
    if (!cart) return;
    if (newQty <= 0) {
      await removeItem(productId);
      return;
    }

    setActionError(null);
    try {
      // If the cart doesn't exist on server yet (dummy empty cart), create it first
      let activeCartId = cart.cart_id;
      const SESSION_STORAGE_KEY = "agentpay_buyer_session_id";
      const sessionId = typeof window !== "undefined" ? window.sessionStorage.getItem(SESSION_STORAGE_KEY) : null;
      const storageKey = sessionId ? `agentpay_cart_id:${sessionId}` : "agentpay_cart_id";

      if (!activeCartId) {
        const createRes = await fetch(`${API_BASE_URL}/cart`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            merchant_id: "m_urbanrun",
            customer_id: "c_demo_001",
          }),
        });
        if (!createRes.ok) throw new Error("Failed to initialize server-side cart");
        const createdData = (await createRes.json()) as Cart;
        localStorage.setItem(storageKey, createdData.cart_id);
        activeCartId = createdData.cart_id;
      }

      const res = await fetch(`${API_BASE_URL}/cart/${activeCartId}/items/${productId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ quantity: newQty }),
      });

      if (!res.ok) {
        let errMsg = `Failed to update quantity (status ${res.status})`;
        try {
          const errData = await res.json();
          if (errData && errData.detail) {
            errMsg = typeof errData.detail === "string" ? errData.detail : JSON.stringify(errData.detail);
          }
        } catch {}
        throw new Error(errMsg);
      }

      const updated = (await res.json()) as Cart;
      setCart(updated);
      setValidation(null); // Reset validation on change
    } catch (err) {
      setActionError(getErrorMessage(err, "Error updating item quantity"));
    }
  };

  const removeItem = async (productId: string) => {
    if (!cart || !cart.cart_id) return;
    setActionError(null);

    try {
      const res = await fetch(`${API_BASE_URL}/cart/${cart.cart_id}/items/${productId}`, {
        method: "DELETE",
      });

      if (!res.ok) {
        let errMsg = `Failed to remove item (status ${res.status})`;
        try {
          const errData = await res.json();
          if (errData && errData.detail) {
            errMsg = typeof errData.detail === "string" ? errData.detail : JSON.stringify(errData.detail);
          }
        } catch {}
        throw new Error(errMsg);
      }

      const updated = (await res.json()) as Cart;
      setCart(updated);
      setValidation(null);
    } catch (err) {
      setActionError(getErrorMessage(err, "Error removing item"));
    }
  };

  const clearCart = async () => {
    if (!cart || !cart.cart_id) return;
    setActionError(null);

    try {
      const res = await fetch(`${API_BASE_URL}/cart/${cart.cart_id}`, {
        method: "DELETE",
      });

      if (!res.ok) {
        let errMsg = `Failed to clear cart (status ${res.status})`;
        try {
          const errData = await res.json();
          if (errData && errData.detail) {
            errMsg = typeof errData.detail === "string" ? errData.detail : JSON.stringify(errData.detail);
          }
        } catch {}
        throw new Error(errMsg);
      }

      const updated = (await res.json()) as Cart;
      setCart(updated);
      setValidation(null);
    } catch (err) {
      setActionError(getErrorMessage(err, "Error clearing cart"));
    }
  };

  const validateCart = async () => {
    if (!cart || !cart.cart_id) return;
    setActionError(null);
    setValidating(true);

    try {
      const res = await fetch(`${API_BASE_URL}/cart/${cart.cart_id}/validate`, {
        method: "POST",
      });

      if (!res.ok) {
        let errMsg = `Validation check failed (status ${res.status})`;
        try {
          const errData = await res.json();
          if (errData && errData.detail) {
            errMsg = typeof errData.detail === "string" ? errData.detail : JSON.stringify(errData.detail);
          }
        } catch {}
        throw new Error(errMsg);
      }

      const result = (await res.json()) as ValidationResult;
      setValidation(result);
    } catch (err) {
      setActionError(getErrorMessage(err, "Error validating cart"));
    } finally {
      setValidating(false);
    }
  };

  if (checkoutStep === "success" && placedOrder) {
    return (
      <main className="mx-auto w-full max-w-md px-6 py-16 text-center">
        <div className="flex flex-col items-center justify-center bg-white rounded-2xl border border-border p-8 shadow-sm">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100 text-emerald-600 mb-4">
            <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">Order placed successfully ✓</h1>
          <p className="text-sm text-muted-foreground mt-2">
            Thank you for your purchase! Your order details are below:
          </p>

          <div className="w-full mt-6 border-t border-b border-border py-4 text-left space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Order ID:</span>
              <code className="font-mono bg-muted px-1.5 py-0.5 rounded text-xs">{placedOrder.order_id}</code>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Total:</span>
              <span className="font-semibold">₹{placedOrder.total}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Payment:</span>
              <span>{placedOrder.payment_method === "mock_card" ? "Mock Card" : "Mock UPI"} — Successful</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Items:</span>
              <span>{placedOrder.items.reduce((acc, x) => acc + x.quantity, 0)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Estimated delivery:</span>
              <span>3–4 days</span>
            </div>
          </div>

          <div className="mt-8 flex w-full gap-4">
            <Link
              href="/buyer"
              className="flex-1 rounded-xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white hover:bg-slate-800 transition text-center"
            >
              Continue Shopping
            </Link>
            <Link
              href={`/tracking/${placedOrder.order_id}`}
              className="flex-1 rounded-xl border border-border px-4 py-3 text-sm font-semibold hover:bg-slate-50 transition text-center flex items-center justify-center"
            >
              Track Shipment
            </Link>
          </div>
        </div>
      </main>
    );
  }

  if (checkoutStep === "review" && cart) {
    return (
      <main className="mx-auto w-full max-w-xl px-6 py-10">
        <div className="border-b border-border pb-4 text-center">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">Order Review</h1>
          <p className="text-sm text-muted-foreground mt-1">Review your details before completing your order.</p>
        </div>

        {actionError && (
          <div className="mt-6 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800 flex items-center justify-between">
            <span>{actionError}</span>
            <button onClick={() => setActionError(null)} className="text-xs font-bold text-red-600 hover:text-red-800">Dismiss</button>
          </div>
        )}

        <div className="mt-6 space-y-6">
          <div className="rounded-xl border border-border bg-card p-5 shadow-sm">
            <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3">Order Details</h2>
            <div className="divide-y divide-border">
              {cart.items.map((item) => (
                <div key={item.product_id} className="flex justify-between py-3 text-sm">
                  <div>
                    <p className="font-medium text-slate-950">{item.name}</p>
                    <p className="text-xs text-muted-foreground">₹{item.unit_price_inr} × {item.quantity}</p>
                  </div>
                  <span className="font-medium text-slate-950">₹{item.line_total_inr}</span>
                </div>
              ))}
            </div>

            <div className="mt-4 border-t border-border pt-4 space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Subtotal</span>
                <span>₹{cart.subtotal_inr}</span>
              </div>
              {cart.discount_inr > 0 && (
                <div className="flex justify-between text-emerald-700">
                  <span>Discount</span>
                  <span>-₹{cart.discount_inr}</span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-muted-foreground">Shipping</span>
                <span>{cart.shipping_inr === 0 ? "FREE" : `₹${cart.shipping_inr}`}</span>
              </div>
              <div className="flex justify-between border-t border-border pt-3 font-semibold text-base text-slate-950">
                <span>TOTAL</span>
                <span>₹{cart.total_inr}</span>
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-border bg-card p-5 shadow-sm">
            <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3">Payment</h2>
            <p className="text-2xs text-amber-700 bg-amber-50 border border-amber-100 rounded-lg p-2.5 mb-3 font-medium">
              ⚠️ DEMO ENVIRONMENT: This is a sandboxed payment layer. No real money or real card details will be collected or processed.
            </p>
            <div className="space-y-2.5">
              <label className="flex items-center gap-3 cursor-pointer p-3 rounded-lg border border-border hover:bg-slate-50 transition">
                <input
                  type="radio"
                  name="payment"
                  value="mock_upi"
                  checked={paymentMethod === "mock_upi"}
                  onChange={() => setPaymentMethod("mock_upi")}
                  className="h-4 w-4 text-indigo-600 border-gray-300 focus:ring-indigo-500"
                />
                <div>
                  <p className="text-sm font-semibold text-slate-950">Mock UPI</p>
                  <p className="text-2xs text-muted-foreground">Simulate instant UPI sandbox payment</p>
                </div>
              </label>

              <label className="flex items-center gap-3 cursor-pointer p-3 rounded-lg border border-border hover:bg-slate-50 transition">
                <input
                  type="radio"
                  name="payment"
                  value="mock_card"
                  checked={paymentMethod === "mock_card"}
                  onChange={() => setPaymentMethod("mock_card")}
                  className="h-4 w-4 text-indigo-600 border-gray-300 focus:ring-indigo-500"
                />
                <div>
                  <p className="text-sm font-semibold text-slate-950">Mock Card</p>
                  <p className="text-2xs text-muted-foreground">Simulate card sandbox credit/debit transaction</p>
                </div>
              </label>
            </div>
          </div>

          <div className="flex gap-4">
            <button
              onClick={() => setCheckoutStep("cart")}
              disabled={checkingOut}
              className="flex-1 rounded-xl border border-border py-3 text-sm font-semibold hover:bg-slate-50 transition disabled:opacity-50"
            >
              Back
            </button>
            <button
              onClick={handlePlaceOrder}
              disabled={checkingOut}
              className="flex-1 rounded-xl bg-indigo-600 py-3 text-sm font-semibold text-white hover:bg-indigo-700 transition disabled:bg-indigo-400"
            >
              {checkingOut ? "Processing..." : "Place Order"}
            </button>
          </div>
        </div>
      </main>
    );
  }

  if (loading) {
    return (
      <main className="mx-auto max-w-4xl px-6 py-16 text-center text-muted-foreground">
        Loading shopping cart...
      </main>
    );
  }

  if (error || !cart) {
    return (
      <main className="mx-auto max-w-4xl px-6 py-16 text-center">
        <p className="text-red-600">Error: {error || "Cart not initialized"}</p>
        <Link href="/buyer" className="mt-4 inline-block text-sky-600 hover:underline">
          Return to Buyer Page
        </Link>
      </main>
    );
  }

  return (
    <main className="mx-auto w-full max-w-4xl px-6 py-10">
      <div className="flex items-center justify-between border-b border-border pb-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Shopping Cart</h1>
          <div className="flex flex-wrap items-center gap-2 mt-1.5 text-sm text-muted-foreground">
            <span>Cart ID:</span>
            <code className="bg-muted px-1.5 py-0.5 rounded text-xs font-mono">{cart.cart_id || "Unsaved"}</code>
            <span className="text-slate-300">|</span>
            <span>Status:</span>
            <span className="inline-flex items-center gap-1 rounded bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700 capitalize border border-emerald-100">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
              {cart.status}
            </span>
          </div>
        </div>
        <Link
          href="/buyer"
          className="rounded-lg border border-border px-4 py-2 text-sm font-medium hover:bg-muted"
        >
          &larr; Continue Shopping
        </Link>
      </div>

      {cart.items.length === 0 ? (
        <div className="mt-12 text-center text-muted-foreground">
          <p>Your shopping cart is empty.</p>
          <Link href="/buyer" className="mt-4 inline-block text-sky-600 hover:underline">
            Browse products &rarr;
          </Link>
        </div>
      ) : (
        <div className="mt-8 grid gap-8 md:grid-cols-3">
          {/* Items Section */}
          <div className="md:col-span-2 space-y-4">
            {actionError && (
              <div className="mb-4 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800 flex items-center justify-between">
                <span>{actionError}</span>
                <button
                  onClick={() => setActionError(null)}
                  className="text-xs font-bold text-red-600 hover:text-red-800"
                >
                  Dismiss
                </button>
              </div>
            )}

            {cart.items.map((item) => (
              <article
                key={item.product_id}
                className="flex items-center justify-between gap-4 rounded-xl border border-border bg-card p-4 shadow-sm"
              >
                <div className="flex-1">
                  <h3 className="font-semibold text-card-foreground">{item.name}</h3>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    SKU: {item.sku} · Unit Price: {cart.currency} {item.unit_price_inr}
                  </p>
                  {!item.available && (
                    <span className="mt-1 inline-block rounded bg-red-100 px-2 py-0.5 text-2xs font-semibold text-red-800">
                      Unavailable
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-3">
                  <div className="flex items-center rounded-lg border border-border bg-muted">
                    <button
                      onClick={() => updateQuantity(item.product_id, item.quantity - 1)}
                      className="px-2.5 py-1 text-sm font-bold hover:bg-card rounded-l-lg"
                    >
                      -
                    </button>
                    <span className="w-8 text-center text-sm font-medium">{item.quantity}</span>
                    <button
                      onClick={() => updateQuantity(item.product_id, item.quantity + 1)}
                      className="px-2.5 py-1 text-sm font-bold hover:bg-card rounded-r-lg"
                    >
                      +
                    </button>
                  </div>

                  <button
                    onClick={() => removeItem(item.product_id)}
                    className="text-sm font-medium text-red-600 hover:text-red-800"
                  >
                    Remove
                  </button>
                </div>
              </article>
            ))}

            <div className="flex justify-between pt-2">
              <button
                onClick={clearCart}
                className="text-sm font-medium text-muted-foreground hover:text-foreground"
              >
                Clear Cart
              </button>

              <button
                onClick={validateCart}
                disabled={validating}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:bg-indigo-400"
              >
                {validating ? "Validating..." : "Validate Cart"}
              </button>
            </div>

            {/* Validation Output */}
            {validation && (
              <div
                className={`mt-4 rounded-xl border p-4 ${
                  validation.valid
                    ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                    : "border-red-200 bg-red-50 text-red-800"
                }`}
              >
                <h4 className="font-semibold text-sm">
                  Validation Status: {validation.valid ? "Ready for checkout" : "Requires attention"}
                </h4>
                {validation.issues.length > 0 ? (
                  <ul className="mt-2 space-y-1 text-xs list-disc list-inside">
                    {validation.issues.map((issue, idx) => (
                      <li key={idx}>
                        <strong>[{issue.type}]</strong> {issue.message}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-1 text-xs">All item checks passed successfully.</p>
                )}
              </div>
            )}
          </div>

          {/* Pricing & Offers Summary */}
          <div className="rounded-xl border border-border bg-card p-6 shadow-sm h-fit">
            <h2 className="text-lg font-semibold border-b border-border pb-3">Order Summary</h2>

            <div className="mt-4 space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Subtotal</span>
                <span>
                  {cart.currency} {cart.subtotal_inr}
                </span>
              </div>

              {cart.discount_inr > 0 && (
                <div className="flex justify-between text-emerald-700">
                  <span>Discount</span>
                  <span>
                    -{cart.currency} {cart.discount_inr}
                  </span>
                </div>
              )}

              <div className="flex justify-between">
                <span className="text-muted-foreground">Shipping</span>
                <span>
                  {cart.shipping_inr === 0 ? "Free" : `${cart.currency} ${cart.shipping_inr}`}
                </span>
              </div>

              <div className="flex justify-between border-t border-border pt-3 font-semibold text-base">
                <span>Total</span>
                <span>
                  {cart.currency} {cart.total_inr}
                </span>
              </div>
            </div>

            <button
              onClick={handleProceedToCheckout}
              disabled={cart.items.length === 0}
              className="mt-6 w-full rounded-xl bg-indigo-600 py-3 text-sm font-semibold text-white hover:bg-indigo-700 transition disabled:bg-indigo-400 disabled:cursor-not-allowed"
            >
              Proceed to Checkout
            </button>

            {/* Offers applied */}
            {cart.applied_offers.length > 0 && (
              <div className="mt-6 border-t border-border pt-4">
                <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  Applied Offers
                </h3>
                <ul className="mt-2 space-y-2">
                  {cart.applied_offers.map((offer) => (
                    <li key={offer.offer_id} className="text-xs">
                      <p className="font-semibold text-emerald-700">{offer.name}</p>
                      <p className="text-muted-foreground">{offer.reason}</p>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}
    </main>
  );
}
