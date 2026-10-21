import json
import os
import time
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional
import numpy as np
from pydantic import BaseModel, Field
from playwright.async_api import BrowserContext, Page
from driftless_playwright.config import TELEMETRY_DIR
from driftless_playwright.schemas import FailureCode, ExecutionReceipt


def generate_trace_id() -> str:
    """Generates standard 32-character hex OpenTelemetry trace ID."""
    return uuid.uuid4().hex


def generate_span_id() -> str:
    """Generates standard 16-character hex OpenTelemetry span ID."""
    return uuid.uuid4().hex[:16]


class ExecutionSpan(BaseModel):
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    action_name: str
    step_id: Optional[str] = None
    tier_used: str = "deterministic"
    started_at: float
    ended_at: float = 0.0
    duration_ms: float = 0.0
    status: str = "PENDING"  # "SUCCESS", "FAILED", "HEALED"
    locator_used: Optional[str] = None
    network_mutation_url: Optional[str] = None
    network_mutation_status: Optional[int] = None
    error_message: Optional[str] = None
    failure_code: FailureCode = FailureCode.NONE


class RunCaptureSession:
    """
    OpenTelemetry-compatible run capture session.
    Manages Playwright tracing (.zip), W3C trace contexts, video recording,
    and microsecond span timelines for production debugging and incident post-mortems.
    """
    def __init__(self, run_id: str, output_dir: Path = TELEMETRY_DIR):
        self.run_id = run_id
        self.trace_id = generate_trace_id()
        self.root_span_id = generate_span_id()
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.spans: List[ExecutionSpan] = []
        self.start_time = time.time()
        self.trace_path = self.output_dir / f"trace_{run_id}.zip"
        self.log_path = self.output_dir / f"events_{run_id}.jsonl"

    async def start_tracing(self, context: BrowserContext) -> None:
        """Starts Playwright trace recording including screenshots, snapshots, and sources."""
        try:
            await context.tracing.start(
                name=f"run_{self.run_id}",
                screenshots=True,
                snapshots=True,
                sources=True
            )
        except Exception as e:
            print(f"[Observability] Warning starting trace: {e}")

    async def stop_tracing(self, context: BrowserContext) -> Optional[str]:
        """Stops trace and writes zip archive to disk."""
        try:
            await context.tracing.stop(path=str(self.trace_path))
            return str(self.trace_path)
        except Exception as e:
            print(f"[Observability] Warning stopping trace: {e}")
            return None

    def start_span(
        self,
        action_name: str,
        step_id: Optional[str] = None,
        tier_used: str = "deterministic",
        parent_span_id: Optional[str] = None
    ) -> ExecutionSpan:
        span = ExecutionSpan(
            trace_id=self.trace_id,
            span_id=generate_span_id(),
            parent_span_id=parent_span_id or self.root_span_id,
            action_name=action_name,
            step_id=step_id,
            tier_used=tier_used,
            started_at=time.time()
        )
        self.spans.append(span)
        return span

    def finish_span(
        self,
        span: ExecutionSpan,
        status: str = "SUCCESS",
        locator_used: Optional[str] = None,
        error_message: Optional[str] = None,
        failure_code: FailureCode = FailureCode.NONE,
        mutation_url: Optional[str] = None,
        mutation_status: Optional[int] = None
    ) -> None:
        span.ended_at = time.time()
        span.duration_ms = round((span.ended_at - span.started_at) * 1000.0, 2)
        span.status = status
        span.locator_used = locator_used
        span.error_message = error_message
        span.failure_code = failure_code
        span.network_mutation_url = mutation_url
        span.network_mutation_status = mutation_status
        self._append_log(span)

    def _append_log(self, span: ExecutionSpan) -> None:
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(span.model_dump_json() + "\n")
        except Exception:
            pass

    def get_summary(self) -> Dict[str, Any]:
        total_duration = time.time() - self.start_time
        span_count = len(self.spans)
        failed_spans = [s for s in self.spans if s.status == "FAILED"]
        healed_spans = [s for s in self.spans if s.status == "HEALED"]
        return {
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "w3c_traceparent": f"00-{self.trace_id}-{self.root_span_id}-01",
            "total_duration_sec": round(total_duration, 3),
            "total_spans": span_count,
            "failed_spans": len(failed_spans),
            "healed_spans": len(healed_spans),
            "trace_path": str(self.trace_path) if self.trace_path.exists() else None,
            "log_path": str(self.log_path) if self.log_path.exists() else None,
            "spans": [s.model_dump() for s in self.spans]
        }


class GlobalTelemetryStore:
    """
    In-memory and persistent OpenTelemetry metrics engine.
    Calculates P50/P95/P99 latency percentiles, throughput, and failure breakdowns.
    """
    _instance: Optional["GlobalTelemetryStore"] = None

    def __init__(self, output_dir: Path = TELEMETRY_DIR):
        self.output_dir = output_dir
        self.boot_time = time.time()
        self.recent_spans: List[Dict[str, Any]] = []
        self.recent_runs: List[Dict[str, Any]] = []

    @classmethod
    def get_instance(cls) -> "GlobalTelemetryStore":
        if cls._instance is None:
            cls._instance = GlobalTelemetryStore()
        return cls._instance

    def record_completed_run(self, receipt: ExecutionReceipt, trace_id: Optional[str] = None, spans: Optional[List[Dict[str, Any]]] = None) -> None:
        entry = receipt.model_dump()
        entry["trace_id"] = trace_id or generate_trace_id()
        entry["timestamp"] = time.time()
        entry["spans_count"] = len(spans) if spans else 0
        self.recent_runs.append(entry)
        if spans:
            self.recent_spans.extend(spans)
            # Keep last 200 spans
            if len(self.recent_spans) > 200:
                self.recent_spans = self.recent_spans[-200:]

    def get_telemetry_stats(self) -> Dict[str, Any]:
        runs = self.recent_runs
        durations_ms = [r.get("duration_sec", 0.0) * 1000.0 for r in runs if r.get("duration_sec", 0.0) > 0]
        
        p50 = float(np.percentile(durations_ms, 50)) if durations_ms else 0.0
        p95 = float(np.percentile(durations_ms, 95)) if durations_ms else 0.0
        p99 = float(np.percentile(durations_ms, 99)) if durations_ms else 0.0
        avg_ms = float(np.mean(durations_ms)) if durations_ms else 0.0

        total = len(runs)
        successes = sum(1 for r in runs if r.get("success", False))
        healed = sum(1 for r in runs if len(r.get("healed_steps", [])) > 0)
        
        failure_breakdown: Dict[str, int] = {}
        for r in runs:
            code = str(r.get("failure_code", "NONE"))
            if code != "NONE":
                failure_breakdown[code] = failure_breakdown.get(code, 0) + 1

        return {
            "success": True,
            "serviceName": "driftless-playwright-execution-engine",
            "activeTracing": True,
            "uptimeSeconds": int(time.time() - self.boot_time),
            "stats": {
                "totalRecordedRuns": total,
                "completionRatePct": round((successes / max(1, total)) * 100.0, 1),
                "selfHealingRatePct": round((healed / max(1, total)) * 100.0, 1),
                "latency": {
                    "avgMs": round(avg_ms, 1),
                    "p50Ms": round(p50, 1),
                    "p95Ms": round(p95, 1),
                    "p99Ms": round(p99, 1)
                },
                "failureTaxonomy": failure_breakdown
            },
            "recentTraces": list(reversed(runs[-15:]))
        }

    def clear(self) -> None:
        self.recent_runs.clear()
        self.recent_spans.clear()
