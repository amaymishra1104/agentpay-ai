"use client";

import { useEffect, useState, use, useCallback } from "react";
import Link from "next/link";
import { API_BASE_URL, DEFAULT_CUSTOMER_ID } from "../../../lib/api";
import type { TrackingInfo, Order } from "../../../lib/types";

const CUSTOMER_ID = DEFAULT_CUSTOMER_ID;

export default function TrackingPage({ params }: { params: Promise<{ orderId: string }> }) {
  const resolvedParams = use(params);
  const orderId = resolvedParams.orderId;

  const [tracking, setTracking] = useState<TrackingInfo | null>(null);
  const [orderDetails, setOrderDetails] = useState<Order | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [actionLoading, setActionLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // Return form states
  const [selectedProductId, setSelectedProductId] = useState<string>("");
  const [returnReason, setReturnReason] = useState<string>("Defective/broken item");
  const [showReturnForm, setShowReturnForm] = useState(false);

  const fetchTrackingAndOrder = useCallback(async () => {
    try {
      // 1. Fetch tracking timeline
      const trackRes = await fetch(
        `${API_BASE_URL}/checkout/order/${orderId}/tracking?customer_id=${CUSTOMER_ID}`
      );
      if (!trackRes.ok) {
        if (trackRes.status === 403) {
          throw new Error("Access Denied: You do not own this order.");
        }
        throw new Error("Order tracking details not found.");
      }
      const trackData = await trackRes.json();
      setTracking(trackData);

      // 2. Fetch order items/total
      const orderRes = await fetch(
        `${API_BASE_URL}/checkout/order/${orderId}?customer_id=${CUSTOMER_ID}`
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
  }, [orderId]);

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
        body: JSON.stringify({ customer_id: CUSTOMER_ID }),
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
          customer_id: CUSTOMER_ID,
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
      <main className="mx-auto max-w-xl px-6 py-16 text-center">
        <div className="rounded-xl bg-red-50 border border-red-200 p-6 text-sm text-red-800">
          {error || "Order tracking details not found."}
        </div>
        <div className="mt-8">
          <Link href="/orders" className="text-sm font-semibold text-indigo-600 hover:text-indigo-500">
            Back to your orders &rarr;
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto w-full max-w-2xl px-6 py-12">
      <div className="flex items-center justify-between border-b border-slate-100 pb-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">Track Shipment</h1>
          <p className="mt-1 text-xs text-slate-500">Carrier details & fulfillment steps</p>
        </div>
        <Link
          href="/orders"
          className="inline-flex items-center justify-center rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs font-semibold hover:bg-slate-50 hover:border-slate-300 transition"
        >
          Back to Orders
        </Link>
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
                <div key={idx} className="relative text-xs">
                  {/* Timeline indicator node */}
                  <div className={`absolute left-[-27px] top-1.5 h-3.5 w-3.5 rounded-full border-2 bg-white transition ${
                    event.completed
                      ? event.status === "cancelled"
                        ? "border-rose-600 bg-rose-50"
                        : "border-emerald-600 bg-emerald-50"
                      : "border-slate-300"
                  }`} />
                  
                  <div className="flex items-start justify-between">
                    <div>
                      <p className={`font-semibold ${event.completed ? "text-slate-900" : "text-slate-400"}`}>
                        {event.label}
                      </p>
                      <p className="text-[10px] text-slate-400 mt-0.5">{formattedTime}</p>
                    </div>
                    {event.completed && (
                      <span className={`text-[10px] font-bold ${
                        event.status === "cancelled" ? "text-rose-600" : "text-emerald-600"
                      }`}>
                        {event.status === "cancelled" ? "Cancelled" : "Completed ✓"}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Order Items Summary */}
        {orderDetails && (
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-2xs">
            <h2 className="text-sm font-semibold text-slate-900 border-b border-slate-100 pb-3 mb-4">Items Shipped</h2>
            <ul className="divide-y divide-slate-100 text-xs">
              {orderDetails.items.map((item, idx) => (
                <li key={idx} className="flex justify-between py-2.5 first:pt-0 last:pb-0">
                  <span className="text-slate-700">{item.name} <span className="text-slate-400">x{item.quantity}</span></span>
                  <span className="font-semibold text-slate-900">₹{item.line_total.toLocaleString("en-IN")}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Sandbox Debug Console Panel */}
        <div className="rounded-2xl border border-amber-200 bg-amber-50/50 p-6 shadow-2xs">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-base">🛠️</span>
            <h3 className="text-sm font-bold text-amber-800">Sandbox Control Center</h3>
          </div>
          <p className="text-[11px] text-amber-700 leading-relaxed mb-5">
            DEMO ONLY: Use these options to simulate package transitions or submit cancels/returns.
          </p>

          <div className="flex flex-wrap gap-3">
            <button
              onClick={handleAdvanceStatus}
              disabled={actionLoading || tracking.status === "delivered" || tracking.status === "cancelled"}
              className="rounded-xl bg-amber-600 hover:bg-amber-700 text-white px-4 py-2.5 text-xs font-semibold shadow-xs transition disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {actionLoading ? "Processing..." : "Advance Status ➔"}
            </button>

            <button
              onClick={handleCancelOrder}
              disabled={actionLoading || !["placed", "confirmed", "packed"].includes(tracking.status)}
              className="rounded-xl bg-white hover:bg-rose-50 border border-rose-200 text-rose-700 px-4 py-2.5 text-xs font-semibold shadow-2xs transition disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Cancel Order ✖
            </button>

            {tracking.status === "delivered" && (
              <button
                onClick={() => setShowReturnForm(!showReturnForm)}
                className="rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2.5 text-xs font-semibold shadow-xs transition"
              >
                Request Return ↺
              </button>
            )}
          </div>

          {showReturnForm && orderDetails && (
            <div className="mt-5 border-t border-amber-200 pt-5 space-y-4 text-xs">
              <h4 className="font-bold text-slate-800">Select Item to Return</h4>
              <div>
                <label className="block text-slate-500 font-medium mb-1">Product</label>
                <select
                  value={selectedProductId}
                  onChange={(e) => setSelectedProductId(e.target.value)}
                  className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 outline-hidden text-xs"
                >
                  {orderDetails.items.map((item) => (
                    <option key={item.product_id} value={item.product_id}>
                      {item.name} (x{item.quantity})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-slate-500 font-medium mb-1">Reason for Return</label>
                <select
                  value={returnReason}
                  onChange={(e) => setReturnReason(e.target.value)}
                  className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 outline-hidden text-xs"
                >
                  <option value="Defective/broken item">Defective/broken item</option>
                  <option value="Incorrect item received">Incorrect item received</option>
                  <option value="Size/Fit issue">Size/Fit issue</option>
                  <option value="No longer needed">No longer needed</option>
                </select>
              </div>

              <div className="flex gap-3">
                <button
                  onClick={handleReturnItem}
                  disabled={actionLoading}
                  className="rounded-xl bg-slate-900 hover:bg-slate-800 text-white px-4 py-2 text-xs font-semibold"
                >
                  Confirm Return
                </button>
                <button
                  onClick={() => setShowReturnForm(false)}
                  className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs font-semibold"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
