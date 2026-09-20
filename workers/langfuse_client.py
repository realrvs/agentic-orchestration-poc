"""
Langfuse client for LLM observability.

Обёртка над Langfuse SDK для трейсинга LLM-вызовов:
- Input / Output
- Token usage
- Cost
- Latency
"""

import os
from contextlib import contextmanager
from typing import Iterator

from langfuse import Langfuse
from dotenv import load_dotenv
load_dotenv()


_langfuse_client: Langfuse | None = None


def get_langfuse() -> Langfuse:
    """Получить singleton Langfuse client."""
    global _langfuse_client

    if _langfuse_client is None:
        _langfuse_client = Langfuse(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
            host=os.getenv("LANGFUSE_HOST", "http://localhost:3001"),
        )

    return _langfuse_client


@contextmanager
def llm_generation(
    name: str,
    model: str,
    input_data: dict | str,
    metadata: dict | None = None,
) -> Iterator[dict]:
    """
    Контекстный менеджер для логирования LLM generation.

    Usage:
        with llm_generation("llm-agent", "mistral:7b", {"prompt": "..."}) as gen:
            response = call_llm(...)
            gen["output"] = response
            gen["usage"] = {"input": 100, "output": 50}
    """
    client = get_langfuse()

    # Создать trace
    trace = client.trace(
        name=name,
        metadata=metadata or {},
    )

    # Создать generation (span для LLM-вызова)
    generation = trace.generation(
        name=name,
        model=model,
        input=input_data,
    )

    result: dict = {}

    try:
        yield result
        generation.end(
            output=result.get("output"),
            usage=result.get("usage"),
            metadata=result.get("metadata", {}),
        )
    except Exception as e:
        generation.end(
            output={"error": str(e)},
            level="ERROR",
        )
        raise
