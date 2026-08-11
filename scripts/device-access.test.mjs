import assert from "node:assert/strict";
import test from "node:test";
import { NextRequest } from "next/server.js";

import {
  DEVICE_RESTRICTED_HTML,
  isMobileOrTabletDevice,
  shouldBypassDeviceGate,
} from "../src/lib/device-access.ts";
import { proxy } from "../src/proxy.ts";

const DESKTOP_CHROME =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36";
const IPHONE_SAFARI =
  "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1";
const IPAD_DESKTOP_MODE =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15) AppleWebKit/605.1.15 Version/17.5 Mobile/15E148 Safari/604.1";
const ANDROID_TABLET =
  "Mozilla/5.0 (Linux; Android 14; SM-X710) AppleWebKit/537.36 Chrome/126.0 Safari/537.36";

test("desktop browsers remain allowed", () => {
  assert.equal(isMobileOrTabletDevice({ userAgent: DESKTOP_CHROME }), false);
  assert.equal(
    isMobileOrTabletDevice({ deviceType: undefined, mobileClientHint: "?0" }),
    false,
  );
});

test("phones and tablets are restricted by parsed device type", () => {
  assert.equal(isMobileOrTabletDevice({ deviceType: "mobile" }), true);
  assert.equal(isMobileOrTabletDevice({ deviceType: "tablet" }), true);
});

test("user-agent and client-hint fallbacks cover common mobile devices", () => {
  assert.equal(isMobileOrTabletDevice({ userAgent: IPHONE_SAFARI }), true);
  assert.equal(isMobileOrTabletDevice({ userAgent: ANDROID_TABLET }), true);
  assert.equal(isMobileOrTabletDevice({ userAgent: IPAD_DESKTOP_MODE }), true);
  assert.equal(
    isMobileOrTabletDevice({
      userAgent: DESKTOP_CHROME,
      mobileClientHint: "?1",
    }),
    true,
  );
});

test("technical and static routes bypass the website device gate", () => {
  for (const pathname of [
    "/api/auth/me",
    "/ws/logs",
    "/_next/static/app.js",
    "/health",
    "/health/database",
    "/healthz",
    "/.well-known/security.txt",
    "/favicon.ico",
    "/assets/brand.svg",
  ]) {
    assert.equal(shouldBypassDeviceGate(pathname), true, pathname);
  }

  for (const pathname of ["/", "/login", "/signup", "/dashboard", "/status"]) {
    assert.equal(shouldBypassDeviceGate(pathname), false, pathname);
  }
  assert.equal(shouldBypassDeviceGate("/docs/v1.0"), false);
});

test("the restricted response is a self-contained accessible document", () => {
  assert.match(DEVICE_RESTRICTED_HTML, /<title>Desktop access required/);
  assert.match(DEVICE_RESTRICTED_HTML, /<h1 id="device-gate-title">/);
  assert.match(DEVICE_RESTRICTED_HTML, /laptop or desktop browser/i);
  assert.doesNotMatch(DEVICE_RESTRICTED_HTML, /<script/i);
  assert.doesNotMatch(DEVICE_RESTRICTED_HTML, /https?:\/\//i);
});

test("the proxy returns a hardened 403 before rendering mobile UI", async () => {
  const response = proxy(
    new NextRequest("https://zeroops.example/dashboard", {
      headers: { "user-agent": IPHONE_SAFARI },
    }),
  );

  assert.equal(response.status, 403);
  assert.equal(response.headers.get("cache-control"), "private, no-store, max-age=0");
  assert.equal(response.headers.get("vary"), "User-Agent, Sec-CH-UA-Mobile");
  assert.equal(response.headers.get("x-frame-options"), "DENY");
  assert.equal(response.headers.get("x-robots-tag"), "noindex, nofollow");
  assert.match(await response.text(), /This workspace is desktop only/);
});

test("the proxy allows desktop UI with device-aware cache variation", () => {
  const response = proxy(
    new NextRequest("https://zeroops.example/login", {
      headers: { "user-agent": DESKTOP_CHROME },
    }),
  );

  assert.equal(response.status, 200);
  assert.equal(response.headers.get("x-middleware-next"), "1");
  assert.equal(response.headers.get("accept-ch"), "Sec-CH-UA-Mobile");
  assert.equal(response.headers.get("vary"), "User-Agent, Sec-CH-UA-Mobile");
});

test("the proxy bypasses backend and health infrastructure paths", () => {
  for (const pathname of ["/api/auth/me", "/ws/logs", "/health", "/healthz"]) {
    const response = proxy(
      new NextRequest(`https://zeroops.example${pathname}`, {
        headers: { "user-agent": IPHONE_SAFARI },
      }),
    );

    assert.equal(response.status, 200, pathname);
    assert.equal(response.headers.get("x-middleware-next"), "1", pathname);
    assert.equal(response.headers.get("vary"), null, pathname);
  }
});
