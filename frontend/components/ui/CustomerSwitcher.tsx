"use client";

import React, { useState, useRef, useEffect } from "react";
import { useCustomer, DemoCustomer } from "../../lib/customer";
import { Check, ChevronDown, Shield } from "lucide-react";

export function CustomerSwitcher() {
  const { customer, customerId, setCustomerId, availableCustomers } = useCustomer();
  const [open, setOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div className="relative inline-block text-left" ref={dropdownRef}>
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="group flex items-center gap-2 rounded-xl border border-slate-200 bg-white/95 px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm transition hover:border-slate-300 hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-slate-900/10"
        aria-expanded={open}
        aria-haspopup="true"
        title={`Active Demo Customer: ${customer.name} (${customer.id})`}
      >
        <div className="flex h-5 w-5 items-center justify-center rounded-full bg-slate-900 text-[10px] font-bold text-white shadow-xs">
          {customer.name.slice(-1)}
        </div>
        <div className="flex flex-col items-start text-left">
          <div className="flex items-center gap-1.5">
            <span className="font-semibold text-slate-900">{customer.name}</span>
            <span className="rounded bg-slate-100 px-1 py-0.2 text-[9px] font-mono text-slate-500">
              {customer.id}
            </span>
          </div>
        </div>
        <ChevronDown
          size={13}
          className={`text-slate-400 transition-transform duration-150 ${
            open ? "rotate-180 text-slate-600" : ""
          }`}
        />
      </button>

      {open && (
        <div className="absolute right-0 z-50 mt-2 w-72 origin-top-right rounded-2xl border border-slate-200 bg-white p-2 shadow-xl ring-1 ring-black/5 focus:outline-none animate-in fade-in zoom-in-95 duration-100">
          <div className="border-b border-slate-100 px-3 py-2">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                Demo Customer Identity
              </span>
              <span className="inline-flex items-center gap-1 rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] font-medium text-indigo-700">
                <Shield size={10} />
                Authorization Isolation
              </span>
            </div>
            <p className="mt-1 text-[11px] leading-tight text-slate-500">
              Switch customer personas to demonstrate strict backend customer &amp; cart isolation.
            </p>
          </div>

          <div className="mt-1 space-y-1">
            {availableCustomers.map((cust: DemoCustomer) => {
              const isSelected = cust.id === customerId;
              return (
                <button
                  key={cust.id}
                  type="button"
                  onClick={() => {
                    setCustomerId(cust.id);
                    setOpen(false);
                  }}
                  className={`flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left text-xs transition ${
                    isSelected
                      ? "bg-slate-900 text-white font-medium shadow-xs"
                      : "text-slate-700 hover:bg-slate-100"
                  }`}
                >
                  <div className="flex items-center gap-2.5">
                    <div
                      className={`flex h-7 w-7 items-center justify-center rounded-lg text-xs font-bold ${
                        isSelected
                          ? "bg-white text-slate-900"
                          : "bg-slate-100 text-slate-700"
                      }`}
                    >
                      {cust.name.slice(-1)}
                    </div>
                    <div>
                      <div className="flex items-center gap-1.5">
                        <span className="font-semibold">{cust.name}</span>
                        <span
                          className={`rounded px-1 text-[9px] font-mono ${
                            isSelected
                              ? "bg-slate-800 text-slate-300"
                              : "bg-slate-100 text-slate-500"
                          }`}
                        >
                          {cust.id}
                        </span>
                      </div>
                      <p
                        className={`text-[10px] ${
                          isSelected ? "text-slate-300" : "text-slate-400"
                        }`}
                      >
                        {cust.badge} · {cust.email}
                      </p>
                    </div>
                  </div>
                  {isSelected && <Check size={14} className="text-emerald-400" />}
                </button>
              );
            })}
          </div>

          <div className="mt-2 border-t border-slate-100 px-3 py-2 text-[10px] text-slate-400 leading-snug">
            <span className="font-semibold text-slate-500">Note:</span> Customer A cannot view, modify, or checkout Customer B&apos;s cart or orders.
          </div>
        </div>
      )}
    </div>
  );
}
