"""Comportements HTTP transverses. Aucune base : l'URL pointe vers une adresse morte."""

from __future__ import annotations

import json
import logging

from fastapi import FastAPI
from pydantic import BaseModel, Field

from blackforge_api.core.ratelimit import TokenBuckets
from tests.conftest import make_settings, running_app


class _Credentials(BaseModel):
    password: str = Field(min_length=12)


def _add_test_routes(app: FastAPI) -> None:
    @app.post("/api/v1/_test/credentials")
    async def credentials(body: _Credentials) -> dict[str, bool]:  # pragma: no cover
        return {"ok": bool(body.password)}

    @app.get("/api/v1/_test/boom")
    async def boom() -> None:
        raise RuntimeError("detail-interne-confidentiel postgresql://svc:pw-secret@db/x")


async def test_liveness_does_not_depend_on_database() -> None:
    async with running_app(make_settings()) as client:
        response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_reports_503_without_leaking_connection_details() -> None:
    async with running_app(make_settings()) as client:
        response = await client.get("/readyz")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "unavailable"}
    assert "nopass" not in response.text
    assert "127.0.0.1" not in response.text


async def test_system_status_is_degraded_without_database() -> None:
    async with running_app(make_settings()) as client:
        response = await client.get("/api/v1/system/status")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"] == "unavailable"
    assert body["service"] == "blackforge-api"
    assert body["api_version"] == "v1"


async def test_security_headers_are_present() -> None:
    async with running_app(make_settings()) as client:
        response = await client.get("/healthz")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"
    assert "strict-transport-security" not in response.headers


async def test_hsts_only_in_production() -> None:
    settings = make_settings(app_env="production", cors_origins=["https://app.example"])
    async with running_app(settings) as client:
        response = await client.get("/healthz")
    assert "max-age" in response.headers["strict-transport-security"]


async def test_request_id_is_generated() -> None:
    async with running_app(make_settings()) as client:
        response = await client.get("/healthz")
    assert len(response.headers["x-request-id"]) >= 8


async def test_safe_incoming_request_id_is_kept_unsafe_is_replaced() -> None:
    async with running_app(make_settings()) as client:
        kept = await client.get("/healthz", headers={"X-Request-ID": "trace-abc.123_XYZ"})
        replaced = await client.get("/healthz", headers={"X-Request-ID": 'x y"<script>'})
    assert kept.headers["x-request-id"] == "trace-abc.123_XYZ"
    assert "<script>" not in replaced.headers["x-request-id"]
    assert replaced.headers["x-request-id"] != 'x y"<script>'


async def test_not_found_uses_error_envelope() -> None:
    async with running_app(make_settings()) as client:
        response = await client.get("/api/v1/nope")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"
    assert error["request_id"] == response.headers["x-request-id"]


async def test_method_not_allowed_uses_error_envelope() -> None:
    async with running_app(make_settings()) as client:
        response = await client.post("/healthz")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


async def test_validation_error_never_echoes_submitted_value() -> None:
    async with running_app(make_settings(), _add_test_routes) as client:
        response = await client.post("/api/v1/_test/credentials", json={"password": "hunter2"})
    assert response.status_code == 422
    assert "hunter2" not in response.text
    detail = response.json()["error"]["details"][0]
    assert detail["loc"] == ["body", "password"]
    assert "input" not in detail


async def test_unhandled_exception_returns_generic_500_with_headers() -> None:
    async with running_app(make_settings(), _add_test_routes) as client:
        response = await client.get("/api/v1/_test/boom")
    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "internal_error"
    assert "detail-interne" not in response.text
    assert "pw-secret" not in response.text
    assert error["request_id"] == response.headers["x-request-id"]
    assert response.headers["x-content-type-options"] == "nosniff"


async def test_unhandled_exception_is_logged_with_secrets_masked() -> None:
    captured: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(self.format(record))

    async with running_app(make_settings(log_json=True), _add_test_routes) as client:
        # create_app a (re)configuré le logging racine : on s'y branche après coup.
        from blackforge_api.core.logging import JsonFormatter

        handler = _Capture()
        handler.setFormatter(JsonFormatter())
        logging.getLogger().addHandler(handler)
        try:
            await client.get("/api/v1/_test/boom?token=query-secret")
        finally:
            logging.getLogger().removeHandler(handler)

    joined = "\n".join(captured)
    assert "unhandled_exception" in joined
    assert "pw-secret" not in joined
    assert "query-secret" not in joined  # la query string n'est jamais journalisée
    access = [json.loads(line) for line in captured if '"request"' in line]
    assert access
    assert access[0]["status"] == 500
    assert access[0]["path"] == "/api/v1/_test/boom"


async def test_cors_allows_configured_origin_only() -> None:
    async with running_app(make_settings()) as client:
        allowed = await client.get("/healthz", headers={"Origin": "http://allowed.example"})
        denied = await client.get("/healthz", headers={"Origin": "http://evil.example"})
    assert allowed.headers["access-control-allow-origin"] == "http://allowed.example"
    assert "access-control-allow-origin" not in denied.headers


async def test_rate_limit_returns_429_with_retry_after_and_spares_health() -> None:
    async with running_app(make_settings(rate_limit_per_minute=3)) as client:
        statuses = [(await client.get("/api/v1/system/status")).status_code for _ in range(5)]
        limited = await client.get("/api/v1/system/status")
        for _ in range(10):
            assert (await client.get("/healthz")).status_code == 200
    assert statuses[:3] == [200, 200, 200]
    assert statuses[3:] == [429, 429]
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) >= 1
    assert limited.json()["error"]["code"] == "rate_limited"


async def test_openapi_is_served_only_when_enabled() -> None:
    async with running_app(make_settings(docs_enabled=True)) as client:
        enabled = await client.get("/api/v1/openapi.json")
    async with running_app(make_settings(docs_enabled=False)) as client:
        disabled = await client.get("/api/v1/openapi.json")
        docs_disabled = await client.get("/api/v1/docs")
    assert enabled.status_code == 200
    assert "/api/v1/system/status" in enabled.json()["paths"]
    assert disabled.status_code == 404
    assert docs_disabled.status_code == 404


def test_token_bucket_refills_over_time() -> None:
    now = [0.0]
    buckets = TokenBuckets(per_minute=60, clock=lambda: now[0])  # 1 jeton / seconde
    assert all(buckets.take("a")[0] for _ in range(60))
    allowed, retry_after = buckets.take("a")
    assert not allowed
    assert 0.9 <= retry_after <= 1.0
    assert buckets.take("b")[0]  # un autre client n'est pas affecté
    now[0] += 2.0
    assert buckets.take("a")[0]
    assert buckets.take("a")[0]
    assert not buckets.take("a")[0]
