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
