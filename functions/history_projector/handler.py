"""Idempotently project workflow events into tenant-visible history."""

from __future__ import annotations

from dataclasses import dataclass

from zeroops_functions.contracts import WorkflowEventV1
from zeroops_functions.history_store import PostgresHistoryProjector, PostgresSettings
from zeroops_functions.identity import workload_credential


@dataclass(frozen=True)
class HistoryHandlerDependencies:
    projector: PostgresHistoryProjector


def dependencies_from_environment() -> HistoryHandlerDependencies:
    return HistoryHandlerDependencies(
        projector=PostgresHistoryProjector(
            PostgresSettings.from_environment(),
            workload_credential(),
        )
    )


async def handle_history_event(
    raw_message: bytes,
    dependencies: HistoryHandlerDependencies | None = None,
) -> bool:
    event = WorkflowEventV1.model_validate_json(raw_message)
    deps = dependencies or dependencies_from_environment()
    return await deps.projector.project(event)
