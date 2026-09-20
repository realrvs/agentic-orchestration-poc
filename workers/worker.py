"""
Python worker for PoC Procurement Process.

Handles Service Tasks:
- validate-request: mock validation of incoming request
- approve-request: auto-approve (replaces User Task for PoC)
- llm-agent: LLM-based analysis via local Ollama (Mistral 7B)
- tool-executor: Policy Enforcement Point (RBAC + confidence threshold)
- mcp-gateway: MCP Gateway integration for legacy systems

Observability:
- OpenTelemetry tracing to Jaeger (localhost:4318)
- Langfuse LLM observability (localhost:3001)
- Prometheus metrics (localhost:8002)
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
from tracing import setup_tracing, span, set_success
from langfuse_client import llm_generation
from metrics import (
    start_metrics_server,
    task_duration_seconds,
    task_total,
    policy_decision_total,
    llm_confidence,
    mcp_call_total,
)


CAMUNDA_ADDRESS = os.getenv("CAMUNDA_ZEEBE_GATEWAY_ADDRESS", "localhost:26500")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral:7b-instruct-q4_K_M")
MCP_GATEWAY_URL = os.getenv("MCP_GATEWAY_URL", "http://localhost:8000")

LLM_AGENT_SVID = "spiffe://company.ru/agents/llm_agent_v1"


# ─── Task handlers ────────────────────────────────────────────────

async def handle_validate_request(job: Job) -> dict[str, Any]:
    """Validate incoming procurement request."""
    variables = job.variables
    request_id = variables.get("request_id", "unknown")
    amount = variables.get("amount", 0)
    comment = variables.get("comment", "")
    trace_id = variables.get("trace_id")

    with task_duration_seconds.labels(task_type="validate-request").time():
        with span("validate-request", trace_id=trace_id, attributes={
            "request_id": request_id,
            "amount": amount,
        }) as current_span:
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
                set_success(current_span, valid=False, reason=reason)
                task_total.labels(task_type="validate-request", status="invalid").inc()
                return {"valid": False, "validation_reason": reason}

            print(f"[validate-request] VALID")
            set_success(current_span, valid=True)
            task_total.labels(task_type="validate-request", status="success").inc()
            return {"valid": True, "validation_reason": "All checks passed"}


async def handle_approve_request(job: Job) -> dict[str, Any]:
    """Auto-approve for PoC testing (replaces User Task)."""
    variables = job.variables
    trace_id = variables.get("trace_id")

    with task_duration_seconds.labels(task_type="approve-request").time():
        with span("approve-request", trace_id=trace_id) as current_span:
            print(f"[approve-request] Auto-approving request")
            set_success(current_span, approved=True)
            task_total.labels(task_type="approve-request", status="success").inc()
            return {"approved": True}


async def handle_llm_agent(job: Job) -> dict[str, Any]:
    """
    LLM agent - analyze request using local Ollama.

    Traced to Jaeger (timing), Langfuse (content), Prometheus (metrics).
    """
    variables = job.variables
    amount = variables.get("amount", 0)
    comment = variables.get("comment", "")
    valid = variables.get("valid", False)
    trace_id = variables.get("trace_id")

    with task_duration_seconds.labels(task_type="llm-agent").time():
        with span("llm-agent", trace_id=trace_id, attributes={
            "model": OLLAMA_MODEL,
            "amount": amount,
        }) as current_span:
            if not valid:
                print(f"[llm-agent] Skipping - request is invalid")
                set_success(current_span, decision="skip")
                task_total.labels(task_type="llm-agent", status="skipped").inc()
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

            with llm_generation(
                name="llm-agent",
                model=OLLAMA_MODEL,
                input_data={"prompt": prompt, "amount": amount, "comment": comment},
                metadata={
                    "trace_id": trace_id or "unknown",
                    "agent_svid": LLM_AGENT_SVID,
                },
            ) as gen:
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

                    gen["output"] = parsed
                    gen["usage"] = {
                        "input": data.get("prompt_eval_count", 0),
                        "output": data.get("eval_count", 0),
                        "unit": "TOKENS",
                    }
                    gen["metadata"] = {
                        "decision": decision,
                        "confidence": confidence,
                    }

                    llm_confidence.observe(confidence)
                    task_total.labels(task_type="llm-agent", status="success").inc()

                    set_success(current_span, decision=decision, confidence=confidence)
                    return {
                        "llm_decision": decision,
                        "llm_confidence": confidence,
                        "llm_reasoning": reasoning,
                        "agent_svid": LLM_AGENT_SVID,
                    }

                except Exception as e:
                    print(f"[llm-agent] ERROR: {e}")
                    current_span.set_attribute("error", str(e))
                    gen["output"] = {"error": str(e)}
                    task_total.labels(task_type="llm-agent", status="error").inc()
                    return {
                        "llm_decision": "error",
                        "llm_confidence": 0.0,
                        "llm_reasoning": str(e),
                        "agent_svid": LLM_AGENT_SVID,
                    }


async def handle_tool_executor(job: Job) -> dict[str, Any]:
    """
    Policy Enforcement Point - validate LLM recommendation.
    """
    variables = job.variables
    llm_decision = variables.get("llm_decision", "unknown")
    llm_confidence_val = float(variables.get("llm_confidence", 0.0))
    llm_reasoning = variables.get("llm_reasoning", "")
    agent_svid = variables.get("agent_svid", LLM_AGENT_SVID)
    trace_id = variables.get("trace_id")

    with task_duration_seconds.labels(task_type="tool-executor").time():
        with span("tool-executor", trace_id=trace_id, attributes={
            "confidence": llm_confidence_val,
            "svid": agent_svid,
        }) as current_span:
            print(f"[tool-executor] Evaluating recommendation:")
            print(f"  decision   = {llm_decision}")
            print(f"  confidence = {llm_confidence_val}")
            print(f"  svid       = {agent_svid}")

            try:
                dto = RecommendationDTO(
                    tool_name=ToolName.SEND_NOTIFICATION,
                    confidence=llm_confidence_val,
                    reasoning=llm_reasoning or "no reasoning provided",
                    parameters={},
                    agent_svid=agent_svid,
                )
            except Exception as e:
                print(f"[tool-executor] INVALID DTO: {e}")
                policy_decision_total.labels(decision="DENY").inc()
                task_total.labels(task_type="tool-executor", status="error").inc()
                set_success(current_span, decision="DENY", reason="invalid_dto")
                return {
                    "policy_decision": "DENY",
                    "policy_reason": f"Invalid RecommendationDTO: {e}",
                }

            reasons = []
            allowed = True

            if dto.agent_svid not in ALLOWED_SVIDS:
                allowed = False
                reasons.append(f"SVID not in allow-list: {dto.agent_svid}")
            else:
                reasons.append("SVID OK")

            if dto.confidence < CONFIDENCE_THRESHOLD:
                allowed = False
                reasons.append(
                    f"Confidence {dto.confidence:.2f} < threshold {CONFIDENCE_THRESHOLD:.2f}"
                )
            else:
                reasons.append(f"Confidence OK ({dto.confidence:.2f})")

            reasons.append(f"Tool OK ({dto.tool_name.value})")

            if dto.confidence < CONFIDENCE_THRESHOLD and llm_decision == "approve":
                allowed = False
                reasons.append("LLM approved but confidence below threshold")

            policy_reason = "; ".join(reasons)
            policy_decision = "ALLOW" if allowed else "DENY"

            print(f"[tool-executor] Policy decision: {policy_decision}")
            print(f"[tool-executor] Reason: {policy_reason}")

            audit_entry = {
                "agent_svid": dto.agent_svid,
                "tool": dto.tool_name.value,
                "confidence": dto.confidence,
                "decision": policy_decision,
                "reason": policy_reason,
            }
            print(f"[AUDIT] {json.dumps(audit_entry, ensure_ascii=False)}")

            policy_decision_total.labels(decision=policy_decision).inc()
            task_total.labels(task_type="tool-executor", status="success").inc()

            set_success(current_span, decision=policy_decision)
            return {
                "policy_decision": policy_decision,
                "policy_reason": policy_reason,
            }


async def handle_mcp_gateway(job: Job) -> dict[str, Any]:
    """MCP Gateway - call legacy systems via MCP."""
    variables = job.variables
    policy_decision = variables.get("policy_decision", "DENY")
    amount = variables.get("amount", 0)
    comment = variables.get("comment", "")
    trace_id = variables.get("trace_id")

    with task_duration_seconds.labels(task_type="mcp-gateway").time():
        with span("mcp-gateway", trace_id=trace_id, attributes={
            "policy_decision": policy_decision,
        }) as current_span:
            print(f"[mcp-gateway] Policy decision: {policy_decision}")

            if policy_decision != "ALLOW":
                print(f"[mcp-gateway] Skipping - policy decision is {policy_decision}")
                mcp_call_total.labels(status="skipped").inc()
                task_total.labels(task_type="mcp-gateway", status="skipped").inc()
                set_success(current_span, status="SKIPPED")
                return {
                    "mcp_status": "SKIPPED",
                    "mcp_reason": f"Policy decision was {policy_decision}",
                }

            print(f"[mcp-gateway] Calling MCP Gateway at {MCP_GATEWAY_URL}...")

            rpc_payload = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "publish_notice",
                    "arguments": {
                        "title": comment,
                        "amount": float(amount),
                        "region": "Moscow",
                    },
                },
                "id": 1,
            }

            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        f"{MCP_GATEWAY_URL}/mcp/messages",
                        json=rpc_payload,
                        headers={
                            "Content-Type": "application/json",
                            "X-Agent-SVID": LLM_AGENT_SVID,
                        },
                    )
                    response.raise_for_status()
                    data = response.json()

                content = data.get("result", {}).get("content", [])
                if content and len(content) > 0:
                    raw_text = content[0].get("text", "{}")
                    mcp_result = json.loads(raw_text)
                else:
                    mcp_result = {"status": "UNKNOWN"}

                status = mcp_result.get("status", "UNKNOWN")
                notice_id = mcp_result.get("notice_id", "N/A")
                message = mcp_result.get("message", "")

                print(f"[mcp-gateway] MCP status: {status}")
                print(f"[mcp-gateway] Notice ID: {notice_id}")

                mcp_call_total.labels(status=status.lower()).inc()
                task_total.labels(task_type="mcp-gateway", status="success").inc()

                set_success(current_span, status=status, notice_id=notice_id)
                return {
                    "mcp_status": status,
                    "mcp_notice_id": notice_id,
                    "mcp_message": message,
                }

            except Exception as e:
                print(f"[mcp-gateway] ERROR: {e}")
                current_span.set_attribute("error", str(e))
                mcp_call_total.labels(status="error").inc()
                task_total.labels(task_type="mcp-gateway", status="error").inc()
                return {
                    "mcp_status": "ERROR",
                    "mcp_reason": str(e),
                }


# ─── Main ─────────────────────────────────────────────────────────

async def main() -> None:
    setup_tracing()
    start_metrics_server()

    print(f"Connecting to Zeebe at {CAMUNDA_ADDRESS}...")
    hostname, port = CAMUNDA_ADDRESS.split(":")
    channel = create_insecure_channel(hostname=hostname, port=int(port))
    worker = ZeebeWorker(channel)

    worker.task(task_type="validate-request")(handle_validate_request)
    worker.task(task_type="approve-request")(handle_approve_request)
    worker.task(task_type="llm-agent")(handle_llm_agent)
    worker.task(task_type="tool-executor")(handle_tool_executor)
    worker.task(task_type="mcp-gateway")(handle_mcp_gateway)

    print("Worker started. Listening for tasks:")
    print("  - validate-request")
    print("  - approve-request")
    print(f"  - llm-agent (model: {OLLAMA_MODEL})")
    print("  - tool-executor (Policy Enforcement Point)")
    print(f"  - mcp-gateway (MCP Gateway: {MCP_GATEWAY_URL})")
    print()

    await worker.work()


if __name__ == "__main__":
    asyncio.run(main())