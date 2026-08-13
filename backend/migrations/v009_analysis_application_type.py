"""Persist the deterministic application type shown in analysis history."""

VERSION = "009_analysis_application_type"

STATEMENTS = (
    "ALTER TABLE ai_analyses ADD COLUMN IF NOT EXISTS application_type TEXT",
)
