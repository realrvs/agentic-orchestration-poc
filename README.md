\# Agentic Orchestration PoC



\*\*Proof of Concept\*\* для архитектурного blueprint \[enterprise-agent-orchestration-blueprint](https://github.com/realrvs/enterprise-agent-orchestration-blueprint).



Демонстрирует гибридную оркестрацию:

\- \*\*Camunda 8.8\*\* — детерминированный BPMN-каркас

\- \*\*LangGraph\*\* — семантические LLM-агенты (план)

\- \*\*MCP Gateway\*\* — интеграция с legacy (план)

\- \*\*WIMSE-идентичность\*\* — безопасность агентов (план)

\- \*\*Policy Enforcement Point\*\* — RBAC + confidence threshold (план)



\---



\## Статус



| Компонент | Статус |

|---|---|

| Docker Compose (Camunda + ES + PostgreSQL) | ✅ Работает |

| Operate / Tasklist | ✅ Доступны на `localhost:8888` |

| BPMN-процесс | ⏳ В работе |

| LLM-агент (LangGraph) | ⏳ В работе |

| Tool Executor (Policy) | ⏳ В работе |

| MCP Gateway | ⏳ В работе |

| Audit log | ⏳ В работе |



\---



\## Запуск



\### Требования



\- Docker Desktop \*\*≥ 4.89\*\* (с Compose v5+)

\- \*\*≥ 8 GB RAM\*\* для Docker

\- \*\*≥ 60 GB\*\* свободного места



\### Core-профиль (Camunda + ES + PostgreSQL)



```powershell

docker compose --profile core up -d

