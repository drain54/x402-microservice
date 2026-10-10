import json
import logging
import time
from pathlib import Path
from typing import Dict, Any, Optional

BASE_DIR = Path(__file__).resolve().parent
LOG_PATH = BASE_DIR / "usage.jsonl"

logger = logging.getLogger("x402_telemetry")

class TelemetryStore:
    def __init__(self, log_path: Path = LOG_PATH):
        self.log_path = log_path

    def log_event(self, path: str, method: str, remote: str, result: str, metadata: Optional[Dict[str, Any]] = None):
        """
        Appends an empirical telemetry event to usage.jsonl.
        Result enum values:
        - free_handshake
        - 402_no_payment
        - 402_invalid_payment
        - 502_settle_failed
        - paid_ok
        - 500_paid_crash
        """
        record = {
            "ts": time.time(),
            "datetime": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "path": path,
            "method": method,
            "remote": remote,
            "result": result,
            "metadata": metadata or {}
        }
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            logger.error(f"Failed to record telemetry log: {e}")

    def get_summary(self) -> Dict[str, Any]:
        """Calculates machine-verifiable operational metrics from usage.jsonl."""
        if not self.log_path.exists():
            return {
                "sample_size": 0,
                "uptime": 1.0,
                "success_rate": 1.0,
                "paid_requests_total": 0,
                "results_breakdown": {}
            }

        counts: Dict[str, int] = {}
        total = 0
        successful_paid = 0
        total_paid_attempts = 0

        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    res = data.get("result", "unknown")
                    counts[res] = counts.get(res, 0) + 1
                    total += 1
                    if res in ("paid_ok", "502_settle_failed", "500_paid_crash"):
                        total_paid_attempts += 1
                    if res == "paid_ok":
                        successful_paid += 1
                except Exception:
                    continue

        success_rate = (successful_paid / total_paid_attempts) if total_paid_attempts > 0 else 1.0

        return {
            "sample_size": total,
            "paid_attempts": total_paid_attempts,
            "paid_successful": successful_paid,
            "success_rate": round(success_rate, 4),
            "results_breakdown": counts
        }

telemetry = TelemetryStore()
