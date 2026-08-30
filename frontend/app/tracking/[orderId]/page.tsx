"use client";

import { useEffect, useState, use, useCallback } from "react";
import Link from "next/link";
import { API_BASE_URL } from "../../../lib/api";
import { useCustomer } from "../../../lib/customer";
import type { TrackingInfo, Order } from "../../../lib/types";
import { ShieldAlert } from "lucide-react";

export default function TrackingPage({ params }: { params: Promise<{ orderId: string }> }) {
  const resolvedParams = use(params);
  const orderId = resolvedParams.orderId;
  const { customer, customerId } = useCustomer();

  const [tracking, setTracking] = useState<TrackingInfo | null>(null);
  const [orderDetails, setOrderDetails] = useState<Order | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [is403, setIs403] = useState<boolean>(false);

  const [actionLoading, setActionLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // Return form states
  const [selectedProductId, setSelectedProductId] = useState<string>("");
  const [returnReason, setReturnReason] = useState<string>("Defective/broken item");
  const [showReturnForm, setShowReturnForm] = useState(false);

  const fetchTrackingAndOrder = useCallback(async () => {
    setLoading(true);
    setError(null);
    setIs403(false);
    try {
      // 1. Fetch tracking timeline
      const trackRes = await fetch(
        `${API_BASE_URL}/checkout/order/${orderId}/tracking?customer_id=${customerId}`
      );
      if (!trackRes.ok) {
        if (trackRes.status === 403) {
          setIs403(true);
          throw new Error(`HTTP 403 Forbidden: Active demo customer ${customer.name} (${customerId}) is not authorized to access order ${orderId} belonging to a different customer.`);
        }
        throw new Error("Order tracking details not found.");
      }
      const trackData = await trackRes.json();
      setTracking(trackData);

      // 2. Fetch order items/total
      const orderRes = await fetch(
        `${API_BASE_URL}/checkout/order/${orderId}?customer_id=${customerId}`
      );
      if (orderRes.ok) {
        const orderData = await orderRes.json();
        setOrderDetails(orderData);
        if (orderData.items && orderData.items.length > 0) {
          setSelectedProductId(orderData.items[0].product_id);
        }
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "An error occurred while loading tracking info.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [orderId, customerId, customer.name]);

  useEffect(() => {
    fetchTrackingAndOrder();
  }, [fetchTrackingAndOrder]);

  const handleAdvanceStatus = async () => {
    setActionError(null);
    setActionSuccess(null);
    setActionLoading(true);

    try {
      const res = await fetch(`${API_BASE_URL}/checkout/order/${orderId}/advance-status`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Failed to advance order status.");
      }

      setActionSuccess("Order advanced to the next fulfillment stage successfully.");
      await fetchTrackingAndOrder();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to advance status.";
      setActionError(msg);
    } finally {
      setActionLoading(false);
    }
  };

  const handleCancelOrder = async () => {
    setActionError(null);
    setActionSuccess(null);
    setActionLoading(true);

    try {
      const res = await fetch(`${API_BASE_URL}/checkout/order/${orderId}/cancel`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ customer_id: customerId }),
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Failed to cancel order.");
      }

      setActionSuccess("Order cancelled and payment refunded successfully.");
      await fetchTrackingAndOrder();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to cancel order.";
      setActionError(msg);
    } finally {
      setActionLoading(false);
    }
  };

  const handleReturnItem = async () => {
    if (!selectedProductId) return;
    setActionError(null);
    setActionSuccess(null);
    setActionLoading(true);

    try {
      const res = await fetch(`${API_BASE_URL}/checkout/order/${orderId}/return`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          customer_id: customerId,
          product_id: selectedProductId,
          quantity: 1,
          reason: returnReason,
        }),
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Failed to submit return request.");
      }

      const retData = await res.json();
      setActionSuccess(`Return request created successfully. Return ID: ${retData.return_id}`);
      setShowReturnForm(false);
      await fetchTrackingAndOrder();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to submit return request.";
      setActionError(msg);
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <main className="mx-auto max-w-xl px-6 py-16 text-center text-slate-500 text-sm">
        Loading shipment tracking...
      </main>
    );
  }

  if (error || !tracking) {
    return (
      <main className="mx-auto max-w-2xl px-6 py-16">
        <div className="flex items-center justify-between border-b border-slate-200 pb-4 mb-6">
          <h1 className="text-xl font-bold tracking-tight text-slate-900">Shipment Tracking</h1>
          <div className="flex items-center gap-3">
            <Link href="/orders" className="text-xs font-semibold text-indigo-600 hover:text-indigo-500">
              Orders &rarr;
            </Link>
          </div>
        </div>

        {is403 ? (
          <div className="rounded-2xl border border-amber-300/80 bg-gradient-to-b from-amber-50/90 to-amber-100/40 p-6 text-slate-800 shadow-sm">
            <div className="flex items-start gap-3.5">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-amber-600 text-white shadow-xs">
                <ShieldAlert className="h-5 w-5" />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-amber-800">
                    ACCESS DENIED
                  </span>
                  <span className="rounded bg-amber-200/70 px-1.5 py-0.5 text-[10px] font-mono font-bold text-amber-900">
                    HTTP 403 FORBIDDEN
                  </span>
                </div>
                <h3 className="mt-1 text-sm font-bold text-slate-900">
                  This resource belongs to another customer identity.
                </h3>
                <p className="mt-1 text-xs text-slate-600 leading-relaxed">
                  The request was rejected by the server-side authorization boundary. The active demo customer (<strong className="text-slate-800">{customer.name} · {customerId}</strong>) is not the owner of this order.
                </p>
                <div className="mt-4 rounded-xl bg-white/90 p-3.5 border border-amber-200 text-[11px] text-slate-600">
                  <span className="font-bold text-slate-800">Security Architecture Note:</span> This demonstrates that AgentPay enforces strict customer isolation at the backend service layer. LLM prompt injection or client tampering cannot bypass this boundary. Use the Demo Customer Switcher above to switch identities.
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="rounded-xl bg-red-50 border border-red-200 p-6 text-sm text-red-800 text-center">
            {error || "Order tracking details not found."}
          </div>
        )}

        <div className="mt-8 text-center">
          <Link href="/orders" className="text-sm font-semibold text-indigo-600 hover:text-indigo-500">
            &larr; Back to your orders
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto w-full max-w-2xl px-6 py-12">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between border-b border-slate-100 pb-6 gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">Track Shipment</h1>
          <p className="mt-1 text-xs text-slate-500">
            Order <code className="font-mono text-slate-700 font-semibold">{orderId}</code> · {customer.name}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Link
            href="/orders"
            className="inline-flex items-center justify-center rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs font-semibold hover:bg-slate-50 hover:border-slate-300 transition"
          >
            Back to Orders
          </Link>
        </div>
      </div>

      {actionError && (
        <div className="mt-6 rounded-xl border border-red-200 bg-red-50 p-4 text-xs text-red-800 flex items-center justify-between">
          <span>{actionError}</span>
          <button onClick={() => setActionError(null)} className="font-bold text-red-600 hover:text-red-800">Dismiss</button>
        </div>
      )}

      {actionSuccess && (
        <div className="mt-6 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-xs text-emerald-800 flex items-center justify-between">
          <span>{actionSuccess}</span>
          <button onClick={() => setActionSuccess(null)} className="font-bold text-emerald-600 hover:text-emerald-800">Dismiss</button>
        </div>
      )}

      <div className="mt-8 space-y-6">
        {/* Carrier Header Card */}
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-2xs">
          <div className="grid grid-cols-2 gap-y-4 sm:grid-cols-4 sm:gap-x-4 text-xs">
            <div>
              <p className="text-slate-400 font-medium uppercase tracking-wider text-[10px]">Carrier</p>
              <p className="mt-1 font-semibold text-slate-800">{tracking.carrier}</p>
            </div>
            <div>
              <p className="text-slate-400 font-medium uppercase tracking-wider text-[10px]">Tracking Number</p>
              <p className="mt-1 font-mono font-semibold text-slate-800">{tracking.tracking_number}</p>
            </div>
            <div>
              <p className="text-slate-400 font-medium uppercase tracking-wider text-[10px]">Est. Delivery</p>
              <p className="mt-1 font-semibold text-slate-800">{tracking.estimated_delivery}</p>
            </div>
            <div>
              <p className="text-slate-400 font-medium uppercase tracking-wider text-[10px]">Current Status</p>
              <span className={`mt-1 inline-block font-semibold capitalize ${
                tracking.status === "delivered" ? "text-emerald-700" :
                tracking.status === "cancelled" ? "text-rose-700" : "text-indigo-600"
              }`}>
                {tracking.status.replace("_", " ")}
              </span>
            </div>
          </div>
        </div>

        {/* Visual Timeline Section */}
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-2xs">
          <h2 className="text-sm font-semibold text-slate-900 border-b border-slate-100 pb-3 mb-6">Delivery Timeline</h2>
          <div className="relative pl-8 space-y-8 before:absolute before:left-[11px] before:top-2 before:bottom-2 before:w-[2px] before:bg-slate-100">
            {tracking.timeline.map((event, idx) => {
              const formattedTime = event.timestamp
                ? new Date(event.timestamp).toLocaleTimeString("en-IN", {
                    hour: "numeric",
                    minute: "2-digit",
                  }) + ` · ` + new Date(event.timestamp).toLocaleDateString("en-IN", {
                    day: "numeric",
                    month: "short",
                  })
                : "Pending";

              return (
                <div key={idx} className="relative group">
                  <span
                    className={`absolute -left-8 top-1 flex h-6 w-6 items-center justify-center rounded-full border-2 bg-white text-[10px] font-bold ${
                      event.completed
                        ? "border-emerald-500 text-emerald-600 shadow-xs"
                        : "border-slate-200 text-slate-400"
                    }`}
                  >
                    {event.completed ? "✓" : idx + 1}
                  </span>
                  <div>
                    <div className="flex items-center justify-between">
                      <h3
                        className={`text-xs font-semibold ${
                          event.completed ? "text-slate-900" : "text-slate-400"
                        }`}
                      >
                        {event.label}
                      </h3>
                      <span className="text-[10px] text-slate-400">{formattedTime}</span>
                    </div>
                    <p className="mt-0.5 text-xs text-slate-500 capitalize">Stage: {event.status.replace("_", " ")}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Order Items Preview */}
        {orderDetails && orderDetails.items && (
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-2xs">
            <h2 className="text-sm font-semibold text-slate-900 border-b border-slate-100 pb-3 mb-4">Items in Package</h2>
            <div className="divide-y divide-slate-100">
              {orderDetails.items.map((item, idx) => (
                <div key={idx} className="flex justify-between py-2 text-xs">
                  <div>
                    <p className="font-semibold text-slate-800">{item.name}</p>
                    <p className="text-[10px] text-slate-400">Qty: {item.quantity} · SKU: {item.sku}</p>
                  </div>
                  <span className="font-semibold text-slate-800">₹{item.line_total}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Order Lifecycle Actions */}
        <div className="rounded-2xl border border-slate-200 bg-slate-50/50 p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-xs font-semibold text-slate-900">Order Management</h3>
              <p className="text-[11px] text-slate-500">Advance fulfillment states, cancel, or initiate returns</p>
            </div>
            {tracking.status !== "delivered" && tracking.status !== "cancelled" && (
              <button
                type="button"
                onClick={handleAdvanceStatus}
                disabled={actionLoading}
                className="rounded-xl bg-indigo-600 px-3 py-2 text-xs font-semibold text-white hover:bg-indigo-700 transition shadow-xs disabled:opacity-50"
              >
                {actionLoading ? "Updating..." : "Advance Status (Demo)"}
              </button>
            )}
          </div>

          <div className="flex flex-wrap gap-3 pt-2">
            {(tracking.status === "placed" || tracking.status === "confirmed" || tracking.status === "packed") && (
              <button
                type="button"
                onClick={handleCancelOrder}
                disabled={actionLoading}
                className="rounded-xl border border-rose-200 bg-rose-50/60 px-3 py-2 text-xs font-semibold text-rose-700 hover:bg-rose-100 transition disabled:opacity-50"
              >
                Cancel Order &amp; Refund
              </button>
            )}

            {tracking.status === "delivered" && (
              <button
                type="button"
                onClick={() => setShowReturnForm((prev) => !prev)}
                className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 transition"
              >
                {showReturnForm ? "Close Return Form" : "Request Return"}
              </button>
            )}
          </div>

          {/* Interactive Return Form Modal/Panel */}
          {showReturnForm && (
            <div className="mt-4 rounded-xl border border-slate-200 bg-white p-4 space-y-3">
              <h4 className="text-xs font-semibold text-slate-900">Select Item for Return</h4>
              <div className="space-y-2">
                <div>
                  <label className="block text-[10px] text-slate-500 font-medium">Product</label>
                  <select
                    value={selectedProductId}
                    onChange={(e) => setSelectedProductId(e.target.value)}
                    className="mt-1 block w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-800"
                  >
                    {orderDetails?.items.map((item) => (
                      <option key={item.product_id} value={item.product_id}>
                        {item.name} (Qty: {item.quantity})
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-[10px] text-slate-500 font-medium">Return Reason</label>
                  <select
                    value={returnReason}
                    onChange={(e) => setReturnReason(e.target.value)}
                    className="mt-1 block w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-800"
                  >
                    <option value="Defective/broken item">Defective or damaged product</option>
                    <option value="Incorrect size/fit">Incorrect size or fit</option>
                    <option value="Item not as described">Item did not match description</option>
                    <option value="Changed mind">Customer changed mind</option>
                  </select>
                </div>
                <div className="flex justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setShowReturnForm(false)}
                    className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={handleReturnItem}
                    disabled={actionLoading}
                    className="rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
                  >
                    {actionLoading ? "Submitting..." : "Submit Return"}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
