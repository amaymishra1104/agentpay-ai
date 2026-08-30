import React from "react";
import Link from "next/link";
import {
  Sparkles,
  Bot,
  ShoppingCart,
  ShieldCheck,
  Package,
  CreditCard,
  Lock,
  Activity,
  Layers,
  Search,
  Key,
} from "lucide-react";

export default function HomePage() {
  return (
    <main className="min-h-full pb-20">
      {/* Hero Section */}
      <section className="relative overflow-hidden border-b border-slate-200/80 bg-white pt-12 pb-16">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <div className="inline-flex items-center gap-2 rounded-full border border-indigo-100 bg-indigo-50/70 px-3.5 py-1 text-xs font-semibold text-indigo-700 mb-6">
            <Sparkles size={13} className="text-indigo-600" />
            Razorpay AI Buildathon 2026 · Track 1: AI Growth &amp; Agentic Commerce
          </div>

          <h1 className="text-4xl font-extrabold tracking-tight sm:text-5xl lg:text-6xl text-slate-950 leading-[1.12]">
            An AI agent that can <span className="text-indigo-600 underline decoration-indigo-200 underline-offset-8">actually complete a purchase</span>.
          </h1>

          <p className="mt-6 max-w-3xl text-base sm:text-lg text-slate-600 leading-relaxed font-normal">
            Search products, manage a persistent cart, complete a Razorpay test payment, verify the transaction cryptographically, safely reserve inventory, and track the resulting order — all through one agentic commerce flow.
          </p>

          <div className="mt-8 flex flex-wrap items-center gap-4">
            <Link
              href="/buyer"
              className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-6 py-3 text-sm font-semibold text-white shadow-md transition hover:bg-slate-800 hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-slate-900/20"
            >
              <Bot size={18} /> Try AI Buyer &rarr;
            </Link>
            <a
              href="#architecture"
              className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-slate-700 shadow-2xs transition hover:bg-slate-50 hover:border-slate-300"
            >
              <Layers size={16} /> Explore Architecture
            </a>
            <Link
              href="/catalog"
              className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-slate-700 shadow-2xs transition hover:bg-slate-50 hover:border-slate-300"
            >
              <Package size={16} /> Catalog (113 SKUs)
            </Link>
          </div>
        </div>
      </section>

      {/* Interactive Architecture Flow Stepper */}
      <section id="architecture" className="mx-auto max-w-6xl px-4 sm:px-6 pt-16">
        <div className="flex flex-col sm:flex-row sm:items-end justify-between mb-8 gap-4">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wider text-indigo-600 mb-1">
              End-to-End Execution Pipeline
            </div>
            <h2 className="text-2xl font-bold tracking-tight text-slate-950">
              The Agentic Commerce Lifecycle
            </h2>
          </div>
          <p className="text-xs text-slate-500 max-w-md leading-relaxed">
            Every customer action moves through deterministic server boundaries ensuring zero hallucinated identities and atomic inventory reservation.
          </p>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <div className="group rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs transition hover:border-slate-300 hover:shadow-sm">
            <div className="flex items-center justify-between">
              <span className="font-mono text-xs font-bold text-slate-400">01</span>
              <Bot size={18} className="text-indigo-600" />
            </div>
            <h3 className="mt-3 text-sm font-semibold text-slate-900">AI Buyer Discovery</h3>
            <p className="mt-1 text-xs text-slate-500 leading-relaxed">
              LangGraph-orchestrated natural language intent parsing across 113 products with budget and rating constraints.
            </p>
          </div>

          <div className="group rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs transition hover:border-slate-300 hover:shadow-sm">
            <div className="flex items-center justify-between">
              <span className="font-mono text-xs font-bold text-slate-400">02</span>
              <Search size={18} className="text-sky-600" />
            </div>
            <h3 className="mt-3 text-sm font-semibold text-slate-900">Product Search &amp; Refinement</h3>
            <p className="mt-1 text-xs text-slate-500 leading-relaxed">
              Multi-turn contextual comparison and pronoun resolution (e.g., &ldquo;Add the second one to cart&rdquo;).
            </p>
          </div>

          <div className="group rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs transition hover:border-slate-300 hover:shadow-sm">
            <div className="flex items-center justify-between">
              <span className="font-mono text-xs font-bold text-slate-400">03</span>
              <ShoppingCart size={18} className="text-emerald-600" />
            </div>
            <h3 className="mt-3 text-sm font-semibold text-slate-900">Persistent Cart State</h3>
            <p className="mt-1 text-xs text-slate-500 leading-relaxed">
              Customer-scoped session persistence across navigation (`Buyer ↔ Cart`), auto-applying rule-based volume discounts.
            </p>
          </div>

          <div className="group rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs transition hover:border-slate-300 hover:shadow-sm">
            <div className="flex items-center justify-between">
              <span className="font-mono text-xs font-bold text-slate-400">04</span>
              <CreditCard size={18} className="text-indigo-600" />
            </div>
            <h3 className="mt-3 text-sm font-semibold text-slate-900">Razorpay Test Mode</h3>
            <p className="mt-1 text-xs text-slate-500 leading-relaxed">
              Official Razorpay SDK modal integration generating real server-side payment orders in paise.
            </p>
          </div>

          <div className="group rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs transition hover:border-slate-300 hover:shadow-sm">
            <div className="flex items-center justify-between">
              <span className="font-mono text-xs font-bold text-slate-400">05</span>
              <Lock size={18} className="text-amber-600" />
            </div>
            <h3 className="mt-3 text-sm font-semibold text-slate-900">HMAC-SHA256 &amp; File Lock</h3>
            <p className="mt-1 text-xs text-slate-500 leading-relaxed">
              Constant-time `hmac.compare_digest` verification followed by atomic `O_CREAT|O_EXCL` cross-process inventory locking.
            </p>
          </div>

          <div className="group rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs transition hover:border-slate-300 hover:shadow-sm">
            <div className="flex items-center justify-between">
              <span className="font-mono text-xs font-bold text-slate-400">06</span>
              <Package size={18} className="text-purple-600" />
            </div>
            <h3 className="mt-3 text-sm font-semibold text-slate-900">Order Tracking &amp; Isolation</h3>
            <p className="mt-1 text-xs text-slate-500 leading-relaxed">
              Full fulfillment timeline with stage advancement and strict HTTP 403 authorization isolation across demo customers.
            </p>
          </div>
        </div>
      </section>

      {/* The Security Principle Section */}
      <section className="mx-auto max-w-6xl px-4 sm:px-6 pt-16">
        <div className="rounded-3xl border border-slate-200 bg-gradient-to-br from-white via-slate-50/60 to-indigo-50/30 p-8 sm:p-10 shadow-sm">
          <div className="inline-flex items-center gap-2 rounded-full border border-indigo-100 bg-white px-3 py-1 text-xs font-semibold text-indigo-700 mb-4 shadow-2xs">
            <ShieldCheck size={14} className="text-indigo-600" />
            Core Architectural Guarantee
          </div>

          <h2 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-950">
            The AI is not the authority.
          </h2>

          <p className="mt-3 max-w-2xl text-sm sm:text-base text-slate-600 leading-relaxed">
            The model can request an action, but it does not get to decide who owns the resource. The server intercepts every tool invocation and forcefully injects verified session identity before execution.
          </p>

          <div className="mt-8 grid gap-4 lg:grid-cols-4 font-mono text-xs">
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-2xs">
              <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1 font-sans">
                1. Untrusted Output
              </div>
              <div className="font-semibold text-slate-900">LLM Tool Call</div>
              <p className="mt-2 text-[11px] text-slate-500 font-sans leading-relaxed">
                Model proposes actions, but identity parameters are treated as untrusted user input.
              </p>
            </div>

            <div className="rounded-2xl border border-indigo-200 bg-indigo-50/50 p-4 shadow-2xs">
              <div className="text-[10px] font-bold uppercase tracking-wider text-indigo-700 mb-1 font-sans">
                2. Trust Boundary
              </div>
              <div className="font-semibold text-indigo-950">_inject_trusted_tool_arguments</div>
              <p className="mt-2 text-[11px] text-indigo-900/80 font-sans leading-relaxed">
                Server overwrites <code className="bg-indigo-100/80 px-1 py-0.5 rounded font-mono">customer_id</code> and <code className="bg-indigo-100/80 px-1 py-0.5 rounded font-mono">cart_id</code> with session values.
              </p>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-2xs">
              <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1 font-sans">
                3. Service AuthZ Check
              </div>
              <div className="font-semibold text-slate-900">Tenant Isolation</div>
              <p className="mt-2 text-[11px] text-slate-500 font-sans leading-relaxed">
                Backend routes query database ownership and reject mismatched IDs with <span className="font-bold text-amber-700">HTTP 403</span>.
              </p>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-2xs">
              <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1 font-sans">
                4. Transaction Execution
              </div>
              <div className="font-semibold text-slate-900">Protected Resource</div>
              <p className="mt-2 text-[11px] text-slate-500 font-sans leading-relaxed">
                Database mutation occurs only under verified customer ownership and atomic inventory lock.
              </p>
            </div>
          </div>

          <div className="mt-6 rounded-2xl bg-white/90 p-4 border border-slate-200/80 text-xs text-slate-600 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Key size={16} className="text-slate-700 shrink-0" />
              <span>
                <strong className="text-slate-900">Scope Clarity:</strong> Customer authorization and tenant isolation are fully implemented. Production authentication (OAuth/JWT) is out-of-scope; demo personas are used for buildathon evaluation.
              </span>
            </div>
            <Link
              href="/audit"
              className="font-semibold text-indigo-600 hover:text-indigo-500 shrink-0"
            >
              View Audit Log &rarr;
            </Link>
          </div>
        </div>
      </section>

      {/* Quick Navigation Cards */}
      <section className="mx-auto max-w-6xl px-4 sm:px-6 pt-16">
        <div className="grid gap-4 sm:grid-cols-4">
          <Link
            href="/buyer"
            className="rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs transition hover:border-slate-300 hover:shadow-sm"
          >
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-slate-900 text-white mb-2">
              <Bot size={16} />
            </div>
            <h3 className="text-sm font-semibold text-slate-900">AI Buyer</h3>
            <p className="mt-1 text-[11px] text-slate-500">Natural search &amp; chat cart</p>
          </Link>

          <Link
            href="/catalog"
            className="rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs transition hover:border-slate-300 hover:shadow-sm"
          >
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600 mb-2">
              <Package size={16} />
            </div>
            <h3 className="text-sm font-semibold text-slate-900">Catalog</h3>
            <p className="mt-1 text-[11px] text-slate-500">113 SKUs across 19 categories</p>
          </Link>

          <Link
            href="/cart"
            className="rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs transition hover:border-slate-300 hover:shadow-sm"
          >
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-emerald-50 text-emerald-600 mb-2">
              <ShoppingCart size={16} />
            </div>
            <h3 className="text-sm font-semibold text-slate-900">Cart &amp; Checkout</h3>
            <p className="mt-1 text-[11px] text-slate-500">Persistent cart &amp; Razorpay</p>
          </Link>

          <Link
            href="/audit"
            className="rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs transition hover:border-slate-300 hover:shadow-sm"
          >
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-amber-50 text-amber-600 mb-2">
              <Activity size={16} />
            </div>
            <h3 className="text-sm font-semibold text-slate-900">Audit &amp; Observability</h3>
            <p className="mt-1 text-[11px] text-slate-500">Security event stream</p>
          </Link>
        </div>
      </section>
    </main>
  );
}
