import argparse
import asyncio
import json
import os
from datetime import timedelta
from pathlib import Path

from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.common import RetryPolicy
from temporalio.worker import Worker

STATE = Path(os.environ.get("KERO_TEMPORAL_STATE", "front11-state"))
TASK_QUEUE = "kero-front11-durable-proof"


def bump(name: str) -> int:
    STATE.mkdir(parents=True, exist_ok=True)
    p = STATE / name
    try:
        n = int(p.read_text().strip() or "0")
    except Exception:
        n = 0
    n += 1
    p.write_text(str(n))
    return n


@activity.defn
async def step_one(parent_job_id: str) -> dict:
    n = bump("step1.count")
    (STATE / "step1.done").write_text(parent_job_id)
    return {"step": 1, "attempt_count": n, "parent_job_id": parent_job_id}


@activity.defn
async def flaky_step(parent_job_id: str) -> dict:
    n = bump("flaky.count")
    if n == 1:
        raise RuntimeError("planned-first-attempt-failure")
    return {"step": 2, "attempt_count": n, "parent_job_id": parent_job_id}


@activity.defn
async def step_three(parent_job_id: str) -> dict:
    n = bump("step3.count")
    return {"step": 3, "attempt_count": n, "parent_job_id": parent_job_id}


@workflow.defn
class DurableKeroProof:
    @workflow.run
    async def run(self, payload: dict) -> dict:
        parent_job_id = payload["parent_job_id"]
        request_key = payload["request_key"]

        s1 = await workflow.execute_activity(
            step_one,
            parent_job_id,
            start_to_close_timeout=timedelta(seconds=20),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )

        # Gives the harness a deterministic window to crash the first Worker.
        await workflow.sleep(timedelta(seconds=12))

        s2 = await workflow.execute_activity(
            flaky_step,
            parent_job_id,
            start_to_close_timeout=timedelta(seconds=20),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                maximum_interval=timedelta(seconds=2),
                maximum_attempts=3,
            ),
        )

        s3 = await workflow.execute_activity(
            step_three,
            parent_job_id,
            start_to_close_timeout=timedelta(seconds=20),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )

        return {
            "parent_job_id": parent_job_id,
            "request_key": request_key,
            "step1": s1,
            "step2": s2,
            "step3": s3,
        }


@activity.defn
async def authority_before(parent_job_id: str) -> dict:
    n = bump("authority_before.count")
    (STATE / "authority_before.done").write_text(parent_job_id)
    return {"phase": "before_authority_loss", "attempt_count": n, "parent_job_id": parent_job_id}


@activity.defn
async def authority_after(parent_job_id: str) -> dict:
    n = bump("authority_after.count")
    return {"phase": "after_authority_restore", "attempt_count": n, "parent_job_id": parent_job_id}


@workflow.defn
class AuthorityGuardProof:
    def __init__(self) -> None:
        self.authority_restored = False

    @workflow.signal
    async def restore_authority(self) -> None:
        self.authority_restored = True

    @workflow.run
    async def run(self, payload: dict) -> dict:
        parent_job_id = payload["parent_job_id"]
        request_key = payload["request_key"]

        before = await workflow.execute_activity(
            authority_before,
            parent_job_id,
            start_to_close_timeout=timedelta(seconds=20),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )

        # No enterprise action may proceed while the Central authority is unavailable.
        await workflow.wait_condition(lambda: self.authority_restored)

        after = await workflow.execute_activity(
            authority_after,
            parent_job_id,
            start_to_close_timeout=timedelta(seconds=20),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )
        return {
            "parent_job_id": parent_job_id,
            "request_key": request_key,
            "before": before,
            "after": after,
        }


async def run_worker() -> None:
    client = await Client.connect("127.0.0.1:7233")
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[DurableKeroProof, AuthorityGuardProof],
        activities=[step_one, flaky_step, step_three, authority_before, authority_after],
    )
    await worker.run()


async def run_client(parent_job_id: str, request_key: str) -> None:
    client = await Client.connect("127.0.0.1:7233")
    workflow_id = f"kero-front11-{parent_job_id}"
    handle = await client.start_workflow(
        DurableKeroProof.run,
        {"parent_job_id": parent_job_id, "request_key": request_key},
        id=workflow_id,
        task_queue=TASK_QUEUE,
        execution_timeout=timedelta(minutes=4),
    )
    result = await handle.result()

    def read_count(name: str) -> int:
        try:
            return int((STATE / name).read_text().strip())
        except Exception:
            return 0

    summary = {
        "workflow_id": workflow_id,
        "parent_job_id": parent_job_id,
        "request_key": request_key,
        "workflow_result": result,
        "step1_count": read_count("step1.count"),
        "flaky_count": read_count("flaky.count"),
        "step3_count": read_count("step3.count"),
    }
    summary["proof_passed"] = (
        summary["step1_count"] == 1
        and summary["flaky_count"] == 2
        and summary["step3_count"] == 1
        and result.get("parent_job_id") == parent_job_id
        and result.get("request_key") == request_key
    )
    print(json.dumps(summary, sort_keys=True))


async def run_guard_client(parent_job_id: str, request_key: str) -> None:
    client = await Client.connect("127.0.0.1:7233")
    workflow_id = f"kero-front11-{parent_job_id}"
    handle = await client.start_workflow(
        AuthorityGuardProof.run,
        {"parent_job_id": parent_job_id, "request_key": request_key},
        id=workflow_id,
        task_queue=TASK_QUEUE,
        execution_timeout=timedelta(minutes=4),
    )

    # Wait until the workflow has completed the last action allowed before authority loss.
    for _ in range(80):
        if (STATE / "authority_before.done").exists():
            break
        await asyncio.sleep(0.25)
    else:
        raise RuntimeError("authority_before_not_reached")

    # Synthetic unreachable authority endpoint. We do not disrupt the real Supabase.
    import socket
    s = socket.socket()
    s.settimeout(0.5)
    central_unreachable = s.connect_ex(("127.0.0.1", 9)) != 0
    s.close()
    if not central_unreachable:
        raise RuntimeError("synthetic_authority_endpoint_unexpectedly_available")

    await asyncio.sleep(5)
    after_during_outage = (STATE / "authority_after.count").exists()
    if after_during_outage:
        raise RuntimeError("workflow_advanced_while_authority_unavailable")

    await handle.signal(AuthorityGuardProof.restore_authority)
    result = await handle.result()

    def read_count(name: str) -> int:
        try:
            return int((STATE / name).read_text().strip())
        except Exception:
            return 0

    summary = {
        "workflow_id": workflow_id,
        "parent_job_id": parent_job_id,
        "request_key": request_key,
        "central_unreachable_simulated": central_unreachable,
        "advanced_during_outage": after_during_outage,
        "authority_before_count": read_count("authority_before.count"),
        "authority_after_count": read_count("authority_after.count"),
        "workflow_result": result,
    }
    summary["proof_passed"] = (
        summary["central_unreachable_simulated"]
        and not summary["advanced_during_outage"]
        and summary["authority_before_count"] == 1
        and summary["authority_after_count"] == 1
        and result.get("parent_job_id") == parent_job_id
        and result.get("request_key") == request_key
    )
    print(json.dumps(summary, sort_keys=True))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["worker", "client", "guard-client"])
    ap.add_argument("--parent-job-id")
    ap.add_argument("--request-key")
    args = ap.parse_args()

    if args.mode == "worker":
        asyncio.run(run_worker())
    else:
        if not args.parent_job_id or not args.request_key:
            raise SystemExit("client requires --parent-job-id and --request-key")
        if args.mode == "guard-client":
            asyncio.run(run_guard_client(args.parent_job_id, args.request_key))
        else:
            asyncio.run(run_client(args.parent_job_id, args.request_key))


if __name__ == "__main__":
    main()
