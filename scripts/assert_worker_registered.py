import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

INSPECT_TIMEOUT_S = float(os.environ.get("INSPECT_TIMEOUT_S", "10"))


def main() -> int:
    from api.contracts.enums import StageName
    from api.tasks import STAGES, celery_app
    from api.workers.app import missing_stage_tasks

    still_missing = {stage.value for stage in missing_stage_tasks()}
    expected = {stage.value for stage in STAGES if stage.value not in still_missing}

    if not expected:
        print(
            "assert_worker_registered: no task module is importable from this "
            "checkout — nothing to assert against the live worker",
            file=sys.stderr,
        )
        return 1

    inspect = celery_app.control.inspect(timeout=INSPECT_TIMEOUT_S)
    registered = inspect.registered() or {}
    if not registered:
        print(
            "assert_worker_registered: no worker replied to `celery inspect "
            "registered` at all — is celery-worker up, and on the vhost this "
            "script's RABBITMQ_URL points at?",
            file=sys.stderr,
        )
        return 1

    all_stage_names = {stage.value for stage in StageName}
    actual: set[str] = set()
    for names in registered.values():
        for name in names:
            actual.add(name.split(" ")[0])
    actual_stages = actual & all_stage_names

    missing = sorted(expected - actual_stages)
    if missing:
        print(
            f"assert_worker_registered: the live worker is missing "
            f"{missing} even though this checkout's task modules define "
            f"them — the compose command is not booting api.workers.app (or "
            f"a task module is failing to import inside the container). "
            f"Live workers reported: {sorted(registered.keys())}",
            file=sys.stderr,
        )
        return 1

    unexpected = sorted(actual_stages - expected)
    if unexpected:
        # A stage this checkout can't import locally (e.g. a dependency the CI
        # runner never installed) but the container's built image can. Worth a
        # look, not a failure — the container is not under-registered.
        print(
            f"assert_worker_registered: live worker reports extra stages "
            f"{unexpected} not importable from this checkout (stale image?)",
            file=sys.stderr,
        )

    print(
        "assert_worker_registered: OK — "
        f"{len(actual_stages)}/{len(STAGES)} frozen stage(s) confirmed live: "
        f"{sorted(actual_stages)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
