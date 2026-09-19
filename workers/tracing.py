"""
OpenTelemetry tracing setup for Agentic Orchestration PoC.

Настраивает OTLP exporter в Jaeger (localhost:4318).
Предоставляет helper для создания спанов в worker'ах.
"""

import os
from contextlib import contextmanager
from typing import Iterator

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Span, Status, StatusCode


JAEGER_ENDPOINT = os.getenv(
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "http://localhost:4318/v1/traces",
)

SERVICE_NAME = "agentic-orchestration-worker"


def setup_tracing() -> None:
    """Инициализировать OTel tracer с экспортом в Jaeger."""
    resource = Resource.create({
        "service.name": SERVICE_NAME,
        "service.version": "1.0.0",
        "deployment.environment": "poc",
    })

    provider = TracerProvider(resource=resource)

    exporter = OTLPSpanExporter(endpoint=JAEGER_ENDPOINT, timeout=10)
    provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)

    print(f"[tracing] Jaeger endpoint: {JAEGER_ENDPOINT}")
    print(f"[tracing] Service name: {SERVICE_NAME}")


def get_tracer():
    """Получить tracer для создания спанов."""
    return trace.get_tracer(SERVICE_NAME)


@contextmanager
def span(
    name: str,
    trace_id: str | None = None,
    attributes: dict | None = None,
) -> Iterator[Span]:
    """Контекстный менеджер для создания спана."""
    tracer = get_tracer()

    with tracer.start_as_current_span(name) as current_span:
        if trace_id:
            current_span.set_attribute("bpmn.trace_id", trace_id)

        if attributes:
            for key, value in attributes.items():
                current_span.set_attribute(key, value)

        try:
            yield current_span
        except Exception as e:
            current_span.set_status(Status(StatusCode.ERROR, str(e)))
            current_span.record_exception(e)
            raise


def set_success(current_span: Span, **result: object) -> None:
    """Пометить спан как успешный и записать результат."""
    current_span.set_status(Status(StatusCode.OK))
    for key, value in result.items():
        current_span.set_attribute(f"result.{key}", str(value))
