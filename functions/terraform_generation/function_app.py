"""Azure Functions entry point for fail-closed Terraform generation."""

import azure.functions as func

from handler import handle_terraform_generation
from zeroops_functions.telemetry import configure_telemetry


app = func.FunctionApp()
logger = configure_telemetry("zeroops.terraform_generation")


@app.service_bus_queue_trigger(
    arg_name="message",
    queue_name="%TERRAFORM_GENERATION_QUEUE_NAME%",
    connection="ServiceBusConnection",
)
def terraform_generation(message: func.ServiceBusMessage) -> None:
    logger.info(
        "Starting Terraform generation message_id=%s correlation_id=%s",
        message.message_id,
        message.correlation_id,
    )
    handle_terraform_generation(message.get_body())
