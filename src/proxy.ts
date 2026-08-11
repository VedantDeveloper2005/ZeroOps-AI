import { NextResponse, userAgent, type NextRequest } from "next/server.js";

import {
  DEVICE_RESTRICTED_HTML,
  isMobileOrTabletDevice,
  shouldBypassDeviceGate,
} from "./lib/device-access.ts";

const RESTRICTED_RESPONSE_HEADERS = {
  "Accept-CH": "Sec-CH-UA-Mobile",
  "Cache-Control": "private, no-store, max-age=0",
  "Content-Security-Policy":
    "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
  "Content-Type": "text/html; charset=utf-8",
  "Permissions-Policy":
    "camera=(), microphone=(), geolocation=(), payment=(), browsing-topics=()",
  "Referrer-Policy": "no-referrer",
  Vary: "User-Agent, Sec-CH-UA-Mobile",
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
  "X-Robots-Tag": "noindex, nofollow",
} as const;

export function proxy(request: NextRequest) {
  if (shouldBypassDeviceGate(request.nextUrl.pathname)) {
    return NextResponse.next();
  }

  const { device } = userAgent(request);
  const restricted = isMobileOrTabletDevice({
    deviceType: device.type,
    mobileClientHint: request.headers.get("sec-ch-ua-mobile"),
    userAgent: request.headers.get("user-agent"),
  });

  if (!restricted) {
    const response = NextResponse.next();
    response.headers.set("Accept-CH", "Sec-CH-UA-Mobile");
    response.headers.set("Vary", "User-Agent, Sec-CH-UA-Mobile");
    return response;
  }

  return new NextResponse(DEVICE_RESTRICTED_HTML, {
    status: 403,
    statusText: "Desktop access required",
    headers: RESTRICTED_RESPONSE_HEADERS,
  });
}
