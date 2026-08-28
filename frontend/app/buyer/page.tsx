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

import {
  API_BASE_URL,
  DEFAULT_CUSTOMER_ID,
  SESSION_STORAGE_KEY,
  CONVERSATION_STORAGE_KEY_PREFIX,
  getStoredCartId,
  setStoredCartId,
  clearStoredCartId,
} from "../../lib/api";

const CUSTOMER_ID = DEFAULT_CUSTOMER_ID;

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
  shipping?: {
    free_shipping: boolean;
    estimated_days: number;
  };
  return_policy?: {
    days: number;
    eligible: boolean;
  };
  offers?: {
    offer_id: string;
    title: string;
    type: string;
    discount_percent: number;
  }[];
  features?: string[];
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
  name?: string;
  discount_type?: string;
  discount_amount_inr?: number;
  reason?: string;
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
  "Find wireless headphones under ₹5,000",
  "Find a laptop for coding under ₹70,000",
  "Build me a fitness kit under ₹10,000",
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
  const [addingIds, setAddingIds] = useState<Record<string, boolean>>({});
  const [cardErrors, setCardErrors] = useState<Record<string, string>>({});

  const cartCount = useMemo(() => {
    if (!cart || cart.status === "checked_out") {
      return 0;
    }

    return cart.items.reduce(
      (total, item) => total + item.quantity,
      0,
    );
  }, [cart]);

  useEffect(() => {
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

    // 1. Immediately restore cached conversation from sessionStorage
    const cachedConversation = window.sessionStorage.getItem(
      `${CONVERSATION_STORAGE_KEY_PREFIX}${activeSessionId}`
    );
    if (cachedConversation) {
      try {
        const parsedMessages: Message[] = JSON.parse(cachedConversation);
        if (Array.isArray(parsedMessages) && parsedMessages.length > 0) {
          setMessages(parsedMessages);
          const lastWithProducts = [...parsedMessages].reverse().find(
            (m) => m.products && m.products.length > 0
          );
          if (lastWithProducts?.products) {
            setProducts(lastWithProducts.products);
          }
        }
      } catch (e) {
        console.error("Failed to parse cached conversation:", e);
      }
    }

    // 2. Load cart and synchronize from backend
    void loadExistingCart(activeSessionId);
    void restoreSessionFromBackend(activeSessionId);
  }, []);

  async function restoreSessionFromBackend(activeSessionId: string) {
    try {
      const res = await fetch(
        `${API_BASE_URL}/agent/sessions/${activeSessionId}?customer_id=${CUSTOMER_ID}`
      );
      if (!res.ok) return;
      const data = await res.json();
      if (data.cart_id && !getStoredCartId(activeSessionId)) {
        setStoredCartId(data.cart_id, activeSessionId);
        void loadExistingCart(activeSessionId);
      }

      // If sessionStorage was empty, reconstruct UI messages from backend history
      const cached = window.sessionStorage.getItem(
        `${CONVERSATION_STORAGE_KEY_PREFIX}${activeSessionId}`
      );
      if (!cached && data.messages && data.messages.length > 0) {
        const reconstructed: Message[] = [];
        let currentProducts: Product[] | undefined = undefined;

        for (const msg of data.messages) {
          if (msg.role === "user") {
            reconstructed.push({
              id: `user-${msg.id || msg.sequence}`,
              role: "user",
              content: msg.content,
            });
            currentProducts = undefined;
          } else if (msg.message_type === "tool_result") {
            try {
              const parsed = JSON.parse(msg.content);
              if (parsed && Array.isArray(parsed.items)) {
                currentProducts = parsed.items.filter(
                  (item: unknown): item is Product =>
                    typeof item === "object" && item !== null && typeof (item as Product).product_id === "string"
                );
              }
            } catch {}
          } else if (msg.role === "assistant" && (msg.message_type === "final" || msg.message_type === "text")) {
            reconstructed.push({
              id: `assistant-${msg.id || msg.sequence}`,
              role: "assistant",
              content: msg.content,
              products: currentProducts && currentProducts.length > 0 ? currentProducts : undefined,
            });
            if (currentProducts && currentProducts.length > 0) {
              setProducts(currentProducts);
            }
          }
        }

        if (reconstructed.length > 0) {
          setMessages(reconstructed);
          window.sessionStorage.setItem(
            `${CONVERSATION_STORAGE_KEY_PREFIX}${activeSessionId}`,
            JSON.stringify(reconstructed)
          );
        }
      }
    } catch (err) {
      console.error("Failed to restore session history from backend:", err);
    }
  }

  async function loadExistingCart(activeSessionId: string) {
    const storedCartId = getStoredCartId(activeSessionId);

    if (!storedCartId) {
      return;
    }

    try {
      const response = await fetch(
        `${API_BASE_URL}/cart/${storedCartId}?customer_id=${CUSTOMER_ID}`,
      );

      if (!response.ok) {
        if (response.status === 404) {
          clearStoredCartId(activeSessionId);
        }
        return;
      }

      const data: Cart = await response.json();
      if (data.status === "checked_out") {
        clearStoredCartId(activeSessionId);
        setCart(null);
        return;
      }
      setCart(data);
    } catch (error) {
      console.error("Failed to restore AgentPay cart:", error);
    }
  }

  async function refreshCart(cartId: string) {
    const response = await fetch(
      `${API_BASE_URL}/cart/${cartId}?customer_id=${CUSTOMER_ID}`,
    );

    if (!response.ok) {
      let errorMessage = `Unable to load cart (${response.status}).`;
      try {
        const errData = await response.json();
        if (errData && errData.detail) {
          errorMessage = typeof errData.detail === "string" ? errData.detail : JSON.stringify(errData.detail);
        }
      } catch {}
      throw new Error(errorMessage);
    }

    const updatedCart: Cart = await response.json();

    setCart(updatedCart);

    setStoredCartId(updatedCart.cart_id, sessionId);

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
        `${API_BASE_URL}/cart/${cart.cart_id}/items/${encodeURIComponent(productId)}?customer_id=${CUSTOMER_ID}`,
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
        let errorMessage = `Unable to update cart item (${response.status})`;
        try {
          const errData = await response.json();
          if (errData && errData.detail) {
            errorMessage = typeof errData.detail === "string" ? errData.detail : JSON.stringify(errData.detail);
          }
        } catch {}
        throw new Error(errorMessage);
      }

      const updatedCart: Cart = await response.json();
      setCart(updatedCart);
    } catch (error) {
      console.error("AgentPay cart update failed:", error);

      setErrorMessage(
        error instanceof TypeError
          ? "Connection Failed: Unable to reach the backend to update cart."
          : error instanceof Error
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
        `${API_BASE_URL}/cart/${cart.cart_id}/items/${encodeURIComponent(productId)}?customer_id=${CUSTOMER_ID}`,
        {
          method: "DELETE",
        },
      );

      if (!response.ok) {
        let errorMessage = `Unable to remove cart item (${response.status})`;
        try {
          const errData = await response.json();
          if (errData && errData.detail) {
            errorMessage = typeof errData.detail === "string" ? errData.detail : JSON.stringify(errData.detail);
          }
        } catch {}
        throw new Error(errorMessage);
      }

      const updatedCart: Cart = await response.json();
      setCart(updatedCart);
    } catch (error) {
      console.error("AgentPay remove-from-cart failed:", error);

      setErrorMessage(
        error instanceof TypeError
          ? "Connection Failed: Unable to reach the backend to remove item."
          : error instanceof Error
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
        `${API_BASE_URL}/cart/${cart.cart_id}?customer_id=${CUSTOMER_ID}`,
        {
          method: "DELETE",
        },
      );

      if (!response.ok) {
        let errorMessage = `Unable to clear cart (${response.status})`;
        try {
          const errData = await response.json();
          if (errData && errData.detail) {
            errorMessage = typeof errData.detail === "string" ? errData.detail : JSON.stringify(errData.detail);
          }
        } catch {}
        throw new Error(errorMessage);
      }

      const updatedCart: Cart = await response.json();
      setCart(updatedCart);
    } catch (error) {
      console.error("AgentPay clear-cart failed:", error);

      setErrorMessage(
        error instanceof TypeError
          ? "Connection Failed: Unable to reach the backend to clear cart."
          : error instanceof Error
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

    setMessages((current) => {
      const next = [...current, userMessage];
      if (sessionId) {
        window.sessionStorage.setItem(
          `${CONVERSATION_STORAGE_KEY_PREFIX}${sessionId}`,
          JSON.stringify(next)
        );
      }
      return next;
    });
    setInput("");
    setLoading(true);
    setErrorMessage(null);

    try {
      const response = await fetch(
        `${API_BASE_URL}/agent/chat`,
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
        let errorMessage = `Agent service error (${response.status})`;
        try {
          const errData = await response.json();
          if (errData && errData.detail) {
            if (typeof errData.detail === "string") {
              errorMessage = errData.detail;
            } else if (Array.isArray(errData.detail)) {
              errorMessage = errData.detail.map((d: { msg?: string }) => d.msg || JSON.stringify(d)).join(", ");
            } else {
              errorMessage = JSON.stringify(errData.detail);
            }
          }
        } catch {}
        throw new Error(errorMessage);
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

      const displayProducts = returnedProducts;

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

      setMessages((current) => {
        const next = [...current, assistantMessage];
        if (sessionId) {
          window.sessionStorage.setItem(
            `${CONVERSATION_STORAGE_KEY_PREFIX}${sessionId}`,
            JSON.stringify(next)
          );
        }
        return next;
      });

      if (displayProducts.length > 0) {
        setProducts(displayProducts);
      }

      /*
       * If the agent itself created/updated a cart,
       * synchronize that server-side cart with the UI.
       */
      if (data.cart_id) {
        setStoredCartId(data.cart_id, sessionId);

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
        error instanceof TypeError
          ? "Connection Failed: Unable to reach the AgentPay backend. Please verify that the backend server is running and accessible."
          : error instanceof Error
          ? error.message
          : "Unable to reach the AgentPay backend.",
      );

      setMessages((current) => {
        const next: Message[] = [
          ...current,
          {
            id: crypto.randomUUID(),
            role: "assistant",
            content:
              "I couldn't complete that request right now. Please check that the AgentPay backend is running and try again.",
          },
        ];
        if (sessionId) {
          window.sessionStorage.setItem(
            `${CONVERSATION_STORAGE_KEY_PREFIX}${sessionId}`,
            JSON.stringify(next)
          );
        }
        return next;
      });
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

  async function handleAddToCartDirectly(product: Product) {
    const productId = product.product_id;
    setAddingIds(prev => ({ ...prev, [productId]: true }));
    setCardErrors(prev => ({ ...prev, [productId]: "" }));

    try {
      let activeCartId = cart?.cart_id;
      if (cart?.status === "checked_out") {
        activeCartId = undefined;
      }
      
      if (!activeCartId) {
        const storedCartId = getStoredCartId(sessionId);
        if (storedCartId) {
          activeCartId = storedCartId;
        }
      }

      if (!activeCartId) {
        const createRes = await fetch(`${API_BASE_URL}/cart`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            merchant_id: "m_urbanrun",
            customer_id: CUSTOMER_ID,
          }),
        });

        if (!createRes.ok) {
          throw new Error("Failed to initialize shopping cart.");
        }

        const newCartData: Cart = await createRes.json();
        activeCartId = newCartData.cart_id;
        setCart(newCartData);
        setStoredCartId(newCartData.cart_id, sessionId);
      }

      const res = await fetch(`${API_BASE_URL}/cart/${activeCartId}/items?customer_id=${CUSTOMER_ID}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          product_id: productId,
          quantity: 1,
        }),
      });

      if (!res.ok) {
        let errMsg = "Failed to add item to cart.";
        try {
          const errData = await res.json();
          if (errData?.detail) {
            errMsg = typeof errData.detail === "string" ? errData.detail : JSON.stringify(errData.detail);
          }
        } catch {}
        throw new Error(errMsg);
      }

      const updatedCart: Cart = await res.json();
      setCart(updatedCart);
    } catch (error) {
      console.error("Direct add to cart failed:", error);
      setCardErrors(prev => ({
        ...prev,
        [productId]: error instanceof Error ? error.message : "Failed to add item.",
      }));
    } finally {
      setAddingIds(prev => ({ ...prev, [productId]: false }));
    }
  }

  function cleanMessageContent(content: string, hasProducts: boolean): string {
    if (!hasProducts) return content;
    const lines = content.split("\n");
    const filteredLines = lines.filter((line) => {
      const trimmed = line.trim();
      if (trimmed.startsWith("|") || trimmed.endsWith("|")) {
        return false;
      }
      if (trimmed.startsWith(":-") || trimmed.startsWith("-:") || trimmed.startsWith("---")) {
        return false;
      }
      return true;
    });
    return filteredLines.join("\n").trim();
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
                window.location.href = "/cart";
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

            <button
              type="button"
              onClick={() => {
                window.location.href = "/orders";
              }}
              className="hidden rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-medium sm:block transition hover:bg-slate-50"
            >
              Orders
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
                      {cleanMessageContent(message.content, !!message.products)}

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
                                    handleAddToCartDirectly(
                                      product,
                                    )
                                  }
                                  onCompare={() =>
                                    void sendMessage(`Compare ${product.name} with the other matching products`)
                                  }
                                  adding={!!addingIds[product.product_id]}
                                  added={cart?.items.some(item => item.product_id === product.product_id) ?? false}
                                  cartQty={cart?.items.find(item => item.product_id === product.product_id)?.quantity ?? 0}
                                  error={cardErrors[product.product_id]}
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
                          handleAddToCartDirectly(product)
                        }
                        adding={!!addingIds[product.product_id]}
                        added={cart?.items.some(item => item.product_id === product.product_id) ?? false}
                        cartQty={cart?.items.find(item => item.product_id === product.product_id)?.quantity ?? 0}
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
                  disabled={selectedProduct.availability?.in_stock === false || addingIds[selectedProduct.product_id]}
                  onClick={async () => {
                    await handleAddToCartDirectly(selectedProduct);
                    setSelectedProduct(null);
                  }}
                  className={`mt-8 flex w-full items-center justify-center gap-2 rounded-xl px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50 ${
                    cart?.items.some(item => item.product_id === selectedProduct.product_id)
                      ? "bg-emerald-600 hover:bg-emerald-700"
                      : selectedProduct.availability?.in_stock === false
                      ? "bg-slate-300 cursor-not-allowed text-slate-500 hover:bg-slate-300"
                      : "bg-slate-950 hover:bg-slate-800"
                  }`}
                >
                  <ShoppingCart size={16} />
                  {addingIds[selectedProduct.product_id]
                    ? "Adding..."
                    : cart?.items.some(item => item.product_id === selectedProduct.product_id)
                    ? "Added ✓"
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
                            <span className="font-semibold">{offer.name ?? "Eligible offer"}</span>
                            {offer.discount_amount_inr ? ` (Saved ₹${offer.discount_amount_inr.toLocaleString("en-IN")})` : ""}
                            {offer.reason ? <div className="text-[10px] text-emerald-600 mt-0.5">{offer.reason}</div> : null}
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
  onCompare,
  adding,
  added,
  cartQty,
  error,
}: {
  product: Product;
  onSelect: () => void;
  onAdd: () => void;
  onCompare: () => void;
  adding: boolean;
  added: boolean;
  cartQty: number;
  error?: string;
}) {
  const isOutOfStock = product.availability?.in_stock === false || (product.availability?.quantity ?? 0) <= 0;

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm transition hover:shadow-md flex flex-col justify-between">
      <div className="relative">
        <button
          type="button"
          onClick={onSelect}
          className="block w-full text-left transition hover:opacity-90"
        >
          <div className="flex h-44 items-center justify-center bg-slate-50 border-b border-slate-100 relative">
            {product.image_url ? (
              <img
                src={product.image_url}
                alt={product.name}
                className="h-full w-full object-cover"
              />
            ) : (
              <Package size={40} className="text-slate-300" />
            )}

            {product.offers && product.offers.length > 0 && (
              <span className="absolute top-2 left-2 rounded bg-emerald-500 px-2 py-0.5 text-[10px] font-bold text-white uppercase tracking-wider">
                {product.offers[0].discount_percent}% OFF
              </span>
            )}
          </div>
        </button>
      </div>

      <div className="p-4 flex-1 flex flex-col justify-between">
        <div>
          <div className="flex justify-between items-start gap-2">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
              {product.brand || "UrbanRun"}
            </span>
            {product.availability && (
              <span className={`text-[10px] font-semibold ${isOutOfStock ? 'text-red-500' : 'text-emerald-600'}`}>
                {isOutOfStock ? "Out of stock" : `✓ In Stock (${product.availability.quantity})`}
              </span>
            )}
          </div>

          <button
            type="button"
            onClick={onSelect}
            className="mt-1 block text-left text-sm font-semibold text-slate-800 hover:underline leading-snug line-clamp-2"
          >
            {product.name}
          </button>

          {product.rating && (
            <div className="mt-1.5 flex items-center gap-1 text-xs text-slate-500">
              <span className="text-amber-500">★</span>
              <span className="font-semibold text-slate-700">{product.rating.score}</span>
              <span>·</span>
              <span>{product.rating.reviews} reviews</span>
            </div>
          )}

          {product.price && (
            <div className="mt-2.5 text-lg font-bold text-slate-900">
              ₹{product.price.amount.toLocaleString("en-IN")}
            </div>
          )}

          <div className="mt-3 space-y-1 text-[11px] text-slate-500 border-t border-slate-100 pt-2.5">
            {product.shipping && (
              <div className="flex items-center gap-1">
                <span>🚚</span>
                <span>
                  {product.shipping.free_shipping ? "Free shipping" : "Standard shipping"} · {product.shipping.estimated_days} days
                </span>
              </div>
            )}
            {product.return_policy && (
              <div className="flex items-center gap-1">
                <span>🔄</span>
                <span>
                  {product.return_policy.eligible ? `${product.return_policy.days}-day returns` : "Final sale"}
                </span>
              </div>
            )}
          </div>

          {product.features && product.features.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1">
              {product.features.slice(0, 3).map((feat, idx) => (
                <span
                  key={idx}
                  className="rounded-full bg-slate-100 px-2 py-0.5 text-[9px] font-medium text-slate-600 border border-slate-200/50"
                >
                  {feat}
                </span>
              ))}
            </div>
          )}
        </div>

        <div className="mt-4 border-t border-slate-100 pt-3">
          {error && (
            <div className="mb-2 text-[10px] font-semibold text-red-600 bg-red-50 p-1.5 rounded border border-red-100">
              ⚠️ {error}
            </div>
          )}

          <div className="flex gap-2">
            <button
              type="button"
              onClick={onCompare}
              className="flex-1 rounded-xl border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50 hover:text-slate-800 flex items-center justify-center gap-1"
            >
              ⚖️ Compare
            </button>

            <button
              type="button"
              onClick={onAdd}
              disabled={isOutOfStock || adding}
              className={`flex-1 rounded-xl px-3 py-2 text-xs font-bold text-white flex items-center justify-center gap-1 transition ${
                added
                  ? "bg-emerald-600 hover:bg-emerald-700"
                  : isOutOfStock
                  ? "bg-slate-300 cursor-not-allowed text-slate-500"
                  : "bg-slate-950 hover:bg-slate-800"
              }`}
            >
              <ShoppingCart size={13} />
              {adding ? "Adding..." : added ? `Added ✓ (${cartQty})` : "Add to Cart"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function ProductPanelCard({
  product,
  onSelect,
  onAdd,
  adding,
  added,
  cartQty,
}: {
  product: Product;
  onSelect: () => void;
  onAdd: () => void;
  adding: boolean;
  added: boolean;
  cartQty: number;
}) {
  const isOutOfStock = product.availability?.in_stock === false || (product.availability?.quantity ?? 0) <= 0;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-3 transition hover:border-slate-300 hover:shadow-sm">
      <div className="flex gap-3">
        <div className="flex h-20 w-20 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-slate-100 border border-slate-100">
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
          <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
            {product.brand || "UrbanRun"}
          </div>

          <button
            type="button"
            onClick={onSelect}
            className="mt-0.5 block truncate text-left text-sm font-semibold hover:underline text-slate-800"
          >
            {product.name}
          </button>

          {product.price && (
            <div className="mt-1 text-sm font-bold text-slate-900">
              ₹{product.price.amount.toLocaleString("en-IN")}
            </div>
          )}

          {product.rating && (
            <div className="mt-1 flex items-center gap-1 text-[11px] text-slate-500">
              <span className="text-amber-500">★</span>
              <span className="font-semibold text-slate-700">{product.rating.score}</span>
              <span>({product.rating.reviews})</span>
            </div>
          )}
        </div>
      </div>

      <div className="mt-3 flex gap-2">
        <button
          type="button"
          onClick={onSelect}
          className="flex flex-1 items-center justify-center gap-1 rounded-xl border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50"
        >
          View
          <ChevronRight size={13} />
        </button>

        <button
          type="button"
          onClick={onAdd}
          disabled={isOutOfStock || adding}
          className={`flex flex-1 items-center justify-center gap-1 rounded-xl px-3 py-2 text-xs font-bold text-white transition ${
            added
              ? "bg-emerald-600 hover:bg-emerald-700"
              : isOutOfStock
              ? "bg-slate-300 cursor-not-allowed text-slate-500"
              : "bg-slate-950 hover:bg-slate-800"
          }`}
        >
          <ShoppingCart size={13} />
          {adding ? "Adding..." : added ? `Added ✓ (${cartQty})` : "Add"}
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