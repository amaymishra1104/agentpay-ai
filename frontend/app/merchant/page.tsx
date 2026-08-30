import React from "react";
import Link from "next/link";
import { Store, Package, ShieldCheck, ArrowLeft, Layers, Percent, Truck } from "lucide-react";

export default function MerchantPage() {
  return (
    <main className="mx-auto w-full max-w-5xl px-6 py-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between border-b border-slate-200 pb-6 gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Store className="h-6 w-6 text-slate-900" />
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">UrbanRun Merchant Workspace</h1>
          </div>
          <p className="mt-1 text-xs text-slate-500">
            Merchant profile, policy constraints, catalog configuration, and settlement status.
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

      {/* Metrics Grid */}
      <div className="mt-8 grid gap-4 sm:grid-cols-4">
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[10px] font-semibold uppercase tracking-wider">Merchant ID</span>
            <Store size={16} />
          </div>
          <p className="mt-2 text-lg font-mono font-bold text-slate-900">m_urbanrun</p>
          <p className="text-[11px] text-slate-500">UrbanRun Performance Apparel</p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[10px] font-semibold uppercase tracking-wider">Active Catalog</span>
            <Package size={16} />
          </div>
          <p className="mt-2 text-lg font-bold text-slate-900">113 SKUs</p>
          <p className="text-[11px] text-slate-500">Across 19 distinct categories</p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[10px] font-semibold uppercase tracking-wider">Active Offers</span>
            <Percent size={16} />
          </div>
          <p className="mt-2 text-lg font-bold text-slate-900">6 Promotions</p>
          <p className="text-[11px] text-slate-500">Rule-based coupon engine</p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[10px] font-semibold uppercase tracking-wider">Settlement Gateway</span>
            <ShieldCheck size={16} />
          </div>
          <p className="mt-2 text-lg font-bold text-slate-900">Razorpay</p>
          <p className="text-[11px] text-emerald-600 font-medium">Test Mode · Verified</p>
        </div>
      </div>

      {/* Policies Summary */}
      <div className="mt-8 rounded-2xl border border-slate-200 bg-white p-6 shadow-2xs">
        <h2 className="text-sm font-semibold text-slate-900 border-b border-slate-100 pb-3 mb-4">
          Merchant Policies &amp; Constraints
        </h2>
        <div className="grid gap-4 sm:grid-cols-3 text-xs">
          <div className="rounded-xl border border-slate-100 bg-slate-50/50 p-4">
            <div className="flex items-center gap-2 font-semibold text-slate-800">
              <Truck size={16} className="text-indigo-600" />
              Shipping Policy
            </div>
            <p className="mt-2 text-[11px] text-slate-600 leading-relaxed">
              Standard flat ₹99 shipping on orders below ₹1,499. Free shipping automatically applied on all carts ₹1,499 and above.
            </p>
          </div>

          <div className="rounded-xl border border-slate-100 bg-slate-50/50 p-4">
            <div className="flex items-center gap-2 font-semibold text-slate-800">
              <Layers size={16} className="text-emerald-600" />
              Return Window
            </div>
            <p className="mt-2 text-[11px] text-slate-600 leading-relaxed">
              30-day return policy on all unworn items with tags. Immediate refund simulation on verified delivered orders.
            </p>
          </div>

          <div className="rounded-xl border border-slate-100 bg-slate-50/50 p-4">
            <div className="flex items-center gap-2 font-semibold text-slate-800">
              <ShieldCheck size={16} className="text-amber-600" />
              Inventory Protection
            </div>
            <p className="mt-2 text-[11px] text-slate-600 leading-relaxed">
              Synchronized cross-process atomic file locking (<code className="font-mono">file_lock.py</code>) ensures strictly serialized inventory decrements.
            </p>
          </div>
        </div>
      </div>

      {/* Quick Navigation */}
      <div className="mt-8 flex gap-4">
        <Link
          href="/catalog"
          className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition"
        >
          Explore Catalog (113 SKUs) &rarr;
        </Link>
        <Link
          href="/audit"
          className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition"
        >
          View System Audit Logs &rarr;
        </Link>
      </div>
    </main>
  );
}
