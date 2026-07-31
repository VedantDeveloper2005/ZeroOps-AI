"""One-time Azure Monitor OpenTelemetry configuration."""

from __future__ import annotations

import logging
import os
import threading


_lock = threading.Lock()
_configured = False


def configure_telemetry(logger_name: str) -> logging.Logger:
    global _configured
    connection_string = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "").strip()
    if connection_string and not _configured:
        with _lock:
            if not _configured:
                from azure.monitor.opentelemetry import configure_azure_monitor

                configure_azure_monitor(
                    connection_string=connection_string,
                    logger_name="zeroops",
                    enable_live_metrics=True,
                )
                _configured = True
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    return logger
