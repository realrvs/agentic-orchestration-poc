"""
Prometheus metrics for Agentic Orchestration PoC.

Экспортирует метрики на порт 8002, которые скрейпит Prometheus.

Метрики:
- task_duration_seconds — время выполнения каждой задачи
- task_total — счётчик выполненных задач
- policy_decision_total — счётчик решений Policy Engine (ALLOW/DENY)
- llm_confidence — распределение confidence от LLM
- mcp_call_total — счётчик вызовов MCP Gateway
"""

import os
from prometheus_client import Counter, Histogram, Gauge, start_http_server


METRICS_PORT = int(os.getenv("METRICS_PORT", "8002"))


# ─── Metrics definitions ──────────────────────────────────────────

task_duration_seconds = Histogram(
    "task_duration_seconds",
    "Duration of each task handler in seconds",
    labelnames=["task_type"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10, 30, 60, 120),
)

task_total = Counter(
    "task_total",
    "Total number of tasks processed",
    labelnames=["task_type", "status"],
)

policy_decision_total = Counter(
    "policy_decision_total",
    "Total number of policy decisions",
    labelnames=["decision"],
)

llm_confidence = Histogram(
    "llm_confidence",
    "Distribution of LLM confidence scores",
    buckets=(0.0, 0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0),
)

mcp_call_total = Counter(
    "mcp_call_total",
    "Total number of MCP Gateway calls",
    labelnames=["status"],
)

active_instances = Gauge(
    "active_instances",
    "Number of currently active process instances",
)


# ─── Server ───────────────────────────────────────────────────────

def start_metrics_server() -> None:
    """Запустить HTTP-сервер для Prometheus scrape."""
    start_http_server(METRICS_PORT)
    print(f"[metrics] Prometheus metrics server started on port {METRICS_PORT}")
