"""Repeatable real-path S1 certification with durable restart evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
import uuid
from pathlib import Path

from appshak_projection.office_state import read_office_state
from appshak_substrate.agent_runtime import AgentRuntime
from appshak_substrate.artifact_validator import ArtifactValidator
from appshak_substrate.baton_routing import CapabilityRoutingPolicy, VerifiedBatonManager
from appshak_substrate.mailstore_sqlite import SQLiteMailStore
from appshak_substrate.policy import ToolPolicy
from appshak_substrate.tool_gateway import ToolGateway
from appshak_substrate.types import SubstrateEvent, iso_now
from appshak_substrate.workspace_manager import WorkspaceManager


def _require(condition: bool, detail: str) -> None:
    if not condition:
        raise AssertionError(detail)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _create_task(store: SQLiteMailStore, workspace_id: str, name: str, expected: str) -> dict:
    task = store.create_owner_task(owner_id="cert-owner", objective=f"Produce {name}",
        authority_id=f"authority:cert:{name}", source_request_id=f"cert:owner:{name}")
    store.add_acceptance_criterion(task_id=task["task_id"], criterion_type="EXACT_TEXT",
        config={"expected": expected}, created_by="cert-owner", source_ref=f"cert:criterion:{name}")
    return store.assign_owner_task(task_id=task["task_id"], agent_id="command",
        workspace_id=workspace_id, authority_id=task["authority_id"], actor_id="cert-owner",
        source_ref=f"cert:assignment:{name}")


def _worker_write(store: SQLiteMailStore, gateway: ToolGateway, workspace: Path,
                  workspace_id: str, task: dict, name: str, content: str) -> tuple[dict, dict]:
    request = {
        "task_id": task["task_id"], "agent_id": "command", "authorized_by": "command",
        "action_type": "WRITE_FILE", "working_dir": str(workspace),
        "authority_id": task["authority_id"], "source_request_id": f"cert:write:{name}",
        "workspace_id": workspace_id, "requested_operation": "WRITE_FILE",
        "created_at": iso_now(),
        "payload": {"path": f"{name}.txt", "content": content,
                    "idempotency_key": f"cert:write-key:{name}"},
    }
    event_id = store.append_event(SubstrateEvent(type="TOOL_REQUEST", origin_id="cert-owner",
        target_agent="command", payload={"request": request}))
    event = None
    for _ in range(10):
        candidate = store.claim_next_event("cert-worker", 0, target_agent="command",
                                           include_unrouted=False)
        if candidate is None:
            break
        if candidate.type == "TOOL_RESULT":
            store.ack_event(candidate.event_id, consumer_id="cert-worker")
            continue
        event = candidate
        break
    _require(event is not None and event.event_id == event_id, "Worker did not claim its durable request.")
    runtime = AgentRuntime(agent_id="command", mail_store=store, tool_gateway=gateway,
                           consumer_id="cert-worker")
    result = runtime.handle_event(event)
    _require(result.get("allowed") is True and bool(result.get("attempt_id")),
             f"Worker write failed: {result}")
    attempt_id = result["attempt_id"]
    store.publish_attempt_result(attempt_id)
    _require(store.ack_attempt_event(attempt_id, consumer_id="cert-worker"),
             "Worker result was not acknowledged.")
    return event.to_dict(), request


def certify(output_root: str | Path = "appshak_state/s1_certification") -> dict:
    run_root = Path(output_root).resolve() / f"run-{uuid.uuid4().hex[:12]}"
    repo = run_root / "repository"
    repo.mkdir(parents=True)
    checks: dict[str, str] = {}
    try:
        _git(repo, "init", "-q")
        _git(repo, "config", "user.email", "s1-certification@example.invalid")
        _git(repo, "config", "user.name", "S1 Certification")
        (repo / ".gitignore").write_text("workspaces/\n", encoding="utf-8")
        (repo / "evidence.md").write_text("S1 controlled certification evidence\n", encoding="utf-8")
        _git(repo, "add", ".gitignore", "evidence.md")
        _git(repo, "commit", "-q", "-m", "certification fixture")
        workspaces = WorkspaceManager(repo_root=repo, workspaces_root="workspaces")
        workspace = workspaces.ensure_worktrees(["command"])["command"]
        sentinel = workspace / "preserve-on-restart.txt"
        sentinel.write_text("preserved\n", encoding="utf-8")
        _require(workspaces.ensure_worktrees(["command"])["command"] == workspace
                 and sentinel.read_text(encoding="utf-8") == "preserved\n",
                 "WP1 workspace content did not survive repeated setup.")
        checks["WP1 workspace/authority"] = "PASS"

        db_path = run_root / "mailstore.db"
        store = SQLiteMailStore(db_path, lease_seconds=0.3, poll_interval=0.01)
        workspace_id = ToolGateway.workspace_identity("command", workspace)
        gateway = ToolGateway(mail_store=store, policy=ToolPolicy(chief_agent_id="command"),
                              workspace_roots={"command": workspace}, command_timeout_seconds=3)
        validator = ArtifactValidator(mail_store=store, tool_gateway=gateway)
        task = _create_task(store, workspace_id, "golden", "CERTIFIED")
        event, request = _worker_write(store, gateway, workspace, workspace_id,
                                       task, "golden", "CERTIFIED")
        ready = store.get_owner_task(task["task_id"])
        _require(ready["state"] == "READY_FOR_VALIDATION" and len(ready["artifacts"]) == 1,
                 "Real worker did not persist a ready task and artifact.")
        artifact = ready["artifacts"][0]
        _require(artifact["sha256"] == hashlib.sha256(b"CERTIFIED").hexdigest(),
                 "Artifact digest does not match the written bytes.")
        checks["WP3 durable task"] = "PASS"
        validation = validator.validate(task_id=task["task_id"], artifact_id=artifact["artifact_id"],
                                        source_request_id="cert:validation:golden")
        _require(validation["status"] == "PASSED"
                 and store.get_owner_task(task["task_id"])["state"] == "COMPLETE",
                 "Independent validation did not gate completion.")
        checks["WP4 persisted validation"] = "PASS"

        manager = VerifiedBatonManager(store, repo)
        baton = manager.create_baton(baton_id="BATON-0008", source_baton_id=None,
            task_id=task["task_id"], work_package="S1-WP6 integrated certification",
            next_objective="Post-S1 architecture review", git_commit=_git(repo, "rev-parse", "HEAD"),
            completion_status="COMPLETE", current_state={"task_state": "COMPLETE"},
            results={"golden_validation": "PASSED", "artifact_sha256": artifact["sha256"]},
            evidence_references=["evidence.md", "workspaces/command/golden.txt"],
            validation_id=validation["validation_id"], required_capability="ARCHITECTURAL_AUDIT",
            producer_id="system:s1-certification")
        verified = manager.verify_baton(baton["baton_id"])
        _require(verified["status"] == "VERIFIED", f"Baton verification failed: {verified['verification_reason']}")
        dispatch = manager.dispatch(baton["baton_id"], CapabilityRoutingPolicy.default())
        _require(dispatch["status"] == "WAITING_FOR_CAPABILITY" and dispatch["target_id"] is None,
                 "Unconfigured capability route did not wait honestly.")
        projection_path = run_root / "CURRENT_BATON.json"
        manager.write_current_projection(projection_path, baton["baton_id"])
        checks["WP5 verified baton/routing"] = "PASS"
        checks["next durable handoff"] = "PASS (WAITING_FOR_CAPABILITY)"

        office_before = read_office_state(db_path)
        _require(any(item["task_id"] == task["task_id"] and item["state"] == "COMPLETE"
                     for item in office_before["tasks"]), "Office state omitted the completed task.")
        _require(any(item["baton_id"] == baton["baton_id"]
                     and item["dispatch_status"] == "WAITING_FOR_CAPABILITY"
                     for item in office_before["batons"]), "Office state omitted the waiting baton.")

        # Reopen every durable component; no in-memory task or attempt is used below.
        store = SQLiteMailStore(db_path, lease_seconds=0.3, poll_interval=0.01)
        gateway = ToolGateway(mail_store=store, policy=ToolPolicy(chief_agent_id="command"),
                              workspace_roots={"command": workspace}, command_timeout_seconds=3)
        manager = VerifiedBatonManager(store, repo)
        reopened_task = store.get_owner_task(task["task_id"])
        reopened_baton = manager.get_baton(baton["baton_id"])
        _require(reopened_task["task_id"] == task["task_id"]
                 and reopened_task["assigned_agent"] == "command"
                 and reopened_task["workspace_id"] == workspace_id
                 and reopened_task["assignment_authority_id"] == task["authority_id"]
                 and reopened_task["state"] == "COMPLETE"
                 and reopened_task["attempts"][0]["attempt_id"] == ready["attempts"][0]["attempt_id"]
                 and reopened_task["artifacts"][0]["artifact_id"] == artifact["artifact_id"]
                 and reopened_task["artifacts"][0]["sha256"] == artifact["sha256"]
                 and reopened_task["validations"][0]["validation_id"] == validation["validation_id"]
                 and reopened_task["validations"][0]["status"] == "PASSED"
                 and reopened_baton["status"] == "VERIFIED"
                 and reopened_baton["source_baton_id"] is None
                 and reopened_baton["dispatch"]["dispatch_id"] == dispatch["dispatch_id"]
                 and reopened_baton["dispatch"]["context"] == dispatch["context"]
                 and sentinel.read_text(encoding="utf-8") == "preserved\n",
                 "Canonical task, evidence, baton or context changed across restart.")
        _require(json.loads(projection_path.read_text(encoding="utf-8"))["baton_id"] == baton["baton_id"],
                 "Current projection did not survive restart.")
        _require(read_office_state(db_path) == office_before,
                 "Office projection changed without canonical changes.")
        checks["restart recovery"] = "PASS"

        attempt_count = len(store.list_attempts())
        output = workspace / "golden.txt"
        write_time = output.stat().st_mtime_ns
        duplicate = AgentRuntime(agent_id="command", mail_store=store, tool_gateway=gateway,
                                 consumer_id="cert-worker").handle_event(SubstrateEvent.coerce(event))
        _require(duplicate["attempt_id"] == ready["attempts"][0]["attempt_id"]
                 and len(store.list_attempts()) == attempt_count
                 and output.stat().st_mtime_ns == write_time
                 and manager.dispatch(baton["baton_id"], CapabilityRoutingPolicy.default())["dispatch_id"]
                    == dispatch["dispatch_id"],
                 "Duplicate processing repeated a side effect or dispatch.")
        checks["duplicate prevention"] = "PASS"

        failed_task = _create_task(store, workspace_id, "negative", "A")
        _worker_write(store, gateway, workspace, workspace_id, failed_task, "negative", "B")
        negative_ready = store.get_owner_task(failed_task["task_id"])
        _require(negative_ready["state"] == "READY_FOR_VALIDATION"
                 and (workspace / "negative.txt").is_file(), "Negative artifact was not produced.")
        failed_validation = ArtifactValidator(mail_store=store, tool_gateway=gateway).validate(
            task_id=failed_task["task_id"], artifact_id=negative_ready["artifacts"][0]["artifact_id"],
            source_request_id="cert:validation:negative")
        _require(failed_validation["status"] == "FAILED"
                 and store.get_owner_task(failed_task["task_id"])["state"] != "COMPLETE",
                 "Wrong artifact completed its task.")
        rejected = manager.create_baton(baton_id="BATON-NEGATIVE", source_baton_id=None,
            task_id=failed_task["task_id"], work_package="negative certification",
            next_objective="must not dispatch", git_commit=_git(repo, "rev-parse", "HEAD"),
            completion_status="COMPLETE", current_state={"task_state": "COMPLETE"},
            results={"validation": "FAILED"}, evidence_references=["evidence.md"],
            validation_id=failed_validation["validation_id"], required_capability="IMPLEMENTATION",
            producer_id="system:s1-certification")
        _require(manager.verify_baton(rejected["baton_id"])["status"] == "REJECTED",
                 "Failed validation verified a success baton.")
        try:
            manager.dispatch(rejected["baton_id"], CapabilityRoutingPolicy.default())
        except ValueError:
            pass
        else:
            raise AssertionError("Rejected baton created a downstream dispatch.")
        checks["negative validation path"] = "PASS"

        uncertain_task = _create_task(store, workspace_id, "uncertain", "never accepted")
        uncertain_request = {
            "task_id": uncertain_task["task_id"], "agent_id": "command", "authorized_by": "command",
            "action_type": "WRITE_FILE", "working_dir": str(workspace),
            "authority_id": uncertain_task["authority_id"], "source_request_id": "cert:write:uncertain",
            "workspace_id": workspace_id, "requested_operation": "WRITE_FILE", "created_at": iso_now(),
            "payload": {"path": "uncertain.txt", "content": "unknown",
                        "idempotency_key": "cert:write-key:uncertain"},
        }
        req = gateway._coerce_request(uncertain_request)
        normalized = gateway.policy.validate(req, worktree_root=workspace).normalized_payload
        normalized.update({"authority_id": req.authority_id, "worker_id": req.agent_id,
                           "source_request_id": req.source_request_id, "workspace_id": req.workspace_id,
                           "requested_operation": req.requested_operation, "created_at": req.created_at})
        reserved = store.reserve_attempt(source_request_id=req.source_request_id, source_event_id=None,
            idempotency_key=uncertain_request["payload"]["idempotency_key"],
            authority_id=req.authority_id, agent_id=req.agent_id, workspace_id=req.workspace_id,
            requested_operation="WRITE_FILE", created_at=req.created_at, task_id=req.task_id,
            request={"working_dir": req.working_dir, "payload": normalized,
                     "authorized_by": req.authorized_by, "correlation_id": None,
                     "task_id": req.task_id})
        generation = store.begin_attempt(reserved["attempt_id"], "cert-stale-worker", 0.1)
        _require(generation is not None, "Uncertain attempt did not begin.")
        time.sleep(0.15)
        store = SQLiteMailStore(db_path, lease_seconds=0.3, poll_interval=0.01)
        _require(store.reconcile_attempts()["fenced_unknown"] == 1,
                 "Interrupted attempt did not reconcile to unknown.")
        _require(store.record_attempt_outcome(reserved["attempt_id"], "cert-stale-worker", generation,
            "SUCCEEDED", {"allowed": True}) is None,
            "Stale worker wrote authoritative success.")
        _require(store.get_owner_task(uncertain_task["task_id"])["state"] == "NEEDS_RECONCILIATION"
                 and store.get_attempt(reserved["attempt_id"])["state"] == "NEEDS_RECONCILIATION",
                 "Unknown effect advanced the task.")
        manager = VerifiedBatonManager(store, repo)
        unknown_baton = manager.create_baton(baton_id="BATON-UNKNOWN", source_baton_id=None,
            task_id=uncertain_task["task_id"], work_package="interrupted certification",
            next_objective="must not dispatch", git_commit=_git(repo, "rev-parse", "HEAD"),
            completion_status="COMPLETE", current_state={"task_state": "COMPLETE"},
            results={"attempt": "NEEDS_RECONCILIATION"}, evidence_references=["evidence.md"],
            validation_id="missing-validation", required_capability="IMPLEMENTATION",
            producer_id="system:s1-certification")
        _require(manager.verify_baton(unknown_baton["baton_id"])["status"] == "REJECTED",
                 "Unknown attempt verified a success baton.")
        try:
            manager.dispatch(unknown_baton["baton_id"], CapabilityRoutingPolicy.default())
        except ValueError:
            pass
        else:
            raise AssertionError("Unknown attempt created a downstream dispatch.")
        checks["WP2 execution recovery"] = "PASS"

        result = {"status": "PASS", "checks": checks, "run_root": str(run_root),
                  "database": str(db_path), "repository": str(repo),
                  "task_id": task["task_id"], "baton_id": baton["baton_id"],
                  "dispatch_id": dispatch["dispatch_id"], "dispatch_status": dispatch["status"],
                  "git_commit": _git(repo, "rev-parse", "HEAD")}
    except Exception as exc:
        result = {"status": "FAIL", "checks": checks, "run_root": str(run_root),
                  "error": f"{type(exc).__name__}: {exc}"}
    (run_root / "certification_result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the integrated S1 certification workflow.")
    parser.add_argument("--output-root", default="appshak_state/s1_certification")
    args = parser.parse_args()
    result = certify(args.output_root)
    for name, status in result["checks"].items():
        print(f"{name}: {status}")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
