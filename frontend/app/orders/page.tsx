"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Receipt } from "lucide-react";
import { API_BASE_URL, getStoredSessionToken } from "../../lib/api";
import { useCustomer } from "../../lib/customer";
import type { Order } from "../../lib/types";

export default function OrdersPage() {
  const { customer, customerId } = useCustomer();
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchOrders() {
      setLoading(true);
      setError(null);
      try {
        const token = getStoredSessionToken(customerId);
        const headers: Record<string, string> = {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        };
        const res = await fetch(`${API_BASE_URL}/checkout/orders`, { headers });
        if (!res.ok) {
          throw new Error("Failed to load order history.");
        }
        const data = await res.json();
        setOrders(data);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to load orders.";
        setError(message);
      } finally {
        setLoading(false);
      }
    }
    fetchOrders();
  }, [customerId]);

  return (
    <main className="mx-auto w-full max-w-4xl px-6 py-12">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between border-b border-slate-200 pb-6 gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">Your Orders</h1>
          <p className="mt-1 text-xs text-slate-500">
            Order history for <span className="font-semibold text-slate-700">{customer.name}</span> ({customer.id})
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Link
            href="/buyer"
            className="inline-flex items-center justify-center rounded-xl bg-slate-900 px-4 py-2 text-xs font-semibold text-white hover:bg-slate-800 transition shadow-sm"
          >
            Launch AI Buyer &rarr;
          </Link>
        </div>
      </div>

      {loading ? (
        <div className="py-16 text-center text-slate-500 text-sm">
          Loading order history for {customer.name}...
        </div>
      ) : error ? (
        <div className="mt-6 rounded-xl border border-red-100 bg-red-50/50 p-4 text-sm text-red-700">
          {error}
        </div>
      ) : orders.length === 0 ? (
        <div className="py-20 text-center bg-white rounded-3xl border border-slate-200 mt-8 p-8 shadow-2xs">
          <div className="flex h-12 w-12 mx-auto items-center justify-center rounded-2xl bg-slate-100 text-slate-500 mb-3">
            <Receipt size={22} />
          </div>
          <h3 className="text-sm font-semibold text-slate-900">No orders yet</h3>
          <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto leading-relaxed">
            Complete your first purchase through the AI Buyer or browse the catalog.
          </p>
          <Link
            href="/buyer"
            className="mt-5 inline-flex items-center gap-1.5 rounded-xl bg-slate-900 px-4 py-2 text-xs font-semibold text-white hover:bg-slate-800 transition shadow-xs"
          >
            Start shopping with AI Buyer &rarr;
          </Link>
        </div>
      ) : (
        <div className="mt-8 space-y-6">
          {orders.map((order) => {
            const formattedDate = new Date(order.created_at).toLocaleDateString("en-IN", {
              day: "numeric",
              month: "short",
              year: "numeric",
            });
            const itemCount = order.items.reduce((sum, item) => sum + item.quantity, 0);

            return (
              <div
                key={order.order_id}
                className="group relative overflow-hidden rounded-2xl border border-slate-200 bg-white transition hover:border-slate-300 hover:shadow-sm"
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 bg-slate-50/50 px-6 py-4">
                  <div className="grid grid-cols-2 gap-4 sm:flex sm:gap-8 text-xs text-slate-500">
                    <div>
                      <p className="font-medium text-slate-400 uppercase tracking-wider text-[10px]">Order Placed</p>
                      <p className="mt-0.5 font-semibold text-slate-700">{formattedDate}</p>
                    </div>
                    <div>
                      <p className="font-medium text-slate-400 uppercase tracking-wider text-[10px]">Total Paid</p>
                      <p className="mt-0.5 font-semibold text-slate-900">₹{order.total.toLocaleString("en-IN")}</p>
                    </div>
                    <div>
                      <p className="font-medium text-slate-400 uppercase tracking-wider text-[10px]">Status</p>
                      <span className={`mt-0.5 inline-block font-semibold capitalize ${
                        order.status === "delivered" ? "text-emerald-700" :
                        order.status === "cancelled" ? "text-rose-700" :
                        order.status === "returned" ? "text-amber-700" : "text-indigo-600"
                      }`}>
                        {order.status.replace("_", " ")}
                      </span>
                    </div>
                  </div>
                  <div>
                    <p className="text-slate-400 text-[10px] uppercase font-medium tracking-wider sm:text-right">Order ID</p>
                    <code className="font-mono text-xs text-slate-800 font-semibold">{order.order_id}</code>
                  </div>
                </div>

                <div className="p-6">
                  <ul className="divide-y divide-slate-100">
                    {order.items.map((item, idx) => (
                      <li key={idx} className="flex justify-between py-3 first:pt-0 last:pb-0 text-sm">
                        <div className="flex-1 min-w-0">
                          <p className="font-medium text-slate-900 truncate">{item.name}</p>
                          <p className="text-xs text-slate-500 mt-0.5">Quantity: {item.quantity} · Price: ₹{item.unit_price.toLocaleString("en-IN")}</p>
                        </div>
                        <span className="font-semibold text-slate-900 pl-4">₹{item.line_total.toLocaleString("en-IN")}</span>
                      </li>
                    ))}
                  </ul>

                  <div className="mt-6 pt-4 border-t border-slate-100 flex flex-wrap gap-4 items-center justify-between">
                    <span className="text-xs text-slate-400">Items Count: {itemCount}</span>
                    <div className="flex gap-3">
                      <Link
                        href={`/tracking/${order.order_id}`}
                        className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 hover:border-slate-300 transition"
                      >
                        Track Shipment
                      </Link>
                      <button
                        onClick={() => alert(JSON.stringify(order, null, 2))}
                        className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 hover:border-slate-300 transition"
                      >
                        View JSON
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </main>
  );
}
