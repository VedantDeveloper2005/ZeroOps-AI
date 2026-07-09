function trimTrailingSlash(value: string) {
  return value.replace(/\/$/, "");
}

function normalizePath(path: string) {
  return path.startsWith("/") ? path : `/${path}`;
}

export function getWebSocketUrl(path: string) {
  const normalizedPath = normalizePath(path);
  const explicitWsBase = process.env.NEXT_PUBLIC_WS_BASE_URL;
  const explicitApiBase = process.env.NEXT_PUBLIC_API_BASE_URL;

  if (explicitWsBase) {
    return `${trimTrailingSlash(explicitWsBase)}${normalizedPath}`;
  }

  if (explicitApiBase) {
    const wsBase = explicitApiBase.replace(/^http/i, "ws");
    return `${trimTrailingSlash(wsBase)}${normalizedPath}`;
  }

  if (typeof window === "undefined") {
    return normalizedPath;
  }

  const isLocal =
    window.location.hostname === "localhost" ||
    window.location.hostname === "127.0.0.1" ||
    window.location.hostname === "::1";

  if (isLocal) {
    return `ws://localhost:8000${normalizedPath}`;
  }

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}${normalizedPath}`;
}

/**
 * Options for the reconnecting WebSocket wrapper.
 */
export interface ReconnectingWebSocketOptions {
  /** Called when the connection opens (including reconnects). */
  onOpen?: () => void;
  /** Called for each incoming message. */
  onMessage?: (event: MessageEvent) => void;
  /** Called when the connection fails to open or drops unexpectedly. */
  onError?: (event: Event) => void;
  /** Called when the connection is closed permanently (after all retries exhausted). */
  onClose?: () => void;
  /** Maximum number of reconnection attempts before giving up. Default: 5. */
  maxRetries?: number;
}

/**
 * Creates a WebSocket connection that automatically reconnects with
 * exponential backoff when the connection drops.  Azure App Service can drop
 * WebSocket connections during scaling events, so this is essential for
 * production stability.
 *
 * Returns a cleanup function that tears down the connection and cancels
 * any pending reconnect timer.
 */
export function createReconnectingWebSocket(
  path: string,
  options: ReconnectingWebSocketOptions,
): () => void {
  const maxRetries = options.maxRetries ?? 5;
  let retryCount = 0;
  let socket: WebSocket | null = null;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;
  let disposed = false;

  function connect() {
    if (disposed) return;
    const url = getWebSocketUrl(path);
    socket = new WebSocket(url);

    socket.onopen = () => {
      retryCount = 0; // reset on successful connect
      options.onOpen?.();
    };

    socket.onmessage = (event) => {
      options.onMessage?.(event);
    };

    socket.onerror = (event) => {
      options.onError?.(event);
    };

    socket.onclose = () => {
      if (disposed) return;
      if (retryCount < maxRetries) {
        const delay = Math.min(1000 * Math.pow(2, retryCount), 16000);
        retryCount++;
        retryTimer = setTimeout(connect, delay);
      } else {
        options.onClose?.();
      }
    };
  }

  connect();

  return () => {
    disposed = true;
    if (retryTimer) clearTimeout(retryTimer);
    socket?.close();
  };
}

