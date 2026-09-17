"""
Python worker for PoC Procurement Process.

Handles Service Tasks:
- validate-request: mock validation of incoming request
- approve-request: auto-approve (replaces User Task for PoC)
- llm-agent: LLM-based analysis via local Ollama
- tool-executor: Policy Enforcement Point (RBAC + confidence threshold)

Connects to Camunda 8 Zeebe via gRPC (localhost:26500).
"""

import asyncio
import json
import os
from typing import Any

import httpx
from pyzeebe import ZeebeWorker, Job
from pyzeebe.channel import create_insecure_channel

from tool_contract import (
    RecommendationDTO,
    ToolName,
    CONFIDENCE_THRESHOLD,
    ALLOWED_SVIDS,
)


CAMUNDA_ADDRESS = os.getenv("CAMUNDA_ZEEBE_GATEWAY_ADDRESS", "localhost:26500")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral:7b-instruct-q4_K_M")

LLM_AGENT_SVID = "spiffe://company.ru/agents/llm_agent_v1"


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
    LLM agent - analyze request using local Ollama.

    Input: amount, comment, valid
    Output: llm_decision, llm_confidence, llm_reasoning, agent_svid
    """
    variables = job.variables
    amount = variables.get("amount", 0)
    comment = variables.get("comment", "")
    valid = variables.get("valid", False)

    if not valid:
        print(f"[llm-agent] Skipping - request is invalid")
        return {
            "llm_decision": "skip",
            "llm_confidence": 0.0,
            "llm_reasoning": "Request was invalid",
            "agent_svid": LLM_AGENT_SVID,
        }

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
            "agent_svid": LLM_AGENT_SVID,
        }

    except Exception as e:
        print(f"[llm-agent] ERROR: {e}")
        return {
            "llm_decision": "error",
            "llm_confidence": 0.0,
            "llm_reasoning": str(e),
            "agent_svid": LLM_AGENT_SVID,
        }


async def handle_tool_executor(job: Job) -> dict[str, Any]:
    """
    Policy Enforcement Point - validate LLM recommendation.

    Input:
        llm_decision, llm_confidence, llm_reasoning, agent_svid

    Output:
        policy_decision (ALLOW/DENY), policy_reason
    """
    variables = job.variables
    llm_decision = variables.get("llm_decision", "unknown")
    llm_confidence = float(variables.get("llm_confidence", 0.0))
    llm_reasoning = variables.get("llm_reasoning", "")
    agent_svid = variables.get("agent_svid", LLM_AGENT_SVID)

    print(f"[tool-executor] Evaluating recommendation:")
    print(f"  decision   = {llm_decision}")
    print(f"  confidence = {llm_confidence}")
    print(f"  svid       = {agent_svid}")

    # Build RecommendationDTO
    try:
        dto = RecommendationDTO(
            tool_name=ToolName.SEND_NOTIFICATION,
            confidence=llm_confidence,
            reasoning=llm_reasoning or "no reasoning provided",
            parameters={},
            agent_svid=agent_svid,
        )
    except Exception as e:
        print(f"[tool-executor] INVALID DTO: {e}")
        return {
            "policy_decision": "DENY",
            "policy_reason": f"Invalid RecommendationDTO: {e}",
        }

    # Policy checks
    reasons = []
    allowed = True

    # 1. SVID check (RBAC)
    if dto.agent_svid not in ALLOWED_SVIDS:
        allowed = False
        reasons.append(f"SVID not in allow-list: {dto.agent_svid}")
    else:
        reasons.append("SVID OK")

    # 2. Confidence threshold
    if dto.confidence < CONFIDENCE_THRESHOLD:
        allowed = False
        reasons.append(
            f"Confidence {dto.confidence:.2f} < threshold {CONFIDENCE_THRESHOLD:.2f}"
        )
    else:
        reasons.append(f"Confidence OK ({dto.confidence:.2f})")

    # 3. Tool allow-list (enforced by enum)
    reasons.append(f"Tool OK ({dto.tool_name.value})")

    # 4. Decision consistency
    if dto.confidence < CONFIDENCE_THRESHOLD and llm_decision == "approve":
        allowed = False
        reasons.append("LLM approved but confidence below threshold")

    policy_reason = "; ".join(reasons)
    policy_decision = "ALLOW" if allowed else "DENY"

    print(f"[tool-executor] Policy decision: {policy_decision}")
    print(f"[tool-executor] Reason: {policy_reason}")

    # Audit log
    audit_entry = {
        "agent_svid": dto.agent_svid,
        "tool": dto.tool_name.value,
        "confidence": dto.confidence,
        "decision": policy_decision,
        "reason": policy_reason,
    }
    print(f"[AUDIT] {json.dumps(audit_entry, ensure_ascii=False)}")

    return {
        "policy_decision": policy_decision,
        "policy_reason": policy_reason,
    }


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
    print("  - tool-executor (Policy Enforcement Point)")
    print()

    await worker.work()


if __name__ == "__main__":
    asyncio.run(main())