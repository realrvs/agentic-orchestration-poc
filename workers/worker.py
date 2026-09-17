"""
Python worker for PoC Procurement Process.

Handles Service Tasks:
- validate-request: mock validation of incoming request
- llm-agent: LLM-based analysis (stub, will be implemented later)
- tool-executor: policy enforcement (stub, will be implemented later)

Connects to Camunda 8 Zeebe via gRPC (localhost:26500).
"""

import asyncio
import os
from typing import Any

from pyzeebe import ZeebeWorker, Job
from pyzeebe.channel import create_insecure_channel


CAMUNDA_ADDRESS = os.getenv("CAMUNDA_ZEEBE_GATEWAY_ADDRESS", "localhost:26500")


# ─── Task handlers ────────────────────────────────────────────────

async def handle_validate_request(job: Job) -> dict[str, Any]:
    """
    Validate incoming procurement request.

    Input variables:
        request_id (str)   — request identifier
        amount (number)    — procurement amount
        comment (str)      — requester comment

    Output variables:
        valid (bool)       — validation result
        validation_reason  — explanation
    """
    variables = job.variables
    request_id = variables.get("request_id", "unknown")
    amount = variables.get("amount", 0)
    comment = variables.get("comment", "")

    print(f"[validate-request] Processing request_id={request_id}, "
          f"amount={amount}, comment='{comment}'")

    # Mock validation logic
    errors = []
    if not request_id or request_id == "unknown":
        errors.append("request_id is missing")
    if amount <= 0:
        errors.append(f"amount must be positive (got {amount})")
    if not comment or len(comment.strip()) < 3:
        errors.append("comment must be at least 3 characters")

    if errors:
        reason = "; ".join(errors)
        print(f"[validate-request] ❌ INVALID: {reason}")
        return {
            "valid": False,
            "validation_reason": reason,
        }

    print(f"[validate-request] ✅ VALID")
    return {
        "valid": True,
        "validation_reason": "All checks passed",
    }

async def handle_approve_request(job: Job) -> dict[str, Any]:
    """
    Auto-approve for PoC testing (replaces User Task).
    
    Output variables:
        approved (bool) — auto-approve = true
    """
    print(f"[approve-request] ✅ Auto-approving request")
    return {
        "approved": True,
    }

async def handle_llm_agent(job: Job) -> dict[str, Any]:
    """Stub for LLM agent. Will be implemented later."""
    print(f"[llm-agent] ⏳ Stub called (not yet implemented)")
    return {
        "llm_decision": "stub",
        "llm_confidence": 0.0,
    }


async def handle_tool_executor(job: Job) -> dict[str, Any]:
    """Stub for tool executor. Will be implemented later."""
    print(f"[tool-executor] ⏳ Stub called (not yet implemented)")
    return {
        "policy_decision": "stub",
    }


# ─── Main ─────────────────────────────────────────────────────────

async def main() -> None:
    print(f"Connecting to Zeebe at {CAMUNDA_ADDRESS}...")
    hostname, port = CAMUNDA_ADDRESS.split(":")
    channel = create_insecure_channel(hostname=hostname, port=int(port))
    worker = ZeebeWorker(channel)

    # Register task handlers
    worker.task(task_type="validate-request")(handle_validate_request)
    worker.task(task_type="approve-request")(handle_approve_request)
    worker.task(task_type="llm-agent")(handle_llm_agent)
    worker.task(task_type="tool-executor")(handle_tool_executor)

    print("Worker started. Listening for tasks:")
    print("  - validate-request")
    print("  - approve-request")
    print("  - llm-agent")
    print("  - tool-executor")

    await worker.work()


if __name__ == "__main__":
    asyncio.run(main())