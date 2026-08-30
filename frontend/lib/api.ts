export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";

export const DEFAULT_CUSTOMER_ID = "c_demo_001";
export const SESSION_STORAGE_KEY = "agentpay_buyer_session_id";
export const SESSION_STORAGE_KEY_PREFIX = "agentpay_session_id:";
export const CONVERSATION_STORAGE_KEY_PREFIX = "agentpay_conversation:";
export const CART_STORAGE_KEY_PREFIX = "agentpay_cart_id:";

export function getCartStorageKey(sessionId?: string | null, customerId?: string | null): string {
  if (sessionId) return `${CART_STORAGE_KEY_PREFIX}${sessionId}`;
  if (customerId) return `${CART_STORAGE_KEY_PREFIX}customer_${customerId}`;
  if (typeof window !== "undefined") {
    const session = window.sessionStorage.getItem(SESSION_STORAGE_KEY);
    if (session) return `${CART_STORAGE_KEY_PREFIX}${session}`;
  }
  return "agentpay_cart_id";
}

export function getStoredCartId(sessionId?: string | null, customerId?: string | null): string | null {
  if (typeof window === "undefined") return null;
  const specificKey = getCartStorageKey(sessionId, customerId);
  return (
    window.localStorage.getItem(specificKey) ||
    (customerId ? window.localStorage.getItem(`${CART_STORAGE_KEY_PREFIX}customer_${customerId}`) : null) ||
    window.localStorage.getItem("agentpay_cart_id")
  );
}

export function setStoredCartId(cartId: string, sessionId?: string | null, customerId?: string | null): void {
  if (typeof window === "undefined") return;
  const specificKey = getCartStorageKey(sessionId, customerId);
  window.localStorage.setItem(specificKey, cartId);
  if (customerId) {
    window.localStorage.setItem(`${CART_STORAGE_KEY_PREFIX}customer_${customerId}`, cartId);
  }
  window.localStorage.setItem("agentpay_cart_id", cartId);
}

export function clearStoredCartId(sessionId?: string | null, customerId?: string | null): void {
  if (typeof window === "undefined") return;
  const specificKey = getCartStorageKey(sessionId, customerId);
  window.localStorage.removeItem(specificKey);
  if (customerId) {
    window.localStorage.removeItem(`${CART_STORAGE_KEY_PREFIX}customer_${customerId}`);
  }
  window.localStorage.removeItem("agentpay_cart_id");
}

export class ApiError extends Error {
  status: number;
  detail: string;
  errorType:
    | "NETWORK_ERROR"
    | "VALIDATION_ERROR"
    | "AUTHORIZATION_ERROR"
    | "NOT_FOUND"
    | "RATE_LIMIT"
    | "SERVER_ERROR"
    | "UNKNOWN";

  constructor(status: number, detail: string) {
    let type: ApiError["errorType"] = "UNKNOWN";
    if (status === 0) type = "NETWORK_ERROR";
    else if (status === 400) type = "VALIDATION_ERROR";
    else if (status === 403) type = "AUTHORIZATION_ERROR";
    else if (status === 404) type = "NOT_FOUND";
    else if (status === 429) type = "RATE_LIMIT";
    else if (status >= 500) type = "SERVER_ERROR";

    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.errorType = type;
  }
}

export async function fetchApi<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
      cache: "no-store",
    });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : "Network request failed";
    throw new ApiError(
      0,
      `Backend API unavailable (${msg}). Please verify that the FastAPI backend server is running on http://127.0.0.1:8000.`,
    );
  }

  if (!response.ok) {
    let errorDetail = `HTTP ${response.status} ${response.statusText}`;
    try {
      const data = await response.json();
      if (data && data.detail) {
        if (typeof data.detail === "string") {
          errorDetail = data.detail;
        } else if (Array.isArray(data.detail)) {
          errorDetail = data.detail
            .map((item: { msg?: string }) => item.msg || JSON.stringify(item))
            .join("; ");
        } else {
          errorDetail = JSON.stringify(data.detail);
        }
      }
    } catch {
      // Fallback to generic status text if JSON body parsing fails
    }
    throw new ApiError(response.status, errorDetail);
  }

  return (await response.json()) as T;
}
