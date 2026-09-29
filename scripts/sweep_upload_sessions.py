#!/usr/bin/env python3
"""S9.5: delete every demo-upload project whose 24h TTL has passed.

Run inside the api container, where `api.db.engine` points at the real
database: `make upload-sweep`, or on a schedule (cron / a systemd timer on
the public host -- see plans/sprint-9/HANDOFF.md for exactly how to wire
that on the box that actually serves the public demo).

    docker compose exec -T api python scripts/sweep_upload_sessions.py
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


async def _main() -> int:
    from api.db.engine import db_session
    from api.pipeline.session_privacy import sweep_expired_upload_sessions

    async with db_session() as session:
        result = await sweep_expired_upload_sessions(session)

    print(
        f"sweep_upload_sessions: swept {result['sessions_swept']} expired "
        f"session(s), deleted {result['books_deleted']} book(s) "
        "(Postgres, MinIO, Neo4j, Langfuse)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
