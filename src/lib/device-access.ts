export type DeviceAccessSignals = Readonly<{
  deviceType?: string;
  mobileClientHint?: string | null;
  userAgent?: string | null;
}>;

const MOBILE_OR_TABLET_USER_AGENT =
  /Android|webOS|iPhone|iPad|iPod|BlackBerry|BB10|IEMobile|Windows Phone|Opera Mini|Mobi|Tablet|Silk|Kindle|PlayBook/i;

const DEVICE_GATE_BYPASS_PREFIXES = [
  "/api",
  "/ws",
  "/_next",
  "/health",
  "/healthz",
  "/.well-known",
] as const;

const STATIC_FILE_PATH =
  /\.(?:avif|css|eot|gif|ico|jpeg|jpg|js|json|map|otf|png|svg|txt|ttf|webmanifest|webp|woff|woff2|xml)$/i;

export function isMobileOrTabletDevice({
  deviceType,
  mobileClientHint,
  userAgent,
}: DeviceAccessSignals): boolean {
  const normalizedType = deviceType?.trim().toLowerCase();
  if (normalizedType === "mobile" || normalizedType === "tablet") {
    return true;
  }

  if (mobileClientHint?.trim() === "?1") {
    return true;
  }

  const agent = userAgent ?? "";
  if (MOBILE_OR_TABLET_USER_AGENT.test(agent)) {
    return true;
  }

  // iPadOS desktop-site mode reports itself as Macintosh, but retains the
  // Mobile build token. Next.js therefore cannot classify it as a tablet.
  return /Macintosh/i.test(agent) && /Mobile\/[A-Z0-9]+/i.test(agent);
}

export function shouldBypassDeviceGate(pathname: string): boolean {
  const normalizedPath = pathname.toLowerCase();

  if (STATIC_FILE_PATH.test(normalizedPath)) {
    return true;
  }

  return DEVICE_GATE_BYPASS_PREFIXES.some(
    (prefix) =>
      normalizedPath === prefix || normalizedPath.startsWith(`${prefix}/`),
  );
}

export const DEVICE_RESTRICTED_HTML = String.raw`<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="robots" content="noindex, nofollow" />
    <meta name="color-scheme" content="light dark" />
    <title>Desktop access required | ZeroOps AI</title>
    <style>
      :root {
        color-scheme: light dark;
        --background: hsl(216 33% 97%);
        --foreground: hsl(222 47% 11%);
        --muted: hsl(215 19% 38%);
        --primary: hsl(215 86% 48%);
        --primary-ink: hsl(215 90% 40%);
        --primary-soft: hsl(214 100% 95%);
        --card: hsl(0 0% 100%);
        --border: hsl(214 26% 88%);
        --surface: hsl(216 30% 96%);
        --success: hsl(156 72% 29%);
        --success-soft: hsl(151 62% 94%);
        --shadow: 0 24px 70px hsl(222 47% 11% / 0.12);
      }

      * { box-sizing: border-box; }

      html { min-width: 320px; background: var(--background); }

      body {
        min-height: 100dvh;
        margin: 0;
        display: grid;
        grid-template-columns: minmax(0, 1fr);
        place-items: center;
        overflow-x: hidden;
        padding: max(24px, env(safe-area-inset-top)) max(20px, env(safe-area-inset-right))
          max(24px, env(safe-area-inset-bottom)) max(20px, env(safe-area-inset-left));
        background:
          radial-gradient(circle at 50% 0%, hsl(215 86% 48% / 0.12), transparent 38rem),
          var(--background);
        color: var(--foreground);
        font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        line-height: 1.5;
        -webkit-font-smoothing: antialiased;
      }

      .shell {
        width: 100%;
        min-width: 0;
        max-width: 720px;
      }

      .brand {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 10px;
        margin-bottom: 20px;
        font-size: 15px;
        font-weight: 700;
        letter-spacing: -0.02em;
      }

      .brand-mark {
        position: relative;
        display: grid;
        width: 34px;
        height: 34px;
        place-items: center;
        border: 1px solid hsl(215 86% 68%);
        border-radius: 10px;
        background: var(--primary);
        box-shadow: 0 8px 24px hsl(215 86% 48% / 0.2);
      }

      .brand-mark::before {
        width: 13px;
        height: 13px;
        border: 1.5px solid white;
        border-radius: 3px;
        content: "";
        transform: rotate(45deg);
      }

      .brand-mark::after {
        position: absolute;
        width: 6px;
        height: 6px;
        border-radius: 2px;
        background: white;
        content: "";
      }

      .brand-muted { color: var(--muted); }

      .card {
        width: 100%;
        overflow: hidden;
        border: 1px solid var(--border);
        border-radius: 22px;
        background: var(--card);
        box-shadow: var(--shadow);
      }

      .content { padding: clamp(28px, 7vw, 52px); text-align: center; }

      .status {
        display: inline-flex;
        min-height: 32px;
        align-items: center;
        gap: 8px;
        border: 1px solid hsl(215 86% 48% / 0.24);
        border-radius: 999px;
        padding: 5px 11px;
        background: var(--primary-soft);
        color: var(--primary-ink);
        font-size: 12px;
        font-weight: 750;
        letter-spacing: 0.08em;
        text-transform: uppercase;
      }

      .status svg { width: 15px; height: 15px; }

      h1 {
        max-width: 600px;
        margin: 22px auto 0;
        font-size: clamp(30px, 8vw, 48px);
        line-height: 1.08;
        letter-spacing: -0.045em;
        text-wrap: balance;
      }

      .lead {
        max-width: 570px;
        margin: 18px auto 0;
        color: var(--muted);
        font-size: clamp(16px, 4vw, 18px);
        line-height: 1.7;
        text-wrap: pretty;
      }

      .device-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 12px;
        margin-top: 30px;
        text-align: left;
      }

      .device {
        min-height: 132px;
        border: 1px solid var(--border);
        border-radius: 15px;
        padding: 18px;
        background: var(--surface);
      }

      .device.allowed {
        border-color: hsl(156 72% 29% / 0.28);
        background: var(--success-soft);
      }

      .device-icon {
        display: grid;
        width: 38px;
        height: 38px;
        place-items: center;
        border: 1px solid var(--border);
        border-radius: 10px;
        background: var(--card);
        color: var(--muted);
      }

      .allowed .device-icon { color: var(--success); }
      .device-icon svg { width: 20px; height: 20px; }
      .device strong { display: block; margin-top: 14px; font-size: 14px; }
      .device span { display: block; margin-top: 3px; color: var(--muted); font-size: 13px; }

      .assurance {
        display: flex;
        align-items: flex-start;
        gap: 11px;
        margin-top: 16px;
        border-top: 1px solid var(--border);
        padding: 20px clamp(28px, 7vw, 52px);
        background: var(--surface);
        color: var(--muted);
        font-size: 13px;
        text-align: left;
      }

      .assurance svg {
        width: 18px;
        height: 18px;
        flex: 0 0 auto;
        color: var(--primary);
      }

      .footer {
        margin: 18px 0 0;
        color: var(--muted);
        font-size: 12px;
        text-align: center;
      }

      @media (max-width: 520px) {
        .device-grid { grid-template-columns: 1fr; }
        .device { min-height: 0; }
      }

      @media (prefers-color-scheme: dark) {
        :root {
          --background: hsl(222 47% 7%);
          --foreground: hsl(210 40% 96%);
          --muted: hsl(215 18% 68%);
          --primary: hsl(213 91% 66%);
          --primary-ink: hsl(213 94% 73%);
          --primary-soft: hsl(215 72% 18%);
          --card: hsl(222 35% 10%);
          --border: hsl(217 24% 20%);
          --surface: hsl(222 31% 13%);
          --success: hsl(156 65% 58%);
          --success-soft: hsl(156 58% 14%);
          --shadow: 0 24px 70px hsl(0 0% 0% / 0.38);
        }
      }
    </style>
  </head>
  <body>
    <div class="shell">
      <div class="brand" aria-label="ZeroOps AI">
        <span class="brand-mark" aria-hidden="true"></span>
        <span>ZeroOps <span class="brand-muted">AI</span></span>
      </div>

      <main class="card" aria-labelledby="device-gate-title">
        <section class="content">
          <div class="status">
            <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" />
              <path d="m9 12 2 2 4-4" />
            </svg>
            Desktop access required
          </div>

          <h1 id="device-gate-title">This workspace is desktop only.</h1>
          <p class="lead">
            ZeroOps AI is not available on phones or tablets. Open this address from a laptop or desktop browser to continue securely.
          </p>

          <div class="device-grid" role="list" aria-label="Supported devices">
            <div class="device" role="listitem">
              <span class="device-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <rect width="14" height="20" x="5" y="2" rx="2" />
                  <path d="M12 18h.01" />
                </svg>
              </span>
              <strong>Phone or tablet</strong>
              <span>Access is unavailable</span>
            </div>

            <div class="device allowed" role="listitem">
              <span class="device-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <rect width="20" height="14" x="2" y="3" rx="2" />
                  <path d="M8 21h8M12 17v4" />
                  <path d="m9 10 2 2 4-4" />
                </svg>
              </span>
              <strong>Laptop or desktop</strong>
              <span>Required to continue</span>
            </div>
          </div>
        </section>

        <aside class="assurance">
          <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />
            <path d="m9 12 2 2 4-4" />
          </svg>
          <span>Your account, projects, and deployment history remain unchanged. This device restriction does not modify any stored data.</span>
        </aside>
      </main>

      <p class="footer">ZeroOps AI &middot; Secure cloud operations workspace</p>
    </div>
  </body>
</html>`;
