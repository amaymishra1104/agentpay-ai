"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Sparkles,
  Bot,
  Package,
  ShoppingCart,
  Receipt,
  Store,
  Activity,
  Menu,
  X,
} from "lucide-react";
import { CustomerSwitcher } from "./CustomerSwitcher";

interface NavItem {
  label: string;
  href: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
}

const NAV_ITEMS: NavItem[] = [
  { label: "Overview", href: "/", icon: Sparkles },
  { label: "AI Buyer", href: "/buyer", icon: Bot },
  { label: "Catalog", href: "/catalog", icon: Package },
  { label: "Cart", href: "/cart", icon: ShoppingCart },
  { label: "Orders", href: "/orders", icon: Receipt },
  { label: "Merchant", href: "/merchant", icon: Store },
  { label: "Audit & Security", href: "/audit", icon: Activity },
];

export function Navbar() {
  const pathname = usePathname();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  };

  return (
    <header className="sticky top-0 z-40 border-b border-slate-200/80 bg-white/95 backdrop-blur-md transition-all">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6">
        {/* Brand & Logo */}
        <div className="flex items-center gap-6">
          <Link href="/" className="flex items-center gap-2.5 group">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-950 text-white shadow-xs transition group-hover:bg-indigo-600">
              <Sparkles size={18} />
            </div>
            <div>
              <div className="text-sm font-bold tracking-tight text-slate-900 group-hover:text-indigo-600 transition">
                AgentPay
              </div>
              <div className="text-[10px] font-medium text-slate-500 hidden sm:block">
                AI Agentic Commerce
              </div>
            </div>
          </Link>

          {/* Desktop Navigation Links */}
          <nav className="hidden md:flex items-center gap-1">
            {NAV_ITEMS.map((item) => {
              const active = isActive(item.href);
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-semibold transition ${
                    active
                      ? "bg-slate-900 text-white shadow-2xs"
                      : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                  }`}
                >
                  <Icon size={14} className={active ? "text-white" : "text-slate-400"} />
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>

        {/* Right Action Area */}
        <div className="flex items-center gap-2.5">
          <CustomerSwitcher />

          {/* Mobile Menu Toggle Button */}
          <button
            type="button"
            onClick={() => setMobileMenuOpen((prev) => !prev)}
            className="flex h-9 w-9 items-center justify-center rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50 md:hidden"
            aria-label="Toggle navigation menu"
          >
            {mobileMenuOpen ? <X size={18} /> : <Menu size={18} />}
          </button>
        </div>
      </div>

      {/* Mobile Drawer Menu */}
      {mobileMenuOpen && (
        <div className="border-t border-slate-100 bg-white px-4 py-3 md:hidden animate-in slide-in-from-top duration-150 shadow-lg">
          <nav className="flex flex-col gap-1">
            {NAV_ITEMS.map((item) => {
              const active = isActive(item.href);
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setMobileMenuOpen(false)}
                  className={`flex items-center gap-2.5 rounded-xl px-3 py-2 text-xs font-semibold transition ${
                    active
                      ? "bg-slate-900 text-white font-bold"
                      : "text-slate-700 hover:bg-slate-100"
                  }`}
                >
                  <Icon size={16} className={active ? "text-white" : "text-slate-400"} />
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>
      )}
    </header>
  );
}
