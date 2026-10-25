#!/usr/bin/env python3
"""Token-free watcher for a file-backed promotion gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


REQUIRED_HOURLY_CYCLES = 24


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _write_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _coverage_reasons(coverage: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    required = {"stock": "SPY", "crypto": "BTC"}
    for asset_type, benchmark in required.items():
        row = _mapping(coverage.get(asset_type))
        if str(row.get("benchmark") or "").upper() != benchmark:
            reasons.append(f"{asset_type}_benchmark")
        try:
            observations = int(row.get("observations", 0))
        except (TypeError, ValueError):
            observations = 0
        if observations <= 0:
            reasons.append(f"{asset_type}_observations")
    return reasons


def evaluate(report: Any) -> tuple[str, list[str]]:
    if not isinstance(report, Mapping):
        return "invalid", ["report_not_object"]
    gate = _mapping(report.get("gate"))
    operational = _mapping(report.get("operational_evidence"))
    reasons: list[str] = []
    if gate.get("operational_shadow_status") != "validated":
        reasons.append("operational_shadow_status")
    if gate.get("promotion_allowed") is not True:
        reasons.append("promotion_allowed")
    hourly = _mapping(operational.get("hourly_cycles"))
    try:
        completed = int(hourly.get("completed", 0))
    except (TypeError, ValueError):
        completed = 0
    if completed < REQUIRED_HOURLY_CYCLES:
        reasons.append("hourly_cycles")
    if _mapping(operational.get("market_day_boundary")).get("completed") is not True:
        reasons.append("market_day_boundary")
    reasons.extend(_coverage_reasons(_mapping(operational.get("asset_class_coverage"))))
    queue = _mapping(operational.get("queue_safety"))
    if queue.get("status") != "validated":
        reasons.append("queue_safety")
    if _mapping(queue.get("verification")).get("status") != "independently_verified":
        reasons.append("queue_safety_verification")
    if reasons:
        return "pending", sorted(set(reasons))
    return "ready", []


def check(report_path: Path, state_path: Path, *, transition_only: bool = False) -> dict[str, Any]:
    """Evaluate the report and persist state.

    The return value always describes the current state. The
    ``transition_only`` flag is retained for callers that want to know whether
    output should be emitted, but it does not hide the state from the caller.
    """
    try:
        raw = report_path.read_bytes()
        report = json.loads(raw)
    except FileNotFoundError:
        raw = b""
        report = None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raw = b""
        report = None
    if report is None:
        status, reasons = "invalid", ["evidence_unreadable"]
    else:
        status, reasons = evaluate(report)
    digest = _digest(raw)
    previous: Mapping[str, Any] = {}
    try:
        previous = _mapping(json.loads(state_path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        previous = {}
    transition = previous.get("status") != status or previous.get("evidence_digest") != digest
    state = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "reasons": reasons,
        "promotion_allowed": status == "ready",
        "evidence_digest": digest,
        "evidence_path": str(report_path),
    }
    _write_atomic(state_path, state)
    return {**state, "transition": transition}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--transition-only", action="store_true")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a human summary")
    args = parser.parse_args()
    result = check(args.evidence, args.state, transition_only=args.transition_only)
    if args.transition_only and not result["transition"]:
        return 0
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(f"promotion_gate={result['status']} reasons={','.join(result['reasons']) or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
