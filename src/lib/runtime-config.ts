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
