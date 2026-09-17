"""
Python worker for PoC Procurement Process.

Handles Service Tasks:
- validate-request: mock validation of incoming request
- approve-request: auto-approve (replaces User Task for PoC)
- llm-agent: LLM-based analysis via local Ollama
- tool-executor: policy enforcement (stub, will be implemented later)

Connects to Camunda 8 Zeebe via gRPC (localhost:26500).
"""

import asyncio
import json
import os
from typing import Any

import httpx
from pyzeebe import ZeebeWorker, Job
from pyzeebe.channel import create_insecure_channel


CAMUNDA_ADDRESS = os.getenv("CAMUNDA_ZEEBE_GATEWAY_ADDRESS", "localhost:26500")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral:7b-instruct-q4_K_M")


# ─── Task handlers ────────────────────────────────────────────────

async def handle_validate_request(job: Job) -> dict[str, Any]:
    """Validate incoming procurement request."""
    variables = job.variables
    request_id = variables.get("request_id", "unknown")
    amount = variables.get("amount", 0)
    comment = variables.get("comment", "")

    print(f"[validate-request] Processing request_id={request_id}, "
          f"amount={amount}, comment='{comment}'")

    errors = []
    if not request_id or request_id == "unknown":
        errors.append("request_id is missing")
    if amount <= 0:
        errors.append(f"amount must be positive (got {amount})")
    if not comment or len(comment.strip()) < 3:
        errors.append("comment must be at least 3 characters")

    if errors:
        reason = "; ".join(errors)
        print(f"[validate-request] INVALID: {reason}")
        return {"valid": False, "validation_reason": reason}

    print(f"[validate-request] VALID")
    return {"valid": True, "validation_reason": "All checks passed"}


async def handle_approve_request(job: Job) -> dict[str, Any]:
    """Auto-approve for PoC testing (replaces User Task)."""
    print(f"[approve-request] Auto-approving request")
    return {"approved": True}


async def handle_llm_agent(job: Job) -> dict[str, Any]:
    """
    LLM agent — analyze request using local Ollama.

    Input: amount, comment, valid
    Output: llm_decision, llm_confidence, llm_reasoning
    """
    variables = job.variables
    amount = variables.get("amount", 0)
    comment = variables.get("comment", "")
    valid = variables.get("valid", False)

    if not valid:
        print(f"[llm-agent] Skipping - request is invalid")
        return {"llm_decision": "skip", "llm_confidence": 0.0}

    prompt = (
        f"You are a procurement committee agent. Analyze the request:\n"
        f"- Amount: {amount} RUB\n"
        f"- Comment: {comment}\n\n"
        f"Respond with strict JSON only (no markdown):\n"
        f'{{"decision": "approve" or "reject", '
        f'"confidence": number from 0 to 1, '
        f'"reasoning": "brief justification"}}'
    )

    print(f"[llm-agent] Sending prompt to Ollama ({OLLAMA_MODEL})...")

    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(
                f"{OLLAMA_HOST}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                },
            )
            response.raise_for_status()
            data = response.json()

        raw_response = data.get("response", "{}")
        print(f"[llm-agent] Ollama response: {raw_response[:300]}")

        parsed = json.loads(raw_response)

        decision = parsed.get("decision", "unknown")
        confidence = float(parsed.get("confidence", 0.0))
        reasoning = parsed.get("reasoning", "")

        print(f"[llm-agent] LLM decision: {decision} (confidence: {confidence})")

        return {
            "llm_decision": decision,
            "llm_confidence": confidence,
            "llm_reasoning": reasoning,
        }

    except Exception as e:
        print(f"[llm-agent] ERROR: {e}")
        return {
            "llm_decision": "error",
            "llm_confidence": 0.0,
            "llm_reasoning": str(e),
        }


async def handle_tool_executor(job: Job) -> dict[str, Any]:
    """Stub for tool executor. Will be implemented later."""
    print(f"[tool-executor] Stub called (not yet implemented)")
    return {"policy_decision": "stub"}


# ─── Main ─────────────────────────────────────────────────────────

async def main() -> None:
    print(f"Connecting to Zeebe at {CAMUNDA_ADDRESS}...")
    hostname, port = CAMUNDA_ADDRESS.split(":")
    channel = create_insecure_channel(hostname=hostname, port=int(port))
    worker = ZeebeWorker(channel)

    worker.task(task_type="validate-request")(handle_validate_request)
    worker.task(task_type="approve-request")(handle_approve_request)
    worker.task(task_type="llm-agent")(handle_llm_agent)
    worker.task(task_type="tool-executor")(handle_tool_executor)

    print("Worker started. Listening for tasks:")
    print("  - validate-request")
    print("  - approve-request")
    print(f"  - llm-agent (model: {OLLAMA_MODEL})")
    print("  - tool-executor")
    print()

    await worker.work()


if __name__ == "__main__":
    asyncio.run(main())