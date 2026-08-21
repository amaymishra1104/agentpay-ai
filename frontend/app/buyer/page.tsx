"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  Bot,
  ChevronRight,
  Clock3,
  Minus,
  Package,
  Plus,
  Search,
  Send,
  ShoppingCart,
  Sparkles,
  Trash2,
  User,
  X,
} from "lucide-react";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

const CUSTOMER_ID = "demo-customer-001";
const SESSION_STORAGE_KEY = "agentpay_buyer_session_id";

function cartStorageKey(activeSessionId: string) {
  return `agentpay_cart_id:${activeSessionId}`;
}

type Product = {
  product_id: string;
  name: string;
  brand?: string;
  category?: string;
  description?: string;
  price?: {
    amount: number;
    currency: string;
  };
  rating?: {
    score: number;
    reviews: number;
  };
  availability?: {
    in_stock: boolean;
    quantity: number;
  };
  image_url?: string;
};

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  products?: Product[];
};

type AgentApiResponse = {
  session_id: string;
  response: string;
  tool_used?: string | null;
  tool_result?: {
    tool_name: string;
    result?: {
      items?: Product[];
      total?: number;
      [key: string]: unknown;
    };
  } | null;
  cart_id?: string | null;
};

type CartItem = {
  product_id: string;
  sku: string;
  name: string;
  unit_price_inr: number;
  quantity: number;
  line_total_inr: number;
  available: boolean;
  inventory_checked: boolean;
};

type AppliedOffer = {
  offer_id?: string;
  title?: string;
  type?: string;
  discount_percent?: number;
};

type Cart = {
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
  created_at?: string;
  updated_at?: string;
};

const starterPrompts = [
  "Find running shoes under ₹5,000",
  "Compare the best running shoes",
  "Build me a running kit under ₹7,000",
];

export default function BuyerPage() {
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string>("");

  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "Hi! I'm your AgentPay shopping agent. Tell me what you're looking for, your budget, or what you're trying to accomplish.",
    },
  ]);

  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(false);
  const [cartLoading, setCartLoading] = useState(false);
  const [cart, setCart] = useState<Cart | null>(null);
  const [cartOpen, setCartOpen] = useState(false);
  const [selectedProduct, setSelectedProduct] =
    useState<Product | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const cartCount = useMemo(() => {
    if (!cart) {
      return 0;
    }

    return cart.items.reduce(
      (total, item) => total + item.quantity,
      0,
    );
  }, [cart]);

  useEffect(() => {
    // Keep the conversation isolated to this browser tab.
    // The previous hard-coded session ID caused old agent conversations
    // to leak into new chats.
    let activeSessionId = window.sessionStorage.getItem(
      SESSION_STORAGE_KEY,
    );

    if (!activeSessionId) {
      activeSessionId = `buyer-${crypto.randomUUID()}`;
      window.sessionStorage.setItem(
        SESSION_STORAGE_KEY,
        activeSessionId,
      );
    }

    setSessionId(activeSessionId);
    void loadExistingCart(activeSessionId);
  }, []);

  async function loadExistingCart(activeSessionId: string) {
    const storedCartId = window.localStorage.getItem(
      cartStorageKey(activeSessionId),
    );

    if (!storedCartId) {
      return;
    }

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/cart/${storedCartId}`,
      );

      if (!response.ok) {
        window.localStorage.removeItem(cartStorageKey(activeSessionId));
        return;
      }

      const data: Cart = await response.json();
      setCart(data);
    } catch (error) {
      console.error("Failed to restore AgentPay cart:", error);
    }
  }

  async function refreshCart(cartId: string) {
    const response = await fetch(
      `${API_BASE_URL}/api/v1/cart/${cartId}`,
    );

    if (!response.ok) {
      throw new Error(
        `Unable to load cart (${response.status}).`,
      );
    }

    const updatedCart: Cart = await response.json();

    setCart(updatedCart);

    window.localStorage.setItem(
      cartStorageKey(sessionId),
      updatedCart.cart_id,
    );

    return updatedCart;
  }

  async function updateCartItem(
    productId: string,
    quantity: number,
  ) {
    if (!cart) {
      return;
    }

    if (quantity <= 0) {
      await removeCartItem(productId);
      return;
    }

    setCartLoading(true);
    setErrorMessage(null);

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/cart/${cart.cart_id}/items/${encodeURIComponent(productId)}`,
        {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            quantity,
          }),
        },
      );

      if (!response.ok) {
        const text = await response.text();

        throw new Error(
          `Unable to update cart item: ${text}`,
        );
      }

      const updatedCart: Cart = await response.json();
      setCart(updatedCart);
    } catch (error) {
      console.error("AgentPay cart update failed:", error);

      setErrorMessage(
        error instanceof Error
          ? error.message
          : "Unable to update the cart.",
      );
    } finally {
      setCartLoading(false);
    }
  }

  async function removeCartItem(productId: string) {
    if (!cart) {
      return;
    }

    setCartLoading(true);
    setErrorMessage(null);

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/cart/${cart.cart_id}/items/${encodeURIComponent(productId)}`,
        {
          method: "DELETE",
        },
      );

      if (!response.ok) {
        const text = await response.text();

        throw new Error(
          `Unable to remove cart item: ${text}`,
        );
      }

      const updatedCart: Cart = await response.json();
      setCart(updatedCart);
    } catch (error) {
      console.error("AgentPay remove-from-cart failed:", error);

      setErrorMessage(
        error instanceof Error
          ? error.message
          : "Unable to remove the item.",
      );
    } finally {
      setCartLoading(false);
    }
  }

  async function clearCart() {
    if (!cart) {
      return;
    }

    setCartLoading(true);
    setErrorMessage(null);

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/cart/${cart.cart_id}`,
        {
          method: "DELETE",
        },
      );

      if (!response.ok) {
        const text = await response.text();

        throw new Error(
          `Unable to clear cart: ${text}`,
        );
      }

      const updatedCart: Cart = await response.json();
      setCart(updatedCart);
    } catch (error) {
      console.error("AgentPay clear-cart failed:", error);

      setErrorMessage(
        error instanceof Error
          ? error.message
          : "Unable to clear the cart.",
      );
    } finally {
      setCartLoading(false);
    }
  }

  async function sendMessage(messageText?: string) {
    const text = (messageText ?? input).trim();

    if (!text || loading || !sessionId) {
      return;
    }

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: text,
    };

    setMessages((current) => [...current, userMessage]);
    setInput("");
    setLoading(true);
    setErrorMessage(null);

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/agent/chat`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            session_id: sessionId,
            customer_id: CUSTOMER_ID,
            message: text,
          }),
        },
      );

      if (!response.ok) {
        const errorText = await response.text();

        throw new Error(
          `Agent API returned ${response.status}: ${errorText}`,
        );
      }

      const data: AgentApiResponse = await response.json();

      const rawItems = data.tool_result?.result?.items;

      const returnedProducts: Product[] =
        Array.isArray(rawItems)
          ? rawItems.filter(
              (item): item is Product =>
                typeof item === "object" &&
                item !== null &&
                typeof (item as Product).product_id ===
                  "string" &&
                typeof (item as Product).name ===
                  "string",
            )
          : [];

      const shoeProducts = returnedProducts.filter(
        (product) => {
          const category =
            product.category?.toLowerCase() ?? "";

          return (
            category.includes("shoe") ||
            category.includes("footwear")
          );
        },
      );

      const displayProducts =
        shoeProducts.length > 0
          ? shoeProducts
          : returnedProducts;

      const assistantMessage: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        content:
          data.response ||
          "I couldn't find a useful answer for that request.",
        products:
          displayProducts.length > 0
            ? displayProducts
            : undefined,
      };

      setMessages((current) => [
        ...current,
        assistantMessage,
      ]);

      if (displayProducts.length > 0) {
        setProducts(displayProducts);
      }

      /*
       * If the agent itself created/updated a cart,
       * synchronize that server-side cart with the UI.
       */
      if (data.cart_id) {
        window.localStorage.setItem(
          cartStorageKey(sessionId),
          data.cart_id,
        );

        try {
          await refreshCart(data.cart_id);
        } catch (error) {
          console.error(
            "Agent returned a cart ID but cart refresh failed:",
            error,
          );
        }
      }
    } catch (error) {
      console.error(
        "AgentPay Buyer Agent request failed:",
        error,
      );

      setErrorMessage(
        error instanceof Error
          ? error.message
          : "Unable to reach the AgentPay backend.",
      );

      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content:
            "I couldn't complete that request right now. Please check that the AgentPay backend is running and try again.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();
    void sendMessage();
  }

  function handleAddToCart(product: Product) {
    void sendMessage(`Add ${product.name} to my cart`);
  }

  return (
    <main className="min-h-screen bg-[#f7f8fa] text-slate-950">
      {/* Top navigation */}
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-[1500px] items-center justify-between px-5 lg:px-8">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-950 text-white">
              <Sparkles size={18} />
            </div>

            <div>
              <div className="text-sm font-semibold tracking-tight">
                AgentPay
              </div>

              <div className="text-[11px] text-slate-500">
                Autonomous commerce agent
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="hidden items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700 sm:flex">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
              Agent online
            </div>

            <button
              type="button"
              onClick={() => {
                setCartOpen(true);
                if (cart?.cart_id) {
                  void refreshCart(cart.cart_id).catch(
                    (error) => {
                      console.error(
                        "Failed to refresh cart:",
                        error,
                      );
                    },
                  );
                }
              }}
              className="relative rounded-xl border border-slate-200 bg-white p-2.5 transition hover:bg-slate-50"
              aria-label="Open shopping cart"
            >
              <ShoppingCart size={18} />

              {cartCount > 0 && (
                <span className="absolute -right-1.5 -top-1.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-slate-950 px-1 text-[10px] font-semibold text-white">
                  {cartCount}
                </span>
              )}
            </button>

            <button
              type="button"
              className="hidden rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-medium sm:block"
            >
              Buyer
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-[1500px] grid-cols-1 lg:grid-cols-[minmax(0,1fr)_420px]">
        {/* Conversation */}
        <section className="flex min-h-[calc(100vh-64px)] flex-col border-r border-slate-200">
          <div className="flex-1 overflow-y-auto px-5 py-8 lg:px-12">
            <div className="mx-auto max-w-4xl">
              <div className="mb-10">
                <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 shadow-sm">
                  <Bot size={14} />
                  AI shopping agent
                </div>

                <h1 className="max-w-3xl text-3xl font-semibold tracking-tight sm:text-4xl">
                  Shop by telling the agent what you need.
                </h1>

                <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-500">
                  AgentPay searches your catalog, evaluates
                  options, manages your cart, and helps you
                  make a decision instead of forcing you
                  through dozens of filters.
                </p>
              </div>

              {errorMessage && (
                <div className="mb-5 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                  {errorMessage}
                </div>
              )}

              <div className="space-y-7">
                {messages.map((message) => (
                  <div
                    key={message.id}
                    className={`flex gap-3 ${
                      message.role === "user"
                        ? "justify-end"
                        : "justify-start"
                    }`}
                  >
                    {message.role === "assistant" && (
                      <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-slate-950 text-white">
                        <Bot size={16} />
                      </div>
                    )}

                    <div
                      className={`max-w-[min(720px,85%)] rounded-2xl px-4 py-3 text-sm leading-6 ${
                        message.role === "user"
                          ? "rounded-br-md bg-slate-950 text-white"
                          : "rounded-bl-md border border-slate-200 bg-white text-slate-700 shadow-sm"
                      }`}
                    >
                      {message.content}

                      {message.products &&
                        message.products.length > 0 && (
                          <div className="mt-4 grid gap-3 sm:grid-cols-2">
                            {message.products.map(
                              (product) => (
                                <ProductMiniCard
                                  key={product.product_id}
                                  product={product}
                                  onSelect={() =>
                                    setSelectedProduct(
                                      product,
                                    )
                                  }
                                  onAdd={() =>
                                    handleAddToCart(
                                      product,
                                    )
                                  }
                                />
                              ),
                            )}
                          </div>
                        )}
                    </div>

                    {message.role === "user" && (
                      <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-slate-200 text-slate-600">
                        <User size={15} />
                      </div>
                    )}
                  </div>
                ))}

                {loading && (
                  <div className="flex items-center gap-3">
                    <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-slate-950 text-white">
                      <Bot size={16} />
                    </div>

                    <div className="flex items-center gap-2 rounded-2xl rounded-bl-md border border-slate-200 bg-white px-4 py-3 shadow-sm">
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" />
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:120ms]" />
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:240ms]" />

                      <span className="ml-1 text-xs text-slate-400">
                        Agent is thinking
                      </span>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Composer */}
          <div className="border-t border-slate-200 bg-white px-5 py-5 lg:px-12">
            <div className="mx-auto max-w-4xl">
              {messages.length === 1 && (
                <div className="mb-3 flex gap-2 overflow-x-auto pb-1">
                  {starterPrompts.map((prompt) => (
                    <button
                      key={prompt}
                      type="button"
                      onClick={() =>
                        void sendMessage(prompt)
                      }
                      className="shrink-0 rounded-full border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-600 transition hover:border-slate-300 hover:bg-slate-50"
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              )}

              <form
                onSubmit={handleSubmit}
                className="flex items-center gap-3 rounded-2xl border border-slate-300 bg-white p-2 shadow-sm focus-within:border-slate-500"
              >
                <Search
                  className="ml-2 shrink-0 text-slate-400"
                  size={18}
                />

                <input
                  value={input}
                  onChange={(event) =>
                    setInput(event.target.value)
                  }
                  placeholder="Tell AgentPay what you're looking for..."
                  className="min-w-0 flex-1 bg-transparent px-1 py-2 text-sm outline-none placeholder:text-slate-400"
                />

                <button
                  type="submit"
                  disabled={!input.trim() || loading}
                  className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-slate-950 text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
                  aria-label="Send message"
                >
                  <Send size={16} />
                </button>
              </form>

              <div className="mt-2 flex items-center justify-center gap-1 text-[11px] text-slate-400">
                <Sparkles size={11} />
                AgentPay uses your request and available
                commerce tools to make recommendations.
              </div>
            </div>
          </div>
        </section>

        {/* Intelligence / product panel */}
        <aside className="hidden bg-white lg:block">
          <div className="sticky top-16 h-[calc(100vh-64px)] overflow-y-auto">
            <div className="border-b border-slate-200 px-6 py-5">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-sm font-semibold">
                    Agent workspace
                  </div>

                  <div className="mt-1 text-xs text-slate-500">
                    Live shopping context
                  </div>
                </div>

                <div className="rounded-xl bg-slate-100 p-2">
                  <Package
                    size={17}
                    className="text-slate-600"
                  />
                </div>
              </div>
            </div>

            <div className="space-y-6 p-6">
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white shadow-sm">
                    <Bot size={18} />
                  </div>

                  <div>
                    <div className="text-sm font-semibold">
                      Buyer Agent
                    </div>

                    <div className="mt-0.5 flex items-center gap-1.5 text-xs text-emerald-600">
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                      Ready to act
                    </div>
                  </div>
                </div>

                <div className="mt-4 grid grid-cols-2 gap-2">
                  <Stat
                    label="Products"
                    value={products.length.toString()}
                  />

                  <Stat
                    label="Cart items"
                    value={cartCount.toString()}
                  />
                </div>
              </div>

              <div>
                <div className="mb-3 flex items-center justify-between">
                  <div>
                    <h2 className="text-sm font-semibold">
                      Recommended
                    </h2>

                    <p className="mt-1 text-xs text-slate-500">
                      Products discovered by the agent
                    </p>
                  </div>

                  {products.length > 0 && (
                    <span className="rounded-full bg-slate-100 px-2 py-1 text-[10px] font-medium text-slate-500">
                      {products.length} found
                    </span>
                  )}
                </div>

                {products.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-slate-300 p-6 text-center">
                    <Package
                      size={22}
                      className="mx-auto text-slate-300"
                    />

                    <p className="mt-3 text-xs font-medium text-slate-600">
                      No products yet
                    </p>

                    <p className="mt-1 text-xs leading-5 text-slate-400">
                      Ask the agent to find something and the
                      results will appear here.
                    </p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {products.map((product) => (
                      <ProductPanelCard
                        key={product.product_id}
                        product={product}
                        onSelect={() =>
                          setSelectedProduct(product)
                        }
                        onAdd={() =>
                          handleAddToCart(product)
                        }
                      />
                    ))}
                  </div>
                )}
              </div>

              <div>
                <div className="mb-3 flex items-center gap-2">
                  <Clock3
                    size={15}
                    className="text-slate-400"
                  />

                  <h2 className="text-sm font-semibold">
                    Agent activity
                  </h2>
                </div>

                <div className="space-y-3">
                  <Activity
                    title="Understands your intent"
                    description="Natural language request"
                    active
                  />

                  <Activity
                    title="Searches catalog"
                    description="Available commerce tools"
                    active={products.length > 0}
                  />

                  <Activity
                    title="Evaluates options"
                    description="Price, rating & availability"
                    active={products.length > 0}
                  />

                  <Activity
                    title="Cart ready"
                    description="Real server-side cart"
                    active={cartCount > 0}
                  />
                </div>
              </div>
            </div>
          </div>
        </aside>
      </div>

      {/* Product detail drawer */}
      {selectedProduct && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/20">
          <button
            type="button"
            className="absolute inset-0 cursor-default"
            aria-label="Close product details"
            onClick={() => setSelectedProduct(null)}
          />

          <div className="relative h-full w-full max-w-md overflow-y-auto bg-white shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-200 px-6 py-5">
              <div className="text-sm font-semibold">
                Product details
              </div>

              <button
                type="button"
                onClick={() => setSelectedProduct(null)}
                className="rounded-xl p-2 transition hover:bg-slate-100"
                aria-label="Close product details"
              >
                <X size={18} />
              </button>
            </div>

            <div className="p-6">
              <div className="flex h-52 items-center justify-center rounded-2xl bg-slate-100">
                {selectedProduct.image_url ? (
                  <img
                    src={selectedProduct.image_url}
                    alt={selectedProduct.name}
                    className="h-full w-full rounded-2xl object-cover"
                  />
                ) : (
                  <Package
                    size={48}
                    className="text-slate-300"
                  />
                )}
              </div>

              <div className="mt-6">
                <div className="text-xs font-medium text-slate-400">
                  {selectedProduct.brand ?? "Product"}
                </div>

                <h2 className="mt-1 text-2xl font-semibold tracking-tight">
                  {selectedProduct.name}
                </h2>

                <p className="mt-3 text-sm leading-6 text-slate-500">
                  {selectedProduct.description}
                </p>

                {selectedProduct.price && (
                  <div className="mt-5 text-2xl font-semibold">
                    ₹
                    {selectedProduct.price.amount.toLocaleString(
                      "en-IN",
                    )}
                  </div>
                )}

                {selectedProduct.rating && (
                  <div className="mt-3 text-sm text-slate-600">
                    ★ {selectedProduct.rating.score} ·{" "}
                    {selectedProduct.rating.reviews.toLocaleString(
                      "en-IN",
                    )}{" "}
                    reviews
                  </div>
                )}

                {selectedProduct.availability && (
                  <div
                    className={`mt-3 text-sm font-medium ${
                      selectedProduct.availability.in_stock
                        ? "text-emerald-600"
                        : "text-red-500"
                    }`}
                  >
                    {selectedProduct.availability.in_stock
                      ? `${selectedProduct.availability.quantity} in stock`
                      : "Currently out of stock"}
                  </div>
                )}

                <button
                  type="button"
                  disabled={cartLoading}
                  onClick={() => {
                    void sendMessage(
                      `Add ${selectedProduct.name} to my cart`,
                    );
                    setSelectedProduct(null);
                  }}
                  className="mt-8 flex w-full items-center justify-center gap-2 rounded-xl bg-slate-950 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <ShoppingCart size={16} />
                  {cartLoading
                    ? "Adding..."
                    : "Add to cart"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Cart drawer */}
      {cartOpen && (
        <div className="fixed inset-0 z-[60] flex justify-end bg-black/30">
          <button
            type="button"
            className="absolute inset-0 cursor-default"
            aria-label="Close cart"
            onClick={() => setCartOpen(false)}
          />

          <aside className="relative flex h-full w-full max-w-md flex-col bg-white shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-200 px-6 py-5">
              <div>
                <div className="flex items-center gap-2">
                  <ShoppingCart size={18} />

                  <h2 className="text-sm font-semibold">
                    Your cart
                  </h2>
                </div>

                <p className="mt-1 text-xs text-slate-500">
                  {cartCount === 0
                    ? "Your cart is empty"
                    : `${cartCount} item${
                        cartCount === 1 ? "" : "s"
                      }`}
                </p>
              </div>

              <button
                type="button"
                onClick={() => setCartOpen(false)}
                className="rounded-xl p-2 transition hover:bg-slate-100"
                aria-label="Close cart"
              >
                <X size={18} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-6">
              {!cart || cart.items.length === 0 ? (
                <div className="flex h-full flex-col items-center justify-center text-center">
                  <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-slate-100">
                    <ShoppingCart
                      size={28}
                      className="text-slate-400"
                    />
                  </div>

                  <h3 className="mt-5 text-sm font-semibold">
                    Your cart is empty
                  </h3>

                  <p className="mt-2 max-w-xs text-xs leading-5 text-slate-500">
                    Ask AgentPay to find something you need,
                    then add products directly from the
                    recommendations.
                  </p>

                  <button
                    type="button"
                    onClick={() => setCartOpen(false)}
                    className="mt-5 rounded-xl bg-slate-950 px-4 py-2.5 text-xs font-semibold text-white hover:bg-slate-800"
                  >
                    Continue shopping
                  </button>
                </div>
              ) : (
                <div className="space-y-4">
                  {cart.items.map((item) => (
                    <div
                      key={item.product_id}
                      className="rounded-2xl border border-slate-200 p-4"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <h3 className="truncate text-sm font-semibold">
                            {item.name}
                          </h3>

                          <p className="mt-1 text-xs text-slate-500">
                            ₹
                            {item.unit_price_inr.toLocaleString(
                              "en-IN",
                            )}{" "}
                            each
                          </p>
                        </div>

                        <button
                          type="button"
                          onClick={() =>
                            void removeCartItem(
                              item.product_id,
                            )
                          }
                          disabled={cartLoading}
                          className="rounded-lg p-2 text-slate-400 transition hover:bg-red-50 hover:text-red-600 disabled:opacity-40"
                          aria-label={`Remove ${item.name}`}
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>

                      <div className="mt-4 flex items-center justify-between">
                        <div className="flex items-center rounded-xl border border-slate-200">
                          <button
                            type="button"
                            onClick={() =>
                              void updateCartItem(
                                item.product_id,
                                item.quantity - 1,
                              )
                            }
                            disabled={cartLoading}
                            className="p-2.5 hover:bg-slate-50 disabled:opacity-40"
                            aria-label="Decrease quantity"
                          >
                            <Minus size={14} />
                          </button>

                          <span className="min-w-10 text-center text-sm font-semibold">
                            {item.quantity}
                          </span>

                          <button
                            type="button"
                            onClick={() =>
                              void updateCartItem(
                                item.product_id,
                                item.quantity + 1,
                              )
                            }
                            disabled={cartLoading}
                            className="p-2.5 hover:bg-slate-50 disabled:opacity-40"
                            aria-label="Increase quantity"
                          >
                            <Plus size={14} />
                          </button>
                        </div>

                        <div className="text-sm font-semibold">
                          ₹
                          {item.line_total_inr.toLocaleString(
                            "en-IN",
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {cart && cart.items.length > 0 && (
              <div className="border-t border-slate-200 p-6">
                {cart.applied_offers &&
                  cart.applied_offers.length > 0 && (
                    <div className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 p-3">
                      <div className="text-xs font-semibold text-emerald-800">
                        Offers applied
                      </div>

                      {cart.applied_offers.map(
                        (offer, index) => (
                          <div
                            key={
                              offer.offer_id ??
                              `offer-${index}`
                            }
                            className="mt-1 text-xs text-emerald-700"
                          >
                            {offer.title ??
                              "Eligible offer"}
                            {offer.discount_percent
                              ? ` · ${offer.discount_percent}% off`
                              : ""}
                          </div>
                        ),
                      )}
                    </div>
                  )}

                <div className="space-y-2 text-sm">
                  <div className="flex justify-between text-slate-500">
                    <span>Subtotal</span>
                    <span>
                      ₹
                      {cart.subtotal_inr.toLocaleString(
                        "en-IN",
                      )}
                    </span>
                  </div>

                  <div className="flex justify-between text-slate-500">
                    <span>Discount</span>
                    <span className="text-emerald-600">
                      -₹
                      {cart.discount_inr.toLocaleString(
                        "en-IN",
                      )}
                    </span>
                  </div>

                  <div className="flex justify-between text-slate-500">
                    <span>Shipping</span>
                    <span>
                      ₹
                      {cart.shipping_inr.toLocaleString(
                        "en-IN",
                      )}
                    </span>
                  </div>

                  <div className="my-3 border-t border-slate-200" />

                  <div className="flex justify-between text-base font-semibold">
                    <span>Total</span>
                    <span>
                      ₹
                      {cart.total_inr.toLocaleString(
                        "en-IN",
                      )}
                    </span>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => void clearCart()}
                  disabled={cartLoading}
                  className="mt-4 w-full rounded-xl border border-slate-200 px-4 py-2.5 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-40"
                >
                  Clear cart
                </button>

                <button
                  type="button"
                  disabled
                  className="mt-2 w-full rounded-xl bg-slate-950 px-4 py-3 text-sm font-semibold text-white opacity-50"
                  title="Checkout will be implemented next"
                >
                  Checkout — coming next
                </button>
              </div>
            )}
          </aside>
        </div>
      )}
    </main>
  );
}

function ProductMiniCard({
  product,
  onSelect,
  onAdd,
}: {
  product: Product;
  onSelect: () => void;
  onAdd: () => void;
}) {
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-slate-50">
      <button
        type="button"
        onClick={onSelect}
        className="block w-full text-left transition hover:bg-white"
      >
        <div className="flex h-28 items-center justify-center bg-slate-100">
          {product.image_url ? (
            <img
              src={product.image_url}
              alt={product.name}
              className="h-full w-full object-cover"
            />
          ) : (
            <Package
              size={30}
              className="text-slate-300"
            />
          )}
        </div>

        <div className="p-3">
          <div className="text-[10px] font-medium text-slate-400">
            {product.brand}
          </div>

          <div className="mt-0.5 text-xs font-semibold text-slate-800">
            {product.name}
          </div>

          {product.price && (
            <div className="mt-2 text-sm font-semibold">
              ₹
              {product.price.amount.toLocaleString(
                "en-IN",
              )}
            </div>
          )}

          {product.rating && (
            <div className="mt-1 text-[11px] text-slate-500">
              ★ {product.rating.score} ·{" "}
              {product.rating.reviews.toLocaleString(
                "en-IN",
              )}{" "}
              reviews
            </div>
          )}
        </div>
      </button>

      <button
        type="button"
        onClick={onAdd}
        className="flex w-full items-center justify-center gap-1.5 border-t border-slate-200 px-3 py-2 text-[11px] font-semibold text-slate-700 hover:bg-white"
      >
        <ShoppingCart size={13} />
        Add
      </button>
    </div>
  );
}

function ProductPanelCard({
  product,
  onSelect,
  onAdd,
}: {
  product: Product;
  onSelect: () => void;
  onAdd: () => void;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-3 transition hover:border-slate-300 hover:shadow-sm">
      <div className="flex gap-3">
        <div className="flex h-20 w-20 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-slate-100">
          {product.image_url ? (
            <img
              src={product.image_url}
              alt={product.name}
              className="h-full w-full object-cover"
            />
          ) : (
            <Package
              size={26}
              className="text-slate-300"
            />
          )}
        </div>

        <div className="min-w-0 flex-1">
          <div className="text-[10px] font-medium text-slate-400">
            {product.brand}
          </div>

          <button
            type="button"
            onClick={onSelect}
            className="mt-0.5 block truncate text-left text-sm font-semibold hover:underline"
          >
            {product.name}
          </button>

          {product.price && (
            <div className="mt-1 text-sm font-semibold">
              ₹
              {product.price.amount.toLocaleString(
                "en-IN",
              )}
            </div>
          )}

          {product.rating && (
            <div className="mt-1 text-[11px] text-slate-500">
              ★ {product.rating.score} ·{" "}
              {product.rating.reviews.toLocaleString(
                "en-IN",
              )}{" "}
              reviews
            </div>
          )}
        </div>
      </div>

      <div className="mt-3 flex gap-2">
        <button
          type="button"
          onClick={onSelect}
          className="flex flex-1 items-center justify-center gap-1 rounded-xl border border-slate-200 px-3 py-2 text-xs font-medium hover:bg-slate-50"
        >
          View
          <ChevronRight size={13} />
        </button>

        <button
          type="button"
          onClick={onAdd}
          className="flex flex-1 items-center justify-center gap-1 rounded-xl bg-slate-950 px-3 py-2 text-xs font-semibold text-white hover:bg-slate-800"
        >
          <ShoppingCart size={13} />
          Add
        </button>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3">
      <div className="text-lg font-semibold">
        {value}
      </div>

      <div className="mt-0.5 text-[10px] text-slate-400">
        {label}
      </div>
    </div>
  );
}

function Activity({
  title,
  description,
  active,
}: {
  title: string;
  description: string;
  active: boolean;
}) {
  return (
    <div className="flex gap-3">
      <div
        className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full ${
          active ? "bg-emerald-50" : "bg-slate-100"
        }`}
      >
        <span
          className={`h-1.5 w-1.5 rounded-full ${
            active
              ? "bg-emerald-500"
              : "bg-slate-300"
          }`}
        />
      </div>

      <div>
        <div className="text-xs font-medium">
          {title}
        </div>

        <div className="mt-0.5 text-[11px] text-slate-400">
          {description}
        </div>
      </div>
    </div>
  );
}