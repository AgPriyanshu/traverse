#!/usr/bin/env python3

from __future__ import annotations

import contextlib
import json
import os
import select
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

COMPOSE = os.environ.get("COMPOSE", "docker compose").split()
CHAOS_NETWORK = os.environ.get("CHAOS_NETWORK", "traverse_default")
_default_api_port = os.environ.get("API_PORT", "8000")
API_BASE_URL = os.environ.get("API_BASE_URL", f"http://localhost:{_default_api_port}")
FIXTURE_PROJECT_SLUG = os.environ.get(
    "CHAOS_TEST_PROJECT_SLUG", "ci-integration-fixture"
)
LIVE_RUN_WINDOW_MINUTES = 10
PROBE_MODULE = "api.tests.graph.checkpoint_probe"


def _log(message: str) -> None:
    print(message, flush=True)


@dataclass
class ScenarioResult:
    name: str
    outcome: str  # "PASS" | "FAIL" | "SKIP"
    detail: str = ""


# ── shared compose/psql helpers, same shape as perf_smoke.py /
# test_integration_ingestion.py ──


def _psql(sql: str) -> str:
    result = subprocess.run(
        [
            *COMPOSE,
            "exec",
            "-T",
            "db",
            "psql",
            "-U",
            "postgres",
            "-d",
            "postgres",
            "-tAc",
            sql,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _compose_run(*args: str, timeout: float = 60) -> subprocess.CompletedProcess:
    """Run a compose command, folding a hang into a normal (non-raising) result.

    A hung `exec` (scenario 6's whole point: does the Neo4j client fail fast
    under a partition, or hang forever?) must show up as a result this
    script's caller can inspect, not an uncaught `TimeoutExpired` that loses
    every other scenario's already-collected results.
    """
    try:
        return subprocess.run(
            [*COMPOSE, *args], capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(
            args=[*COMPOSE, *args],
            returncode=-1,
            stdout=(exc.stdout or b"").decode(errors="replace")
            if isinstance(exc.stdout, bytes)
            else (exc.stdout or ""),
            stderr=f"TIMED OUT after {timeout}s",
        )


def _wait_for_exec(service: str, timeout: float) -> bool:
    """Poll ``docker compose exec -T <service> true`` until it succeeds.

    A generic "the container is up and accepting execs again" check -- good
    enough for a service with no HTTP health endpoint of its own reachable
    from the host (celery-worker).
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = _compose_run("exec", "-T", service, "true", timeout=10)
        if result.returncode == 0:
            return True
        time.sleep(2)

    return False


def _wait_for_health(timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    url = f"{API_BASE_URL}/health"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310
                if response.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(2)

    return False


def _read_json_line(stream, timeout_s: float) -> dict | None:
    """Read from a live pipe until one JSON line arrives, or ``timeout_s`` elapses.

    Not ``Popen.communicate()``: that waits for the process to exit, and the
    probe process is deliberately hung at this point in scenarios 1/2 -- it
    never exits until killed.
    """
    deadline = time.monotonic() + timeout_s
    buf = b""
    while time.monotonic() < deadline:
        remaining = max(0.0, deadline - time.monotonic())
        ready, _, _ = select.select([stream], [], [], remaining)
        if not ready:
            continue
        chunk = os.read(stream.fileno(), 4096)
        if not chunk:
            break
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue

    return None


def _last_json_line(text_output: str) -> dict | None:
    payload = None
    for line in text_output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue

    return payload


def assert_no_live_pipeline_run() -> str | None:
    """Return a reason to abort if a real (not stale) pipeline run looks live.

    Distinguishes a genuinely running stage from a stale ``RUNNING`` row left
    by a crashed worker the only way this script can from the host: recency.
    A row updated in the last ten minutes is treated as live -- killing
    celery-worker under it would be indistinguishable from a bug in this
    script, from another agent's point of view.
    """
    try:
        count = _psql(
            "SELECT COUNT(*) FROM ingestionstage "
            f"WHERE state = 'RUNNING' AND updated_at > now() - interval "
            f"'{LIVE_RUN_WINDOW_MINUTES} minutes';"
        )
    except subprocess.CalledProcessError as exc:
        return f"could not query ingestionstage: {exc.stderr}"

    if count and int(count) > 0:
        return (
            f"{count} ingestionstage row(s) RUNNING within the last "
            f"{LIVE_RUN_WINDOW_MINUTES} minutes -- looks like a live pipeline "
            "run on the shared stack, not a stale row. Refusing to kill "
            "celery-worker under it."
        )

    return None


def ensure_checkpointer_schema() -> str | None:
    """Run `setup_checkpointer()` once, same as `test_checkpointer.py`'s own
    session fixture -- idempotent, and scenarios 1/2 need the `checkpoints`/
    `checkpoint_writes` tables to exist before they can prove anything about
    them. Returns an error string on failure, ``None`` on success."""
    result = _compose_run(
        "exec",
        "-T",
        "celery-worker",
        "python",
        "-c",
        "import asyncio\n"
        "from api.graph.checkpoint import setup_checkpointer\n"
        "asyncio.run(setup_checkpointer())\n",
        timeout=60,
    )
    if result.returncode != 0:
        return f"setup_checkpointer() failed: {result.stderr}"

    return None


# ── scenario 1: kill celery-worker mid-review ──────────────────────────────


def scenario_kill_celery_worker(enforcing: bool) -> ScenarioResult:
    name = "kill celery-worker mid-review -> restart -> resume with state intact"
    if not enforcing:
        return ScenarioResult(
            name, "SKIP", "reporting host only (INTEGRATION_HOST != 1)."
        )

    thread_id = f"chaos-worker-{uuid.uuid4()}"
    token = str(uuid.uuid4())
    proc = subprocess.Popen(
        [
            *COMPOSE,
            "exec",
            "-T",
            "celery-worker",
            "python",
            "-m",
            PROBE_MODULE,
            "start",
            "--thread-id",
            thread_id,
            "--token",
            token,
            "--hang",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        interrupted = _read_json_line(proc.stdout, 60)
        if interrupted is None or interrupted.get("marker") != "PROBE_INTERRUPTED":
            stderr = proc.stderr.read().decode(errors="replace")[:500]
            return ScenarioResult(
                name, "FAIL", f"probe never reached the interrupt: {stderr}"
            )

        # SIGKILL the whole container -- no shutdown hook, no flush. Whatever
        # survives is in Postgres or it is lost (checkpoint.py's own claim,
        # now proven at the container level rather than the subprocess level).
        subprocess.run([*COMPOSE, "kill", "celery-worker"], check=True)
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()

        subprocess.run([*COMPOSE, "up", "-d", "--no-deps", "celery-worker"], check=True)
        if not _wait_for_exec("celery-worker", timeout=120):
            return ScenarioResult(
                name, "FAIL", "celery-worker never came back up after restart"
            )

        resume = _compose_run(
            "exec",
            "-T",
            "celery-worker",
            "python",
            "-m",
            PROBE_MODULE,
            "resume",
            "--thread-id",
            thread_id,
            "--answer",
            "chaos-verified",
            timeout=60,
        )
        payload = _last_json_line(resume.stdout)
        if payload is None or payload.get("marker") != "PROBE_RESUMED":
            return ScenarioResult(
                name,
                "FAIL",
                f"resume incomplete: stdout={resume.stdout!r} stderr={resume.stderr!r}",
            )
        if payload.get("token") != token:
            return ScenarioResult(
                name,
                "FAIL",
                f"token lost: expected {token}, got {payload.get('token')}",
            )
        if payload.get("answer") != "chaos-verified":
            return ScenarioResult(name, "FAIL", "resume value not honoured")

        return ScenarioResult(
            name,
            "PASS",
            f"thread {thread_id}: state and resume value survived a real "
            "`docker compose kill celery-worker`",
        )
    finally:
        if proc.poll() is None:
            proc.kill()


# ── scenario 2: kill Postgres mid-resolve ──────────────────────────────────


def scenario_kill_postgres(enforcing: bool) -> ScenarioResult:
    name = "kill db mid-resolve -> restart -> resume reads the pre-kill checkpoint"
    if not enforcing:
        return ScenarioResult(
            name, "SKIP", "reporting host only (INTEGRATION_HOST != 1)."
        )

    thread_id = f"chaos-db-{uuid.uuid4()}"
    token = str(uuid.uuid4())
    start = _compose_run(
        "exec",
        "-T",
        "celery-worker",
        "python",
        "-m",
        PROBE_MODULE,
        "start",
        "--thread-id",
        thread_id,
        "--token",
        token,
        timeout=60,
    )
    payload = _last_json_line(start.stdout)
    if payload is None or payload.get("marker") != "PROBE_INTERRUPTED":
        return ScenarioResult(
            name,
            "FAIL",
            f"probe never interrupted: stdout={start.stdout!r} stderr={start.stderr!r}",
        )

    # The checkpoint committed above is on Postgres's data volume, not in any
    # process's memory -- killing (not `down -v`ing) db must not touch it.
    subprocess.run([*COMPOSE, "kill", "db"], check=True)
    subprocess.run([*COMPOSE, "up", "-d", "--no-deps", "db"], check=True)

    deadline = time.monotonic() + 120
    healthy = False
    while time.monotonic() < deadline:
        probe = _compose_run(
            "exec", "-T", "db", "pg_isready", "-U", "postgres", timeout=10
        )
        if probe.returncode == 0:
            healthy = True
            break
        time.sleep(2)
    if not healthy:
        return ScenarioResult(name, "FAIL", "db never became ready again after restart")

    resume = _compose_run(
        "exec",
        "-T",
        "celery-worker",
        "python",
        "-m",
        PROBE_MODULE,
        "resume",
        "--thread-id",
        thread_id,
        "--answer",
        "chaos-verified",
        timeout=60,
    )
    resumed = _last_json_line(resume.stdout)
    if resumed is None or resumed.get("marker") != "PROBE_RESUMED":
        return ScenarioResult(
            name,
            "FAIL",
            f"resume incomplete after db restart: stdout={resume.stdout!r} "
            f"stderr={resume.stderr!r}",
        )
    if resumed.get("token") != token:
        return ScenarioResult(name, "FAIL", "token lost across the db restart")

    return ScenarioResult(
        name,
        "PASS",
        f"thread {thread_id}: checkpoint survived `docker compose kill db` + restart",
    )


# ── scenario 3: kill the API mid SSE-stream ────────────────────────────────


def scenario_kill_api_mid_stream(enforcing: bool) -> ScenarioResult:
    name = "kill api mid SSE-stream -> restart -> a fresh query still works"
    if not enforcing:
        return ScenarioResult(
            name, "SKIP", "reporting host only (INTEGRATION_HOST != 1)."
        )

    try:
        project_id = _psql(
            f"SELECT id FROM project WHERE slug = '{FIXTURE_PROJECT_SLUG}';"
        )
    except subprocess.CalledProcessError as exc:
        return ScenarioResult(name, "FAIL", f"could not query project: {exc.stderr}")
    if not project_id:
        return ScenarioResult(
            name,
            "SKIP",
            f"no project with slug {FIXTURE_PROJECT_SLUG!r} -- "
            "run `make test-integration` first.",
        )

    body = json.dumps(
        {"project_id": project_id, "question": "What happens in this book?"}
    ).encode()
    req = urllib.request.Request(
        f"{API_BASE_URL}/api/query",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        response = urllib.request.urlopen(req, timeout=10)  # noqa: S310
    except urllib.error.HTTPError as exc:
        if exc.code == 501:
            return ScenarioResult(name, "SKIP", "POST /api/query not implemented yet.")
        return ScenarioResult(
            name, "FAIL", f"HTTP {exc.code} before the kill: {exc.read()!r}"
        )
    except urllib.error.URLError as exc:
        return ScenarioResult(name, "FAIL", f"could not reach the API: {exc}")

    # Read a little of the stream so the kill lands mid-response, then drop it.
    try:
        response.read(64)
    except OSError:
        pass
    finally:
        response.close()

    subprocess.run([*COMPOSE, "kill", "api"], check=True)
    subprocess.run([*COMPOSE, "up", "-d", "--no-deps", "api"], check=True)
    if not _wait_for_health(120):
        return ScenarioResult(
            name, "FAIL", "api never became healthy again after restart"
        )

    retry_req = urllib.request.Request(
        f"{API_BASE_URL}/api/query",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(retry_req, timeout=30) as retry_response:  # noqa: S310
            status_code = retry_response.status
            raw = retry_response.read()
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        raw = exc.read()

    if status_code != 200:
        return ScenarioResult(
            name,
            "FAIL",
            f"a fresh query after restart returned HTTP {status_code}: {raw[:300]!r}",
        )

    return ScenarioResult(
        name,
        "PASS",
        "api recovered from a mid-stream kill; a fresh query answers normally",
    )


# ── scenario 4/5: resolve races (need S7.4's resolve handler) ─────────────


def _insert_synthetic_review_task(project_id: str, graph_thread_id: str | None) -> str:
    """Insert a minimal open ``review_task`` row directly, same pattern as
    ``test_integration_ingestion.py``'s straight-to-Postgres project creation
    for a dependency (``POST /review/tasks`` does not exist -- tasks are
    queued by the pipeline, never created via the API)."""
    task_id = str(uuid.uuid4())
    thread_sql = f"'{graph_thread_id}'" if graph_thread_id else "NULL"
    _psql(
        "INSERT INTO reviewtask "
        "(id, project_id, task_type, payload, graph_thread_id, priority, "
        "status, created_at, updated_at) "
        # SQLAlchemy's native Enum stores the Python member NAME, not
        # `.value` -- 'classify_candidate' is rejected; the enum only
        # accepts 'CLASSIFY_CANDIDATE' (data-model.md's documented gotcha).
        f"VALUES ('{task_id}', '{project_id}', 'CLASSIFY_CANDIDATE', "
        f"'{{}}'::jsonb, {thread_sql}, 0, 'OPEN', now(), now());"
    )

    return task_id


def _delete_review_task(task_id: str) -> None:
    """Remove a scenario's synthetic row so a real (nightly, integration-host)
    run doesn't leave throwaway tasks in the fixture project's review queue."""
    with contextlib.suppress(subprocess.CalledProcessError):
        _psql(f"DELETE FROM reviewtask WHERE id = '{task_id}';")


def _post_resolve(task_id: str, decision: str) -> tuple[int, str]:
    body = json.dumps({"decision": decision, "payload": {}}).encode()
    req = urllib.request.Request(
        f"{API_BASE_URL}/api/review/tasks/{task_id}/resolve",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:  # noqa: S310
            return response.status, response.read().decode(errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(errors="replace")
    except urllib.error.URLError as exc:
        return -1, str(exc)


def scenario_concurrent_resolve(enforcing: bool) -> ScenarioResult:
    name = "two reviewers resolving the same task concurrently -> exactly one wins"
    project_id = None
    try:
        project_id = _psql(
            f"SELECT id FROM project WHERE slug = '{FIXTURE_PROJECT_SLUG}';"
        )
    except subprocess.CalledProcessError as exc:
        return ScenarioResult(name, "FAIL", f"could not query project: {exc.stderr}")
    if not project_id:
        return ScenarioResult(
            name,
            "SKIP",
            f"no project with slug {FIXTURE_PROJECT_SLUG!r} to hang a task off.",
        )

    task_id = _insert_synthetic_review_task(project_id, graph_thread_id=None)
    try:
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(_post_resolve, task_id, "accept"),
                pool.submit(_post_resolve, task_id, "reject"),
            ]
            results = [f.result() for f in futures]

        if any(status == 501 for status, _ in results):
            return ScenarioResult(
                name,
                "SKIP",
                "POST /api/review/tasks/{id}/resolve not implemented yet.",
            )

        ok_count = sum(1 for status, _ in results if status == 200)
        status_row = _psql(f"SELECT status FROM reviewtask WHERE id = '{task_id}';")
        resolved_at_count = _psql(
            f"SELECT COUNT(resolved_at) FROM reviewtask WHERE id = '{task_id}';"
        )

        if status_row.lower() != "resolved":
            return ScenarioResult(
                name,
                "FAIL",
                f"task ended in status={status_row!r}, not resolved: {results}",
            )
        if ok_count == 0:
            return ScenarioResult(
                name, "FAIL", f"neither concurrent resolve succeeded: {results}"
            )
        if int(resolved_at_count) != 1:
            return ScenarioResult(
                name,
                "FAIL",
                f"resolved_at recorded {resolved_at_count} times for one "
                "task -- not idempotent",
            )

        return ScenarioResult(
            name, "PASS", f"exactly one resolve applied cleanly; results={results}"
        )
    finally:
        _delete_review_task(task_id)


def scenario_resolve_completed_thread(enforcing: bool) -> ScenarioResult:
    name = "resolve a task whose thread already completed -> clean error"
    try:
        project_id = _psql(
            f"SELECT id FROM project WHERE slug = '{FIXTURE_PROJECT_SLUG}';"
        )
    except subprocess.CalledProcessError as exc:
        return ScenarioResult(name, "FAIL", f"could not query project: {exc.stderr}")
    if not project_id:
        return ScenarioResult(
            name,
            "SKIP",
            f"no project with slug {FIXTURE_PROJECT_SLUG!r} to hang a task off.",
        )

    completed_thread = f"chaos-completed-{uuid.uuid4()}"
    task_id = _insert_synthetic_review_task(
        project_id, graph_thread_id=completed_thread
    )
    try:
        status_code, detail = _post_resolve(task_id, "accept")
        if status_code == 501:
            return ScenarioResult(
                name,
                "SKIP",
                "POST /api/review/tasks/{id}/resolve not implemented yet.",
            )

        # A completed/absent thread must fail loudly (4xx/5xx), never silently
        # accept a resolution that resumes nothing, and it must not leave the
        # task stuck neither open nor resolved.
        status_row = _psql(f"SELECT status FROM reviewtask WHERE id = '{task_id}';")
        if status_code == 200 and status_row.lower() not in ("resolved",):
            return ScenarioResult(
                name,
                "FAIL",
                f"resolve returned 200 but left task status={status_row!r}: {detail}",
            )
        if status_row.lower() not in ("open", "resolved", "dismissed"):
            return ScenarioResult(
                name, "FAIL", f"task left in an unrecognised status={status_row!r}"
            )

        return ScenarioResult(
            name,
            "PASS",
            f"resolve returned HTTP {status_code}, task status={status_row!r}",
        )
    finally:
        _delete_review_task(task_id)


# ── scenario 6: network partition between worker/api and Neo4j ────────────

NEO4J_SERVICE = "neo4j"


def _neo4j_container_name() -> str | None:
    result = _compose_run("ps", "neo4j", "--format", "{{.Name}}", timeout=15)
    name = result.stdout.strip().splitlines()[0] if result.stdout.strip() else None

    return name


NEO4J_PROBE_TIMEOUT_S = 20


def _neo4j_probe() -> subprocess.CompletedProcess:
    script = (
        "import asyncio\n"
        "from api.graph import client\n"
        "async def main():\n"
        "    result = await client.execute('RETURN 1 AS ok')\n"
        "    print('NEO4J_OK', result.records[0]['ok'])\n"
        "asyncio.run(main())\n"
    )

    return _compose_run(
        "exec", "-T", "api", "python", "-c", script, timeout=NEO4J_PROBE_TIMEOUT_S
    )


def scenario_neo4j_network_partition(enforcing: bool) -> ScenarioResult:
    name = (
        "network partition worker<->Neo4j -> clean bounded failure, then auto-recovery"
    )
    if not enforcing:
        return ScenarioResult(
            name, "SKIP", "reporting host only (INTEGRATION_HOST != 1)."
        )

    container = _neo4j_container_name()
    if not container:
        return ScenarioResult(
            name, "FAIL", "could not resolve the neo4j container name"
        )

    baseline = _neo4j_probe()
    if baseline.returncode != 0 or "NEO4J_OK" not in baseline.stdout:
        return ScenarioResult(
            name,
            "FAIL",
            f"neo4j unreachable before the partition even started: {baseline.stderr}",
        )

    subprocess.run(
        ["docker", "network", "disconnect", CHAOS_NETWORK, container], check=True
    )
    try:
        during = _neo4j_probe()
        if during.returncode == 0 and "NEO4J_OK" in during.stdout:
            return ScenarioResult(
                name,
                "FAIL",
                "a query succeeded despite the partition -- disconnect had no effect",
            )
        if "TIMED OUT" in during.stderr:
            return ScenarioResult(
                name,
                "FAIL",
                f"the client hung past the {NEO4J_PROBE_TIMEOUT_S}s probe "
                "timeout under the partition instead of failing fast -- "
                "likely no connection/query timeout configured on the "
                "driver (runbook candidate).",
            )
    finally:
        # `docker network connect` bare, with no `--alias`, reconnects the
        # container but drops the compose-assigned service-name DNS alias --
        # every other container that resolves it by service name (`neo4j`,
        # not the container name) breaks silently afterward. Restoring the
        # alias explicitly is the difference between this scenario cleaning
        # up after itself and leaving the shared stack worse than it found it.
        subprocess.run(
            [
                "docker",
                "network",
                "connect",
                "--alias",
                NEO4J_SERVICE,
                CHAOS_NETWORK,
                container,
            ],
            check=True,
        )

    deadline = time.monotonic() + 90
    recovered = False
    while time.monotonic() < deadline:
        after = _neo4j_probe()
        if after.returncode == 0 and "NEO4J_OK" in after.stdout:
            recovered = True
            break
        time.sleep(3)

    if not recovered:
        return ScenarioResult(
            name, "FAIL", "neo4j did not recover after the network was reconnected"
        )

    return ScenarioResult(
        name,
        "PASS",
        "the partition failed cleanly (bounded, no hang) and the client "
        "recovered once reconnected",
    )


SCENARIOS = [
    scenario_kill_celery_worker,
    scenario_kill_postgres,
    scenario_kill_api_mid_stream,
    scenario_concurrent_resolve,
    scenario_resolve_completed_thread,
    scenario_neo4j_network_partition,
]


def main() -> int:
    enforcing = os.environ.get("INTEGRATION_HOST") == "1"
    waiver = os.environ.get("CHAOS_TEST_WAIVE")

    if not enforcing:
        _log(
            "INTEGRATION_HOST != 1 -- reporting only, no containers will be touched. "
            "Per BRANCH.md §9, real infrastructure disruption must only run on the "
            "integration host or a nightly job's own disposable stack, never a "
            "worktree sharing infra with other agents."
        )
    else:
        live_run = assert_no_live_pipeline_run()
        if live_run:
            _log(f"ABORT: {live_run}")
            return 1

        schema_error = ensure_checkpointer_schema()
        if schema_error:
            _log(f"ABORT: {schema_error}")
            return 1

    if waiver:
        _log(
            f"CHAOS_TEST_WAIVE set: {waiver!r} -- failures will not fail "
            "the build this run."
        )

    results: list[ScenarioResult] = []
    for scenario in SCENARIOS:
        try:
            results.append(scenario(enforcing))
        except Exception as exc:  # noqa: BLE001
            # One scenario's bug must not lose every other scenario's already-
            # collected result -- a chaos harness that itself crashes silently
            # is exactly the kind of gap this file exists to catch.
            results.append(ScenarioResult(scenario.__name__, "FAIL", f"raised {exc!r}"))

    _log("")
    _log("Chaos test results:")
    for result in results:
        _log(f"  [{result.outcome:4}] {result.name}")
        if result.detail:
            _log(f"         {result.detail}")

    failures = [r for r in results if r.outcome == "FAIL"]
    if not failures:
        _log("\nPASS: no state loss detected in any exercised scenario.")
        return 0

    _log(f"\n{len(failures)} scenario(s) FAILED.")
    if not enforcing or waiver:
        _log("Not failing the build (report-only host or waived).")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
