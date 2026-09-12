"use client";

import { useEffect } from "react";

/**
 * Recovers from stale Next.js chunks after production deployment.
 * When the server has been redeployed with new asset hashes, clients
 * requesting old chunks receive 404s leading to ChunkLoadError.
 * This component catches those errors and forces a single page reload.
 */
export function ChunkErrorHandler() {
  useEffect(() => {
    const handleChunkError = (event: ErrorEvent | PromiseRejectionEvent) => {
      const message =
        "message" in event ? event.message : String(event.reason?.message || event.reason || "");
      if (
        message.includes("ChunkLoadError") ||
        message.includes("Failed to load chunk") ||
        message.includes("Loading chunk")
      ) {
        const lastReload = sessionStorage.getItem("zeroops_chunk_reload");
        const now = Date.now();
        if (!lastReload || now - Number(lastReload) > 10_000) {
          sessionStorage.setItem("zeroops_chunk_reload", String(now));
          window.location.reload();
        }
      }
    };

    window.addEventListener("error", handleChunkError);
    window.addEventListener("unhandledrejection", handleChunkError);

    return () => {
      window.removeEventListener("error", handleChunkError);
      window.removeEventListener("unhandledrejection", handleChunkError);
    };
  }, []);

  return null;
}
