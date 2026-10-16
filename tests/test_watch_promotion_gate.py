import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / ".agents/skills/watch-promotion-gate/scripts/watch_promotion_gate.py"


def load_module():
    spec = importlib.util.spec_from_file_location("watch_promotion_gate", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def evidence(*, allowed: bool = True, completed: int = 24) -> dict:
    return {
        "gate": {
            "promotion_allowed": allowed,
            "operational_shadow_status": "validated" if allowed else "pending_live_evidence",
        },
        "operational_evidence": {
            "hourly_cycles": {"completed": completed},
            "market_day_boundary": {"completed": allowed},
            "queue_safety": {
                "status": "validated" if allowed else "missing",
                "verification": {"status": "independently_verified" if allowed else "missing"},
            },
            "asset_class_coverage": {
                "stock": {"benchmark": "SPY", "observations": 96},
                "crypto": {"benchmark": "BTC", "observations": 96},
            },
        },
    }


def test_ready_evidence_is_reported_once_per_digest(tmp_path):
    module = load_module()
    report = tmp_path / "evidence.json"
    state = tmp_path / "state.json"
    report.write_text(json.dumps(evidence()), encoding="utf-8")

    first = module.check(report, state, transition_only=True)
    second = module.check(report, state, transition_only=True)

    assert first["status"] == "ready"
    assert first["transition"] is True
    assert second["status"] == "ready"
    assert second["transition"] is False


def test_pending_and_invalid_evidence_fail_closed(tmp_path):
    module = load_module()
    report = tmp_path / "evidence.json"
    state = tmp_path / "state.json"

    report.write_text(json.dumps(evidence(allowed=False)), encoding="utf-8")
    pending = module.check(report, state)
    assert pending["status"] == "pending"
    assert pending["promotion_allowed"] is False

    report.write_text("not-json", encoding="utf-8")
    invalid = module.check(report, state)
    assert invalid["status"] == "invalid"
    assert invalid["promotion_allowed"] is False


def test_insufficient_cycles_cannot_be_ready(tmp_path):
    module = load_module()
    report = tmp_path / "evidence.json"
    state = tmp_path / "state.json"
    report.write_text(json.dumps(evidence(completed=23)), encoding="utf-8")

    result = module.check(report, state)

    assert result["status"] == "pending"
    assert "hourly_cycles" in result["reasons"]


def test_cli_transition_only_is_quiet_on_unchanged_state(tmp_path):
    report = tmp_path / "evidence.json"
    state = tmp_path / "state.json"
    report.write_text(json.dumps(evidence()), encoding="utf-8")
    command = [
        sys.executable,
        str(SCRIPT),
        "--evidence",
        str(report),
        "--state",
        str(state),
        "--transition-only",
        "--json",
    ]

    first = subprocess.run(command, capture_output=True, text=True, check=True)
    second = subprocess.run(command, capture_output=True, text=True, check=True)

    assert json.loads(first.stdout)["transition"] is True
    assert second.stdout == ""
