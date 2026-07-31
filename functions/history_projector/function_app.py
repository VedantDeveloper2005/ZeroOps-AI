"""Azure Functions entry point for workflow history projection."""

import azure.functions as func

from handler import handle_history_event
from zeroops_functions.telemetry import configure_telemetry


app = func.FunctionApp()
logger = configure_telemetry("zeroops.history_projector")


@app.service_bus_queue_trigger(
    arg_name="message",
    queue_name="%WORKFLOW_EVENTS_QUEUE_NAME%",
    connection="ServiceBusConnection",
    is_sessions_enabled=True,
)
async def history_projector(message: func.ServiceBusMessage) -> None:
    projected = await handle_history_event(message.get_body())
    logger.info(
        "History event message_id=%s projected=%s",
        message.message_id,
        projected,
    )
