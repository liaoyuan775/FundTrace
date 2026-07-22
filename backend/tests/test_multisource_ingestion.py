import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import run_multisource_ingestion


def test_runner_help_bootstraps_backend_imports_without_pythonpath():
    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    result = subprocess.run(
        [sys.executable, "tools/run_multisource_ingestion.py", "--help"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert result.returncode == 0, result.stderr
    assert "--data-dir" in result.stdout


def test_ingestion_preflights_effective_model_capability_before_confirmed_graph(tmp_path, monkeypatch):
    output_dir = tmp_path / "batch"
    materials_dir = output_dir / "materials"
    oracle_dir = output_dir / "oracle"
    materials_dir.mkdir(parents=True)
    oracle_dir.mkdir()
    (materials_dir / "statement.csv").write_text("serial_number\nS-1\n", "utf-8")
    (oracle_dir / "ground_truth.json").write_text(
        json.dumps({"transactions": [], "expected_graph": {
            "node_count": 0, "edge_count": 0, "transaction_count": 0, "total_amount": 0,
        }}),
        "utf-8",
    )
    (oracle_dir / "distribution.json").write_text("[]", "utf-8")
    calls = []

    class FakeResponse:
        status_code = 201

        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

        def raise_for_status(self):
            pass

    class FakeClient:
        def __init__(self, app):
            pass

        def post(self, path, **kwargs):
            calls.append(path)
            if path == "/api/cases":
                return FakeResponse({"case_id": "CASE-TEST"})
            if path.endswith("/materials"):
                return FakeResponse([{"file_id": "FILE-1"}])
            if path.endswith("/parse?use_model=true"):
                adapter.vision_attempted = True
                adapter.vision_succeeded = True
                return FakeResponse({"material": {
                    "status": "parsed", "draft_count": 0, "error_count": 0, "warning_count": 0,
                }, "errors": [], "warnings": []})
            if path.endswith("/confirm-all"):
                return FakeResponse({})
            if path.endswith("/versions"):
                return FakeResponse({"record_count": 0})
            raise AssertionError(path)

        def get(self, path, **kwargs):
            calls.append(path)
            if path.endswith("/draft-transactions?page=1&page_size=500"):
                return FakeResponse({"items": []})
            if path.endswith("/analysis/graph"):
                return FakeResponse({"nodes": [], "edges": [], "transaction_count": 0, "total_amount": 0})
            raise AssertionError(path)

    class FakeAdapter:
        enabled = True

        def __init__(self):
            self.probe_calls = 0
            self.vision_attempted = False
            self.vision_succeeded = False

        def probe(self):
            self.probe_calls += 1
            return type("Capability", (), {
                "reachable": True,
                "text_json": True,
                "vision": self.vision_succeeded,
                "vision_attempted": self.vision_attempted,
                "message": "vision ready" if self.vision_succeeded else "vision deferred",
            })()

    adapter = FakeAdapter()
    app = SimpleNamespace(state=SimpleNamespace(qwen=adapter))
    monkeypatch.setattr(run_multisource_ingestion, "create_app", lambda settings: app)
    monkeypatch.setattr(run_multisource_ingestion, "TestClient", FakeClient)
    monkeypatch.setattr(
        run_multisource_ingestion,
        "QwenAdapter",
        lambda settings: pytest.fail("runner must probe app.state.qwen"),
        raising=False,
    )

    report = run_multisource_ingestion.run(output_dir, tmp_path / "case-data")

    assert report["model_capability"] == {
        "enabled": True,
        "reachable": True,
        "text_json": True,
        "vision_preflight": False,
        "vision_attempted": True,
        "vision": True,
        "message": "vision ready",
    }
    assert adapter.probe_calls == 2
    assert calls.index("/api/cases/CASE-TEST/draft-transactions/confirm-all") < calls.index(
        "/api/cases/CASE-TEST/analysis/graph"
    )
    assert calls.index("/api/cases/CASE-TEST/versions") < calls.index(
        "/api/cases/CASE-TEST/analysis/graph"
    )
