import pytest
import httpx
from sandbox_portal.server import app
from driftless_playwright.observability import GlobalTelemetryStore, RunCaptureSession
from driftless_playwright.schemas import ExecutionReceipt


@pytest.mark.asyncio
async def test_health_check_endpoint():
    """Verify /health endpoint matches production observability standards."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "driftless-playwright-execution-engine"
        assert "uptimeSeconds" in data
        assert data["activeTracing"] is True
        # Check X-Trace-Id header presence
        assert "x-trace-id" in resp.headers


@pytest.mark.asyncio
async def test_telemetry_stats_endpoint():
    """Verify /api/v1/telemetry/stats endpoint matches OpenTelemetry format."""
    store = GlobalTelemetryStore.get_instance()
    # Seed a receipt
    receipt = ExecutionReceipt(
        run_id="run_otel_test_1",
        merchant_id="streampulse",
        workflow_type="cancel",
        success=True,
        terminal_reward=10.0,
        total_reward=10.0,
        network_confirmed=True,
        dom_confirmed=True,
        visual_confirmed=True,
        duration_sec=1.15
    )
    store.record_completed_run(receipt, trace_id="4bf92f3577b34da6a3ce929d0e0e4736")

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/telemetry/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["serviceName"] == "driftless-playwright-execution-engine"
        assert data["activeTracing"] is True
        
        stats = data["stats"]
        assert "totalRecordedRuns" in stats
        assert "latency" in stats
        assert "p50Ms" in stats["latency"]
        assert "p95Ms" in stats["latency"]
        assert "p99Ms" in stats["latency"]
        assert len(data["recentTraces"]) >= 1
        assert data["recentTraces"][0]["trace_id"] == "4bf92f3577b34da6a3ce929d0e0e4736"


@pytest.mark.asyncio
async def test_telemetry_spans_endpoint():
    """Verify /api/v1/telemetry/spans endpoint returns recent microsecond trace spans."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/telemetry/spans")
        assert resp.status_code == 200
        data = resp.json()
        assert "spans" in data
