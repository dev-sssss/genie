import os
from app.utils.file_utils import (
    read_file_safe, find_file_anywhere,
    find_files_by_extension
)


def detect_monitoring(repo_path: str, language: str) -> dict:
    """Detect monitoring, observability and logging tools."""
    result = {
        "has_prometheus": False,
        "has_grafana": False,
        "has_opentelemetry": False,
        "has_datadog": False,
        "has_newrelic": False,
        "has_cloudwatch": False,
        "has_sentry": False,
        "has_elk": False,
        "tools_detected": []
    }

    # Collect all dependency content
    dep_files = [
        "requirements.txt", "package.json", "pom.xml",
        "build.gradle", "go.mod", "docker-compose.yml",
        "docker-compose.yaml"
    ]
    combined = ""
    for f in dep_files:
        path = find_file_anywhere(repo_path, f)
        if path:
            combined += read_file_safe(path)

    # Scan source files too
    if language == "Python":
        for pf in find_files_by_extension(repo_path, ".py")[:20]:
            combined += read_file_safe(pf)
    if language == "Node.js":
        for jf in find_files_by_extension(repo_path, ".js")[:20]:
            combined += read_file_safe(jf)

    # Prometheus
    if any(kw in combined for kw in [
        "prometheus", "prom-client", "prometheus_client",
        "prometheus.yml", "promtheus"
    ]):
        result["has_prometheus"] = True
        result["tools_detected"].append("Prometheus")

    # Grafana
    if "grafana" in combined:
        result["has_grafana"] = True
        result["tools_detected"].append("Grafana")

    # OpenTelemetry
    if any(kw in combined for kw in [
        "opentelemetry", "otel", "@opentelemetry"
    ]):
        result["has_opentelemetry"] = True
        result["tools_detected"].append("OpenTelemetry")

    # Datadog
    if any(kw in combined for kw in [
        "datadog", "dd-trace", "ddtrace"
    ]):
        result["has_datadog"] = True
        result["tools_detected"].append("Datadog")

    # New Relic
    if any(kw in combined for kw in [
        "newrelic", "new-relic", "new_relic"
    ]):
        result["has_newrelic"] = True
        result["tools_detected"].append("New Relic")

    # CloudWatch
    if any(kw in combined for kw in [
        "cloudwatch", "aws-cloudwatch", "boto3"
    ]):
        result["has_cloudwatch"] = True
        result["tools_detected"].append("CloudWatch")

    # Sentry
    if any(kw in combined for kw in [
        "sentry", "@sentry", "sentry-sdk"
    ]):
        result["has_sentry"] = True
        result["tools_detected"].append("Sentry")

    # ELK Stack
    if any(kw in combined for kw in [
        "elasticsearch", "logstash", "kibana", "elastic"
    ]):
        result["has_elk"] = True
        result["tools_detected"].append("ELK Stack")

    return result
