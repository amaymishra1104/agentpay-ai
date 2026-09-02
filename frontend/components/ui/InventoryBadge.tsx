"use client";

import React from "react";
import { AvailabilityInfo, formatInventoryStatus } from "../../lib/inventory";
import { AlertCircle, CheckCircle2, XCircle } from "lucide-react";

interface InventoryBadgeProps {
  availability?: AvailabilityInfo | null;
  size?: "xs" | "sm" | "md";
  showIcon?: boolean;
  className?: string;
}

export function InventoryBadge({
  availability,
  size = "sm",
  showIcon = true,
  className = "",
}: InventoryBadgeProps) {
  const status = formatInventoryStatus(availability);

  const sizeClasses = {
    xs: "text-[10px] px-2 py-0.5 rounded-md gap-1",
    sm: "text-xs px-2.5 py-0.5 rounded-lg gap-1.5",
    md: "text-sm px-3 py-1 rounded-xl gap-2",
  };

  const iconSize = size === "xs" ? 10 : size === "sm" ? 12 : 14;

  return (
    <span
      className={`inline-flex items-center font-medium border transition-colors ${
        sizeClasses[size]
      } ${status.badgeClass} ${className}`}
      title={status.text}
    >
      {showIcon && (
        <>
          {status.isOutOfStock ? (
            <XCircle size={iconSize} className="shrink-0 text-rose-600" />
          ) : status.isLowStock ? (
            <AlertCircle size={iconSize} className="shrink-0 text-amber-700" />
          ) : (
            <CheckCircle2 size={iconSize} className="shrink-0 text-emerald-600" />
          )}
        </>
      )}
      <span>{status.text}</span>
    </span>
  );
}
