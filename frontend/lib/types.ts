export type HealthResponse = {
  status: string;
  timestamp: string;
};

export type CatalogProduct = {
  product_id: string;
  name: string;
  category: string;
  subcategory: string;
  description: string;
  brand: string;
  price: {
    amount: number;
    currency: string;
  };
  availability: {
    in_stock: boolean;
    quantity: number;
  };
  rating: {
    score: number;
    reviews: number;
  };
  features: string[];
  offers: Array<{
    offer_id: string;
    title: string;
    type: string;
    discount_percent: number;
  }>;
  image_url?: string;
  shipping?: {
    free_shipping: boolean;
    estimated_days: number;
  };
  return_policy?: {
    days: number;
    eligible: boolean;
  };
  recommended_with?: string[];
  better_alternative?: string | null;
};

export type ProductSearchResponse = {
  items: CatalogProduct[];
  total: number;
};

export type CategoriesResponse = {
  categories: string[];
};

export type AppliedOffer = {
  offer_id: string;
  name: string;
  discount_type: string;
  discount_amount_inr: number;
  reason: string;
};

export type CartItem = {
  product_id: string;
  sku: string;
  name: string;
  unit_price_inr: number;
  quantity: number;
  line_total_inr: number;
  available: boolean;
  inventory_checked: boolean;
};

export type Cart = {
  cart_id: string;
  merchant_id: string;
  customer_id: string;
  currency: string;
  items: CartItem[];
  subtotal_inr: number;
  discount_inr: number;
  shipping_inr: number;
  total_inr: number;
  applied_offers: AppliedOffer[];
  status: string;
  created_at: string;
  updated_at: string;
};

export type OrderItem = {
  product_id: string;
  sku: string;
  name: string;
  quantity: number;
  unit_price: number;
  line_total: number;
};

export type Order = {
  order_id: string;
  cart_id: string;
  customer_id: string;
  merchant_id: string;
  currency: string;
  items: OrderItem[];
  subtotal: number;
  discount: number;
  shipping: number;
  total: number;
  status: string;
  payment_status: string;
  payment_id?: string | null;
  payment_method?: string | null;
  transaction_reference?: string | null;
  created_at: string;
  updated_at: string;
  confirmed_at?: string | null;
  packed_at?: string | null;
  shipped_at?: string | null;
  delivered_at?: string | null;
  cancelled_at?: string | null;
};

export type TrackingTimelineEvent = {
  status: string;
  timestamp: string | null;
  label: string;
  completed: boolean;
};

export type TrackingInfo = {
  order_id: string;
  status: string;
  estimated_delivery: string;
  tracking_number: string;
  carrier: string;
  timeline: TrackingTimelineEvent[];
};

export type ReturnItem = {
  product_id: string;
  quantity: number;
  reason?: string | null;
};

export type ReturnRequest = {
  return_id: string;
  order_id: string;
  customer_id: string;
  status: string;
  items: ReturnItem[];
  created_at: string;
  updated_at: string;
};

