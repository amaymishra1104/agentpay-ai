export interface AvailabilityInfo {
  in_stock?: boolean;
  quantity?: number;
}

export interface FormattedInventory {
  text: string;
  shortText: string;
  badgeClass: string;
  textClass: string;
  isOutOfStock: boolean;
  isLowStock: boolean;
  quantity?: number;
}

/**
 * Format server-authoritative inventory availability according to platform UX rules:
 * - quantity > 5: "In stock · X available"
 * - quantity between 2 and 5: "Only X left"
 * - quantity === 1: "Only 1 left"
 * - quantity === 0 or in_stock === false: "Out of stock"
 * - missing quantity but in_stock true: "In stock"
 * - missing availability: "Availability unavailable"
 */
export function formatInventoryStatus(
  availability?: AvailabilityInfo | null
): FormattedInventory {
  if (!availability) {
    return {
      text: "Availability unavailable",
      shortText: "Unavailable",
      badgeClass: "bg-slate-100 text-slate-600 border-slate-200",
      textClass: "text-slate-500",
      isOutOfStock: false,
      isLowStock: false,
    };
  }

  const { in_stock, quantity } = availability;

  // Out of stock
  if (in_stock === false || (quantity !== undefined && quantity !== null && quantity <= 0)) {
    return {
      text: "Out of stock",
      shortText: "Out of stock",
      badgeClass: "bg-rose-50 text-rose-700 border-rose-200/80 font-medium",
      textClass: "text-rose-600 font-medium",
      isOutOfStock: true,
      isLowStock: false,
      quantity: 0,
    };
  }

  // Exact quantity available
  if (quantity !== undefined && quantity !== null) {
    if (quantity === 1) {
      return {
        text: "Only 1 left",
        shortText: "Only 1 left",
        badgeClass: "bg-amber-50 text-amber-800 border-amber-300/80 font-semibold shadow-2xs animate-pulse",
        textClass: "text-amber-700 font-semibold",
        isOutOfStock: false,
        isLowStock: true,
        quantity: 1,
      };
    }

    if (quantity > 1 && quantity <= 5) {
      return {
        text: `Only ${quantity} left`,
        shortText: `${quantity} left`,
        badgeClass: "bg-amber-50 text-amber-800 border-amber-300/80 font-semibold shadow-2xs",
        textClass: "text-amber-700 font-semibold",
        isOutOfStock: false,
        isLowStock: true,
        quantity,
      };
    }

    return {
      text: `In stock · ${quantity} available`,
      shortText: `${quantity} in stock`,
      badgeClass: "bg-emerald-50 text-emerald-700 border-emerald-200/80 font-medium",
      textClass: "text-emerald-600 font-medium",
      isOutOfStock: false,
      isLowStock: false,
      quantity,
    };
  }

  // Fallback if in_stock boolean exists but quantity is omitted
  return {
    text: in_stock ? "In stock" : "Out of stock",
    shortText: in_stock ? "In stock" : "Out of stock",
    badgeClass: in_stock
      ? "bg-emerald-50 text-emerald-700 border-emerald-200/80 font-medium"
      : "bg-rose-50 text-rose-700 border-rose-200/80 font-medium",
    textClass: in_stock ? "text-emerald-600 font-medium" : "text-rose-600 font-medium",
    isOutOfStock: !in_stock,
    isLowStock: false,
  };
}
