"""Azure Functions entry point for repository analysis."""

import azure.functions as func

from handler import handle_repository_analysis
from zeroops_functions.telemetry import configure_telemetry


app = func.FunctionApp()
logger = configure_telemetry("zeroops.repository_analysis")


@app.service_bus_queue_trigger(
    arg_name="message",
    queue_name="%REPOSITORY_ANALYSIS_QUEUE_NAME%",
    connection="ServiceBusConnection",
)
def repository_analysis(message: func.ServiceBusMessage) -> None:
    logger.info(
        "Starting repository analysis message_id=%s correlation_id=%s",
        message.message_id,
        message.correlation_id,
    )
    handle_repository_analysis(message.get_body())
