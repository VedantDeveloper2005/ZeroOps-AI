import uuid
from types import SimpleNamespace

import pytest

from backend.services.pipeline_records import context_from_configuration


def test_runtime_context_carries_repository_analysis_decision():
    context = context_from_configuration(
        None,
        target_type="azure-app-service",
        repository_analysis_required=False,
    )

    assert context.repository_analysis_required is False
