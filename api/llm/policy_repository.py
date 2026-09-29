"""Postgres access for the live routing policy (S9.6, F7.3).

``RoutingPolicy`` (migration 0012, frozen) is append-only: every write is a
new row rather than an update, so the audit trail keeps the demo's own
cost/accuracy delta explainable after a policy flip. The live policy is
always the max-version row.
"""

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..config import settings
from ..contracts.enums import LLMPurpose
from ..db.models.ops_model import RoutingPolicy

# Reflects today's actual implicit behaviour (everything local, judge
# frontier-if-configured-else-local) as a policy shape, so a caller that has
# never issued a PUT still has a well-defined "current policy" to read
# rather than reverse-engineering route_for's defaults.
DEFAULT_PURPOSES: dict[str, str] = {
    purpose.value: settings.llm_model for purpose in LLMPurpose
}
DEFAULT_PURPOSES[LLMPurpose.JUDGE.value] = settings.frontier_model or settings.llm_model


async def get_current_policy(session: SQLModelAsyncSession) -> RoutingPolicy | None:
    """The live policy row (max version), or ``None`` if none has ever been written."""
    result = await session.exec(
        select(RoutingPolicy).order_by(RoutingPolicy.version.desc()).limit(1)
    )
    return result.first()


async def write_new_policy(
    session: SQLModelAsyncSession, purposes: dict[str, str]
) -> RoutingPolicy:
    """Append the next version. Never updates a row in place -- see module docstring."""
    current = await get_current_policy(session)
    next_version = (current.version if current else 0) + 1

    row = RoutingPolicy(version=next_version, purposes=dict(purposes))
    session.add(row)
    await session.commit()
    await session.refresh(row)

    return row
