export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`
    try {
      const body = await response.json()
      if (body.detail) {
        detail = body.detail
      }
    } catch {
      // keep default detail
    }
    throw new ApiError(response.status, detail)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json()
}

/**
 * Resolve the WebSocket base URL (no path).
 *
 * Both the Vite dev server (with its proxy) and the packaged Electron static
 * server are same-origin with the renderer, so we always derive the base
 * from `window.location`. The async signature is retained so existing
 * callers (useWebSocket, useJob) keep compiling without changes.
 */
export async function resolveWebSocketBase(): Promise<string> {
  if (typeof window === 'undefined') return 'ws://localhost'
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}`
}

/**
 * Issue a same-origin fetch to /api/<path>. In dev the Vite proxy forwards
 * to the backend; in packaged Electron the local static server proxies the
 * same prefix to the spawned Python process.
 */
export async function apiFetch<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const response = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })
  return handleResponse<T>(response)
}
