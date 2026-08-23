export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";

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
