from backend.migrations import v009_analysis_application_type


def test_v009_adds_persisted_application_type_idempotently():
    sql = "\n".join(v009_analysis_application_type.STATEMENTS).lower()

    assert v009_analysis_application_type.VERSION == "009_analysis_application_type"
    assert "alter table ai_analyses add column if not exists application_type text" in sql
