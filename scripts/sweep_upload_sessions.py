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
    from api.ops.upload_guard import sweep_expired_sessions

    async with db_session() as session:
        cleaned = await sweep_expired_sessions(session)

    print(f"sweep_upload_sessions: cleaned up {cleaned} expired session(s)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
