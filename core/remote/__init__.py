"""
Remote-session layer — the invite / return-channel / inbox stack described in
`docs/REMOTE_SESSION_PLAN.md`.

Split the same way the rest of the project is: pure logic in `invites.py` and
`ingest.py` (no I/O, unit-tested without a network), file persistence in
`store.py`, and the cloud transport behind `relay.py` so the flow can be
exercised end to end before Firestore exists (plan §7).
"""
