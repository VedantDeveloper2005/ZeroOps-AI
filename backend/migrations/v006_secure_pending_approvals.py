"""Retire legacy plaintext pending-action parameters.

Application code now stores a versioned Fernet ciphertext envelope in the
compatibility JSON column and clears it after execution. Existing plaintext
approvals cannot be safely transformed inside SQL, so they are invalidated
and must be requested again.
"""

VERSION = "006_secure_pending_approvals"

STATEMENTS = [
    """
    UPDATE pending_approvals
       SET raw_parameters = '{}'::json
     WHERE raw_parameters IS NOT NULL
       AND raw_parameters::text <> '{}'
    """,
]
