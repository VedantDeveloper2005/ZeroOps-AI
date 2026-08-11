from __future__ import annotations

import unittest
from unittest.mock import patch

from worker.queue import PostgresJobQueue, QueueUnavailableError


class RecordingCursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def execute(self, statement: str, params: tuple[object, ...]) -> None:
        self.calls.append((statement, params))


class RecordingConnection:
    def __init__(self) -> None:
        self.recording_cursor = RecordingCursor()
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return self.recording_cursor

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


def decoded_update_parameters(params: tuple[object, ...]) -> dict[str, tuple[bool, object]]:
    values = params[1:-1]
    return {
        field: (bool(values[index]), values[index + 1])
        for field, index in zip(
            PostgresJobQueue._UPDATE_PARAMETER_FIELDS,
            range(0, len(values), 2),
        )
    }


class DeploymentJobUpdateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.queue = PostgresJobQueue("postgresql://example.invalid/zeroops")

    def execute_update(self, status: str, **kwargs):
        connection = RecordingConnection()
        with patch.object(self.queue, "_get_connection", return_value=connection):
            self.queue.update_job_status("job-id", status, **kwargs)
        self.assertEqual(len(connection.recording_cursor.calls), 1)
        statement, params = connection.recording_cursor.calls[0]
        self.assertEqual(connection.commits, 1)
        self.assertEqual(connection.rollbacks, 0)
        self.assertTrue(connection.closed)
        return statement, params

    def test_status_only_update_uses_one_static_atomic_statement(self) -> None:
        statement, params = self.execute_update("running")

        self.assertEqual(statement, PostgresJobQueue._UPDATE_JOB_STATUS_SQL)
        self.assertEqual(params[0], "running")
        self.assertEqual(params[-1], "job-id")
        decoded = decoded_update_parameters(params)
        self.assertTrue(
            all(
                not supplied and value is None
                for supplied, value in decoded.values()
            )
        )

    def test_allowed_field_combinations_are_bound_in_a_fixed_order(self) -> None:
        hostile_log_value = "finished'); DROP TABLE deployment_jobs; --"
        statement, params = self.execute_update(
            "completed",
            logs=hostile_log_value,
            terraform_status="completed",
            failure_reason=None,
        )
        decoded = decoded_update_parameters(params)

        self.assertEqual(statement, PostgresJobQueue._UPDATE_JOB_STATUS_SQL)
        self.assertNotIn(hostile_log_value, statement)
        self.assertEqual(decoded["terraform_status"], (True, "completed"))
        self.assertEqual(decoded["logs"], (True, hostile_log_value))
        self.assertEqual(decoded["failure_reason"], (True, None))
        self.assertEqual(decoded["live_url"], (False, None))

    def test_unapproved_identifier_is_rejected_before_database_access(self) -> None:
        injected_identifier = "logs = NULL; DROP TABLE deployment_jobs; --"
        with patch.object(self.queue, "_get_connection") as get_connection:
            with self.assertRaises(QueueUnavailableError) as error:
                self.queue.update_job_status(
                    "job-id",
                    "failed",
                    **{injected_identifier: "attacker-controlled"},
                )

        get_connection.assert_not_called()
        self.assertIsInstance(error.exception.__cause__, ValueError)
        self.assertIn(
            "Unsupported deployment job update fields",
            str(error.exception.__cause__),
        )


if __name__ == "__main__":
    unittest.main()
