/**
 * Typed HTTP client for the Peaky Peek API.
 *
 * Wraps fetch() with consistent error handling, validation,
 * and response typing so individual API functions stay focused
 * on their specific parameters and return types.
 */

export class ApiError extends Error {
  constructor(
    public status: number,
    public statusText: string,
    public endpoint: string,
    detail?: string,
  ) {
    const msg = detail
      ? `API ${status} ${statusText} on ${endpoint}: ${detail}`
      : `API ${status} ${statusText} on ${endpoint}`
    super(msg)
    this.name = "ApiError"
  }
}

interface RequestOptions {
  method?: string
  body?: unknown
  headers?: Record<string, string>
}

/**
 * Make an API request and return parsed JSON.
 * Throws ApiError on non-2xx responses.
 */
export async function apiRequest<T>(endpoint: string, options?: RequestOptions): Promise<T> {
  const url = `/api${endpoint}`
  const config: RequestInit = {
    method: options?.method ?? "GET",
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  }

  if (options?.body !== undefined) {
    config.body = JSON.stringify(options.body)
  }

  const response = await fetch(url, config)

  if (!response.ok) {
    let detail: string | undefined
    try {
      const errBody = await response.json()
      detail = errBody.detail ?? errBody.error
    } catch {
      // response body wasn't JSON
    }
    throw new ApiError(response.status, response.statusText, endpoint, detail)
  }

  return response.json() as Promise<T>
}

/** Shorthand for GET requests. */
export async function apiGet<T>(endpoint: string): Promise<T> {
  return apiRequest<T>(endpoint)
}

/** Shorthand for POST requests. */
export async function apiPost<T>(endpoint: string, body?: unknown): Promise<T> {
  return apiRequest<T>(endpoint, { method: "POST", body })
}

/** Shorthand for PUT requests. */
export async function apiPut<T>(endpoint: string, body?: unknown): Promise<T> {
  return apiRequest<T>(endpoint, { method: "PUT", body })
}

/** Shorthand for DELETE requests. */
export async function apiDelete<T>(endpoint: string): Promise<T> {
  return apiRequest<T>(endpoint, { method: "DELETE" })
}
