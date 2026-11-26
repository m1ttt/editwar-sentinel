"""Logging and APM setup shared by all services.

When APPLICATIONINSIGHTS_CONNECTION_STRING is set, the Azure Monitor
OpenTelemetry distro sends traces, exceptions, logs and metrics to Application
Insights. Without it, the services only log to stdout, which is what the tests
and docker compose use.
"""

from __future__ import annotations

import logging
import os

from editwar_domain.settings import (
    APPLICATIONINSIGHTS_CONNECTION_STRING,
    LOG_LEVEL,
    SERVICE_VERSION,
    env,
)

_configured = False


def configure_telemetry(service_name: str) -> bool:
    """Configure logging and, if possible, Application Insights.

    Returns True when Application Insights is active.
    """
    global _configured
    logging.basicConfig(
        level=env(LOG_LEVEL, "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    if _configured:
        return True
    connection_string = env(APPLICATIONINSIGHTS_CONNECTION_STRING, "")
    if not connection_string:
        return False
    try:
        from azure.monitor.opentelemetry import configure_azure_monitor
    except ImportError:
        logging.getLogger(__name__).warning("azure-monitor-opentelemetry is not installed")
        return False
    os.environ.setdefault(
        "OTEL_RESOURCE_ATTRIBUTES",
        f"service.name={service_name},service.version={env(SERVICE_VERSION, 'dev')}",
    )
    os.environ.setdefault("OTEL_SERVICE_NAME", service_name)
    configure_azure_monitor(
        connection_string=connection_string,
        logger_name="editwar",
    )
    _configured = True
    logging.getLogger(__name__).info("Application Insights enabled for %s", service_name)
    return True
