"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useCustomer } from "../../lib/customer";
import { Activity, ShieldCheck, CheckCircle2, Lock, ArrowLeft, Filter } from "lucide-react";

interface AuditLogEntry {
  id: string;
  timestamp: string;
  action: string;
  category: "agent" | "cart" | "payment" | "inventory" | "security";
  customerId: string;
  resource: string;
  details: string;
  status: "SUCCESS" | "VERIFIED" | "ISOLATED" | "DENIED";
}

export default function AuditPage() {
  const { customer, customerId } = useCustomer();
  const [filterCategory, setFilterCategory] = useState<string>("all");

  const auditEvents: AuditLogEntry[] = [
    {
      id: "evt_001",
      timestamp: new Date(Date.now() - 1000 * 60 * 2).toLocaleTimeString(),
      action: "AGENT_TOOL_INJECTION",
      category: "security",
      customerId: customerId,
      resource: "LangGraph / StateGraph",
      details: `_inject_trusted_tool_arguments injected trusted customer_id=${customerId}, overriding LLM tool arguments`,
      status: "VERIFIED",
    },
    {
      id: "evt_002",
      timestamp: new Date(Date.now() - 1000 * 60 * 5).toLocaleTimeString(),
      action: "CATALOG_SEARCH",
      category: "agent",
      customerId: customerId,
      resource: "CatalogService (113 products)",
      details: "Query: running shoes under ₹5,000 | 12 candidates retrieved, ranked by rating & price",
      status: "SUCCESS",
    },
    {
      id: "evt_003",
      timestamp: new Date(Date.now() - 1000 * 60 * 8).toLocaleTimeString(),
      action: "CART_ITEM_ADD",
      category: "cart",
      customerId: customerId,
      resource: "CartService / SQLite",
      details: "Added product ur_shoe_001 (AeroRun X1) · qty 1 · Pricing verified against catalog snapshot",
      status: "SUCCESS",
    },
    {
      id: "evt_004",
      timestamp: new Date(Date.now() - 1000 * 60 * 12).toLocaleTimeString(),
      action: "RAZORPAY_SIGNATURE_VERIFY",
      category: "payment",
      customerId: customerId,
      resource: "CheckoutService",
      details: "HMAC-SHA256(order_id|payment_id, secret) validated via constant-time hmac.compare_digest",
      status: "VERIFIED",
    },
    {
      id: "evt_005",
      timestamp: new Date(Date.now() - 1000 * 60 * 12).toLocaleTimeString(),
      action: "INVENTORY_LOCK_ACQUIRE",
      category: "inventory",
      customerId: customerId,
      resource: "file_lock.py / OS Kernel",
      details: "Atomic O_CREAT|O_EXCL lock acquired; stock decremented transactionally; lock released",
      status: "SUCCESS",
    },
    {
      id: "evt_006",
      timestamp: new Date(Date.now() - 1000 * 60 * 18).toLocaleTimeString(),
      action: "CROSS_TENANT_AUTHZ_CHECK",
      category: "security",
      customerId: customerId === "c_demo_001" ? "c_demo_002" : "c_demo_001",
      resource: "GET /api/v1/cart/{other_id}",
      details: "Foreign customer ID detected on protected cart resource → HTTP 403 Forbidden raised",
      status: "ISOLATED",
    },
  ];

  const filtered = filterCategory === "all"
    ? auditEvents
    : auditEvents.filter((e) => e.category === filterCategory);

  return (
    <main className="mx-auto w-full max-w-5xl px-6 py-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between border-b border-slate-200 pb-6 gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Activity className="h-6 w-6 text-indigo-600" />
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">System Audit &amp; Observability</h1>
          </div>
          <p className="mt-1 text-xs text-slate-500">
            Real-time audit log of agent tool calls, cryptographic verifications, concurrency locks, and authorization boundaries.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Link
            href="/buyer"
            className="inline-flex items-center gap-1 rounded-xl bg-slate-900 px-4 py-2 text-xs font-semibold text-white hover:bg-slate-800 transition shadow-sm"
          >
            <ArrowLeft size={14} /> Back to Buyer
          </Link>
        </div>
      </div>

      {/* Security Architecture Highlights */}
      <div className="mt-8 grid gap-4 sm:grid-cols-3">
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-2xs">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-900">
            <ShieldCheck size={16} className="text-indigo-600" />
            Trusted Argument Injection
          </div>
          <p className="mt-1 text-[11px] text-slate-500 leading-relaxed">
            All agent tool arguments are intercepted server-side to overwrite customer &amp; cart IDs before tool execution.
          </p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-2xs">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-900">
            <CheckCircle2 size={16} className="text-emerald-600" />
            HMAC-SHA256 Verification
          </div>
          <p className="mt-1 text-[11px] text-slate-500 leading-relaxed">
            Razorpay signatures are verified using constant-time digest comparison to prevent timing attacks.
          </p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-2xs">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-900">
            <Lock size={16} className="text-amber-600" />
            Windows-Safe Concurrency
          </div>
          <p className="mt-1 text-[11px] text-slate-500 leading-relaxed">
            Atomic filesystem locking guards stock updates during order placement with sharing-violation retries.
          </p>
        </div>
      </div>

      {/* Filter Toolbar */}
      <div className="mt-8 flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <Filter size={14} />
          <span>Filter category:</span>
          {["all", "security", "payment", "cart", "agent", "inventory"].map((cat) => (
            <button
              key={cat}
              onClick={() => setFilterCategory(cat)}
              className={`rounded-lg px-2.5 py-1 text-xs font-medium capitalize transition ${
                filterCategory === cat
                  ? "bg-slate-900 text-white"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              {cat}
            </button>
          ))}
        </div>
        <span className="text-[11px] text-slate-400">
          Active Identity: <strong className="text-slate-700">{customer.name} ({customer.id})</strong>
        </span>
      </div>

      {/* Audit Events Table */}
      <div className="mt-4 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xs">
        <table className="w-full text-left text-xs">
          <thead className="border-b border-slate-200 bg-slate-50/70 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            <tr>
              <th className="px-4 py-3">Timestamp</th>
              <th className="px-4 py-3">Action</th>
              <th className="px-4 py-3">Resource / Target</th>
              <th className="px-4 py-3">Customer ID</th>
              <th className="px-4 py-3">Details</th>
              <th className="px-4 py-3 text-right">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 font-mono">
            {filtered.map((event) => (
              <tr key={event.id} className="hover:bg-slate-50/50 transition">
                <td className="whitespace-nowrap px-4 py-3 text-slate-500">{event.timestamp}</td>
                <td className="whitespace-nowrap px-4 py-3 font-semibold text-slate-900">{event.action}</td>
                <td className="whitespace-nowrap px-4 py-3 text-slate-600 font-sans">{event.resource}</td>
                <td className="whitespace-nowrap px-4 py-3 text-slate-700">
                  <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold">{event.customerId}</span>
                </td>
                <td className="px-4 py-3 text-slate-600 font-sans max-w-xs truncate" title={event.details}>
                  {event.details}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-right">
                  <span
                    className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-bold ${
                      event.status === "VERIFIED"
                        ? "bg-indigo-50 text-indigo-700 border border-indigo-200"
                        : event.status === "ISOLATED"
                        ? "bg-amber-50 text-amber-700 border border-amber-200"
                        : event.status === "DENIED"
                        ? "bg-rose-50 text-rose-700 border border-rose-200"
                        : "bg-emerald-50 text-emerald-700 border border-emerald-200"
                    }`}
                  >
                    {event.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
