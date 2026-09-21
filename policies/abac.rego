package tool_executor

import future.keywords.if
import future.keywords.in

# ─── Default decision ─────────────────────────────────────────────
default allow = false

# ─── Main policy ──────────────────────────────────────────────────
allow if {
    rbac_pass
    confidence_pass
    tool_allowed
    attributes_pass
}

# ─── RBAC (Role-Based Access Control) ─────────────────────────────
rbac_pass if {
    input.agent_svid in data.allowed_svids
}

# ─── Confidence threshold ─────────────────────────────────────────
confidence_pass if {
    input.confidence >= data.confidence_threshold
}

# ─── Tool allow-list ──────────────────────────────────────────────
tool_allowed if {
    input.tool_name in data.allowed_tools
}

# ─── ABAC (Attribute-Based Access Control) ────────────────────────
attributes_pass if {
    amount_pass
    region_pass
    category_pass
}

amount_pass if {
    input.amount <= data.limits.max_amount
}

region_pass if {
    input.region in data.limits.allowed_regions
}

category_pass if {
    input.category in data.limits.allowed_categories
}

# ─── Escalation rules ─────────────────────────────────────────────
escalate if {
    input.amount > data.limits.max_amount
}

escalate if {
    input.confidence < data.confidence_threshold
}

escalate if {
    input.category == "classified"
}

# ─── Reason for decision ──────────────────────────────────────────
reason = msg if {
    not rbac_pass
    msg := "RBAC failed: SVID not in allow-list"
}

reason = msg if {
    rbac_pass
    not confidence_pass
    msg := sprintf("Confidence %.2f below threshold %.2f", [
        input.confidence,
        data.confidence_threshold,
    ])
}

reason = msg if {
    rbac_pass
    confidence_pass
    not tool_allowed
    msg := sprintf("Tool '%s' not in allow-list", [input.tool_name])
}

reason = msg if {
    rbac_pass
    confidence_pass
    tool_allowed
    not amount_pass
    msg := sprintf("Amount %d exceeds limit %d", [
        input.amount,
        data.limits.max_amount,
    ])
}

reason = msg if {
    rbac_pass
    confidence_pass
    tool_allowed
    amount_pass
    not region_pass
    msg := sprintf("Region '%s' not allowed", [input.region])
}

reason = msg if {
    allow
    msg := "All checks passed"
}