import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from driftless_playwright.schemas import ExecutionReceipt, RunReport, FailureCode
from driftless_playwright.config import TELEMETRY_DIR


class TelemetryFlightRecorder:
    """
    Observability and flight recorder engine.
    Records Playwright traces, screenshot receipts, latency metrics, and run summaries.
    Maintains run history accessible by the /dashboard telemetry UI.
    """
    _instance: Optional["TelemetryFlightRecorder"] = None

    def __init__(self, output_dir: Path = TELEMETRY_DIR):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.history_file = self.output_dir / "flight_recorder_history.json"
        self._history: List[Dict[str, Any]] = self._load_history()

    @classmethod
    def get_instance(cls) -> "TelemetryFlightRecorder":
        if cls._instance is None:
            cls._instance = TelemetryFlightRecorder()
        return cls._instance

    def _load_history(self) -> List[Dict[str, Any]]:
        if self.history_file.exists():
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def record_run(self, receipt: ExecutionReceipt, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Stores a run execution receipt and persists it to disk."""
        entry = receipt.model_dump()
        entry["timestamp"] = time.time()
        if metadata:
            entry["metadata"] = metadata

        self._history.append(entry)
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(self._history, f, indent=2)
        except Exception as e:
            print(f"[Telemetry] Warning writing history: {e}")

    def get_all_runs(self) -> List[Dict[str, Any]]:
        return list(self._history)

    def compute_dashboard_kpis(self) -> Dict[str, Any]:
        """Calculates live KPIs for the Flight Recorder dashboard."""
        runs = self._history
        if not runs:
            return {
                "total_runs": 0,
                "completion_rate_pct": 100.0,
                "self_healing_rate_pct": 0.0,
                "tokens_saved_pct": 100.0,
                "avg_latency_sec": 0.0,
                "runs": []
            }

        total = len(runs)
        successes = sum(1 for r in runs if r.get("success", False))
        healed = sum(1 for r in runs if len(r.get("healed_steps", [])) > 0)
        
        # Token savings: deterministic runs cost 0 tokens vs standard ~1500 tokens per full run
        total_tokens_used = sum(r.get("llm_tokens_used", 0) for r in runs)
        potential_cloud_tokens = total * 1500
        tokens_saved_pct = round(max(0.0, (1.0 - (total_tokens_used / max(1, potential_cloud_tokens)))) * 100.0, 1)

        durations = [r.get("duration_sec", 0.0) for r in runs if r.get("duration_sec", 0.0) > 0]
        avg_latency = round(sum(durations) / max(1, len(durations)), 2) if durations else 0.0

        return {
            "total_runs": total,
            "completion_rate_pct": round((successes / total) * 100.0, 1),
            "self_healing_rate_pct": round((healed / total) * 100.0, 1),
            "tokens_saved_pct": tokens_saved_pct,
            "avg_latency_sec": avg_latency,
            "runs": list(reversed(runs[-10:]))
        }

    def clear(self) -> None:
        self._history.clear()
        if self.history_file.exists():
            self.history_file.unlink()
